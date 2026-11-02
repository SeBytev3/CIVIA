import os
from pathlib import Path
import tempfile
from uuid import UUID

import pytest

from app.config import is_strong_admin_token, settings
from app.db import ensure_isolated_database, get_conn, get_database_name, run_migrations
from app.seed import seed_synthetic_reports

TEST_ADMIN_TOKEN = "civia_test_admin_secret_token_9876543210_strong"

# Aislar automáticamente la base de datos y directorio de subidas para la suite de pruebas (M-07 / N-03)
if not is_strong_admin_token(settings.ADMIN_TOKEN):
    settings.ADMIN_TOKEN = TEST_ADMIN_TOKEN
    os.environ["ADMIN_TOKEN"] = TEST_ADMIN_TOKEN

if get_database_name(settings.DATABASE_URL) == "civia" and os.getenv("CIVIA_ALLOW_MAIN_DB_TESTS") != "1":
    try:
        isolated_url = ensure_isolated_database("civia_test", settings.DATABASE_URL)
        settings.DATABASE_URL = isolated_url
        os.environ["DATABASE_URL"] = isolated_url
    except Exception:
        pass

_test_upload_dir = Path(tempfile.gettempdir()) / "civia_test_uploads"
_test_upload_dir.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR = _test_upload_dir
os.environ["UPLOAD_DIR"] = str(_test_upload_dir)


def snapshot_db_state() -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM reports;")
            report_ids = [r["id"] for r in cur.fetchall()]
            cur.execute("SELECT id FROM pending_approvals;")
            pa_ids = [r["id"] for r in cur.fetchall()]
            cur.execute(
                "SELECT status, human_override_note, version FROM reports WHERE tracking_code = 'CIV-2026-DEMO0001';"
            )
            demo1 = cur.fetchone()
            return {
                "report_ids": report_ids,
                "pa_ids": pa_ids,
                "demo1": dict(demo1) if demo1 else None,
            }


def restore_db_snapshot(snap: dict) -> None:
    report_ids: list[UUID] = snap.get("report_ids") or []
    pa_ids: list[UUID] = snap.get("pa_ids") or []
    demo1: dict | None = snap.get("demo1")
    with get_conn() as conn:
        with conn.cursor() as cur:
            if pa_ids:
                cur.execute("DELETE FROM pending_approvals WHERE NOT (id = ANY(%s));", (pa_ids,))
            else:
                cur.execute("DELETE FROM pending_approvals;")

            if report_ids:
                cur.execute(
                    "DELETE FROM reports WHERE is_synthetic = FALSE AND NOT (id = ANY(%s));",
                    (report_ids,),
                )
            else:
                cur.execute("DELETE FROM reports WHERE is_synthetic = FALSE;")

            if demo1 is not None:
                cur.execute(
                    """
                    UPDATE reports
                    SET status = %s,
                        human_override_note = %s,
                        version = %s
                    WHERE tracking_code = 'CIV-2026-DEMO0001';
                    """,
                    (demo1["status"], demo1.get("human_override_note"), demo1.get("version") or 1),
                )
            conn.commit()


@pytest.fixture(scope="session", autouse=True)
def initialize_isolated_test_db():
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    run_migrations()
    seed_synthetic_reports(force_reset=False)
    yield
