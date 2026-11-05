import hashlib
import hmac
import json
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
    Contrato A: Cancelación externa por statement_timeout de 20ms con plazo local a 60ms
    no se clasifica falsamente como cancelación local de CIVIA (margen de 50ms eliminado).
    """
    exc = psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
    setattr(exc, "sqlstate", "57014")

    future_deadline = time.monotonic() + 0.060
    assert is_deadline_cancellation(exc, future_deadline) is False

    past_deadline = time.monotonic() - 0.001
    assert is_deadline_cancellation(exc, past_deadline) is True


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
