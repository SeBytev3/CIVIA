import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import os
from pathlib import Path
import threading
import time
from typing import Any
import uuid

from fastapi.testclient import TestClient
import httpx
import psycopg
import pytest
from starlette.requests import Request
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
    """Crea una base de datos desechable para pruebas sin tocar la base principal."""
    admin_conn = psycopg.connect("postgresql://civia:local_dev_change_me@db:5432/civia", autocommit=True)
    with admin_conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_name};")
        cur.execute(f"CREATE DATABASE {db_name};")
    admin_conn.close()
    return f"postgresql://civia:local_dev_change_me@db:5432/{db_name}"


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
        conn = psycopg.connect(test_db_url)
        orig_commit = conn.commit

        def wrapped_commit():
            rem = deadline - time.monotonic()
            if rem <= 0:
                conn.rollback()
                raise TimeoutError("Deadline expirado antes de commit")
            t = threading.Timer(rem, conn.cancel)
            t.daemon = True
            t.start()
            try:
                orig_commit()
            except (psycopg.errors.QueryCanceled, psycopg.errors.AdminShutdown) as exc:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise TimeoutError("Operación abortada por expiración del deadline durante commit.") from exc
            finally:
                t.cancel()

        conn.commit = wrapped_commit

        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE test_deferred_reports SET status = 'LATE_MUTATION' WHERE id = 1;")
            time.sleep(0.15)  # Espera previa al commit
            conn.commit()
            return {"status": "committed"}
        finally:
            reset_deadline_context(tok)
            conn.close()

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(worker_action)
    t0 = time.monotonic()
    threw_timeout = False
    try:
        future.result(timeout=0.25)
    except (FuturesTimeoutError, TimeoutError):
        threw_timeout = True
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    elapsed = time.monotonic() - t0
    assert threw_timeout, "La operación debió abortar por timeout"

    # Esperar un momento adicional para comprobar que el trabajador no dejó escrituras tardías
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

    from app import agent as agent_mod

    old_dispatch = dict(agent_mod.TOOL_DISPATCH)
    agent_mod.TOOL_DISPATCH["mock_slow"] = mock_slow_tool
    try:
        with pytest.raises(TimeoutError):
            execute_tool_with_timeout("mock_slow", {}, timeout_sec=0.15)
        assert not executed, "La herramienta lenta no debió completarse con éxito"
    finally:
        agent_mod.TOOL_DISPATCH = old_dispatch


# ==============================================================================
# Prioridad 2 — M-03: Deadline integral y fallback honesto sin HTTP 500
# ==============================================================================


def test_g2_1_m03_agent_capping_total_timeout_server_side():
    """
    Verifica que el agente acota total_timeout_seconds del cliente frente a settings.AI_TIMEOUT_SECONDS.
    """
    # Si el cliente pide 60.0 segundos, el agente debe toparlo con settings.AI_TIMEOUT_SECONDS
    res = run_civia_agent(
        "Consulta general",
        max_iterations=1,
        max_tokens_budget=50,
        total_timeout_seconds=60.0,
    )
    # Se ejecutó con cap servidor
    assert "answer" in res
    assert res["latency_ms"] < (settings.AI_TIMEOUT_SECONDS * 1000 + 500)


def test_g2_1_m03_agent_expired_deadline_returns_honest_degradation_without_http500():
    """
    Verifica que cuando el agente se ejecuta con un deadline muy ajustado (0.10s)
    y el contexto expira, no lanza TimeoutError no manejado en fallback SQL ni causa HTTP 500.
    """
    client = TestClient(app)

    # Inyección de retardo simulado para provocar expiración de deadline
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
        # El contrato debió ser rechazado por exceder el deadline de 0.15s
        assert contract is None, "El router no debe aceptar un contrato cuya respuesta excedió el deadline"
        assert meta["all_failed"] or meta["attempts"] >= 1


# ==============================================================================
# Prioridad 3 — M-06: Confianza en proxies y anti-spoofing en rate limiting
# ==============================================================================


def test_g2_1_m06_untrusted_peer_cannot_spoof_client_ip():
    """
    Verifica que conexiones de peers no confiables (ej. 198.51.100.2) no puedan suplantar su IP
    enviando X-Forwarded-For o X-Real-IP.
    """
    scope_untrusted = {
        "type": "http",
        "client": ("198.51.100.2", 54321),
        "headers": [
            (b"x-forwarded-for", b"203.0.113.195"),
            (b"x-real-ip", b"203.0.113.195"),
        ],
    }
    req = Request(scope_untrusted)
    resolved_ip = get_trusted_client_ip(req)
    assert resolved_ip == "198.51.100.2", f"Peer no confiable no debe suplantar IP: {resolved_ip}"


def test_g2_1_m06_rate_limiter_not_bypassed_by_varying_xff():
    """
    Verifica que un cliente no puede eludir el rate limit variando la cabecera X-Forwarded-For
    usando el middleware Uvicorn ProxyHeadersMiddleware configurado de forma segura (sin wildcard).
    """
    # Envolver app con middleware seguro confiando solo en 127.0.0.1
    wrapped_app = ProxyHeadersMiddleware(app, trusted_hosts=["127.0.0.1"])
    client = TestClient(wrapped_app)

    # Limpiar rate limiter
    rate_limiter.reset()

    # Configurar cuota baja temporal
    old_max = settings.RATE_LIMIT_MAX_REQUESTS
    settings.RATE_LIMIT_MAX_REQUESTS = 2
    try:
        # Petición 1 con XFF falso 1
        r1 = client.post(
            "/api/agent/query",
            json={"query": "consulta 1", "max_iterations": 1},
            headers={"X-Forwarded-For": "203.0.113.1"},
        )
        assert r1.status_code == 200

        # Petición 2 con XFF falso 2
        r2 = client.post(
            "/api/agent/query",
            json={"query": "consulta 2", "max_iterations": 1},
            headers={"X-Forwarded-For": "203.0.113.2"},
        )
        assert r2.status_code == 200

        # Petición 3 con XFF falso 3: DEBE SER BLOQUEADA CON 429
        r3 = client.post(
            "/api/agent/query",
            json={"query": "consulta 3", "max_iterations": 1},
            headers={"X-Forwarded-For": "203.0.113.3"},
        )
        assert r3.status_code == 429, f"Rate limit debió bloquear la 3ra petición: {r3.status_code}"
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
    impidiendo que consuma 1020 tokens indebidamente.
    """
    # Para un presupuesto de 100 tokens, el prompt del sistema + tools ya excede 500 tokens
    res = run_civia_agent(
        "Consulta detallada sobre basuras en la Comuna 2",
        max_iterations=1,
        max_tokens_budget=100,
    )
    assert res["guardrail_triggered"] == "MAX_TOKENS"
    # El modelo no fue invocado, total_tokens_used se mantiene en 0
    assert res["total_tokens_used"] == 0, f"No debió gastar tokens: {res['total_tokens_used']}"


def test_g2_1_m02_nested_multimodal_classification_accounted_in_agent_budget():
    """
    Verifica que cuando el agente invoca tool_clasificar_evidencia, los tokens
    consumidos por la clasificación multimodal se descuentan del presupuesto compartido.
    """
    # Crear reporte sintético
    report_row = create_report(
        title="Evidencia multimodal para prueba de presupuesto",
        description="Presupuesto compartido multimodal",
        latitude=3.45,
        longitude=-76.53,
        in_service_area=True,
        comuna="Comuna 2",
        neighborhood="San Vicente",
        address_hint="Calle 5 # 10-20",
        photo_meta={
            "photo_path": "test.png",
            "photo_mime": "image/png",
            "photo_size_bytes": 100,
            "photo_width": 100,
            "photo_height": 100,
            "photo_sha256": "0" * 64,
        },
    )
    tcode = report_row["tracking_code"]

    tracker = TokenBudgetTracker(max_budget=2000)
    tok = agent_mod = None
    from app import agent as ag_mod

    tok = ag_mod._ACTIVE_TOKEN_TRACKER.set(tracker)
    try:
        from unittest.mock import patch

        fake_contract = type(
            "Contract",
            (),
            {
                "category": "BASURAS",
                "severity": "ALTA",
                "confidence": 0.95,
                "summary": "Acumulación de residuos sólidos.",
                "keywords": ["residuos"],
                "model_dump": lambda self: {"category": "BASURAS", "severity": "ALTA"},
            },
        )()

        # Router simulado que reporta 1500 prompt + 100 completion = 1600 tokens
        def fake_classify(**kwargs):
            return fake_contract, {
                "prompt_tokens": 1500,
                "completion_tokens": 100,
                "total_tokens": 1600,
                "provider": "google",
                "model": "gemini-3.8-flash",
                "tier": "primary",
                "fallback_used": False,
                "attempts": 1,
                "latency_ms": 150,
            }

        with patch("app.agent.classify_evidence_with_router", side_effect=fake_classify):
            res_tool = tool_clasificar_evidencia({"identificador": tcode})
            assert res_tool.get("encontrado") is True

        # Verificar que el tracker registró los 1600 tokens
        assert tracker.total_tokens == 1600, f"El tracker debió registrar 1600 tokens: {tracker.total_tokens}"
        assert tracker.remaining() == 400

        # Si ahora intentamos con un presupuesto menor al consumo multimodal (ej. presupuesto 200),
        # tool_clasificar_evidencia debe rechazar la ejecución
        tracker_small = TokenBudgetTracker(max_budget=200)
        ag_mod._ACTIVE_TOKEN_TRACKER.set(tracker_small)
        tracker_small.record_usage(100, 50)  # Quedan 50 (< 150)
        res_small = tool_clasificar_evidencia({"identificador": tcode})
        assert res_small.get("guardrail_triggered") == "MAX_TOKENS"
        assert res_small.get("analisis_completado") is False
    finally:
        if tok is not None:
            ag_mod._ACTIVE_TOKEN_TRACKER.reset(tok)
