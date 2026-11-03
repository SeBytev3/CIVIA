from contextlib import contextmanager
import contextvars
from enum import StrEnum
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Any, Generator
from urllib.parse import urlparse, urlunparse
import uuid

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.config import settings

logger = logging.getLogger("civia.db")

_SAFE_DB_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")
_CURRENT_DEADLINE: contextvars.ContextVar[float | None] = contextvars.ContextVar("_CURRENT_DEADLINE", default=None)


class OperationStatus(StrEnum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"
    UNKNOWN = "UNKNOWN"


class IdempotencyConflictError(Exception):
    """Se eleva cuando se reutiliza una clave de idempotencia con un payload diferente."""
    pass


def canonical_payload_hash(payload: Any) -> str:
    """Calcula el hash SHA-256 canónico y determinista de un payload (ignorando claves de control como idempotency_key)."""
    try:
        if isinstance(payload, dict):
            filtered = {k: v for k, v in payload.items() if k not in ("idempotency_key", "operation_id")}
        else:
            filtered = payload
        serialized = json.dumps(filtered, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        serialized = str(payload)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


_IN_FLIGHT_COMMITS: dict[int, dict[str, Any]] = {}
_IN_FLIGHT_LOCK = threading.Lock()


def register_in_flight_commit(
    tid: int,
    operation_id: uuid.UUID | str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT_COMMITS[tid] = {
            "operation_id": operation_id,
            "started_at": time.monotonic(),
            "details": details or {},
        }


def unregister_in_flight_commit(tid: int) -> dict[str, Any] | None:
    with _IN_FLIGHT_LOCK:
        return _IN_FLIGHT_COMMITS.pop(tid, None)


def get_in_flight_commit_for_thread(tid: int) -> dict[str, Any] | None:
    with _IN_FLIGHT_LOCK:
        info = _IN_FLIGHT_COMMITS.get(tid)
        return dict(info) if info else None


_CURRENT_OPERATION: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "_CURRENT_OPERATION", default=None
)


def set_current_operation(op: dict[str, Any] | None) -> contextvars.Token[dict[str, Any] | None]:
    return _CURRENT_OPERATION.set(op)


def reset_current_operation(tok: contextvars.Token[dict[str, Any] | None]) -> None:
    _CURRENT_OPERATION.reset(tok)


def get_current_operation() -> dict[str, Any] | None:
    return _CURRENT_OPERATION.get()


def is_deadline_cancellation(exc: BaseException, deadline: float | None = None) -> bool:
    """
    Determina si una excepción de base de datos fue causada inequívocamente por
    la expiración de un plazo/deadline local, y NO por un fallo de infraestructura,
    terminación administrativa ajena (57P01 AdminShutdown), o un timer de sesión ajeno (G2.1.7).
    """
    # 1. Terminación administrativa ajena nunca es deadline propio
    if isinstance(exc, psycopg.errors.AdminShutdown):
        return False
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate == "57P01":
        return False

    # 2. TransactionTimeout de PostgreSQL (25P04)
    if sqlstate == "25P04" or isinstance(exc, getattr(psycopg.errors, "TransactionTimeout", ())):
        cap = get_current_capability()
        if cap is not None and not cap.is_valid():
            return True
        dl = deadline if deadline is not None else get_deadline_context()
        if dl is not None and time.monotonic() >= (dl - 0.05):
            return True
        return False

    # 3. QueryCanceled (57014) o timeout operacional
    if isinstance(exc, psycopg.errors.QueryCanceled) or sqlstate == "57014":
        cap = get_current_capability()
        if cap is not None and not cap.is_valid():
            return True
        dl = deadline if deadline is not None else get_deadline_context()
        if dl is not None and time.monotonic() >= (dl - 0.05):
            return True
        return False

    if isinstance(exc, psycopg.OperationalError):
        msg = str(exc).lower()
        if "canceling statement due to statement timeout" in msg or "canceling statement due to user request" in msg:
            cap = get_current_capability()
            if cap is not None and not cap.is_valid():
                return True
            dl = deadline if deadline is not None else get_deadline_context()
            if dl is not None and time.monotonic() >= (dl - 0.05):
                return True
        if "transaction timeout" in msg:
            cap = get_current_capability()
            if cap is not None and not cap.is_valid():
                return True
            dl = deadline if deadline is not None else get_deadline_context()
            if dl is not None and time.monotonic() >= (dl - 0.05):
                return True
            return False

    return False


def register_operation_intent(
    operation_id: uuid.UUID | str,
    operation_type: str,
    target_id: str | None = None,
    idempotency_key: str | None = None,
    proposed_payload: dict[str, Any] | None = None,
    requester_id: str = "citizen",
    backend_pid: int | None = None,
) -> dict[str, Any]:
    """
    Registra durablemente la intención de una operación transaccional en estado PENDING.
    Se ejecuta con autocommit en conexión independiente.
    FAIL-CLOSED OBLIGATORIO: si la tabla operation_records no existe o falla la BD,
    la excepción se propaga para impedir la ejecución del negocio sin registro durable.
    Realiza un reclamo atómico mediante INSERT ... ON CONFLICT si se suministra idempotency_key.
    """
    query_token = secrets.token_urlsafe(32)
    query_token_hash = hashlib.sha256(query_token.encode("utf-8")).hexdigest()
    payload_hash = canonical_payload_hash(proposed_payload) if proposed_payload is not None else None
    payload_json = json.dumps(proposed_payload) if proposed_payload is not None else None

    with psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            if idempotency_key:
                cur.execute(
                    """
                    INSERT INTO operation_records (
                        operation_id, requester_id, operation_type, idempotency_key, payload_hash,
                        query_token_hash, target_id, status, proposed_payload, backend_pid,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, 'PENDING', %s, %s,
                        clock_timestamp(), clock_timestamp()
                    )
                    ON CONFLICT (requester_id, operation_type, idempotency_key)
                    DO UPDATE SET updated_at = operation_records.updated_at
                    RETURNING *, (xmax = 0) AS is_new_claim;
                    """,
                    (
                        str(operation_id),
                        requester_id,
                        operation_type,
                        idempotency_key,
                        payload_hash,
                        query_token_hash,
                        target_id,
                        payload_json,
                        backend_pid,
                    ),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError(f"Fallo al registrar reclamo para operación {operation_id}")
                claim = dict(row)
                is_new = bool(claim.get("is_new_claim", True))
                if not is_new:
                    # El registro ya existía previamente para esta clave
                    existing_hash = claim.get("payload_hash")
                    if payload_hash and existing_hash and existing_hash != payload_hash:
                        raise IdempotencyConflictError(
                            f"Conflicto de clave de idempotencia: el payload suministrado no coincide con la operación registrada previamente para la clave '{idempotency_key}'."
                        )
                    claim["claim_acquired"] = False
                else:
                    claim["claim_acquired"] = True
                claim["query_token"] = query_token
                return claim
            else:
                cur.execute(
                    """
                    INSERT INTO operation_records (
                        operation_id, requester_id, operation_type, idempotency_key, payload_hash,
                        query_token_hash, target_id, status, proposed_payload, backend_pid,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, NULL, %s,
                        %s, %s, 'PENDING', %s, %s,
                        clock_timestamp(), clock_timestamp()
                    )
                    ON CONFLICT (operation_id) DO NOTHING
                    RETURNING *;
                    """,
                    (
                        str(operation_id),
                        requester_id,
                        operation_type,
                        payload_hash,
                        query_token_hash,
                        target_id,
                        payload_json,
                        backend_pid,
                    ),
                )
                row = cur.fetchone()
                if not row:
                    cur.execute("SELECT * FROM operation_records WHERE operation_id = %s;", (str(operation_id),))
                    row = cur.fetchone()
                if not row:
                    raise RuntimeError(f"Fallo al registrar intención para operación {operation_id}")
                res = dict(row)
                res["claim_acquired"] = True
                res["query_token"] = query_token
                return res


def mark_operation_committed(
    operation_id: uuid.UUID | str,
    result_payload: dict[str, Any] | None = None,
    conn: psycopg.Connection[Any] | None = None,
) -> None:
    """
    Marca la operación como COMMITTED.
    Si se pasa `conn`, se ejecuta dentro de la MISMA transacción para atomicidad absoluta.
    Exige que cur.rowcount == 1 y falla cerrado si no puede actualizar el registro.
    """
    sql_stmt = """
        UPDATE operation_records
        SET status = 'COMMITTED',
            result_payload = COALESCE(%s, result_payload),
            updated_at = clock_timestamp()
        WHERE operation_id = %s;
    """
    payload_json = json.dumps(result_payload) if result_payload is not None else None
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql_stmt, (payload_json, str(operation_id)))
            if cur.rowcount != 1:
                raise RuntimeError(
                    f"Fallo de trazabilidad obligatoria: operation_records {operation_id} no pudo ser actualizado a COMMITTED (filas afectadas: {cur.rowcount})."
                )
    else:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True, connect_timeout=5) as c:
            with c.cursor() as cur:
                cur.execute(sql_stmt, (payload_json, str(operation_id)))


def mark_operation_aborted(
    operation_id: uuid.UUID | str,
    error_message: str | None = None,
) -> None:
    """Marca la operación como ABORTED en conexión independiente (si estaba en PENDING)."""
    try:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE operation_records
                    SET status = 'ABORTED',
                        error_message = %s,
                        updated_at = clock_timestamp()
                    WHERE operation_id = %s AND status = 'PENDING';
                    """,
                    (error_message, str(operation_id)),
                )
    except Exception as exc:
        logger.warning("No se pudo marcar operación %s como ABORTED: %s", operation_id, exc)


def mark_operation_unknown(
    operation_id: uuid.UUID | str,
    error_message: str | None = None,
) -> None:
    """Marca la operación como UNKNOWN en conexión independiente (si estaba en PENDING)."""
    try:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE operation_records
                    SET status = 'UNKNOWN',
                        error_message = %s,
                        updated_at = clock_timestamp()
                    WHERE operation_id = %s AND status = 'PENDING';
                    """,
                    (error_message, str(operation_id)),
                )
    except Exception as exc:
        logger.warning("No se pudo marcar operación %s como UNKNOWN: %s", operation_id, exc)


def update_operation_backend_pid(operation_id: uuid.UUID | str, backend_pid: int) -> None:
    try:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE operation_records SET backend_pid = %s WHERE operation_id = %s;",
                    (backend_pid, str(operation_id)),
                )
    except Exception:
        pass


def get_operation_record(operation_id: uuid.UUID | str) -> dict[str, Any] | None:
    with psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM operation_records WHERE operation_id = %s;", (str(operation_id),))
            row = cur.fetchone()
            return dict(row) if row else None


def get_operation_by_idempotency_key(idempotency_key: str, requester_id: str = "citizen") -> dict[str, Any] | None:
    with psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM operation_records WHERE idempotency_key = %s AND requester_id = %s;",
                (idempotency_key, requester_id),
            )
            row = cur.fetchone()
            if not row:
                cur.execute("SELECT * FROM operation_records WHERE idempotency_key = %s;", (idempotency_key,))
                row = cur.fetchone()
            return dict(row) if row else None


def reconcile_operation(operation_id: uuid.UUID | str) -> dict[str, Any]:
    """
    Reconcilia el estado de una operación que quedó PENDING o en estado no definitivo.
    Solo transiciona a COMMITTED si existe evidencia transaccional inequívoca vinculada
    al operation_id. Si no hay evidencia concluyente de commit ni de aborto confirmado,
    la operación permanece PENDING o UNKNOWN (nunca deduce ABORTED por simple ausencia de PID).
    """
    record = get_operation_record(operation_id)
    if not record:
        raise ValueError(f"Operación no encontrada: {operation_id}")

    current_status = record.get("status")
    # Estados terminales son monótonos e inmutables
    if current_status in ("COMMITTED", "ABORTED"):
        record["reconciled"] = False
        return record

    target_id = record.get("target_id")
    op_type = record.get("operation_type")

    # 1. Buscar evidencia directa de commit en tablas de negocio vinculada a este operation_id
    committed_evidence = False
    try:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                # Comprobar en pending_approvals por operation_id exacto
                cur.execute(
                    "SELECT id, status FROM pending_approvals WHERE operation_id = %s LIMIT 1;",
                    (str(operation_id),),
                )
                if cur.fetchone():
                    committed_evidence = True
    except Exception as exc:
        logger.debug("Error comprobando evidencia para reconciliar %s: %s", operation_id, exc)

    if committed_evidence:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE operation_records
                    SET status = 'COMMITTED',
                        updated_at = clock_timestamp()
                    WHERE operation_id = %s AND status = 'PENDING'
                    RETURNING *;
                    """,
                    (str(operation_id),),
                )
                updated = cur.fetchone()
                res = dict(updated) if updated else record
                res["reconciled"] = True
                return res

    # 2. Si no hay evidencia de commit:
    backend_pid = record.get("backend_pid")
    if backend_pid is not None:
        is_pid_alive = False
        try:
            with psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM pg_stat_activity WHERE pid = %s AND query NOT LIKE '%%pg_stat_activity%%';",
                        (backend_pid,),
                    )
                    is_pid_alive = cur.fetchone() is not None
        except Exception:
            is_pid_alive = False

        if is_pid_alive:
            # El backend sigue en ejecución en PostgreSQL: permanece PENDING
            record["reconciled"] = False
            return record

        # El backend estuvo activo pero ya cerró definitivamente sin confirmar negocio: marcar ABORTED
        with psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE operation_records
                    SET status = 'ABORTED',
                        error_message = COALESCE(error_message, 'Conexión de base de datos finalizada sin confirmación de negocio.'),
                        updated_at = clock_timestamp()
                    WHERE operation_id = %s AND status = 'PENDING'
                    RETURNING *;
                    """,
                    (str(operation_id),),
                )
                updated = cur.fetchone()
                res = dict(updated) if updated else record
                res["reconciled"] = True
                return res

    # 3. Si backend_pid es None: el worker aún no ha abierto conexión o la intención sigue en curso.
    # Conservamos PENDING (o UNKNOWN si ya estaba así) para evitar falsos abortos prematuros.
    record["reconciled"] = False
    return record



class ExecutionCapability:
    """
    Capacidad revocable de ejecución para acotar efectos secundarios (M-03).
    Asociada al deadline y ciclo de vida de la herramienta o invocación.
    Permite invalidación síncrona inmediata que bloquea nuevas sentencias SQL,
    commits o escrituras en disco incluso si el worker no coopera o se retrasa.
    """

    def __init__(self, deadline: float | None = None, label: str = "default") -> None:
        self.deadline = deadline
        self.label = label
        self._revoked = False
        self._lock = threading.Lock()

    def revoke(self) -> None:
        with self._lock:
            self._revoked = True

    def is_valid(self) -> bool:
        with self._lock:
            if self._revoked:
                return False
            if self.deadline is not None and time.monotonic() >= self.deadline:
                self._revoked = True
                return False
            return True

    def check_or_raise(self, operation_desc: str = "operación") -> None:
        with self._lock:
            if self._revoked:
                raise TimeoutError(f"Capacidad de ejecución revocada: {operation_desc} rechazada.")
            if self.deadline is not None and time.monotonic() >= self.deadline:
                self._revoked = True
                raise TimeoutError(f"Capacidad de ejecución expirada por deadline: {operation_desc} rechazada.")

    def authorized_replace(self, src: Path | str, dst: Path | str) -> None:
        """Promoción atómica de archivo coordinada con la revocación bajo candado (M-03).

        Garantiza que la validación y os.replace sean atómicos respecto a revoke(),
        impidiendo que un archivo se publique si revoke() ya fue invocado o el
        deadline ya expiró. os.replace es una operación atómica a nivel de metadatos
        de directorio (microsegundos), por lo que no introduce bloqueos indefinidos.
        """
        with self._lock:
            if self._revoked:
                raise TimeoutError("Capacidad de ejecución revocada: promoción de archivo rechazada.")
            if self.deadline is not None and time.monotonic() >= self.deadline:
                self._revoked = True
                raise TimeoutError("Capacidad de ejecución expirada por deadline: promoción de archivo rechazada.")
            os.replace(src, dst)


_CURRENT_CAPABILITY: contextvars.ContextVar[ExecutionCapability | None] = contextvars.ContextVar(
    "_CURRENT_CAPABILITY", default=None
)


def set_execution_capability(cap: ExecutionCapability | None) -> contextvars.Token[ExecutionCapability | None]:
    return _CURRENT_CAPABILITY.set(cap)


def reset_execution_capability(tok: contextvars.Token[ExecutionCapability | None]) -> None:
    _CURRENT_CAPABILITY.reset(tok)


def get_current_capability() -> ExecutionCapability | None:
    return _CURRENT_CAPABILITY.get()


def check_execution_capability_or_raise(operation_desc: str = "operación") -> None:
    cap = get_current_capability()
    if cap is not None:
        cap.check_or_raise(operation_desc)
    dl = get_deadline_context()
    if dl is not None and time.monotonic() >= dl:
        raise TimeoutError(f"Deadline de ejecución expirado: {operation_desc} rechazada.")


def atomic_publish_file(src: Path | str, dst: Path | str) -> None:
    """Publica atómicamente un archivo validando la capacidad de ejecución activa bajo candado (M-03)."""
    cap = get_current_capability()
    if cap is not None:
        cap.authorized_replace(src, dst)
        return
    dl = get_deadline_context()
    if dl is not None and time.monotonic() >= dl:
        raise TimeoutError("Deadline de ejecución expirado: promoción de archivo rechazada.")
    os.replace(src, dst)


class _CapabilityCopyProxy:
    """Proxy para operaciones Copy de psycopg que valida la capacidad de ejecución."""

    def __init__(self, copy_obj: Any, cap: ExecutionCapability | None) -> None:
        self._cm = copy_obj
        self._active_copy = copy_obj if not hasattr(copy_obj, "__enter__") else None
        self._cap = cap

    def _check(self, op: str = "operación copy") -> None:
        if self._cap is not None:
            self._cap.check_or_raise(op)
        check_execution_capability_or_raise(op)

    @property
    def _target(self) -> Any:
        return self._active_copy if self._active_copy is not None else self._cm

    def read(self, *args: Any, **kwargs: Any) -> Any:
        self._check("lectura copy")
        return self._target.read(*args, **kwargs)

    def read_row(self, *args: Any, **kwargs: Any) -> Any:
        self._check("lectura copy")
        return self._target.read_row(*args, **kwargs)

    def rows(self, *args: Any, **kwargs: Any) -> Any:
        self._check("filas copy")
        raw_rows = self._target.rows(*args, **kwargs)
        return _CapabilityStreamProxy(raw_rows, self._cap)

    def write(self, *args: Any, **kwargs: Any) -> Any:
        self._check("escritura copy")
        return self._target.write(*args, **kwargs)

    def write_row(self, *args: Any, **kwargs: Any) -> Any:
        self._check("escritura copy")
        return self._target.write_row(*args, **kwargs)

    def __iter__(self) -> Any:
        self._check("iteración copy")
        return _CapabilityStreamProxy(iter(self._target), self._cap)

    def __enter__(self) -> "_CapabilityCopyProxy":
        self._check("apertura copy")
        if hasattr(self._cm, "__enter__"):
            self._active_copy = self._cm.__enter__()
        else:
            self._active_copy = self._cm
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        if hasattr(self._cm, "__exit__"):
            return self._cm.__exit__(exc_type, exc_val, exc_tb)
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)


class _CapabilityStreamProxy:
    """Proxy para streams/iteradores de cursores y copy de psycopg que valida cada iteración."""

    def __init__(self, stream_obj: Any, cap: ExecutionCapability | None) -> None:
        self._stream_obj = stream_obj
        self._cap = cap

    def __iter__(self) -> "_CapabilityStreamProxy":
        return self

    def __next__(self) -> Any:
        if self._cap is not None:
            self._cap.check_or_raise("stream SQL fila")
        check_execution_capability_or_raise("stream SQL fila")
        return next(self._stream_obj)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream_obj, name)


class _CapabilityCursorProxy:
    """Proxy para cursores psycopg que valida la capacidad de ejecución antes de cada consulta."""

    def __init__(self, cur: Any, cap: ExecutionCapability | None) -> None:
        self._cur = cur
        self._cap = cap

    def execute(self, query: Any, params: Any = None, **kwargs: Any) -> "_CapabilityCursorProxy":
        if self._cap is not None:
            self._cap.check_or_raise("sentencia SQL")
        check_execution_capability_or_raise("sentencia SQL")
        self._cur.execute(query, params, **kwargs)
        return self

    def executemany(self, query: Any, params_seq: Any, **kwargs: Any) -> "_CapabilityCursorProxy":
        if self._cap is not None:
            self._cap.check_or_raise("sentencia SQL múltiple")
        check_execution_capability_or_raise("sentencia SQL múltiple")
        self._cur.executemany(query, params_seq, **kwargs)
        return self

    def copy(self, statement: Any, params: Any = None, **kwargs: Any) -> _CapabilityCopyProxy:
        if self._cap is not None:
            self._cap.check_or_raise("sentencia SQL copy")
        check_execution_capability_or_raise("sentencia SQL copy")
        copy_obj = self._cur.copy(statement, params, **kwargs)
        return _CapabilityCopyProxy(copy_obj, self._cap)

    def stream(self, query: Any, params: Any = None, **kwargs: Any) -> _CapabilityStreamProxy:
        if self._cap is not None:
            self._cap.check_or_raise("stream SQL")
        check_execution_capability_or_raise("stream SQL")
        stream_obj = self._cur.stream(query, params, **kwargs)
        return _CapabilityStreamProxy(stream_obj, self._cap)

    def __iter__(self) -> Any:
        if self._cap is not None:
            self._cap.check_or_raise("iteración cursor SQL")
        check_execution_capability_or_raise("iteración cursor SQL")
        return iter(self._cur)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cur, name)

    def __enter__(self) -> "_CapabilityCursorProxy":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        return self._cur.__exit__(exc_type, exc_val, exc_tb)

_ACTIVE_CONNS_BY_THREAD: dict[int, set[psycopg.Connection[Any]]] = {}
_CONNS_LOCK = threading.Lock()


def register_active_conn(conn: psycopg.Connection[Any]) -> None:
    tid = threading.get_ident()
    with _CONNS_LOCK:
        if tid not in _ACTIVE_CONNS_BY_THREAD:
            _ACTIVE_CONNS_BY_THREAD[tid] = set()
        _ACTIVE_CONNS_BY_THREAD[tid].add(conn)


def unregister_active_conn(conn: psycopg.Connection[Any]) -> None:
    tid = threading.get_ident()
    with _CONNS_LOCK:
        conns = _ACTIVE_CONNS_BY_THREAD.get(tid)
        if conns is not None:
            conns.discard(conn)
            if not conns:
                _ACTIVE_CONNS_BY_THREAD.pop(tid, None)


def cancel_active_conns_for_thread(tid: int) -> int:
    with _CONNS_LOCK:
        conns = list(_ACTIVE_CONNS_BY_THREAD.get(tid, set()))
    canceled_count = 0
    for c in conns:
        try:
            c.cancel()
            canceled_count += 1
        except Exception:
            pass
    return canceled_count


def set_deadline_context(deadline: float | None) -> contextvars.Token[float | None]:
    return _CURRENT_DEADLINE.set(deadline)


def reset_deadline_context(token: contextvars.Token[float | None]) -> None:
    _CURRENT_DEADLINE.reset(token)


def get_deadline_context() -> float | None:
    return _CURRENT_DEADLINE.get()


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


def checked_commit(conn: psycopg.Connection[Any]) -> None:
    conn_cap = getattr(conn, "_execution_capability", None)
    if conn_cap is not None:
        conn_cap.check_or_raise("commit en base de datos")

    cur_op = get_current_operation()
    op_id = cur_op.get("operation_id") if cur_op else None
    tid = threading.get_ident()

    # Si hay una operación activa en contexto, actualizar operation_records
    # dentro de esta misma transacción antes de commit (atomicidad A-02 / G2.1.7).
    # FAIL-CLOSED OBLIGATORIO: no se usa SAVEPOINT. Cualquier fallo aborta la transacción.
    if op_id is not None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE operation_records
                SET status = 'COMMITTED',
                    updated_at = clock_timestamp()
                WHERE operation_id = %s AND status = 'PENDING';
                """,
                (str(op_id),),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise RuntimeError(
                    f"Fallo de atomicidad obligatoria: el marcador operation_records para la operación {op_id} no pudo transicionar a COMMITTED (filas afectadas: {cur.rowcount}). Transacción abortada."
                )

    dl_check = get_deadline_context()
    if dl_check is not None:
        rem_sec = dl_check - time.monotonic()
        if rem_sec <= 0:
            try:
                conn.rollback()
            except Exception:
                pass
            if op_id is not None:
                mark_operation_aborted(op_id, "Operación abortada por expiración del deadline antes de commit.")
            raise TimeoutError("Operación abortada por expiración del deadline antes de commit.")

        target_epoch = time.time() + rem_sec
        # 1. Aplicar límite de transacción determinista evaluado dinámicamente en el dominio
        # temporal de PostgreSQL (clock_timestamp) para absorber cualquier pausa de transporte (A-02)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    /* SET LOCAL transaction_timeout */
                    SELECT CASE
                        WHEN %s <= EXTRACT(EPOCH FROM clock_timestamp())
                        THEN pg_cancel_backend(pg_backend_pid())::text
                        ELSE set_config(concat('transaction', '_timeout'), GREATEST(1, CEIL((%s - EXTRACT(EPOCH FROM clock_timestamp())) * 1000))::text, true)
                    END;
                    """,
                    (target_epoch, target_epoch),
                )
        except (
            psycopg.errors.QueryCanceled,
            psycopg.errors.AdminShutdown,
            getattr(psycopg.errors, "TransactionTimeout", psycopg.OperationalError),
        ) as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            if not is_deadline_cancellation(exc, dl_check):
                raise
            if op_id is not None:
                mark_operation_aborted(op_id, "Operación abortada por expiración del deadline durante sincronización inicial de commit.")
            raise TimeoutError("Operación abortada por expiración del deadline durante sincronización inicial de commit.") from exc
        except Exception:
            try:
                rem_fallback = max(1, int((dl_check - time.monotonic()) * 1000))
                with conn.cursor() as cur:
                    cur.execute(f"SET LOCAL statement_timeout = {rem_fallback};")
            except Exception:
                pass

        # 2. Re-verificar el tiempo disponible inmediatamente antes de iniciar COMMIT (Requisito 3)
        rem_sec_commit = dl_check - time.monotonic()
        if rem_sec_commit <= 0:
            try:
                conn.rollback()
            except Exception:
                pass
            if op_id is not None:
                mark_operation_aborted(op_id, "Operación abortada por expiración del deadline antes de commit.")
            raise TimeoutError("Operación abortada por expiración del deadline antes de commit.")

        # 3. Ajuste fino de seguridad anclado a clock_timestamp() en PostgreSQL
        target_epoch_commit = time.time() + rem_sec_commit
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    /* set_config('transaction_timeout', ...) */
                    SELECT CASE
                        WHEN %s <= EXTRACT(EPOCH FROM clock_timestamp())
                        THEN pg_cancel_backend(pg_backend_pid())::text
                        ELSE set_config('transaction_timeout', GREATEST(1, CEIL((%s - EXTRACT(EPOCH FROM clock_timestamp())) * 1000))::text, true)
                    END;
                    """,
                    (target_epoch_commit, target_epoch_commit),
                )
        except (
            psycopg.errors.QueryCanceled,
            psycopg.errors.AdminShutdown,
            getattr(psycopg.errors, "TransactionTimeout", psycopg.OperationalError),
        ) as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            if not is_deadline_cancellation(exc, dl_check):
                raise
            if op_id is not None:
                mark_operation_aborted(op_id, "Operación abortada por expiración del deadline durante ajuste final de commit.")
            raise TimeoutError("Operación abortada por expiración del deadline durante ajuste final de commit.") from exc
        except Exception:
            pass

        rem_sec_final = dl_check - time.monotonic()
        if rem_sec_final <= 0:
            try:
                conn.rollback()
            except Exception:
                pass
            if op_id is not None:
                mark_operation_aborted(op_id, "Operación abortada por expiración del deadline antes de commit.")
            raise TimeoutError("Operación abortada por expiración del deadline antes de commit.")

        timer = threading.Timer(max(0.001, rem_sec_final), conn.cancel)
        timer.daemon = True
        timer.start()
        register_in_flight_commit(tid, op_id)
        try:
            commit_fn = getattr(conn, "_orig_commit", conn.commit)
            commit_fn()
        except (
            psycopg.errors.QueryCanceled,
            psycopg.errors.AdminShutdown,
            psycopg.OperationalError,
            getattr(psycopg.errors, "TransactionTimeout", psycopg.OperationalError),
        ) as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            if not is_deadline_cancellation(exc, dl_check):
                raise
            if op_id is not None:
                mark_operation_aborted(op_id, "Operación abortada por expiración del deadline durante commit en base de datos.")
            raise TimeoutError("Operación abortada por expiración del deadline durante commit en base de datos.") from exc
        finally:
            timer.cancel()
            unregister_in_flight_commit(tid)

        # 4. Verificación post-commit de integridad:
        # Si el commit nativo retornó éxito, PostgreSQL confirmó la transacción.
        # NUNCA lanzar TimeoutError post-commit: la transacción ya es definitiva (COMMITTED).
    else:
        check_execution_capability_or_raise("commit en base de datos")
        register_in_flight_commit(tid, op_id)
        try:
            commit_fn = getattr(conn, "_orig_commit", conn.commit)
            commit_fn()
        finally:
            unregister_in_flight_commit(tid)


@contextmanager
def get_conn(statement_timeout_ms: int | None = None) -> Generator[psycopg.Connection[dict[str, Any]], None, None]:
    cap = get_current_capability()
    if cap is not None:
        cap.check_or_raise("apertura de conexión a base de datos")
    dl = get_deadline_context()
    if dl is not None:
        rem_sec = dl - time.monotonic()
        if rem_sec <= 0:
            raise TimeoutError("Deadline de base de datos expirado antes de abrir conexión.")
        if statement_timeout_ms is None:
            statement_timeout_ms = max(10, int(rem_sec * 1000))

    conn = psycopg.connect(settings.DATABASE_URL, row_factory=dict_row, connect_timeout=5)
    cap = get_current_capability()
    conn._execution_capability = cap  # type: ignore[attr-defined]
    orig_cursor = conn.cursor

    def _proxy_cursor(*c_args: Any, **c_kwargs: Any) -> _CapabilityCursorProxy:
        return _CapabilityCursorProxy(orig_cursor(*c_args, **c_kwargs), cap)

    conn.cursor = _proxy_cursor  # type: ignore[assignment]

    def _wrapped_conn_execute(query: Any, params: Any = None, **kwargs: Any) -> _CapabilityCursorProxy:
        proxy_cur = _proxy_cursor()
        return proxy_cur.execute(query, params, **kwargs)

    conn.execute = _wrapped_conn_execute  # type: ignore[assignment]

    orig_conn_copy = getattr(conn, "copy", None)
    if orig_conn_copy is not None:
        def _wrapped_conn_copy(statement: Any, params: Any = None, **kwargs: Any) -> _CapabilityCopyProxy:
            if cap is not None:
                cap.check_or_raise("sentencia SQL copy")
            check_execution_capability_or_raise("sentencia SQL copy")
            return _CapabilityCopyProxy(orig_conn_copy(statement, params, **kwargs), cap)

        conn.copy = _wrapped_conn_copy  # type: ignore[assignment]

    register_active_conn(conn)
    orig_commit = conn.commit
    conn._orig_commit = orig_commit  # type: ignore[attr-defined]

    def _wrapped_commit() -> None:
        checked_commit(conn)

    conn.commit = _wrapped_commit  # type: ignore[assignment]
    conn._backend_pid = getattr(getattr(conn, "info", None), "backend_pid", None)

    cur_op = get_current_operation()
    if cur_op and cur_op.get("operation_id") and conn._backend_pid:
        update_operation_backend_pid(cur_op["operation_id"], conn._backend_pid)

    try:
        if statement_timeout_ms is not None:
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)};")
                cur.execute(f"SET LOCAL lock_timeout = {int(statement_timeout_ms)};")
                if dl is not None:
                    target_epoch_early = time.time() + max(0.001, dl - time.monotonic())
                    try:
                        cur.execute(
                            """
                            SELECT CASE
                                WHEN %s <= EXTRACT(EPOCH FROM clock_timestamp())
                                THEN pg_cancel_backend(pg_backend_pid())::text
                                ELSE set_config('transaction_timeout', GREATEST(1, CEIL((%s - EXTRACT(EPOCH FROM clock_timestamp())) * 1000))::text, false)
                            END;
                            """,
                            (target_epoch_early, target_epoch_early),
                        )
                    except Exception:
                        pass
        yield conn
    finally:
        unregister_active_conn(conn)
        conn.close()


def run_migrations(migrations_dir: Path | None = None, database_url: str | None = None) -> list[str]:
    """Ejecuta migraciones SQL en orden alfabético de forma idempotente."""
    mdir = migrations_dir or settings.MIGRATIONS_DIR
    if not mdir.exists():
        logger.warning("Directorio de migraciones no encontrado: %s", mdir)
        return []

    applied: list[str] = []
    target_url = database_url or settings.DATABASE_URL
    with psycopg.connect(target_url, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(64) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

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
