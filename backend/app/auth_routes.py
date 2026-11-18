from datetime import datetime
import os
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db import get_conn
from app.identity import (
    COOKIE_NAME,
    SESSION_SECONDS,
    _DUMMY_HASH,
    _PUBLIC_USER_COLUMNS,
    AccountRegistration,
    Credentials,
    CurrentSession,
    Role,
    UserView,
    WebAdminSession,
    audit,
    check_auth_rate_limit,
    create_session,
    csrf_token,
    forbidden,
    hash_password,
    insert_user,
    lock_user_administration,
    unauthorized,
    verify_password,
    verify_web_admin_at_write,
)
from app.security import CitizenValidationError, get_trusted_client_ip

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,https://localhost,http://localhost"
ALLOWED_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip() and origin.strip() != "*"
)
_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "").lower() in ("1", "true", "yes")

auth_router = APIRouter(prefix="/api/auth", tags=["Autenticación"])
users_router = APIRouter(prefix="/api/admin", tags=["Identidad y auditoría"])
SessionMode = Annotated[Literal["cookie", "bearer"], Header(alias="X-Session-Mode")]


class SessionResponse(BaseModel):
    user: UserView
    expires_at: datetime
    csrf_token: str | None = None
    token: str | None = None


class ManagedAccount(AccountRegistration):
    role: Role


class UserChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def require_a_change(self) -> "UserChanges":
        if self.role is None and self.active is None:
            raise ValueError("Especifica el rol o el estado de la cuenta.")
        return self


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    password: str = Field(min_length=15, max_length=128, repr=False)


class UserPage(BaseModel):
    items: list[UserView]
    total: int
    limit: int
    offset: int


class AuditEntry(BaseModel):
    id: int
    actor_id: UUID | None
    action: str
    target_id: UUID | None
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    limit: int
    offset: int


def _require_trusted_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    effective_origin = f"{request.url.scheme}://{request.url.netloc}"
    if origin and origin not in ALLOWED_ORIGINS and origin != effective_origin:
        raise forbidden()


def _secure_cookie(request: Request) -> bool:
    return _COOKIE_SECURE or request.url.scheme == "https"


def _send_session(
    request: Request,
    response: Response,
    user: dict,
    session: tuple[str, datetime],
    mode: str,
) -> SessionResponse:
    token, expires_at = session
    if mode == "cookie":
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=_secure_cookie(request),
            samesite="lax",
        )
    return SessionResponse(
        user=UserView.model_validate(user),
        expires_at=expires_at,
        csrf_token=csrf_token(token) if mode == "cookie" else None,
        token=token if mode == "bearer" else None,
    )


def duplicate_account() -> CitizenValidationError:
    return CitizenValidationError(
        "No se pudo registrar la cuenta con los datos indicados.",
        status_code=409,
        code="ACCOUNT_REGISTRATION_FAILED",
    )


@auth_router.post("/register", response_model=SessionResponse, response_model_exclude_none=True, status_code=201)
def register(
    account: AccountRegistration, request: Request, response: Response, mode: SessionMode = "cookie"
) -> SessionResponse:
    _require_trusted_origin(request)
    check_auth_rate_limit((f"register:ip:{get_trusted_client_ip(request)}", 20))
    encoded = hash_password(account.password)
    with get_conn(3000) as conn, conn.cursor() as cur:
        user = insert_user(cur, account, encoded, Role.CITIZEN)
        if user is None:
            raise duplicate_account()
        session = create_session(cur, user["id"], mode, password_hash=encoded)
        if session is None:
            raise unauthorized()
        audit(cur, "auth.register", user["id"], user["id"])
        conn.commit()
    return _send_session(request, response, user, session, mode)


@auth_router.post("/login", response_model=SessionResponse, response_model_exclude_none=True)
def login(
    credentials: Credentials, request: Request, response: Response, mode: SessionMode = "cookie"
) -> SessionResponse:
    _require_trusted_origin(request)
    check_auth_rate_limit(
        (f"login:ip:{get_trusted_client_ip(request)}", 40), (f"login:email:{credentials.email}", 6)
    )
    with get_conn(3000) as conn:
        user = conn.execute(
            f"SELECT {_PUBLIC_USER_COLUMNS}, password_hash FROM users WHERE email = %s;",
            (credentials.email,),
        ).fetchone()
    encoded = user["password_hash"] if user else _DUMMY_HASH
    valid_password = verify_password(encoded, credentials.password)
    if not valid_password or user is None or not user["active"]:
        raise unauthorized("Correo o contraseña incorrectos.")
    if mode == "bearer" and user["role"] != Role.CITIZEN:
        raise forbidden()
    with get_conn(3000) as conn, conn.cursor() as cur:
        session = create_session(cur, user["id"], mode, password_hash=encoded)
        if session is None:
            raise unauthorized("Correo o contraseña incorrectos.")
        audit(cur, "auth.login", user["id"], user["id"])
        conn.commit()
    return _send_session(request, response, user, session, mode)


@auth_router.get("/session", response_model=SessionResponse, response_model_exclude_none=True)
def session_details(principal: CurrentSession) -> SessionResponse:
    return SessionResponse(
        user=UserView.model_validate(principal.model_dump()),
        expires_at=principal.expires_at,
        csrf_token=principal.csrf_token,
    )


@auth_router.post("/logout", status_code=204)
def logout(principal: CurrentSession, request: Request, response: Response) -> None:
    with get_conn(3000) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE auth_sessions SET revoked_at = NOW() WHERE token_hash = %s AND revoked_at IS NULL;",
            (principal.token_hash,),
        )
        if cur.rowcount:
            audit(cur, "auth.logout", principal.id, principal.id)
        conn.commit()
    if principal.mode == "cookie":
        response.delete_cookie(
            COOKIE_NAME, httponly=True, secure=_secure_cookie(request), samesite="lax"
        )


@users_router.get("/users", response_model=UserPage)
def users_index(
    principal: WebAdminSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
) -> UserPage:
    with get_conn(3000) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM users;")
        total = cur.fetchone()["total"]
        cur.execute(
            f"SELECT {_PUBLIC_USER_COLUMNS} FROM users ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s;",
            (limit, offset),
        )
        return UserPage(items=cur.fetchall(), total=total, limit=limit, offset=offset)


@users_router.post("/users", response_model=UserView, status_code=201)
def create_user(account: ManagedAccount, principal: WebAdminSession) -> UserView:
    encoded = hash_password(account.password)
    with get_conn(3000) as conn, conn.cursor() as cur:
        lock_user_administration(cur)
        verify_web_admin_at_write(cur, principal)
        user = insert_user(cur, account, encoded, account.role)
        if user is None:
            raise duplicate_account()
        audit(cur, "users.create", principal.id, user["id"])
        conn.commit()
        return UserView.model_validate(user)


def _user_not_found() -> CitizenValidationError:
    return CitizenValidationError("La cuenta no existe.", status_code=404, code="USER_NOT_FOUND")


def _revoke_user_sessions(cur, user_id: UUID) -> None:
    cur.execute(
        "UPDATE auth_sessions SET revoked_at = NOW() WHERE user_id = %s AND revoked_at IS NULL;",
        (user_id,),
    )


@users_router.patch("/users/{user_id}", response_model=UserView)
def update_user(user_id: UUID, changes: UserChanges, principal: WebAdminSession) -> UserView:
    with get_conn(3000) as conn, conn.cursor() as cur:
        lock_user_administration(cur)
        verify_web_admin_at_write(cur, principal)
        cur.execute(f"SELECT {_PUBLIC_USER_COLUMNS} FROM users WHERE id = %s FOR UPDATE;", (user_id,))
        user = cur.fetchone()
        if user is None:
            raise _user_not_found()
        role = changes.role if changes.role is not None else user["role"]
        active = changes.active if changes.active is not None else user["active"]
        if role == user["role"] and active == user["active"]:
            return UserView.model_validate(user)
        if user["active"] and user["role"] == Role.WEB_ADMIN and (not active or role != Role.WEB_ADMIN):
            cur.execute(
                "SELECT 1 FROM users WHERE active AND role = 'WEB_ADMIN' AND id <> %s LIMIT 1;",
                (user_id,),
            )
            if cur.fetchone() is None:
                raise CitizenValidationError(
                    "Debe mantenerse al menos un administrador web activo.",
                    status_code=409,
                    code="LAST_ACTIVE_WEB_ADMIN",
                )
        cur.execute(
            f"""
            UPDATE users SET role = %s, active = %s, updated_at = NOW() WHERE id = %s
            RETURNING {_PUBLIC_USER_COLUMNS};
            """,
            (role, active, user_id),
        )
        updated = cur.fetchone()
        _revoke_user_sessions(cur, user_id)
        audit(cur, "users.change_access", principal.id, user_id)
        conn.commit()
        return UserView.model_validate(updated)


@users_router.post("/users/{user_id}/reset-password", status_code=204)
def reset_user_password(user_id: UUID, payload: PasswordReset, principal: WebAdminSession) -> None:
    encoded = hash_password(payload.password)
    with get_conn(3000) as conn, conn.cursor() as cur:
        lock_user_administration(cur)
        verify_web_admin_at_write(cur, principal)
        cur.execute("UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s;", (encoded, user_id))
        if not cur.rowcount:
            raise _user_not_found()
        _revoke_user_sessions(cur, user_id)
        audit(cur, "users.reset_password", principal.id, user_id)
        conn.commit()


@users_router.get("/audit", response_model=AuditPage)
def audit_index(
    principal: WebAdminSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
) -> AuditPage:
    with get_conn(3000) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM security_audit;")
        total = cur.fetchone()["total"]
        cur.execute(
            """
            SELECT id, actor_id, action, target_id, created_at
            FROM security_audit ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s;
            """,
            (limit, offset),
        )
        return AuditPage(items=cur.fetchall(), total=total, limit=limit, offset=offset)
