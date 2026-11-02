import io
import struct
import wave

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.config import settings
from app.db import run_migrations
from app.main import app
from app.security import rate_limiter
from app.seed import seed_synthetic_reports
from tests.conftest import restore_db_snapshot, snapshot_db_state


@pytest.fixture(scope="module", autouse=True)
def setup_db_and_seed():
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    run_migrations()
    seed_synthetic_reports(force_reset=False)
    snap = snapshot_db_state()
    yield
    restore_db_snapshot(snap)


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


def make_test_image_bytes(width: int = 64, height: int = 64, fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (width, height), color=(120, 60, 40))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def make_test_wav_bytes(duration_seconds: float = 2.0, sample_rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    num_frames = int(duration_seconds * sample_rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * num_frames, *([0] * num_frames)))
    return buf.getvalue()


client = TestClient(app)


def test_health_and_db_ready():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["db"]["connected"] is True
    assert body["db"]["schema_ready"] is True


def test_synthetic_fixtures_loaded_and_identifiable():
    res = client.get("/api/reports?limit=50")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 10
    demo1 = next((item for item in data["items"] if item["tracking_code"] == "CIV-2026-DEMO0001"), None)
    assert demo1 is not None
    assert demo1["is_synthetic"] is True
    assert demo1["effective_category"] == "HUECO"
    assert demo1["comuna"] == "Comuna 2"

    # Lookup por código de seguimiento
    res_code = client.get("/api/reports/by-code/CIV-2026-DEMO0001")
    assert res_code.status_code == 200
    assert res_code.json()["id"] == demo1["id"]


def test_create_report_and_pii_sanitization_and_photo_serving():
    img_bytes = make_test_image_bytes(80, 60, "JPEG")
    wav_bytes = make_test_wav_bytes(1.5)

    resp = client.post(
        "/api/reports",
        data={
            "title": "<b>Hueco peligroso en barrio Granada</b>",
            "description": "Hay un hueco grande en la vía. Escríbanme a usuario@correo.com o al 315 222 3344 por favor.",
            "latitude": "3.4572",
            "longitude": "-76.5345",
            "comuna": "Comuna 2",
            "neighborhood": "Granada",
            "address_hint": "Avenida 9N # 14N-20",
            "auto_analyze": "false",
        },
        files={
            "photo": ("evidencia.jpg", img_bytes, "image/jpeg"),
            "audio": ("nota.wav", wav_bytes, "audio/wav"),
        },
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["title"] == "Hueco peligroso en barrio Granada"
    assert "[CORREO_PROTEGIDO]" in created["description"]
    assert "[TELEFONO_PROTEGIDO]" in created["description"]
    assert "usuario@correo.com" not in created["description"]
    assert "315 222 3344" not in created["description"]
    assert created["in_service_area"] is True
    assert created["has_audio"] is True
    assert created["status"] == "PENDING_ANALYSIS"
    assert created["is_synthetic"] is False

    report_id = created["id"]
    edit_token = created["citizen_edit_token"]
    assert edit_token is not None and len(edit_token) >= 32

    # Verificar que la foto se sirve con cabeceras seguras
    photo_resp = client.get(f"/api/reports/{report_id}/photo")
    assert photo_resp.status_code == 200
    assert photo_resp.headers["content-type"] == "image/jpeg"
    assert photo_resp.headers["x-content-type-options"] == "nosniff"
    assert len(photo_resp.content) > 100

    # Confirmar / editar categoría por humano con credencial del reporte
    confirm_resp = client.patch(
        f"/api/reports/{report_id}/confirm",
        headers={"X-Citizen-Edit-Token": edit_token},
        json={
            "final_category": "HUECO",
            "final_severity": "ALTA",
            "human_override_note": "Confirmado por ciudadano en sitio.",
        },
    )
    assert confirm_resp.status_code == 200
    confirmed = confirm_resp.json()
    assert confirmed["human_confirmed"] is True
    assert confirmed["final_category"] == "HUECO"
    assert confirmed["effective_category"] == "HUECO"
    assert confirmed["status"] == "CONFIRMED"

    admin_headers = {"X-Admin-Token": settings.ADMIN_TOKEN}

    # Cambio de estado sin aprobación humana debe rechazarse
    bad_status = client.patch(
        f"/api/reports/{report_id}/status",
        headers=admin_headers,
        json={"status": "IN_REVIEW", "human_approved": False},
    )
    assert bad_status.status_code == 400
    assert bad_status.json()["error"] == "HUMAN_APPROVAL_REQUIRED"

    # Cambio de estado con autenticación admin y aprobación humana explícita
    ok_status = client.patch(
        f"/api/reports/{report_id}/status",
        headers=admin_headers,
        json={"status": "IN_REVIEW", "human_approved": True, "note": "Asignado a cuadrilla vial."},
    )
    assert ok_status.status_code == 200
    assert ok_status.json()["status"] == "IN_REVIEW"


def test_security_rejects_invalid_files_and_coordinates():
    valid_img = make_test_image_bytes(64, 64, "PNG")

    # 1. Archivo que no es imagen disfrazado de .jpg
    r_fake = client.post(
        "/api/reports",
        data={
            "description": "Reporte con archivo ejecutable o texto falso.",
            "latitude": "3.45",
            "longitude": "-76.53",
        },
        files={"photo": ("malware.jpg", b"#!/bin/sh\necho hacked", "image/jpeg")},
    )
    assert r_fake.status_code == 415
    assert r_fake.json()["error"] == "UNSUPPORTED_MEDIA_TYPE"

    # 2. Imagen de 1x1 píxel (< 32x32 mínimo requerido)
    tiny_img = make_test_image_bytes(1, 1, "PNG")
    r_tiny = client.post(
        "/api/reports",
        data={
            "description": "Reporte con imagen de 1x1 pixel inválida.",
            "latitude": "3.45",
            "longitude": "-76.53",
        },
        files={"photo": ("tiny.png", tiny_img, "image/png")},
    )
    assert r_tiny.status_code == 422

    # 3. Archivo mayor a 5 MB
    oversized = b"\x89PNG\r\n\x1a\n" + (b"0" * (5 * 1024 * 1024 + 100))
    r_big = client.post(
        "/api/reports",
        data={
            "description": "Reporte con fotografía demasiado pesada.",
            "latitude": "3.45",
            "longitude": "-76.53",
        },
        files={"photo": ("huge.png", oversized, "image/png")},
    )
    assert r_big.status_code == 413
    assert r_big.json()["error"] == "FILE_TOO_LARGE"

    # 4. Coordenadas fuera de rango o Null Island (0, 0)
    r_null_island = client.post(
        "/api/reports",
        data={
            "description": "Coordenadas en punto cero del océano.",
            "latitude": "0.0",
            "longitude": "0.0",
        },
        files={"photo": ("ok.png", valid_img, "image/png")},
    )
    assert r_null_island.status_code == 422

    r_out_of_bounds = client.post(
        "/api/reports",
        data={
            "description": "Latitud imposible fuera del planeta.",
            "latitude": "98.5",
            "longitude": "-76.53",
        },
        files={"photo": ("ok.png", valid_img, "image/png")},
    )
    assert r_out_of_bounds.status_code == 422

    # 5. Audio WAV mayor a 60 segundos
    long_wav = make_test_wav_bytes(duration_seconds=62.0, sample_rate=4000)
    r_long_audio = client.post(
        "/api/reports",
        data={
            "description": "Reporte con nota de voz que excede un minuto.",
            "latitude": "3.45",
            "longitude": "-76.53",
        },
        files={
            "photo": ("ok.png", valid_img, "image/png"),
            "audio": ("largo.wav", long_wav, "audio/wav"),
        },
    )
    assert r_long_audio.status_code == 422
    assert r_long_audio.json()["error"] == "AUDIO_TOO_LONG"


def test_spatial_and_category_filtering():
    # Búsqueda por categoría QUEMA
    r_quema = client.get("/api/reports?category=QUEMA")
    assert r_quema.status_code == 200
    items_q = r_quema.json()["items"]
    assert len(items_q) >= 2
    assert all(i["effective_category"] == "QUEMA" for i in items_q)

    # Búsqueda espacial alrededor de Avenida Sexta (3.4658, -76.5283) en radio de 2.0 km
    r_geo = client.get("/api/reports?lat=3.4658&lon=-76.5283&radius_km=2.0")
    assert r_geo.status_code == 200
    geo_items = r_geo.json()["items"]
    assert len(geo_items) >= 1
    assert geo_items[0]["tracking_code"] == "CIV-2026-DEMO0001"
    assert geo_items[0]["distance_km"] is not None
    assert geo_items[0]["distance_km"] <= 0.1
    # Verificar orden ascendente por distancia
    distances = [x["distance_km"] for x in geo_items]
    assert distances == sorted(distances)


def test_rate_limiter_enforced(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX_REQUESTS", 2)
    valid_img = make_test_image_bytes(64, 64, "PNG")

    for _ in range(2):
        r = client.post(
            "/api/reports",
            data={
                "description": "Prueba de límite de velocidad ciudadano.",
                "latitude": "3.44",
                "longitude": "-76.52",
                "auto_analyze": "false",
            },
            files={"photo": ("ok.png", valid_img, "image/png")},
        )
        assert r.status_code == 201

    r_blocked = client.post(
        "/api/reports",
        data={
            "description": "Tercer envío consecutivo debe recibir 429 amigable.",
            "latitude": "3.44",
            "longitude": "-76.52",
        },
        files={"photo": ("ok.png", valid_img, "image/png")},
    )
    assert r_blocked.status_code == 429
    assert r_blocked.json()["error"] == "RATE_LIMIT_EXCEEDED"
