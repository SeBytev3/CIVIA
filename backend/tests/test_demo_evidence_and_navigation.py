"""
CIVIA - Pruebas de Integridad de Evidencias Sintéticas Fotorrealistas y Actualización Idempotente
Verifica:
1. Integridad de los 10 activos fotográficos empaquetados localmente (resolución 1200x896, JPEG, SHA-256).
2. Sembrado de reportes sintéticos con los nuevos metadatos fotográficos.
3. Procedimiento idempotente de actualización sin afectar reportes reales ni aprobaciones.
4. Servicio correcto de la evidencia a través del endpoint /api/reports/{id}/photo.
5. Presencia y consistencia de las muestras de demostración en frontend/public/demo_evidence.
"""

import hashlib
import io
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.db import get_conn
from app.main import app
from app.seed import (
    DEMO_ASSETS_DIR,
    SYNTHETIC_REPORTS,
    get_synthetic_evidence_bytes,
    seed_synthetic_reports,
    update_synthetic_catalog_photos,
)
from tests.conftest import register_test_report_id


def test_packaged_assets_integrity():
    """Valida que los 10 activos fotográficos fotorrealistas existan y cumplan especificaciones."""
    assert DEMO_ASSETS_DIR.exists(), f"Directorio {DEMO_ASSETS_DIR} no encontrado."

    for item in SYNTHETIC_REPORTS:
        code = item["tracking_code"]
        data, filename, mime, width, height = get_synthetic_evidence_bytes(code, item["ai_category"])

        assert mime == "image/jpeg", f"{code} debe ser image/jpeg"
        assert width == 1200, f"{code} debe tener ancho 1200"
        assert height == 896, f"{code} debe tener alto 896"
        assert filename == f"synthetic_{code.lower()}.jpg"
        assert len(data) > 100_000, f"{code} debe ser una fotografía de alta resolución (>100KB)"

        im = Image.open(io.BytesIO(data))
        assert im.format == "JPEG"
        assert im.size == (1200, 896)


def test_frontend_samples_consistency():
    """Verifica que las muestras por categoría en frontend/public/demo_evidence existan y sean válidas."""
    frontend_demo_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "demo_evidence"
    assert frontend_demo_dir.exists(), f"Directorio {frontend_demo_dir} no encontrado."

    required_samples = ["sample_hueco.jpg", "sample_basuras.jpg", "sample_tala.jpg", "sample_quema.jpg", "sample_otro.jpg"]
    for sample in required_samples:
        sample_path = frontend_demo_dir / sample
        assert sample_path.exists(), f"Muestra {sample} no encontrada en frontend."
        data = sample_path.read_bytes()
        assert len(data) > 100_000

        im = Image.open(io.BytesIO(data))
        assert im.format == "JPEG"
        assert im.size == (1200, 896)


def test_seed_synthetic_reports_with_new_assets():
    """Verifica que el seed inserte los 10 reportes sintéticos con los nuevos metadatos fotográficos."""
    result = seed_synthetic_reports(force_reset=True)
    assert result["total_synthetic_catalog"] == 10
    assert result["inserted"] == 10

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tracking_code, photo_path, photo_mime, photo_width, photo_height,
                       photo_size_bytes, photo_sha256, is_synthetic
                FROM reports
                WHERE tracking_code LIKE 'CIV-2026-DEMO%'
                ORDER BY tracking_code;
                """
            )
            rows = cur.fetchall()
            assert len(rows) == 10

            for r in rows:
                assert r["is_synthetic"] is True
                assert r["photo_mime"] == "image/jpeg"
                assert r["photo_width"] == 1200
                assert r["photo_height"] == 896
                assert r["photo_path"].startswith("synthetic_civ-2026-demo")
                assert r["photo_path"].endswith(".jpg")
                assert r["photo_size_bytes"] > 100_000
                assert len(r["photo_sha256"]) == 64


def test_update_synthetic_catalog_photos_idempotent_and_safe():
    """
    Verifica que la actualización de fotos sintéticas:
    1. Actualice exclusivamente los 10 reportes de catálogo sintético.
    2. Respete íntegramente los reportes reales de usuario (is_synthetic = FALSE).
    3. Sea completamente idempotente en ejecuciones repetidas.
    """
    # 1. Sembrar el catálogo inicial
    seed_synthetic_reports(force_reset=True)

    # 2. Insertar un reporte real creado por un ciudadano ficticio
    real_report_id = uuid4()
    register_test_report_id(real_report_id)
    real_code = f"CIV-2026-REAL{uuid4().hex[:6].upper()}"
    dummy_photo_data = b"REAL_CITIZEN_PHOTO_DATA_12345"
    dummy_sha = hashlib.sha256(dummy_photo_data).hexdigest()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reports (
                    id, tracking_code, title, description,
                    latitude, longitude, in_service_area,
                    photo_path, photo_mime, photo_size_bytes,
                    photo_width, photo_height, photo_sha256,
                    final_category, final_severity,
                    human_confirmed, status, is_synthetic
                )
                VALUES (
                    %s, %s, 'Reporte real ciudadano', 'Descripción real de prueba de integridad',
                    3.4516, -76.5320, TRUE,
                    'real_citizen_photo.png', 'image/png', %s,
                    640, 480, %s,
                    'HUECO', 'MEDIA',
                    FALSE, 'PENDING_ANALYSIS', FALSE
                );
                """,
                (real_report_id, real_code, len(dummy_photo_data), dummy_sha),
            )
            # Simular que los reportes demo tenían metadatos antiguos (ej. 240x160 png)
            cur.execute(
                """
                UPDATE reports
                SET photo_path = 'old_paint_image.png',
                    photo_mime = 'image/png',
                    photo_width = 240,
                    photo_height = 160,
                    photo_sha256 = '0000000000000000000000000000000000000000000000000000000000000000'
                WHERE is_synthetic = TRUE;
                """
            )
            conn.commit()

    # 3. Ejecutar la actualización controlada de fotos
    res1 = update_synthetic_catalog_photos()
    assert res1["updated"] == 10
    assert res1["unchanged"] == 0

    # 4. Verificar que los reportes demo se actualizaron
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT photo_mime, photo_width, photo_height FROM reports WHERE is_synthetic = TRUE;")
            for r in cur.fetchall():
                assert r["photo_mime"] == "image/jpeg"
                assert r["photo_width"] == 1200
                assert r["photo_height"] == 896

            # Verificar que el reporte real ciudadano NO FUE TOCADO
            cur.execute("SELECT photo_path, photo_mime, photo_width, photo_height, photo_sha256, is_synthetic FROM reports WHERE id = %s;", (real_report_id,))
            real_row = cur.fetchone()
            assert real_row["is_synthetic"] is False
            assert real_row["photo_path"] == "real_citizen_photo.png"
            assert real_row["photo_mime"] == "image/png"
            assert real_row["photo_width"] == 640
            assert real_row["photo_height"] == 480
            assert real_row["photo_sha256"] == dummy_sha

    # 5. Ejecutar por segunda vez para verificar IDEMPOTENCIA
    res2 = update_synthetic_catalog_photos()
    assert res2["updated"] == 0
    assert res2["unchanged"] == 10
    assert res2["catalog_total"] == 10


def test_photo_endpoint_serves_new_asset():
    """Verifica que /api/reports/{id}/photo sirva la nueva imagen fotorrealista con sus encabezados de seguridad."""
    seed_synthetic_reports(force_reset=True)

    client = TestClient(app)
    # Obtener el primer reporte demo
    rep_res = client.get("/api/reports/by-code/CIV-2026-DEMO0001")
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    rep_id = rep_data["id"]

    # Solicitar la foto
    photo_res = client.get(f"/api/reports/{rep_id}/photo")
    assert photo_res.status_code == 200
    assert photo_res.headers["content-type"] == "image/jpeg"
    assert photo_res.headers["x-content-type-options"] == "nosniff"
    assert len(photo_res.content) > 100_000

    # Validar que los bytes recibidos son un JPEG válido
    im = Image.open(io.BytesIO(photo_res.content))
    assert im.format == "JPEG"
    assert im.size == (1200, 896)
