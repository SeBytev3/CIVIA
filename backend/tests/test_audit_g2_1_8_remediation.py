import hashlib
import hmac
import json
import secrets
import time
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
import psycopg
import pytest

from app import agent as a, db, main as m
from app.config import settings
from app.db import (
    get_conn,
    get_operation_record,
    is_deadline_cancellation,
    mark_operation_aborted,
    mark_operation_committed,
    mark_operation_unknown,
    reconcile_operation,
    register_operation_intent,
)

from tests.conftest import create_authenticated_client


@pytest.fixture
def clean_db():
    from tests.test_audit_g2_1_remediation import _get_clean_test_db
    test_db = _get_clean_test_db("test_g218_remed")
    old_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db
    try:
        yield test_db
    finally:
        settings.DATABASE_URL = old_url


def test_f1_owner_token_replay_no_nameerror_and_no_secret_in_proposed_payload(clean_db):
    """
    F1: El replay con prueba de posesión no debe fallar por NameError (import hmac presente en db.py),
    y la capacidad secreta no debe quedar persistida en texto plano en proposed_payload.
    """
    token = secrets.token_urlsafe(32)
    key = uuid.uuid4().hex
    args = {"idempotency_key": key, "operation_token": token, "data": "business_arg"}
    
    claim = register_operation_intent(
        uuid.uuid4(),
        "audit_f1_owner",
        idempotency_key=key,
        proposed_payload=args,
        client_token=token,
    )
    op_id = claim["operation_id"]
    mark_operation_committed(op_id, {"ok": True, "secret_calc": 42})
    
    # 1. Comprobar que proposed_payload persistido NO contiene el token secreto en claro
    rec = get_operation_record(op_id)
    assert rec is not None
    serialized_proposed = json.dumps(rec.get("proposed_payload") or {})
    assert token not in serialized_proposed, "El token en claro NO debe quedar en proposed_payload durable"
    
    # 2. Replay con el token propio: debe reconocer posesión sin NameError y devolver el payload
    with patch.dict(a.TOOL_DISPATCH, {"audit_f1_owner": lambda a: {"should_not_run": True}}):
        res = a.execute_tool_with_timeout("audit_f1_owner", args, 1.0)
    
    assert res == {"ok": True, "secret_calc": 42}


def test_f2_privacy_in_replays_no_result_target_or_error_leak(clean_db):
    """
    F2: Replays no autenticados no deben divulgar result_payload privado, target_id sensible,
    ni el mensaje de error interno detallado de operaciones abortadas.
    """
    # Caso 2.1: Operación ciudadana COMMITTED con payload privado
    key_pub = uuid.uuid4().hex
    args_pub = {"idempotency_key": key_pub, "param": "val"}
    c_pub = register_operation_intent(
        uuid.uuid4(), "audit_public_tool", idempotency_key=key_pub, proposed_payload=args_pub
    )
    mark_operation_committed(c_pub["operation_id"], {"private": "SYNTHETIC SECRET RESULT"})
    
    # Invocador sin token (anónimo): replay NO debe revelar {"private": "SYNTHETIC SECRET RESULT"}
    with patch.dict(a.TOOL_DISPATCH, {"audit_public_tool": lambda a: (_ for _ in ()).throw(AssertionError("NO WORKER"))}):
        r_unauth = a.execute_tool_with_timeout("audit_public_tool", args_pub, 1.0)
    
    assert "private" not in r_unauth
    assert r_unauth.get("status") == "COMMITTED"
    assert r_unauth.get("replayed") is True
    
    # Caso 2.2: Operación privada ADMIN_PRIVATE_REPLAY con target_id
    key_priv = uuid.uuid4().hex
    args_priv = {"idempotency_key": key_priv, "param": "admin_val"}
    c_priv = register_operation_intent(
        uuid.uuid4(),
        "ADMIN_PRIVATE_REPLAY",
        idempotency_key=key_priv,
        proposed_payload=args_priv,
        target_id="SYNTHETIC_PRIVATE_TARGET",
    )
    mark_operation_committed(c_priv["operation_id"], {"admin_secret": "TOP_SECRET"})
    
    with patch.dict(a.TOOL_DISPATCH, {"ADMIN_PRIVATE_REPLAY": lambda a: (_ for _ in ()).throw(AssertionError("NO WORKER"))}):
        r_priv = a.execute_tool_with_timeout("ADMIN_PRIVATE_REPLAY", args_priv, 1.0)
    
    assert "admin_secret" not in r_priv
    assert r_priv.get("target_id") is None, "target_id privado no debe ser expuesto a llamador no autorizado"
    
    # Caso 2.3: Operación abortada privada ADMIN_ABORT_PRIVATE
    key_abort = uuid.uuid4().hex
    args_abort = {"idempotency_key": key_abort}
    c_abort = register_operation_intent(
        uuid.uuid4(),
        "ADMIN_ABORT_PRIVATE",
        idempotency_key=key_abort,
        proposed_payload=args_abort,
        target_id="SYNTHETIC_ADMIN_TARGET",
    )
    mark_operation_aborted(c_abort["operation_id"], "SYNTHETIC PRIVATE FAILURE DETAIL")
    
    with patch.dict(a.TOOL_DISPATCH, {"ADMIN_ABORT_PRIVATE": lambda a: (_ for _ in ()).throw(AssertionError("NO WORKER"))}):
        r_abort = a.execute_tool_with_timeout("ADMIN_ABORT_PRIVATE", args_abort, 1.0)
    
    assert r_abort.get("status") == "ABORTED"
    assert r_abort.get("target_id") is None
    assert "SYNTHETIC PRIVATE FAILURE DETAIL" not in str(r_abort.get("mensaje")), "Detalle de fallo interno no debe ser expuesto"


def test_f3_private_operation_requires_web_admin_or_the_owner(clean_db):
    owner, profile = create_authenticated_client("CASE_ADMIN")
    other, _ = create_authenticated_client()
    web_admin, _ = create_authenticated_client("WEB_ADMIN")
    case_admin, _ = create_authenticated_client("CASE_ADMIN")
    operation_id = uuid.uuid4()
    path = f"/api/operations/{operation_id}"
    register_operation_intent(
        operation_id, "ADMIN_F3", requester_id=profile["id"], target_id="sintetico"
    )
    mark_operation_committed(operation_id, {"private": "RESULTADO SINTÉTICO"})

    assert TestClient(m.app).get(path).status_code == 401
    assert other.get(path).status_code == 404
    assert case_admin.get(path).status_code == 404
    assert owner.get(path).json()["result_payload"] == {"private": "RESULTADO SINTÉTICO"}
    assert web_admin.get(path).status_code == 200


def test_f4_pending_operation_response_scopes_request_and_omits_private_data(clean_db):
    client, profile = create_authenticated_client()
    idempotency_key = f"synthetic-http-{secrets.token_hex(8)}"
    operation_id = str(uuid.uuid4())
    result = {
        "answer": "Operación en proceso.",
        "trace_group_id": str(uuid.uuid4()),
        "tools_invoked": [],
        "iterations_used": 1,
        "total_tokens_used": 20,
        "latency_ms": 30,
        "guardrail_triggered": "OPERATION_PENDING",
        "operation_id": operation_id,
        "operation_status": "PENDING",
        "query_token": secrets.token_urlsafe(32),
    }
    with patch("app.main.run_civia_agent", return_value=result) as mock_agent:
        response = client.post(
            "/api/agent/query",
            json={"query": "consulta sintética en proceso"},
            headers={"Idempotency-Key": idempotency_key},
        )
    assert response.status_code == 200
    assert response.json() == {
        "answer": "Operación en proceso.",
        "requires_human_approval": False,
        "pending_approval_id": None,
        "operation_id": operation_id,
        "operation_status": "PENDING",
    }
    assert mock_agent.call_args.kwargs["owner_id"] == uuid.UUID(profile["id"])
    assert mock_agent.call_args.kwargs["idempotency_key"] == idempotency_key


def test_f5_unknown_cannot_be_committed_without_evidence_and_get_reconciles_unknown(clean_db):
    """
    F5: mark_operation_committed no puede confirmar UNKNOWN sin evidencia duradera propia.
    Y GET /api/operations/{id} autorizado debe reconciliar operaciones en estado UNKNOWN.
    """
    client, profile = create_authenticated_client(raise_server_exceptions=False)
    op = uuid.uuid4()
    register_operation_intent(op, "audit_f5_tool", requester_id=profile["id"])
    mark_operation_unknown(op)
    
    # 1. Intento de confirmación genérica sin evidencia debe ser rechazado
    with pytest.raises(RuntimeError):
        mark_operation_committed(op, {"synthetic": "NO EVIDENCE"})
    
    assert get_operation_record(op)["status"] == "UNKNOWN", "UNKNOWN no debe pasar a COMMITTED sin evidencia"
    
    # 2. Con evidencia propia ligada al operation_id exacto:
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as c:
        row = c.execute("SELECT id FROM reports LIMIT 1").fetchone()
        if row:
            rid = row[0]
        else:
            rid = uuid.uuid4()
            c.execute(
                """
                INSERT INTO reports (
                    id, tracking_code, title, description, latitude, longitude, in_service_area,
                    photo_path, photo_mime, photo_size_bytes, photo_width, photo_height, photo_sha256,
                    status, is_synthetic
                )
                VALUES (
                    %s, 'CIV-2026-F5001', 'Test F5', 'Reporte F5 test', 3.45, -76.53, TRUE,
                    'test_f5.jpg', 'image/jpeg', 100, 64, 64, 'sha256dummy',
                    'PENDING_ANALYSIS', TRUE
                )
                """,
                (rid,),
            )
        c.execute(
            """
            INSERT INTO pending_approvals (id, report_id, proposed_action, proposed_payload, reason, status, operation_id)
            VALUES (%s, %s, 'UPDATE_REPORT_STATUS', '{}'::jsonb, 'EVIDENCIA PROPIA', 'PENDING', %s)
            """,
            (uuid.uuid4(), rid, op),
        )
    
    # La sesión del titular autoriza la reconciliación.
    r_get = client.get(f"/api/operations/{op}")
    assert r_get.status_code == 200
    assert r_get.json()["status"] == "COMMITTED"


def test_f6_absent_backend_pid_does_not_infer_aborted_and_no_unauthorized_reconcile(clean_db):
    """
    F6: Un backend_pid ausente o inexistente NO debe inferir ABORTED por sí solo (debe quedar PENDING/UNKNOWN).
    Y una petición GET no autorizada a una operación privada no debe ejecutar reconciliación ni mutar estado.
    """
    client, _ = create_authenticated_client(raise_server_exceptions=False)
    op = uuid.uuid4()
    register_operation_intent(op, "ADMIN_PRIVATE_F6", requester_id="admin", backend_pid=999999)
    assert get_operation_record(op)["status"] == "PENDING"
    
    # 1. Una sesión de otra identidad no puede reconciliar la operación.
    r_other = client.get(f"/api/operations/{op}")
    assert r_other.status_code == 404
    rec_after_anon = get_operation_record(op)
    assert rec_after_anon["status"] == "PENDING", "Petición no autorizada NO debe mutar el estado de la operación"
    
    # 2. Reconciliación directa sin evidencia: no debe deducir ABORTED solo por PID ausente
    res_rec = reconcile_operation(op)
    assert res_rec["status"] in ("PENDING", "UNKNOWN"), f"PID ausente no debe producir ABORTED falso (dio {res_rec['status']})"
    assert get_operation_record(op)["status"] in ("PENDING", "UNKNOWN")


def test_f7_rest_status_mutation_records_detailed_changes_in_ledger(clean_db):
    """
    F7: La mutación REST PATCH /api/reports/{id}/status debe persistir en operation_records
    el estado anterior, el nuevo estado, las versiones y la nota en proposed_payload / result_payload.
    """
    client, profile = create_authenticated_client("CASE_ADMIN", raise_server_exceptions=False)
    
    rep_id = uuid.uuid4()
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as c:
        c.execute(
            """
            INSERT INTO reports (
                id, tracking_code, title, description, latitude, longitude, in_service_area,
                photo_path, photo_mime, photo_size_bytes, photo_width, photo_height, photo_sha256,
                status, is_synthetic, version
            ) VALUES (
                %s, 'CIV-2026-F7AUD', 'Reporte F7', 'Prueba auditoria detallada.',
                3.45, -76.53, TRUE, 'sentinel.png', 'image/png', 128, 64, 64, %s,
                'CONFIRMED', FALSE, 3
            );
            """,
            (rep_id, "c" * 64),
        )
    
    r = client.patch(
        f"/api/reports/{rep_id}/status",
        json={"status": "IN_REVIEW", "human_approved": True, "note": "Nota administrativa de auditoria F7"},
    )
    assert r.status_code == 200
    
    with psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=psycopg.rows.dict_row) as c:
        rows = c.execute(
            "SELECT * FROM operation_records WHERE target_id = %s AND operation_type = 'admin_update_report_status'",
            (str(rep_id),),
        ).fetchall()
    
    assert len(rows) == 1
    ledger = rows[0]
    assert ledger["requester_id"] == profile["id"]
    assert ledger["status"] == "COMMITTED"
    
    proposed = ledger.get("proposed_payload") or {}
    result = ledger.get("result_payload") or {}
    
    assert proposed.get("previous_status") == "CONFIRMED"
    assert proposed.get("new_status") == "IN_REVIEW"
    assert proposed.get("expected_version") == 3
    assert result.get("status") == "IN_REVIEW"
    assert result.get("version") == 4
    assert result.get("note") == "Nota administrativa de auditoria F7"


def test_f8_cancellation_provenance_not_skewed_by_delayed_inspection(clean_db):
    """
    F8: Una cancelación PostgreSQL externa ocurrida antes del deadline no debe ser clasificada
    como cancelación local de plazo simplemente porque la excepción se inspeccione después de transcurrido el tiempo.
    """
    for setting in ["statement_timeout", "transaction_timeout"]:
        with psycopg.connect(settings.DATABASE_URL) as c:
            c.execute(f"SET {setting} = '20ms'")
            dl = time.monotonic() + 0.06
            try:
                c.execute("SELECT pg_sleep(0.2)")
            except Exception as e:
                # Inmediatamente: tiempo actual < dl
                immediate_local = is_deadline_cancellation(e, dl)
                assert immediate_local is False, f"Timeout externo {setting} no debe ser clasificado como local inmediatamente"
                
                # Simular retención de la excepción pasando el tiempo del deadline
                time.sleep(0.07)
                delayed_local = is_deadline_cancellation(e, dl)
                assert delayed_local is False, f"Timeout externo {setting} NO debe ser clasificado como local en inspección tardía"
