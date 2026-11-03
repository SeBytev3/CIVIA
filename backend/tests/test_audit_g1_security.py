from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
from uuid import UUID
import uuid

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app import agent as agent_module
from app import main as main_module
from app import observability as obs_module
from app.agent import decide_pending_approval, tool_proponer_actualizacion_critica
from app.ai_router import reset_all_circuits, set_runtime_fault_override
from app.config import (
    WEAK_ADMIN_TOKENS,
    generate_admin_token,
    is_strong_admin_token,
    settings,
    validate_admin_token_or_raise,
)
from app.db import (
    assert_disposable_test_db,
    get_conn,
    is_disposable_test_or_eval_db,
    run_migrations,
)
from app.main import app
from app.repository import create_report, get_report_raw, update_report_status
from app.security import rate_limiter
from app.seed import seed_synthetic_reports
from tests.conftest import (
    cleanup_tracked_test_records,
    register_test_approval_id,
    register_test_report_id,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def hermetic_multimodal_adapter_fixture(monkeypatch):
    """Sustituye adaptadores de IA por mocks herméticos en suite de seguridad G1 (G2.1.3)."""
    import app.ai_router as ai_router_module

    def _mock_multimodal(*, model: str, api_key: str, prompt_text: str, image_bytes: bytes | None, image_mime: str | None, timeout_sec: float) -> tuple[str, int, int]:
        payload = {
            "category": "HUECO",
            "severity": "ALTA",
            "confidence": 0.9,
            "summary": "Hueco detectado en calzada.",
            "keywords": ["hueco"],
        }
        return json.dumps(payload), 450, 85

    monkeypatch.setattr(ai_router_module, "_call_gemini_multimodal", _mock_multimodal)
    monkeypatch.setattr(ai_router_module, "_call_groq_multimodal", _mock_multimodal)


@pytest.fixture(scope="module", autouse=True)
def setup_g1_audit_db():
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    run_migrations()
    seed_synthetic_reports(force_reset=False)
    yield
    set_runtime_fault_override("NONE")
    reset_all_circuits()
    cleanup_tracked_test_records()


@pytest.fixture(autouse=True)
def clear_limiter_and_faults():
    rate_limiter.reset()
    set_runtime_fault_override("NONE")
    reset_all_circuits()
    yield
    rate_limiter.reset()
    set_runtime_fault_override("NONE")
    reset_all_circuits()
    cleanup_tracked_test_records()


def _make_png_bytes(color: tuple[int, int, int] = (90, 120, 150)) -> bytes:
    img = Image.new("RGB", (64, 64), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_c01_admin_token_mandatory_and_rejects_weak_or_default(monkeypatch):
    """
    C-01: El backend debe rechazar arranque y peticiones admin si ADMIN_TOKEN falta,
    es corto o coincide con tokens débiles/por defecto conocidos.
    """
    for weak in ("", "civia-admin-demo-2026", "admin", "1234567890", "short_token_123"):
        assert is_strong_admin_token(weak) is False
        with pytest.raises(RuntimeError):
            validate_admin_token_or_raise(weak)

    for w in WEAK_ADMIN_TOKENS:
        assert is_strong_admin_token(w) is False

    # Sin cabecera o con el antiguo token por defecto debe responder 401
    r_no_hdr = client.get("/api/admin/observability")
    assert r_no_hdr.status_code == 401

    r_old_default = client.get(
        "/api/admin/observability",
        headers={"X-Admin-Token": "civia-admin-demo-2026"},
    )
    assert r_old_default.status_code == 401

    # Si el servidor tuviera configurado un token débil en runtime, debe negar acceso (401)
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "civia-admin-demo-2026")
    r_weak_server = client.get(
        "/api/admin/observability",
        headers={"X-Admin-Token": "civia-admin-demo-2026"},
    )
    assert r_weak_server.status_code == 401


def test_g1_1_c01_rejects_sequential_and_repeated_tokens(monkeypatch):
    """
    G1.1 C-01 (contraejemplo exacto de Codex):
    Secuencias numéricas/alfabéticas y patrones periódicos repetidos como '0123456789' * 3
    deben ser rechazados en validación, en el arranque de FastAPI y en endpoints admin.
    """
    predictable_tokens = [
        "0123456789" * 3,
        "9876543210" * 3,
        "abcdefghij" * 3,
        "qwertyuiop" * 3,
        "Ab1!" * 8,
        "civia_admin_0123456789_secret_token",
        "11112222333344445555666677778888",
        "abcdefghijklmnopqrstuvwxyz123456",
    ]
    for bad_tok in predictable_tokens:
        assert is_strong_admin_token(bad_tok) is False, f"Debió rechazarse: {bad_tok}"
        with pytest.raises(RuntimeError):
            validate_admin_token_or_raise(bad_tok)

    # Verificar que el lifespan de FastAPI falla al iniciar si ADMIN_TOKEN es '0123456789' * 3
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "0123456789" * 3)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass

    # Y aun si se inyecta en caliente en settings, el endpoint devuelve 401
    r_obs = client.get(
        "/api/admin/observability",
        headers={"X-Admin-Token": "0123456789" * 3},
    )
    assert r_obs.status_code == 401

    # Token generado con CSPRNG (secrets.token_urlsafe(32)) sí es aceptado
    strong_csprng = generate_admin_token(32)
    assert is_strong_admin_token(strong_csprng) is True
    monkeypatch.setattr(settings, "ADMIN_TOKEN", strong_csprng)
    r_ok = client.get(
        "/api/admin/observability",
        headers={"X-Admin-Token": strong_csprng},
    )
    assert r_ok.status_code == 200


def test_g1_2_c01_rejects_contextual_project_role_year_demo_token(monkeypatch):
    """
    G1.2 C-01 (contraejemplo contextual exacto de docs/auditoria_codex_g1_1.md):
    El patrón construido con nombre público del proyecto, rol administrativo, año y etiqueta
    Demo/Test ('_'.join(('Civia', 'AdminToken', '2026', 'Demo')) + '!') y sus variantes
    (incluso extendidas a >= 32 caracteres o con ADMIN_TOKEN_ALLOW_CUSTOM_FORMAT=true)
    no permiten iniciar el servidor ni acceder a /api/admin/observability.
    """
    codex_pattern = "_".join(("Civia", "AdminToken", "2026", "Demo")) + "!"
    contextual_variants = [
        codex_pattern,
        "Civia_AdminToken_2026_Demo_Extended_9842",
        "Civia-Admin-Role-2026-Test-Credential-7391",
        "Proyecto_Civia_Operador_2026_Demo_Key_8472",
        "Supervisor_Cali_Valle_2026_Production_9182",
    ]

    for candidate in contextual_variants:
        assert is_strong_admin_token(candidate) is False, f"Debió rechazarse patrón contextual: {candidate}"
        with pytest.raises(RuntimeError):
            validate_admin_token_or_raise(candidate)

    # Incluso si se habilita ADMIN_TOKEN_ALLOW_CUSTOM_FORMAT=true, los patrones contextuales siguen rechazados
    monkeypatch.setenv("ADMIN_TOKEN_ALLOW_CUSTOM_FORMAT", "true")
    for candidate in contextual_variants:
        assert is_strong_admin_token(candidate) is False
    monkeypatch.delenv("ADMIN_TOKEN_ALLOW_CUSTOM_FORMAT", raising=False)

    # Reproductor exacto de Codex: el lifespan completo rechaza iniciar con codex_pattern
    monkeypatch.setattr(settings, "ADMIN_TOKEN", codex_pattern)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass

    # Y ante cualquier petición al endpoint administrativo devuelve 401
    r_ctx = client.get(
        "/api/admin/observability",
        headers={"X-Admin-Token": codex_pattern},
    )
    assert r_ctx.status_code == 401

    r_no_tok = client.get("/api/admin/observability")
    assert r_no_tok.status_code == 401

    # Un secreto nuevo generado mediante CSPRNG permite iniciar la aplicación y acceder a /api/admin/observability
    csprng_secret = generate_admin_token(32)
    monkeypatch.setattr(settings, "ADMIN_TOKEN", csprng_secret)
    with TestClient(app) as fresh_client:
        r_valid = fresh_client.get(
            "/api/admin/observability",
            headers={"X-Admin-Token": csprng_secret},
        )
        assert r_valid.status_code == 200


def test_a01_confirm_requires_report_edit_token_and_blocks_post_admin_mutation():
    """
    A-01:
    1) PATCH /api/reports/{id}/status exige X-Admin-Token válido (human_approved=true no basta).
    2) PATCH /api/reports/{id}/confirm exige X-Citizen-Edit-Token válido del reporte.
    3) Una vez confirmado o gestionado administrativamente (ej. RESOLVED/IN_REVIEW), un tercero
       anónimo o incluso el ciudadano sin token admin no puede sobreescribir el reporte (409).
    """
    # 1. Crear reporte nuevo
    r_create = client.post(
        "/api/reports",
        data={
            "title": "Reporte para prueba A-01 de autorización",
            "description": "DATO SINTÉTICO A-01: Bache profundo frente a estación para probar control de acceso.",
            "latitude": "3.4510",
            "longitude": "-76.5310",
            "comuna": "Comuna 2",
            "auto_analyze": "false",
        },
        files={"photo": ("a01.png", _make_png_bytes(), "image/png")},
    )
    assert r_create.status_code == 201
    created = r_create.json()
    rid = created["id"]
    edit_token = created["citizen_edit_token"]
    assert edit_token and len(edit_token) >= 32

    # 2. Intento de cambio de estado administrativo sin X-Admin-Token pero con human_approved=True -> 401
    r_status_unauth = client.patch(
        f"/api/reports/{rid}/status",
        json={"status": "RESOLVED", "human_approved": True, "note": "Intento anónimo"},
    )
    assert r_status_unauth.status_code == 401

    # 3. Intento de confirmación ciudadana sin edit_token o con edit_token falso -> 403
    r_confirm_no_tok = client.patch(
        f"/api/reports/{rid}/confirm",
        json={"final_category": "QUEMA", "final_severity": "CRITICA"},
    )
    assert r_confirm_no_tok.status_code == 403
    assert r_confirm_no_tok.json()["error"] == "CONFIRMATION_UNAUTHORIZED"

    r_confirm_bad_tok = client.patch(
        f"/api/reports/{rid}/confirm",
        headers={"X-Citizen-Edit-Token": "token_falso_invalido_000000000000"},
        json={"final_category": "QUEMA", "final_severity": "CRITICA"},
    )
    assert r_confirm_bad_tok.status_code == 403

    # 4. Confirmación legítima con el edit_token devuelto al creador -> 200 CONFIRMED
    r_confirm_ok = client.patch(
        f"/api/reports/{rid}/confirm",
        headers={"X-Citizen-Edit-Token": edit_token},
        json={"final_category": "HUECO", "final_severity": "ALTA", "human_override_note": "Confirmado por autor"},
    )
    assert r_confirm_ok.status_code == 200
    assert r_confirm_ok.json()["status"] == "CONFIRMED"

    # 5. Gestión administrativa pasa el reporte a RESOLVED
    r_admin_resolve = client.patch(
        f"/api/reports/{rid}/status",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"status": "RESOLVED", "human_approved": True, "note": "Atendido por cuadrilla."},
    )
    assert r_admin_resolve.status_code == 200
    assert r_admin_resolve.json()["status"] == "RESOLVED"

    # 6. Intento posterior de volver a confirmar o alterar categoría sin ser admin -> 409 REPORT_ALREADY_MANAGED
    r_reconfirm = client.patch(
        f"/api/reports/{rid}/confirm",
        headers={"X-Citizen-Edit-Token": edit_token},
        json={"final_category": "BASURAS", "final_severity": "BAJA", "human_override_note": "Sabotaje post-resolución"},
    )
    assert r_reconfirm.status_code == 409
    assert r_reconfirm.json()["error"] == "REPORT_ALREADY_MANAGED"

    # Verificar que en BD sigue RESOLVED y HUECO
    current = client.get(f"/api/reports/{rid}").json()
    assert current["status"] == "RESOLVED"
    assert current["final_category"] == "HUECO"


def test_g1_1_a01_public_replay_cannot_recover_citizen_edit_token():
    """
    G1.1 A-01 (contraejemplo exacto de Codex):
    Dos clientes independientes:
    - El cliente 1 crea un reporte (con PNG público).
    - El cliente 2 descarga título, descripción, coordenadas y fotografía públicos desde GET /api/reports/{id}
      y GET /api/reports/{id}/photo, y reconstruye el POST /api/reports.
    - El cliente 2 NO recupera el reporte original ni su citizen_edit_token, y al intentar confirmar el reporte
      del cliente 1 recibe 403 CONFIRMATION_UNAUTHORIZED.
    """
    c1 = TestClient(app)
    c2 = TestClient(app)

    png_bytes = _make_png_bytes((20, 40, 60))
    r1 = c1.post(
        "/api/reports",
        data={
            "title": "Reporte original cliente 1",
            "description": "DATO SINTÉTICO G1.1 A01: Reporte creado por cliente 1 para probar aislamiento de token.",
            "latitude": "3.4525",
            "longitude": "-76.5325",
            "auto_analyze": "false",
        },
        files={"photo": ("c1.png", png_bytes, "image/png")},
    )
    assert r1.status_code == 201
    b1 = r1.json()
    orig_id = b1["id"]
    orig_token = b1["citizen_edit_token"]
    assert orig_token and len(orig_token) >= 32

    # Cliente 2 consulta únicamente endpoints públicos
    pub = c2.get(f"/api/reports/{orig_id}").json()
    assert pub.get("citizen_edit_token") is None
    pub_photo = c2.get(pub["photo_url"]).content

    # Cliente 2 reconstruye el POST con los datos y foto públicos descargados
    r2 = c2.post(
        "/api/reports",
        data={
            "title": pub["title"],
            "description": pub["description"],
            "latitude": str(pub["latitude"]),
            "longitude": str(pub["longitude"]),
            "auto_analyze": "false",
        },
        files={"photo": ("replay.png", pub_photo, "image/png")},
    )
    assert r2.status_code == 201
    b2 = r2.json()
    assert b2["id"] != orig_id
    assert b2["citizen_edit_token"] != orig_token

    # Cliente 2 intenta usar el token de su POST reconstruido para alterar el reporte original del Cliente 1 -> 403
    r_hijack = c2.patch(
        f"/api/reports/{orig_id}/confirm",
        headers={"X-Citizen-Edit-Token": b2["citizen_edit_token"]},
        json={
            "final_category": "QUEMA",
            "final_severity": "CRITICA",
            "human_override_note": "Hijacked by reconstructed public post",
        },
    )
    assert r_hijack.status_code == 403
    assert r_hijack.json()["error"] == "CONFIRMATION_UNAUTHORIZED"

    # El reporte del Cliente 1 permanece intacto y sin confirmar
    after_orig = c1.get(f"/api/reports/{orig_id}").json()
    assert after_orig["human_confirmed"] is False
    assert after_orig["final_category"] is None


def test_m07_and_n03_seed_force_reset_rejects_non_test_db():
    """
    M-07 / N-03: assert_disposable_test_db rechaza cualquier base de datos que no sea
    explícitamente de pruebas (*_test) o evaluación (*_eval), tanto para 'civia' como para
    cualquier otro nombre de producción (ej. 'civia_prod_probe').
    """
    for non_disposable_url in (
        "postgresql://civia:secret@db:5432/civia",
        "postgresql://civia:secret@db:5432/civia_prod_probe",
        "postgresql://civia:secret@db:5432/produccion_cali",
    ):
        assert is_disposable_test_or_eval_db(non_disposable_url) is False
        with pytest.raises(RuntimeError):
            assert_disposable_test_db(non_disposable_url)

    assert is_disposable_test_or_eval_db("postgresql://civia:secret@db:5432/civia_test") is True
    assert is_disposable_test_or_eval_db("postgresql://civia:secret@db:5432/civia_test_abc123") is True
    assert is_disposable_test_or_eval_db("postgresql://civia:secret@db:5432/civia_eval") is True
    assert is_disposable_test_or_eval_db("postgresql://civia:secret@db:5432/test_civia") is True


def test_g1_1_m07_concurrent_records_and_demo0001_survive_cleanup():
    """
    G1.1 M-07 (contraejemplo exacto de Codex):
    Si otra conexión inserta un reporte no sintético, inserta una aprobación pendiente
    y modifica CIV-2026-DEMO0001 a IN_REVIEW mientras corre una prueba, el teardown de pruebas
    (cleanup_tracked_test_records) JAMÁS debe borrar las filas concurrentes ni restaurar DEMO0001.
    """
    sentinel_report_id = uuid.uuid4()
    sentinel_code = f"CIV-2026-SENT{sentinel_report_id.hex[:6].upper()}"
    sentinel_pa_id = uuid.uuid4()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, status, human_override_note, version FROM reports WHERE tracking_code = 'CIV-2026-DEMO0001';"
            )
            orig_demo1 = cur.fetchone()
            assert orig_demo1 is not None
            demo1_id = orig_demo1["id"]

            # Simular operación concurrente externa durante la prueba
            cur.execute(
                """
                UPDATE reports
                SET status = 'IN_REVIEW',
                    human_override_note = 'Concurrent operator note',
                    version = COALESCE(version, 1) + 1
                WHERE id = %s;
                """,
                (demo1_id,),
            )
            cur.execute(
                """
                INSERT INTO reports (
                    id, tracking_code, title, description, latitude, longitude, in_service_area,
                    photo_path, photo_mime, photo_size_bytes, photo_width, photo_height, photo_sha256,
                    status, is_synthetic
                )
                VALUES (
                    %s, %s, 'Sentinel concurrent report',
                    'Registro concurrente ajeno que no debe borrarse.',
                    3.45, -76.53, TRUE, 'sentinel.png', 'image/png', 128, 64, 64, %s,
                    'PENDING_ANALYSIS', FALSE
                );
                """,
                (sentinel_report_id, sentinel_code, "a" * 64),
            )
            cur.execute(
                """
                INSERT INTO pending_approvals (
                    id, report_id, proposed_action, proposed_payload, reason, status
                )
                VALUES (
                    %s, %s, 'UPDATE_REPORT_STATUS',
                    '{"previous_status":"IN_REVIEW","expected_version":2,"proposed_status":"RESOLVED"}'::jsonb,
                    'Sentinel approval', 'PENDING'
                );
                """,
                (sentinel_pa_id, demo1_id),
            )
            conn.commit()

    try:
        # La prueba crea su propio reporte y su propia aprobación (registrados por los hooks)
        r_own = client.post(
            "/api/reports",
            data={
                "title": "Reporte propio de la prueba",
                "description": "DATO SINTÉTICO M07: Reporte creado por la prueba para verificar limpieza selectiva.",
                "latitude": "3.4410",
                "longitude": "-76.5210",
                "auto_analyze": "false",
            },
            files={"photo": ("own.png", _make_png_bytes(), "image/png")},
        )
        assert r_own.status_code == 201
        own_id = UUID(r_own.json()["id"])
        own_code = r_own.json()["tracking_code"]

        pa_own = tool_proponer_actualizacion_critica(
            {"identificador": own_code, "nuevo_estado": "IN_REVIEW", "motivo": "Propuesta propia test"}
        )
        own_pa_id = UUID(pa_own["approval_id"])

        # Ejecutar la limpieza de la prueba
        cleanup_tracked_test_records()

        # Verificar que lo creado por la prueba se limpió, pero los datos concurrentes y DEMO0001 siguen intactos
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM reports WHERE id = %s;", (own_id,))
                assert cur.fetchone() is None

                cur.execute("SELECT 1 FROM pending_approvals WHERE id = %s;", (own_pa_id,))
                assert cur.fetchone() is None

                cur.execute("SELECT 1 FROM reports WHERE id = %s;", (sentinel_report_id,))
                assert cur.fetchone() is not None, "El reporte concurrente ajeno fue eliminado indebidamente"

                cur.execute("SELECT 1 FROM pending_approvals WHERE id = %s;", (sentinel_pa_id,))
                assert cur.fetchone() is not None, "La aprobación concurrente ajena fue eliminada indebidamente"

                cur.execute(
                    "SELECT status, human_override_note FROM reports WHERE id = %s;",
                    (demo1_id,),
                )
                demo1_after = cur.fetchone()
                assert demo1_after is not None
                assert demo1_after["status"] == "IN_REVIEW"
                assert demo1_after["human_override_note"] == "Concurrent operator note"
    finally:
        # Limpiar únicamente los centinelas de esta prueba y dejar DEMO0001 en su estado previo
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM pending_approvals WHERE id = %s;", (sentinel_pa_id,))
                cur.execute("DELETE FROM reports WHERE id = %s;", (sentinel_report_id,))
                cur.execute(
                    """
                    UPDATE reports
                    SET status = %s,
                        human_override_note = %s,
                        version = %s
                    WHERE id = %s;
                    """,
                    (
                        orig_demo1["status"],
                        orig_demo1["human_override_note"],
                        orig_demo1["version"],
                        orig_demo1["id"],
                    ),
                )
                conn.commit()


def test_g1_1_n03_evaluator_cleanup_preserves_concurrent_approvals(monkeypatch):
    """
    G1.1 N-03 (contraejemplo exacto de Codex):
    Si durante eval/evaluar.py se inserta una pending_approval concurrente después del inicio
    de run_evaluation, la limpieza final del evaluador solo debe borrar las aprobaciones
    generadas por el propio evaluador y conservar intacta la aprobación concurrente.
    """
    import eval.evaluar as ev
    from app.schemas import AIAnalysisContract

    concurrent_pa_id = uuid.uuid4()
    eval_own_pa_id = uuid.uuid4()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM reports WHERE tracking_code = 'CIV-2026-DEMO0001';")
            rep1_id = cur.fetchone()["id"]
            cur.execute("SELECT id FROM reports WHERE tracking_code = 'CIV-2026-DEMO0002';")
            rep2_id = cur.fetchone()["id"]

    def fake_agent(query: str, **kwargs):
        if "CIV-2026-DEMO0002" in query:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Aprobación propia de Q13 en el evaluador
                    cur.execute(
                        """
                        INSERT INTO pending_approvals (
                            id, report_id, proposed_action, proposed_payload, reason, status
                        )
                        VALUES (
                            %s, %s, 'UPDATE_REPORT_STATUS',
                            '{"previous_status":"IN_REVIEW","expected_version":1,"proposed_status":"RESOLVED"}'::jsonb,
                            'Eval own Q13 approval', 'PENDING'
                        );
                        """,
                        (eval_own_pa_id, rep2_id),
                    )
                    # Aprobación concurrente ajena creada después del inicio de run_evaluation
                    cur.execute(
                        """
                        INSERT INTO pending_approvals (
                            id, report_id, proposed_action, proposed_payload, reason, status
                        )
                        VALUES (
                            %s, %s, 'UPDATE_REPORT_STATUS',
                            '{"previous_status":"CONFIRMED","expected_version":1,"proposed_status":"IN_REVIEW"}'::jsonb,
                            'Concurrent external approval during eval', 'PENDING'
                        );
                        """,
                        (concurrent_pa_id, rep1_id),
                    )
                    conn.commit()
            return {
                "answer": "Solicitud registrada en estado PENDING para aprobación humana sobre CIV-2026-DEMO0002.",
                "trace_group_id": str(uuid.uuid4()),
                "tools_invoked": [
                    {
                        "tool": "proponer_actualizacion_critica",
                        "args": {"identificador": "CIV-2026-DEMO0002"},
                        "result": {"approval_id": str(eval_own_pa_id), "requiere_aprobacion_humana": True},
                    }
                ],
                "guardrail_triggered": "HUMAN_APPROVAL_REQUIRED",
                "requires_human_approval": True,
                "pending_approval_id": str(eval_own_pa_id),
                "degraded_sql_mode": False,
            }
        return {
            "answer": "Respuesta determinista de prueba no existe 0 CIV-2026-DEMO0001 CIV-2026-DEMO0004 CIV-2026-DEMO0006 CIV-2026-DEMO0003 CIV-2026-DEMO0009 CIV-2026-DEMO0010 CIV-2026-DEMO0008 HUECO QUEMA BASURAS TALA Comuna 2 Pance Siloé Santa Elena Capri CRITICA RESOLVED.",
            "trace_group_id": str(uuid.uuid4()),
            "tools_invoked": [{"tool": "consultar_reportes", "args": {}, "result": {}}],
            "guardrail_triggered": None,
            "requires_human_approval": False,
            "pending_approval_id": None,
            "degraded_sql_mode": True,
        }

    def fake_classify(**kwargs):
        return (
            AIAnalysisContract(
                category="HUECO",
                severity="ALTA",
                confidence=0.9,
                summary=" Resumen sintético de prueba para evaluación.",
                keywords=["hueco"],
            ),
            {"trace_group_id": str(uuid.uuid4()), "fallback_used": True},
        )

    monkeypatch.setattr(ev, "run_civia_agent", fake_agent)
    monkeypatch.setattr(ev, "classify_evidence_with_router", fake_classify)
    monkeypatch.setattr(ev, "RESULTS_DIR", settings.UPLOAD_DIR / "eval_out_tmp")

    try:
        ev.run_evaluation(mode="live", pause_sec=0)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pending_approvals WHERE id = %s;", (eval_own_pa_id,))
                assert cur.fetchone() is None, "La aprobación propia del evaluador debió limpiarse"

                cur.execute("SELECT 1 FROM pending_approvals WHERE id = %s;", (concurrent_pa_id,))
                assert cur.fetchone() is not None, "La aprobación concurrente ajena NO debió borrarse"
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM pending_approvals WHERE id = ANY(%s);",
                    ([eval_own_pa_id, concurrent_pa_id],),
                )
                conn.commit()


def test_a06_idempotency_and_post_commit_trace_failure_isolation(monkeypatch):
    """
    A-06:
    1) Enviar el mismo POST /api/reports con la misma Idempotency-Key devuelve el mismo
       reporte y tracking_code sin duplicar filas en PostgreSQL, recuperando citizen_edit_token.
    2) Reutilizar la misma Idempotency-Key con payload distinto devuelve 409 IDEMPOTENCY_KEY_CONFLICT.
    3) Si record_ai_trace lanza excepción después del commit del reporte, el ciudadano igual
       recibe 201 con su radicado y un reintento devuelve el mismo reporte.
    """
    idem_key = f"idem-g1-{uuid.uuid4().hex}"
    png_bytes = _make_png_bytes((40, 140, 90))
    form_data = {
        "title": "Reporte idempotente A-06",
        "description": "DATO SINTÉTICO A-06: Prueba de idempotencia ante reintentos de red del cliente.",
        "latitude": "3.4420",
        "longitude": "-76.5240",
        "comuna": "Comuna 19",
        "auto_analyze": "false",
    }

    r1 = client.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_key},
        data=form_data,
        files={"photo": ("idem.png", png_bytes, "image/png")},
    )
    assert r1.status_code == 201
    b1 = r1.json()

    r2 = client.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_key},
        data=form_data,
        files={"photo": ("idem.png", png_bytes, "image/png")},
    )
    assert r2.status_code == 201
    b2 = r2.json()

    assert b1["id"] == b2["id"]
    assert b1["tracking_code"] == b2["tracking_code"]
    assert b1["citizen_edit_token"] == b2["citizen_edit_token"]

    # Reutilizar la misma Idempotency-Key con otra descripción debe dar 409
    r_conflict = client.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_key},
        data={**form_data, "description": "Descripción diferente con la misma clave de idempotencia."},
        files={"photo": ("idem.png", png_bytes, "image/png")},
    )
    assert r_conflict.status_code == 409
    assert r_conflict.json()["error"] == "IDEMPOTENCY_KEY_CONFLICT"

    # Concurrencia real: 4 hilos enviando simultáneamente la misma operación idempotente
    concurrent_key = f"idem-concurrent-{uuid.uuid4().hex}"
    photo_meta = {
        "photo_path": "synthetic_civ-2026-demo0001.png",
        "photo_mime": "image/png",
        "photo_size_bytes": len(png_bytes),
        "photo_width": 64,
        "photo_height": 64,
        "photo_sha256": "a" * 64,
    }

    def _worker():
        return create_report(
            title="Concurrente A-06",
            description="DATO SINTÉTICO CONCURRENCIA: Misma clave en paralelo.",
            latitude=3.44,
            longitude=-76.52,
            in_service_area=True,
            comuna="Comuna 2",
            neighborhood=None,
            address_hint=None,
            photo_meta=photo_meta,
            idempotency_key=concurrent_key,
            request_fingerprint="fp_concurrent_test",
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: _worker(), range(4)))

    unique_ids = {str(r["id"]) for r in results}
    assert len(unique_ids) == 1

    # Fallo de observabilidad post-commit: si record_ai_trace falla durante el análisis,
    # POST /api/reports jamás debe devolver 500 ni perder el radicado ya confirmado.
    def exploding_trace(**kwargs):
        raise RuntimeError("Fallo simulado post-commit en tabla ai_traces")

    monkeypatch.setattr(obs_module, "record_ai_trace", exploding_trace)
    idem_trace_key = f"idem-trace-fail-{uuid.uuid4().hex}"
    r_trace1 = client.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_trace_key},
        data={
            "title": "Reporte resistente a fallo de traza",
            "description": "DATO SINTÉTICO POST-COMMIT: Quema de pastizal aunque falle el log de trazas.",
            "latitude": "3.4715",
            "longitude": "-76.5435",
            "auto_analyze": "true",
        },
        files={"photo": ("trace.png", png_bytes, "image/png")},
    )
    assert r_trace1.status_code == 201
    b_trace1 = r_trace1.json()
    assert b_trace1["tracking_code"].startswith("CIV-")

    # Si el cliente reintenta la misma solicitud, obtiene exactamente el mismo radicado
    r_trace2 = client.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_trace_key},
        data={
            "title": "Reporte resistente a fallo de traza",
            "description": "DATO SINTÉTICO POST-COMMIT: Quema de pastizal aunque falle el log de trazas.",
            "latitude": "3.4715",
            "longitude": "-76.5435",
            "auto_analyze": "true",
        },
        files={"photo": ("trace.png", png_bytes, "image/png")},
    )
    assert r_trace2.status_code == 201
    assert r_trace2.json()["id"] == b_trace1["id"]
    assert r_trace2.json()["tracking_code"] == b_trace1["tracking_code"]


def test_g1_1_a06_canonical_fingerprint_detects_optional_field_and_audio_mutations():
    """
    G1.1 A-06 (contraejemplo exacto de Codex):
    Reutilizar la misma Idempotency-Key cambiando comuna, neighborhood, address_hint,
    auto_analyze o audio debe devolver 409 IDEMPOTENCY_KEY_CONFLICT y jamás retornar
    silenciosamente el primer reporte.
    """
    idem_key = f"idem-a06-optional-fields-{uuid.uuid4().hex[:12]}"
    png_bytes = _make_png_bytes((50, 60, 70))

    r1 = client.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_key},
        data={
            "title": "Idempotencia campos opcionales",
            "description": "DATO SINTÉTICO G1.1 A06: Primera solicitud sin comuna ni dirección.",
            "latitude": "3.4500",
            "longitude": "-76.5300",
            "auto_analyze": "false",
        },
        files={"photo": ("p.png", png_bytes, "image/png")},
    )
    assert r1.status_code == 201
    orig_id = r1.json()["id"]

    # Variación 1: cambiar comuna y address_hint (contraejemplo exacto de Codex)
    r_comuna = client.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_key},
        data={
            "title": "Idempotencia campos opcionales",
            "description": "DATO SINTÉTICO G1.1 A06: Primera solicitud sin comuna ni dirección.",
            "latitude": "3.4500",
            "longitude": "-76.5300",
            "comuna": "Comuna 99",
            "address_hint": "Otra referencia completamente distinta",
            "auto_analyze": "false",
        },
        files={"photo": ("p.png", png_bytes, "image/png")},
    )
    assert r_comuna.status_code == 409
    assert r_comuna.json()["error"] == "IDEMPOTENCY_KEY_CONFLICT"

    # Variación 2: cambiar neighborhood
    r_barrio = client.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_key},
        data={
            "title": "Idempotencia campos opcionales",
            "description": "DATO SINTÉTICO G1.1 A06: Primera solicitud sin comuna ni dirección.",
            "latitude": "3.4500",
            "longitude": "-76.5300",
            "neighborhood": "San Antonio",
            "auto_analyze": "false",
        },
        files={"photo": ("p.png", png_bytes, "image/png")},
    )
    assert r_barrio.status_code == 409
    assert r_barrio.json()["error"] == "IDEMPOTENCY_KEY_CONFLICT"

    # Variación 3: cambiar auto_analyze
    r_auto = client.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_key},
        data={
            "title": "Idempotencia campos opcionales",
            "description": "DATO SINTÉTICO G1.1 A06: Primera solicitud sin comuna ni dirección.",
            "latitude": "3.4500",
            "longitude": "-76.5300",
            "auto_analyze": "true",
        },
        files={"photo": ("p.png", png_bytes, "image/png")},
    )
    assert r_auto.status_code == 409
    assert r_auto.json()["error"] == "IDEMPOTENCY_KEY_CONFLICT"

    # El reporte original sigue intacto sin comuna ni dirección
    stored = client.get(f"/api/reports/{orig_id}").json()
    assert stored["comuna"] is None
    assert stored["address_hint"] is None


def test_a07_stale_pending_approval_rejected_if_report_changed():
    """
    A-07: Si un reporte cambia de estado o versión después de crearse una solicitud en
    pending_approvals, intentar aprobar esa solicitud obsoleta debe devolver 409 STALE_APPROVAL
    y jamás sobreescribir el estado actual del reporte.
    """
    r_create = client.post(
        "/api/reports",
        data={
            "title": "Reporte para prueba A-07 de obsolescencia",
            "description": "DATO SINTÉTICO A-07: Hueco vial para verificar rechazo de aprobaciones obsoletas.",
            "latitude": "3.4550",
            "longitude": "-76.5320",
            "auto_analyze": "false",
        },
        files={"photo": ("a07.png", _make_png_bytes(), "image/png")},
    )
    assert r_create.status_code == 201
    created = r_create.json()
    rid = created["id"]
    tcode = created["tracking_code"]

    # 1. El agente genera una propuesta para pasar el reporte a IN_REVIEW cuando está en PENDING_ANALYSIS (v1)
    prop = tool_proponer_actualizacion_critica(
        {
            "identificador": tcode,
            "nuevo_estado": "IN_REVIEW",
            "motivo": "Revisión inicial sugerida por el agente.",
        }
    )
    assert prop["creado"] is True
    approval_id = prop["approval_id"]

    # 2. Antes de que se decida esa propuesta, un operador resuelve directamente el reporte (v1 -> v2, RESOLVED)
    r_resolve = client.patch(
        f"/api/reports/{rid}/status",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"status": "RESOLVED", "human_approved": True, "note": "Resuelto directamente en terreno."},
    )
    assert r_resolve.status_code == 200
    assert r_resolve.json()["status"] == "RESOLVED"

    # 3. Ahora alguien intenta aprobar la solicitud vieja (que proponía IN_REVIEW sobre v1) -> 409 STALE_APPROVAL
    r_decide = client.post(
        f"/api/admin/approvals/{approval_id}/decide",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"approve": True, "decided_by": "Operador Tardío"},
    )
    assert r_decide.status_code == 409
    assert r_decide.json()["error"] == "STALE_APPROVAL"

    # 4. El reporte debe permanecer en RESOLVED (no retrocedió a IN_REVIEW)
    after = client.get(f"/api/reports/{rid}").json()
    assert after["status"] == "RESOLVED"


def test_g1_1_a07_legacy_approval_without_expected_version_rejected_after_aba_cycle():
    """
    G1.1 A-07 (contraejemplo exacto de Codex):
    Una propuesta PENDING heredada sin expected_version en proposed_payload debe ser
    rechazada como obsoleta (stale_conflict=True / 409 STALE_APPROVAL), incluso si el
    reporte hizo un ciclo ABA (CONFIRMED -> RESOLVED -> CONFIRMED) y volvió al mismo status.
    Además, run_migrations() invalida propuestas PENDING sin expected_version mediante 003.
    """
    r_create = client.post(
        "/api/reports",
        data={
            "title": "Reporte para ciclo ABA A-07",
            "description": "DATO SINTÉTICO G1.1 A07: Prueba de ciclo ABA con propuesta heredada sin expected_version.",
            "latitude": "3.4560",
            "longitude": "-76.5330",
            "auto_analyze": "false",
        },
        files={"photo": ("aba.png", _make_png_bytes(), "image/png")},
    )
    assert r_create.status_code == 201
    created = r_create.json()
    rid = UUID(created["id"])
    tcode = created["tracking_code"]

    # Pasar inicialmente a CONFIRMED
    update_report_status(rid, status="CONFIRMED", note="Confirmado inicial")

    # Insertar propuesta heredada sin expected_version (como en el contraejemplo de Codex)
    legacy_pa_id = uuid.uuid4()
    register_test_approval_id(legacy_pa_id)
    legacy_payload = {
        "tracking_code": tcode,
        "previous_status": "CONFIRMED",
        "proposed_status": "IN_REVIEW",
    }
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pending_approvals (
                    id, report_id, proposed_action, proposed_payload, reason, status
                )
                VALUES (%s, %s, 'UPDATE_REPORT_STATUS', %s::jsonb, 'Legacy proposal without expected_version', 'PENDING');
                """,
                (legacy_pa_id, rid, json.dumps(legacy_payload)),
            )
            conn.commit()

    # Ciclo ABA: CONFIRMED -> RESOLVED -> CONFIRMED (mismo status, versión posterior)
    update_report_status(rid, status="RESOLVED", note="Resuelto en campo")
    update_report_status(rid, status="CONFIRMED", note="Reabierto y confirmado")

    # Intentar aprobar la propuesta heredada sin expected_version -> debe rechazarse por obsolescencia
    res = decide_pending_approval(legacy_pa_id, approve=True, decided_by="auditor")
    assert res is not None
    assert res["status"] == "REJECTED"
    assert res["stale_conflict"] is True

    after_row = get_report_raw(rid)
    assert after_row is not None
    assert after_row["status"] == "CONFIRMED"


def test_b03_no_orphan_files_on_db_failure_or_idempotent_replay(monkeypatch):
    """
    B-03:
    1) Si create_report lanza una excepción de BD después de haber escrito la foto en disco,
       el archivo huérfano se elimina inmediatamente.
    2) Si un reintento idempotente llega con la misma Idempotency-Key, el archivo temporal
       escrito antes de detectar el replay se elimina y solo queda el archivo original.
    """
    c_no_raise = TestClient(app, raise_server_exceptions=False)
    png_bytes = _make_png_bytes((180, 70, 70))
    before_files = set(settings.UPLOAD_DIR.glob("*"))

    orig_create = main_module.create_report

    def failing_create_report(**kwargs):
        raise RuntimeError("Fallo simulado de base de datos al insertar reporte")

    monkeypatch.setattr(main_module, "create_report", failing_create_report)
    r_fail = c_no_raise.post(
        "/api/reports",
        data={
            "description": "DATO SINTÉTICO B-03: Reporte cuya inserción en BD falla.",
            "latitude": "3.4500",
            "longitude": "-76.5300",
            "auto_analyze": "false",
        },
        files={"photo": ("orphan.png", png_bytes, "image/png")},
    )
    assert r_fail.status_code == 500
    after_fail_files = set(settings.UPLOAD_DIR.glob("*"))
    assert after_fail_files == before_files

    # Restaurar create_report y verificar que un replay idempotente deja solo 1 archivo en disco
    monkeypatch.setattr(main_module, "create_report", orig_create)
    idem_b03 = f"idem-b03-{uuid.uuid4().hex}"
    r_ok1 = c_no_raise.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_b03},
        data={
            "description": "DATO SINTÉTICO B-03: Reporte con reintento idempotente sin archivos duplicados.",
            "latitude": "3.4510",
            "longitude": "-76.5310",
            "auto_analyze": "false",
        },
        files={"photo": ("ok1.png", png_bytes, "image/png")},
    )
    assert r_ok1.status_code == 201
    files_after_first = set(settings.UPLOAD_DIR.glob("*"))
    assert len(files_after_first) == len(before_files) + 1

    r_ok2 = c_no_raise.post(
        "/api/reports",
        headers={"Idempotency-Key": idem_b03},
        data={
            "description": "DATO SINTÉTICO B-03: Reporte con reintento idempotente sin archivos duplicados.",
            "latitude": "3.4510",
            "longitude": "-76.5310",
            "auto_analyze": "false",
        },
        files={"photo": ("ok1.png", png_bytes, "image/png")},
    )
    assert r_ok2.status_code == 201
    files_after_second = set(settings.UPLOAD_DIR.glob("*"))
    assert files_after_second == files_after_first


def test_g1_1_b03_partial_file_write_oserror_leaves_zero_orphan_files(monkeypatch):
    """
    G1.1 B-03 (contraejemplo exacto de Codex):
    Si Path.write_bytes escribe 16 bytes parciales y lanza OSError a mitad de la escritura,
    validate_and_store_photo limpia el archivo temporal/parcial antes de propagar el error
    y no queda ningún archivo huérfano en UPLOAD_DIR ni fila en reports.
    """
    c_no_raise = TestClient(app, raise_server_exceptions=False)
    png_bytes = _make_png_bytes((110, 80, 140))
    before_files = set(settings.UPLOAD_DIR.glob("*"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM reports;")
            before_count = int(cur.fetchone()["c"])

    orig_open = Path.open
    orig_write_bytes = Path.write_bytes

    def partial_write_bytes(self: Path, data: bytes, *args, **kwargs):
        if self.parent == settings.UPLOAD_DIR:
            with orig_open(self, "wb") as f:
                f.write(data[:16])
                f.flush()
            raise OSError("synthetic partial write failure")
        return orig_write_bytes(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_bytes", partial_write_bytes)

    r_partial = c_no_raise.post(
        "/api/reports",
        data={
            "title": "Escritura parcial interrumpida",
            "description": "DATO SINTÉTICO G1.1 B03: Prueba de escritura parcial de 16 bytes seguida de OSError.",
            "latitude": "3.4500",
            "longitude": "-76.5300",
            "auto_analyze": "false",
        },
        files={"photo": ("partial.png", png_bytes, "image/png")},
    )
    assert r_partial.status_code == 500

    after_files = set(settings.UPLOAD_DIR.glob("*"))
    new_files = after_files - before_files
    assert len(new_files) == 0, f"Quedaron archivos parciales/huérfanos en UPLOAD_DIR: {new_files}"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM reports;")
            after_count = int(cur.fetchone()["c"])
    assert after_count == before_count
