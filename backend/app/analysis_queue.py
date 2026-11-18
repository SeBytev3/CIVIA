"""Cola durable de diagnóstico, compartida por la API y los workers."""

from dataclasses import dataclass
import hashlib
import logging
import math
import os
import random
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from app.db import get_conn
from app.schemas import AIAnalysisContract
from app.security import CitizenValidationError, sanitize_generated_text

logger = logging.getLogger("civia.analysis_queue")

STATES = ("QUEUED", "PROCESSING", "RETRY_SCHEDULED", "COMPLETED", "DEAD_LETTER", "CANCELLED")
BACKOFF_BASE_SECONDS = min(300, max(1, int(os.getenv("QUEUE_BACKOFF_BASE_SECONDS", "15"))))
BACKOFF_MAX_SECONDS = min(3600, max(BACKOFF_BASE_SECONDS, int(os.getenv("QUEUE_BACKOFF_MAX_SECONDS", "900"))))
MAX_PENDING = min(100_000, max(1, int(os.getenv("QUEUE_MAX_PENDING", "2000"))))
MAX_PENDING_PER_OWNER = min(MAX_PENDING, max(1, int(os.getenv("QUEUE_MAX_PENDING_PER_OWNER", "25"))))
MAX_PROCESSING = min(16, max(1, int(os.getenv("QUEUE_MAX_PROCESSING", "2"))))
MAX_ATTEMPTS = min(10, max(1, int(os.getenv("QUEUE_MAX_ATTEMPTS", "4"))))

_SAFE_ERRORS = {
    "TIMEOUT", "NETWORK_ERROR", "HTTP_429", "INVALID_JSON", "INVALID_SCHEMA",
    "PROVIDER_UNAVAILABLE", "CONFIGURATION", "EMPTY_RESPONSE", "EMPTY_TEXT",
    "MISSING_EVIDENCE", "LEASE_EXPIRED", "INTERNAL_ERROR", "INPUT_INVALID",
    "CIRCUIT_OPEN", "BUDGET_EXHAUSTED", "RATE_LIMITED", "PROVIDER_CAPACITY",
}
_ACTIVE_STATES = "('QUEUED', 'PROCESSING', 'RETRY_SCHEDULED')"


@dataclass(frozen=True)
class AnalysisJob:
    id: UUID
    report_id: UUID
    report_version: int
    fence: int


def _check_capacity(cur: Any, owner_id: UUID | None) -> None:
    # Serializar las admisiones, incluidas las reactivaciones de la DLQ.
    cur.execute("SELECT pg_advisory_xact_lock(6110, 1)")
    cur.execute(
        f"""
        SELECT count(*) AS total, count(*) FILTER (WHERE r.owner_id = %s) AS owned
        FROM analysis_jobs j JOIN reports r ON r.id = j.report_id
        WHERE j.state IN {_ACTIVE_STATES}
        """,
        (owner_id,),
    )
    row = cur.fetchone()
    if row["total"] >= MAX_PENDING or row["owned"] >= MAX_PENDING_PER_OWNER:
        raise CitizenValidationError(
            "El servicio de recepción está ocupado. Conserva el borrador e inténtalo más tarde.",
            status_code=429,
            code="RECEIPT_CAPACITY_REACHED",
        )


def enqueue_in_transaction(
    cur: Any, report_id: UUID, report_version: int, owner_id: UUID | None
) -> bool:
    cur.execute(
        "SELECT 1 FROM analysis_jobs WHERE report_id = %s AND report_version = %s",
        (report_id, report_version),
    )
    if cur.fetchone():
        return False
    _check_capacity(cur, owner_id)
    cur.execute(
        """
        INSERT INTO analysis_jobs (report_id, report_version, max_attempts) VALUES (%s, %s, %s)
        ON CONFLICT (report_id, report_version) DO NOTHING
        """,
        (report_id, report_version, MAX_ATTEMPTS),
    )
    return cur.rowcount == 1


def enqueue_report_analysis(report_id: UUID, *, owner_id: UUID | None = None) -> bool:
    with get_conn(statement_timeout_ms=5000) as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(6110, 1)")
        cur.execute(
            """
            SELECT id, version, owner_id FROM reports WHERE id = %s
              AND (%s::uuid IS NULL OR owner_id = %s)
              AND status = 'PENDING_ANALYSIS' AND NOT human_confirmed
            FOR NO KEY UPDATE
            """,
            (report_id, owner_id, owner_id),
        )
        row = cur.fetchone()
        queued = bool(row and enqueue_in_transaction(cur, row["id"], row["version"], row["owner_id"]))
        conn.commit()
        return queued


def retry_delay(attempts: int, retry_after_seconds: float | None = None) -> float:
    base = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** min(10, max(0, attempts - 1))))
    jittered = base * random.uniform(0.9, 1.1)
    requested = (
        retry_after_seconds
        if retry_after_seconds is not None and math.isfinite(retry_after_seconds)
        else 0
    )
    return min(BACKOFF_MAX_SECONDS, max(jittered, requested))


def _transition_failed(
    cur: Any, job: dict[str, Any], code: str, *, retryable: bool,
    retry_after_seconds: float | None = None, defer_attempt: bool = False,
    require_current_lease: bool = False,
) -> bool:
    cur.execute("SELECT * FROM civia_lock_analysis_report(%s)", (job["id"],))
    report = cur.fetchone()
    valid = (
        report and report["version"] == job["report_version"]
        and not report["human_confirmed"] and report["status"] == "PENDING_ANALYSIS"
    )
    attempts = job["attempts"] - int(defer_attempt and retryable)
    if not valid:
        state = "CANCELLED"
    elif retryable and attempts < job["max_attempts"]:
        state = "RETRY_SCHEDULED"
    else:
        state = "DEAD_LETTER"
    delay = retry_delay(attempts, retry_after_seconds) if state == "RETRY_SCHEDULED" else 0
    cur.execute(
        """
        UPDATE analysis_jobs
        SET state = %(state)s, attempts = %(attempts)s, worker_id = NULL, lease_expires_at = NULL,
            last_error = %(code)s, available_at = clock_timestamp() + make_interval(secs => %(delay)s),
            finished_at = CASE WHEN %(terminal)s THEN clock_timestamp() ELSE NULL END
        WHERE id = %(id)s AND (NOT %(require_current_lease)s OR lease_expires_at > clock_timestamp())
        """,
        {
            "state": state, "attempts": attempts, "code": code, "delay": delay,
            "terminal": state != "RETRY_SCHEDULED", "id": job["id"],
            "require_current_lease": require_current_lease,
        },
    )
    if cur.rowcount != 1:
        return False
    if state == "DEAD_LETTER":
        cur.execute(
            """
            INSERT INTO report_events (report_id, event_type, public_message)
            VALUES (%s, 'ANALYSIS_MANUAL_REVIEW', 'El reporte requiere revisión manual.')
            """,
            (job["report_id"],),
        )
        cur.execute(
            """
            INSERT INTO admin_notifications (report_id, title, message, is_synthetic)
            VALUES (%s, %s, 'El reporte requiere revisión manual.', %s)
            ON CONFLICT (report_id) DO UPDATE
            SET title = EXCLUDED.title, message = EXCLUDED.message,
                is_read = FALSE, read_at = NULL, created_at = clock_timestamp()
            """,
            (job["report_id"], f"Revisión manual: {report['tracking_code']}", report["is_synthetic"]),
        )
    return True


def claim_job(
    worker_id: str, *, lease_seconds: int = 90, circuit_breakers: list[dict[str, Any]] | None = None,
) -> AnalysisJob | None:
    if not worker_id or len(worker_id) > 128 or not 1 <= lease_seconds <= 300:
        raise ValueError("Identificador o duración del arrendamiento no válidos.")
    with get_conn(statement_timeout_ms=5000) as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(6110, 2)")
        cur.execute(
            """
            INSERT INTO analysis_worker_status (worker_id, last_seen_at, circuits)
            VALUES (%s, clock_timestamp(), %s)
            ON CONFLICT (worker_id) DO UPDATE
            SET last_seen_at = EXCLUDED.last_seen_at, circuits = EXCLUDED.circuits
            """,
            (worker_id, Jsonb(circuit_breakers or [])),
        )
        cur.execute(
            "DELETE FROM analysis_worker_status WHERE last_seen_at < clock_timestamp() - interval '1 hour'"
        )
        cur.execute(
            """
            SELECT id, report_id, report_version, attempts, max_attempts FROM analysis_jobs
            WHERE state = 'PROCESSING' AND lease_expires_at <= clock_timestamp()
            ORDER BY lease_expires_at
            LIMIT 10 FOR UPDATE SKIP LOCKED
            """
        )
        expired_jobs = cur.fetchall()
        for expired in expired_jobs:
            _transition_failed(cur, expired, "LEASE_EXPIRED", retryable=True)
        cur.execute(
            """
            WITH candidate AS (
                SELECT id FROM analysis_jobs
                WHERE state IN ('QUEUED', 'RETRY_SCHEDULED') AND available_at <= clock_timestamp()
                  AND attempts < max_attempts
                  AND (
                    SELECT count(*) FROM analysis_jobs
                    WHERE state = 'PROCESSING' AND lease_expires_at > clock_timestamp()
                  ) < %s
                ORDER BY priority DESC, available_at, id
                LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            UPDATE analysis_jobs j
            SET state = 'PROCESSING', attempts = j.attempts + 1, fence = j.fence + 1,
                worker_id = %s, lease_expires_at = clock_timestamp() + make_interval(secs => %s)
            FROM candidate
            WHERE j.id = candidate.id
            RETURNING j.id, j.report_id, j.report_version, j.fence
            """,
            (MAX_PROCESSING, worker_id, lease_seconds),
        )
        row = cur.fetchone()
        conn.commit()
    for expired in expired_jobs:
        logger.info("Arrendamiento expirado recuperado para trabajo %s.", expired["id"])
    return AnalysisJob(**row) if row else None


def get_job_evidence(job: AnalysisJob) -> dict[str, Any] | None:
    with get_conn(statement_timeout_ms=5000) as conn:
        return conn.execute(
            "SELECT * FROM civia_worker_job_evidence(%s, %s)",
            (job.id, job.fence),
        ).fetchone()


def finish_job(job: AnalysisJob, analysis: AIAnalysisContract, *, transcript: str | None = None) -> bool:
    summary = sanitize_generated_text(analysis.summary, 450)
    if len(summary) < 10:
        fail_job(job, "INVALID_SCHEMA", retryable=True)
        return False
    keywords = [word for value in analysis.keywords if (word := sanitize_generated_text(value, 40))]
    with get_conn(statement_timeout_ms=5000) as conn:
        row = conn.execute(
            """
            SELECT civia_publish_analysis_with_audio(%s, %s, %s, %s, %s, %s, %s, %s) AS published
            """,
            (
                job.id, job.fence, analysis.category, analysis.severity,
                analysis.confidence, summary, Jsonb(keywords), sanitize_generated_text(transcript, 600) or None,
            ),
        ).fetchone()
        conn.commit()
        return row["published"]


def fail_job(
    job: AnalysisJob, code: str, *,
    retryable: bool, retry_after_seconds: float | None = None, defer_attempt: bool = False,
) -> bool:
    if code not in _SAFE_ERRORS:
        code = "PROVIDER_UNAVAILABLE"
    with get_conn(statement_timeout_ms=5000) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, report_id, report_version, attempts, max_attempts FROM analysis_jobs
            WHERE id = %s AND fence = %s AND state = 'PROCESSING'
              AND lease_expires_at > clock_timestamp()
            FOR UPDATE
            """,
            (job.id, job.fence),
        )
        row = cur.fetchone()
        if not row:
            return False
        transitioned = _transition_failed(
            cur, row, code, retryable=retryable,
            retry_after_seconds=retry_after_seconds, defer_attempt=defer_attempt,
            require_current_lease=True,
        )
        conn.commit()
        if transitioned:
            logger.info("Fallo registrado en trabajo %s por %s.", job.id, code)
        return transitioned


def requeue_dead_letter(
    job_id: UUID, actor_id: UUID, idempotency_key: str | None = None,
) -> bool:
    operation_key = hashlib.sha256(f"{job_id}:{idempotency_key or 'default'}".encode()).hexdigest()
    with get_conn(statement_timeout_ms=5000) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE id = %s AND active AND role = 'WEB_ADMIN' FOR SHARE",
            (actor_id,),
        )
        if not cur.fetchone():
            return False
        cur.execute("SELECT pg_advisory_xact_lock(6110, 1)")
        cur.execute(
            """
            SELECT 1 FROM operation_records
            WHERE requester_id = %s AND operation_type = 'admin_requeue_analysis'
              AND idempotency_key = %s AND status = 'COMMITTED'
            """,
            (str(actor_id), operation_key),
        )
        if cur.fetchone():
            return True
        cur.execute(
            """
            SELECT j.id, j.report_id, j.state,
                   r.owner_id, r.version, r.status, r.human_confirmed, j.report_version
            FROM analysis_jobs j JOIN reports r ON r.id = j.report_id
            WHERE j.id = %s FOR UPDATE OF j FOR SHARE OF r
            """,
            (job_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        if row["state"] != "DEAD_LETTER":
            return False
        if row["human_confirmed"] or row["status"] != "PENDING_ANALYSIS" or row["version"] != row["report_version"]:
            return False
        _check_capacity(cur, row["owner_id"])
        cur.execute(
            """
            UPDATE analysis_jobs
            SET state = 'QUEUED', attempts = 0, fence = fence + 1, last_error = NULL,
                available_at = clock_timestamp(), finished_at = NULL, requeue_count = requeue_count + 1
            WHERE id = %s
            """,
            (job_id,),
        )
        cur.execute(
            """
            INSERT INTO operation_records (
                operation_id, requester_id, operation_type, target_id, status, proposed_payload, idempotency_key
            ) VALUES (gen_random_uuid(), %s, 'admin_requeue_analysis', %s, 'COMMITTED', %s, %s)
            """,
            (str(actor_id), str(row["report_id"]), Jsonb({"job_id": str(job_id)}), operation_key),
        )
        cur.execute(
            "INSERT INTO security_audit (actor_id, action, target_id) VALUES (%s, 'queue.requeue', %s)",
            (actor_id, job_id),
        )
        conn.commit()
        return True


def list_dead_letters(*, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with get_conn(statement_timeout_ms=5000) as conn:
        return conn.execute(
            """
            SELECT j.id, j.report_id, r.tracking_code, j.attempts, j.max_attempts, j.last_error, j.finished_at
            FROM analysis_jobs j JOIN reports r ON r.id = j.report_id
            WHERE j.state = 'DEAD_LETTER' ORDER BY j.finished_at DESC, j.id
            LIMIT %s OFFSET %s
            """,
            (min(200, max(1, limit)), max(0, offset)),
        ).fetchall()


def worker_available() -> bool:
    with get_conn(statement_timeout_ms=5000) as conn:
        return conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM analysis_worker_status
                WHERE last_seen_at > clock_timestamp() - interval '5 minutes'
            ) AS available
            """
        ).fetchone()["available"]


def queue_status() -> dict[str, Any]:
    with get_conn(statement_timeout_ms=5000) as conn:
        rows = conn.execute(
            """
            SELECT state, count(*) AS count, min(created_at) AS oldest
            FROM analysis_jobs GROUP BY state
            """
        ).fetchall()
        workers = conn.execute(
            """
            SELECT worker_id, circuits FROM analysis_worker_status
            WHERE last_seen_at > clock_timestamp() - interval '5 minutes'
            ORDER BY last_seen_at DESC, worker_id
            """
        ).fetchall()
        completion = conn.execute(
            """
            SELECT now() AS db_now, count(*) AS samples,
                   percentile_cont(0.50) WITHIN GROUP (ORDER BY seconds) AS p50,
                   percentile_cont(0.90) WITHIN GROUP (ORDER BY seconds) AS p90,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY seconds) AS p95,
                   (SELECT count(*) FROM analysis_jobs
                    WHERE state = 'COMPLETED' AND finished_at > now() - interval '1 minute') AS last_minute
            FROM (
                SELECT extract(epoch FROM finished_at - created_at) AS seconds
                FROM analysis_jobs WHERE state = 'COMPLETED'
                ORDER BY finished_at DESC LIMIT 100
            ) latest
            """
        ).fetchone()
    counts = dict.fromkeys(STATES, 0)
    waiting = []
    for row in rows:
        counts[row["state"]] = row["count"]
        if row["state"] in ("QUEUED", "RETRY_SCHEDULED"):
            waiting.append(row["oldest"])
    return {
        "counts": counts,
        "oldest_pending_seconds": max(0, int((completion["db_now"] - min(waiting)).total_seconds())) if waiting else None,
        "worker_available": bool(workers),
        "workers_active": len(workers),
        "worker_circuits": [dict(circuit, worker_id=worker["worker_id"]) for worker in workers for circuit in worker["circuits"]],
        "completed_last_minute": completion["last_minute"],
        "latency_seconds": {key: completion[key] for key in ("samples", "p50", "p90", "p95")},
    }
