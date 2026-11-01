import json
import math
import re
from typing import Any
from uuid import UUID
import uuid

from app.db import get_conn

# Tarifas de referencia documentadas (USD por 1M de tokens) para estimación transparente de costos
MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gemini-3.8-flash": (0.15, 0.60),
    "gemini-3.6-flash": (0.10, 0.40),
    "qwen/qwen3.8-27b": (0.20, 0.60),
    "whisper-large-v3-turbo": (0.04, 0.04),
}

_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"gsk_[0-9A-Za-z]{20,}"),
    re.compile(r"Bearer\s+[0-9A-Za-z\-_\.]+", re.IGNORECASE),
    re.compile(r"key=[0-9A-Za-z\-_]+", re.IGNORECASE),
]


def sanitize_secret_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = str(text)
    for pat in _SECRET_PATTERNS:
        cleaned = pat.sub("[CREDENCIAL_REDACTADA]", cleaned)
    return cleaned[:600]


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_rate, out_rate = MODEL_PRICING_PER_1M.get(model, (0.15, 0.60))
    cost = (max(0, prompt_tokens) * in_rate + max(0, completion_tokens) * out_rate) / 1_000_000.0
    return round(cost, 8)


def record_ai_trace(
    *,
    trace_group_id: UUID,
    operation: str,
    provider: str,
    model: str,
    attempt_number: int,
    success: bool,
    latency_ms: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    report_id: UUID | str | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> UUID:
    trace_id = uuid.uuid4()
    rid = UUID(str(report_id)) if report_id else None
    total_tokens = max(0, prompt_tokens) + max(0, completion_tokens)
    cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)
    safe_error_detail = sanitize_secret_text(error_detail)
    safe_error_code = sanitize_secret_text(error_code)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_traces (
                    id, report_id, trace_group_id, operation,
                    provider, model, attempt_number, success,
                    latency_ms, prompt_tokens, completion_tokens,
                    total_tokens, estimated_cost_usd,
                    error_code, error_detail, tool_calls, metadata
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s::jsonb, %s::jsonb
                );
                """,
                (
                    trace_id,
                    rid,
                    trace_group_id,
                    operation,
                    provider,
                    model,
                    attempt_number,
                    success,
                    max(0, int(latency_ms)),
                    max(0, int(prompt_tokens)),
                    max(0, int(completion_tokens)),
                    total_tokens,
                    cost,
                    safe_error_code,
                    safe_error_detail,
                    json.dumps(tool_calls or [], ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
    return trace_id


def _percentile(sorted_vals: list[int], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    idx = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(sorted_vals[lo])
    frac = idx - lo
    return round(sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo]), 2)


def get_observability_summary(limit: int = 80) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM ai_traces
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            traces = cur.fetchall()

            cur.execute("SELECT latency_ms, success, total_tokens, estimated_cost_usd, provider, model FROM ai_traces;")
            all_rows = cur.fetchall()

    latencies = sorted(int(r["latency_ms"]) for r in all_rows)
    ok_latencies = sorted(int(r["latency_ms"]) for r in all_rows if r["success"])
    total_calls = len(all_rows)
    success_calls = sum(1 for r in all_rows if r["success"])
    total_tokens = sum(int(r["total_tokens"]) for r in all_rows)
    total_cost = round(sum(float(r["estimated_cost_usd"]) for r in all_rows), 6)

    by_provider: dict[str, dict[str, Any]] = {}
    for r in all_rows:
        key = f"{r['provider']}:{r['model']}"
        entry = by_provider.setdefault(
            key,
            {"provider": r["provider"], "model": r["model"], "calls": 0, "successes": 0, "failures": 0, "tokens": 0},
        )
        entry["calls"] += 1
        if r["success"]:
            entry["successes"] += 1
        else:
            entry["failures"] += 1
        entry["tokens"] += int(r["total_tokens"])

    return {
        "metrics": {
            "total_trace_events": total_calls,
            "successful_events": success_calls,
            "failed_events": total_calls - success_calls,
            "success_rate_pct": round((success_calls / total_calls) * 100.0, 2) if total_calls else 0.0,
            "p50_latency_ms": _percentile(latencies, 50.0),
            "p90_latency_ms": _percentile(latencies, 90.0),
            "p50_success_latency_ms": _percentile(ok_latencies, 50.0),
            "p90_success_latency_ms": _percentile(ok_latencies, 90.0),
            "total_tokens": total_tokens,
            "total_estimated_cost_usd": total_cost,
            "avg_cost_per_event_usd": round(total_cost / total_calls, 6) if total_calls else 0.0,
        },
        "by_provider_model": list(by_provider.values()),
        "recent_traces": traces,
    }
