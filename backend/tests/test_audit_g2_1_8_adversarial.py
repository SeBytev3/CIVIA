import hashlib
import hmac
import json
import threading
import time
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
import psycopg
import pytest

from app import agent as a, db, main as m
from app.config import generate_admin_token, settings
from app.db import (
    get_conn,
    get_operation_record,
    is_deadline_cancellation,
    mark_operation_aborted,
    mark_operation_committed,
    reconcile_operation,
    register_operation_intent,
)


@pytest.fixture
def clean_db():
    from tests.test_audit_g2_1_remediation import _get_clean_test_db
    test_db = _get_clean_test_db("test_g2_1_8_adv")
    old_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db
    try:
        yield test_db
    finally:
        settings.DATABASE_URL = old_url


def test_adversarial_rest_status_mutation_joint_atomic_rollback(clean_db):
    """
    Contrato C: La mutación REST PATCH /api/reports/{id}/status y su registro de auditoría
    se ejecutan en una única transacción PostgreSQL. Si el registro falla, ambos hacen rollback.
    """
    settings.ADMIN_TOKEN = generate_admin_token()
    rep_id = uuid.uuid4()
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as c:
        c.execute(
            """
            INSERT INTO reports (
                id, tracking_code, title, description, latitude, longitude, in_service_area,
                photo_path, photo_mime, photo_size_bytes, photo_width, photo_height, photo_sha256,
                status, is_synthetic, version
            ) VALUES (
                %s, 'CIV-2026-REST001', 'Test REST', 'Reporte para probar auditoria atomica.',
                3.45, -76.53, TRUE, 'sentinel.png', 'image/png', 128, 64, 64, %s,
                'CONFIRMED', FALSE, 1
            );
            """,
            (rep_id, "a" * 64),
        )

    client = TestClient(m.app, raise_server_exceptions=False)
    # 1. Éxito síncrono con auditoría
    r = client.patch(
        f"/api/reports/{rep_id}/status",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"status": "IN_REVIEW", "human_approved": True, "note": "Aprobado por admin"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "IN_REVIEW"

    with get_conn() as c:
        rec = c.execute(
            "SELECT * FROM operation_records WHERE target_id = %s AND operation_type = 'admin_update_report_status'",
            (str(rep_id),),
        ).fetchone()
        assert rec is not None
        assert rec["status"] == "COMMITTED"
        assert rec["requester_id"] == "admin"

    # 2. Rollback conjunto si la tabla operation_records no estuviese disponible
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as c:
        c.execute("ALTER TABLE operation_records RENAME TO hidden_operation_records")

    try:
        r_fail = client.patch(
            f"/api/reports/{rep_id}/status",
            headers={"X-Admin-Token": settings.ADMIN_TOKEN},
            json={"status": "RESOLVED", "human_approved": True, "note": "Intento sin tabla"},
        )
        assert r_fail.status_code == 500
        # Verificar que el reporte conservó su estado IN_REVIEW anterior
        with get_conn() as c:
            rep = c.execute("SELECT status FROM reports WHERE id = %s", (rep_id,)).fetchone()
            assert rep["status"] == "IN_REVIEW"
    finally:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True) as c:
            c.execute("ALTER TABLE hidden_operation_records RENAME TO operation_records")


def test_adversarial_terminal_state_aborted_immutable(clean_db):
    """
    Contrato A: ABORTED es terminal. mark_operation_committed no puede sobreescribir ABORTED.
    """
    op = str(uuid.uuid4())
    register_operation_intent(op, "test_immutability")
    mark_operation_aborted(op, "Fallo inicial")
    assert get_operation_record(op)["status"] == "ABORTED"

    with pytest.raises(RuntimeError) as exc_info:
        mark_operation_committed(op, {"res": 1})
    assert "ABORTED" in str(exc_info.value)
    assert get_operation_record(op)["status"] == "ABORTED"


def test_adversarial_observation_failure_does_not_abort(clean_db):
    """
    Contrato B: Falla al consultar pg_stat_activity es incertidumbre, jamás prueba de aborto.
    Conserva PENDING y no persiste ABORTED.
    """
    claim = register_operation_intent(str(uuid.uuid4()), "test_obs_failure", backend_pid=999999)
    op = claim["operation_id"]

    orig_connect = psycopg.connect
    class BrokenCursor:
        def __init__(self, c): self.c = c
        def __enter__(self): self.c.__enter__(); return self
        def __exit__(self, *args): return self.c.__exit__(*args)
        def __getattr__(self, k): return getattr(self.c, k)
        def execute(self, q, *args, **kw):
            if "pg_stat_activity" in str(q):
                raise psycopg.OperationalError("SIMULATED OBSERVATION FAILURE")
            return self.c.execute(q, *args, **kw)

    class BrokenConnection:
        def __init__(self, c): self.c = c
        def __enter__(self): self.c.__enter__(); return self
        def __exit__(self, *args): return self.c.__exit__(*args)
        def __getattr__(self, k): return getattr(self.c, k)
        def cursor(self, *args, **kw): return BrokenCursor(self.c.cursor(*args, **kw))

    with patch.object(psycopg, "connect", side_effect=lambda *args, **kw: BrokenConnection(orig_connect(*args, **kw))):
        reconciled = reconcile_operation(op)

    assert reconciled["status"] == "PENDING"
    assert get_operation_record(op)["status"] == "PENDING"


def test_adversarial_unknown_resolves_to_committed_with_own_evidence(clean_db):
    """
    Contrato A: Una operación en UNKNOWN se reconcilia exitosamente a COMMITTED
    cuando existe evidencia exacta vinculada a su operation_id.
    """
    rep_id = uuid.uuid4()
    op = uuid.uuid4()
    claim = register_operation_intent(op, "proponer_actualizacion_critica", target_id=str(rep_id))

    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as c:
        c.execute(
            """
            INSERT INTO reports (
                id, tracking_code, title, description, latitude, longitude, in_service_area,
                photo_path, photo_mime, photo_size_bytes, photo_width, photo_height, photo_sha256,
                status, is_synthetic, version
            ) VALUES (
                %s, 'CIV-2026-UNK001', 'Test UNK', 'Reporte para probar UNKNOWN',
                3.45, -76.53, TRUE, 'sentinel.png', 'image/png', 128, 64, 64, %s,
                'CONFIRMED', FALSE, 1
            );
            """,
            (rep_id, "b" * 64),
        )
        c.execute(
            """
            INSERT INTO pending_approvals (
                id, report_id, proposed_action, proposed_payload, reason, status, operation_id
            ) VALUES (%s, %s, 'UPDATE_REPORT_STATUS', '{"nuevo_estado":"IN_REVIEW"}'::jsonb, 'Razón', 'PENDING', %s);
            """,
            (uuid.uuid4(), rep_id, str(op)),
        )
        # Forzar estado a UNKNOWN
        c.execute("UPDATE operation_records SET status = 'UNKNOWN' WHERE operation_id = %s", (str(op),))

    assert get_operation_record(op)["status"] == "UNKNOWN"

    res = reconcile_operation(op)
    assert res["status"] == "COMMITTED"
    assert res["reconciled"] is True
    assert get_operation_record(op)["status"] == "COMMITTED"


def test_adversarial_replay_terminal_aborted_unknown_no_worker(clean_db):
    """
    Contrato A: Replays de operaciones en ABORTED o UNKNOWN no instancian ni ejecutan workers.
    """
    key_aborted = "aborted-" + uuid.uuid4().hex
    c1 = register_operation_intent(str(uuid.uuid4()), "tool_test", idempotency_key=key_aborted, proposed_payload={"x": 1})
    mark_operation_aborted(c1["operation_id"], "Abortada previamente")

    calls = []
    def dummy_worker(args):
        calls.append(1)
        return {"done": True}

    with patch.dict(a.TOOL_DISPATCH, {"tool_test": dummy_worker}):
        res_abort = a.execute_tool_with_timeout("tool_test", {"x": 1, "idempotency_key": key_aborted}, 1.0)
        assert res_abort["status"] == "ABORTED"
        assert len(calls) == 0

    key_unknown = "unknown-" + uuid.uuid4().hex
    c2 = register_operation_intent(str(uuid.uuid4()), "tool_test", idempotency_key=key_unknown, proposed_payload={"x": 2})
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
        conn.execute("UPDATE operation_records SET status = 'UNKNOWN' WHERE operation_id = %s", (str(c2["operation_id"]),))

    with patch.dict(a.TOOL_DISPATCH, {"tool_test": dummy_worker}):
        with pytest.raises(a.OperationPendingError) as exc_info:
            a.execute_tool_with_timeout("tool_test", {"x": 2, "idempotency_key": key_unknown}, 1.0)
        assert exc_info.value.status == "UNKNOWN"
        assert len(calls) == 0


def test_adversarial_external_timeout_not_local_cancellation():
    """
    Contrato A / F8: Cancelación externa por statement_timeout de 20ms con plazo local a 60ms
    no se clasifica como cancelación local de CIVIA, ni inmediata ni tras vencer el plazo.
    """
    exc = psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
    setattr(exc, "sqlstate", "57014")

    future_deadline = time.monotonic() + 0.060
    assert is_deadline_cancellation(exc, future_deadline) is False

    past_deadline = time.monotonic() - 0.001
    assert is_deadline_cancellation(exc, past_deadline) is False


def test_adversarial_private_operation_unauthorized_404(clean_db):
    """
    Contrato B: Operación privada no revela tipo ni destino a anónimos ni a tokens ajenos (HTTP 404).
    """
    claim = register_operation_intent(
        str(uuid.uuid4()),
        "ADMIN_PRIVATE_TASK",
        target_id="SECRET_TARGET_99",
        requester_id="admin",
    )
    op = str(claim["operation_id"])
    mark_operation_committed(op, {"sensitive": "SECRET_DATA"})

    client = TestClient(m.app)
    # Anónimo -> 404
    r_anon = client.get(f"/api/operations/{op}")
    assert r_anon.status_code == 404

    # Token ajeno -> 404
    other_claim = register_operation_intent(str(uuid.uuid4()), "other")
    r_other = client.get(f"/api/operations/{op}", headers={"X-Operation-Token": other_claim["query_token"]})
    assert r_other.status_code == 404

    # Token propio -> 200 con resultado
    r_own = client.get(f"/api/operations/{op}", headers={"X-Operation-Token": claim["query_token"]})
    assert r_own.status_code == 200
    assert r_own.json()["result_payload"] == {"sensitive": "SECRET_DATA"}


def test_adversarial_hijack_attempt_fails(clean_db):
    """
    Contrato B: Un tercero que conozca la Idempotency-Key y payload no puede obtener
    resultados sensibles si no demuestra ser el propietario legítimo.
    """
    key = "stolen-" + uuid.uuid4().hex
    args = {"idempotency_key": key, "secret_param": "classified"}
    c1 = register_operation_intent(str(uuid.uuid4()), "ADMIN_AUDIT", idempotency_key=key, proposed_payload=args, requester_id="citizen")
    mark_operation_committed(c1["operation_id"], {"secret_key": "VAULT_PASS"})

    with patch.dict(a.TOOL_DISPATCH, {"ADMIN_AUDIT": lambda x: {"executed": True}}):
        # Invocación sin token de propietario no entrega el result_payload privado
        res_eve = a.execute_tool_with_timeout("ADMIN_AUDIT", args, 1.0)
        assert res_eve.get("secret_key") is None
        assert res_eve["status"] == "COMMITTED"
        assert res_eve["replayed"] is True


def test_adversarial_operation_pending_delivers_token():
    """
    Contrato B: OPERATION_PENDING entrega query_token en AgentQueryResponse.
    """
    def pending_worker(args):
        raise a.OperationPendingError("Wait pending", operation_id=uuid.uuid4(), status="PENDING", query_token="test_token_123")

    with patch.dict(a.TOOL_DISPATCH, {"audit_tool": pending_worker}), patch.object(
        a, "_call_agent_turn_gemini", return_value=(None, [{"name": "audit_tool", "args": {}}], 10, 10)
    ):
        client = TestClient(m.app)
        r = client.post("/api/agent/query", json={"query": "consulta sintetica"})
        assert r.status_code == 200
        data = r.json()
        assert data["guardrail_triggered"] == "OPERATION_PENDING"
        assert data["query_token"] == "test_token_123"


# ==============================================================================
# F8 — SUITE OBLIGATORIA: CLASIFICACIÓN DE EVIDENCIA CAUSAL Y TIMEOUTS
# ==============================================================================

def test_f8_1_statement_timeout_57014_late_inspection():
    """
    1. 57014 externo antes del deadline e inspección posterior: False.
    """
    exc = psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
    setattr(exc, "sqlstate", "57014")

    # Deadline configurado en el pasado o presente
    dl = time.monotonic() - 0.05
    assert is_deadline_cancellation(exc, dl) is False
    # Con deadline en el futuro
    assert is_deadline_cancellation(exc, time.monotonic() + 10.0) is False


def test_f8_2_transaction_timeout_25p04_late_inspection():
    """
    2. 25P04 externo antes del deadline e inspección posterior: False.
    """
    exc = psycopg.OperationalError("canceling transaction due to transaction timeout")
    setattr(exc, "sqlstate", "25P04")

    dl = time.monotonic() - 0.05
    assert is_deadline_cancellation(exc, dl) is False
    assert is_deadline_cancellation(exc, time.monotonic() + 5.0) is False


def test_f8_3_external_exception_stable_after_capability_expiry():
    """
    3. Excepción externa inicialmente False; capability expira; misma excepción continúa False.
    """
    dl = time.monotonic() + 0.05
    cap = db.ExecutionCapability(deadline=dl)
    tok = db.set_execution_capability(cap)
    try:
        exc = psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
        setattr(exc, "sqlstate", "57014")

        # Primera evaluación antes de vencer
        first = is_deadline_cancellation(exc, dl)
        assert first is False

        # Esperar a que la capability expire
        time.sleep(0.06)
        assert not cap.is_valid()

        # Segunda evaluación tras expiración
        second = is_deadline_cancellation(exc, dl)
        assert second is False
    finally:
        db.reset_execution_capability(tok)


def test_f8_4_failed_cancel_request_not_local(clean_db):
    """
    4. Solicitud cancel() fallida y posterior timeout externo: False.
    """
    with db.get_conn() as conn:
        def failed_cancel():
            raise RuntimeError("SYNTHETIC CANCEL TRANSPORT FAILURE")

        conn.cancel = failed_cancel
        count = db.cancel_active_conns_for_thread(threading.get_ident())
        assert count == 0
        assert getattr(conn, "_civia_cancel_failed", False) is True

        exc = psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
        setattr(exc, "sqlstate", "57014")
        assert is_deadline_cancellation(exc, time.monotonic() + 2.0) is False


def test_f8_5_cancel_requested_no_conclusive_proof_remains_false():
    """
    5. Cancelación solicitada sin prueba concluyente de causalidad: no atribuirla automáticamente a CIVIA (False).
    """
    exc = psycopg.errors.QueryCanceled("canceling statement due to user request")
    setattr(exc, "sqlstate", "57014")
    # Incluso si una rutina ajena marcó intento de cancelación, sin confirmación positiva local concluyente es False
    assert is_deadline_cancellation(exc, time.monotonic() + 1.0) is False


def test_f8_6_supervisor_timeout_preserves_guardrail():
    """
    6. Timeout generado directamente por el supervisor: conservar guardrail TIMEOUT.
    """
    def slow_worker(args):
        time.sleep(0.2)
        return {"done": True}

    with patch.dict(a.TOOL_DISPATCH, {"slow_tool": slow_worker}):
        with pytest.raises(TimeoutError) as exc_info:
            a.execute_tool_with_timeout("slow_tool", {}, timeout_sec=0.05)
        assert "superó el límite de" in str(exc_info.value)


def test_f8_7_admin_shutdown_57p01_infrastructure():
    """
    7. 57P01 administrativo: conservar clasificación de infraestructura (False).
    """
    exc = psycopg.errors.AdminShutdown("terminating connection due to administrator command")
    setattr(exc, "sqlstate", "57P01")
    assert is_deadline_cancellation(exc, time.monotonic() + 5.0) is False
    assert is_deadline_cancellation(exc, time.monotonic() - 1.0) is False


def test_f8_8_undefined_table_42p01_preserves_original_error():
    """
    8. 42P01 por tabla inexistente: conservar error original (False).
    """
    exc = psycopg.errors.UndefinedTable('relation "nonexistent" does not exist')
    setattr(exc, "sqlstate", "42P01")
    assert is_deadline_cancellation(exc, time.monotonic() + 5.0) is False


def test_f8_9_repeated_classification_stable_immutable():
    """
    9. Repetir la clasificación de la misma excepción en distintos instantes: resultado estable.
    """
    exc = psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
    setattr(exc, "sqlstate", "57014")

    res1 = is_deadline_cancellation(exc, time.monotonic() + 1.0)
    time.sleep(0.02)
    res2 = is_deadline_cancellation(exc, time.monotonic() - 5.0)
    time.sleep(0.02)
    res3 = is_deadline_cancellation(exc, None)

    assert res1 is False
    assert res2 is False
    assert res3 is False


def test_f8_10_positive_local_deadline_classification():
    """
    10. Prueba positiva: error de deadline local genuino: True.
    """
    # Caso A: TimeoutError nativo de Python generado por deadline local de CIVIA
    local_timeout = TimeoutError("Deadline de ejecución expirado: sentencia SQL rechazada.")
    assert is_deadline_cancellation(local_timeout) is True

    # Caso B: Excepción explícitamente confirmada como deadline causal local
    confirmed_exc = psycopg.errors.QueryCanceled("canceling statement due to user request")
    setattr(confirmed_exc, "_civia_confirmed_local_deadline", True)
    assert is_deadline_cancellation(confirmed_exc) is True


# ==============================================================================
# F1 Y F8 — PRUEBAS PERMANENTES DE LÍMITE (GEMINI BOUNDARY Y CONTRAEJEMPLOS COMMIT)
# ==============================================================================

@pytest.mark.allow_mock_transport
def test_f1_gemini_boundary_mock_transport_no_capacity_in_outbound_json(clean_db, monkeypatch):
    """
    F1: Ejecución del adaptador real de Gemini interceptado por httpx.MockTransport.
    Garantiza que la capacidad (client_token) jamás se inyecte en tool_args ni reaparezca
    en raw_gemini_part en la segunda petición serializada.
    """
    import secrets
    import httpx
    from app.ai_router import reset_all_circuits

    reset_all_circuits()
    monkeypatch.setattr(a, "_call_agent_turn_gemini", a._ORIGINAL_CALL_AGENT_TURN_GEMINI)

    old_pri = settings.GOOGLE_API_KEY_PRIMARY
    old_sec = settings.GOOGLE_API_KEY_SECONDARY
    old_groq = settings.GROQ_API_KEY
    settings.GOOGLE_API_KEY_PRIMARY = "SYNTHETIC_NOT_REAL"
    settings.GOOGLE_API_KEY_SECONDARY = ""
    settings.GROQ_API_KEY = ""

    cap = secrets.token_urlsafe(32)
    seen = []
    original_client = httpx.Client

    def handler(request):
        body = json.loads(request.content)
        seen.append({
            "request_number": len(seen) + 1,
            "client_capacity_in_outbound_json": cap in json.dumps(body),
        })
        if len(seen) == 1:
            parts = [
                {
                    "functionCall": {
                        "name": "audit_raw_gemini",
                        "args": {"business": "SYNTHETIC", "nested": {"quantity": 7}},
                    },
                    "thoughtSignature": "SYNTHETIC_SIGNATURE",
                }
            ]
        else:
            parts = [{"text": "Resultado sintético verificado."}]
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": parts}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10},
            },
        )

    def mock_client(*args, **kw):
        return original_client(*args, transport=httpx.MockTransport(handler), **kw)

    def tool(args):
        return {
            "operation_id": str(db.get_current_operation()["operation_id"]),
            "business": "SYNTHETIC",
            "quantity": args["nested"]["quantity"],
        }

    try:
        with patch.object(a.httpx, "Client", side_effect=mock_client), patch.dict(
            a.TOOL_DISPATCH, {"audit_raw_gemini": tool}
        ):
            result = a.run_civia_agent(
                "SYNTHETIC RAW GEMINI BOUNDARY",
                client_token=cap,
                idempotency_key=uuid.uuid4().hex,
                total_timeout_seconds=5,
            )

        # 1. Petición 1 sin capacidad
        assert seen[0]["request_number"] == 1
        assert seen[0]["client_capacity_in_outbound_json"] is False

        # 2. Petición 2 con historial de tool_call sin capacidad en el JSON serializado
        assert seen[1]["request_number"] == 2
        assert seen[1]["client_capacity_in_outbound_json"] is False

        # 3. No filtrado a las herramientas públicas ni al proposed_payload persistido
        assert cap not in json.dumps(result.get("tools_invoked", []))
        assert cap not in json.dumps(get_operation_record(result["operation_id"])["proposed_payload"])
    finally:
        settings.GOOGLE_API_KEY_PRIMARY = old_pri
        settings.GOOGLE_API_KEY_SECONDARY = old_sec
        settings.GROQ_API_KEY = old_groq


def test_f8_external_cancel_during_commit_preserves_error_and_no_local_marker(clean_db):
    """
    F8 Contraejemplo A: pg_cancel_backend externo durante checked_commit cuando aún queda plazo de CIVIA.
    Verifica que:
    - No se enmascara como TimeoutError (preserva QueryCanceled).
    - No se marca _civia_confirmed_local_deadline=True.
    - is_deadline_cancellation retorna False.
    - Rollback e integridad conservados; operation_records pasa a ABORTED.
    """
    with psycopg.connect(clean_db, autocommit=True) as admin_c:
        admin_c.execute("CREATE TABLE IF NOT EXISTS test_f8_ext_cancel(id int PRIMARY KEY, n int);")
        admin_c.execute("DELETE FROM test_f8_ext_cancel;")
        admin_c.execute("INSERT INTO test_f8_ext_cancel VALUES (1, 0);")
        admin_c.execute(
            """
            CREATE OR REPLACE FUNCTION test_f8_sleep_trg() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN PERFORM pg_sleep(0.3); RETURN NEW; END;
            $$;
            """
        )
        admin_c.execute("DROP TRIGGER IF EXISTS trg_test_f8_sleep ON test_f8_ext_cancel;")
        admin_c.execute(
            "CREATE CONSTRAINT TRIGGER trg_test_f8_sleep AFTER UPDATE ON test_f8_ext_cancel DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION test_f8_sleep_trg();"
        )

    op = uuid.uuid4()
    register_operation_intent(op, "external_cancel_test")
    dl = time.monotonic() + 2.0  # Plazo amplio de 2s
    td = db.set_deadline_context(dl)
    to = db.set_current_operation({"operation_id": op})
    controller = None
    caught_error = None

    try:
        with psycopg.connect(clean_db) as conn:
            conn.execute("UPDATE test_f8_ext_cancel SET n = n + 1 WHERE id = 1;")
            pid = conn.info.backend_pid

            def interrupt():
                end = time.monotonic() + 1.5
                with psycopg.connect(clean_db, autocommit=True) as control:
                    while time.monotonic() < end:
                        seen = control.execute(
                            "SELECT state, query, wait_event FROM pg_stat_activity WHERE pid=%s", (pid,)
                        ).fetchone()
                        if seen and seen[0] == "active" and seen[1] == "COMMIT" and seen[2] == "PgSleep":
                            control.execute("SELECT pg_cancel_backend(%s)", (pid,))
                            return
                        time.sleep(0.002)

            controller = threading.Thread(target=interrupt)
            controller.start()
            db.checked_commit(conn)
    except Exception as exc:
        caught_error = exc
    finally:
        if controller:
            controller.join(2.0)
        db.reset_current_operation(to)
        db.reset_deadline_context(td)

    assert caught_error is not None, "Debió ocurrir una excepción por pg_cancel_backend"
    assert not isinstance(caught_error, TimeoutError), f"No debe ser TimeoutError de CIVIA, fue: {type(caught_error).__name__}"
    assert isinstance(caught_error, psycopg.errors.QueryCanceled) or getattr(caught_error, "sqlstate", None) == "57014"
    assert getattr(caught_error, "_civia_confirmed_local_deadline", False) is False
    assert is_deadline_cancellation(caught_error, dl) is False

    # Rollback verificado e integridad en BD
    with psycopg.connect(clean_db, autocommit=True) as verify_c:
        val = verify_c.execute("SELECT n FROM test_f8_ext_cancel WHERE id = 1;").fetchone()[0]
        assert val == 0, "La transacción debió hacer rollback; n debe ser 0"

    rec = get_operation_record(op)
    assert rec["status"] == "ABORTED"


def test_f8_external_session_transaction_timeout_during_commit_preserves_error(clean_db):
    """
    F8 Contraejemplo B: transaction_timeout de sesión externo corto (60ms) con plazo CIVIA amplio (2s).
    Verifica que:
    - No se enmascara como TimeoutError (preserva TransactionTimeout u OperationalError).
    - No se marca _civia_confirmed_local_deadline=True.
    - is_deadline_cancellation retorna False.
    - Rollback e integridad conservados; operation_records pasa a ABORTED.
    """
    with psycopg.connect(clean_db, autocommit=True) as admin_c:
        admin_c.execute("CREATE TABLE IF NOT EXISTS test_f8_ext_tt(id int PRIMARY KEY, n int);")
        admin_c.execute("DELETE FROM test_f8_ext_tt;")
        admin_c.execute("INSERT INTO test_f8_ext_tt VALUES (1, 0);")
        admin_c.execute(
            """
            CREATE OR REPLACE FUNCTION test_f8_sleep_trg_b() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN PERFORM pg_sleep(0.3); RETURN NEW; END;
            $$;
            """
        )
        admin_c.execute("DROP TRIGGER IF EXISTS trg_test_f8_sleep_b ON test_f8_ext_tt;")
        admin_c.execute(
            "CREATE CONSTRAINT TRIGGER trg_test_f8_sleep_b AFTER UPDATE ON test_f8_ext_tt DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION test_f8_sleep_trg_b();"
        )

    op = uuid.uuid4()
    register_operation_intent(op, "external_tt_test")
    dl = time.monotonic() + 2.0  # Plazo amplio de 2s
    td = db.set_deadline_context(dl)
    to = db.set_current_operation({"operation_id": op})
    caught_error = None

    try:
        with psycopg.connect(clean_db, options="-c transaction_timeout=60ms") as conn:
            conn.execute("UPDATE test_f8_ext_tt SET n = n + 1 WHERE id = 1;")
            db.checked_commit(conn)
    except Exception as exc:
        caught_error = exc
    finally:
        db.reset_current_operation(to)
        db.reset_deadline_context(td)

    assert caught_error is not None, "Debió ocurrir una excepción por transaction_timeout externo"
    assert not isinstance(caught_error, TimeoutError), f"No debe ser TimeoutError de CIVIA, fue: {type(caught_error).__name__}"
    assert getattr(caught_error, "sqlstate", None) == "25P04" or isinstance(caught_error, (psycopg.errors.OperationalError, getattr(psycopg.errors, "TransactionTimeout", ())))
    assert getattr(caught_error, "_civia_confirmed_local_deadline", False) is False
    assert is_deadline_cancellation(caught_error, dl) is False

    with psycopg.connect(clean_db, autocommit=True) as verify_c:
        val = verify_c.execute("SELECT n FROM test_f8_ext_tt WHERE id = 1;").fetchone()[0]
        assert val == 0, "La transacción debió hacer rollback; n debe ser 0"

    rec = get_operation_record(op)
    assert rec["status"] == "ABORTED"
