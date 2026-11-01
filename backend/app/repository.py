import json
from typing import Any
from uuid import UUID
import uuid

from app.db import get_conn

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
        "title": row["title"],
        "description": row["description"],
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "in_service_area": bool(row["in_service_area"]),
        "comuna": row.get("comuna"),
        "neighborhood": row.get("neighborhood"),
        "address_hint": row.get("address_hint"),
        "photo_url": f"/api/reports/{report_id}/photo",
        "photo_mime": row["photo_mime"],
        "photo_width": int(row["photo_width"]),
        "photo_height": int(row["photo_height"]),
        "has_audio": bool(row.get("audio_path")),
        "audio_transcript": row.get("audio_transcript"),
        "ai_category": row.get("ai_category"),
        "ai_severity": row.get("ai_severity"),
        "ai_confidence": float(row["ai_confidence"]) if row.get("ai_confidence") is not None else None,
        "ai_summary": row.get("ai_summary"),
        "ai_keywords": ai_keywords,
        "final_category": row.get("final_category"),
        "final_severity": row.get("final_severity"),
        "effective_category": effective_cat,
        "effective_severity": effective_sev,
        "human_confirmed": bool(row["human_confirmed"]),
        "human_override_note": row.get("human_override_note"),
        "status": status,
        "status_message": STATUS_MESSAGES.get(status, "Reporte registrado."),
        "distance_km": round(float(dist), 3) if dist is not None else None,
        "is_synthetic": bool(row.get("is_synthetic", False)),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def generate_tracking_code(report_uuid: UUID) -> str:
    short = report_uuid.hex[:8].upper()
    return f"CIV-2026-{short}"


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
) -> dict[str, Any]:
    rid = report_id or uuid.uuid4()
    tcode = tracking_code or generate_tracking_code(rid)
    am = audio_meta or {}

    with get_conn() as conn:
        with conn.cursor() as cur:
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
                    status, is_synthetic
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    'PENDING_ANALYSIS', %s
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
                ),
            )
            row = cur.fetchone()
            conn.commit()
            assert row is not None
            return row


def get_report_raw(report_id: UUID | str) -> dict[str, Any] | None:
    try:
        rid = UUID(str(report_id))
    except ValueError:
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM reports WHERE id = %s;", (rid,))
            return cur.fetchone()


def get_report_by_tracking_code(tracking_code: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM reports WHERE UPPER(tracking_code) = UPPER(%s);",
                (tracking_code.strip(),),
            )
            return cur.fetchone()


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
            conn.commit()
            return row


def confirm_report_category(
    report_id: UUID | str,
    *,
    final_category: str,
    final_severity: str | None = None,
    human_override_note: str | None = None,
) -> dict[str, Any] | None:
    rid = UUID(str(report_id))
    with get_conn() as conn:
        with conn.cursor() as cur:
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
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (final_category, final_severity, human_override_note, rid),
            )
            row = cur.fetchone()
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
            cur.execute(
                """
                UPDATE reports
                SET status = %s,
                    human_override_note = COALESCE(%s, human_override_note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (status, note, rid),
            )
            row = cur.fetchone()
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
        conditions.append("UPPER(COALESCE(comuna, '')) = UPPER(%s)")
        params.append(comuna.strip())

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
