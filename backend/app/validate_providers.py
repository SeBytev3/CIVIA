"""
Módulo de comprobación y validación de conectividad de proveedores de IA de CIVIA.
Verifica si las claves están cargadas en el entorno del contenedor y, si se solicita
con --live, ejecuta un ping minimalista a cada API sin divulgar secretos ni datos sensibles.
"""
import argparse
import json
import sys
from typing import Any
import httpx

from app.config import settings


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

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key_clean}"
    payload = {
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 2, "temperature": 0.0},
    }
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(url, json=payload)
        if resp.status_code == 200:
            return {
                "tier": tier_label,
                "provider": "google",
                "model": model,
                "configured": True,
                "status": "VALIDADA",
                "detail": f"Conexión exitosa con Google AI Studio ({model}, HTTP 200)",
            }
        elif resp.status_code in (400, 401, 403):
            return {
                "tier": tier_label,
                "provider": "google",
                "model": model,
                "configured": True,
                "status": "CLAVE_INVALIDA",
                "detail": f"Rechazado por Google AI Studio (HTTP {resp.status_code}) - Verifique la clave privada",
            }
        elif resp.status_code == 429:
            return {
                "tier": tier_label,
                "provider": "google",
                "model": model,
                "configured": True,
                "status": "CUOTA_AGOTADA",
                "detail": "Clave válida pero cuota o tasa excedida en Google AI Studio (HTTP 429)",
            }
        else:
            return {
                "tier": tier_label,
                "provider": "google",
                "model": model,
                "configured": True,
                "status": f"ERROR_HTTP_{resp.status_code}",
                "detail": f"Respuesta inesperada de Google (HTTP {resp.status_code})",
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
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(url, headers=headers, json=payload)
        if resp.status_code == 200:
            return {
                "tier": "fallback",
                "provider": "groq",
                "model": model,
                "configured": True,
                "status": "VALIDADA",
                "detail": f"Conexión exitosa con Groq Cloud ({model}, HTTP 200)",
            }
        elif resp.status_code in (401, 403):
            return {
                "tier": "fallback",
                "provider": "groq",
                "model": model,
                "configured": True,
                "status": "CLAVE_INVALIDA",
                "detail": f"Rechazado por Groq Cloud (HTTP {resp.status_code}) - Clave inválida o revocada",
            }
        elif resp.status_code == 429:
            return {
                "tier": "fallback",
                "provider": "groq",
                "model": model,
                "configured": True,
                "status": "CUOTA_AGOTADA",
                "detail": "Clave válida pero cuota o límite de tasa excedido en Groq (HTTP 429)",
            }
        else:
            return {
                "tier": "fallback",
                "provider": "groq",
                "model": model,
                "configured": True,
                "status": f"ERROR_HTTP_{resp.status_code}",
                "detail": f"Respuesta inesperada de Groq (HTTP {resp.status_code})",
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
    google_secondary = check_google_key(
        settings.GOOGLE_API_KEY_SECONDARY,
        settings.AI_TERTIARY_MODEL,
        tier_label="tertiary",
        live_check=live_check,
    )
    groq = check_groq_key(
        settings.GROQ_API_KEY,
        settings.AI_FALLBACK_MODEL,
        live_check=live_check,
    )
    return {
        "live_check_executed": live_check,
        "google_primary": google_primary,
        "google_secondary": google_secondary,
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
    p2 = results["google_secondary"]
    p3 = results["groq"]

    print(f" - Google Primaria ({p1['model']}):   [{p1['status']}] {p1['detail']}")
    print(f" - Google Secundaria ({p2['model']}): [{p2['status']}] {p2['detail']}")
    print(f" - Groq Cloud ({p3['model']}):        [{p3['status']}] {p3['detail']}")
    print("=================================================================")


if __name__ == "__main__":
    main()
