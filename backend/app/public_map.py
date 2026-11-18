from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.db import get_conn
from app.schemas import ReportCategory, ReportSeverity

router = APIRouter(prefix="/api/public/reports", tags=["Mapa público"])


class MapPoint(BaseModel):
    latitude: float
    longitude: float
    category: ReportCategory | None
    severity: ReportSeverity | None
    status: Literal["CONFIRMED", "IN_REVIEW", "RESOLVED"]


class MapPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[MapPoint]


_VISIBLE = "status IN ('CONFIRMED', 'IN_REVIEW', 'RESOLVED')"


@router.get("", response_model=MapPage)
def map_reports(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0, le=1_000_000)) -> MapPage:
    with get_conn(3000) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM reports WHERE {_VISIBLE};")
        total = cur.fetchone()["total"]
        cur.execute(
            f"""
            SELECT ROUND(latitude::numeric, 2) AS latitude, ROUND(longitude::numeric, 2) AS longitude,
                   COALESCE(final_category, ai_category) AS category,
                   COALESCE(final_severity, ai_severity) AS severity, status
            FROM reports WHERE {_VISIBLE}
            ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s;
            """,
            (limit, offset),
        )
        return MapPage(total=total, limit=limit, offset=offset, items=cur.fetchall())


@router.get("/stats")
def map_stats() -> dict:
    with get_conn(3000) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT status, COALESCE(final_category, ai_category, 'SIN_CATEGORIA') AS category,
                   COALESCE(final_severity, ai_severity, 'SIN_SEVERIDAD') AS severity, COUNT(*) AS count
            FROM reports WHERE {_VISIBLE}
            GROUP BY status, category, severity;
            """
        )
        total = 0
        counts: dict[str, dict[str, int]] = {"by_status": {}, "by_category": {}, "by_severity": {}}
        for row in cur.fetchall():
            total += row["count"]
            for column in ("status", "category", "severity"):
                bucket = counts[f"by_{column}"]
                key = row[column]
                bucket[key] = bucket.get(key, 0) + row["count"]
        return {"total": total, **counts}
