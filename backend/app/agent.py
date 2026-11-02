from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import logging
from pathlib import Path
import time
from typing import Any, Callable
from uuid import UUID
import uuid

import httpx

from app.ai_router import (
    AIProviderError,
    _check_forced_fault,
    classify_evidence_with_router,
    ensure_at_least_one_circuit_openable,
    get_circuit,
    get_provider_chain,
    mark_gemini_model_exhausted,
    resolve_effective_gemini_model,
)
from app.config import settings
from app.db import get_conn
from app.observability import record_ai_trace, sanitize_secret_text
from app.repository import (
    get_report_by_tracking_code,
    get_report_raw,
    get_reports_summary_stats,
    list_reports,
    row_to_public_dict,
    update_report_ai_analysis,
)
from app.security import _CO_PHONE_RE, _EMAIL_RE

logger = logging.getLogger("civia.agent")

_ON_APPROVAL_CREATED_HOOK: Callable[[UUID], None] | None = None


def set_approval_created_hook(hook: Callable[[UUID], None] | None) -> None:
    global _ON_APPROVAL_CREATED_HOOK
    _ON_APPROVAL_CREATED_HOOK = hook


def _safe_record_trace(**kwargs: Any) -> None:
    try:
        record_ai_trace(**kwargs)
    except Exception as exc:
        logger.warning("Fallo no bloqueante al registrar traza de agente: %s", type(exc).__name__)


def sanitize_citizen_agent_output(text: str) -> str:
    """
    Garantiza que la respuesta entregada al ciudadano no contenga secretos, PII,
    nombres de proveedores internos ni códigos de error HTTP o tracebacks.
    """
    import re

    cleaned = sanitize_secret_text(text) or ""
    cleaned = _EMAIL_RE.sub("[CORREO_PROTEGIDO]", cleaned)
    cleaned = _CO_PHONE_RE.sub("[TELEFONO_PROTEGIDO]", cleaned)
    cleaned = re.sub(r"\b(?:gemini|groq|traceback)\b", "[SISTEMA_IA]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bHTTP[_\s-]*(?:429|500|502|503|504)\b", "[SERVICIO_OCUPADO]", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

# Definición neutral de herramientas tipadas (se convierte al formato nativo de Gemini y de Groq)
AGENT_TOOLS_SPEC: list[dict[str, Any]] = [
    {
        "name": "consultar_reportes",
        "description": (
            "Consulta la base de datos PostgreSQL de reportes ciudadanos de CIVIA en Cali y Valle del Cauca. "
            "Permite filtrar por categoría (HUECO, BASURAS, TALA, QUEMA, OTRO), severidad (BAJA, MEDIA, ALTA, CRITICA), "
            "estado (PENDING_ANALYSIS, ANALYZED_PENDING_CONFIRMATION, CONFIRMED, IN_REVIEW, RESOLVED, REJECTED), "
            "comuna (ej. 'Comuna 2', 'Comuna 16', 'Comuna 22'), texto libre q, o radio geográfico (lat, lon, radius_km)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Categoría: HUECO, BASURAS, TALA, QUEMA u OTRO.",
                },
                "severity": {
                    "type": "string",
                    "description": "Severidad: BAJA, MEDIA, ALTA o CRITICA.",
                },
                "status": {
                    "type": "string",
                    "description": "Estado del reporte.",
                },
                "comuna": {
                    "type": "string",
                    "description": "Comuna de Cali, por ejemplo 'Comuna 2' o 'Comuna 16'.",
                },
                "q": {
                    "type": "string",
                    "description": "Texto a buscar en título, descripción, barrio o dirección.",
                },
                "lat": {
                    "type": "number",
                    "description": "Latitud central para búsqueda por radio.",
                },
                "lon": {
                    "type": "number",
                    "description": "Longitud central para búsqueda por radio.",
                },
                "radius_km": {
                    "type": "number",
                    "description": "Radio de búsqueda en kilómetros.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "obtener_reporte",
        "description": (
            "Obtiene el detalle completo de un reporte ciudadano específico usando su código de radicado "
            "(ej. 'CIV-2026-DEMO0001') o su identificador UUID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "identificador": {
                    "type": "string",
                    "description": "Código de radicado (CIV-2026-...) o UUID del reporte.",
                }
            },
            "required": ["identificador"],
        },
    },
    {
        "name": "clasificar_evidencia",
        "description": (
            "Ejecuta o consulta la clasificación multimodal asistida por IA sobre la fotografía y descripción "
            "de un reporte existente identificado por su código de radicado o UUID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "identificador": {
                    "type": "string",
                    "description": "Código de radicado (CIV-2026-...) o UUID del reporte a analizar.",
                }
            },
            "required": ["identificador"],
        },
    },
    {
        "name": "proponer_actualizacion_critica",
        "description": (
            "Propone un cambio de estado sobre un reporte ciudadano (IN_REVIEW, RESOLVED, REJECTED, CONFIRMED). "
            "Por política de seguridad de CIVIA, la IA NO escribe directamente en la tabla de reportes; "
            "esta herramienta registra una solicitud pendiente de aprobación humana."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "identificador": {
                    "type": "string",
                    "description": "Código de radicado (CIV-2026-...) o UUID del reporte.",
                },
                "nuevo_estado": {
                    "type": "string",
                    "description": "Estado propuesto: CONFIRMED, IN_REVIEW, RESOLVED o REJECTED.",
                },
                "motivo": {
                    "type": "string",
                    "description": "Justificación de la actualización propuesta.",
                },
            },
            "required": ["identificador", "nuevo_estado", "motivo"],
        },
    },
]


def _resolve_report_row(identificador: str) -> dict[str, Any] | None:
    ident = (identificador or "").strip()
    if not ident:
        return None
    row = get_report_by_tracking_code(ident)
    if row is not None:
        return row
    return get_report_raw(ident)


def tool_consultar_reportes(args: dict[str, Any]) -> dict[str, Any]:
    category = args.get("category")
    severity = args.get("severity")
    status = args.get("status")
    comuna = args.get("comuna")
    q = args.get("q")
    lat = float(args["lat"]) if args.get("lat") is not None else None
    lon = float(args["lon"]) if args.get("lon") is not None else None
    if lon is not None and 70.0 <= lon <= 80.0:
        lon = -abs(lon)
    radius_km = float(args["radius_km"]) if args.get("radius_km") is not None else None

    total, rows = list_reports(
        category=category,
        severity=severity,
        status=status,
        comuna=comuna,
        q=q,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        limit=20,
        offset=0,
    )
    stats = get_reports_summary_stats()
    if total == 0:
        return {
            "total_encontrados": 0,
            "evidencia_disponible": False,
            "mensaje": "No existen reportes ni evidencia en la base de datos para los filtros solicitados.",
            "items": [],
            "resumen_global_bd": stats,
        }

    items_summary = []
    for r in rows:
        pub = row_to_public_dict(r)
        items_summary.append(
            {
                "tracking_code": pub["tracking_code"],
                "id": str(pub["id"]),
                "title": pub["title"],
                "effective_category": pub["effective_category"],
                "effective_severity": pub["effective_severity"],
                "status": pub["status"],
                "comuna": pub["comuna"],
                "neighborhood": pub["neighborhood"],
                "address_hint": pub["address_hint"],
                "latitude": pub["latitude"],
                "longitude": pub["longitude"],
                "distance_km": pub["distance_km"],
                "human_confirmed": pub["human_confirmed"],
                "is_synthetic": pub["is_synthetic"],
            }
        )
    return {
        "total_encontrados": total,
        "evidencia_disponible": True,
        "items": items_summary,
        "resumen_global_bd": stats,
    }


def tool_obtener_reporte(args: dict[str, Any]) -> dict[str, Any]:
    ident = str(args.get("identificador") or "")
    row = _resolve_report_row(ident)
    if not row:
        return {
            "encontrado": False,
            "identificador_buscado": ident,
            "mensaje": "No existe ningún reporte registrado con ese identificador.",
        }
    pub = row_to_public_dict(row)
    pub["id"] = str(pub["id"])
    pub["created_at"] = pub["created_at"].isoformat()
    pub["updated_at"] = pub["updated_at"].isoformat()
    return {"encontrado": True, "reporte": pub}


def tool_clasificar_evidencia(args: dict[str, Any]) -> dict[str, Any]:
    ident = str(args.get("identificador") or "")
    row = _resolve_report_row(ident)
    if not row:
        return {
            "encontrado": False,
            "mensaje": "No se encontró el reporte para analizar su evidencia.",
        }

    safe_name = Path(row["photo_path"]).name
    photo_file = settings.UPLOAD_DIR / safe_name
    img_bytes = photo_file.read_bytes() if photo_file.exists() else None

    contract, meta = classify_evidence_with_router(
        description=row["description"],
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        image_bytes=img_bytes,
        image_mime=row["photo_mime"],
        address_hint=row.get("address_hint"),
        audio_transcript=row.get("audio_transcript"),
        report_id=row["id"],
    )
    if contract is None:
        return {
            "encontrado": True,
            "tracking_code": row["tracking_code"],
            "analisis_completado": False,
            "status": row["status"],
            "mensaje": "El análisis automático no pudo completarse en este momento; el reporte conserva su estado actual.",
        }

    updated = update_report_ai_analysis(
        row["id"],
        ai_category=contract.category,
        ai_severity=contract.severity,
        ai_confidence=contract.confidence,
        ai_summary=contract.summary,
        ai_keywords=contract.keywords,
        auto_confirm=False,
    )
    return {
        "encontrado": True,
        "tracking_code": row["tracking_code"],
        "analisis_completado": True,
        "diagnostico_ia_sugerido": contract.model_dump(),
        "confirmado_por_humano": bool(updated["human_confirmed"]) if updated else False,
        "nota": "Diagnóstico sugerido por IA; requiere confirmación humana para ser definitivo.",
        "router_meta": {"fallback_used": meta.get("fallback_used", False)},
    }


def tool_proponer_actualizacion_critica(args: dict[str, Any]) -> dict[str, Any]:
    ident = str(args.get("identificador") or "")
    nuevo_estado = str(args.get("nuevo_estado") or "IN_REVIEW").strip().upper()
    motivo = str(args.get("motivo") or "Solicitud generada por asistente").strip()

    if nuevo_estado not in ("CONFIRMED", "IN_REVIEW", "RESOLVED", "REJECTED"):
        return {
            "creado": False,
            "mensaje": f"Estado '{nuevo_estado}' no válido. Use CONFIRMED, IN_REVIEW, RESOLVED o REJECTED.",
        }

    row = _resolve_report_row(ident)
    if not row:
        return {
            "creado": False,
            "mensaje": f"No existe el reporte '{ident}' para proponer actualización.",
        }

    approval_id = uuid.uuid4()
    payload = {
        "tracking_code": row["tracking_code"],
        "previous_status": row["status"],
        "expected_version": int(row.get("version") or 1),
        "proposed_status": nuevo_estado,
    }
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pending_approvals (
                    id, report_id, proposed_action, proposed_payload, reason, status
                )
                VALUES (%s, %s, 'UPDATE_REPORT_STATUS', %s::jsonb, %s, 'PENDING');
                """,
                (approval_id, row["id"], json.dumps(payload, ensure_ascii=False), motivo[:500]),
            )
            conn.commit()
    if _ON_APPROVAL_CREATED_HOOK is not None:
        try:
            _ON_APPROVAL_CREATED_HOOK(approval_id)
        except Exception:
            pass

    return {
        "creado": True,
        "requiere_aprobacion_humana": True,
        "approval_id": str(approval_id),
        "tracking_code": row["tracking_code"],
        "estado_actual_reporte": row["status"],
        "estado_propuesto": nuevo_estado,
        "estado_aprobacion": "PENDING",
        "mensaje": (
            "Por límite de seguridad, la IA NO modifica directamente la base de datos de reportes. "
            f"Se creó la solicitud de aprobación humana #{str(approval_id)[:8]} en estado PENDING."
        ),
    }


TOOL_DISPATCH: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "consultar_reportes": tool_consultar_reportes,
    "obtener_reporte": tool_obtener_reporte,
    "clasificar_evidencia": tool_clasificar_evidencia,
    "proponer_actualizacion_critica": tool_proponer_actualizacion_critica,
}


def execute_tool_with_timeout(
    tool_name: str,
    tool_args: dict[str, Any],
    timeout_sec: float,
) -> dict[str, Any]:
    fn = TOOL_DISPATCH.get(tool_name)
    if fn is None:
        return {"error": f"Herramienta desconocida: {tool_name}"}

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn, tool_args)
    try:
        return future.result(timeout=timeout_sec)
    except FuturesTimeoutError as exc:
        raise TimeoutError(f"La herramienta '{tool_name}' superó el límite de {timeout_sec}s.") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _gemini_tools_declaration() -> list[dict[str, Any]]:
    decls = []
    for t in AGENT_TOOLS_SPEC:
        props = {}
        for k, v in t["parameters"]["properties"].items():
            gtype = "NUMBER" if v["type"] == "number" else "STRING"
            props[k] = {"type": gtype, "description": v["description"]}
        decls.append(
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": {
                    "type": "OBJECT",
                    "properties": props,
                    "required": t["parameters"].get("required", []),
                },
            }
        )
    return [{"functionDeclarations": decls}]


def _groq_tools_declaration() -> list[dict[str, Any]]:
    return [{"type": "function", "function": t} for t in AGENT_TOOLS_SPEC]


AGENT_SYSTEM_PROMPT = (
    "Eres el Agente de Consulta y Gestión de CIVIA para Cali y el Valle del Cauca.\n"
    "REGLAS ESTRICTAS:\n"
    "1. Usa SIEMPRE las herramientas disponibles (`consultar_reportes`, `obtener_reporte`, `clasificar_evidencia`, `proponer_actualizacion_critica`) para consultar datos reales en PostgreSQL antes de responder.\n"
    "2. JAMÁS inventes cifras, fechas, códigos de radicado, datos satelitales NDVI ni reportes inexistentes.\n"
    "3. Si la consulta pide datos que no están en la base de datos (ej. Comuna 99, sensores satelitales en tiempo real, radiación, video), responde claramente que NO existe evidencia registrada en la base de datos de CIVIA.\n"
    "4. Si el usuario pide cambiar el estado de un reporte, usa `proponer_actualizacion_critica` e informa que la acción quedó pendiente de aprobación humana.\n"
    "5. Responde en español claro, conciso y verificable citando los códigos `CIV-2026-...` cuando corresponda."
)


def _call_agent_turn_gemini(
    *,
    model: str,
    api_key: str,
    conversation_messages: list[dict[str, Any]],
    timeout_sec: float,
) -> tuple[str | None, list[dict[str, Any]], int, int]:
    if not api_key:
        raise AIProviderError("MISSING_API_KEY", "Clave Google no disponible.", retryable=False)

    eff_model = resolve_effective_gemini_model(model)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{eff_model}:generateContent?key={api_key}"
    contents: list[dict[str, Any]] = []
    for m in conversation_messages:
        role = m["role"]
        if role == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif role == "assistant_tool":
            if m.get("raw_gemini_part"):
                contents.append({"role": "model", "parts": [m["raw_gemini_part"]]})
            else:
                contents.append(
                    {
                        "role": "model",
                        "parts": [{"functionCall": {"name": m["name"], "args": m["args"]}}],
                    }
                )
        elif role == "tool_result":
            if m.get("had_gemini_part"):
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": m["name"],
                                    "response": {"result": m["result"]},
                                }
                            }
                        ],
                    }
                )
            else:
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": f"Resultado de herramienta {m['name']}: {json.dumps(m['result'], ensure_ascii=False)}"
                            }
                        ],
                    }
                )

    payload = {
        "systemInstruction": {"parts": [{"text": AGENT_SYSTEM_PROMPT}]},
        "contents": contents,
        "tools": _gemini_tools_declaration(),
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 700},
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=min(4.0, timeout_sec))) as client:
            resp = client.post(url, json=payload)
            if resp.status_code in (429, 503):
                alt_model = mark_gemini_model_exhausted(model)
                if alt_model != eff_model:
                    alt_url = f"https://generativelanguage.googleapis.com/v1beta/models/{alt_model}:generateContent?key={api_key}"
                    resp = client.post(alt_url, json=payload)
    except httpx.TimeoutException as exc:
        raise AIProviderError("TIMEOUT", "Timeout en llamada de agente a Gemini.", retryable=True) from exc
    except httpx.HTTPError as exc:
        raise AIProviderError("NETWORK_ERROR", f"Error red Gemini: {type(exc).__name__}", retryable=True) from exc

    if resp.status_code == 429:
        raise AIProviderError("HTTP_429", "Cuota 429 en Gemini.", retryable=True)
    if resp.status_code >= 500:
        raise AIProviderError(f"HTTP_{resp.status_code}", f"Error servidor Gemini {resp.status_code}", retryable=True)
    if resp.status_code >= 400:
        raise AIProviderError(f"HTTP_{resp.status_code}", f"Error solicitud Gemini {resp.status_code}", retryable=False)

    body = resp.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise AIProviderError("EMPTY_RESPONSE", "Sin candidatos en Gemini.", retryable=False)

    parts = (candidates[0].get("content") or {}).get("parts") or []
    tool_calls = []
    text_parts = []
    for p in parts:
        if "functionCall" in p:
            fc = p["functionCall"]
            tool_calls.append({"name": fc.get("name"), "args": fc.get("args") or {}, "raw_gemini_part": p})
        elif "text" in p and not p.get("thought"):
            text_parts.append(p["text"])

    usage = body.get("usageMetadata") or {}
    in_tok = int(usage.get("promptTokenCount") or 0)
    out_tok = int(usage.get("candidatesTokenCount") or 0)
    final_text = "\n".join(text_parts).strip() if text_parts else None
    return final_text, tool_calls, in_tok, out_tok


def _call_agent_turn_groq(
    *,
    model: str,
    api_key: str,
    conversation_messages: list[dict[str, Any]],
    timeout_sec: float,
) -> tuple[str | None, list[dict[str, Any]], int, int]:
    if not api_key:
        raise AIProviderError("MISSING_API_KEY", "Clave Groq no disponible.", retryable=False)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    messages: list[dict[str, Any]] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    for idx, m in enumerate(conversation_messages):
        role = m["role"]
        if role == "user":
            messages.append({"role": "user", "content": m["content"]})
        elif role == "assistant_tool":
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"call_{idx}",
                            "type": "function",
                            "function": {
                                "name": m["name"],
                                "arguments": json.dumps(m["args"], ensure_ascii=False),
                            },
                        }
                    ],
                }
            )
        elif role == "tool_result":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": f"call_{idx - 1}",
                    "name": m["name"],
                    "content": json.dumps(m["result"], ensure_ascii=False),
                }
            )

    payload = {
        "model": model,
        "messages": messages,
        "tools": _groq_tools_declaration(),
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": 700,
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=min(4.0, timeout_sec))) as client:
            resp = client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise AIProviderError("TIMEOUT", "Timeout en llamada de agente a Groq.", retryable=True) from exc
    except httpx.HTTPError as exc:
        raise AIProviderError("NETWORK_ERROR", f"Error red Groq: {type(exc).__name__}", retryable=True) from exc

    if resp.status_code == 429:
        raise AIProviderError("HTTP_429", "Cuota 429 en Groq.", retryable=True)
    if resp.status_code >= 500:
        raise AIProviderError(f"HTTP_{resp.status_code}", f"Error servidor Groq {resp.status_code}", retryable=True)
    if resp.status_code >= 400:
        raise AIProviderError(f"HTTP_{resp.status_code}", f"Error solicitud Groq {resp.status_code}", retryable=False)

    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise AIProviderError("EMPTY_RESPONSE", "Sin opciones en Groq.", retryable=False)

    msg = choices[0].get("message") or {}
    raw_tcs = msg.get("tool_calls") or []
    tool_calls = []
    for tc in raw_tcs:
        fn = tc.get("function") or {}
        try:
            parsed_args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            parsed_args = {}
        tool_calls.append({"name": fn.get("name"), "args": parsed_args})

    raw_content = (msg.get("content") or "").strip()
    # Limpiar bloques <think>...</think> si el modelo Qwen los incluye
    if "<think>" in raw_content and "</think>" in raw_content:
        raw_content = raw_content.split("</think>", 1)[-1].strip()

    usage = body.get("usage") or {}
    in_tok = int(usage.get("prompt_tokens") or 0)
    out_tok = int(usage.get("completion_tokens") or 0)
    return (raw_content or None), tool_calls, in_tok, out_tok


def _deterministic_sql_fallback_answer(query: str, tool_history: list[dict[str, Any]]) -> str:
    """
    Si todos los proveedores de IA fallan o se alcanza un límite tras ejecutar herramientas,
    construye una respuesta honesta y verificable a partir de PostgreSQL sin exponer errores técnicos.
    """
    q_up = query.upper()
    # Si aún no se ejecutó ninguna herramienta, ejecutar consulta directa según intención
    if not tool_history:
        import re

        code_match = re.search(r"CIV-\d{4}-[A-Z0-9]+", q_up)
        wants_status_change = any(
            w in q_up for w in ("CAMBIA", "ACTUALIZA", "PROPON", "MARCAR COMO", "PASAR A", "CAMBIAR")
        )
        if code_match and wants_status_change:
            new_st = "IN_REVIEW"
            for candidate_st in ("RESOLVED", "IN_REVIEW", "CONFIRMED", "REJECTED"):
                if candidate_st in q_up:
                    new_st = candidate_st
                    break
            targs = {
                "identificador": code_match.group(0),
                "nuevo_estado": new_st,
                "motivo": "Solicitud ciudadana procesada en modo determinista con aprobación humana obligatoria.",
            }
            res = tool_proponer_actualizacion_critica(targs)
            tool_history.append({"tool": "proponer_actualizacion_critica", "args": targs, "result": res})
        elif code_match:
            res = tool_obtener_reporte({"identificador": code_match.group(0)})
            tool_history.append({"tool": "obtener_reporte", "args": {"identificador": code_match.group(0)}, "result": res})
        else:
            args: dict[str, Any] = {}
            for cat in ("HUECO", "BASURAS", "TALA", "QUEMA"):
                if cat in q_up:
                    args["category"] = cat
                    break
            if "ANALYZED_PENDING_CONFIRMATION" in q_up or "PENDIENTES DE CONFIRMACIÓN" in q_up or "PENDIENTE DE CONFIRMACIÓN" in q_up:
                args["status"] = "ANALYZED_PENDING_CONFIRMATION"
            elif "PENDING_ANALYSIS" in q_up:
                args["status"] = "PENDING_ANALYSIS"
            elif "IN_REVIEW" in q_up or "EN REVISIÓN" in q_up:
                args["status"] = "IN_REVIEW"
            elif "RESOLVED" in q_up or "RESUELTO" in q_up:
                args["status"] = "RESOLVED"
            comuna_match = re.search(r"COMUNA\s+(\d+)", q_up)
            if comuna_match:
                args["comuna"] = f"Comuna {comuna_match.group(1)}"
            lat_match = re.search(r"LAT(?:ITUD)?\s*[:=]?\s*(-?\d+\.\d+)", q_up)
            lon_match = re.search(r"LON(?:GITUD)?\s*[:=]?\s*(-?\d+\.\d+)", q_up)
            rad_match = re.search(r"(\d+(?:\.\d+)?)\s*KM", q_up)
            if lat_match and lon_match:
                args["lat"] = float(lat_match.group(1))
                args["lon"] = float(lon_match.group(1))
                args["radius_km"] = float(rad_match.group(1)) if rad_match else 2.5
            if any(w in q_up for w in ("SATELITAL", "NDVI", "RADIACION", "RADIACIÓN", "NUCLEAR")):
                args["q"] = "NDVI_INEXISTENTE_999"
            res = tool_consultar_reportes(args)
            tool_history.append({"tool": "consultar_reportes", "args": args, "result": res})

    last = tool_history[-1]["result"]
    if "encontrado" in last:
        if not last["encontrado"]:
            return "No se encontró ningún reporte ni evidencia registrada en la base de datos con ese identificador."
        rep = last.get("reporte") or {}
        if rep:
            return (
                f"Reporte {rep['tracking_code']} ({rep['title']}): categoría {rep['effective_category'] or 'PENDIENTE'}, "
                f"severidad {rep['effective_severity'] or 'PENDIENTE'}, estado {rep['status']}, "
                f"ubicado en {rep.get('comuna') or 'Cali'} ({rep.get('neighborhood') or rep.get('address_hint') or ''})."
            )
    if "total_encontrados" in last:
        total = last["total_encontrados"]
        if total == 0:
            return "No existe evidencia ni reportes registrados en la base de datos de CIVIA para los criterios consultados (0 encontrados)."
        items = last.get("items") or []
        codigos = ", ".join(
            f"{it['tracking_code']} ({it['effective_category']}, {it.get('effective_severity')}, {it.get('comuna') or 'Cali'}, {it.get('neighborhood') or ''}, estado {it.get('status')})"
            for it in items[:5]
        )
        return f"Se encontraron {total} reporte(s) registrados en la base de datos: {codigos}."
    if last.get("requiere_aprobacion_humana"):
        return last.get("mensaje", "La solicitud de cambio de estado quedó registrada pendiente de aprobación humana.")
    return "Consulta procesada sobre la base de datos de reportes ciudadanos."


def run_civia_agent(
    query: str,
    *,
    max_iterations: int | None = None,
    max_tokens_budget: int | None = None,
    tool_timeout_seconds: float = 4.0,
    total_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """
    Ejecuta el agente CIVIA con herramientas tipadas y los 4 límites obligatorios:
    1) max_iterations (vueltas máximas)
    2) max_tokens_budget (presupuesto de tokens)
    3) tool_timeout_seconds / total_timeout_seconds (timeout por herramienta y global)
    4) human_approval_required (las escrituras críticas van a pending_approvals, nunca directo a reports)
    """
    trace_group_id = uuid.uuid4()
    eff_max_iter = max(1, int(max_iterations if max_iterations is not None else settings.AGENT_MAX_ITERATIONS))
    eff_max_tokens = max(50, int(max_tokens_budget if max_tokens_budget is not None else settings.AGENT_MAX_TOKENS))
    eff_total_timeout = float(total_timeout_seconds if total_timeout_seconds is not None else settings.AI_TIMEOUT_SECONDS)

    t_start = time.perf_counter()
    conversation: list[dict[str, Any]] = [{"role": "user", "content": query}]
    executed_tools: list[dict[str, Any]] = []
    iterations_used = 0
    total_tokens_used = 0
    prompt_tokens_used = 0
    completion_tokens_used = 0
    guardrail_triggered: str | None = None
    requires_human_approval = False
    pending_approval_id: str | None = None
    active_provider = "none"
    active_model = "none"
    fallback_used = False

    chain = get_provider_chain()

    for turn in range(1, eff_max_iter + 1):
        elapsed = time.perf_counter() - t_start
        if elapsed >= eff_total_timeout:
            guardrail_triggered = "TIMEOUT"
            break

        if total_tokens_used >= eff_max_tokens:
            guardrail_triggered = "MAX_TOKENS"
            break

        iterations_used = turn
        turn_text: str | None = None
        turn_tool_calls: list[dict[str, Any]] = []
        turn_succeeded = False

        ensure_at_least_one_circuit_openable(chain)
        for idx, node in enumerate(chain):
            provider = node["provider"]
            model = node["model"]
            api_key = node["api_key"]
            tier = node["tier"]

            cb = get_circuit(provider, model)
            if not cb.allow_request():
                continue

            t_call = time.perf_counter()
            remaining_sec = max(1.0, min(6.0, eff_total_timeout - (time.perf_counter() - t_start)))
            try:
                forced = _check_forced_fault(tier, provider)
                if forced is not None:
                    raise AIProviderError("INVALID_JSON", "JSON inválido forzado en turno de agente.", retryable=False)

                if provider == "google":
                    turn_text, turn_tool_calls, in_tok, out_tok = _call_agent_turn_gemini(
                        model=model,
                        api_key=api_key,
                        conversation_messages=conversation,
                        timeout_sec=remaining_sec,
                    )
                else:
                    turn_text, turn_tool_calls, in_tok, out_tok = _call_agent_turn_groq(
                        model=model,
                        api_key=api_key,
                        conversation_messages=conversation,
                        timeout_sec=remaining_sec,
                    )

                dt_ms = int((time.perf_counter() - t_call) * 1000)
                cb.record_success()
                prompt_tokens_used += in_tok
                completion_tokens_used += out_tok
                total_tokens_used += in_tok + out_tok
                active_provider = provider
                active_model = model
                if idx > 0:
                    fallback_used = True
                turn_succeeded = True

                _safe_record_trace(
                    trace_group_id=trace_group_id,
                    operation="agent_turn",
                    provider=provider,
                    model=model,
                    attempt_number=turn,
                    success=True,
                    latency_ms=dt_ms,
                    prompt_tokens=in_tok,
                    completion_tokens=out_tok,
                    tool_calls=[{"name": tc["name"], "args": tc.get("args") or {}} for tc in turn_tool_calls],
                    metadata={"turn": turn, "tier": tier, "fallback_used": fallback_used},
                )
                break
            except AIProviderError as exc:
                dt_ms = int((time.perf_counter() - t_call) * 1000)
                cb.record_failure(exc.code)
                _safe_record_trace(
                    trace_group_id=trace_group_id,
                    operation="agent_turn",
                    provider=provider,
                    model=model,
                    attempt_number=turn,
                    success=False,
                    latency_ms=dt_ms,
                    error_code=exc.code,
                    error_detail=exc.message,
                    metadata={"turn": turn, "tier": tier},
                )
                fallback_used = True
                continue
            except Exception as exc:
                dt_ms = int((time.perf_counter() - t_call) * 1000)
                cb.record_failure("UNEXPECTED_ERROR")
                _safe_record_trace(
                    trace_group_id=trace_group_id,
                    operation="agent_turn",
                    provider=provider,
                    model=model,
                    attempt_number=turn,
                    success=False,
                    latency_ms=dt_ms,
                    error_code="UNEXPECTED_ERROR",
                    error_detail=type(exc).__name__,
                    metadata={"turn": turn, "tier": tier},
                )
                fallback_used = True
                continue

        if not turn_succeeded:
            # Caída total de proveedores IA: responder con respaldo SQL determinista sin error técnico
            answer = _deterministic_sql_fallback_answer(query, executed_tools)
            for et in executed_tools:
                res_obj = et.get("result") or {}
                if res_obj.get("requiere_aprobacion_humana"):
                    requires_human_approval = True
                    pending_approval_id = res_obj.get("approval_id")
                    guardrail_triggered = guardrail_triggered or "HUMAN_APPROVAL_REQUIRED"
            total_ms = int((time.perf_counter() - t_start) * 1000)
            return {
                "answer": answer,
                "trace_group_id": str(trace_group_id),
                "tools_invoked": executed_tools,
                "iterations_used": iterations_used,
                "max_iterations": eff_max_iter,
                "total_tokens_used": total_tokens_used,
                "max_tokens_budget": eff_max_tokens,
                "latency_ms": total_ms,
                "guardrail_triggered": guardrail_triggered,
                "requires_human_approval": requires_human_approval,
                "pending_approval_id": pending_approval_id,
                "degraded_sql_mode": True,
            }

        # Verificar presupuesto de tokens tras recibir respuesta del modelo
        if total_tokens_used > eff_max_tokens:
            guardrail_triggered = "MAX_TOKENS"
            break

        # Si el modelo no pidió más herramientas y dio respuesta final
        if not turn_tool_calls:
            final_answer = turn_text or _deterministic_sql_fallback_answer(query, executed_tools)
            # Garantizar trazabilidad de radicados verificados por SQL cuando la herramienta encontró <= 5 reportes
            for et in executed_tools:
                res_obj = et.get("result") or {}
                if res_obj.get("encontrado") and isinstance(res_obj.get("reporte"), dict):
                    rep = res_obj["reporte"]
                    tcode = rep.get("tracking_code", "")
                    if tcode and tcode not in final_answer:
                        final_answer += f" [Radicado SQL: {tcode} · {rep.get('effective_category')} · {rep.get('effective_severity')} · {rep.get('comuna')} · {rep.get('status')}]"
                elif 0 < int(res_obj.get("total_encontrados", 0)) <= 5:
                    items = res_obj.get("items") or []
                    missing_codes = [
                        f"{it['tracking_code']} ({it.get('effective_category')}, {it.get('comuna')}, {it.get('neighborhood')}, {it.get('status')})"
                        for it in items
                        if it.get("tracking_code") and it["tracking_code"] not in final_answer
                    ]
                    if missing_codes:
                        final_answer += " [Registros SQL verificados: " + "; ".join(missing_codes) + "]"
            total_ms = int((time.perf_counter() - t_start) * 1000)
            return {
                "answer": sanitize_citizen_agent_output(final_answer),
                "trace_group_id": str(trace_group_id),
                "tools_invoked": executed_tools,
                "iterations_used": iterations_used,
                "max_iterations": eff_max_iter,
                "total_tokens_used": total_tokens_used,
                "max_tokens_budget": eff_max_tokens,
                "latency_ms": total_ms,
                "guardrail_triggered": guardrail_triggered,
                "requires_human_approval": requires_human_approval,
                "pending_approval_id": pending_approval_id,
                "degraded_sql_mode": False,
            }

        # Ejecutar cada herramienta solicitada con control de timeout por herramienta
        for tc in turn_tool_calls:
            tname = tc["name"]
            targs = tc.get("args") or {}
            raw_gpart = tc.get("raw_gemini_part")
            conversation.append(
                {
                    "role": "assistant_tool",
                    "name": tname,
                    "args": targs,
                    "raw_gemini_part": raw_gpart,
                }
            )
            try:
                t_res = execute_tool_with_timeout(tname, targs, timeout_sec=tool_timeout_seconds)
            except TimeoutError as exc:
                guardrail_triggered = "TIMEOUT"
                _safe_record_trace(
                    trace_group_id=trace_group_id,
                    operation="tool_timeout",
                    provider=active_provider,
                    model=active_model,
                    attempt_number=turn,
                    success=False,
                    latency_ms=int(tool_timeout_seconds * 1000),
                    error_code="TOOL_TIMEOUT",
                    error_detail=str(exc),
                )
                break

            if t_res.get("requiere_aprobacion_humana"):
                requires_human_approval = True
                pending_approval_id = t_res.get("approval_id")
                guardrail_triggered = "HUMAN_APPROVAL_REQUIRED"

            executed_tools.append({"tool": tname, "args": targs, "result": t_res})
            conversation.append(
                {
                    "role": "tool_result",
                    "name": tname,
                    "result": t_res,
                    "had_gemini_part": bool(raw_gpart),
                }
            )

        if guardrail_triggered == "TIMEOUT":
            break

        if turn >= eff_max_iter:
            guardrail_triggered = guardrail_triggered or "MAX_ITERATIONS"
            break

    # Si salimos del bucle por alcanzar un guardrail (MAX_ITERATIONS, MAX_TOKENS, TIMEOUT o HUMAN_APPROVAL_REQUIRED)
    answer = _deterministic_sql_fallback_answer(query, executed_tools)
    total_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "answer": answer,
        "trace_group_id": str(trace_group_id),
        "tools_invoked": executed_tools,
        "iterations_used": iterations_used,
        "max_iterations": eff_max_iter,
        "total_tokens_used": total_tokens_used,
        "max_tokens_budget": eff_max_tokens,
        "latency_ms": total_ms,
        "guardrail_triggered": guardrail_triggered,
        "requires_human_approval": requires_human_approval,
        "pending_approval_id": pending_approval_id,
        "degraded_sql_mode": False,
    }


def list_pending_approvals(status: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    """
                    SELECT pa.*, r.tracking_code, r.title, r.status AS current_report_status
                    FROM pending_approvals pa
                    JOIN reports r ON r.id = pa.report_id
                    WHERE pa.status = %s
                    ORDER BY pa.created_at DESC;
                    """,
                    (status.upper(),),
                )
            else:
                cur.execute(
                    """
                    SELECT pa.*, r.tracking_code, r.title, r.status AS current_report_status
                    FROM pending_approvals pa
                    JOIN reports r ON r.id = pa.report_id
                    ORDER BY pa.created_at DESC;
                    """
                )
            return cur.fetchall()


def decide_pending_approval(
    approval_id: UUID | str,
    *,
    approve: bool,
    decided_by: str = "operador-humano",
) -> dict[str, Any] | None:
    aid = UUID(str(approval_id))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pending_approvals WHERE id = %s FOR UPDATE;", (aid,))
            row = cur.fetchone()
            if not row:
                return None
            if row["status"] != "PENDING":
                return row

            cur.execute("SELECT * FROM reports WHERE id = %s FOR UPDATE;", (row["report_id"],))
            report_row = cur.fetchone()

            payload = row["proposed_payload"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            elif not isinstance(payload, dict):
                payload = {}

            expected_status = payload.get("previous_status")
            expected_version = payload.get("expected_version")
            proposed_status = payload.get("proposed_status", "IN_REVIEW")

            has_valid_expected_version = (
                isinstance(expected_version, int)
                and not isinstance(expected_version, bool)
                and expected_version >= 1
            )

            is_stale = False
            if approve:
                if report_row is None:
                    is_stale = True
                elif not isinstance(expected_status, str) or not expected_status.strip():
                    is_stale = True
                elif not has_valid_expected_version:
                    is_stale = True
                elif report_row["status"] != expected_status:
                    is_stale = True
                elif int(report_row.get("version") or 1) != int(expected_version):
                    is_stale = True

            if approve and is_stale:
                cur.execute(
                    """
                    UPDATE pending_approvals
                    SET status = 'REJECTED',
                        decided_by = %s,
                        decided_at = NOW(),
                        reason = LEFT(reason || ' [Rechazada automáticamente por obsolescencia: el estado o versión del reporte cambió previamente]', 500)
                    WHERE id = %s AND status = 'PENDING'
                    RETURNING *;
                    """,
                    (decided_by, aid),
                )
                stale_pa = cur.fetchone() or row
                stale_pa["stale_conflict"] = True
                conn.commit()
                return stale_pa

            new_decision = "APPROVED" if approve else "REJECTED"
            cur.execute(
                """
                UPDATE pending_approvals
                SET status = %s,
                    decided_by = %s,
                    decided_at = NOW()
                WHERE id = %s AND status = 'PENDING'
                RETURNING *;
                """,
                (new_decision, decided_by, aid),
            )
            updated_pa = cur.fetchone()
            if not updated_pa:
                return row

            if approve:
                cur.execute(
                    """
                    UPDATE reports
                    SET status = %s,
                        human_override_note = %s,
                        version = COALESCE(version, 1) + 1,
                        updated_at = NOW()
                    WHERE id = %s
                      AND status = %s
                      AND COALESCE(version, 1) = %s
                    RETURNING id;
                    """,
                    (
                        proposed_status,
                        f"Aprobado por humano ({decided_by}): {row['reason']}",
                        row["report_id"],
                        expected_status,
                        int(expected_version),
                    ),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        """
                        UPDATE pending_approvals
                        SET status = 'REJECTED',
                            decided_by = %s,
                            decided_at = NOW(),
                            reason = LEFT(reason || ' [Rechazada automáticamente por obsolescencia: el estado o versión del reporte cambió previamente]', 500)
                        WHERE id = %s
                        RETURNING *;
                        """,
                        (decided_by, aid),
                    )
                    stale_pa = cur.fetchone() or updated_pa
                    stale_pa["stale_conflict"] = True
                    conn.commit()
                    return stale_pa
            updated_pa["stale_conflict"] = False
            conn.commit()
            return updated_pa
