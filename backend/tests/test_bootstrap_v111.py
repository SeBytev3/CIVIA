import json
import stat
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.bootstrap_admins import main as bootstrap_cli
from app.config import settings
from app.db import ensure_isolated_database, get_conn, run_migrations
from app.main import app
from app.seed import DEMO_ASSETS_DIR


def test_installation_metadata_is_public_minimal_and_stable(monkeypatch):
    monkeypatch.setattr(settings, "BUILD_SHA", "a" * 40, raising=False)
    client = TestClient(app)
    first = client.get("/api/meta")
    second = TestClient(app).get("/api/meta")
    assert first.status_code == second.status_code == 200
    document = first.json()
    assert document == second.json()
    assert set(document) == {"version", "commit", "installation_id", "protocol"}
    assert document["version"] == settings.VERSION
    assert document["commit"] == "a" * 40
    assert document["protocol"] == 1
    assert UUID(document["installation_id"]).version == 4
    assert first.headers["cache-control"] == "no-store"


def test_unready_database_fails_the_http_healthcheck(monkeypatch):
    monkeypatch.setattr("app.main.check_db_health", lambda: {"connected": True, "schema_ready": False})
    response = TestClient(app).get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_lan_cookie_uses_https_from_the_configured_gateway(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "172.28.0.2")
    tls_host = "civia.local:5443"
    request_headers = {"Origin": f"https://{tls_host}", "X-Forwarded-Proto": "https"}
    credentials = {
        "name": "Prueba TLS",
        "email": f"{uuid4().hex}@example.test",
        "password": "Fixture local para prueba TLS",
    }
    direct = TestClient(app, base_url=f"http://{tls_host}", client=("198.51.100.11", 5000))
    assert direct.post("/api/auth/register", json=credentials, headers=request_headers).status_code == 403
    proxied = TestClient(app, base_url=f"http://{tls_host}", client=("172.28.0.2", 5000))
    response = proxied.post("/api/auth/register", json=credentials, headers=request_headers)
    assert response.status_code == 201
    assert "; Secure" in response.headers["set-cookie"]


def test_stale_browser_submission_cannot_use_the_new_session(citizen_client):
    profile = citizen_client.get("/api/auth/session").json()["user"]
    installation = citizen_client.get("/api/meta").json()["installation_id"]
    photo = (DEMO_ASSETS_DIR / "civ-2026-demo0001.jpg").read_bytes()
    for headers in (
        {"X-Civia-Account": str(uuid4()), "X-Civia-Installation": installation},
        {"X-Civia-Account": profile["id"], "X-Civia-Installation": str(uuid4())},
        {"X-Civia-Account": profile["id"]},
    ):
        response = citizen_client.post(
            "/api/reports",
            data={"description": "Prueba de alcance de borradores.", "latitude": "3.45", "longitude": "-76.53"},
            files={"photo": ("fixture.jpg", photo, "image/jpeg")},
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["error"] == "REPORT_SCOPE_CHANGED"
    with get_conn() as conn:
        assert conn.execute("SELECT count(*) AS total FROM reports WHERE owner_id = %s", (profile["id"],)).fetchone()["total"] == 0


def test_automatic_bootstrap_creates_accounts_once_and_keeps_credentials_private(tmp_path, monkeypatch, capsys):
    isolated = ensure_isolated_database(f"civia_test_bootstrap_{uuid4().hex[:8]}", settings.DATABASE_URL)
    monkeypatch.setattr(settings, "DATABASE_URL", isolated)
    run_migrations()
    credentials = tmp_path / "admin-access.json"
    monkeypatch.setattr("sys.argv", [
        "bootstrap_admins", "--automatic", "--credentials-file", str(credentials),
    ])
    with get_conn(3000) as conn:
        active_count_before = conn.execute(
            "SELECT COUNT(*) AS total FROM users WHERE role IN ('WEB_ADMIN', 'CASE_ADMIN')",
        ).fetchone()["total"]

    assert bootstrap_cli() == 0
    private_content = credentials.read_bytes()
    accounts = json.loads(private_content)["accounts"]
    assert set(accounts) == {"WEB_ADMIN", "CASE_ADMIN"}
    assert stat.S_IMODE(credentials.stat().st_mode) & 0o077 == 0
    assert accounts["WEB_ADMIN"]["password"] != accounts["CASE_ADMIN"]["password"]
    assert all(len(account["password"]) >= 32 for account in accounts.values())
    for role, credentials_for_role in accounts.items():
        session = TestClient(app).post("/api/auth/login", json=credentials_for_role)
        assert session.status_code == 200
        assert session.json()["user"]["role"] == role

    assert bootstrap_cli() == 0
    assert credentials.read_bytes() == private_content
    with get_conn(3000) as conn:
        active_count_after = conn.execute(
            "SELECT COUNT(*) AS total FROM users WHERE role IN ('WEB_ADMIN', 'CASE_ADMIN')",
        ).fetchone()["total"]
    assert active_count_after == active_count_before + 2
    output = capsys.readouterr().out
    assert all(account["password"] not in output for account in accounts.values())
