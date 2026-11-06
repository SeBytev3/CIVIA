"""
Pruebas herméticas de comprobación y validación de proveedores de IA de CIVIA.
Verifica que validate_providers evalúe correctamente los estados (PENDIENTE, CONFIGURADA,
VALIDADA, CLAVE_INVALIDA, CUOTA_AGOTADA, TIMEOUT) sin divulgar secretos en ningún caso.
"""
from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.validate_providers import (
    check_all_providers,
    check_google_key,
    check_groq_key,
)


def test_check_google_key_empty():
    res = check_google_key("", "gemini-3.8-flash", "primary", live_check=False)
    assert res["status"] == "PENDIENTE"
    assert res["configured"] is False
    assert "MVP local" in res["detail"]


def test_check_google_key_configured_no_live():
    res = check_google_key("AIzaSyFakeSecretKey123", "gemini-3.8-flash", "primary", live_check=False)
    assert res["status"] == "CONFIGURADA"
    assert res["configured"] is True
    assert "AIzaSyFakeSecretKey123" not in res["detail"]
    assert "AIzaSyFakeSecretKey123" not in str(res)


@patch("httpx.Client.post")
def test_check_google_key_live_valid(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    res = check_google_key("AIzaSyValidKey123", "gemini-3.8-flash", "primary", live_check=True)
    assert res["status"] == "VALIDADA"
    assert res["configured"] is True
    assert "AIzaSyValidKey123" not in str(res)


@patch("httpx.Client.post")
def test_check_google_key_live_invalid(mock_post):
    mock_post.return_value = MagicMock(status_code=403)
    res = check_google_key("AIzaSyInvalidKey123", "gemini-3.8-flash", "primary", live_check=True)
    assert res["status"] == "CLAVE_INVALIDA"
    assert "AIzaSyInvalidKey123" not in str(res)


@patch("httpx.Client.post")
def test_check_google_key_live_quota(mock_post):
    mock_post.return_value = MagicMock(status_code=429)
    res = check_google_key("AIzaSyValidKey123", "gemini-3.8-flash", "primary", live_check=True)
    assert res["status"] == "CUOTA_AGOTADA"


@patch("httpx.Client.post")
def test_check_google_key_live_timeout(mock_post):
    mock_post.side_effect = httpx.TimeoutException("Timeout")
    res = check_google_key("AIzaSyValidKey123", "gemini-3.8-flash", "primary", live_check=True)
    assert res["status"] == "TIMEOUT"


def test_check_groq_key_empty():
    res = check_groq_key("", "qwen/qwen3.8-27b", live_check=False)
    assert res["status"] == "PENDIENTE"
    assert res["configured"] is False


def test_check_groq_key_configured_no_live():
    res = check_groq_key("gsk_fakegroqkey12345", "qwen/qwen3.8-27b", live_check=False)
    assert res["status"] == "CONFIGURADA"
    assert res["configured"] is True
    assert "gsk_fakegroqkey12345" not in str(res)


@patch("httpx.Client.post")
def test_check_groq_key_live_valid(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    res = check_groq_key("gsk_validkey12345", "qwen/qwen3.8-27b", live_check=True)
    assert res["status"] == "VALIDADA"
    assert "gsk_validkey12345" not in str(res)


@patch("httpx.Client.post")
def test_check_groq_key_live_invalid(mock_post):
    mock_post.return_value = MagicMock(status_code=401)
    res = check_groq_key("gsk_invalidkey12345", "qwen/qwen3.8-27b", live_check=True)
    assert res["status"] == "CLAVE_INVALIDA"
    assert "gsk_invalidkey12345" not in str(res)


@patch("httpx.Client.post")
def test_check_groq_key_live_quota(mock_post):
    mock_post.return_value = MagicMock(status_code=429)
    res = check_groq_key("gsk_validkey12345", "qwen/qwen3.8-27b", live_check=True)
    assert res["status"] == "CUOTA_AGOTADA"


@patch("httpx.Client.post")
def test_check_groq_key_live_timeout(mock_post):
    mock_post.side_effect = httpx.TimeoutException("Timeout")
    res = check_groq_key("gsk_validkey12345", "qwen/qwen3.8-27b", live_check=True)
    assert res["status"] == "TIMEOUT"


def test_check_all_providers():
    res = check_all_providers(live_check=False)
    assert "google_primary" in res
    assert "google_secondary" in res
    assert "groq" in res
    assert res["live_check_executed"] is False
