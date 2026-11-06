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


def test_update_synthetic_catalog_photos_detects_same_length_corruption():
    """
    Verifica que update_synthetic_catalog_photos() detecte corrupción de igual longitud
    y no se confíe únicamente en st_size.
    Si el archivo en disco tiene un byte alterado pero conserva el tamaño exacto,
    debe identificar el desajuste de SHA-256/PIL y restaurar el archivo sano.
    """
    seed_synthetic_reports(force_reset=True)

    demo1_path = settings.UPLOAD_DIR / "synthetic_civ-2026-demo0001.jpg"
    assert demo1_path.exists()
    original_bytes = demo1_path.read_bytes()
    original_size = len(original_bytes)
    original_sha = hashlib.sha256(original_bytes).hexdigest()

    # Corromper el primer byte pero preservando exactamente el tamaño
    corrupt_bytes = b"X" + original_bytes[1:]
    assert len(corrupt_bytes) == original_size
    demo1_path.write_bytes(corrupt_bytes)

    # Ejecutar actualizador
    res = update_synthetic_catalog_photos()
    # Debe detectar la corrupción y reparar exactamente 1 archivo
    assert res["updated"] == 1
    assert res["unchanged"] == 9

    # Verificar que el archivo en disco quedó restaurado e íntegro
    restored_bytes = demo1_path.read_bytes()
    assert hashlib.sha256(restored_bytes).hexdigest() == original_sha
    im = Image.open(io.BytesIO(restored_bytes))
    im.verify()


def test_update_synthetic_catalog_photos_zero_orphans_on_rollback():
    """
    Verifica que ante un fallo o rollback en la transacción SQL de actualización,
    no queden archivos huérfanos ni archivos temporales (.tmp_*) en UPLOAD_DIR.
    """
    seed_synthetic_reports(force_reset=True)

    # Contar archivos antes
    initial_files = set(settings.UPLOAD_DIR.iterdir())

    # 1. Modificar metadatos en BD para forzar actualización de DEMO0002
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reports SET photo_sha256 = '0000000000000000000000000000000000000000000000000000000000000000' WHERE tracking_code = 'CIV-2026-DEMO0002';"
            )
            conn.commit()

    # 2. Instalar trigger que aborte cuando update_synthetic_catalog_photos intente actualizar DEMO0002
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE OR REPLACE FUNCTION raise_test_abort()
                RETURNS trigger AS $$
                BEGIN
                    IF NEW.tracking_code = 'CIV-2026-DEMO0002' THEN
                        RAISE EXCEPTION 'TEST_INJECTED_ABORT_FOR_ROLLBACK';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                DROP TRIGGER IF EXISTS trg_test_abort_demo ON reports;
                CREATE TRIGGER trg_test_abort_demo
                BEFORE UPDATE ON reports
                FOR EACH ROW EXECUTE FUNCTION raise_test_abort();
                """
            )
            conn.commit()

    try:
        # Al ejecutar la actualización, el trigger abortará la transacción
        with pytest.raises(Exception) as exc_info:
            update_synthetic_catalog_photos()
        assert "TEST_INJECTED_ABORT_FOR_ROLLBACK" in str(exc_info.value)

        # Verificar que NO hay archivos temporales .tmp_*
        tmp_files = list(settings.UPLOAD_DIR.glob("*.tmp_*"))
        assert len(tmp_files) == 0, f"Quedaron archivos temporales huérfanos: {tmp_files}"

    finally:
        # Limpiar trigger de prueba
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TRIGGER IF EXISTS trg_test_abort_demo ON reports;")
                cur.execute("DROP FUNCTION IF EXISTS raise_test_abort();")
                conn.commit()


def test_update_synthetic_catalog_photos_fs_failure_compensates_and_rolls_back(monkeypatch):
    """
    Verifica que si ocurre un fallo en os.replace durante la publicación en disco:
    1. Se interrumpe la operación antes del commit SQL.
    2. Se compensa restaurando los archivos originales desde sus backups temporales.
    3. No quedan archivos temporales (.tmp_*) ni backups (.bak_*).
    4. En PostgreSQL las filas conservan sus valores previos.
    """
    seed_synthetic_reports(force_reset=True)

    # Forzar actualización en DEMO0001 y DEMO0002
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reports SET photo_sha256 = '0000000000000000000000000000000000000000000000000000000000000000' WHERE tracking_code IN ('CIV-2026-DEMO0001', 'CIV-2026-DEMO0002');"
            )
            conn.commit()

    import os
    real_replace = os.replace
    call_count = 0

    def faulty_replace(src, dst):
        nonlocal call_count
        call_count += 1
        # Fallar durante la publicación de reemplazo
        if call_count >= 3:
            raise OSError("INJECTED_DISK_IO_FAILURE_ON_REPLACE")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", faulty_replace)

    with pytest.raises(OSError) as exc_info:
        update_synthetic_catalog_photos()
    assert "INJECTED_DISK_IO_FAILURE_ON_REPLACE" in str(exc_info.value)

    # Restaurar replace real
    monkeypatch.setattr(os, "replace", real_replace)

    # Verificar que no quedaron temporales .tmp_* ni .bak_*
    tmp_files = list(settings.UPLOAD_DIR.glob("*.tmp_*")) + list(settings.UPLOAD_DIR.glob("*.bak_*"))
    assert len(tmp_files) == 0, f"Quedaron residuos temporales: {tmp_files}"

    # Verificar que el commit SQL NO se ejecutó: las filas siguen en '0000...'
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT photo_sha256 FROM reports WHERE tracking_code = 'CIV-2026-DEMO0002';")
            assert cur.fetchone()["photo_sha256"] == "0000000000000000000000000000000000000000000000000000000000000000"


def test_update_synthetic_catalog_photos_recovers_after_interruption():
    """
    Verifica que si una sesión previa se interrumpió dejando archivos .tmp_* y .bak_* residuales,
    el inicio de update_synthetic_catalog_photos() los limpie y complete la reconciliación.
    """
    seed_synthetic_reports(force_reset=True)

    # Inyectar archivos residuales simulando corte previo
    residual_tmp = settings.UPLOAD_DIR / "synthetic_civ-2026-demo0001.jpg.tmp_abandoned123"
    residual_bak = settings.UPLOAD_DIR / "synthetic_civ-2026-demo0002.jpg.bak_abandoned456"
    residual_tmp.write_bytes(b"RESIDUAL_ORPHAN_DATA_1")
    residual_bak.write_bytes(b"RESIDUAL_ORPHAN_DATA_2")

    # Forzar que DEMO0003 esté desincronizado
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE reports SET photo_sha256 = 'desync_sha' WHERE tracking_code = 'CIV-2026-DEMO0003';")
            conn.commit()

    # Ejecutar actualizador
    res = update_synthetic_catalog_photos()
    assert res["updated"] == 1
    assert res["unchanged"] == 9

    # Verificar que los residuos fueron limpiados
    assert not residual_tmp.exists()
    assert not residual_bak.exists()
    assert len(list(settings.UPLOAD_DIR.glob("*.tmp_*"))) == 0
    assert len(list(settings.UPLOAD_DIR.glob("*.bak_*"))) == 0


def test_photo_endpoint_versioning_etag_and_caching():
    """
    Verifica:
    1. photo_url incluye parámetro ?v={sha[:16]}
    2. Endpoint /photo sirve con Cache-Control immutable para URL versionada
    3. Soporta ETag y responde HTTP 304 Not Modified con If-None-Match
    4. URL canónica (sin versión) responde con must-revalidate
    """
    seed_synthetic_reports(force_reset=True)
    client = TestClient(app)

    rep_res = client.get("/api/reports/by-code/CIV-2026-DEMO0001")
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    photo_url = rep_data["photo_url"]
    rep_id = rep_data["id"]

    assert "?v=" in photo_url, f"photo_url debe estar versionada: {photo_url}"
    version_param = photo_url.split("?v=")[1]
    assert len(version_param) == 16

    # 1. Solicitud a URL versionada
    v_res = client.get(photo_url)
    assert v_res.status_code == 200
    assert "public, max-age=31536000, immutable" in v_res.headers.get("cache-control", "")
    etag = v_res.headers.get("etag")
    assert etag is not None

    # 2. Solicitud condicional con If-None-Match
    not_mod_res = client.get(photo_url, headers={"If-None-Match": etag})
    assert not_mod_res.status_code == 304

    # 3. Solicitud a URL canónica (sin ?v)
    canon_res = client.get(f"/api/reports/{rep_id}/photo")
    assert canon_res.status_code == 200
    assert "must-revalidate" in canon_res.headers.get("cache-control", "")


def test_synthetic_photo_ethical_provenance_enforced_on_server():
    """
    Verifica el principio de procedencia certificada por servidor:
    1. Si un usuario sube una muestra oficial del catálogo sintético (aun enviando is_synthetic=False),
       el servidor impone criptográficamente is_synthetic = TRUE.
    2. Si un usuario sube una fotografía arbitraria/externa pretendiendo marcarla con is_synthetic=True,
       el servidor NO confunde esa marca voluntaria con procedencia certificada y guarda is_synthetic = FALSE.
    """
    seed_synthetic_reports(force_reset=True)
    client = TestClient(app)

    # Caso 1: Foto del catálogo oficial enviada con is_synthetic=false -> Servidor certifica is_synthetic=True
    sample_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "demo_evidence" / "sample_hueco.jpg"
    assert sample_path.exists()
    sample_bytes = sample_path.read_bytes()

    payload_sample = {
        "description": "Reporte ciudadano común con fotografía de prueba enviada sin marca",
        "latitude": 3.4516,
        "longitude": -76.5320,
        "is_synthetic": "false",
        "auto_analyze": "false",
    }
    files_sample = {
        "photo": ("evidencia.jpg", io.BytesIO(sample_bytes), "image/jpeg"),
    }

    create_res = client.post("/api/reports", data=payload_sample, files=files_sample)
    assert create_res.status_code == 201
    created_official = create_res.json()
    register_test_report_id(created_official["id"])

    assert created_official["is_synthetic"] is True

    # Caso 2: Fotografía externa/arbitraria enviada con is_synthetic=true -> Servidor guarda is_synthetic=False
    # Generar una imagen JPEG válida externa no presente en el catálogo
    test_img = Image.new("RGB", (640, 480), color=(120, 180, 240))
    buf = io.BytesIO()
    test_img.save(buf, format="JPEG")
    arbitrary_bytes = buf.getvalue()

    payload_arbitrary = {
        "description": "Reporte ciudadano ordinario donde cliente envía is_synthetic=true fraudulentamente",
        "latitude": 3.4520,
        "longitude": -76.5330,
        "is_synthetic": "true",
        "auto_analyze": "false",
    }
    files_arbitrary = {
        "photo": ("camara_usuario.jpg", io.BytesIO(arbitrary_bytes), "image/jpeg"),
    }

    create_arb_res = client.post("/api/reports", data=payload_arbitrary, files=files_arbitrary)
    assert create_arb_res.status_code == 201
    created_arb = create_arb_res.json()
    register_test_report_id(created_arb["id"])

    # El servidor NO valida procedencia oficial para una foto externa arbitraria
    assert created_arb["is_synthetic"] is False

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT is_synthetic FROM reports WHERE id = %s;", (created_official["id"],))
            assert cur.fetchone()["is_synthetic"] is True

            cur.execute("SELECT is_synthetic FROM reports WHERE id = %s;", (created_arb["id"],))
            assert cur.fetchone()["is_synthetic"] is False


def test_sample_otro_is_independent_and_distinct():
    """
    Verifica que sample_otro.jpg sea una escena independiente y NO una copia
    del socavón de DEMO0009 / sample_hueco.
    """
    frontend_demo_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "demo_evidence"
    otro_path = frontend_demo_dir / "sample_otro.jpg"
    hueco_path = frontend_demo_dir / "sample_hueco.jpg"
    demo9_path = settings.UPLOAD_DIR / "synthetic_civ-2026-demo0009.jpg"

    assert otro_path.exists()
    assert hueco_path.exists()

    otro_sha = hashlib.sha256(otro_path.read_bytes()).hexdigest()
    hueco_sha = hashlib.sha256(hueco_path.read_bytes()).hexdigest()

    assert otro_sha != hueco_sha, "sample_otro.jpg no debe tener el mismo hash que sample_hueco.jpg"

    if demo9_path.exists():
        demo9_sha = hashlib.sha256(demo9_path.read_bytes()).hexdigest()
        assert otro_sha != demo9_sha, "sample_otro.jpg no debe ser una copia de civ-2026-demo0009.jpg"


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
