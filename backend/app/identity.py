from datetime import datetime
from enum import StrEnum
import hashlib
import hmac
import re
import secrets
from threading import BoundedSemaphore
from typing import Annotated, Any, Literal
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Header, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db import get_conn
from app.security import CitizenValidationError, sanitize_text


class Role(StrEnum):
    CITIZEN = "CITIZEN"
    CASE_ADMIN = "CASE_ADMIN"
    WEB_ADMIN = "WEB_ADMIN"


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(
            r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", value
        ):
            raise ValueError("El correo electrónico no es válido.")
        local, domain = value.split("@", 1)
        if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
            raise ValueError("El correo electrónico no es válido.")
        if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in domain.split(".")):
            raise ValueError("El correo electrónico no es válido.")
        return value


class AccountRegistration(Credentials):
    password: str = Field(min_length=15, max_length=128, repr=False)
    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return sanitize_text(value, field_name="nombre", min_len=2, max_len=120, required=True)


class UserView(BaseModel):
    id: UUID
    name: str
    email: str
    role: Role
    active: bool
    created_at: datetime


class Principal(UserView):
    mode: Literal["cookie", "bearer"]
    expires_at: datetime
    token_hash: bytes = Field(exclude=True, repr=False)
    csrf_token: str | None = Field(exclude=True, repr=False)


COOKIE_NAME = "civia_session"
SESSION_SECONDS = 8 * 60 * 60
RATE_WINDOW_SECONDS = 5 * 60
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
_HASH_SLOTS = BoundedSemaphore(4)
_DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_PUBLIC_USER_COLUMNS = "id, name, email, role, active, created_at"


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def csrf_token(token: str) -> str:
    return hmac.new(token.encode("ascii"), b"civia csrf v1", "sha256").hexdigest()


def _busy() -> CitizenValidationError:
    return CitizenValidationError(
        "Demasiadas solicitudes. Intenta nuevamente en unos minutos.",
        status_code=429,
        code="AUTH_RATE_LIMITED",
    )


def hash_password(value: str) -> str:
    if not _HASH_SLOTS.acquire(blocking=False):
        raise _busy()
    try:
        return PASSWORD_HASHER.hash(value)
    finally:
        _HASH_SLOTS.release()


def verify_password(encoded: str, supplied: str) -> bool:
    if not _HASH_SLOTS.acquire(blocking=False):
        raise _busy()
    try:
        return PASSWORD_HASHER.verify(encoded, supplied)
    except (InvalidHashError, VerificationError):
        return False
    finally:
        _HASH_SLOTS.release()


def check_auth_rate_limit(*buckets: tuple[str, int]) -> None:
    with get_conn(3000) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM auth_rate_limits WHERE bucket IN (
                    SELECT bucket FROM auth_rate_limits WHERE expires_at <= NOW()
                    ORDER BY expires_at LIMIT 50 FOR UPDATE SKIP LOCKED
                );
                """
            )
            if secrets.randbelow(32) == 0:
                cur.execute(
                    """
                    DELETE FROM auth_sessions WHERE token_hash IN (
                        SELECT token_hash FROM auth_sessions WHERE expires_at <= NOW()
                        ORDER BY expires_at LIMIT 50 FOR UPDATE SKIP LOCKED
                    );
                    """
                )
            for key, ceiling in buckets:
                cur.execute(
                    """
                    INSERT INTO auth_rate_limits (bucket, attempts, expires_at)
                    VALUES (%s, 1, NOW() + make_interval(secs => %s))
                    ON CONFLICT (bucket) DO UPDATE SET
                        attempts = CASE
                            WHEN auth_rate_limits.expires_at <= NOW() THEN 1
                            ELSE LEAST(auth_rate_limits.attempts + 1, %s)
                        END,
                        expires_at = CASE
                            WHEN auth_rate_limits.expires_at <= NOW() THEN EXCLUDED.expires_at
                            ELSE auth_rate_limits.expires_at
                        END
                    RETURNING attempts;
                    """,
                    (digest(key), RATE_WINDOW_SECONDS, ceiling + 1),
                )
                if cur.fetchone()["attempts"] > ceiling:
                    conn.commit()
                    raise _busy()
        conn.commit()


def unauthorized(message: str = "Inicia sesión para continuar.") -> CitizenValidationError:
    return CitizenValidationError(message, status_code=401, code="UNAUTHORIZED")


def forbidden() -> CitizenValidationError:
    return CitizenValidationError(
        "Tu cuenta no tiene acceso a esta operación.", status_code=403, code="FORBIDDEN"
    )


_session_cookie = APIKeyCookie(name=COOKIE_NAME, scheme_name="CiviaWebSession", auto_error=False)
_native_bearer = HTTPBearer(scheme_name="CiviaCitizenBearer", auto_error=False)


def get_session(
    request: Request,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_native_bearer)] = None,
    cookie: Annotated[str | None, Security(_session_cookie)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Principal:
    if "authorization" in request.headers:
        if bearer is None:
            raise unauthorized()
        token = bearer.credentials
        mode = "bearer"
    else:
        mode = "cookie"
        token = cookie or ""
    if not _TOKEN_PATTERN.fullmatch(token):
        raise unauthorized()

    token_hash = digest(token)
    with get_conn(3000) as conn:
        row = conn.execute(
            """
            SELECT u.id, u.name, u.email, u.role, u.active, u.created_at, s.expires_at
            FROM auth_sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.mode = %s AND s.revoked_at IS NULL
                AND s.expires_at > NOW() AND u.active
                AND (s.mode = 'cookie' OR u.role = 'CITIZEN');
            """,
            (token_hash, mode),
        ).fetchone()
    if row is None:
        raise unauthorized()

    csrf = csrf_token(token) if mode == "cookie" else None
    if csrf is not None and request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = csrf_header or ""
        if not re.fullmatch(r"[0-9a-f]{64}", supplied) or not hmac.compare_digest(csrf, supplied):
            raise CitizenValidationError(
                "Vuelve a cargar la página y repite la operación.",
                status_code=403,
                code="CSRF_VALIDATION_FAILED",
            )
    return Principal(**row, mode=mode, csrf_token=csrf, token_hash=token_hash)


CurrentSession = Annotated[Principal, Depends(get_session)]


def require_citizen(principal: CurrentSession) -> Principal:
    if principal.role != Role.CITIZEN:
        raise forbidden()
    return principal


def require_case_admin(principal: CurrentSession) -> Principal:
    if principal.role not in (Role.CASE_ADMIN, Role.WEB_ADMIN):
        raise forbidden()
    return principal


def require_web_admin(principal: CurrentSession) -> Principal:
    if principal.role != Role.WEB_ADMIN:
        raise forbidden()
    return principal


CitizenSession = Annotated[Principal, Depends(require_citizen)]
CaseAdminSession = Annotated[Principal, Depends(require_case_admin)]
WebAdminSession = Annotated[Principal, Depends(require_web_admin)]


def insert_user(cur: Any, account: AccountRegistration, password_hash: str, role: Role) -> dict | None:
    cur.execute(
        f"""
        INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)
        ON CONFLICT (email) DO NOTHING RETURNING {_PUBLIC_USER_COLUMNS};
        """,
        (account.name, account.email, password_hash, role.value),
    )
    return cur.fetchone()


def create_session(cur: Any, user_id: UUID, mode: str, *, password_hash: str) -> tuple[str, datetime] | None:
    token = secrets.token_urlsafe(32)
    cur.execute(
        """
        INSERT INTO auth_sessions (token_hash, user_id, mode, expires_at)
        SELECT %s, id, %s, NOW() + make_interval(secs => %s) FROM users
        WHERE id = %s AND active AND password_hash = %s AND (%s = 'cookie' OR role = 'CITIZEN')
        FOR SHARE
        RETURNING expires_at;
        """,
        (digest(token), mode, SESSION_SECONDS, user_id, password_hash, mode),
    )
    created = cur.fetchone()
    return (token, created["expires_at"]) if created else None


def audit(cur: Any, action: str, actor_id: UUID | None = None, target_id: UUID | None = None) -> None:
    cur.execute(
        "INSERT INTO security_audit (actor_id, action, target_id) VALUES (%s, %s, %s);",
        (actor_id, action, target_id),
    )


def lock_user_administration(cur: Any) -> None:
    cur.execute("SELECT pg_advisory_xact_lock(22677104);")


def verify_web_admin_at_write(cur: Any, principal: Principal) -> None:
    cur.execute(
        """
        SELECT u.id FROM users u JOIN auth_sessions s ON s.user_id = u.id
        WHERE u.id = %s AND u.role = 'WEB_ADMIN' AND u.active
            AND s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > NOW()
        FOR SHARE OF u, s;
        """,
        (principal.id, principal.token_hash),
    )
    if cur.fetchone() is None:
        raise forbidden()
