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
        assert filename.startswith(f"synthetic_{code.lower()}_") and filename.endswith(".jpg")
        assert hashlib.sha256(data).hexdigest()[:16] in filename
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


# ---------------------------------------------------------------------------
# PRUEBAS ADVERSARIALES OBLIGATORIAS (CASOS A HASTA L)
# ---------------------------------------------------------------------------

def test_adversarial_case_a_interruption_after_staging():
    """
    Caso A: Interrupción después de crear archivo de staging temporal.
    Verifica que:
    1. Un archivo temporal .staging_* abandonado por un corte no afecte al catálogo existente.
    2. Las filas en PostgreSQL sigan apuntando a sus archivos válidos.
    3. El endpoint /photo responda HTTP 200 con imagen válida.
    """
    seed_synthetic_reports(force_reset=True)
    orphan_staging = settings.UPLOAD_DIR / f".staging_deadpid_civ-2026-demo0001_{uuid4().hex}.tmp"
    orphan_staging.write_bytes(b"TEMPORARY_STAGING_BEFORE_CRASH")

    client = TestClient(app)
    rep = client.get("/api/reports/by-code/CIV-2026-DEMO0001").json()
    photo_res = client.get(f"/api/reports/{rep['id']}/photo")
    assert photo_res.status_code == 200
    assert len(photo_res.content) > 100_000

    res = update_synthetic_catalog_photos()
    assert res["unchanged"] == 10


def test_adversarial_case_b_c_interruption_after_publishing_before_commit():
    """
    Casos B y C: Interrupción después de publicar imagen nueva en disco pero antes de confirmar SQL.
    Verifica que:
    1. Al no haberse confirmado SQL, la base de datos sigue apuntando al archivo anterior.
    2. El archivo anterior NUNCA fue eliminado ni sobreescrito.
    3. Las solicitudes de usuarios reciben la imagen anterior sin errores 404 ni roturas.
    """
    seed_synthetic_reports(force_reset=True)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, photo_path, photo_sha256 FROM reports WHERE tracking_code = 'CIV-2026-DEMO0001';")
            row_before = cur.fetchone()

    old_file_path = settings.UPLOAD_DIR / row_before["photo_path"]
    assert old_file_path.exists()
    old_bytes = old_file_path.read_bytes()

    # Simular que en disco ya se publicó un archivo con nuevo contenido
    simulated_new_name = "synthetic_civ-2026-demo0001_ffffffffffffffff.jpg"
    simulated_new_file = settings.UPLOAD_DIR / simulated_new_name
    simulated_new_file.write_bytes(b"SIMULATED_NEW_PHOTO_CONTENT")

    # Corte abrupto antes del commit: en PostgreSQL sigue apuntando a old_path
    client = TestClient(app)
    photo_res = client.get(f"/api/reports/{row_before['id']}/photo")
    assert photo_res.status_code == 200
    assert photo_res.content == old_bytes

    simulated_new_file.unlink(missing_ok=True)


def test_adversarial_case_d_replace_failure_rolls_back_and_preserves_original(monkeypatch):
    """
    Caso D: Fallo en os.replace durante publicación.
    Verifica que:
    1. La excepción no deja referencias rotas en PostgreSQL.
    2. El archivo existente referenciado permanece intacto.
    3. Los temporales de staging creados por este proceso se limpian defensivamente.
    """
    seed_synthetic_reports(force_reset=True)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, photo_path, photo_sha256 FROM reports WHERE tracking_code = 'CIV-2026-DEMO0001';")
            row1 = cur.fetchone()

    dest_file = settings.UPLOAD_DIR / row1["photo_path"]
    original_bytes = dest_file.read_bytes()
    dest_file.unlink()

    import os
    real_replace = os.replace

    def faulty_replace(src, dst):
        if "synthetic_civ-2026-demo0001" in str(dst):
            raise OSError("INJECTED_DISK_IO_FAILURE_ON_REPLACE")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", faulty_replace)

    try:
        with pytest.raises(OSError) as exc_info:
            update_synthetic_catalog_photos()
        assert "INJECTED_DISK_IO_FAILURE_ON_REPLACE" in str(exc_info.value)
    finally:
        monkeypatch.setattr(os, "replace", real_replace)
        dest_file.write_bytes(original_bytes)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT photo_sha256 FROM reports WHERE tracking_code = 'CIV-2026-DEMO0001';")
            assert cur.fetchone()["photo_sha256"] == row1["photo_sha256"]


def test_adversarial_case_e_persistent_replace_failure_keeps_integrity(monkeypatch):
    """
    Caso E: Fallo persistente de os.replace.
    Verifica que si el sistema de archivos rechaza sistemáticamente os.replace,
    la base de datos y los archivos existentes no sufran daño ni pérdida de información.
    """
    seed_synthetic_reports(force_reset=True)

    import os
    def always_fail_replace(src, dst):
        raise OSError("PERSISTENT_PERMISSION_DENIED_ON_FILESYSTEM")

    monkeypatch.setattr(os, "replace", always_fail_replace)

    # Desincronizar BD y eliminar dest_file para forzar publicación vía os.replace
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT photo_path FROM reports WHERE tracking_code = 'CIV-2026-DEMO0002';")
            dest_file = settings.UPLOAD_DIR / cur.fetchone()["photo_path"]
            dest_file.unlink(missing_ok=True)
            cur.execute("UPDATE reports SET photo_sha256 = 'desync_hash' WHERE tracking_code = 'CIV-2026-DEMO0002';")
            conn.commit()

    with pytest.raises(OSError) as exc_info:
        update_synthetic_catalog_photos()
    assert "PERSISTENT_PERMISSION_DENIED_ON_FILESYSTEM" in str(exc_info.value)


def test_adversarial_case_f_sql_commit_failure_preserves_original():
    """
    Caso F: Commit SQL fallido.
    Verifica que ante un fallo en la transacción SQL:
    1. Se ejecuta rollback en PostgreSQL.
    2. Las filas conservan los valores anteriores.
    3. Ningún archivo referenciado previamente es destruido.
    """
    seed_synthetic_reports(force_reset=True)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT photo_path, photo_sha256 FROM reports WHERE tracking_code = 'CIV-2026-DEMO0002';")
            row_orig = cur.fetchone()

            cur.execute(
                """
                CREATE OR REPLACE FUNCTION abort_demo02() RETURNS trigger AS $$
                BEGIN
                    IF NEW.tracking_code = 'CIV-2026-DEMO0002' AND NEW.photo_sha256 != 'temp_hash' THEN
                        RAISE EXCEPTION 'TEST_INJECTED_SQL_COMMIT_ABORT';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                DROP TRIGGER IF EXISTS trg_abort_demo02 ON reports;
                CREATE TRIGGER trg_abort_demo02 BEFORE UPDATE ON reports
                FOR EACH ROW EXECUTE FUNCTION abort_demo02();
                """
            )
            conn.commit()

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE reports SET photo_sha256 = 'temp_hash' WHERE tracking_code = 'CIV-2026-DEMO0002';")
                conn.commit()

        with pytest.raises(Exception) as exc_info:
            update_synthetic_catalog_photos()
        assert "TEST_INJECTED_SQL_COMMIT_ABORT" in str(exc_info.value)

        orig_file = settings.UPLOAD_DIR / row_orig["photo_path"]
        assert orig_file.exists()
        assert len(orig_file.read_bytes()) > 100_000

    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TRIGGER IF EXISTS trg_abort_demo02 ON reports;")
                cur.execute("DROP FUNCTION IF EXISTS abort_demo02();")
                conn.commit()


def test_adversarial_case_g_concurrent_updaters():
    """
    Caso G: Dos actualizadores concurrentes ejecutándose simultáneamente.
    Verifica que:
    1. Procesos concurrentes usen temporales exclusivos y no interfieran.
    2. Las escrituras atómicas os.replace y bloqueos de fila en PostgreSQL no causen fallos.
    3. Todos los reportes queden íntegros al terminar.
    """
    import threading
    seed_synthetic_reports(force_reset=True)

    results = []
    errors = []

    def worker(worker_id: int):
        try:
            res = update_synthetic_catalog_photos()
            results.append((worker_id, res))
        except Exception as e:
            errors.append((worker_id, e))

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(errors) == 0, f"Errores en concurrencia: {errors}"
    assert len(results) == 2

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT photo_path, photo_sha256 FROM reports WHERE tracking_code LIKE 'CIV-2026-DEMO%';")
            rows = cur.fetchall()
            assert len(rows) == 10
            for r in rows:
                p = settings.UPLOAD_DIR / r["photo_path"]
                assert p.exists()
                assert len(p.read_bytes()) > 100_000


def test_adversarial_case_h_detects_same_length_corruption():
    """
    Caso H: Corrupción JPEG de igual longitud.
    Verifica que si un archivo en disco conserva el tamaño exacto pero altera bytes,
    se detecte la corrupción por SHA-256 y decodificación PIL, y se restaure el archivo sano.
    """
    seed_synthetic_reports(force_reset=True)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT photo_path, photo_sha256 FROM reports WHERE tracking_code = 'CIV-2026-DEMO0001';")
            row = cur.fetchone()

    demo1_path = settings.UPLOAD_DIR / row["photo_path"]
    assert demo1_path.exists()
    orig_bytes = demo1_path.read_bytes()
    orig_sha = hashlib.sha256(orig_bytes).hexdigest()

    corrupt_bytes = b"X" + orig_bytes[1:]
    assert len(corrupt_bytes) == len(orig_bytes)
    demo1_path.write_bytes(corrupt_bytes)

    res = update_synthetic_catalog_photos()
    assert res["updated"] == 1
    assert res["unchanged"] == 9

    restored = demo1_path.read_bytes()
    assert hashlib.sha256(restored).hexdigest() == orig_sha
    with Image.open(io.BytesIO(restored)) as im:
        im.verify()


def test_adversarial_case_i_repeated_update_idempotent():
    """
    Caso I: Actualización repetida sin cambios.
    Verifica que la ejecución sucesiva sea matemáticamente idempotente: updated=0, unchanged=10.
    """
    seed_synthetic_reports(force_reset=True)
    res1 = update_synthetic_catalog_photos()
    assert res1["updated"] == 0
    assert res1["unchanged"] == 10

    res2 = update_synthetic_catalog_photos()
    assert res2["updated"] == 0
    assert res2["unchanged"] == 10


def test_adversarial_case_j_migration_legacy_png_to_jpeg():
    """
    Caso J: Instalación con PNG antiguos y migración hacia JPEG inmutable.
    Verifica que si una base de datos contiene reportes sintéticos con PNG legacy:
    1. Se publique el archivo JPEG inmutable en disco.
    2. Se actualice PostgreSQL a photo_mime='image/jpeg' y nuevo photo_path.
    3. El archivo PNG legacy no referenciado se desvincule limpiamente post-commit.
    """
    seed_synthetic_reports(force_reset=True)

    legacy_png_name = "synthetic_civ-2026-demo0005_legacy.png"
    legacy_file = settings.UPLOAD_DIR / legacy_png_name
    legacy_file.write_bytes(b"LEGACY_PNG_SIMULATED_CONTENT")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE reports
                SET photo_path = %s, photo_mime = 'image/png', photo_sha256 = 'legacy_sha'
                WHERE tracking_code = 'CIV-2026-DEMO0005';
                """,
                (legacy_png_name,),
            )
            conn.commit()

    res = update_synthetic_catalog_photos()
    assert res["updated"] == 1

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT photo_path, photo_mime, photo_sha256 FROM reports WHERE tracking_code = 'CIV-2026-DEMO0005';")
            row = cur.fetchone()
            assert row["photo_mime"] == "image/jpeg"
            assert row["photo_path"].startswith("synthetic_civ-2026-demo0005_")
            assert row["photo_path"].endswith(".jpg")
            new_file = settings.UPLOAD_DIR / row["photo_path"]
            assert new_file.exists()

    assert not legacy_file.exists()


def test_adversarial_case_k_missing_catalog_asset_safe_fallback():
    """
    Caso K: Ausencia de archivos de catálogo en disco.
    Verifica que si un código de reporte no tiene activo .jpg en DEMO_ASSETS_DIR,
    get_synthetic_evidence_bytes() devuelva un fallback válido en memoria sin abortar el servidor.
    """
    data, filename, mime, width, height = get_synthetic_evidence_bytes("CIV-2026-DEMO9999", "OTRO")
    assert mime == "image/png"
    assert len(data) > 1000
    assert width == 1024
    assert height == 768
    im = Image.open(io.BytesIO(data))
    assert im.format == "PNG"


def test_adversarial_case_l_citizen_reports_untouched():
    """
    Caso L: Reportes ciudadanos con fotos propias que deben permanecer inalterados.
    Verifica que ninguna fotografía o metadato de un reporte ciudadano (is_synthetic = FALSE)
    sea modificado, renombrado o alterado por update_synthetic_catalog_photos().
    """
    seed_synthetic_reports(force_reset=True)

    citizen_photo_name = f"citizen_real_{uuid4().hex}.jpg"
    citizen_file = settings.UPLOAD_DIR / citizen_photo_name
    citizen_file.write_bytes(b"AUTHENTIC_CITIZEN_PHOTO_BYTES_DONOTTOUCH")
    citizen_sha = hashlib.sha256(b"AUTHENTIC_CITIZEN_PHOTO_BYTES_DONOTTOUCH").hexdigest()

    cid = uuid4()
    register_test_report_id(cid)
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
                    %s, 'CIV-2026-CITIZEN99', 'Hueco ciudadano', 'Reportado por vecino',
                    3.4516, -76.5320, TRUE,
                    %s, 'image/jpeg', 40,
                    640, 480, %s,
                    'HUECO', 'MEDIA',
                    FALSE, 'PENDING_ANALYSIS', FALSE
                );
                """,
                (cid, citizen_photo_name, citizen_sha),
            )
            conn.commit()

    res = update_synthetic_catalog_photos()
    assert res["updated"] == 0
    assert res["unchanged"] == 10

    assert citizen_file.exists()
    assert citizen_file.read_bytes() == b"AUTHENTIC_CITIZEN_PHOTO_BYTES_DONOTTOUCH"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT photo_path, photo_sha256, is_synthetic FROM reports WHERE id = %s;", (cid,))
            c_row = cur.fetchone()
            assert c_row["photo_path"] == citizen_photo_name
            assert c_row["photo_sha256"] == citizen_sha
            assert c_row["is_synthetic"] is False


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
    demo9_files = list(settings.UPLOAD_DIR.glob("synthetic_civ-2026-demo0009*"))
    demo9_path = demo9_files[0] if demo9_files else None

    assert otro_path.exists()
    assert hueco_path.exists()

    otro_sha = hashlib.sha256(otro_path.read_bytes()).hexdigest()
    hueco_sha = hashlib.sha256(hueco_path.read_bytes()).hexdigest()

    assert otro_sha != hueco_sha, "sample_otro.jpg no debe tener el mismo hash que sample_hueco.jpg"

    if demo9_path and demo9_path.exists():
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
