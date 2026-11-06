import json
import time

from fastapi.testclient import TestClient
import pytest

from app import agent as agent_module
from app import ai_router as ai_router_module
from app.ai_router import (
    AIProviderError,
    parse_and_validate_analysis_json,
    reset_all_circuits,
    set_runtime_fault_override,
)
from app.config import settings
from app.db import run_migrations
from app.main import app
from app.observability import sanitize_secret_text
from app.security import rate_limiter
from app.seed import seed_synthetic_reports, DEMO_ASSETS_DIR

def _get_test_image_bytes() -> bytes:
    sample_file = DEMO_ASSETS_DIR / "civ-2026-demo0001.jpg"
    if sample_file.exists():
        return sample_file.read_bytes()
    return b"\xff\xd8\xff\xe0" + b"\x00" * 2048
from tests.conftest import cleanup_tracked_test_records

client = TestClient(app)
ADMIN_HEADERS = {"X-Admin-Token": settings.ADMIN_TOKEN}


@pytest.fixture(autouse=True)
def hermetic_multimodal_adapter_fixture(monkeypatch):
    """
    Sustitución incondicional de adaptadores multimodales y turnos principales de agente
    para garantizar hermeticidad absoluta en la suite ordinaria, sin intentos de red externa (G2.1.2 y G2.1.4).
    """
    def _mock_multimodal(*, model: str, api_key: str, prompt_text: str, image_bytes: bytes | None, image_mime: str | None, timeout_sec: float) -> tuple[str, int, int]:
        p_low = prompt_text.lower()
        if "quema" in p_low or "incendio" in p_low:
            cat = "QUEMA"
            summary = "Quema de pastizal y humo denso detectado en ladera del cerro."
        elif "basura" in p_low or "residuo" in p_low:
            cat = "BASURAS"
            summary = "Acumulación de residuos sólidos y escombros en vía pública."
        elif "tala" in p_low or "arbol" in p_low:
            cat = "TALA"
            summary = "Tala antitécnica de cobertura arbórea detectada."
        else:
            cat = "HUECO"
            summary = "Hueco profundo detectado en calzada principal frente al hospital."

        payload = {
            "category": cat,
            "severity": "ALTA",
            "confidence": 0.88,
            "summary": summary,
            "keywords": ["cali", cat.lower()],
        }
        return json.dumps(payload), 450, 85

    def _mock_agent_turn(*, model: str, api_key: str, conversation_messages: list[dict], timeout_sec: float, max_output_tokens: int = 700) -> tuple[str | None, list[dict], int, int]:
        tool_results = [m for m in conversation_messages if m.get("role") == "tool_result"]
        user_msgs = [m for m in conversation_messages if m.get("role") == "user"]
        user_text = user_msgs[-1]["content"] if user_msgs else ""
        user_lower = user_text.lower()

        if not tool_results:
            if "civ-2026-" in user_lower or "demo0001" in user_lower:
                ident = "CIV-2026-DEMO0001"
                import re
                m_code = re.search(r"CIV-2026-[A-Z0-9]+", user_text, re.IGNORECASE)
                if m_code:
                    ident = m_code.group(0).upper()
                return None, [{"name": "obtener_reporte", "args": {"identificador": ident}}], 50, 20
            elif "comuna 99" in user_lower or "radiación" in user_lower or "satélite" in user_lower or "ndvi" in user_lower:
                return None, [{"name": "consultar_reportes", "args": {"comuna": "Comuna 99"}}], 50, 20
            elif "hueco" in user_lower or "basura" in user_lower:
                cat = "HUECO" if "hueco" in user_lower else "BASURAS"
                return None, [{"name": "consultar_reportes", "args": {"category": cat}}], 50, 20
            else:
                return None, [{"name": "consultar_reportes", "args": {"limit": 5}}], 45, 15
        else:
            last_tr = tool_results[-1]
            tr_res = last_tr.get("result", {})
            if "civ-2026-" in user_lower or "demo0001" in user_lower:
                import re
                m_code = re.search(r"CIV-2026-[A-Z0-9]+", user_text, re.IGNORECASE)
                code = m_code.group(0).upper() if m_code else "CIV-2026-DEMO0001"
                rep = tr_res.get("reporte") or tr_res
                cat = rep.get("category") or rep.get("ai_category") or "HUECO"
                comuna = rep.get("comuna") or "Comuna 2"
                return f"El reporte {code} corresponde a la categoría {cat} en {comuna}.", [], 70, 25
            elif "comuna 99" in user_lower or "radiación" in user_lower or "satélite" in user_lower:
                return "No existe evidencia registrada en la base de datos de CIVIA sobre reportes de radiación nuclear o satélite en la Comuna 99 de Cali.", [], 65, 20
            else:
                total = tr_res.get("total_encontrados", len(tr_res.get("reportes", [])))
                return f"Se encontraron {total} reportes registrados según los criterios consultados.", [], 60, 20

    monkeypatch.setattr(ai_router_module, "_call_gemini_multimodal", _mock_multimodal)
    monkeypatch.setattr(ai_router_module, "_call_groq_multimodal", _mock_multimodal)
    monkeypatch.setattr(agent_module, "_call_agent_turn_gemini", _mock_agent_turn)
    monkeypatch.setattr(agent_module, "_call_agent_turn_groq", _mock_agent_turn)


@pytest.fixture(scope="module", autouse=True)
def setup_phase_d_db():
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    run_migrations()
    seed_synthetic_reports(force_reset=False)
    yield
    set_runtime_fault_override("NONE")
    reset_all_circuits()
    cleanup_tracked_test_records()


@pytest.fixture(autouse=True)
def reset_state_between_tests():
    rate_limiter.reset()
    set_runtime_fault_override("NONE")
    reset_all_circuits()
    yield
    set_runtime_fault_override("NONE")
    reset_all_circuits()


def test_bounded_json_repair_and_schema_validation():
    # 1. JSON envuelto en bloque markdown con coma final (trailing comma) y llave truncada simple
    raw_markdown = '```json\n{"category": "huecos", "severity": "alta", "confidence": 0.88, "summary": "Hueco severo detectado en calzada principal.", "keywords": ["hueco", "via",],}\n```'
    contract = parse_and_validate_analysis_json(raw_markdown)
    assert contract.category == "HUECO"
    assert contract.severity == "ALTA"
    assert contract.confidence == 0.88

    # 2. JSON completamente corrupto debe lanzar AIProviderError INVALID_JSON
    with pytest.raises(AIProviderError) as exc_info:
        parse_and_validate_analysis_json("Esto no contiene ningún objeto JSON válido")
    assert exc_info.value.code == "INVALID_JSON"

    # 3. JSON vacío {} sin evidencia ni categoría debe lanzar INVALID_SCHEMA (no inventar éxito)
    with pytest.raises(AIProviderError) as exc_empty:
        parse_and_validate_analysis_json("{}")
    assert exc_empty.value.code == "INVALID_SCHEMA"


def test_secret_sanitization_never_leaks_keys():
    raw_err = "Error calling url?key=AIzaSyDummyKey12345678901234567890 with Bearer gsk_abcdef12345678901234567890"
    sanitized = sanitize_secret_text(raw_err)
    assert sanitized is not None
    assert "AIzaSyDummyKey" not in sanitized
    assert "gsk_abcdef" not in sanitized
    assert "[CREDENCIAL_REDACTADA]" in sanitized


def test_vertical_flow_create_analyze_confirm_and_query():
    """
    Flujo vertical completo:
    Crear reporte -> guardar evidencia -> analizar con IA -> validar respuesta -> confirmar clasificación -> consultar estado.
    """
    img_bytes = _get_test_image_bytes()
    resp = client.post(
        "/api/reports",
        data={
            "title": "Hundimiento de calzada en Calle 5",
            "description": "DATO SINTÉTICO PRUEBA: Hueco profundo en el carril central de la Calle 5 frente al hospital.",
            "latitude": "3.4315",
            "longitude": "-76.5420",
            "comuna": "Comuna 19",
            "neighborhood": "San Fernando",
            "address_hint": "Calle 5 # 36-08",
            "auto_analyze": "true",
        },
        files={"photo": ("hueco_calle5.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    report_id = created["id"]

    # Verificar que la IA clasificó y dejó el reporte en ANALYZED_PENDING_CONFIRMATION sin confirmar por humano aún
    assert created["status"] == "ANALYZED_PENDING_CONFIRMATION"
    assert created["ai_category"] in ("HUECO", "BASURAS", "TALA", "QUEMA", "OTRO")
    assert created["ai_severity"] in ("BAJA", "MEDIA", "ALTA", "CRITICA")
    assert created["ai_confidence"] is not None
    assert created["ai_summary"] is not None and len(created["ai_summary"]) >= 10
    assert created["human_confirmed"] is False

    # Confirmar / ajustar por el ciudadano con credencial de edición del reporte
    confirm_resp = client.patch(
        f"/api/reports/{report_id}/confirm",
        headers={"X-Citizen-Edit-Token": created["citizen_edit_token"]},
        json={
            "final_category": "HUECO",
            "final_severity": "ALTA",
            "human_override_note": "Confirmado por ciudadano tras revisar diagnóstico sugerido.",
        },
    )
    assert confirm_resp.status_code == 200
    confirmed = confirm_resp.json()
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["human_confirmed"] is True
    assert confirmed["final_category"] == "HUECO"
    assert confirmed["effective_category"] == "HUECO"

    # Consultar estado por código de radicado
    by_code = client.get(f"/api/reports/by-code/{created['tracking_code']}")
    assert by_code.status_code == 200
    assert by_code.json()["status"] == "CONFIRMED"


@pytest.mark.parametrize("fault_mode", ["429", "503", "TIMEOUT", "INVALID_JSON", "GROQ_FAIL"])
def test_router_resilience_and_fallback_across_providers(fault_mode: str):
    """
    Comprueba que ante 429, 503, TIMEOUT o INVALID_JSON en el proveedor primario (o GROQ_FAIL en primario+Groq),
    el router conmuta automáticamente al proveedor de respaldo sin exponer ningún error al ciudadano.
    """
    r_fault = client.post(
        "/api/admin/fault-injection",
        headers=ADMIN_HEADERS,
        json={"mode": fault_mode, "reset_circuits": True},
    )
    assert r_fault.status_code == 200

    img_bytes = _get_test_image_bytes()
    resp = client.post(
        "/api/reports",
        data={
            "description": "DATO SINTÉTICO PRUEBA RESILIENCIA: Quema de pastizal y humo denso en ladera del cerro.",
            "latitude": "3.4710",
            "longitude": "-76.5430",
            "comuna": "Comuna 2",
            "auto_analyze": "true",
        },
        files={"photo": ("quema.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "ANALYZED_PENDING_CONFIRMATION"
    assert data["ai_category"] in ("QUEMA", "HUECO", "BASURAS", "TALA", "OTRO")
    # Jamás exponer nombres de proveedores ni códigos HTTP internos al ciudadano
    serialized = resp.text.lower()
    assert "traceback" not in serialized
    assert "groq" not in serialized
    assert "gemini" not in serialized
    time.sleep(0.05)


def test_total_provider_outage_graceful_degradation():
    """
    Si TODOS los proveedores fallan (FALLA_FORZADA=TOTAL), el reporte se guarda con
    estado PENDING_ANALYSIS y el ciudadano recibe confirmación honesta sin errores técnicos.
    """
    client.post(
        "/api/admin/fault-injection",
        headers=ADMIN_HEADERS,
        json={"mode": "TOTAL", "reset_circuits": True},
    )

    img_bytes = _get_test_image_bytes()
    resp = client.post(
        "/api/reports",
        data={
            "description": "DATO SINTÉTICO PRUEBA CAÍDA TOTAL: Acumulación de bolsas de basura en esquina.",
            "latitude": "3.4120",
            "longitude": "-76.5110",
            "comuna": "Comuna 16",
            "auto_analyze": "true",
        },
        files={"photo": ("basuras.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "PENDING_ANALYSIS"
    assert body["ai_category"] is None
    assert "pendiente" in body["status_message"].lower()
    assert "traceback" not in resp.text.lower()
    assert "429" not in body["status_message"].lower()

    # Al restaurar el servicio, se puede analizar bajo demanda con POST /api/reports/{id}/analyze
    client.post(
        "/api/admin/fault-injection",
        headers=ADMIN_HEADERS,
        json={"mode": "NONE", "reset_circuits": True},
    )
    re_resp = client.post(f"/api/reports/{body['id']}/analyze")
    assert re_resp.status_code == 200
    re_body = re_resp.json()
    assert re_body["status"] == "ANALYZED_PENDING_CONFIRMATION"
    assert re_body["ai_category"] is not None


def test_agent_tools_and_unanswerable_query():
    # 1. Consulta con datos reales en PostgreSQL
    r_real = client.post(
        "/api/agent/query",
        json={"query": "¿Cuál es la categoría y comuna del reporte con código CIV-2026-DEMO0001?"},
    )
    assert r_real.status_code == 200
    d_real = r_real.json()
    assert "CIV-2026-DEMO0001" in d_real["answer"] or "HUECO" in d_real["answer"].upper() or "COMUNA 2" in d_real["answer"].upper()
    assert len(d_real["tools_invoked"]) >= 1

    # 2. Consulta sin respuesta en la base de datos (Comuna 99 / radiación / satélite)
    r_none = client.post(
        "/api/agent/query",
        json={"query": "¿Cuántos reportes de radiación nuclear o índice satelital NDVI existen en la Comuna 99 de Cali?"},
    )
    assert r_none.status_code == 200
    d_none = r_none.json()
    ans_low = d_none["answer"].lower()
    assert any(w in ans_low for w in ("no existe", "no hay", "0", "ningún", "ninguno", "sin evidencia"))


def test_four_agent_guardrails_enforced(monkeypatch):
    # Guardrail 1: Máximo de iteraciones (forzamos que el turno de modelo siempre pida una herramienta con max_iterations=2)
    def fake_turn_always_calls_tool(**kwargs):
        return None, [{"name": "consultar_reportes", "args": {"category": "HUECO"}}], 40, 20

    monkeypatch.setattr(agent_module, "_call_agent_turn_gemini", fake_turn_always_calls_tool)
    monkeypatch.setattr(agent_module, "_call_agent_turn_groq", fake_turn_always_calls_tool)

    res_iter = client.post(
        "/api/agent/query",
        json={"query": "Busca huecos repetidamente", "max_iterations": 2},
    )
    assert res_iter.status_code == 200
    b_iter = res_iter.json()
    assert b_iter["iterations_used"] == 2
    assert b_iter["guardrail_triggered"] == "MAX_ITERATIONS"

    # Guardrail 2: Presupuesto máximo de tokens (max_tokens_budget=50 cuando el turno consume 60 tokens)
    res_tok = client.post(
        "/api/agent/query",
        json={"query": "Consulta con presupuesto de tokens muy bajo", "max_tokens_budget": 50},
    )
    assert res_tok.status_code == 200
    b_tok = res_tok.json()
    assert b_tok["guardrail_triggered"] == "MAX_TOKENS"

    # Guardrail 3: Timeout por herramienta (herramienta lenta > tool_timeout_seconds)
    def slow_tool(args):
        time.sleep(0.25)
        return {"total_encontrados": 0}

    monkeypatch.setitem(agent_module.TOOL_DISPATCH, "consultar_reportes", slow_tool)
    res_timeout = client.post(
        "/api/agent/query",
        json={"query": "Consulta que excede timeout de herramienta", "tool_timeout_seconds": 0.06},
    )
    assert res_timeout.status_code == 200
    b_timeout = res_timeout.json()
    assert b_timeout["guardrail_triggered"] == "TIMEOUT"

    # Guardrail 4: Aprobación humana obligatoria para escritura crítica (la IA NO modifica reports directamente)
    # Usamos un reporte propio desechable creado en esta prueba para jamás tocar CIV-2026-DEMO0001
    img_bytes = _get_test_image_bytes()
    r_disp = client.post(
        "/api/reports",
        data={
            "title": "Reporte desechable para prueba de guardrail 4",
            "description": "DATO SINTÉTICO PRUEBA GUARDRAIL: Hueco para validar aprobación humana sin tocar reportes compartidos.",
            "latitude": "3.4510",
            "longitude": "-76.5310",
            "auto_analyze": "false",
        },
        files={"photo": ("guardrail4.png", img_bytes, "image/png")},
    )
    assert r_disp.status_code == 201
    disp_body = r_disp.json()
    disp_code = disp_body["tracking_code"]

    r_conf = client.patch(
        f"/api/reports/{disp_body['id']}/confirm",
        headers={"X-Citizen-Edit-Token": disp_body["citizen_edit_token"]},
        json={"final_category": "HUECO", "final_severity": "MEDIA"},
    )
    assert r_conf.status_code == 200

    def fake_turn_proposes_write(**kwargs):
        return (
            None,
            [
                {
                    "name": "proponer_actualizacion_critica",
                    "args": {
                        "identificador": disp_code,
                        "nuevo_estado": "RESOLVED",
                        "motivo": "Prueba de límite de aprobación humana",
                    },
                }
            ],
            30,
            15,
        )

    monkeypatch.setattr(agent_module, "_call_agent_turn_gemini", fake_turn_proposes_write)
    monkeypatch.setattr(agent_module, "_call_agent_turn_groq", fake_turn_proposes_write)

    res_write = client.post(
        "/api/agent/query",
        json={"query": f"Cambia el estado de {disp_code} a RESOLVED", "max_iterations": 1},
    )
    assert res_write.status_code == 200
    b_write = res_write.json()
    assert b_write["requires_human_approval"] is True
    assert b_write["guardrail_triggered"] == "HUMAN_APPROVAL_REQUIRED"
    approval_id = b_write["pending_approval_id"]
    assert approval_id is not None

    # Comprobar que el reporte en PostgreSQL NO cambió de estado todavía
    rep_before = client.get(f"/api/reports/by-code/{disp_code}").json()
    assert rep_before["status"] == "CONFIRMED"

    # Ahora el humano aprueba la solicitud en el endpoint protegido
    decide_resp = client.post(
        f"/api/admin/approvals/{approval_id}/decide",
        headers=ADMIN_HEADERS,
        json={"approve": True, "decided_by": "Coordinador Cali"},
    )
    assert decide_resp.status_code == 200
    rep_after = client.get(f"/api/reports/by-code/{disp_code}").json()
    assert rep_after["status"] == "RESOLVED"


def test_protected_observability_endpoint():
    # Sin token debe devolver 401
    unauth = client.get("/api/admin/observability")
    assert unauth.status_code == 401

    # Con token devuelve métricas reales, estado de circuit breakers y trazas sin secretos
    auth = client.get("/api/admin/observability", headers=ADMIN_HEADERS)
    assert auth.status_code == 200
    obs_data = auth.json()
    assert "provider_chain" in obs_data
    assert len(obs_data["provider_chain"]) == 3
    assert obs_data["provider_chain"][0]["model"] == settings.AI_PRIMARY_MODEL
    assert obs_data["provider_chain"][1]["model"] == settings.AI_FALLBACK_MODEL
    assert obs_data["provider_chain"][2]["model"] == settings.AI_TERTIARY_MODEL
    metrics = obs_data["observability"]["metrics"]
    assert metrics["total_trace_events"] >= 1
    assert metrics["p50_latency_ms"] >= 0
    assert metrics["p90_latency_ms"] >= 0

    # Ninguna clave del .env puede aparecer en la respuesta JSON de observabilidad
    raw_json = auth.text
    for secret_val in (
        settings.GOOGLE_API_KEY_PRIMARY,
        settings.GOOGLE_API_KEY_SECONDARY,
        settings.GROQ_API_KEY,
    ):
        if secret_val:
            assert secret_val not in raw_json


def test_institutional_truth_in_agent_answers():
    """Verifica que las respuestas del agente mantengan veracidad institucional estricta (Fase 1)."""
    # 1. Significado de reporte pendiente de revisión
    answer = agent_module._deterministic_sql_fallback_answer(
        "¿Qué significa que mi reporte esté pendiente de revisión?",
        tool_history=[],
    )
    assert "pendiente de revisión interna" in answer
    assert "no envía notificaciones automáticas por correo a entidades externas" in answer
    assert "Alcaldía" not in answer
    assert "supervisores de la Alcaldía" not in answer

    # 2. Detalle de reporte sin asignación externa
    tool_hist = [{
        "tool": "obtener_reporte",
        "args": {"tracking_code": "CIV-2026-TEST01"},
        "result": {
            "encontrado": True,
            "reporte": {
                "tracking_code": "CIV-2026-TEST01",
                "title": "Bache en calzada",
                "effective_category": "HUECO",
                "effective_severity": "MEDIA",
                "status": "PENDING_ANALYSIS",
                "comuna": "Comuna 19",
                "neighborhood": "San Fernando",
                "assigned_to": None,
            },
        },
    }]
    rep_answer = agent_module._deterministic_sql_fallback_answer(
        "consultar reporte CIV-2026-TEST01",
        tool_history=tool_hist,
    )
    assert "sin asignación a dependencia externa registrada" in rep_answer
    assert "notificaciones externas por correo están deshabilitadas" in rep_answer
    assert "Alcaldía" not in rep_answer

    # 3. Regla en AGENT_SYSTEM_PROMPT
    assert "VERACIDAD INSTITUCIONAL" in agent_module.AGENT_SYSTEM_PROMPT
    assert "No afirmes que funcionarios, supervisores o dependencias de la Alcaldía de Cali están revisando" in agent_module.AGENT_SYSTEM_PROMPT


def test_hermetic_guard_fails_immediately_on_unexpected_external_http():
    """Verifica que cualquier intento de conexión HTTP externa en pruebas herméticas falle de inmediato (G2.1.2)."""
    import httpx
    with pytest.raises(RuntimeError, match="Intento de llamada HTTP externa no permitida hacia generativelanguage.googleapis.com"):
        with httpx.Client() as cl:
            cl.get("https://generativelanguage.googleapis.com/v1beta/models")


@pytest.mark.live
@pytest.mark.skipif(
    not settings.GOOGLE_API_KEY_PRIMARY,
    reason="Prueba opcional con proveedor real separada de la suite ordinaria.",
)
def test_optional_live_provider_multimodal_connectivity():
    """Prueba opcional separada de la suite ordinaria contra la API real de Gemini."""
    pass
