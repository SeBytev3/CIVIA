"""Exercise the exact inference capabilities with generated, non-citizen fixtures."""

import base64
import io
import json
import wave

import httpx
from PIL import Image

from app.ai_router import AIProviderError, check_gemini_safety, check_groq_safety, provider_response_error
from app.inference_transport import gemini_url, post_inference, record_capability

_FUNCTION = {
    "name": "capability_probe",
    "description": "Indicate that the isolated capability check reached the tool boundary.",
    "parameters": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
}


def _fixture_photo() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (255, 0, 0)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _fixture_audio() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(bytes(32000))
    return buf.getvalue()


def _probe(provider: str, model: str, key: str, capability: str) -> None:
    common = {"timeout": 8, "reserve": False}
    if capability == "audio":
        response = post_inference(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"}, data={"model": model, "response_format": "json"},
            files={"file": ("preflight.wav", _fixture_audio(), "audio/wav")},
            **common,
        )
        provider_response_error(response)
        if not isinstance(response.json().get("text"), str):
            raise ValueError("Audio output")
        return

    prompt = {
        "tools": "Call capability_probe with ok=true.",
        "structured": 'Return only {"ok": true} as JSON.',
        "vision": 'What is the dominant color of the supplied image? Return JSON with key color and one English word.',
    }[capability]
    image = _fixture_photo() if capability == "vision" else None
    if provider == "google":
        parts = [{"text": prompt}]
        if image:
            parts.append({"inline_data": {"mime_type": "image/png", "data": image}})
        payload = {"contents": [{"parts": parts}], "generationConfig": {"maxOutputTokens": 800}}
        if capability == "tools":
            payload["tools"] = [{"functionDeclarations": [_FUNCTION]}]
            payload["toolConfig"] = {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [_FUNCTION["name"]]}}
        else:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        response = post_inference(gemini_url(model), headers={"x-goog-api-key": key}, payload=payload, **common)
        provider_response_error(response)
        body = response.json()
        check_gemini_safety(body)
        parts = body["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        calls = [part["functionCall"]["name"] for part in parts if "functionCall" in part]
    else:
        content = [{"type": "text", "text": prompt}]
        if image:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}})
        payload = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 400}
        if capability == "tools":
            payload["tools"] = [{"type": "function", "function": _FUNCTION}]
            payload["tool_choice"] = {"type": "function", "function": {"name": _FUNCTION["name"]}}
        else:
            payload["response_format"] = {"type": "json_object"}
        response = post_inference(
            "https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
            payload=payload, **common,
        )
        provider_response_error(response)
        choices = response.json()["choices"]
        check_groq_safety(choices)
        message = choices[0]["message"]
        text = message.get("content") or ""
        calls = [call["function"]["name"] for call in message.get("tool_calls", [])]
    if capability == "tools":
        if _FUNCTION["name"] not in calls:
            raise ValueError("Tool output")
    elif capability == "vision":
        if json.loads(text).get("color", "").casefold() != "red":
            raise ValueError("Vision output")
    elif json.loads(text).get("ok") is not True:
        raise ValueError("Structured output")


def validate_capability(provider: str, model: str, key: str, capability: str) -> dict[str, str]:
    status = "PENDIENTE"
    if model and key.strip():
        try:
            _probe(provider, model, key.strip(), capability)
        except AIProviderError as exc:
            status = exc.code
        except httpx.TimeoutException:
            status = "TIMEOUT"
        except httpx.HTTPError:
            status = "ERROR_RED"
        except (AttributeError, ValueError, KeyError, IndexError, TypeError):
            status = "SALIDA_NO_VALIDADA"
        else:
            status = "VALIDADA"
        record_capability(provider, model, capability, key.strip(), status == "VALIDADA")
    return {"model": model, "status": status}
