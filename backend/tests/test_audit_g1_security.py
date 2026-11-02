from pathlib import Path
from uuid import UUID
import uuid

from fastapi.testclient import TestClient
import pytest

from app import ai_router, main as main_module
from app.agent import decide_pending_approval, tool_proponer_actualizacion_critica
from app.config import is_strong_admin_token, settings, validate_admin_token_or_raise
from app.db import assert_disposable_test_db, get_conn, get_database_name
from app.main import app
from app.repository import (
    generate_tracking_code,
    get_report_raw,
    update_report_status,
)
from app.security import rate_limiter
from app.seed import generate_synthetic_evidence_png
from tests.conftest import restore_db_snapshot, snapshot_db_state

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_g1_test_scope():
    rate_limiter.reset()
    snap = snapshot_db_state()
    yield
    rate_limiter.reset()
    restore_db_snapshot(snap)


def test_c01_admin_token_rejects_default_weak_or_empty_and_lifespan_fails(monkeypatch):
    # 1. Validación de fortaleza de secretos
    assert is_strong_admin_token("") is False
    assert is_strong_admin_token("x") is False
    assert is_strong_admin_token("civia-admin-demo-2026") is False
    assert is_strong_admin_token("local_dev_change_me") is False
    assert is_strong_admin_token("a" * 30) is False  # baja entropía

    # 2. Lifespan debe fallar al iniciar si ADMIN_TOKEN falta, es corto o es el antiguo valor demo
    for bad_token in ("", "x", "civia-admin-demo-2026"):
        monkeypatch.setattr(settings, "ADMIN_TOKEN", bad_token)
        with pytest.raises(RuntimeError):
            validate_admin_token_or_raise(bad_token)
        with pytest.raises(RuntimeError):
            with TestClient(app):
                pass

        # Y el endpoint protegido debe rechazar incluso si la cabecera coincide con el token débil
        resp = client.get("/api/admin/observability", headers={"X-Admin-Token": bad_token})
        assert resp.status_code == 401

    # 3. Comprobar que el token demo fue eliminado de archivos de configuración y documentación
    repo_root = Path(__file__).resolve().parent.parent.parent
    for rel_path in ("docker-compose.yml", ".env.example", "README.md"):
        candidate = repo_root / rel_path
        if candidate.exists():
            content = candidate.read_text(encoding="utf-8")
            assert "civia-admin-demo-2026" not in content, f"Token débil hallado en {rel_path}"


def test_a01_anonymous_status_and_confirm_rejected_and_post_admin_confirm_blocked():
    img_bytes = generate_synthetic_evidence_png("HUECO", "G1-A01")
    create_resp = client.post(
        "/api/reports",
        data={
            "title": "Reporte prueba autorización A-01",
            "description": "DATO SINTÉTICO AUDITORÍA: Verificación de control de acceso en confirm y status.",
            "latitude": "3.4516",
            "longitude": "-76.5320",
            "comuna": "Comuna 2",
            "auto_analyze": "false",
        },
        files={"photo": ("a01.png", img_bytes, "image/png")},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    rid = created["id"]
    edit_token = created["citizen_edit_token"]
    assert edit_token is not None

    # Las lecturas públicas jamás deben exponer el citizen_edit_token a terceros
    pub_get = client.get(f"/api/reports/{rid}").json()
    assert pub_get.get("citizen_edit_token") is None
    pub_code = client.get(f"/api/reports/by-code/{created['tracking_code']}").json()
    assert pub_code.get("citizen_edit_token") is None

    # 1. PATCH /status sin X-Admin-Token debe devolver 401 aunque envíe human_approved=True
    anon_status = client.patch(
        f"/api/reports/{rid}/status",
        json={"status": "RESOLVED", "human_approved": True, "note": "Intento anónimo"},
    )
    assert anon_status.status_code == 401
    assert get_report_raw(rid)["status"] == "PENDING_ANALYSIS"

    # 2. PATCH /confirm anónimo sin X-Citizen-Edit-Token ni X-Admin-Token debe devolver 403
    anon_confirm = client.patch(
        f"/api/reports/{rid}/confirm",
        json={
            "final_category": "QUEMA",
            "final_severity": "CRITICA",
            "human_override_note": "Intento anónimo sin credencial",
        },
    )
    assert anon_confirm.status_code == 403
    assert anon_confirm.json()["error"] == "CONFIRMATION_UNAUTHORIZED"
    assert get_report_raw(rid)["human_confirmed"] is False

    # 3. Confirmación legítima con X-Citizen-Edit-Token funciona una sola vez
    ok_confirm = client.patch(
        f"/api/reports/{rid}/confirm",
        headers={"X-Citizen-Edit-Token": edit_token},
        json={
            "final_category": "HUECO",
            "final_severity": "ALTA",
            "human_override_note": "Confirmado por autor del reporte",
        },
    )
    assert ok_confirm.status_code == 200
    assert ok_confirm.json()["status"] == "CONFIRMED"

    # 4. Tras gestión administrativa (RESOLVED), ni siquiera con X-Citizen-Edit-Token se puede alterar
    prop = tool_proponer_actualizacion_critica(
        {
            "identificador": created["tracking_code"],
            "nuevo_estado": "RESOLVED",
            "motivo": "Cierre administrativo verificado",
        }
    )
    decide_resp = client.post(
        f"/api/admin/approvals/{prop['approval_id']}/decide",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"approve": True, "decided_by": "auditor-admin"},
    )
    assert decide_resp.status_code == 200
    assert get_report_raw(rid)["status"] == "RESOLVED"

    late_Overwrite = client.patch(
        f"/api/reports/{rid}/confirm",
        headers={"X-Citizen-Edit-Token": edit_token},
        json={
            "final_category": "TALA",
            "final_severity": "BAJA",
            "human_override_note": "Intento de sobrescribir tras gestión admin",
        },
    )
    assert late_Overwrite.status_code == 409
    assert late_Overwrite.json()["error"] == "REPORT_ALREADY_MANAGED"
    row_after = get_report_raw(rid)
    assert row_after["status"] == "RESOLVED"
    assert row_after["final_category"] == "HUECO"
    assert row_after["final_severity"] == "ALTA"


def test_a06_idempotency_durable_unique_and_postcommit_trace_failure_isolation(monkeypatch):
    img_bytes = generate_synthetic_evidence_png("BASURAS", "G1-A06")
    headers = {"Idempotency-Key": f"synthetic-audit-same-op-{uuid.uuid4().hex[:8]}"}
    form_data = {
        "title": "Reporte idempotente A-06",
        "description": "DATO SINTÉTICO AUDITORÍA: Prueba de idempotencia con clave única.",
        "latitude": "3.4210",
        "longitude": "-76.5180",
        "comuna": "Comuna 10",
        "auto_analyze": "false",
    }

    r1 = client.post(
        "/api/reports",
        headers=headers,
        data=form_data,
        files={"photo": ("idem.png", img_bytes, "image/png")},
    )
    r2 = client.post(
        "/api/reports",
        headers=headers,
        data=form_data,
        files={"photo": ("idem.png", img_bytes, "image/png")},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["tracking_code"] == r2.json()["tracking_code"]
    assert r1.json()["citizen_edit_token"] == r2.json()["citizen_edit_token"]

    # Reutilizar la misma Idempotency-Key con payload distinto debe devolver 409
    r_conflict = client.post(
        "/api/reports",
        headers=headers,
        data={**form_data, "description": "Descripción distinta con la misma clave Idempotency-Key."},
        files={"photo": ("idem.png", img_bytes, "image/png")},
    )
    assert r_conflict.status_code == 409
    assert r_conflict.json()["error"] == "IDEMPOTENCY_KEY_CONFLICT"

    # Fallo de observabilidad posterior al commit (record_ai_trace lanza RuntimeError)
    # jamás debe causar HTTP 500 ni duplicar el reporte al reintentar
    def boom_trace(**kwargs):
        raise RuntimeError("synthetic trace store failure")

    def fast_gemini_ok(**kwargs):
        return (
            '{"category":"QUEMA","severity":"ALTA","confidence":0.94,"summary":"Evidencia sintética de quema verificada en prueba post-commit.","keywords":["quema","humo"]}',
            35,
            18,
        )

    monkeypatch.setattr(ai_router, "record_ai_trace", boom_trace)
    monkeypatch.setattr(ai_router, "_call_gemini_multimodal", fast_gemini_ok)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM reports;")
            before_count = int(cur.fetchone()["c"])

    img_postcommit = generate_synthetic_evidence_png("QUEMA", "G1-POSTCOMMIT")
    pc_data = {
        "title": "POSTCOMMIT SYNTHETIC",
        "description": "DATO SINTÉTICO AUDITORÍA: Fallo de traza post-commit no debe invalidar alta.",
        "latitude": "3.4658",
        "longitude": "-76.5283",
        "comuna": "Comuna 2",
        "auto_analyze": "true",
    }
    p1 = client.post(
        "/api/reports",
        data=pc_data,
        files={"photo": ("pc.png", img_postcommit, "image/png")},
    )
    p2 = client.post(
        "/api/reports",
        data=pc_data,
        files={"photo": ("pc.png", img_postcommit, "image/png")},
    )
    assert p1.status_code == 201
    assert p2.status_code == 201
    assert p1.json()["id"] == p2.json()["id"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM reports;")
            after_count = int(cur.fetchone()["c"])
    assert (after_count - before_count) == 1


def test_a07_stale_approval_rejected_in_same_transaction():
    img_bytes = generate_synthetic_evidence_png("TALA", "G1-A07")
    resp = client.post(
        "/api/reports",
        data={
            "title": "Reporte prueba obsolescencia A-07",
            "description": "DATO SINTÉTICO AUDITORÍA: Propuesta obsoleta no debe sobrescribir estado posterior.",
            "latitude": "3.3385",
            "longitude": "-76.5410",
            "comuna": "Comuna 22",
            "auto_analyze": "false",
        },
        files={"photo": ("a07.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 201
    rep = resp.json()
    rid = rep["id"]
    tcode = rep["tracking_code"]

    update_report_status(rid, status="CONFIRMED", note="Estado base para prueba A-07")

    p_older = tool_proponer_actualizacion_critica(
        {"identificador": tcode, "nuevo_estado": "IN_REVIEW", "motivo": "stale proposal"}
    )
    p_newer = tool_proponer_actualizacion_critica(
        {"identificador": tcode, "nuevo_estado": "RESOLVED", "motivo": "newer proposal"}
    )

    # Se aprueba primero la propuesta más reciente (pasa a RESOLVED)
    res_newer = decide_pending_approval(p_newer["approval_id"], approve=True, decided_by="audit")
    assert res_newer is not None
    assert res_newer["status"] == "APPROVED"
    assert get_report_raw(rid)["status"] == "RESOLVED"

    # Al intentar aprobar la propuesta antigua (que esperaba previous_status=CONFIRMED),
    # debe detectarse obsolescencia en la misma transacción, marcarse REJECTED y NO tocar reports
    res_older = decide_pending_approval(p_older["approval_id"], approve=True, decided_by="audit")
    assert res_older is not None
    assert res_older["status"] == "REJECTED"
    assert res_older.get("stale_conflict") is True
    assert get_report_raw(rid)["status"] == "RESOLVED"


def test_b03_no_orphan_files_on_db_insert_failure_and_no_tracking_code_collision(monkeypatch):
    # 1. Cero archivos huérfanos cuando falla create_report en BD
    before_photos = {p.name for p in settings.UPLOAD_DIR.glob("photo_*")}
    before_audios = {p.name for p in settings.UPLOAD_DIR.glob("audio_*")}

    def fail_create_report(**kwargs):
        raise RuntimeError("synthetic insert failure")

    monkeypatch.setattr(main_module, "create_report", fail_create_report)
    img_bytes = generate_synthetic_evidence_png("HUECO", "G1-B03-ORPHAN")

    with TestClient(app, raise_server_exceptions=False) as no_raise_client:
        r_fail = no_raise_client.post(
            "/api/reports",
            data={
                "description": "Descripción válida para probar limpieza de huérfanos en fallo de BD.",
                "latitude": "3.45",
                "longitude": "-76.53",
                "auto_analyze": "false",
            },
            files={"photo": ("orphan_check.png", img_bytes, "image/png")},
        )
    assert r_fail.status_code == 500

    after_photos = {p.name for p in settings.UPLOAD_DIR.glob("photo_*")}
    after_audios = {p.name for p in settings.UPLOAD_DIR.glob("audio_*")}
    assert len(after_photos - before_photos) == 0
    assert len(after_audios - before_audios) == 0

    # 2. Dos UUIDs con el mismo prefijo de 8 hex jamás colisionan en generate_tracking_code
    u1 = UUID("aaaaaaaa-1111-4111-8111-111111111111")
    u2 = UUID("aaaaaaaa-2222-4222-8222-222222222222")
    code1 = generate_tracking_code(u1)
    code2 = generate_tracking_code(u2)
    assert code1 != code2


def test_m07_n03_test_and_eval_isolation_and_sentinel_preservation():
    # 1. La suite corre sobre base aislada (nunca sobre 'civia') y bloquea resets en 'civia'
    assert get_database_name(settings.DATABASE_URL) != "civia"
    with pytest.raises(RuntimeError):
        assert_disposable_test_db("postgresql://civia:local_dev_change_me@db:5432/civia")

    # 2. Verificar que el mecanismo de snapshot/restore preserva sentinels ajenos intactos
    sentinel_report_id = uuid.uuid4()
    sentinel_pa_id = uuid.uuid4()
    sentinel_code = f"CIV-2026-SNT{sentinel_report_id.hex[:6].upper()}"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM reports WHERE tracking_code = 'CIV-2026-DEMO0001';")
            demo1_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO reports (
                    id, tracking_code, title, description,
                    latitude, longitude, in_service_area,
                    comuna, neighborhood, address_hint,
                    photo_path, photo_mime, photo_size_bytes,
                    photo_width, photo_height, photo_sha256,
                    status, is_synthetic
                )
                VALUES (
                    %s, %s, 'UNRELATED REAL SENTINEL', 'No debe borrarse por limpiezas globales',
                    3.45, -76.53, TRUE,
                    'Comuna 2', 'Granada', 'Av 9N',
                    'synthetic_civ-2026-demo0001.png', 'image/png', 123,
                    240, 160, 'deadbeef',
                    'PENDING_ANALYSIS', FALSE
                );
                """,
                (sentinel_report_id, sentinel_code),
            )
            cur.execute(
                """
                INSERT INTO pending_approvals (
                    id, report_id, proposed_action, proposed_payload, reason, status
                )
                VALUES (
                    %s, %s, 'UPDATE_REPORT_STATUS', '{"proposed_status":"RESOLVED"}'::jsonb,
                    'UNRELATED SENTINEL ya atendido', 'PENDING'
                );
                """,
                (sentinel_pa_id, demo1_id),
            )
            cur.execute("UPDATE reports SET status = 'RESOLVED' WHERE id = %s;", (demo1_id,))
            conn.commit()

    try:
        inner_snap = snapshot_db_state()
        # Crear un reporte temporal dentro del alcance de la prueba
        img_bytes = generate_synthetic_evidence_png("HUECO", "G1-TEMP")
        r_temp = client.post(
            "/api/reports",
            data={
                "description": "Reporte temporal dentro de prueba aislada.",
                "latitude": "3.44",
                "longitude": "-76.52",
                "auto_analyze": "false",
            },
            files={"photo": ("temp.png", img_bytes, "image/png")},
        )
        assert r_temp.status_code == 201
        temp_id = UUID(r_temp.json()["id"])

        restore_db_snapshot(inner_snap)

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM reports WHERE id = %s;", (temp_id,))
                assert int(cur.fetchone()["c"]) == 0
                cur.execute("SELECT COUNT(*) AS c FROM reports WHERE id = %s;", (sentinel_report_id,))
                assert int(cur.fetchone()["c"]) == 1
                cur.execute("SELECT COUNT(*) AS c FROM pending_approvals WHERE id = %s;", (sentinel_pa_id,))
                assert int(cur.fetchone()["c"]) == 1
                cur.execute("SELECT status FROM reports WHERE id = %s;", (demo1_id,))
                assert cur.fetchone()["status"] == "RESOLVED"
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM pending_approvals WHERE id = %s;", (sentinel_pa_id,))
                cur.execute("DELETE FROM reports WHERE id = %s;", (sentinel_report_id,))
                conn.commit()
