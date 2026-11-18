"""
Módulo de comprobación y validación de conectividad de proveedores de IA de CIVIA.
Verifica si las claves están cargadas en el entorno del contenedor y, si se solicita
con --live, ejecuta un ping minimalista a cada API sin divulgar secretos ni datos sensibles.
"""
import argparse
import json
from typing import Any
import httpx

from app.config import settings
from app.inference_transport import gemini_url, post_inference
from app.provider_preflight import validate_capability


_GENERATION_STATUS = {
    400: ("SOLICITUD_NO_ADMITIDA", "La API rechazó la configuración de la prueba de generación."),
    401: ("CLAVE_INVALIDA", "La API rechazó la autenticación."),
    403: ("PERMISO_DENEGADO", "La API denegó la generación. Revisa políticas de proyecto, modelo y red."),
    404: ("MODELO_NO_DISPONIBLE", "El modelo configurado no está disponible para esta cuenta."),
    429: ("CUOTA_AGOTADA", "Se alcanzó un límite de cuota o de frecuencia."),
}


def _generation_result(status: int, provider_name: str) -> dict[str, str]:
    if status == 200:
        return {"status": "VALIDADA", "detail": f"Respuesta de generación recibida de {provider_name}."}
    label, detail = _GENERATION_STATUS.get(
        status, (f"ERROR_HTTP_{status}", "Respuesta inesperada de la API de generación."),
    )
    return {"status": label, "detail": detail}


def _google_catalog_status(api_key: str, model: str) -> str:
    try:
        url = gemini_url(model).removesuffix(":generateContent")
        with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
            with client.stream("GET", url, headers={"x-goog-api-key": api_key}) as response:
                return {
                    200: "MODELO_VISIBLE",
                    401: "AUTENTICACION_RECHAZADA",
                    403: "ACCESO_CATALOGO_DENEGADO",
                    404: "MODELO_NO_VISIBLE",
                    429: "LIMITE_CATALOGO",
                }.get(response.status_code, "ERROR_CATALOGO")
    except httpx.TimeoutException:
        return "TIMEOUT_CATALOGO"
    except (httpx.HTTPError, ValueError):
        return "ERROR_CATALOGO"


def check_google_key(
    api_key: str,
    model: str,
    tier_label: str,
    live_check: bool = False,
    timeout_sec: float = 6.0,
) -> dict[str, Any]:
    key_clean = (api_key or "").strip()
    if not key_clean:
        return {
            "tier": tier_label,
            "provider": "google",
            "model": model,
            "configured": False,
            "status": "PENDIENTE",
            "detail": "Clave no configurada en .env (Modo MVP local activo)",
        }

    if not live_check:
        return {
            "tier": tier_label,
            "provider": "google",
            "model": model,
            "configured": True,
            "status": "CONFIGURADA",
            "detail": "Variable cargada en el contenedor; validación de llamada en vivo no solicitada",
        }

    payload = {
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 2, "temperature": 0.0},
    }
    try:
        url = gemini_url(model)
        resp = post_inference(url, timeout=timeout_sec, headers={"x-goog-api-key": key_clean}, payload=payload, reserve=False)
        return {
            "tier": tier_label, "provider": "google", "model": model, "configured": True,
            **_generation_result(resp.status_code, "Google AI Studio"),
        }
    except httpx.TimeoutException:
        return {
            "tier": tier_label,
            "provider": "google",
            "model": model,
            "configured": True,
            "status": "TIMEOUT",
            "detail": "Tiempo de espera agotado al conectar con Google AI Studio (>6s)",
        }
    except Exception as exc:
        return {
            "tier": tier_label,
            "provider": "google",
            "model": model,
            "configured": True,
            "status": "ERROR_RED",
            "detail": f"Error de red al conectar con Google: {type(exc).__name__}",
        }


def check_groq_key(
    api_key: str,
    model: str,
    live_check: bool = False,
    timeout_sec: float = 6.0,
) -> dict[str, Any]:
    key_clean = (api_key or "").strip()
    if not key_clean:
        return {
            "tier": "fallback",
            "provider": "groq",
            "model": model,
            "configured": False,
            "status": "PENDIENTE",
            "detail": "Clave no configurada en .env (Modo MVP local activo)",
        }

    if not live_check:
        return {
            "tier": "fallback",
            "provider": "groq",
            "model": model,
            "configured": True,
            "status": "CONFIGURADA",
            "detail": "Variable cargada en el contenedor; validación de llamada en vivo no solicitada",
        }

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key_clean}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 2,
    }
    try:
        resp = post_inference(url, timeout=timeout_sec, headers=headers, payload=payload, reserve=False)
        return {
            "tier": "fallback", "provider": "groq", "model": model, "configured": True,
            **_generation_result(resp.status_code, "Groq Cloud"),
        }
    except httpx.TimeoutException:
        return {
            "tier": "fallback",
            "provider": "groq",
            "model": model,
            "configured": True,
            "status": "TIMEOUT",
            "detail": "Tiempo de espera agotado al conectar con Groq Cloud (>6s)",
        }
    except Exception as exc:
        return {
            "tier": "fallback",
            "provider": "groq",
            "model": model,
            "configured": True,
            "status": "ERROR_RED",
            "detail": f"Error de red al conectar con Groq: {type(exc).__name__}",
        }


def check_all_providers(live_check: bool = False) -> dict[str, Any]:
    google_primary = check_google_key(
        settings.GOOGLE_API_KEY_PRIMARY,
        settings.AI_PRIMARY_MODEL,
        tier_label="primary",
        live_check=live_check,
    )
    groq = check_groq_key(
        settings.GROQ_API_KEY,
        settings.AI_FALLBACK_MODEL,
        live_check=live_check,
    )
    if live_check:
        if google_primary["configured"] and google_primary["status"] != "VALIDADA":
            google_primary["catalog"] = _google_catalog_status(
                settings.GOOGLE_API_KEY_PRIMARY.strip(), settings.AI_PRIMARY_MODEL,
            )
        google_primary["capabilities"] = {
            mode: (
                validate_capability("google", settings.AI_PRIMARY_MODEL, settings.GOOGLE_API_KEY_PRIMARY, mode)
                if google_primary["status"] == "VALIDADA"
                else {"model": settings.AI_PRIMARY_MODEL,
                      "status": "NO_PROBADA" if google_primary["configured"] else "PENDIENTE"}
            )
            for mode in ("tools", "structured", "vision")
        }
        groq["capabilities"] = {
            mode: validate_capability("groq", model, settings.GROQ_API_KEY, mode)
            for mode, model in (
                ("tools", settings.AI_FALLBACK_MODEL), ("structured", settings.AI_FALLBACK_MODEL),
                ("vision", settings.AI_GROQ_VISION_MODEL), ("audio", settings.AI_GROQ_AUDIO_MODEL),
            )
        }
    return {
        "live_check_executed": live_check,
        "google_primary": google_primary,
        "groq": groq,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Comprueba las credenciales de IA de CIVIA de forma segura sin divulgar secretos."
    )
    parser.add_argument("--live", action="store_true", help="Ejecuta llamada real a las APIs para verificar validez")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON estructurado")
    args = parser.parse_args()

    results = check_all_providers(live_check=args.live)
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    print("=================================================================")
    print(" ESTADO DE CREDENCIALES DE INTELIGENCIA ARTIFICIAL — CIVIA")
    print("=================================================================")
    p1 = results["google_primary"]
    p3 = results["groq"]

    print(f" - Google Primaria ({p1['model']}):   [{p1['status']}] {p1['detail']}")
    print(f" - Groq Cloud ({p3['model']}):        [{p3['status']}] {p3['detail']}")
    if args.live:
        if p1.get("catalog"):
            print(f"   Google / catálogo: {p1['catalog']}")
        for summary in (p1, p3):
            for capability, result in summary.get("capabilities", {}).items():
                print(f"   {summary['provider']} / {capability} / {result['model'] or 'sin modelo'}: {result['status']}")
    print("=================================================================")


if __name__ == "__main__":
    main()
