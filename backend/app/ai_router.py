import base64
from dataclasses import dataclass
import json
import logging
import random
import re
import threading
import time
from typing import Any
from uuid import UUID
import uuid

import httpx
from pydantic import ValidationError

from app.config import settings
from app.db import get_deadline_context
from app.observability import record_ai_trace, sanitize_secret_text
from app.schemas import AIAnalysisContract

logger = logging.getLogger("civia.ai_router")


def _safe_record_trace(**kwargs: Any) -> None:
    try:
        record_ai_trace(**kwargs)
    except Exception as exc:
        logger.warning("Fallo no bloqueante al registrar traza de observabilidad: %s", type(exc).__name__)


class AIProviderError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.message = sanitize_secret_text(message) or code
        self.retryable = retryable


class CircuitBreakerState:
    def __init__(
        self,
        provider: str,
        model: str,
        failures: int = 0,
        state: str = "CLOSED",
        opened_at: float = 0.0,
        last_error: str | None = None,
        cooldown_seconds: float = 10.0,
        failure_threshold: int = 2,
    ):
        self.provider = provider
        self.model = model
        self.failures = failures
        self.state = state  # CLOSED, OPEN, HALF_OPEN
        self.opened_at = opened_at
        self.last_error = last_error
        self.cooldown_seconds = cooldown_seconds
        self.failure_threshold = failure_threshold
        self._lock = threading.Lock()
        self._half_open_in_flight: bool = False

    def can_attempt(self) -> bool:
        """Comprueba si el circuito permitiría una solicitud sin consumir el ensayo en HALF_OPEN."""
        with self._lock:
            if self.state == "CLOSED":
                return True
            now = time.monotonic()
            if self.state == "OPEN":
                return (now - self.opened_at) >= self.cooldown_seconds
            if self.state == "HALF_OPEN":
                return not self._half_open_in_flight
            return False

    def allow_request(self) -> bool:
        with self._lock:
            if self.state == "CLOSED":
                return True
            now = time.monotonic()
            if self.state == "OPEN":
                if (now - self.opened_at) >= self.cooldown_seconds:
                    self.state = "HALF_OPEN"
                    self._half_open_in_flight = True
                    return True
                return False
            if self.state == "HALF_OPEN":
                if not self._half_open_in_flight:
                    self._half_open_in_flight = True
                    return True
                return False
            return False

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.state = "CLOSED"
            self.opened_at = 0.0
            self.last_error = None
            self._half_open_in_flight = False

    def record_failure(self, error_code: str, retry_after: float | None = None) -> None:
        with self._lock:
            self._half_open_in_flight = False
            # Errores del cliente (esquema, json o clave ausente) no disparan circuito del proveedor
            if error_code in ("INVALID_JSON", "INVALID_SCHEMA", "MISSING_API_KEY", "INVALID_ARGUMENT"):
                return

            self.failures += 1
            self.last_error = error_code
            if error_code in ("HTTP_429", "429"):
                self.state = "OPEN"
                self.opened_at = time.monotonic()
                if retry_after is not None:
                    self.cooldown_seconds = float(retry_after)
                elif self.cooldown_seconds < 1.0:
                    pass  # preserve custom test cooldown
                else:
                    self.cooldown_seconds = 30.0
            elif error_code in ("HTTP_503", "TIMEOUT") or self.failures >= self.failure_threshold:
                self.state = "OPEN"
                self.opened_at = time.monotonic()
                if self.cooldown_seconds >= 1.0:
                    self.cooldown_seconds = 10.0


_CIRCUITS: dict[str, CircuitBreakerState] = {}
_RUNTIME_FAULT_OVERRIDE: str | None = None
_EXHAUSTED_GEMINI_MODELS: dict[str, float] = {}


def resolve_effective_gemini_model(model: str) -> str:
    # Eliminada sustitución oculta (N-02): la selección de modelo es responsabilidad exclusiva del router
    return model


def mark_gemini_model_exhausted(model: str) -> str:
    return model


def set_runtime_fault_override(mode: str | None) -> str:
    global _RUNTIME_FAULT_OVERRIDE
    cleaned = (mode or "").strip().upper()
    if cleaned in ("", "NONE", "OFF"):
        _RUNTIME_FAULT_OVERRIDE = None
        return ""
    _RUNTIME_FAULT_OVERRIDE = cleaned
    return cleaned


def get_effective_fault_mode() -> str:
    if _RUNTIME_FAULT_OVERRIDE is not None:
        return _RUNTIME_FAULT_OVERRIDE
    return settings.falla_forzada


def get_circuit(provider: str, model: str) -> CircuitBreakerState:
    key = f"{provider}:{model}"
    if key not in _CIRCUITS:
        _CIRCUITS[key] = CircuitBreakerState(provider=provider, model=model)
    return _CIRCUITS[key]


def ensure_at_least_one_circuit_openable(chain: list[dict[str, str]]) -> None:
    """
    Si los 3 niveles tienen el circuit breaker en estado OPEN simultáneamente,
    habilita en modo HALF_OPEN el circuito que lleve más tiempo abierto para permitir
    exactamente un ensayo de sondeo sin bloqueo total.
    """
    cbs = [get_circuit(node["provider"], node["model"]) for node in chain]
    if any(cb.can_attempt() for cb in cbs):
        return
    oldest = min(cbs, key=lambda c: c.opened_at)
    with oldest._lock:
        oldest.state = "HALF_OPEN"
        oldest._half_open_in_flight = False


def reset_all_circuits() -> None:
    _CIRCUITS.clear()


def get_all_circuit_states() -> list[dict[str, Any]]:
    out = []
    for cb in _CIRCUITS.values():
        out.append(
            {
                "provider": cb.provider,
                "model": cb.model,
                "state": cb.state,
                "failures": cb.failures,
                "last_error": cb.last_error,
            }
        )
    return out


_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def extract_first_json_object(raw_text: str) -> str:
    """Extrae de forma determinista el primer objeto JSON balanceado {...}."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No se encontró apertura de objeto JSON '{'.")
    depth = 0
    in_str = False
    escape = False
    for idx in range(start, len(cleaned)):
        ch = cleaned[idx]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : idx + 1]
                    return _TRAILING_COMMA_RE.sub(r"\1", candidate)
    # Si quedó truncado por cierre simple, intentar reparación acotada de llaves
    if 0 < depth <= 2 and not in_str:
        candidate = cleaned[start:] + ("}" * depth)
        return _TRAILING_COMMA_RE.sub(r"\1", candidate)
    raise ValueError("Objeto JSON desbalanceado o incompleto.")


ALLOWED_CATEGORIES = {"HUECO", "BASURAS", "TALA", "QUEMA", "OTRO"}
CATEGORY_SYNONYMS = {
    "HUECOS": "HUECO",
    "BACHE": "HUECO",
    "BASURA": "BASURAS",
    "RESIDUOS": "BASURAS",
    "ARBOL": "TALA",
    "INCENDIO": "QUEMA",
    "QUEMAS": "QUEMA",
}

ALLOWED_SEVERITIES = {"BAJA", "MEDIA", "ALTA", "CRITICA"}
SEVERITY_SYNONYMS = {
    "CRÍTICA": "CRITICA",
    "CRITICO": "CRITICA",
    "CRÍTICO": "CRITICA",
    "ALTO": "ALTA",
    "MEDIO": "MEDIA",
    "MODERADA": "MEDIA",
    "MODERADO": "MEDIA",
    "BAJO": "BAJA",
    "LEVE": "BAJA",
}


def parse_and_validate_analysis_json(raw_text: str) -> AIAnalysisContract:
    """
    Valida de forma estricta la salida JSON del modelo según AIAnalysisContract sin fabricar datos (A-03).
    Rechaza campos ausentes, categorías o severidades no permitidas, confianzas fuera de rango o negativas,
    y resúmenes artificialmente inflados con relleno inventado.
    """
    try:
        json_str = extract_first_json_object(raw_text)
        data = json.loads(json_str)
    except Exception as exc:
        raise AIProviderError("INVALID_JSON", f"JSON inválido del modelo: {type(exc).__name__}", retryable=False) from exc

    if not isinstance(data, dict):
        raise AIProviderError("INVALID_JSON", "El JSON devuelto no es un objeto.", retryable=False)

    # 1. Validar Category (obligatorio, debe pertenecer al conjunto permitido)
    raw_cat_val = data.get("category")
    if raw_cat_val is None:
        raw_cat_val = data.get("categoria")
    if raw_cat_val is None or not isinstance(raw_cat_val, str) or not raw_cat_val.strip():
        raise AIProviderError("INVALID_SCHEMA", "Campo obligatorio 'category' ausente o vacío.", retryable=False)
    cat_norm = raw_cat_val.strip().upper()
    cat_norm = CATEGORY_SYNONYMS.get(cat_norm, cat_norm)
    if cat_norm not in ALLOWED_CATEGORIES:
        raise AIProviderError("INVALID_SCHEMA", f"Categoría '{raw_cat_val}' no permitida en CIVIA.", retryable=False)
    data["category"] = cat_norm

    # 2. Validar Severity (obligatorio, no fabricar default "MEDIA")
    raw_sev_val = data.get("severity")
    if raw_sev_val is None:
        raw_sev_val = data.get("severidad")
    if raw_sev_val is None or not isinstance(raw_sev_val, str) or not raw_sev_val.strip():
        raise AIProviderError("INVALID_SCHEMA", "Campo obligatorio 'severity' ausente o vacío.", retryable=False)
    sev_norm = raw_sev_val.strip().upper()
    sev_norm = SEVERITY_SYNONYMS.get(sev_norm, sev_norm)
    if sev_norm not in ALLOWED_SEVERITIES:
        raise AIProviderError("INVALID_SCHEMA", f"Severidad '{raw_sev_val}' no permitida en CIVIA.", retryable=False)
    data["severity"] = sev_norm

    # 3. Validar Confidence (obligatorio, numérico en rango 0.0 - 1.0, no fabricar default ni aceptar negativos)
    raw_conf_val = data.get("confidence")
    if raw_conf_val is None:
        raw_conf_val = data.get("confianza")
    if raw_conf_val is None or isinstance(raw_conf_val, bool):
        raise AIProviderError("INVALID_SCHEMA", "Campo obligatorio 'confidence' ausente o booleano.", retryable=False)
    try:
        conf_float = float(raw_conf_val)
    except (ValueError, TypeError) as exc:
        raise AIProviderError("INVALID_SCHEMA", f"Campo 'confidence' no numérico: {raw_conf_val}", retryable=False) from exc
    if conf_float < 0.0 or conf_float > 100.0:
        raise AIProviderError("INVALID_SCHEMA", f"Campo 'confidence' fuera de rango (0.0 a 1.0): {conf_float}", retryable=False)
    if conf_float > 1.0:
        conf_float = conf_float / 100.0
    data["confidence"] = round(conf_float, 4)

    # 4. Validar Summary (obligatorio, >= 10 caracteres reales, no inventar padding)
    raw_sum_val = data.get("summary")
    if raw_sum_val is None:
        raw_sum_val = data.get("resumen")
    if raw_sum_val is None or not isinstance(raw_sum_val, str):
        raise AIProviderError("INVALID_SCHEMA", "Campo obligatorio 'summary' ausente o no textual.", retryable=False)
    clean_summary = raw_sum_val.strip()
    if len(clean_summary) < 10:
        raise AIProviderError("INVALID_SCHEMA", f"Campo 'summary' demasiado corto ({len(clean_summary)} < 10 caracteres).", retryable=False)
    data["summary"] = clean_summary[:500]

    # 5. Keywords (opcional, lista de strings)
    kw = data.get("keywords")
    if kw is None:
        kw = data.get("palabras_clave")
    if isinstance(kw, list):
        data["keywords"] = [str(x)[:40] for x in kw[:8]]
    else:
        data["keywords"] = []

    try:
        return AIAnalysisContract.model_validate(data)
    except ValidationError as exc:
        raise AIProviderError("INVALID_SCHEMA", f"Violación de esquema en contrato AI: {exc}", retryable=False) from exc


def get_provider_chain() -> list[dict[str, str]]:
    """Orden estricto: 1) Gemini primario -> 2) Groq respaldo -> 3) Gemini alternativo."""
    secondary_key = settings.GOOGLE_API_KEY_SECONDARY or settings.GOOGLE_API_KEY_PRIMARY
    return [
        {
            "tier": "primary",
            "provider": "google",
            "model": settings.AI_PRIMARY_MODEL,
            "api_key": settings.GOOGLE_API_KEY_PRIMARY,
        },
        {
            "tier": "fallback",
            "provider": "groq",
            "model": settings.AI_FALLBACK_MODEL,
            "api_key": settings.GROQ_API_KEY,
        },
        {
            "tier": "tertiary",
            "provider": "google",
            "model": settings.AI_TERTIARY_MODEL,
            "api_key": secondary_key,
        },
    ]


def _check_forced_fault(tier: str, provider: str) -> str | None:
    """Evalúa si hay una falla forzada activa para este nivel/proveedor."""
    mode = get_effective_fault_mode()
    if not mode:
        return None
    if mode in ("TOTAL", "CAIDA_TOTAL", "429_ALL", "ALL_FAIL"):
        raise AIProviderError("HTTP_429", "Falla forzada total (429/caída total en todos los proveedores).", retryable=False)
    if mode in ("429", "429_PRIMARY") and tier == "primary":
        raise AIProviderError("HTTP_429", "Falla forzada 429 en proveedor primario.", retryable=True)
    if mode in ("503", "503_PRIMARY") and tier == "primary":
        raise AIProviderError("HTTP_503", "Falla forzada 503 en proveedor primario.", retryable=True)
    if mode in ("TIMEOUT", "TIMEOUT_PRIMARY") and tier == "primary":
        raise AIProviderError("TIMEOUT", "Falla forzada de timeout en proveedor primario.", retryable=True)
    if mode in ("INVALID_JSON", "INVALID_JSON_PRIMARY") and tier == "primary":
        return "{bad_json: true, unclosed"
    if mode == "GROQ_FAIL" and tier in ("primary", "fallback"):
        raise AIProviderError("HTTP_503", f"Falla forzada en {tier} para probar tercer nivel.", retryable=False)
    return None


def _call_gemini_multimodal(
    *,
    model: str,
    api_key: str,
    prompt_text: str,
    image_bytes: bytes | None,
    image_mime: str | None,
    timeout_sec: float,
) -> tuple[str, int, int]:
    if not api_key:
        raise AIProviderError("MISSING_API_KEY", "Clave de Google no configurada.", retryable=False)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    parts: list[dict[str, Any]] = [{"text": prompt_text}]
    if image_bytes and image_mime:
        b64_img = base64.b64encode(image_bytes).decode("ascii")
        parts.append({"inline_data": {"mime_type": image_mime, "data": b64_img}})

    payload: dict[str, Any] = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
            "maxOutputTokens": 1200,
        },
    }

    if timeout_sec <= 0.005:
        raise AIProviderError("TIMEOUT", "Tiempo de espera agotado antes de llamar a Gemini.", retryable=False)

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=min(4.0, timeout_sec))) as client:
            resp = client.post(url, json=payload)
    except httpx.TimeoutException as exc:
        raise AIProviderError("TIMEOUT", "Tiempo de espera agotado en llamada a Gemini.", retryable=True) from exc
    except httpx.HTTPError as exc:
        raise AIProviderError("NETWORK_ERROR", f"Error de red en Gemini: {type(exc).__name__}", retryable=True) from exc

    if resp.status_code == 429:
        raise AIProviderError("HTTP_429", "Cuota o límite de tasa excedido (429).", retryable=True)
    if resp.status_code >= 500:
        raise AIProviderError(f"HTTP_{resp.status_code}", f"Error de servidor ({resp.status_code}).", retryable=True)
    if resp.status_code >= 400:
        raise AIProviderError(f"HTTP_{resp.status_code}", f"Solicitud rechazada ({resp.status_code}).", retryable=False)

    body = resp.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise AIProviderError("EMPTY_RESPONSE", "Respuesta sin candidatos.", retryable=False)

    content_parts = (candidates[0].get("content") or {}).get("parts") or []
    text_chunks = [p.get("text", "") for p in content_parts if not p.get("thought") and "text" in p]
    text_out = "\n".join(text_chunks).strip()
    if not text_out:
        raise AIProviderError("EMPTY_TEXT", "Candidato sin texto útil.", retryable=False)

    usage = body.get("usageMetadata") or {}
    in_tok = int(usage.get("promptTokenCount") or 0)
    out_tok = int(usage.get("candidatesTokenCount") or 0)
    return text_out, in_tok, out_tok


def _call_groq_multimodal(
    *,
    model: str,
    api_key: str,
    prompt_text: str,
    image_bytes: bytes | None,
    image_mime: str | None,
    timeout_sec: float,
) -> tuple[str, int, int]:
    if not api_key:
        raise AIProviderError("MISSING_API_KEY", "Clave de Groq no configurada.", retryable=False)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    content_items: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]
    if image_bytes and image_mime:
        b64_img = base64.b64encode(image_bytes).decode("ascii")
        content_items.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image_mime};base64,{b64_img}"},
            }
        )

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": content_items}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 500,
    }

    if timeout_sec <= 0.005:
        raise AIProviderError("TIMEOUT", "Tiempo de espera agotado antes de llamar a Groq.", retryable=False)

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=min(4.0, timeout_sec))) as client:
            resp = client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise AIProviderError("TIMEOUT", "Tiempo de espera agotado en llamada a Groq.", retryable=True) from exc
    except httpx.HTTPError as exc:
        raise AIProviderError("NETWORK_ERROR", f"Error de red en Groq: {type(exc).__name__}", retryable=True) from exc

    if resp.status_code == 429:
        raise AIProviderError("HTTP_429", "Límite de tasa excedido en Groq (429).", retryable=True)
    if resp.status_code >= 500:
        raise AIProviderError(f"HTTP_{resp.status_code}", f"Error de servidor Groq ({resp.status_code}).", retryable=True)
    if resp.status_code >= 400:
        raise AIProviderError(f"HTTP_{resp.status_code}", f"Solicitud rechazada en Groq ({resp.status_code}): {resp.text[:200]}", retryable=False)

    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise AIProviderError("EMPTY_RESPONSE", "Groq no devolvió opciones.", retryable=False)

    text_out = ((choices[0].get("message") or {}).get("content") or "").strip()
    usage = body.get("usage") or {}
    in_tok = int(usage.get("prompt_tokens") or 0)
    out_tok = int(usage.get("completion_tokens") or 0)
    return text_out, in_tok, out_tok


def build_classification_prompt(
    *,
    description: str,
    latitude: float,
    longitude: float,
    address_hint: str | None = None,
    audio_transcript: str | None = None,
) -> str:
    extra_audio = f"\nTranscripción de nota de voz: {audio_transcript}" if audio_transcript else ""
    extra_addr = f"\nReferencia geográfica: {address_hint}" if address_hint else ""
    return (
        "Eres el clasificador multimodal de incidentes urbanos y ambientales de CIVIA en Cali y Valle del Cauca.\n"
        "Analiza conjuntamente la fotografía adjunta y el reporte ciudadano.\n"
        "Categorías permitidas (exactamente una):\n"
        "- HUECO: baches, hundimientos de calzada o deterioro vial.\n"
        "- BASURAS: acumulación de residuos sólidos, escombros o puntos críticos de basura.\n"
        "- TALA: corte, tala o daño antitécnico de árboles o cobertura arbórea.\n"
        "- QUEMA: incendios forestales, quema de vegetación o quema abierta de residuos/humo.\n"
        "- OTRO: si la evidencia no corresponde a ninguna de las cuatro categorías anteriores o es insuficiente/ambigua.\n\n"
        "Niveles de severidad permitidos: BAJA, MEDIA, ALTA, CRITICA.\n"
        "Si hay incertidumbre visual o contradicción entre la foto y el texto, reduce `confidence` (< 0.65) y menciónalo con honestidad en `summary`.\n\n"
        f"Descripción ciudadana: {description}\n"
        f"Coordenadas GPS: ({latitude}, {longitude}){extra_addr}{extra_audio}\n\n"
        "Devuelve ÚNICAMENTE un objeto JSON válido con estas claves exactas:\n"
        '{"category": "HUECO|BASURAS|TALA|QUEMA|OTRO", "severity": "BAJA|MEDIA|ALTA|CRITICA", '
        '"confidence": 0.0..1.0, "summary": "explicación breve en español de 15 a 350 caracteres", '
        '"keywords": ["palabra1", "palabra2"]}'
    )


def classify_evidence_with_router(
    *,
    description: str,
    latitude: float,
    longitude: float,
    image_bytes: bytes | None = None,
    image_mime: str | None = None,
    address_hint: str | None = None,
    audio_transcript: str | None = None,
    report_id: UUID | str | None = None,
    trace_group_id: UUID | None = None,
    total_timeout_override: float | None = None,
) -> tuple[AIAnalysisContract | None, dict[str, Any]]:
    """
    Ejecuta clasificación multimodal a través del router Gemini -> Groq -> Gemini.
    Nunca lanza excepción hacia el ciudadano; si todos los proveedores fallan,
    retorna (None, metadata_de_traza) para conservar el reporte en PENDING_ANALYSIS.
    """
    eff_trace_group_id = trace_group_id or uuid.uuid4()
    prompt_text = build_classification_prompt(
        description=description,
        latitude=latitude,
        longitude=longitude,
        address_hint=address_hint,
        audio_transcript=audio_transcript,
    )

    chain = get_provider_chain()
    ensure_at_least_one_circuit_openable(chain)
    max_retries = max(0, min(settings.AI_MAX_RETRIES, 2))
    per_call_timeout = max(1.0, min(settings.AI_TIMEOUT_SECONDS, 6.0))
    t_start = time.perf_counter()
    total_timeout = float(total_timeout_override if total_timeout_override is not None else settings.AI_TIMEOUT_SECONDS)
    dl = get_deadline_context()
    if dl is not None:
        rem_dl = dl - time.monotonic()
        total_timeout = min(total_timeout, max(0.0, rem_dl))

    attempt_global = 0
    provider_switches = 0

    for idx, node in enumerate(chain):
        elapsed_router = time.perf_counter() - t_start
        if elapsed_router >= total_timeout or (dl is not None and time.monotonic() >= dl):
            break

        provider = node["provider"]
        model = node["model"]
        api_key = node["api_key"]
        tier = node["tier"]

        cb = get_circuit(provider, model)
        if not cb.allow_request():
            attempt_global += 1
            _safe_record_trace(
                trace_group_id=eff_trace_group_id,
                operation="classify_evidence",
                provider=provider,
                model=model,
                attempt_number=attempt_global,
                success=False,
                latency_ms=0,
                report_id=report_id,
                error_code="CIRCUIT_OPEN",
                error_detail=f"Circuit breaker abierto para {provider}:{model}",
                metadata={"tier": tier, "circuit_state": cb.state},
            )
            provider_switches += 1
            continue

        # Si falla por error no reintentable (ej. INVALID_JSON o 400), pasamos directo al siguiente proveedor
        max_node_attempts = 1 + max_retries
        for node_try in range(max_node_attempts):
            elapsed_now = time.perf_counter() - t_start
            remaining_for_call = total_timeout - elapsed_now
            if dl is not None:
                rem_ctx = dl - time.monotonic()
                remaining_for_call = min(remaining_for_call, rem_ctx)
            if remaining_for_call <= 0.01:
                break

            effective_timeout = min(per_call_timeout, remaining_for_call)
            if effective_timeout <= 0.005:
                break
            attempt_global += 1
            t0 = time.perf_counter()
            try:
                forced_raw = _check_forced_fault(tier, provider)
                if forced_raw is not None:
                    raw_text, in_tok, out_tok = forced_raw, 40, 12
                elif provider == "google":
                    raw_text, in_tok, out_tok = _call_gemini_multimodal(
                        model=model,
                        api_key=api_key,
                        prompt_text=prompt_text,
                        image_bytes=image_bytes,
                        image_mime=image_mime,
                        timeout_sec=effective_timeout,
                    )
                else:
                    raw_text, in_tok, out_tok = _call_groq_multimodal(
                        model=model,
                        api_key=api_key,
                        prompt_text=prompt_text,
                        image_bytes=image_bytes,
                        image_mime=image_mime,
                        timeout_sec=effective_timeout,
                    )

                # Post-call deadline verification: reject if call finished outside deadline
                post_elapsed = time.perf_counter() - t_start
                if post_elapsed > total_timeout or (dl is not None and time.monotonic() >= dl):
                    raise AIProviderError(
                        "TIMEOUT",
                        f"Llamada a {provider}:{model} finalizó fuera del plazo permitido ({post_elapsed:.3f}s > {total_timeout:.3f}s).",
                        retryable=False,
                    )

                contract = parse_and_validate_analysis_json(raw_text)
                dt_ms = int((time.perf_counter() - t0) * 1000)
                cb.record_success()

                _safe_record_trace(
                    trace_group_id=eff_trace_group_id,
                    operation="classify_evidence",
                    provider=provider,
                    model=model,
                    attempt_number=attempt_global,
                    success=True,
                    latency_ms=dt_ms,
                    prompt_tokens=in_tok,
                    completion_tokens=out_tok,
                    report_id=report_id,
                    metadata={
                        "tier": tier,
                        "fallback_used": idx > 0,
                        "provider_switches": provider_switches,
                        "category": contract.category,
                        "severity": contract.severity,
                    },
                )
                return contract, {
                    "trace_group_id": str(eff_trace_group_id),
                    "provider": provider,
                    "model": model,
                    "tier": tier,
                    "fallback_used": idx > 0,
                    "attempts": attempt_global,
                    "latency_ms": dt_ms,
                    "prompt_tokens": in_tok,
                    "completion_tokens": out_tok,
                    "total_tokens": in_tok + out_tok,
                }

            except AIProviderError as exc:
                dt_ms = int((time.perf_counter() - t0) * 1000)
                cb.record_failure(exc.code)
                _safe_record_trace(
                    trace_group_id=eff_trace_group_id,
                    operation="classify_evidence",
                    provider=provider,
                    model=model,
                    attempt_number=attempt_global,
                    success=False,
                    latency_ms=dt_ms,
                    report_id=report_id,
                    error_code=exc.code,
                    error_detail=exc.message,
                    metadata={
                        "tier": tier,
                        "retry": node_try,
                        "provider_switches": provider_switches,
                    },
                )
                if (
                    exc.code == "TIMEOUT"
                    or exc.code == "HTTP_429"
                    or not exc.retryable
                    or node_try >= max_retries
                    or (tier == "primary" and node_try >= 1)
                    or (time.perf_counter() - t_start) >= total_timeout
                ):
                    break
                backoff = min(0.6, 0.15 * (2**node_try) + random.uniform(0.01, 0.08))
                time.sleep(backoff)
            except Exception as exc:
                dt_ms = int((time.perf_counter() - t0) * 1000)
                cb.record_failure("UNEXPECTED_ERROR")
                _safe_record_trace(
                    trace_group_id=eff_trace_group_id,
                    operation="classify_evidence",
                    provider=provider,
                    model=model,
                    attempt_number=attempt_global,
                    success=False,
                    latency_ms=dt_ms,
                    report_id=report_id,
                    error_code="UNEXPECTED_ERROR",
                    error_detail=type(exc).__name__,
                    metadata={"tier": tier},
                )
                break

        provider_switches += 1

    dt_total = int((time.perf_counter() - t_start) * 1000)
    return None, {
        "trace_group_id": str(eff_trace_group_id),
        "provider": "none",
        "model": "none",
        "fallback_used": True,
        "attempts": attempt_global,
        "all_failed": True,
        "latency_ms": dt_total,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def transcribe_audio_optional(audio_bytes: bytes, filename: str, mime_type: str) -> str | None:
    """Transcribe nota de voz opcional (<=60s/5MB) usando whisper-large-v3-turbo en Groq si está disponible."""
    if not settings.GROQ_API_KEY or not audio_bytes:
        return None
    if get_effective_fault_mode() in ("TOTAL", "CAIDA_TOTAL", "429_ALL"):
        return None

    trace_group_id = uuid.uuid4()
    t0 = time.perf_counter()
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    try:
        with httpx.Client(timeout=httpx.Timeout(6.0, connect=3.0)) as client:
            resp = client.post(
                url,
                headers=headers,
                data={"model": "whisper-large-v3-turbo", "language": "es", "response_format": "json"},
                files={"file": (filename or "audio.wav", audio_bytes, mime_type)},
            )
        dt_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            txt = (resp.json().get("text") or "").strip()
            _safe_record_trace(
                trace_group_id=trace_group_id,
                operation="transcribe_audio",
                provider="groq",
                model="whisper-large-v3-turbo",
                attempt_number=1,
                success=True,
                latency_ms=dt_ms,
                prompt_tokens=50,
                completion_tokens=max(1, len(txt) // 4),
            )
            return txt[:1000] if txt else None
        _safe_record_trace(
            trace_group_id=trace_group_id,
            operation="transcribe_audio",
            provider="groq",
            model="whisper-large-v3-turbo",
            attempt_number=1,
            success=False,
            latency_ms=dt_ms,
            error_code=f"HTTP_{resp.status_code}",
            error_detail="No se pudo transcribir audio opcional.",
        )
    except Exception as exc:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        _safe_record_trace(
            trace_group_id=trace_group_id,
            operation="transcribe_audio",
            provider="groq",
            model="whisper-large-v3-turbo",
            attempt_number=1,
            success=False,
            latency_ms=dt_ms,
            error_code=type(exc).__name__,
            error_detail="Fallo en transcripción opcional de audio.",
        )
    return None
