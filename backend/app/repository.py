from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any, Callable
from uuid import UUID
import uuid

import psycopg

from app.db import get_conn
from app.observability import sanitize_secret_text
from app.security import _CO_PHONE_RE, _EMAIL_RE, CitizenValidationError

_ON_REPORT_CREATED_HOOK: Callable[[UUID], None] | None = None


def set_report_created_hook(hook: Callable[[UUID], None] | None) -> None:
    global _ON_REPORT_CREATED_HOOK
    _ON_REPORT_CREATED_HOOK = hook


def _sanitize_public_text(text: str | None) -> str | None:
    if not text:
        return text
    import re

    cleaned = sanitize_secret_text(text) or ""
    cleaned = _EMAIL_RE.sub("[CORREO_PROTEGIDO]", cleaned)
    cleaned = _CO_PHONE_RE.sub("[TELEFONO_PROTEGIDO]", cleaned)
    cleaned = re.sub(
        r"\b(?:gemini|groq|google\s+api|google|anthropic|openai|qwen|api|traceback|valueerror|typeerror|runtimeerror|connectionerror|httperror)\b",
        "[SISTEMA_IA]",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bHTTP[_\s-]*(?:4\d\d|5\d\d)\b", "[SERVICIO_OCUPADO]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:status[_\s-]*code|status|error[_\s-]*code)\s*[:=]?\s*(?:4\d\d|5\d\d)\b",
        "[ERROR_SERVICIO]",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()

STATUS_MESSAGES: dict[str, str] = {
    "PENDING_ANALYSIS": "Reporte recibido y almacenado de forma segura. El análisis automático está pendiente de procesamiento.",
    "ANALYZED_PENDING_CONFIRMATION": "Evidencia analizada automáticamente. Revise y confirme o ajuste la categoría sugerida.",
    "CONFIRMED": "Reporte confirmado por la ciudadanía y disponible para gestión.",
    "IN_REVIEW": "Reporte en revisión técnica por el equipo operativo.",
    "RESOLVED": "Reporte atendido y resuelto.",
    "REJECTED": "Reporte descartado tras verificación.",
}


def row_to_public_dict(row: dict[str, Any]) -> dict[str, Any]:
    report_id = str(row["id"])
    ai_keywords = row.get("ai_keywords")
    if isinstance(ai_keywords, str):
        try:
            ai_keywords = json.loads(ai_keywords)
        except Exception:
            ai_keywords = []
    elif not isinstance(ai_keywords, list):
        ai_keywords = []

    effective_cat = row.get("final_category") or row.get("ai_category")
    effective_sev = row.get("final_severity") or row.get("ai_severity")
    status = row["status"]
    dist = row.get("distance_km")

    return {
        "id": row["id"],
        "tracking_code": row["tracking_code"],
        "title": _sanitize_public_text(row["title"]) or row["title"],
        "description": _sanitize_public_text(row["description"]) or row["description"],
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "in_service_area": bool(row["in_service_area"]),
        "comuna": row.get("comuna"),
        "neighborhood": row.get("neighborhood"),
        "address_hint": row.get("address_hint"),
        "photo_url": f"/api/reports/{report_id}/photo?v={str(row.get('photo_sha256') or '')[:16]}" if row.get("photo_sha256") else f"/api/reports/{report_id}/photo",
        "photo_mime": row["photo_mime"],
        "photo_width": int(row["photo_width"]),
        "photo_height": int(row["photo_height"]),
        "has_audio": bool(row.get("audio_path")),
        "audio_transcript": _sanitize_public_text(row.get("audio_transcript")),
        "ai_category": row.get("ai_category"),
        "ai_severity": row.get("ai_severity"),
        "ai_confidence": float(row["ai_confidence"]) if row.get("ai_confidence") is not None else None,
        "ai_summary": _sanitize_public_text(row.get("ai_summary")),
        "ai_keywords": ai_keywords,
        "final_category": row.get("final_category"),
        "final_severity": row.get("final_severity"),
        "effective_category": effective_cat,
        "effective_severity": effective_sev,
        "human_confirmed": bool(row["human_confirmed"]),
        "human_override_note": _sanitize_public_text(row.get("human_override_note")),
        "status": status,
        "status_message": STATUS_MESSAGES.get(status, "Reporte registrado."),
        "distance_km": round(float(dist), 3) if dist is not None else None,
        "is_synthetic": bool(row.get("is_synthetic", False)),
        "citizen_edit_token": row.get("_citizen_edit_token"),
        "assigned_to": row.get("assigned_to"),
        "assigned_at": row.get("assigned_at"),
        "external_delivery_status": row.get("external_delivery_status") or "NOT_ENABLED",
        "external_delivery_channel": "Correo electrónico (No habilitado)",
        "external_delivery_message": "Correo a entidad: No enviado — servicio no habilitado",
        "admin_review_status": row.get("admin_review_status") or "PENDING_REVIEW",
        "last_public_note": _sanitize_public_text(row.get("last_public_note")),
        "events": [
            {
                "id": str(ev["id"]),
                "report_id": str(ev["report_id"]),
                "event_type": str(ev.get("event_type") or ""),
                "previous_status": ev.get("previous_status"),
                "new_status": ev.get("new_status"),
                "public_message": _sanitize_public_text(ev.get("public_message")) or str(ev.get("public_message") or ""),
                "actor_type": str(ev.get("actor_type") or "SYSTEM"),
                "created_at": ev["created_at"].isoformat() if hasattr(ev["created_at"], "isoformat") else str(ev["created_at"]),
            }
            for ev in (row.get("events") or [])
        ],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def generate_citizen_edit_token() -> str:
    """Genera una capacidad de edición impredecible por reporte mediante CSPRNG."""
    return secrets.token_urlsafe(32)


def hash_edit_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def hash_idempotency_key(raw_key: str) -> str:
    return hashlib.sha256(f"civia-idem-v2:{raw_key.strip()}".encode("utf-8")).hexdigest()


def _seal_edit_token_for_idempotency(raw_idem_key: str, report_id: UUID, edit_token: str) -> str:
    token_bytes = edit_token.encode("utf-8")
    rid = UUID(str(report_id))
    keystream = hashlib.pbkdf2_hmac(
        "sha256",
        raw_idem_key.strip().encode("utf-8"),
        rid.bytes,
        iterations=10_000,
        dklen=len(token_bytes),
    )
    cipher_bytes = bytes(a ^ b for a, b in zip(token_bytes, keystream))
    return cipher_bytes.hex()


def _unseal_edit_token_for_idempotency(
    raw_idem_key: str, report_id: UUID, sealed_hex: str | None
) -> str | None:
    if not sealed_hex:
        return None
    try:
        cipher_bytes = bytes.fromhex(sealed_hex)
    except ValueError:
        return None
    rid = UUID(str(report_id))
    keystream = hashlib.pbkdf2_hmac(
        "sha256",
        raw_idem_key.strip().encode("utf-8"),
        rid.bytes,
        iterations=10_000,
        dklen=len(cipher_bytes),
    )
    plain_bytes = bytes(a ^ b for a, b in zip(cipher_bytes, keystream))
    try:
        return plain_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None


def generate_tracking_code(
    report_uuid: UUID,
    *,
    created_year: int | None = None,
    attempt: int = 0,
) -> str:
    year = created_year if created_year is not None else datetime.now(timezone.utc).year
    seed = report_uuid.bytes if attempt == 0 else f"{report_uuid.hex}:{attempt}".encode("utf-8")
    short = hashlib.sha256(seed).hexdigest()[:10].upper()
    return f"CIV-{year}-{short}"


def create_report(
    *,
    title: str,
    description: str,
    latitude: float,
    longitude: float,
    in_service_area: bool,
    comuna: str | None,
    neighborhood: str | None,
    address_hint: str | None,
    photo_meta: dict[str, Any],
    audio_meta: dict[str, Any] | None = None,
    audio_transcript: str | None = None,
    report_id: UUID | None = None,
    tracking_code: str | None = None,
    is_synthetic: bool = False,
    idempotency_key: str | None = None,
    request_fingerprint: str | None = None,
    citizen_edit_token: str | None = None,
) -> dict[str, Any]:
    rid = report_id or uuid.uuid4()
    am = audio_meta or {}
    raw_idem_key = idempotency_key.strip() if (idempotency_key and idempotency_key.strip()) else None
    if raw_idem_key is not None and (len(raw_idem_key) < 8 or len(raw_idem_key) > 128):
        raise CitizenValidationError(
            "La clave de idempotencia proporcionada no tiene una longitud válida.",
            status_code=422,
            code="INVALID_IDEMPOTENCY_KEY",
        )
    idem_key_hash = hash_idempotency_key(raw_idem_key) if raw_idem_key else None
    eff_fingerprint = (request_fingerprint or "").strip()[:64]
    c_token = (citizen_edit_token or generate_citizen_edit_token()).strip()
    c_token_hash = hash_edit_token(c_token)

    with get_conn() as conn:
        with conn.cursor() as cur:
            if idem_key_hash and raw_idem_key:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s));", (idem_key_hash,))
                cur.execute(
                    """
                    SELECT r.*,
                           ir.request_fingerprint AS _stored_fingerprint,
                           ir.citizen_edit_token AS _sealed_edit_token
                    FROM reports r
                    LEFT JOIN idempotency_records ir ON ir.idempotency_key = r.idempotency_key
                    WHERE r.idempotency_key = %s
                    LIMIT 1;
                    """,
                    (idem_key_hash,),
                )
                existing_row = cur.fetchone()
                if existing_row is not None:
                    stored_fp = existing_row.get("_stored_fingerprint")
                    if eff_fingerprint and stored_fp and stored_fp != eff_fingerprint:
                        raise CitizenValidationError(
                            "La clave Idempotency-Key ya fue utilizada para una solicitud distinta.",
                            status_code=409,
                            code="IDEMPOTENCY_KEY_CONFLICT",
                        )
                    existing_row["_replayed"] = True
                    existing_row["_citizen_edit_token"] = _unseal_edit_token_for_idempotency(
                        raw_idem_key,
                        existing_row["id"],
                        existing_row.get("_sealed_edit_token"),
                    )
                    conn.commit()
                    return existing_row

            row: dict[str, Any] | None = None
            last_exc: Exception | None = None
            for attempt in range(5):
                tcode = (
                    tracking_code
                    if (tracking_code and attempt == 0)
                    else generate_tracking_code(rid, attempt=attempt)
                )
                cur.execute("SAVEPOINT sp_insert_report;")
                try:
                    cur.execute(
                        """
                        INSERT INTO reports (
                            id, tracking_code, title, description,
                            latitude, longitude, in_service_area,
                            comuna, neighborhood, address_hint,
                            photo_path, photo_mime, photo_size_bytes,
                            photo_width, photo_height, photo_sha256,
                            audio_path, audio_mime, audio_size_bytes,
                            audio_duration_seconds, audio_transcript,
                            status, is_synthetic, edit_token_hash, idempotency_key, version
                        )
                        VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            'PENDING_ANALYSIS', %s, %s, %s, 1
                        )
                        RETURNING *;
                        """,
                        (
                            rid,
                            tcode,
                            title,
                            description,
                            latitude,
                            longitude,
                            in_service_area,
                            comuna,
                            neighborhood,
                            address_hint,
                            photo_meta["photo_path"],
                            photo_meta["photo_mime"],
                            photo_meta["photo_size_bytes"],
                            photo_meta["photo_width"],
                            photo_meta["photo_height"],
                            photo_meta["photo_sha256"],
                            am.get("audio_path"),
                            am.get("audio_mime"),
                            am.get("audio_size_bytes"),
                            am.get("audio_duration_seconds"),
                            audio_transcript,
                            is_synthetic,
                            c_token_hash,
                            idem_key_hash,
                        ),
                    )
                    row = cur.fetchone()
                    cur.execute("RELEASE SAVEPOINT sp_insert_report;")
                    break
                except psycopg.errors.UniqueViolation as exc:
                    last_exc = exc
                    cur.execute("ROLLBACK TO SAVEPOINT sp_insert_report;")
                    if idem_key_hash and raw_idem_key:
                        cur.execute(
                            """
                            SELECT r.*,
                                   ir.request_fingerprint AS _stored_fingerprint,
                                   ir.citizen_edit_token AS _sealed_edit_token
                            FROM reports r
                            LEFT JOIN idempotency_records ir ON ir.idempotency_key = r.idempotency_key
                            WHERE r.idempotency_key = %s
                            LIMIT 1;
                            """,
                            (idem_key_hash,),
                        )
                        concurrent_row = cur.fetchone()
                        if concurrent_row is not None:
                            stored_fp = concurrent_row.get("_stored_fingerprint")
                            if eff_fingerprint and stored_fp and stored_fp != eff_fingerprint:
                                raise CitizenValidationError(
                                    "La clave Idempotency-Key ya fue utilizada para una solicitud distinta.",
                                    status_code=409,
                                    code="IDEMPOTENCY_KEY_CONFLICT",
                                ) from exc
                            concurrent_row["_replayed"] = True
                            concurrent_row["_citizen_edit_token"] = _unseal_edit_token_for_idempotency(
                                raw_idem_key,
                                concurrent_row["id"],
                                concurrent_row.get("_sealed_edit_token"),
                            )
                            conn.commit()
                            return concurrent_row
                    rid = report_id or uuid.uuid4()
                    c_token = (citizen_edit_token or generate_citizen_edit_token()).strip()
                    c_token_hash = hash_edit_token(c_token)

            if row is None:
                if last_exc is not None:
                    raise last_exc
                raise RuntimeError("No se pudo insertar el reporte tras reintentos de colisión.")

            if idem_key_hash and raw_idem_key:
                sealed_token = _seal_edit_token_for_idempotency(raw_idem_key, row["id"], c_token)
                cur.execute(
                    """
                    INSERT INTO idempotency_records (
                        idempotency_key, request_fingerprint, report_id, tracking_code, citizen_edit_token
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (idempotency_key) DO NOTHING;
                    """,
                    (
                        idem_key_hash,
                        eff_fingerprint or "default",
                        row["id"],
                        row["tracking_code"],
                        sealed_token,
                    ),
                )

            # Registrar evento inicial de trazabilidad ciudadana
            try:
                cur.execute(
                    """
                    INSERT INTO report_events (id, report_id, event_type, previous_status, new_status, public_message, actor_type, created_at)
                    VALUES (gen_random_uuid(), %s, 'REPORT_REGISTERED', NULL, 'PENDING_ANALYSIS', 'Reporte recibido y registrado exitosamente en la plataforma CIVIA.', 'CITIZEN', %s)
                    ON CONFLICT DO NOTHING;
                    """,
                    (row["id"], row["created_at"]),
                )
                # Registrar notificación interna para la administración
                cur.execute(
                    """
                    INSERT INTO admin_notifications (id, report_id, title, message, is_read, is_synthetic, created_at)
                    VALUES (gen_random_uuid(), %s, %s, %s, FALSE, %s, %s)
                    ON CONFLICT (report_id) DO NOTHING;
                    """,
                    (
                        row["id"],
                        f"Nuevo reporte recibido: {row['tracking_code']}",
                        f"Reporte ciudadano registrado en {row.get('neighborhood') or row.get('comuna') or 'Santiago de Cali'}. Pendiente de revisión.",
                        bool(is_synthetic),
                        row["created_at"],
                    ),
                )
            except Exception:
                pass

            try:
                cur.execute(
                    """
                    SELECT id, report_id, event_type, previous_status, new_status,
                           public_message, actor_type, created_at
                    FROM report_events
                    WHERE report_id = %s
                    ORDER BY created_at ASC;
                    """,
                    (row["id"],),
                )
                row["events"] = cur.fetchall()
            except Exception:
                row["events"] = []

            conn.commit()
            if _ON_REPORT_CREATED_HOOK is not None and not is_synthetic:
                try:
                    _ON_REPORT_CREATED_HOOK(UUID(str(row["id"])))
                except Exception:
                    pass
            row["_replayed"] = False
            row["_citizen_edit_token"] = c_token
            return row


def get_report_raw(report_id: UUID | str, include_events: bool = True) -> dict[str, Any] | None:
    try:
        rid = UUID(str(report_id))
    except (ValueError, TypeError):
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM reports WHERE id = %s;", (rid,))
            row = cur.fetchone()
            if row and include_events:
                try:
                    cur.execute(
                        """
                        SELECT id, report_id, event_type, previous_status, new_status,
                               public_message, actor_type, created_at
                        FROM report_events
                        WHERE report_id = %s
                        ORDER BY created_at ASC;
                        """,
                        (row["id"],),
                    )
                    row["events"] = cur.fetchall()
                except Exception:
                    row["events"] = []
            return row


def get_report_by_tracking_code(tracking_code: str, include_events: bool = True) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM reports WHERE UPPER(tracking_code) = UPPER(%s);",
                (tracking_code.strip(),),
            )
            row = cur.fetchone()
            if row and include_events:
                try:
                    cur.execute(
                        """
                        SELECT id, report_id, event_type, previous_status, new_status,
                               public_message, actor_type, created_at
                        FROM report_events
                        WHERE report_id = %s
                        ORDER BY created_at ASC;
                        """,
                        (row["id"],),
                    )
                    row["events"] = cur.fetchall()
                except Exception:
                    row["events"] = []
            return row


def update_report_ai_analysis(
    report_id: UUID | str,
    *,
    ai_category: str,
    ai_severity: str,
    ai_confidence: float,
    ai_summary: str,
    ai_keywords: list[str],
    auto_confirm: bool = False,
) -> dict[str, Any] | None:
    rid = UUID(str(report_id))
    new_status = "CONFIRMED" if auto_confirm else "ANALYZED_PENDING_CONFIRMATION"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE reports
                SET ai_category = %s,
                    ai_severity = %s,
                    ai_confidence = %s,
                    ai_summary = %s,
                    ai_keywords = %s::jsonb,
                    final_category = COALESCE(final_category, %s),
                    final_severity = COALESCE(final_severity, %s),
                    human_confirmed = CASE WHEN %s THEN TRUE ELSE human_confirmed END,
                    status = CASE
                        WHEN status IN ('CONFIRMED', 'IN_REVIEW', 'RESOLVED', 'REJECTED') THEN status
                        ELSE %s
                    END,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (
                    ai_category,
                    ai_severity,
                    ai_confidence,
                    ai_summary,
                    json.dumps(ai_keywords, ensure_ascii=False),
                    ai_category if auto_confirm else None,
                    ai_severity if auto_confirm else None,
                    auto_confirm,
                    new_status,
                    rid,
                ),
            )
            row = cur.fetchone()
            if row is not None:
                try:
                    cur.execute(
                        """
                        INSERT INTO report_events (id, report_id, event_type, previous_status, new_status, public_message, actor_type)
                        VALUES (gen_random_uuid(), %s, 'AI_ANALYSIS_COMPLETED', 'PENDING_ANALYSIS', %s, %s, 'SYSTEM');
                        """,
                        (
                            rid,
                            row["status"],
                            f"Análisis preliminar de IA completado. Categoría sugerida: {ai_category}.",
                        ),
                    )
                except Exception:
                    pass
            try:
                cur.execute(
                    """
                    SELECT id, report_id, event_type, previous_status, new_status,
                           public_message, actor_type, created_at
                    FROM report_events
                    WHERE report_id = %s
                    ORDER BY created_at ASC;
                    """,
                    (rid,),
                )
                row["events"] = cur.fetchall()
            except Exception:
                row["events"] = []

            conn.commit()
            return row


def confirm_report_category(
    report_id: UUID | str,
    *,
    final_category: str,
    final_severity: str | None = None,
    human_override_note: str | None = None,
    edit_token: str | None = None,
    is_admin: bool = False,
) -> dict[str, Any] | None:
    rid = UUID(str(report_id))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM reports WHERE id = %s FOR UPDATE;", (rid,))
            existing = cur.fetchone()
            if not existing:
                return None

            if not is_admin:
                if bool(existing.get("human_confirmed")) or existing["status"] in (
                    "CONFIRMED",
                    "IN_REVIEW",
                    "RESOLVED",
                    "REJECTED",
                ):
                    raise CitizenValidationError(
                        "El reporte ya fue confirmado o gestionado administrativamente y no puede modificarse sin autorización administrativa.",
                        status_code=409,
                        code="REPORT_ALREADY_MANAGED",
                    )

                stored_hash = (existing.get("edit_token_hash") or "").strip()
                provided_token = (edit_token or "").strip()
                provided_hash = hash_edit_token(provided_token) if provided_token else ""
                if (
                    not stored_hash
                    or not provided_hash
                    or not hmac.compare_digest(provided_hash, stored_hash)
                ):
                    raise CitizenValidationError(
                        "Se requiere la credencial de edición del reporte para confirmar o ajustar su clasificación.",
                        status_code=403,
                        code="CONFIRMATION_UNAUTHORIZED",
                    )

            cur.execute(
                """
                UPDATE reports
                SET final_category = %s,
                    final_severity = COALESCE(%s, ai_severity, 'MEDIA'),
                    human_confirmed = TRUE,
                    human_override_note = %s,
                    status = CASE
                        WHEN status IN ('IN_REVIEW', 'RESOLVED', 'REJECTED') THEN status
                        ELSE 'CONFIRMED'
                    END,
                    version = COALESCE(version, 1) + 1,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (final_category, final_severity, human_override_note, rid),
            )
            row = cur.fetchone()
            if row is not None:
                try:
                    cur.execute(
                        """
                        INSERT INTO report_events (id, report_id, event_type, previous_status, new_status, public_message, actor_type)
                        VALUES (gen_random_uuid(), %s, 'CITIZEN_CONFIRMED', %s, %s, %s, 'CITIZEN');
                        """,
                        (
                            rid,
                            existing["status"],
                            row["status"],
                            f"Categoría confirmada por el ciudadano: {final_category}." + (f" Nota: {human_override_note}" if human_override_note else ""),
                        ),
                    )
                except Exception:
                    pass
            conn.commit()
            return row


def update_report_status(
    report_id: UUID | str,
    *,
    status: str,
    note: str | None = None,
) -> dict[str, Any] | None:
    rid = UUID(str(report_id))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, version FROM reports WHERE id = %s FOR UPDATE;", (rid,))
            prev = cur.fetchone()
            if not prev:
                conn.rollback()
                return None
            prev_status = prev["status"]
            prev_version = prev["version"]

            cur.execute(
                """
                UPDATE reports
                SET status = %s,
                    human_confirmed = TRUE,
                    human_override_note = COALESCE(%s, human_override_note),
                    version = COALESCE(version, 1) + 1,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (status, note, rid),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None

            new_version = row["version"]
            proposed_payload = {
                "action": "UPDATE_REPORT_STATUS",
                "previous_status": prev_status,
                "new_status": status,
                "expected_version": prev_version,
                "note": note,
            }
            result_payload = {
                "action": "UPDATE_REPORT_STATUS",
                "previous_status": prev_status,
                "status": status,
                "previous_version": prev_version,
                "version": new_version,
                "note": note,
            }

            # Auditoría administrativa síncrona obligatoria en la MISMA transacción PostgreSQL (G2.1.8)
            # Si operation_records no existe o falla el INSERT, rollback revierte el cambio del reporte
            cur.execute(
                """
                INSERT INTO operation_records (
                    operation_id, requester_id, operation_type, target_id, status,
                    proposed_payload, result_payload,
                    created_at, updated_at
                ) VALUES (
                    %s, 'admin', 'admin_update_report_status', %s, 'COMMITTED',
                    %s::jsonb, %s::jsonb,
                    clock_timestamp(), clock_timestamp()
                );
                """,
                (
                    str(uuid.uuid4()),
                    str(rid),
                    json.dumps(proposed_payload),
                    json.dumps(result_payload),
                ),
            )

            # Evento público en report_events obligatorio en la MISMA transacción (sin silenciar errores)
            cur.execute(
                """
                INSERT INTO report_events (id, report_id, event_type, previous_status, new_status, public_message, actor_type)
                VALUES (gen_random_uuid(), %s, 'STATUS_UPDATED', %s, %s, %s, 'ADMIN');
                """,
                (
                    rid,
                    prev_status,
                    status,
                    f"Estado administrativo actualizado a: {status}." + (f" Motivo: {note}" if note else ""),
                ),
            )

            cur.execute(
                """
                SELECT id, report_id, event_type, previous_status, new_status,
                       public_message, actor_type, created_at
                FROM report_events
                WHERE report_id = %s
                ORDER BY created_at ASC;
                """,
                (rid,),
            )
            row["events"] = cur.fetchall()

            conn.commit()
            return row


def list_reports(
    *,
    category: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    comuna: str | None = None,
    q: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    conditions: list[str] = []
    params: list[Any] = []

    if category:
        conditions.append("COALESCE(final_category, ai_category) = %s")
        params.append(category.upper())

    if severity:
        conditions.append("COALESCE(final_severity, ai_severity) = %s")
        params.append(severity.upper())

    if status:
        conditions.append("status = %s")
        params.append(status.upper())

    if comuna:
        c_clean = comuna.strip()
        if c_clean.isdigit():
            c_clean = f"Comuna {c_clean}"
        conditions.append(
            "(UPPER(COALESCE(comuna, '')) = UPPER(%s) OR COALESCE(neighborhood, '') ILIKE %s OR COALESCE(address_hint, '') ILIKE %s)"
        )
        like_comuna = f"%{comuna.strip()}%"
        params.extend([c_clean, like_comuna, like_comuna])

    if q:
        like_pat = f"%{q.strip()}%"
        conditions.append(
            "(title ILIKE %s OR description ILIKE %s OR COALESCE(address_hint, '') ILIKE %s OR COALESCE(neighborhood, '') ILIKE %s OR tracking_code ILIKE %s)"
        )
        params.extend([like_pat, like_pat, like_pat, like_pat, like_pat])

    distance_select = "NULL::double precision AS distance_km"
    order_clause = "created_at DESC"

    if lat is not None and lon is not None:
        # Fórmula Haversine en SQL directo (radio terrestre medio = 6371.0 km)
        haversine_expr = """
            (6371.0 * 2.0 * ASIN(SQRT(
                POWER(SIN(RADIANS(latitude - %s) / 2.0), 2) +
                COS(RADIANS(%s)) * COS(RADIANS(latitude)) *
                POWER(SIN(RADIANS(longitude - %s) / 2.0), 2)
            )))
        """
        distance_select = f"{haversine_expr} AS distance_km"
        if radius_km is not None and radius_km > 0:
            # Filtro bounding box rápido para usar el índice (latitude, longitude) antes de Haversine
            lat_delta = radius_km / 111.0
            lon_delta = radius_km / max(20.0, 111.0 * abs(__import__("math").cos(__import__("math").radians(lat))))
            conditions.append("latitude BETWEEN %s AND %s")
            params.extend([lat - lat_delta, lat + lat_delta])
            conditions.append("longitude BETWEEN %s AND %s")
            params.extend([lon - lon_delta, lon + lon_delta])
            conditions.append(f"{haversine_expr} <= %s")
            params.extend([lat, lat, lon, radius_km])
        order_clause = "distance_km ASC, created_at DESC"

    where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_conn() as conn:
        with conn.cursor() as cur:
            count_sql = f"SELECT COUNT(*) AS total FROM reports {where_sql};"
            cur.execute(count_sql, params)
            total_row = cur.fetchone()
            total = int(total_row["total"]) if total_row else 0

            select_params: list[Any] = []
            if lat is not None and lon is not None:
                select_params.extend([lat, lat, lon])
            select_params.extend(params)
            select_params.extend([limit, offset])

            query_sql = f"""
                SELECT *, {distance_select}
                FROM reports
                {where_sql}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s;
            """
            cur.execute(query_sql, select_params)
            rows = cur.fetchall()
            return total, rows


def get_reports_summary_stats() -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM reports;")
            total = int((cur.fetchone() or {}).get("total", 0))

            cur.execute(
                """
                SELECT COALESCE(final_category, ai_category, 'SIN_CLASIFICAR') AS category,
                       COUNT(*) AS count
                FROM reports
                GROUP BY 1
                ORDER BY count DESC;
                """
            )
            by_category = {r["category"]: int(r["count"]) for r in cur.fetchall()}

            cur.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM reports
                GROUP BY status
                ORDER BY count DESC;
                """
            )
            by_status = {r["status"]: int(r["count"]) for r in cur.fetchall()}

            cur.execute(
                """
                SELECT COALESCE(comuna, 'NO_ESPECIFICADA') AS comuna,
                       COUNT(*) AS count
                FROM reports
                GROUP BY 1
                ORDER BY count DESC;
                """
            )
            by_comuna = {r["comuna"]: int(r["count"]) for r in cur.fetchall()}

            return {
                "total_reports": total,
                "by_category": by_category,
                "by_status": by_status,
                "by_comuna": by_comuna,
            }


def get_report_events(report_id: UUID | str) -> list[dict[str, Any]]:
    try:
        rid = UUID(str(report_id))
    except (ValueError, TypeError):
        return []
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT id, report_id, event_type, previous_status, new_status,
                           public_message, actor_type, created_at
                    FROM report_events
                    WHERE report_id = %s
                    ORDER BY created_at ASC;
                    """,
                    (rid,),
                )
                return cur.fetchall()
            except Exception:
                return []


def list_admin_notifications(
    limit: int = 50,
    unread_only: bool = False,
    filter_type: str = "ALL",
) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE NOT is_read) AS unread_total,
                        COUNT(*) FILTER (WHERE NOT is_read AND NOT is_synthetic) AS unread_citizen,
                        COUNT(*) FILTER (WHERE NOT is_read AND is_synthetic) AS unread_synthetic
                    FROM admin_notifications;
                    """
                )
                counts = cur.fetchone() or {"total": 0, "unread_total": 0, "unread_citizen": 0, "unread_synthetic": 0}

                query = """
                    SELECT an.*,
                           r.tracking_code,
                           r.status,
                           r.neighborhood,
                           r.final_category,
                           r.ai_category,
                           r.photo_sha256
                    FROM admin_notifications an
                    JOIN reports r ON r.id = an.report_id
                    WHERE 1=1
                """
                params = []
                if unread_only:
                    query += " AND NOT an.is_read"
                if filter_type == "CITIZEN":
                    query += " AND NOT an.is_synthetic"
                elif filter_type == "SYNTHETIC":
                    query += " AND an.is_synthetic"

                query += " ORDER BY an.created_at DESC LIMIT %s;"
                params.append(limit)

                cur.execute(query, tuple(params))
                items = []
                for row in cur.fetchall():
                    report_id = str(row["report_id"])
                    photo_sha = row.get("photo_sha256")
                    photo_url = f"/api/reports/{report_id}/photo?v={photo_sha[:16]}" if photo_sha else f"/api/reports/{report_id}/photo"
                    items.append({
                        "id": row["id"],
                        "report_id": row["report_id"],
                        "tracking_code": row["tracking_code"],
                        "title": row["title"],
                        "message": row["message"],
                        "is_read": bool(row["is_read"]),
                        "is_synthetic": bool(row["is_synthetic"]),
                        "read_at": row.get("read_at"),
                        "created_at": row["created_at"],
                        "photo_url": photo_url,
                        "category": row.get("final_category") or row.get("ai_category"),
                        "status": row.get("status"),
                        "neighborhood": row.get("neighborhood"),
                    })

                return {
                    "total": int(counts["total"] or 0),
                    "unread_total": int(counts["unread_total"] or 0),
                    "unread_citizen": int(counts["unread_citizen"] or 0),
                    "unread_synthetic": int(counts["unread_synthetic"] or 0),
                    "items": items,
                }
            except Exception:
                return {"total": 0, "unread_total": 0, "unread_citizen": 0, "unread_synthetic": 0, "items": []}


def mark_admin_notification_read(notification_id: UUID | str) -> bool:
    try:
        nid = UUID(str(notification_id))
    except (ValueError, TypeError):
        return False
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    UPDATE admin_notifications
                    SET is_read = TRUE, read_at = NOW()
                    WHERE id = %s
                    RETURNING id;
                    """,
                    (nid,),
                )
                res = cur.fetchone()
                conn.commit()
                return res is not None
            except Exception:
                return False


def mark_all_admin_notifications_read() -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    UPDATE admin_notifications
                    SET is_read = TRUE, read_at = NOW()
                    WHERE NOT is_read;
                    """
                )
                count = cur.rowcount
                conn.commit()
                return count
            except Exception:
                return 0


def update_report_management(
    report_id: UUID | str,
    *,
    assigned_to: str | None = None,
    admin_review_status: str | None = None,
    public_note: str | None = None,
    internal_note: str | None = None,
) -> dict[str, Any] | None:
    try:
        rid = UUID(str(report_id))
    except (ValueError, TypeError):
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM reports WHERE id = %s FOR UPDATE;", (rid,))
            existing = cur.fetchone()
            if not existing:
                conn.rollback()
                return None

            updates = []
            params = []
            if assigned_to is not None:
                updates.append("assigned_to = %s, assigned_at = NOW()")
                params.append(assigned_to.strip() or None)
            if admin_review_status is not None:
                updates.append("admin_review_status = %s")
                params.append(admin_review_status)
            if public_note is not None:
                updates.append("last_public_note = %s")
                params.append(public_note.strip() or None)
            if internal_note is not None:
                updates.append("admin_internal_notes = %s")
                params.append(internal_note.strip() or None)

            if updates:
                updates.append("updated_at = NOW()")
                params.append(rid)
                query = f"UPDATE reports SET {', '.join(updates)} WHERE id = %s RETURNING *;"
                cur.execute(query, tuple(params))
                updated_row = cur.fetchone()

                # Evento público si se asigna a una dependencia (sin silenciar errores)
                if assigned_to is not None and assigned_to.strip() and assigned_to.strip() != (existing.get("assigned_to") or ""):
                    cur.execute(
                        """
                        INSERT INTO report_events (id, report_id, event_type, previous_status, new_status, public_message, actor_type)
                        VALUES (gen_random_uuid(), %s, 'ASSIGNED_TO_DEPARTMENT', %s, %s, %s, 'ADMIN');
                        """,
                        (rid, existing["status"], existing["status"], f"Reporte asignado a la dependencia competente: {assigned_to.strip()}."),
                    )

                # Evento público si se añade una observación pública de seguimiento
                if public_note is not None and public_note.strip() and public_note.strip() != (existing.get("last_public_note") or ""):
                    cur.execute(
                        """
                        INSERT INTO report_events (id, report_id, event_type, previous_status, new_status, public_message, actor_type)
                        VALUES (gen_random_uuid(), %s, 'PUBLIC_NOTE_ADDED', %s, %s, %s, 'ADMIN');
                        """,
                        (rid, existing["status"], existing["status"], f"Observación de seguimiento: {public_note.strip()}."),
                    )

                # NOTA DE SEGURIDAD: internal_note NUNCA genera evento público para preservar la confidencialidad interna

                cur.execute(
                    """
                    SELECT id, report_id, event_type, previous_status, new_status,
                           public_message, actor_type, created_at
                    FROM report_events
                    WHERE report_id = %s
                    ORDER BY created_at ASC;
                    """,
                    (rid,),
                )
                if updated_row is not None:
                    updated_row["events"] = cur.fetchall()

                conn.commit()
                return updated_row
            return existing
