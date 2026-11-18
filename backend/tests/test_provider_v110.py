import httpx
import pytest

from app.ai_router import AIProviderError, get_provider_chain, classify_evidence_with_router, reset_all_circuits
from app.config import settings
from app.inference_transport import ModelPreflightRequired, gemini_url, post_inference, record_capability
from app.validate_providers import check_all_providers, check_google_key


def test_provider_chain_uses_two_independent_providers():
    assert [tier["provider"] for tier in get_provider_chain()] == ["google", "groq"]
    assert set(check_all_providers()) == {"live_check_executed", "google_primary", "groq"}


def test_google_preflight_authenticates_in_header(monkeypatch):
    original_init = httpx.Client.__init__
    sent = []

    def respond(request):
        sent.append(request)
        return httpx.Response(200, json={"candidates": []})

    def client_init(self, **kwargs):
        original_init(self, transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", client_init)
    result = check_google_key("synthetic-credential", "test-model", "primary", live_check=True)
    assert sent, result["detail"]
    assert not sent[0].url.query
    assert sent[0].headers["x-goog-api-key"] == "synthetic-credential"


def test_runtime_requires_exact_model_and_capability_preflight(monkeypatch):
    original_init = httpx.Client.__init__
    sent = []

    def respond(request):
        sent.append(request)
        return httpx.Response(200, json={"ready": True})

    def client_init(self, **kwargs):
        original_init(self, transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", client_init)
    key = "synthetic-live-preflight"
    record_capability("google", "preflight-model", "structured", key, True)
    kwargs = {"timeout": 2, "headers": {"x-goog-api-key": key}, "payload": {"contents": []}}
    with pytest.raises(ModelPreflightRequired):
        post_inference(gemini_url("preflight-model"), capability="vision", **kwargs)
    assert sent == []
    assert post_inference(gemini_url("preflight-model"), capability="structured", **kwargs).json()["ready"]
    assert len(sent) == 1


def test_router_does_not_fallback_on_provider_policy_refusal(monkeypatch):
    from app import ai_router

    def deny(**_):
        raise AIProviderError("SAFETY_REFUSAL", "Política del proveedor.", retryable=False)

    def unexpected(*_, **__):
        pytest.fail("Una denegación de seguridad termina el ciclo.")

    reset_all_circuits()
    monkeypatch.setattr(settings, "GOOGLE_API_KEY_PRIMARY", "synthetic-primary")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "synthetic-backup")
    monkeypatch.setattr(ai_router, "_call_gemini_multimodal", deny)
    monkeypatch.setattr(ai_router, "_call_groq_multimodal", unexpected)
    with pytest.raises(AIProviderError, match="Política del proveedor") as failure:
        classify_evidence_with_router(description="Evidencia sintética", latitude=3.45, longitude=-76.53, for_queue=True)
    assert not failure.value.retryable
    reset_all_circuits()
