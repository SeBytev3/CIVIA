from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from psycopg.types.json import Jsonb

from app.bootstrap_admins import bootstrap_admin_accounts
from app.config import settings
from app.db import ensure_isolated_database, get_conn, run_migrations
from app.identity import AccountRegistration
from app import main as main_module
from app.main import app
from app.repository import ReceiptCommitUncertain
from tests.conftest import create_authenticated_client


def new_account():
    return {
        "name": "Persona sintética",
        "email": f"{uuid4().hex}@example.test",
        "password": "Synthetic test only, long passphrase.",
    }


def register(client):
    response = client.post("/api/auth/register", json=new_account())
    assert response.status_code == 201
    return response.json()


def test_public_registration_issues_citizen_cookie():
    client = TestClient(app)
    response = client.post("/api/auth/register", json=new_account())
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "CITIZEN"
    assert response.json().get("token") is None
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert client.get("/api/auth/session").json()["user"]["role"] == "CITIZEN"


def test_cookie_logout_requires_csrf_then_revokes_session():
    client = TestClient(app)
    session = register(client)
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post(
        "/api/auth/logout", headers={"X-CSRF-Token": session["csrf_token"]}
    ).status_code == 204
    assert client.get("/api/auth/session").status_code == 401


def test_reports_and_administration_require_a_session():
    client = TestClient(app)
    assert client.get("/api/reports").status_code == 401
    assert client.get("/api/admin/observability").status_code == 401
    assert client.post("/api/agent/query", json={"query": "Reportes de mi cuenta"}).status_code == 401


def test_citizen_cannot_access_case_or_web_administration():
    client = TestClient(app)
    register(client)
    assert client.get("/api/admin/notifications").status_code == 403
    assert client.get("/api/admin/observability").status_code == 403


def test_case_admin_can_read_case_but_cannot_read_web_admin_views(case_admin_client):
    assert case_admin_client.get("/api/admin/notifications").status_code == 200
    assert case_admin_client.get("/api/admin/users").status_code == 403
    assert case_admin_client.get("/api/admin/audit").status_code == 403
    assert case_admin_client.get("/api/admin/observability").status_code == 403
    assert case_admin_client.get("/api/admin/queue").status_code == 403


def test_legacy_admin_token_does_not_authorize_http_admin():
    response = TestClient(app).get(
        "/api/admin/observability", headers={"X-Admin-Token": settings.ADMIN_TOKEN}
    )
    assert response.status_code == 401


def test_revoked_or_expired_mobile_session_has_no_access(web_admin_client):
    client, user = create_authenticated_client(mode="bearer")
    assert not client.cookies
    assert client.get("/api/auth/session").status_code == 200
    updated = web_admin_client.patch(f"/api/admin/users/{user['id']}", json={"active": False})
    assert updated.status_code == 200
    assert client.get("/api/auth/session").status_code == 401

    expired_client, expired_user = create_authenticated_client(mode="bearer")
    with get_conn() as conn:
        conn.execute("UPDATE auth_sessions SET expires_at = NOW() WHERE user_id = %s", (expired_user["id"],))
        conn.commit()
    assert expired_client.get("/api/auth/session").status_code == 401


def test_password_reset_revokes_sessions_and_audit_omits_secrets(web_admin_client):
    client, user = create_authenticated_client()
    new_password = new_account()["password"]
    response = web_admin_client.post(
        f"/api/admin/users/{user['id']}/reset-password", json={"password": new_password}
    )
    assert response.status_code == 204
    assert client.get("/api/auth/session").status_code == 401
    new_session = client.post("/api/auth/login", json={"email": user["email"], "password": new_password})
    assert new_session.status_code == 200
    audit = web_admin_client.get("/api/admin/audit")
    assert audit.status_code == 200
    assert new_password not in audit.text and "password_hash" not in audit.text
    assert any(row["action"] == "users.reset_password" and row["target_id"] == user["id"] for row in audit.json()["items"])


def test_bootstrap_can_run_once_and_last_web_admin_is_protected(monkeypatch):
    isolated_url = ensure_isolated_database(f"civia_test_bootstrap_{uuid4().hex[:10]}")
    monkeypatch.setattr(settings, "DATABASE_URL", isolated_url)
    run_migrations()
    web = AccountRegistration.model_validate(new_account())
    cases = AccountRegistration.model_validate(new_account())
    assert bootstrap_admin_accounts(web, cases) is True
    assert bootstrap_admin_accounts(web, cases) is False
    client = TestClient(app)
    authenticated = client.post("/api/auth/login", json={"email": web.email, "password": web.password})
    assert authenticated.status_code == 200
    session = authenticated.json()
    client.headers["X-CSRF-Token"] = session["csrf_token"]
    target = f"/api/admin/users/{session['user']['id']}"
    assert client.patch(target, json={"active": False}).status_code == 409
    assert client.patch(target, json={"role": "CASE_ADMIN"}).status_code == 409
    assert client.get("/api/auth/session").json()["user"]["role"] == "WEB_ADMIN"


def test_login_uses_generic_denial_and_limited_account_window():
    client = TestClient(app, client=("192.0.2.231", 50000))
    new = new_account()
    register_response = client.post("/api/auth/register", json=new)
    assert register_response.status_code == 201
    registered = {"email": new["email"].upper(), "password": "Incorrecta"}
    missing = {"email": new_account()["email"], "password": "Incorrecta"}
    unknown = client.post("/api/auth/login", json=missing)
    assert unknown.status_code == 401
    for _ in range(6):
        wrong_password = client.post("/api/auth/login", json=registered)
        assert wrong_password.status_code == 401
        assert wrong_password.json() == unknown.json()
    assert client.post("/api/auth/login", json=registered).status_code == 429


def _submit_report(client, headers=None):
    evidence = BytesIO()
    Image.new("RGB", (64, 64), (67, 100, 120)).save(evidence, "JPEG")
    return client.post(
        "/api/reports",
        data={"description": "Bache profundo en cruce de tránsito.", "latitude": 3.44567, "longitude": -76.52873},
        files={"photo": ("sintetica.jpg", evidence.getvalue(), "image/jpeg")},
        headers=headers,
    )


def test_report_private_to_owner_and_public_map_is_minimized(citizen_client, case_admin_client):
    assert _submit_report(case_admin_client).status_code == 403
    response = _submit_report(citizen_client)
    assert response.status_code == 201
    item = response.json()
    report_path = f"/api/reports/{item['id']}"
    tracking_path = f"/api/reports/by-code/{item['tracking_code']}"
    other, _ = create_authenticated_client()
    assert citizen_client.get("/api/reports").json()["total"] == 1
    assert other.get("/api/reports").json()["total"] == 0
    for path in (report_path, tracking_path, f"{report_path}/photo", f"{report_path}/events", f"{tracking_path}/events"):
        assert citizen_client.get(path).status_code == 200
        assert other.get(path).status_code == 404
        assert case_admin_client.get(path).status_code == 200
    assert other.patch(f"{report_path}/confirm", json={"final_category": "HUECO"}).status_code == 404
    assert citizen_client.patch(f"{report_path}/confirm", json={"final_category": "HUECO"}).status_code == 200

    management_url = f"/api/admin/reports/{item['id']}"
    note = "La nota privada debe aparecer solo en el portal."
    assert case_admin_client.post(f"{management_url}/management", json={"internal_note": note}).status_code == 200
    assert case_admin_client.get(f"{management_url}/internal-notes").json()["items"][0]["note"] == note
    assert citizen_client.get(f"{management_url}/internal-notes").status_code == 403
    assert note not in citizen_client.get(report_path).text
    assert note not in citizen_client.get(f"{report_path}/events").text

    results = TestClient(app).get("/api/public/reports").json()["items"]
    assert {"latitude": 3.45, "longitude": -76.53, "category": "HUECO", "severity": "MEDIA", "status": "CONFIRMED"} in results
    assert all(set(point) == {"latitude", "longitude", "category", "severity", "status"} for point in results)


def test_uncertain_receipt_can_retry_identically_and_preserves_evidence(monkeypatch, citizen_client):
    real_create = main_module.create_report

    def commit_then_lose_acknowledgement(**kwargs):
        real_create(**kwargs)
        raise ReceiptCommitUncertain()

    headers = {"Idempotency-Key": uuid4().hex}
    with monkeypatch.context() as context:
        context.setattr(main_module, "create_report", commit_then_lose_acknowledgement)
        pending = _submit_report(citizen_client, headers)
    assert pending.status_code == 503
    assert pending.json()["error"] == "RECEIPT_UNCONFIRMED"
    saved = _submit_report(citizen_client, headers)
    assert saved.status_code == 201
    assert citizen_client.get(saved.json()["photo_url"]).status_code == 200
    assert citizen_client.get("/api/reports").json()["total"] == 1


def test_case_operator_approval_records_actor_once_and_uses_public_event(
    citizen_client, case_admin_client, web_admin_client
):
    created = _submit_report(citizen_client)
    assert created.status_code == 201
    report_id = created.json()["id"]
    owner_id = citizen_client.get("/api/auth/session").json()["user"]["id"]
    reviewer_id = case_admin_client.get("/api/auth/session").json()["user"]["id"]
    reason = "Explicación interna para revisión exclusivamente administrativa."
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pending_approvals (report_id, proposed_action, proposed_payload, reason, requested_by, id)
            VALUES (%s, 'UPDATE_REPORT_STATUS', %s, %s, %s, gen_random_uuid()) RETURNING id;
            """,
            (report_id, Jsonb({"previous_status": "PENDING_ANALYSIS", "expected_version": 1, "proposed_status": "IN_REVIEW"}),
             reason, owner_id),
        )
        approval_id = cur.fetchone()["id"]
        conn.commit()

    path = f"/api/admin/approvals/{approval_id}/decide"
    assert citizen_client.post(path, json={"approve": True}).status_code == 403
    assert case_admin_client.post(path, json={"approve": True}).status_code == 200
    assert case_admin_client.post(path, json={"approve": False}).status_code == 409
    audit_page = web_admin_client.get("/api/admin/audit").json()["items"]
    actions = [entry for entry in audit_page if entry["target_id"] == str(approval_id)]
    assert [(action["actor_id"], action["action"]) for action in actions] == [(reviewer_id, "approvals.approve")]
    events = citizen_client.get(f"/api/reports/{report_id}/events")
    assert reason not in events.text and reviewer_id not in events.text
    assert any(event["new_status"] == "IN_REVIEW" for event in events.json())
