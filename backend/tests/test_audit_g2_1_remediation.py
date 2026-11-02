import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import os
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import urlparse, urlunparse
import uuid

from fastapi.testclient import TestClient
import httpx
import psycopg
import pytest
from starlette.requests import Request
from uvicorn.config import Config
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.agent import (
    TokenBudgetTracker,
    estimate_prompt_tokens,
    execute_tool_with_timeout,
    run_civia_agent,
    tool_clasificar_evidencia,
    tool_proponer_actualizacion_critica,
)
from app.ai_router import AIProviderError, classify_evidence_with_router
from app.config import settings
from app.db import (
    cancel_active_conns_for_thread,
    checked_commit,
    get_conn,
    get_deadline_context,
    reset_deadline_context,
    set_deadline_context,
)
from app.main import app
from app.repository import create_report
from app.schemas import AgentQueryRequest
from app.security import get_trusted_client_ip, rate_limiter


def _get_clean_test_db(db_name: str) -> str:
    """Crea una base de datos desechable para pruebas sin tocar la base principal, usando DATABASE_URL dinámico."""
    base_url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    parsed = urlparse(base_url)

    admin_url = urlunparse(parsed._replace(path="/postgres"))
    try:
        admin_conn = psycopg.connect(admin_url, autocommit=True, connect_timeout=5)
    except Exception:
        admin_url = urlunparse(parsed._replace(path="/civia"))
        admin_conn = psycopg.connect(admin_url, autocommit=True, connect_timeout=5)

    with admin_conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_name};")
        cur.execute(f"CREATE DATABASE {db_name};")
    admin_conn.close()
    return urlunparse(parsed._replace(path=f"/{db_name}"))


# ==============================================================================
# Prioridad 1 — A-02: Escrituras posteriores a TIMEOUT
# ==============================================================================


def test_g2_1_a02_deferred_constraint_trigger_cancelled_on_timeout():
    """
    Reproduce exactamente el contraejemplo de Codex:
    - Tabla con constraint trigger AFTER UPDATE DEFERRABLE INITIALLY DEFERRED con pg_sleep(0.18).
    - Deadline de herramienta: 0.25 s.
    - UPDATE y espera de 0.15 s antes de commit.
    - Entrada a commit a ~0.198 s (dentro del plazo).
    - Commit toma 0.18 s de trigger -> excede el plazo de 0.25 s.
    - Verificación: la operación aborta por TimeoutError y OTRA conexión verifica que
      la fila NUNCA persistió el cambio tardío (cero escrituras posteriores a TIMEOUT).
    """
    test_db_url = _get_clean_test_db("test_g2_1_a02_trigger")

    # Configurar tabla y trigger diferido en la base desechable
    init_conn = psycopg.connect(test_db_url, autocommit=True)
    with init_conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE test_deferred_reports (
                id int PRIMARY KEY,
                status text NOT NULL
            );
            INSERT INTO test_deferred_reports (id, status) VALUES (1, 'ORIGINAL');

            CREATE OR REPLACE FUNCTION trg_sleep_fn() RETURNS trigger AS '
            BEGIN
                PERFORM pg_sleep(0.18);
                RETURN NEW;
            END;
            ' LANGUAGE plpgsql;

            CREATE CONSTRAINT TRIGGER trg_deferred_sleep
                AFTER UPDATE ON test_deferred_reports
                DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW
                EXECUTE FUNCTION trg_sleep_fn();
            """
        )
    init_conn.close()

    # Ejecutar transacción bajo control de deadline
    def worker_action():
        deadline = time.monotonic() + 0.25
        tok = set_deadline_context(deadline)
        try:
            with psycopg.connect(test_db_url) as conn:
                from app.db import register_active_conn, unregister_active_conn
                register_active_conn(conn)
                try:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE test_deferred_reports SET status = 'CORRUPTED' WHERE id = 1;")
                    time.sleep(0.15)  # Espera dentro del plazo antes de commit
                    checked_commit(conn)
                finally:
                    unregister_active_conn(conn)
        finally:
            reset_deadline_context(tok)

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(worker_action)

    timeout_caught = False
    try:
        future.result(timeout=0.25)
    except (FuturesTimeoutError, TimeoutError):
        timeout_caught = True
    except Exception as exc:
        if "TimeoutError" in type(exc).__name__:
            timeout_caught = True
        else:
            raise

    assert timeout_caught, "La operación debió levantar TimeoutError por cruzar el deadline en commit diferido"

    executor.shutdown(wait=False, cancel_futures=True)
    time.sleep(0.10)

    # Verificar desde otra conexión independiente
    verify_conn = psycopg.connect(test_db_url)
    with verify_conn.cursor() as cur:
        cur.execute("SELECT status FROM test_deferred_reports WHERE id = 1;")
        current_status = cur.fetchone()[0]
    verify_conn.close()

    assert current_status == "ORIGINAL", (
        f"Violación A-02: la fila cambió a '{current_status}' después del timeout declarado."
    )


def test_g2_1_a02_active_conn_cancellation_on_slow_worker():
    """
    Verifica que si un trabajador tarda dentro de una herramienta,
    cancel_active_conns_for_thread aborta activamente las conexiones en PostgreSQL.
    """
    executed = False
    worker_tid = []

    def mock_slow_tool(args):
        nonlocal executed
        worker_tid.append(threading.get_ident())
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Simular consulta larga
                cur.execute("SELECT pg_sleep(1.0);")
        executed = True
        return {"status": "ok"}

    from unittest.mock import patch

    with patch.dict("app.agent.TOOL_DISPATCH", {"mock_slow": mock_slow_tool}):
        with pytest.raises(TimeoutError):
            execute_tool_with_timeout("mock_slow", {}, timeout_sec=0.15)
        assert not executed, "La herramienta lenta no debió completarse con éxito"


# ==============================================================================
# Prioridad 2 — M-03: Deadline integral y fallback honesto sin HTTP 500
# ==============================================================================


def test_g2_1_m03_agent_capping_total_timeout_server_side():
    """
    Verifica que el agente acota total_timeout_seconds del cliente frente a settings.AI_TIMEOUT_SECONDS.
    """
    res = run_civia_agent(
        "Consulta general",
        max_iterations=1,
        max_tokens_budget=50,
        total_timeout_seconds=60.0,
    )
    assert "answer" in res
    assert res["latency_ms"] < (settings.AI_TIMEOUT_SECONDS * 1000 + 500)


def test_g2_1_m03_agent_expired_deadline_returns_honest_degradation_without_http500():
    """
    Verifica que cuando el agente se ejecuta con un deadline muy ajustado (0.10s)
    y el contexto expira, no lanza TimeoutError no manejado en fallback SQL ni causa HTTP 500.
    """
    client = TestClient(app)

    from unittest.mock import patch

    def slow_call(*args, **kwargs):
        time.sleep(0.12)
        raise AIProviderError("TIMEOUT", "Simulated timeout", retryable=False)

    with patch("app.agent._call_agent_turn_gemini", side_effect=slow_call), patch(
        "app.agent._call_agent_turn_groq", side_effect=slow_call
    ):
        resp = client.post(
            "/api/agent/query",
            json={
                "query": "CIV-2026-TEST no existe",
                "max_iterations": 1,
                "max_tokens_budget": 2000,
                "total_timeout_seconds": 0.11,
            },
        )
        assert resp.status_code == 200, f"No debe retornar HTTP 500: {resp.text}"
        data = resp.json()
        assert data["guardrail_triggered"] == "TIMEOUT"
        assert "no pudo completar" in data["answer"].lower() or "límite de tiempo" in data["answer"].lower()


def test_g2_1_m03_uncooperative_worker_does_not_block_timeout():
    """
    Reproduce el contraejemplo M-03 de Codex:
    Una herramienta no cooperativa se inicia antes de vencer el plazo y duerme 0.45 s (sin conexiones BD que cancelar).
    Con límite de 0.10 s, execute_tool_with_timeout NO debe esperar los 0.45 s completos; debe retornar en < 0.22 s.
    """
    started_event = threading.Event()

    def uncooperative_tool(args):
        started_event.set()
        time.sleep(0.45)
        return {"status": "uncooperative_done"}

    from unittest.mock import patch

    t_start = time.perf_counter()
    with patch.dict("app.agent.TOOL_DISPATCH", {"uncooperative": uncooperative_tool}):
        with pytest.raises(TimeoutError) as exc_info:
            execute_tool_with_timeout("uncooperative", {}, timeout_sec=0.10)

    elapsed = time.perf_counter() - t_start
    assert started_event.is_set(), "La herramienta debió haber iniciado"
    assert "superó el límite" in str(exc_info.value) or "deadline" in str(exc_info.value)
    # Verificación estricta: debe retornar inmediatamente (~0.10 s), NUNCA esperar los 0.45 s
    assert elapsed < 0.22, f"El worker no cooperativo bloqueó el timeout durante {elapsed:.4f} s (esperado < 0.22 s)"


def test_g2_1_m03_endpoint_literal_010_timeout_and_error_handler():
    """
    Verifica que:
    1) Un payload HTTP literal con total_timeout_seconds=0.10 es aceptado por el esquema Pydantic (HTTP 200, no 422).
    2) El manejador HTTP final de TimeoutError en main.py responde HTTP 200 con guardrail TIMEOUT
       y un trace_group_id UUID válido (sin NameError de uuid ni HTTP 500).
    """
    client = TestClient(app)

    from unittest.mock import patch

    # Caso 1: Petición HTTP literal total_timeout_seconds=0.10 con timeout normal
    with patch("app.main.run_civia_agent", side_effect=TimeoutError("Deadline agotado en ejecución del agente")):
        resp = client.post(
            "/api/agent/query",
            json={
                "query": "Consulta con timeout literal 0.10",
                "total_timeout_seconds": 0.10,
                "tool_timeout_seconds": 0.05,
            },
        )
        assert resp.status_code == 200, f"Debe responder 200 en lugar de 422 o 500: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert data["guardrail_triggered"] == "TIMEOUT"
        # Verificar que trace_group_id es un UUID válido (corrige NameError uuid.uuid4())
        uuid_obj = uuid.UUID(data["trace_group_id"])
        assert str(uuid_obj) == data["trace_group_id"]
        assert "límite de tiempo" in data["answer"].lower() or "deadline" in data["answer"].lower()


def test_g2_1_m03_router_respects_remaining_deadline_without_05s_floor():
    """
    Verifica que classify_evidence_with_router respeta deadlines pequeños (ej. 0.15s),
    no impone un floor de 0.5s y rechaza respuestas tardías de transporte simulado.
    """

    def delayed_handler(request: httpx.Request) -> httpx.Response:
        time.sleep(0.20)  # Demora mayor al deadline de 0.15s
        valid_json = json.dumps(
            {
                "category": "HUECO",
                "severity": "MEDIA",
                "confidence": 0.9,
                "summary": "Hueco en la calzada detectado.",
                "keywords": ["hueco"],
            }
        )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": valid_json}]}},
                ],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20},
            },
        )

    mock_transport = httpx.MockTransport(delayed_handler)
    from unittest.mock import patch

    with patch("httpx.Client", lambda *args, **kwargs: httpx.Client(transport=mock_transport)):
        contract, meta = classify_evidence_with_router(
            description="Hueco en la vía",
            latitude=3.45,
            longitude=-76.53,
            total_timeout_override=0.15,
        )
        assert contract is None, "El router no debe aceptar un contrato cuya respuesta excedió el deadline"
        assert meta["all_failed"] or meta["attempts"] >= 1


# ==============================================================================
# Prioridad 3 — M-06: Confianza en proxies y anti-spoofing en rate limiting
# ==============================================================================


def test_g2_1_m06_dockerfile_cmd_disables_uvicorn_proxy_headers():
    """
    Verifica que el Dockerfile deshabilita explícitamente proxy_headers en Uvicorn CMD
    para evitar que ProxyHeadersMiddleware sobrescriba scope['client'] en loopback.
    """
    dockerfile_candidates = [
        Path("/app/Dockerfile"),
        Path(__file__).resolve().parent.parent / "Dockerfile",
        Path(__file__).resolve().parent.parent.parent / "backend" / "Dockerfile",
    ]
    content = ""
    for cand in dockerfile_candidates:
        if cand.exists():
            content = cand.read_text(encoding="utf-8")
            break
    assert content, "No se encontró el Dockerfile para verificación"
    assert "--no-proxy-headers" in content, "Dockerfile CMD debe incluir --no-proxy-headers"
    assert "--forwarded-allow-ips" in content, "Dockerfile CMD debe restringir --forwarded-allow-ips"


def test_g2_1_m06_anti_spoofing_full_matrix_public_loopback_private_proxy():
    """
    Reproduce la matriz completa de Codex para M-06:
    1) Peer TCP público 198.51.100.2 con XFF variable -> 200 / 200 / 429
    2) Peer TCP loopback 127.0.0.1 con XFF variable -> 200 / 200 / 429 (no evade cuota)
    3) Peer TCP privado directo 10.20.30.40 con XFF variable -> 200 / 200 / 429 (no evade cuota)
    4) Peer TCP proxy Docker 172.18.0.2 con cabeceras de Nginx fijas -> 200 / 200 / 429 (cuota aplicada al cliente)
    """
    old_max = settings.RATE_LIMIT_MAX_REQUESTS
    settings.RATE_LIMIT_MAX_REQUESTS = 2

    # Construir configuración Uvicorn con opciones del Dockerfile (--no-proxy-headers y --forwarded-allow-ips "")
    uvicorn_cfg = Config(app, proxy_headers=False, forwarded_allow_ips="")
    # Envolver con ProxyHeadersMiddleware tal como hace Uvicorn internamente
    wrapped_app = ProxyHeadersMiddleware(app, trusted_hosts=uvicorn_cfg.forwarded_allow_ips)

    from unittest.mock import patch

    def dummy_agent(query, **kwargs):
        return {
            "answer": "Respuesta sintética de prueba",
            "trace_group_id": str(uuid.uuid4()),
            "tools_invoked": [],
            "iterations_used": 1,
            "max_iterations": 1,
            "total_tokens_used": 10,
            "max_tokens_budget": 100,
            "latency_ms": 5,
        }

    try:
        with patch("app.main.run_civia_agent", side_effect=dummy_agent):
            peers_to_test = [
                ("198.51.100.2", "público"),
                ("127.0.0.1", "loopback"),
                ("10.20.30.40", "privado directo"),
            ]

            for peer_ip, peer_desc in peers_to_test:
                rate_limiter.reset()
                statuses = []
                for i in range(1, 4):
                    # Variar cabecera X-Forwarded-For en cada petición para intentar eludir la cuota
                    headers = {
                        "X-Forwarded-For": f"203.0.113.{i}",
                        "X-Real-IP": f"203.0.113.{i}",
                    }
                    # Simular conexión TCP directa desde peer_ip usando TestClient con client=(peer_ip, port)
                    peer_client = TestClient(wrapped_app, client=(peer_ip, 50000 + i))
                    resp = peer_client.post(
                        "/api/agent/query",
                        json={"query": f"consulta {i} desde {peer_desc}"},
                        headers=headers,
                    )
                    statuses.append(resp.status_code)

                expected = [200, 200, 429]
                assert statuses == expected, (
                    f"Fallo en peer {peer_desc} ({peer_ip}): se obtuvo {statuses}, esperado {expected}. "
                    f"Un cliente directo no debe evadir el rate limit variando cabeceras X-Forwarded-For."
                )

            # Prueba del proxy confiable (172.18.0.2 / Nginx en Docker)
            rate_limiter.reset()
            proxy_statuses = []
            for i in range(1, 4):
                # Nginx sobrescribe cabeceras fijando la IP del cliente real (203.0.113.88)
                headers = {
                    "X-Forwarded-For": "203.0.113.88",
                    "X-Real-IP": "203.0.113.88",
                }
                proxy_client = TestClient(wrapped_app, client=("172.18.0.2", 40000 + i))
                resp = proxy_client.post(
                    "/api/agent/query",
                    json={"query": f"consulta {i} a través de Nginx"},
                    headers=headers,
                )
                proxy_statuses.append(resp.status_code)

        assert proxy_statuses == [200, 200, 429], (
            f"Fallo a través del proxy: se obtuvo {proxy_statuses}, esperado [200, 200, 429]."
        )

    finally:
        settings.RATE_LIMIT_MAX_REQUESTS = old_max
        rate_limiter.reset()


# ==============================================================================
# Prioridad 4 — M-02: Presupuesto de tokens dinámico y contabilidad multimodal
# ==============================================================================


def test_g2_1_m02_dynamic_prompt_token_estimation_triggers_max_tokens_before_call():
    """
    Verifica que el agente calcula la reserva dinámica de entrada (prompt + historial + tools)
    y activa MAX_TOKENS antes de invocar al modelo si el presupuesto es insuficiente (ej. 100 tokens),
    impidiendo que consuma tokens indebidamente.
    """
    res = run_civia_agent(
        "Consulta detallada sobre basuras en la Comuna 2",
        max_iterations=1,
        max_tokens_budget=100,
    )
    assert res["guardrail_triggered"] == "MAX_TOKENS"
    assert res["total_tokens_used"] == 0, f"No debió gastar tokens: {res['total_tokens_used']}"


def test_g2_1_m02_multimodal_classification_budget_reservation_prior_to_call():
    """
    Reproduce el contraejemplo M-02 de Codex:
    Se invoca tool_clasificar_evidencia con max_budget=200 sobre un reporte existente.
    El prompt de clasificación requiere ~394 tokens estimados (sin contar imagen ni salida).
    Verificación: la herramienta calcula la reserva requerida (~394+), detecta saldo insuficiente (200),
    activa MAX_TOKENS y NO inicia ninguna llamada multimodal (cero llamadas al router).
    """
    report_row = create_report(
        title="Reporte para prueba de reserva multimodal previa",
        description="Presupuesto insuficiente para llamada multimodal",
        latitude=3.45,
        longitude=-76.53,
        in_service_area=True,
        comuna="Comuna 2",
        neighborhood="San Vicente",
        address_hint="Calle 5 # 10-20",
        photo_meta={
            "photo_path": "test_m02.png",
            "photo_mime": "image/png",
            "photo_size_bytes": 100,
            "photo_width": 100,
            "photo_height": 100,
            "photo_sha256": "0" * 64,
        },
    )
    tcode = report_row["tracking_code"]

    tracker = TokenBudgetTracker(max_budget=200)
    from app import agent as ag_mod
    from unittest.mock import patch

    router_invoked = False

    def mock_router(*args, **kwargs):
        nonlocal router_invoked
        router_invoked = True
        raise RuntimeError("No debió llamarse al router con presupuesto insuficiente")

    tok = ag_mod._ACTIVE_TOKEN_TRACKER.set(tracker)
    try:
        with patch("app.agent.classify_evidence_with_router", side_effect=mock_router):
            res_tool = tool_clasificar_evidencia({"identificador": tcode})

        assert not router_invoked, "El router multimodal fue invocado a pesar de que el costo estimado supera el saldo"
        assert res_tool.get("guardrail_triggered") == "MAX_TOKENS"
        assert res_tool.get("analisis_completado") is False
        assert "insuficiente" in res_tool.get("mensaje", "").lower()
        # El saldo no debió haberse gastado
        assert tracker.total_tokens == 0
    finally:
        ag_mod._ACTIVE_TOKEN_TRACKER.reset(tok)


def test_g2_1_m02_full_agent_propagates_token_tracker_to_worker_thread():
    """
    Reproduce el contraejemplo M-02 de integración del executor:
    Se ejecuta el agente CIVIA completo con max_tokens_budget=6000.
    - El turno 1 del modelo solicita la herramienta clasificar_evidencia (declara 10 prompt + 10 completion = 20 tokens).
    - La herramienta clasificar_evidencia se ejecuta en el worker thread de ThreadPoolExecutor.
    - El clasificador multimodal reporta 1500 prompt + 100 completion = 1600 tokens.
    - El turno 2 del modelo recibe el resultado y produce la respuesta final (10 prompt + 10 completion = 20 tokens).
    Verificación:
    El worker thread hereda el contexto del TokenBudgetTracker;
    total_tokens_used devuelto por run_civia_agent es exactamente 1640 (40 del agente + 1600 multimodal),
    en lugar de 40.
    """
    report_row = create_report(
        title="Reporte para despacho multimodal con propagación de tracker",
        description="Verificación de contexto en worker thread",
        latitude=3.45,
        longitude=-76.53,
        in_service_area=True,
        comuna="Comuna 4",
        neighborhood="La Flora",
        address_hint="Avenida 6N # 26-10",
        photo_meta={
            "photo_path": "test_m02_prop.png",
            "photo_mime": "image/png",
            "photo_size_bytes": 100,
            "photo_width": 100,
            "photo_height": 100,
            "photo_sha256": "0" * 64,
        },
    )
    tcode = report_row["tracking_code"]

    fake_contract = type(
        "Contract",
        (),
        {
            "category": "BASURAS",
            "severity": "ALTA",
            "confidence": 0.95,
            "summary": "Acumulación de residuos sólidos en vía pública.",
            "keywords": ["residuos", "basuras"],
            "model_dump": lambda self: {
                "category": "BASURAS",
                "severity": "ALTA",
                "confidence": 0.95,
                "summary": "Acumulación de residuos sólidos en vía pública.",
                "keywords": ["residuos", "basuras"],
            },
        },
    )()

    from unittest.mock import patch

    def fake_classify(**kwargs):
        # Verificar que el worker thread tiene tracker activo
        from app.agent import _ACTIVE_TOKEN_TRACKER
        current_tracker = _ACTIVE_TOKEN_TRACKER.get()
        assert current_tracker is not None, "El worker thread de execute_tool_with_timeout NO heredó _ACTIVE_TOKEN_TRACKER"
        return fake_contract, {
            "prompt_tokens": 1500,
            "completion_tokens": 100,
            "total_tokens": 1600,
            "provider": "google",
            "model": "gemini-3.8-flash",
            "tier": "primary",
            "fallback_used": False,
            "attempts": 1,
            "latency_ms": 120,
        }

    from app.ai_router import reset_all_circuits
    reset_all_circuits()

    turn_count = 0

    def mock_agent_turn(*args, **kwargs):
        nonlocal turn_count
        turn_count += 1
        if turn_count == 1:
            # Turno 1: pide clasificar_evidencia (10 prompt + 10 completion)
            return (
                "",
                [{"name": "clasificar_evidencia", "args": {"identificador": tcode}}],
                10,
                10,
            )
        else:
            # Turno 2: respuesta final (10 prompt + 10 completion)
            return (
                "La evidencia del reporte fue clasificada exitosamente como BASURAS.",
                [],
                10,
                10,
            )

    with patch("app.agent._call_agent_turn_gemini", side_effect=mock_agent_turn), patch(
        "app.agent.classify_evidence_with_router", side_effect=fake_classify
    ):
        res = run_civia_agent(
            f"Analiza la evidencia del radicado {tcode}",
            max_iterations=3,
            max_tokens_budget=6000,
        )

    assert turn_count == 2, f"Debió ejecutar 2 turnos de modelo: {turn_count}"
    assert len(res["tools_invoked"]) == 1
    assert res["tools_invoked"][0]["tool"] == "clasificar_evidencia"
    assert res["tools_invoked"][0]["result"]["analisis_completado"] is True

    # El total de tokens debe incluir: 20 (turno 1) + 1600 (clasificación multimodal) + 20 (turno 2) = 1640
    assert res["total_tokens_used"] == 1640, (
        f"Violación M-02: total_tokens_used fue {res['total_tokens_used']}, se esperaban 1640. "
        f"El worker thread no sumó los tokens multimodales al tracker del agente."
    )
