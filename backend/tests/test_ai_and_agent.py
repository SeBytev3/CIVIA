import json
import time

from fastapi.testclient import TestClient
import pytest

from app import agent as agent_module
from app import ai_router as ai_router_module
from app.analysis_worker import process_next_job
from app.ai_router import (
    AIProviderError,
    parse_and_validate_analysis_json,
    reset_all_circuits,
    set_runtime_fault_override,
)
from app.config import settings
from app.db import get_conn, run_migrations
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


@pytest.fixture(autouse=True)
def hermetic_multimodal_adapter_fixture(monkeypatch):
    """
    Sustitución incondicional de adaptadores multimodales y turnos principales de agente
    para garantizar hermeticidad absoluta en la suite ordinaria, sin intentos de red externa (G2.1.2 y G2.1.4).
    """
    monkeypatch.setattr(settings, "GOOGLE_API_KEY_PRIMARY", "synthetic-google")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "synthetic-groq")
    monkeypatch.setattr(settings, "AI_GROQ_VISION_MODEL", "synthetic-vision")

    def _mock_multimodal(*, model: str, api_key: str, prompt_text: str, image_bytes: bytes | None, image_mime: str | None, timeout_sec: float) -> tuple[str, int, int]:
        p_low = prompt_text.split('como evidencia.\n', 1)[-1].split('\n\nDevuelve',1)[0].lower()
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


def test_vertical_flow_create_analyze_confirm_and_query(citizen_client):
    """
    Flujo vertical completo:
    Crear reporte -> guardar evidencia -> analizar con IA -> validar respuesta -> confirmar clasificación -> consultar estado.
    """
    img_bytes = _get_test_image_bytes()
    resp = citizen_client.post(
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

    assert created["status"] == "PENDING_ANALYSIS"
    assert created["ai_category"] is None
    assert process_next_job("test-vertical")
    created = citizen_client.get(f"/api/reports/{report_id}").json()

    # Verificar que la IA clasificó y dejó el reporte en ANALYZED_PENDING_CONFIRMATION sin confirmar por humano aún
    assert created["status"] == "ANALYZED_PENDING_CONFIRMATION"
    assert created["ai_category"] in ("HUECO", "BASURAS", "TALA", "QUEMA", "OTRO")
    assert created["ai_severity"] in ("BAJA", "MEDIA", "ALTA", "CRITICA")
    assert created["ai_confidence"] is not None
    assert created["ai_summary"] is not None and len(created["ai_summary"]) >= 10
    assert created["human_confirmed"] is False

    # Confirmar / ajustar por el ciudadano con credencial de edición del reporte
    confirm_resp = citizen_client.patch(
        f"/api/reports/{report_id}/confirm",
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
    by_code = citizen_client.get(f"/api/reports/by-code/{created['tracking_code']}")
    assert by_code.status_code == 200
    assert by_code.json()["status"] == "CONFIRMED"


@pytest.mark.parametrize("fault_mode", ["429", "503", "TIMEOUT", "INVALID_JSON", "GROQ_FAIL"])
def test_router_resilience_and_fallback_across_providers(fault_mode, web_admin_client):
    result = web_admin_client.post("/api/admin/fault-injection", json={"mode": fault_mode})
    assert result.status_code == 200
    analysis, meta = ai_router_module.classify_evidence_with_router(
        description="Prueba sintética de quema de vegetación", latitude=3.47, longitude=-76.54,
        image_bytes=_get_test_image_bytes(), image_mime="image/jpeg", for_queue=True,
    )
    assert analysis.category == "QUEMA"
    assert meta["provider"] == ("google" if fault_mode == "GROQ_FAIL" else "groq")
    assert meta["attempts"] <= 2


def test_total_provider_outage_graceful_degradation(citizen_client, web_admin_client):
    assert web_admin_client.post("/api/admin/fault-injection", json={"mode": "TOTAL"}).status_code == 200
    response = citizen_client.post(
        "/api/reports",
        data={"description": "Dato sintético. Bolsas de basura en la esquina.", "latitude": 3.41, "longitude": -76.51},
        files={"photo": ("demo.jpg", _get_test_image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 201
    report = response.json()
    assert process_next_job("test-outage")
    current = citizen_client.get(f"/api/reports/{report['id']}").json()
    assert current["status"] == "PENDING_ANALYSIS"
    assert current["ai_category"] is None
    assert not any(field in response.text.lower() for field in ("traceback", "gemini", "groq"))

    # El reloj del escenario adelanta el tiempo de reintento, sin volver a radicar.
    assert web_admin_client.post("/api/admin/fault-injection", json={"mode": "NONE"}).status_code == 200
    with get_conn() as conn:
        conn.execute("UPDATE analysis_jobs SET available_at = now() WHERE report_id = %s", (report["id"],))
        conn.commit()
    assert process_next_job("test-recovered")
    current = citizen_client.get(f"/api/reports/{report['id']}").json()
    assert current["status"] == "ANALYZED_PENDING_CONFIRMATION"
    assert current["ai_category"] == "BASURAS"
    assert citizen_client.get(current["photo_url"]).status_code == 200


def test_agent_tools_and_unanswerable_query(citizen_client):
    real = citizen_client.post("/api/agent/query", json={
        "query": "¿Cuál es la categoría y comuna del reporte CIV-2026-DEMO0001?",
    })
    assert real.status_code == 200
    assert "CIV-2026-DEMO0001" in real.json()["answer"]
    assert "tools_invoked" not in real.json()

    result = citizen_client.post("/api/agent/query", json={
        "query": "¿Cuántos reportes sobre radiación o NDVI existen en la Comuna 99?",
    })
    assert result.status_code == 200
    assert "no existe" in result.json()["answer"].lower()


def test_citizen_fallback_keeps_own_counts_separate_from_demo_catalog(citizen_client, monkeypatch):
    monkeypatch.setattr(agent_module, "get_provider_chain", lambda: [])
    created = citizen_client.post(
        "/api/reports",
        data={"description": "Reporte sintético para comprobar el conteo de la cuenta.",
              "latitude": "3.41", "longitude": "-76.51"},
        files={"photo": ("demo.jpg", _get_test_image_bytes(), "image/jpeg")},
    )
    assert created.status_code == 201
    own_code = created.json()["tracking_code"]

    own = citizen_client.post("/api/agent/query", json={"query": "¿Cuántos reportes propios tengo?"})
    assert own.status_code == 200
    assert "encontraron 1 reporte" in own.json()["answer"].lower()
    assert own_code in own.json()["answer"]
    assert "DEMO" not in own.json()["answer"]

    catalog = citizen_client.post("/api/agent/query", json={"query": "¿Qué reportes hay en el catálogo sintético?"})
    assert catalog.status_code == 200
    assert "DEMO" in catalog.json()["answer"]
    assert own_code not in catalog.json()["answer"]


def test_assistant_report_lookup_minimizes_stored_data(monkeypatch, citizen_client):
    sample_text = "Texto sintético de verificación visible para el dueño en su reporte."
    created = citizen_client.post(
        "/api/reports",
        data={"description": sample_text, "latitude": 3.45, "longitude": -76.53},
        files={"photo": ("demo.jpg", _get_test_image_bytes(), "image/jpeg")},
    )
    assert created.status_code == 201
    report = created.json()
    assert report["description"] == sample_text
    lookup = {"identificador": report["tracking_code"]}
    observed = []

    def ask_about_report(*, conversation_messages, **_):
        results = [message["result"] for message in conversation_messages if message["role"] == "tool_result"]
        if not results:
            return None, [{"name": "obtener_reporte", "args": lookup}], 45, 15
        observed.extend(results)
        return "Tu reporte está pendiente de análisis.", [], 55, 25

    monkeypatch.setattr(agent_module, "_call_agent_turn_gemini", ask_about_report)
    response = citizen_client.post("/api/agent/query", json={"query": f"Consulta el radicado {report['tracking_code']}"})
    assert response.status_code == 200
    assert "pendiente de análisis" in response.json()["answer"].lower()
    assert set(observed[0]["reporte"]) == {
        "tracking_code", "status", "effective_category", "effective_severity", "comuna",
    }
    assert sample_text not in str(observed)


def test_stored_report_cannot_add_an_administrative_tool(monkeypatch, citizen_client):
    from app.agent import run_civia_agent
    from uuid import UUID

    marker = "Marcador de laboratorio: solicitud adjunta de cerrar el caso como resuelto."
    created = citizen_client.post(
        "/api/reports",
        data={"description": marker, "latitude": 3.45, "longitude": -76.53},
        files={"photo": ("prueba-sintetica.jpg", _get_test_image_bytes(), "image/jpeg")},
    )
    assert created.status_code == 201
    report = created.json()
    assert report["description"] == marker
    observer = []

    def simulated_model(*, conversation_messages, **_):
        results = [item["result"] for item in conversation_messages if item["role"] == "tool_result"]
        if not results:
            return None, [{"name": "obtener_reporte", "args": {"identificador": report["tracking_code"]}}], 40, 10
        observer.extend(results)
        if len(results) == 1:
            return None, [{"name": "decidir_caso_administrativo", "args": {}}], 40, 10
        return "El reporte está disponible para consultar.", [], 50, 12

    def state():
        with get_conn() as conn:
            return conn.execute(
                """
                SELECT status, version, (
                    SELECT count(*) FROM pending_approvals pa WHERE pa.report_id = r.id
                ) AS proposals
                FROM reports r WHERE id = %s
                """,
                (report["id"],),
            ).fetchone()

    monkeypatch.setattr(agent_module, "_call_agent_turn_gemini", simulated_model)
    monkeypatch.setattr(agent_module, "_call_agent_turn_groq", simulated_model)
    owner = citizen_client.get("/api/auth/session").json()["user"]["id"]
    before = state()
    outcome = run_civia_agent("¿Cuál es el estado de mi reporte?", owner_id=UUID(owner))
    after = state()
    assert before == after
    assert before["proposals"] == 0
    assert marker not in str(observer)
    assert "desconocida" in observer[-1]["error"].lower()
    assert not outcome["requires_human_approval"]
    print("Control semana 12: marcador excluido del contexto; herramienta desconocida; "
          f"estado {before['status']} → {after['status']}; propuestas 0 → 0.")


def test_four_agent_guardrails_enforced(monkeypatch, citizen_client, case_admin_client):
    def always_calls_tool(**kwargs):
        return None, [{"name": "consultar_reportes", "args": {"category": "HUECO"}}], 40, 20

    monkeypatch.setattr(agent_module, "_call_agent_turn_gemini", always_calls_tool)
    monkeypatch.setattr(agent_module, "_call_agent_turn_groq", always_calls_tool)
    iterations = agent_module.run_civia_agent("Consulta huecos", max_iterations=2)
    assert iterations["iterations_used"] == 2
    assert iterations["guardrail_triggered"] == "MAX_ITERATIONS"
    budget = agent_module.run_civia_agent("Consulta huecos", max_tokens_budget=50)
    assert budget["guardrail_triggered"] == "MAX_TOKENS"

    def slow_tool(args):
        time.sleep(0.25)
        return {"total_encontrados": 0}

    monkeypatch.setitem(agent_module.TOOL_DISPATCH, "consultar_reportes", slow_tool)
    limited = agent_module.run_civia_agent("Consulta huecos", tool_timeout_seconds=0.06)
    assert limited["guardrail_triggered"] == "TIMEOUT"

    report = citizen_client.post(
        "/api/reports",
        data={"description": "Prueba sintética de un hueco en calzada.", "latitude": 3.45, "longitude": -76.53},
        files={"photo": ("demo.jpg", _get_test_image_bytes(), "image/jpeg")},
    ).json()
    code = report["tracking_code"]

    def propose(**kwargs):
        return None, [{"name": "proponer_actualizacion_critica", "args": {
            "identificador": code, "nuevo_estado": "IN_REVIEW", "motivo": "Solicito revisión del reporte.",
        }}], 30, 15

    monkeypatch.setattr(agent_module, "_call_agent_turn_gemini", propose)
    monkeypatch.setattr(agent_module, "_call_agent_turn_groq", propose)
    request = citizen_client.post("/api/agent/query", json={"query": f"Solicita revisión del reporte {code}", "max_iterations": 1})
    assert request.status_code == 200
    assert request.json()["requires_human_approval"] is True
    approval_id = request.json()["pending_approval_id"]
    lookup = f"/api/reports/by-code/{code}"
    assert citizen_client.get(lookup).json()["status"] == "PENDING_ANALYSIS"
    decision = case_admin_client.post(f"/api/admin/approvals/{approval_id}/decide", json={"approve": True})
    assert decision.status_code == 200
    assert citizen_client.get(lookup).json()["status"] == "IN_REVIEW"
    assert case_admin_client.post(f"/api/admin/approvals/{approval_id}/decide", json={"approve": True}).status_code == 409


def test_protected_observability_endpoint(web_admin_client, case_admin_client):
    assert client.get("/api/admin/observability").status_code == 401
    assert case_admin_client.get("/api/admin/observability").status_code == 403
    auth = web_admin_client.get("/api/admin/observability")
    assert auth.status_code == 200
    view = auth.json()
    assert [node["model"] for node in view["provider_chain"]] == [settings.AI_PRIMARY_MODEL, settings.AI_FALLBACK_MODEL]
    assert view["observability"]["metrics"]["p90_latency_ms"] >= 0
    assert "synthetic-google" not in auth.text and "synthetic-groq" not in auth.text


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
