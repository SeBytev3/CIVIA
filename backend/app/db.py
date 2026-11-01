from contextlib import contextmanager
import logging
from pathlib import Path
from typing import Any, Generator

import psycopg
from psycopg.rows import dict_row

from app.config import settings

logger = logging.getLogger("civia.db")


@contextmanager
def get_conn() -> Generator[psycopg.Connection[ dict[str, Any]], None, None]:
    conn = psycopg.connect(settings.DATABASE_URL, row_factory=dict_row, connect_timeout=5)
    try:
        yield conn
    finally:
        conn.close()


def run_migrations(migrations_dir: Path | None = None) -> list[str]:
    """Ejecuta migraciones SQL en orden alfabético de forma idempotente."""
    mdir = migrations_dir or settings.MIGRATIONS_DIR
    if not mdir.exists():
        logger.warning("Directorio de migraciones no encontrado: %s", mdir)
        return []

    applied: list[str] = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(64) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            conn.commit()

            cur.execute("SELECT version FROM schema_migrations;")
            existing = {row["version"] for row in cur.fetchall()}

            sql_files = sorted(mdir.glob("*.sql"))
            for sql_file in sql_files:
                version = sql_file.name
                sql_text = sql_file.read_text(encoding="utf-8")
                # Ejecutamos el DDL idempotente (CREATE TABLE/INDEX IF NOT EXISTS)
                cur.execute(sql_text)
                if version not in existing:
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING;",
                        (version,),
                    )
                    applied.append(version)
            conn.commit()
    return applied


def check_db_health() -> dict[str, Any]:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok;")
                row = cur.fetchone()
                cur.execute(
                    "SELECT COUNT(*) AS count FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'reports';"
                )
                tbl = cur.fetchone()
                has_reports = bool(tbl and tbl["count"] > 0)
                return {
                    "connected": bool(row and row["ok"] == 1),
                    "schema_ready": has_reports,
                }
    except Exception as exc:
        logger.error("Error de salud de BD: %s", type(exc).__name__)
        return {"connected": False, "schema_ready": False}
