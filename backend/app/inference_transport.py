"""Fixed inference routes and shared reservation limits for actual provider calls."""

import json
import hashlib
import re
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.db import get_conn, get_deadline_context

_GOOGLE_ORIGIN = "https://generativelanguage.googleapis.com"
_GROQ_CHAT = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_AUDIO = "https://api.groq.com/openai/v1/audio/transcriptions"
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_GOOGLE_PATH = re.compile(r"/v1beta/models/[A-Za-z0-9][A-Za-z0-9._-]{0,127}:generateContent\Z")
_RESPONSE_LIMIT = 256 * 1024


class InferenceQuotaExceeded(Exception):
    pass


class ModelPreflightRequired(Exception):
    pass


def _credential_digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def record_capability(provider: str, model: str, capability: str, key: str, passed: bool) -> None:
    with get_conn(statement_timeout_ms=2000) as conn:
        if passed:
            conn.execute(
                """
                INSERT INTO ai_validated_models (provider, model, capability, credential_fingerprint)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (provider, model, capability)
                DO UPDATE SET credential_fingerprint = EXCLUDED.credential_fingerprint, validated_at = now()
                """,
                (provider, model, capability, _credential_digest(key)),
            )
        else:
            conn.execute(
                """
                DELETE FROM ai_validated_models
                WHERE provider = %s AND model = %s AND capability = %s AND credential_fingerprint = %s
                """,
                (provider, model, capability, _credential_digest(key)),
            )
        conn.commit()


def gemini_url(model: str) -> str:
    if not _MODEL_NAME.fullmatch(model):
        raise ValueError("Identificador de modelo Gemini inválido.")
    return f"{_GOOGLE_ORIGIN}/v1beta/models/{model}:generateContent"


def _reserve(provider: str, tokens: int) -> None:
    now = datetime.now(timezone.utc)
    minute = now.replace(second=0, microsecond=0)
    day = minute.replace(hour=0, minute=0)
    scopes = (
        ("system-day", day, settings.AI_DAILY_REQUESTS, settings.AI_DAILY_TOKENS),
        (f"{provider}-minute", minute, settings.AI_PROVIDER_RPM, settings.AI_PROVIDER_TPM),
    )
    with get_conn() as conn, conn.cursor() as cur:
        for scope, start, call_limit, token_limit in scopes:
            cur.execute(
                """
                INSERT INTO ai_quota_windows (scope, window_start, calls, estimated_tokens)
                SELECT %s, %s, 1, %s WHERE %s >= 1 AND %s >= %s
                ON CONFLICT (scope, window_start) DO UPDATE
                SET calls = ai_quota_windows.calls + 1,
                    estimated_tokens = ai_quota_windows.estimated_tokens + EXCLUDED.estimated_tokens
                WHERE ai_quota_windows.calls < %s
                  AND ai_quota_windows.estimated_tokens + EXCLUDED.estimated_tokens <= %s
                RETURNING calls
                """,
                (scope, start, tokens, call_limit, token_limit, tokens, call_limit, token_limit),
            )
            if cur.fetchone() is None:
                raise InferenceQuotaExceeded(scope)
        cur.execute("DELETE FROM ai_quota_windows WHERE window_start < %s - interval '2 days'", (day,))
        conn.commit()


def post_inference(
    url: str,
    *,
    timeout: float,
    headers: dict[str, str],
    payload: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
    reserve: bool = True,
    capability: str = "text",
) -> httpx.Response:
    target = httpx.URL(url)
    if url in (_GROQ_CHAT, _GROQ_AUDIO):
        provider = "groq"
    elif (
        target.scheme == "https"
        and target.netloc == b"generativelanguage.googleapis.com"
        and not target.userinfo
        and not target.query
        and not target.fragment
        and _GOOGLE_PATH.fullmatch(target.path)
    ):
        provider = "google"
    else:
        raise ValueError("Destino de inferencia fuera de la configuración permitida.")

    started = time.monotonic()
    deadline = min(started + timeout, get_deadline_context() or float("inf"))
    if reserve:
        if settings.AI_REQUIRE_PREFLIGHT:
            if provider == "google":
                model = target.path.rsplit("/", 1)[-1].removesuffix(":generateContent")
                key = headers["x-goog-api-key"]
            else:
                model = (payload or data or {})["model"]
                key = headers["Authorization"].removeprefix("Bearer ")
            with get_conn(statement_timeout_ms=1000) as conn:
                valid = conn.execute(
                    """
                    SELECT 1 FROM ai_validated_models
                    WHERE provider = %s AND model = %s AND capability = %s AND credential_fingerprint = %s
                    """,
                    (provider, model, capability, _credential_digest(key)),
                ).fetchone()
            if not valid:
                raise ModelPreflightRequired()

        # El tamaño base64 de una foto no corresponde a tokens de texto.
        estimate = json.dumps(payload or data or {}, ensure_ascii=False)
        estimate = re.sub(r"(?<=base64,)[A-Za-z0-9+/=]+|\"data\": \"[A-Za-z0-9+/=]+\"", "", estimate)
        output = (payload or {}).get("max_tokens") or (payload or {}).get("generationConfig", {}).get("maxOutputTokens", 0)
        _reserve(provider, min(len(estimate.encode("utf-8")), 100_000) + int(output) + (2400 if files or len(estimate) > 5000 else 1200))

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise httpx.ReadTimeout("Plazo de inferencia agotado.")
    with httpx.Client(
        timeout=httpx.Timeout(remaining, connect=min(4.0, remaining)),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        with client.stream("POST", url, headers=headers, json=payload, data=data, files=files) as response:
            # Para errores solo hacen falta el código y las cabeceras de reintento.
            if response.status_code != 200:
                return httpx.Response(response.status_code, headers=response.headers)
            content = bytearray()
            for chunk in response.iter_bytes(chunk_size=8192):
                content.extend(chunk)
                if len(content) > _RESPONSE_LIMIT:
                    raise httpx.DecodingError("Respuesta de inferencia demasiado grande.")
                if time.monotonic() >= deadline:
                    raise httpx.ReadTimeout("Plazo de inferencia agotado.")
            return httpx.Response(response.status_code, headers={}, content=bytes(content))
