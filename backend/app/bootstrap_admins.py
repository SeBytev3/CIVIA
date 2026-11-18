import argparse
from getpass import getpass
from hmac import compare_digest
import sys

from pydantic import ValidationError

from app.db import get_conn
from app.identity import AccountRegistration, Role, audit, hash_password, insert_user, lock_user_administration
from app.security import CitizenValidationError


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
            user = insert_user(cur, account, encoded, role)
            if user is None:
                raise ValueError("Uno de los correos indicados ya está en uso.")
            audit(cur, "users.bootstrap", target_id=user["id"])
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
