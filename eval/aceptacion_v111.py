"""Smoke de caja negra contra el gateway de un despliegue Compose desechable."""

import argparse
import io
import json
import os
from pathlib import Path
import secrets
import time
from uuid import uuid4
import wave

import httpx

ORIGIN = "http://frontend"


def expect(response: httpx.Response, status: int) -> httpx.Response:
    if response.status_code != status:
        raise AssertionError(f"{response.request.method} {response.request.url.path}: "
                             f"esperado {status}, recibido {response.status_code}")
    return response


def session(client: httpx.Client, response: httpx.Response, role: str, status: int = 200) -> dict:
    data = expect(response, status).json()
    assert data["user"]["role"] == role
    assert "HttpOnly" in response.headers["set-cookie"]
    client.headers["X-CSRF-Token"] = data["csrf_token"]
    return data["user"]


def silent_audio() -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(bytes(16000))
    return stream.getvalue()


def create_citizen(client: httpx.Client) -> dict:
    credentials = {
        "name": "Evaluación CIVIA sintética",
        "email": f"{uuid4().hex}@example.test",
        "password": secrets.token_urlsafe(32),
    }
    return session(client, client.post("/api/auth/register", json=credentials), "CITIZEN", 201)


def verify(credentials_file: Path) -> dict:
    if any(os.getenv(name) for name in ("GOOGLE_API_KEY_PRIMARY", "GROQ_API_KEY")):
        raise SystemExit("Esta prueba se ejecuta en un clon desechable con claves de IA vacías.")
    private = json.loads(credentials_file.read_text(encoding="utf-8"))
    clients = [httpx.Client(base_url=ORIGIN, timeout=8, trust_env=False) for _ in range(4)]
    web, cases, citizen, other = clients
    try:
        meta = expect(web.get("/api/meta"), 200).json()
        build = expect(web.get("/build.json"), 200).json()
        assert meta["version"] == build["version"] == "1.1.1"
        assert meta["commit"] == build["commit"]
        assert meta["installation_id"] == private["installation_id"]
        for path in ("/", "/app/", "/admin/", "/health"):
            expect(web.get(path), 200)
        for path in ("/app/", "/admin/"):
            manifest = expect(web.get(f"{path}manifest.webmanifest"), 200).json()
            assert manifest["scope"] == path
            expect(web.get(f"{path}sw.js"), 200)

        for client, role in ((web, "WEB_ADMIN"), (cases, "CASE_ADMIN")):
            result = client.post("/api/auth/login", json=private["accounts"][role])
            session(client, result, role)
        create_citizen(citizen)
        other_user = create_citizen(other)
        for path in ("/api/admin/users", "/api/admin/audit", "/api/admin/observability",
                     "/api/admin/system", "/api/admin/queue", "/api/admin/queue/dead-letter"):
            expect(web.get(path), 200)
            expect(cases.get(path), 403)
            expect(citizen.get(path), 403)
        expect(cases.get("/api/admin/approvals"), 200)
        expect(citizen.get("/api/admin/approvals"), 403)
        expect(web.post("/api/admin/fault-injection", json={"mode": "TOTAL"}), 200)
        try:
            report = _receipt(citizen, other, web)
        finally:
            expect(web.post("/api/admin/fault-injection", json={"mode": "NONE"}), 200)

        _manage_report(cases, citizen, report)
        expect(web.patch(f"/api/admin/users/{other_user['id']}", json={"active": False}), 200)
        expect(other.get("/api/auth/session"), 401)
        for client in (citizen, cases, web):
            expect(client.post("/api/auth/logout"), 204)
            expect(client.get("/api/auth/session"), 401)
        return {"version": meta["version"], "commit": meta["commit"], "radicado_sintetico": report["tracking_code"],
                "receipt": True, "worker_retry": True, "roles": 3, "private_notes": True,
                "evidence": ["foto", "audio"], "revocation": True}
    finally:
        for client in clients:
            client.close()


def _receipt(citizen: httpx.Client, other: httpx.Client, web: httpx.Client) -> dict:
    photo = Path("/app/app/demo_assets/civ-2026-demo0001.jpg").read_bytes()
    audio = silent_audio()
    request = {
        "headers": {"Idempotency-Key": str(uuid4())},
        "data": {"title": "Caso sintético de aceptación", "description": "Ensayo aislado de radicación CIVIA.",
                 "latitude": "3.45", "longitude": "-76.53"},
        "files": {"photo": ("demo.jpg", photo, "image/jpeg"), "audio": ("test.wav", audio, "audio/wav")},
    }
    report = expect(citizen.post("/api/reports", **request), 201).json()
    replay = citizen.post("/api/reports", **request)
    assert replay.status_code in (200, 201)
    assert replay.json()["id"] == report["id"]
    assert report["status"] == "PENDING_ANALYSIS"
    assert report["analysis_status"] == "PENDING"
    expect(citizen.get(report["photo_url"]), 200)
    expect(other.get(report["photo_url"]), 404)
    assert expect(citizen.get(f"/api/reports/{report['id']}/audio"), 200).content == audio
    deadline = time.monotonic() + 16
    while time.monotonic() < deadline:
        queue = expect(web.get("/api/admin/queue"), 200).json()
        if queue["counts"]["RETRY_SCHEDULED"]:
            break
        time.sleep(0.4)
    else:
        raise AssertionError("El worker no reprogramó el diagnóstico durante la simulación.")
    own = expect(citizen.get(f"/api/reports/by-code/{report['tracking_code']}"), 200).json()
    assert own["id"] == report["id"] and own["status"] == "PENDING_ANALYSIS"
    return report


def _manage_report(cases: httpx.Client, citizen: httpx.Client, report: dict) -> None:
    report_id = report["id"]
    expect(cases.get("/api/reports?limit=2"), 200)
    notices = expect(cases.get("/api/admin/notifications"), 200).json()["items"]
    notice = next(item for item in notices if item["report_id"] == report_id)
    expect(cases.patch(f"/api/admin/notifications/{notice['id']}/read"), 200)
    notes_path = f"/api/admin/reports/{report_id}/internal-notes"
    changes = {"assigned_to": "Equipo sintético", "public_note": "Recibimos el caso de prueba.",
               "internal_note": "Nota reservada de prueba."}
    expect(cases.post(f"/api/admin/reports/{report_id}/management", json=changes), 200)
    notes = expect(cases.get(notes_path), 200).json()["items"]
    assert notes[0]["note"] == changes["internal_note"]
    expect(citizen.get(notes_path), 403)
    expect(cases.patch(f"/api/reports/{report_id}/status",
                       json={"status": "IN_REVIEW", "human_approved": True}), 200)
    updated = expect(citizen.get(f"/api/reports/{report_id}"), 200).json()
    assert updated["status"] == "IN_REVIEW"
    assert changes["public_note"] in json.dumps(updated, ensure_ascii=False)
    assert changes["internal_note"] not in json.dumps(updated, ensure_ascii=False)
    result = expect(citizen.post("/api/agent/query",
                                 json={"query": f"Estado del reporte {report['tracking_code']}"}), 200).json()
    assert report["tracking_code"] in result["answer"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.credentials_file), ensure_ascii=False))
