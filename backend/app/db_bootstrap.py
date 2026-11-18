"""Ejecuta migraciones con credenciales separadas de los procesos en ejecución."""

import logging
import os

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from app.db import run_migrations

logger = logging.getLogger("civia.db_bootstrap")
_SERVICE_LOGINS = {
    "DATABASE_URL": "civia_app",
    "AGENT_DATABASE_URL": "civia_agent",
    "WORKER_DATABASE_URL": "civia_worker",
}


def provision_database_roles(migration_dsn: str) -> None:
    owner = conninfo_to_dict(migration_dsn)
    services = {}
    passwords = {owner.get("password")}
    for env_name, role in _SERVICE_LOGINS.items():
        config = conninfo_to_dict(os.environ[env_name])
        if (
            config.get("user") != role
            or not config.get("password")
            or config["password"] in passwords
            or owner.get("user") == role
            or any(config.get(key) != owner.get(key) for key in ("host", "port", "dbname"))
        ):
            raise ValueError(f"Configuración de conexión inválida: {env_name}")
        passwords.add(config["password"])
        services[role] = config["password"]

    with psycopg.connect(migration_dsn, connect_timeout=5) as conn:
        for role, password in services.items():
            if conn.execute(
                """
                SELECT 1 FROM pg_roles r JOIN pg_auth_members m ON r.oid = m.member
                WHERE r.rolname = %s
                """,
                (role,),
            ).fetchone():
                raise ValueError(f"El rol {role} tiene membresías inesperadas.")
            credential = conn.pgconn.encrypt_password(password.encode(), role.encode(), b"scram-sha-256")
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                conn.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
            conn.execute(
                sql.SQL(
                    "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(credential.decode())),
            )


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        migration_dsn = os.environ["MIGRATION_DATABASE_URL"]
        provision_database_roles(migration_dsn)
        versions = run_migrations(database_url=migration_dsn)
    except (KeyError, ValueError, psycopg.Error) as exc:
        logger.error("La preparación de PostgreSQL falló (%s).", type(exc).__name__)
        return 1
    logger.info("Preparación de PostgreSQL terminada. Migraciones nuevas: %s.", len(versions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
