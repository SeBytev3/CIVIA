"""
Adversarial regression test suite for CIVIA - Audit Remediation Block G2.
Covers findings:
- A-02: Timeout blocks worker tool writes and rollbacks DB operations
- M-03: Global agent timeout propagation prevents late execution
- M-02: Server-side token reservation and bounds enforcement
- A-03: Strict JSON validation in router without silent fallbacks or invented fields
- A-04: PII and internal technical error sanitization in citizen outputs
- M-04: Circuit breaker allows strictly one probe in HALF_OPEN
- N-02: No hidden unconfigured model substitutions
- M-01: Deep audio payload validation rejecting ID3-only dummy files
- M-06: Trusted reverse-proxy IP extraction preventing spoofing
- Q13: Deterministic fallback preserves tracking code and proposed status
"""

import json
import time
import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request

from app.config import settings
from app.db import (
    set_deadline_context,
    reset_deadline_context,
    get_deadline_context,
    checked_commit,
    get_conn,
)
from app.ai_router import (
    CircuitBreakerState,
    AIProviderError,
    parse_and_validate_analysis_json,
    resolve_effective_gemini_model,
)
from app.agent import (
    execute_tool_with_timeout,
    TOOL_DISPATCH,
    sanitize_citizen_agent_output,
    run_civia_agent,
    _deterministic_sql_fallback_answer,
    tool_proponer_actualizacion_critica,
)
from app.security import (
    validate_and_store_audio,
    CitizenValidationError,
    get_trusted_client_ip,
)
from app.schemas import AgentQueryRequest
from app.repository import _sanitize_public_text, row_to_public_dict


# -------------------------------------------------------------------------
# A-02: Late tool write blocked after timeout & checked_commit rollback
# -------------------------------------------------------------------------

def test_a02_checked_commit_blocks_late_writes():
    """Verify that checked_commit aborts and rolls back if deadline expired."""
    mock_conn = MagicMock()
    # Set a deadline in the past
    token = set_deadline_context(time.monotonic() - 1.0)
    try:
        with pytest.raises(TimeoutError, match="expiración del deadline"):
            checked_commit(mock_conn)
        # Verify rollback was called and commit was NOT called
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
    finally:
        reset_deadline_context(token)


def test_a02_execute_tool_with_timeout_aborts_slow_worker():
    """Verify that a tool exceeding timeout raises TimeoutError."""
    def slow_tool(args: dict):
        time.sleep(1.0)
        return {"success": True}

    with patch.dict(TOOL_DISPATCH, {"slow_tool": slow_tool}):
        with pytest.raises(TimeoutError, match="superó el límite de 0.2s"):
            execute_tool_with_timeout("slow_tool", {}, timeout_sec=0.2)


# -------------------------------------------------------------------------
# M-03: Global deadline propagation in agent loop
# -------------------------------------------------------------------------

def test_m03_global_deadline_context_propagation():
    """Verify that agent honors tight deadline and does not attempt work after expiration."""
    # When deadline is in the past, get_conn rejects connection immediately
    token = set_deadline_context(time.monotonic() - 0.5)
    try:
        assert get_deadline_context() is not None
        with pytest.raises(TimeoutError, match="expirado antes de abrir conexión"):
            with get_conn():
                pass
    finally:
        reset_deadline_context(token)


# -------------------------------------------------------------------------
# M-02: Server-side token reservation and bounds enforcement
# -------------------------------------------------------------------------

def test_m02_schema_caps_client_input():
    """Verify schema bounds prevent unbounded iterations or tokens."""
    # Pydantic validation rejects iterations > 5
    with pytest.raises(Exception):
        AgentQueryRequest(query="hola", max_iterations=99)

    # Pydantic validation rejects tokens > 6000
    with pytest.raises(Exception):
        AgentQueryRequest(query="hola", max_tokens_budget=99999)


def test_m02_token_reservation_breaks_before_llm_call():
    """Verify that agent loop triggers MAX_TOKENS guardrail if budget < 60."""
    result = run_civia_agent(
        query="Consulta",
        max_iterations=1,
        max_tokens_budget=50,
    )
    assert result.get("guardrail_triggered") == "MAX_TOKENS"


# -------------------------------------------------------------------------
# A-03: Strict contract validation in AI router
# -------------------------------------------------------------------------

@pytest.mark.parametrize("invalid_payload", [
    {},  # Empty dict
    {"category": "NUCLEAR", "severity": "ALTA", "confidence": 0.9, "summary": "Valid summary long enough"},
    {"category": "HUECO", "severity": "INVENTADA", "confidence": 0.9, "summary": "Valid summary long enough"},
    {"category": "HUECO", "severity": "ALTA", "confidence": -5, "summary": "Valid summary long enough"},
    {"category": "HUECO", "severity": "ALTA", "confidence": "no-numerico", "summary": "Valid summary long enough"},
    {"category": "HUECO", "severity": "ALTA", "confidence": 0.9, "summary": "corto"},  # < 10 chars
    {"category": "HUECO", "confidence": 0.9, "summary": "Valid summary long enough"},  # Missing severity
    {"severity": "ALTA", "confidence": 0.9, "summary": "Valid summary long enough"},  # Missing category
])
def test_a03_strict_contract_validation_rejects_adversarial_data(invalid_payload):
    """Verify router rejects malformed payloads with INVALID_SCHEMA instead of coercing."""
    with pytest.raises(AIProviderError) as exc_info:
        parse_and_validate_analysis_json(json.dumps(invalid_payload))
    assert exc_info.value.code == "INVALID_SCHEMA"


def test_a03_strict_contract_validation_accepts_valid():
    """Verify valid analysis payload is accepted accurately."""
    valid_payload = {
        "category": "BASURAS",
        "severity": "CRITICA",
        "confidence": 0.95,
        "summary": "Acumulación severa de residuos en vía pública",
    }
    parsed = parse_and_validate_analysis_json(json.dumps(valid_payload))
    assert parsed.category == "BASURAS"
    assert parsed.severity == "CRITICA"
    assert parsed.confidence == 0.95


# -------------------------------------------------------------------------
# A-04: PII and technical error sanitization in citizen outputs
# -------------------------------------------------------------------------

def test_a04_sanitize_citizen_agent_output_redacts_internals_and_pii():
    """Verify agent output redacts API errors, provider names, tracebacks, emails, phones."""
    leaked_text = (
        "Ocurrió un error en Google API: HTTP 401 Unauthorized ValueError. "
        "Contactar a soporte en admin@cali.gov.co o al teléfono +57 312 987 6543. "
        "Traceback (most recent call last): File agent.py line 40"
    )
    sanitized = sanitize_citizen_agent_output(leaked_text)
    assert "Google" not in sanitized
    assert "HTTP 401" not in sanitized
    assert "ValueError" not in sanitized
    assert "admin@cali.gov.co" not in sanitized
    assert "312 987 6543" not in sanitized
    assert "Traceback" not in sanitized
    assert "[CORREO_PROTEGIDO]" in sanitized
    assert "[TELEFONO_PROTEGIDO]" in sanitized
    assert "[SISTEMA_IA]" in sanitized


def test_a04_repository_sanitizes_public_text():
    """Verify repository text sanitizer protects public report fields."""
    raw = "Reporte con error en Groq API y contacto ciudadano ciudadano@example.com cel 3001234567"
    cleaned = _sanitize_public_text(raw)
    assert "Groq" not in cleaned
    assert "API" not in cleaned
    assert "[CORREO_PROTEGIDO]" in cleaned
    assert "[TELEFONO_PROTEGIDO]" in cleaned


# -------------------------------------------------------------------------
# M-04: Circuit breaker single probe in HALF_OPEN
# -------------------------------------------------------------------------

def test_m04_circuit_breaker_single_probe_half_open():
    """Verify circuit breaker in HALF_OPEN allows strictly one request at a time."""
    cb = CircuitBreakerState(provider="test", model="test_model", failure_threshold=2, cooldown_seconds=0.1)
    
    # Trip the circuit
    cb.record_failure("429")
    cb.record_failure("429")
    assert cb.state == "OPEN"
    assert cb.allow_request() is False

    # Wait for cooldown to transition to HALF_OPEN
    time.sleep(0.15)

    # First request: should be allowed (the probe)
    assert cb.allow_request() is True
    assert cb.state == "HALF_OPEN"

    # Second concurrent request while probe in flight: must be BLOCKED
    assert cb.allow_request() is False

    # Probe succeeds: resets to CLOSED
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.allow_request() is True


def test_m04_circuit_breaker_probe_failure_reopens():
    """Verify failed probe in HALF_OPEN trips circuit back to OPEN."""
    cb = CircuitBreakerState(provider="test", model="test_model2", failure_threshold=1, cooldown_seconds=0.1)
    cb.record_failure("500")
    assert cb.state == "OPEN"

    time.sleep(0.15)
    # Admitted probe
    assert cb.allow_request() is True
    # Probe fails
    cb.record_failure("500")
    assert cb.state == "OPEN"
    assert cb.allow_request() is False


# -------------------------------------------------------------------------
# N-02: No hidden unconfigured model substitutions
# -------------------------------------------------------------------------

def test_n02_resolve_effective_gemini_model_no_silent_switch():
    """Verify model resolver strictly preserves the requested model ID."""
    configured = "gemini-3.8-flash"
    resolved = resolve_effective_gemini_model(configured)
    assert resolved == configured

    # Even if model was reported exhausted, resolver does not silently alter it
    from app.ai_router import mark_gemini_model_exhausted
    mark_gemini_model_exhausted(configured)
    assert resolve_effective_gemini_model(configured) == configured


# -------------------------------------------------------------------------
# M-01: Deep audio payload validation
# -------------------------------------------------------------------------

def test_m01_rejects_id3_only_dummy_files():
    """Verify audio validator rejects dummy files with ID3 headers but no audio data."""
    # ID3 header with invalid/empty payload
    fake_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x10not-real-audio-data"
    with pytest.raises(CitizenValidationError) as exc:
        validate_and_store_audio(fake_mp3, "test.mp3")
    assert exc.value.status_code == 415

    # ID3 header with zero frames
    fake_mp3_zeros = b"ID3\x04" + b"\x00" * 96
    with pytest.raises(CitizenValidationError) as exc:
        validate_and_store_audio(fake_mp3_zeros, "zeros.mp3")
    assert exc.value.status_code == 415


def test_m01_rejects_empty_wav():
    """Verify audio validator rejects WAV file with 0 data frames."""
    # Minimal WAV header with 0 data length
    fake_wav = (
        b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )
    with pytest.raises(CitizenValidationError) as exc:
        validate_and_store_audio(fake_wav, "empty.wav")
    assert exc.value.status_code == 415


# -------------------------------------------------------------------------
# M-06: Trusted reverse proxy IP extraction
# -------------------------------------------------------------------------

def test_m06_trusted_proxy_client_ip(monkeypatch):
    """Verify get_trusted_client_ip respects X-Forwarded-For only from trusted networks."""
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "172.28.0.2")
    # Untrusted client attempting to spoof IP via X-Forwarded-For
    scope_untrusted = {
        "type": "http",
        "client": ("198.51.100.2", 54321),
        "headers": [(b"x-forwarded-for", b"203.0.113.195")],
    }
    req_untrusted = Request(scope_untrusted)
    assert get_trusted_client_ip(req_untrusted) == "198.51.100.2"

    # Gateway or untrusted container (172.18.0.1 / 172.28.0.1) cannot spoof IP via headers
    scope_gateway = {
        "type": "http",
        "client": ("172.18.0.1", 54321),
        "headers": [(b"x-forwarded-for", b"203.0.113.195")],
    }
    req_gateway = Request(scope_gateway)
    assert get_trusted_client_ip(req_gateway) == "172.18.0.1"

    # Sole trusted proxy (Nginx 172.28.0.2) forwarding real client IP
    scope_trusted_nginx = {
        "type": "http",
        "client": ("172.28.0.2", 54321),
        "headers": [(b"x-forwarded-for", b"203.0.113.195")],
    }
    req_trusted = Request(scope_trusted_nginx)
    assert get_trusted_client_ip(req_trusted) == "203.0.113.195"

    # Trusted proxy with multiple hops in X-Forwarded-For (from 172.28.0.2)
    scope_trusted_hops = {
        "type": "http",
        "client": ("172.28.0.2", 54321),
        "headers": [(b"x-forwarded-for", b"190.85.12.34, 172.28.0.2")],
    }
    req_hops = Request(scope_trusted_hops)
    assert get_trusted_client_ip(req_hops) == "190.85.12.34"

    # Direct loopback connection (127.0.0.1) cannot spoof IP via headers
    scope_loopback = {
        "type": "http",
        "client": ("127.0.0.1", 54321),
        "headers": [(b"x-forwarded-for", b"190.85.12.34")],
    }
    req_loopback = Request(scope_loopback)
    assert get_trusted_client_ip(req_loopback) == "127.0.0.1"


# -------------------------------------------------------------------------
# Q13: Deterministic fallback preserves tracking code and proposed status
# -------------------------------------------------------------------------

def test_q13_deterministic_fallback_contains_tracking_code():
    """Verify outage deterministic answer includes tracking code and proposed status."""
    tool_hist = [{
        "tool": "proponer_actualizacion_critica",
        "result": {
            "requiere_aprobacion_humana": True,
            "approval_id": "12345678-abcd-1234-abcd-1234567890ab",
            "tracking_code": "CIV-2026-TEST42",
            "estado_propuesto": "RESOLVED",
            "mensaje": (
                "Por límite de seguridad, la IA NO modifica directamente la base de datos de reportes. "
                "Se creó la solicitud de aprobación humana #12345678 en estado PENDING "
                "para actualizar el reporte CIV-2026-TEST42 al estado RESOLVED."
            ),
        },
    }]
    fallback_answer = _deterministic_sql_fallback_answer(
        "proponer cambio CIV-2026-TEST42 a RESOLVED",
        tool_history=tool_hist,
    )
    assert "CIV-2026-TEST42" in fallback_answer
    assert "RESOLVED" in fallback_answer
    assert "aprobación humana" in fallback_answer
