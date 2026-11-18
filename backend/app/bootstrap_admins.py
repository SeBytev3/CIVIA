import argparse
from getpass import getpass
from hmac import compare_digest
import json
import os
from pathlib import Path
import secrets
import sys
from tempfile import NamedTemporaryFile
from uuid import UUID

import psycopg
from pydantic import ValidationError

from app.db import get_conn
from app.identity import AccountRegistration, Role, audit, hash_password, insert_user, lock_user_administration
from app.security import CitizenValidationError


def _insert_admin(cur, role: Role, account: AccountRegistration, password_hash: str) -> None:
    user = insert_user(cur, account, password_hash, role)
    if user is None:
        raise ValueError("Uno de los correos indicados ya está en uso.")
    audit(cur, "users.bootstrap", target_id=user["id"])


def bootstrap_admin_accounts(web: AccountRegistration, cases: AccountRegistration) -> bool:
    if web.email == cases.email:
        raise ValueError("Usa un correo distinto para cada cuenta.")
    accounts = (
        (Role.WEB_ADMIN, web, hash_password(web.password)),
        (Role.CASE_ADMIN, cases, hash_password(cases.password)),
    )
    with get_conn(5000) as conn, conn.cursor() as cur:
        lock_user_administration(cur)
        cur.execute("SELECT 1 FROM users WHERE role = 'WEB_ADMIN' LIMIT 1;")
        if cur.fetchone():
            return False
        for role, account, encoded in accounts:
            _insert_admin(cur, role, account, encoded)
        conn.commit()
    return True


def _save_private_accounts(path: Path, data: dict) -> None:
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
            temporary_path = Path(output.name)
            os.chmod(temporary_path, 0o600)
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _private_accounts(path: Path, installation_id: UUID) -> dict[str, dict[str, str]]:
    if path.is_symlink():
        raise ValueError("El archivo de acceso debe ser un archivo local privado.")
    if path.exists():
        with path.open(encoding="utf-8") as source:
            data = json.loads(source.read(8192))
        if data["installation_id"] != str(installation_id):
            raise ValueError("El archivo de recuperación pertenece a otra instalación.")
        return data["accounts"]

    accounts = {
        role.value: {
            "email": f"{alias}-{secrets.token_hex(5)}@civia.local",
            "password": secrets.token_urlsafe(32),
        }
        for role, alias in ((Role.WEB_ADMIN, "web"), (Role.CASE_ADMIN, "casos"))
    }
    _save_private_accounts(path, {"installation_id": str(installation_id), "accounts": accounts})
    return accounts


def bootstrap_automatic(credentials_file: Path) -> bool:
    with get_conn(5000) as conn, conn.cursor() as cur:
        lock_user_administration(cur)
        cur.execute("SELECT 1 FROM users WHERE role = 'WEB_ADMIN' LIMIT 1")
        if cur.fetchone():
            return False
        cur.execute("SELECT installation_id FROM installation_metadata WHERE singleton")
        installation = cur.fetchone()
        if installation is None:
            raise ValueError("Falta la identidad de la instalación.")
        accounts = _private_accounts(credentials_file, installation["installation_id"])
        cur.execute("SELECT 1 FROM users WHERE role = 'CASE_ADMIN' LIMIT 1")
        existing_case_admin = cur.fetchone() is not None
        for role, name in (
            (Role.WEB_ADMIN, "Administración web"),
            (Role.CASE_ADMIN, "Administración de casos"),
        ):
            if role == Role.CASE_ADMIN and existing_case_admin:
                continue
            account = AccountRegistration(name=name, **accounts[role.value])
            _insert_admin(cur, role, account, hash_password(account.password))
        conn.commit()
    return True


def _read_password(profile: str) -> str:
    password = getpass(f"Contraseña de {profile} (mínimo 15 caracteres): ")
    confirmation = getpass("Confirma la contraseña: ")
    if not compare_digest(password.encode(), confirmation.encode()):
        raise ValueError("Las contraseñas no coinciden.")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Crear las dos primeras cuentas administrativas de CIVIA.")
    parser.add_argument("--web-email")
    parser.add_argument("--case-email")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--automatic", action="store_true")
    parser.add_argument("--credentials-file", type=Path)
    args = parser.parse_args()
    if args.status:
        with get_conn(3000) as conn:
            rows = conn.execute(
                "SELECT DISTINCT role FROM users WHERE active AND role IN ('CASE_ADMIN', 'WEB_ADMIN');"
            ).fetchall()
        available = {row["role"] for row in rows}
        for role in (Role.WEB_ADMIN, Role.CASE_ADMIN):
            print(f"{role}: {'ACTIVA' if role in available else 'PENDIENTE'}")
        return 0 if {Role.WEB_ADMIN, Role.CASE_ADMIN} <= available else 1
    if args.automatic:
        if args.credentials_file is None:
            parser.error("--automatic requiere --credentials-file")
        try:
            created = bootstrap_automatic(args.credentials_file)
        except (ValidationError, CitizenValidationError, OSError, ValueError, TypeError, KeyError, psycopg.Error):
            print("El acceso inicial no pudo prepararse. Revisa la base y el archivo privado de esta instalación.")
            return 1
        print("Acceso inicial preparado en el archivo privado." if created else "La administración ya está inicializada.")
        return 0
    if not sys.stdin.isatty():
        print("Ejecuta el comando desde una terminal interactiva para introducir las contraseñas de forma privada.")
        return 1
    try:
        web = AccountRegistration(
            name="Administración web",
            email=args.web_email or input("Correo de administración web: "),
            password=_read_password("administración web"),
        )
        cases = AccountRegistration(
            name="Administración de casos",
            email=args.case_email or input("Correo de administración de casos: "),
            password=_read_password("administración de casos"),
        )
        if not bootstrap_admin_accounts(web, cases):
            print("La administración web ya se inicializó.")
            return 1
    except (ValidationError, CitizenValidationError, ValueError):
        print("Revisa que los correos sean válidos y distintos y que ambas contraseñas cumplan la longitud mínima.")
        return 1
    print("Se crearon las cuentas iniciales WEB_ADMIN y CASE_ADMIN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
