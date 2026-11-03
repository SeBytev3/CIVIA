import os
from pathlib import Path
import shutil
import tempfile
from uuid import UUID
import uuid

import pytest

from app.agent import set_approval_created_hook
from app.config import generate_admin_token, is_strong_admin_token, settings
from app.db import (
    assert_disposable_test_db,
    ensure_isolated_database,
    get_conn,
    is_disposable_test_or_eval_db,
    run_migrations,
)
from app.repository import set_report_created_hook
from app.seed import seed_synthetic_reports

TEST_ADMIN_TOKEN = generate_admin_token()

if not is_strong_admin_token(settings.ADMIN_TOKEN):
    settings.ADMIN_TOKEN = TEST_ADMIN_TOKEN
    os.environ["ADMIN_TOKEN"] = TEST_ADMIN_TOKEN

# Aislar de forma estricta (fail-closed) cualquier base de datos que no sea explícitamente desechable (*_test / test_*)
if not is_disposable_test_or_eval_db(settings.DATABASE_URL):
    if os.getenv("CIVIA_STRICT_REJECT_NON_TEST_DB") == "1":
        assert_disposable_test_db(settings.DATABASE_URL)
    _ephemeral_db_name = f"civia_test_{uuid.uuid4().hex[:8]}"
    isolated_url = ensure_isolated_database(_ephemeral_db_name, settings.DATABASE_URL)
    settings.DATABASE_URL = isolated_url
    os.environ["DATABASE_URL"] = isolated_url

assert_disposable_test_db(settings.DATABASE_URL)

_test_upload_dir = Path(tempfile.gettempdir()) / f"civia_test_uploads_{uuid.uuid4().hex[:8]}"
_test_upload_dir.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR = _test_upload_dir
os.environ["UPLOAD_DIR"] = str(_test_upload_dir)

_TRACKED_REPORT_IDS: set[UUID] = set()
_TRACKED_APPROVAL_IDS: set[UUID] = set()


def register_test_report_id(report_id: UUID | str) -> None:
    _TRACKED_REPORT_IDS.add(UUID(str(report_id)))


def register_test_approval_id(approval_id: UUID | str) -> None:
    _TRACKED_APPROVAL_IDS.add(UUID(str(approval_id)))


set_report_created_hook(register_test_report_id)
set_approval_created_hook(register_test_approval_id)


def cleanup_tracked_test_records() -> None:
    """
    Limpia exclusivamente los registros cuyos UUID fueron generados por las operaciones
    de la prueba en curso. Jamás usa DELETE por complemento (NOT IN / NOT ANY) ni
    sobreescribe el estado de reportes preexistentes o concurrentes.
    """
    approval_ids = list(_TRACKED_APPROVAL_IDS)
    report_ids = list(_TRACKED_REPORT_IDS)
    _TRACKED_APPROVAL_IDS.clear()
    _TRACKED_REPORT_IDS.clear()

    if not approval_ids and not report_ids:
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            if approval_ids:
                cur.execute(
                    "DELETE FROM pending_approvals WHERE id = ANY(%s);",
                    (approval_ids,),
                )
            if report_ids:
                cur.execute(
                    "DELETE FROM reports WHERE id = ANY(%s) AND is_synthetic = FALSE;",
                    (report_ids,),
                )
            conn.commit()


@pytest.fixture(scope="session", autouse=True)
def initialize_isolated_test_db():
    assert_disposable_test_db(settings.DATABASE_URL)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    run_migrations()
    seed_synthetic_reports(force_reset=False)
    yield
    cleanup_tracked_test_records()
    shutil.rmtree(_test_upload_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def guard_no_external_network_calls(monkeypatch, request):
    """
    Bloquea incondicionalmente cualquier conexión HTTP hacia proveedores externos
    (Google Gemini / Groq) en toda la suite ordinaria de pruebas (G2.1.3).
    """
    if "live" in request.keywords:
        yield
        return

    import httpx
    orig_send = httpx.Client.send

    def guarded_send(self, req, *args, **kwargs):
        host = getattr(req.url, "host", "")
        if host in ("generativelanguage.googleapis.com", "api.groq.com"):
            raise RuntimeError(f"Intento de llamada HTTP externa no permitida hacia {host} en prueba hermética.")
        return orig_send(self, req, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", guarded_send)
    yield
