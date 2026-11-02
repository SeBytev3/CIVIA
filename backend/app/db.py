from contextlib import contextmanager
import logging
from pathlib import Path
import re
from typing import Any, Generator
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.config import settings

logger = logging.getLogger("civia.db")

_SAFE_DB_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def get_database_name(db_url: str | None = None) -> str:
    url = db_url or settings.DATABASE_URL
    parsed = urlparse(url)
    return (parsed.path or "").lstrip("/") or "civia"


def is_disposable_test_or_eval_db(db_url: str | None = None) -> bool:
    db_name = get_database_name(db_url).lower()
    return (
        db_name.endswith("_test")
        or db_name.endswith("_eval")
        or db_name.startswith("test_")
        or db_name.startswith("eval_")
        or "_test_" in db_name
        or "_eval_" in db_name
    )


def assert_disposable_test_db(db_url: str | None = None) -> None:
    db_name = get_database_name(db_url)
    if not is_disposable_test_or_eval_db(db_url):
        raise RuntimeError(
            f"Operación destructiva rechazada sobre la base de datos '{db_name}'. "
            "Las pruebas destructivas o resets globales solo se permiten en bases aisladas (*_test / *_eval)."
        )


def replace_database_in_url(db_url: str, new_db_name: str) -> str:
    if not _SAFE_DB_NAME_RE.match(new_db_name):
        raise ValueError(f"Nombre de base de datos inválido: {new_db_name}")
    parsed = urlparse(db_url)
    return urlunparse(parsed._replace(path=f"/{new_db_name}"))


def ensure_isolated_database(target_db_name: str = "civia_test", base_url: str | None = None) -> str:
    if not _SAFE_DB_NAME_RE.match(target_db_name):
        raise ValueError(f"Nombre de base de datos inválido: {target_db_name}")
    src_url = base_url or settings.DATABASE_URL
    target_url = replace_database_in_url(src_url, target_db_name)
    admin_url = replace_database_in_url(src_url, "postgres")
    try:
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (target_db_name,))
                if cur.fetchone() is None:
                    cur.execute(
                        sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db_name))
                    )
    except Exception:
        # Fallback conectando a la BD origen si el usuario no tiene acceso a 'postgres'
        with psycopg.connect(src_url, autocommit=True, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (target_db_name,))
                if cur.fetchone() is None:
                    cur.execute(
                        sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db_name))
                    )
    return target_url


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
