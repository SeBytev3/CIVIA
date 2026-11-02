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


# ==============================================================================
# G2.1.1 Remediaciones Específicas: M-03, M-06, M-02 (Docs: auditoria_codex_g2_1_8162a12.md)
# ==============================================================================


def test_g2_1_1_m03_late_storage_write_rejected_by_execution_capability(tmp_path):
    """
    Reproduce el contraejemplo adversarial M-03 de Codex:
    Un worker no cooperativo supera el deadline de 0.10s.
    El llamador recibe TimeoutError oportunamente (<0.16s).
    Al despertar el worker (a 0.30s), intenta persistir un archivo mediante
    el helper real 'security._atomic_write_bytes(upload_dir, "late_file.txt", ...)'.
    Verificación:
    La capacidad revocada rechaza la escritura / promoción y lanza TimeoutError.
    El archivo NUNCA se crea en disco (cero efectos secundarios posteriores a TIMEOUT).
    """
    from app.agent import TOOL_DISPATCH
    from app.security import _atomic_write_bytes

    late_file_name = f"late_side_effect_{uuid.uuid4().hex[:8]}.txt"
    late_file_path = tmp_path / late_file_name
    worker_error: list[Exception] = []
    worker_done = threading.Event()

    def slow_uncooperative_tool(args):
        # Duerme pasando el deadline asignado de 0.10 s
        time.sleep(0.30)
        try:
            _atomic_write_bytes(tmp_path, late_file_name, b"SYNTHETIC AFTER DEADLINE")
        except Exception as e:
            worker_error.append(e)
        finally:
            worker_done.set()
        return {"status": "ok"}

    TOOL_DISPATCH["_test_uncooperative_tool"] = slow_uncooperative_tool
    t_start = time.perf_counter()
    try:
        with pytest.raises(TimeoutError):
            execute_tool_with_timeout("_test_uncooperative_tool", {}, timeout_sec=0.10)
        elapsed_caller = time.perf_counter() - t_start
        assert elapsed_caller < 0.16, f"El llamador demoró demasiado en retornar: {elapsed_caller:.4f}s"

        # Esperar a que el worker despierte y termine su intento de escritura
        worker_done.wait(timeout=1.0)
        assert len(worker_error) == 1, "El worker debió capturar una excepción al intentar escribir tras deadline"
        assert isinstance(worker_error[0], TimeoutError), f"Tipo de error inesperado: {type(worker_error[0])}"
        assert "Capacidad de ejecución" in str(worker_error[0])

        # Verificación crítica: el archivo NO debe existir en el directorio destino
        assert not late_file_path.exists(), "Fallo M-03: el helper real de archivos creó el archivo después de TIMEOUT!"
    finally:
        TOOL_DISPATCH.pop("_test_uncooperative_tool", None)


def test_g2_1_1_m03_retained_connection_late_sql_rejected_by_execution_capability():
    """
    Reproduce el contraejemplo M-03 de conexión retenida de Codex:
    Una herramienta obtiene db.get_conn() ANTES del deadline, duerme superando
    el deadline (0.30s con límite 0.10s) y luego intenta ejecutar:
    conn.execute('SELECT 8675309 AS marker')
    Verificación:
    La sentencia SQL posterior al deadline es rechazada con TimeoutError;
    la conexión retenida no puede enviar nuevas consultas una vez revocada la capacidad.
    """
    from app.agent import TOOL_DISPATCH

    marker_result: list[Any] = []
    worker_error: list[Exception] = []
    worker_done = threading.Event()

    def tool_with_retained_conn(args):
        # Obtener conexión ANTES de vencer el deadline
        with get_conn() as conn:
            time.sleep(0.30)
            try:
                res = conn.execute("SELECT 8675309 AS marker").fetchone()
                marker_result.append(res)
            except Exception as e:
                worker_error.append(e)
            finally:
                worker_done.set()
        return {"done": True}

    TOOL_DISPATCH["_test_retained_conn_tool"] = tool_with_retained_conn
    t_start = time.perf_counter()
    try:
        with pytest.raises(TimeoutError):
            execute_tool_with_timeout("_test_retained_conn_tool", {}, timeout_sec=0.10)
        elapsed_caller = time.perf_counter() - t_start
        assert elapsed_caller < 0.16, f"El llamador demoró demasiado: {elapsed_caller:.4f}s"

        worker_done.wait(timeout=1.0)
        assert len(marker_result) == 0, f"Violación M-03: SELECT 8675309 fue ejecutado tras deadline! Resultado: {marker_result}"
        assert len(worker_error) == 1, "La conexión retenida debió lanzar TimeoutError al intentar ejecutar SQL tras deadline"
        assert isinstance(worker_error[0], TimeoutError)
        assert "Capacidad de ejecución" in str(worker_error[0])
    finally:
        TOOL_DISPATCH.pop("_test_retained_conn_tool", None)


def test_g2_1_1_m06_direct_container_ip_spoofing_rejected_200_200_429(monkeypatch):
    """
    Reproduce el ataque directo desde contenedor Docker no proxy (172.19.0.9):
    El atacante envía X-Forwarded-For variable desde la misma IP peer.
    Verificación:
    172.19.0.9 NO pertenece a TRUSTED_PROXIES ("172.28.0.2,172.18.0.2").
    Por tanto, sus cabeceras XFF se descartan y la cuota aplica sobre su IP real.
    Resultado exacto: 200, 200, 429 (evasión bloqueada).
    """
    from app.seed import generate_synthetic_evidence_png
    valid_png = generate_synthetic_evidence_png("HUECO", "M06-DIRECT")

    rate_limiter.reset()
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "172.28.0.2,172.18.0.2")

    fake_client = TestClient(app, client=("172.19.0.9", 45678))

    statuses: list[int] = []
    fake_ips = ["203.0.113.1", "203.0.113.2", "203.0.113.3"]

    for spoofed_ip in fake_ips:
        headers = {
            "X-Forwarded-For": spoofed_ip,
            "X-Real-IP": spoofed_ip,
        }
        res = fake_client.post(
            "/api/reports",
            data={
                "description": "Reporte de prueba para spoofing de IP",
                "latitude": "3.45",
                "longitude": "-76.53",
                "comuna": "Comuna 1",
                "neighborhood": "San Fernando",
                "address_hint": "Calle 1 # 2-3",
                "auto_analyze": "false",
            },
            files={"photo": ("photo.png", valid_png, "image/png")},
            headers=headers,
        )
        statuses.append(res.status_code)

    assert statuses == [201, 201, 429], (
        f"Violación M-06: El contenedor 172.19.0.9 logró evadir el rate limiter enviando XFF variable. "
        f"Códigos obtenidos: {statuses}, esperados [201, 201, 429]"
    )


def test_g2_1_1_m06_trusted_proxy_separate_client_quotas(monkeypatch):
    """
    Verifica que las peticiones que sí provienen del proxy inverso legítimo
    (172.28.0.2 o 172.18.0.2) preservan cuotas independientes para clientes distintos.
    """
    from app.seed import generate_synthetic_evidence_png
    valid_png = generate_synthetic_evidence_png("HUECO", "M06-PROXY")

    rate_limiter.reset()
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "172.28.0.2,172.18.0.2")

    proxy_client = TestClient(app, client=("172.28.0.2", 80))

    # Cliente A (198.51.100.10): realiza 3 peticiones -> 201, 201, 429
    statuses_a: list[int] = []
    for _ in range(3):
        res = proxy_client.post(
            "/api/reports",
            data={
                "description": "Reporte de prueba cliente A",
                "latitude": "3.45",
                "longitude": "-76.53",
                "comuna": "Comuna 1",
                "neighborhood": "San Fernando",
                "address_hint": "Calle 1 # 2-3",
                "auto_analyze": "false",
            },
            files={"photo": ("photo.png", valid_png, "image/png")},
            headers={"X-Forwarded-For": "198.51.100.10", "X-Real-IP": "198.51.100.10"},
        )
        statuses_a.append(res.status_code)
    assert statuses_a == [201, 201, 429]

    # Cliente B (198.51.100.11): cuota independiente -> 201, 201, 429
    statuses_b: list[int] = []
    for _ in range(3):
        res = proxy_client.post(
            "/api/reports",
            data={
                "description": "Reporte de prueba cliente B",
                "latitude": "3.45",
                "longitude": "-76.53",
                "comuna": "Comuna 1",
                "neighborhood": "San Fernando",
                "address_hint": "Calle 1 # 2-3",
                "auto_analyze": "false",
            },
            files={"photo": ("photo.png", valid_png, "image/png")},
            headers={"X-Forwarded-For": "198.51.100.11", "X-Real-IP": "198.51.100.11"},
        )
        statuses_b.append(res.status_code)
    assert statuses_b == [201, 201, 429]


def test_g2_1_1_m02_concurrent_token_reservation_prevents_overconsumption():
    """
    Reproduce el contraejemplo M-02 de concurrencia de Codex:
    Se comparte un tracker con presupuesto de 1000 tokens entre dos llamadas de clasificación.
    Cada llamada requiere una reserva estimada de ~700 tokens y consume 600+100=700.
    Ambas llamadas se inician concurrentemente mediante una barrera de sincronización.
    Verificación:
    La reserva atómica (try_reserve) impide que ambas llamadas procedan;
    una procede y la otra es rechazada inmediatamente con MAX_TOKENS;
    el consumo total nunca supera el presupuesto de 1000 tokens.
    """
    from unittest.mock import patch
    import app.agent as ag_mod

    tracker = TokenBudgetTracker(max_budget=1000)
    barrier = threading.Barrier(2)

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (settings.UPLOAD_DIR / "c1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (settings.UPLOAD_DIR / "c2.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    rep1 = create_report(
        title="Reporte Concurrente 1",
        description="Prueba de reserva atómica 1",
        latitude=3.45,
        longitude=-76.53,
        in_service_area=True,
        comuna="Comuna 1",
        neighborhood="San Fernando",
        address_hint="Calle 1 # 2-3",
        photo_meta={"photo_path": "c1.png", "photo_mime": "image/png", "photo_size_bytes": 100, "photo_width": 100, "photo_height": 100, "photo_sha256": "0"*64},
    )
    rep2 = create_report(
        title="Reporte Concurrente 2",
        description="Prueba de reserva atómica 2",
        latitude=3.45,
        longitude=-76.53,
        in_service_area=True,
        comuna="Comuna 1",
        neighborhood="San Fernando",
        address_hint="Calle 1 # 2-3",
        photo_meta={"photo_path": "c2.png", "photo_mime": "image/png", "photo_size_bytes": 100, "photo_width": 100, "photo_height": 100, "photo_sha256": "0"*64},
    )

    fake_contract = type(
        "Contract",
        (),
        {
            "category": "HUECO",
            "severity": "ALTA",
            "confidence": 0.9,
            "summary": "Hueco vial",
            "keywords": [],
            "model_dump": lambda self: {
                "category": "HUECO",
                "severity": "ALTA",
                "confidence": 0.9,
                "summary": "Hueco vial",
                "keywords": [],
            },
        },
    )()

    def fake_classify_with_barrier(**kwargs):
        try:
            barrier.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        return fake_contract, {
            "prompt_tokens": 600,
            "completion_tokens": 100,
            "total_tokens": 700,
            "provider": "google",
            "model": "gemini-3.8-flash",
            "tier": "primary",
            "attempts": 1,
            "latency_ms": 50,
        }

    results: list[dict[str, Any]] = []

    def call_tool(tcode: str):
        tok = ag_mod._ACTIVE_TOKEN_TRACKER.set(tracker)
        try:
            res = ag_mod.tool_clasificar_evidencia({"identificador": tcode})
            results.append(res)
        finally:
            ag_mod._ACTIVE_TOKEN_TRACKER.reset(tok)

    with patch("app.agent.classify_evidence_with_router", side_effect=fake_classify_with_barrier):
        t1 = threading.Thread(target=call_tool, args=(rep1["tracking_code"],))
        t2 = threading.Thread(target=call_tool, args=(rep2["tracking_code"],))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    assert len(results) == 2
    guardrails = [r.get("guardrail_triggered") for r in results]
    assert "MAX_TOKENS" in guardrails, (
        f"Violación M-02: Ninguna de las llamadas concurrentes fue bloqueada por MAX_TOKENS. "
        f"Resultados: {guardrails}, tokens consumidos: {tracker.total_tokens}"
    )
    # Solo una llamada debió completarse
    completed_count = sum(1 for r in results if r.get("analisis_completado") is True)
    assert completed_count == 1, f"Debió completarse exactamente 1 análisis, pero se completaron {completed_count}"
    assert tracker.total_tokens <= 1000, f"Sobreconsumo de tokens detectado: {tracker.total_tokens} > 1000"


def test_g2_1_1_m02_token_accumulation_invalid_json_fallback(monkeypatch):
    """
    Reproduce el contraejemplo M-02 de pérdida de tokens en JSON inválido:
    - Gemini devuelve JSON inválido '{}' con 500 prompt + 100 completion = 600 tokens.
    - Router conmuta a Groq (fallback).
    - Groq devuelve contrato válido con 700 prompt + 100 completion = 800 tokens.
    Verificación:
    El router reporta total_tokens = 1400 conocidos (600 + 800), en lugar de perder
    los tokens de Gemini y reportar solo 800.
    """
    from app import ai_router as ai_r
    ai_r.reset_all_circuits()

    def mock_gemini(**kwargs):
        return "{}", 500, 100

    def mock_groq(**kwargs):
        valid_json = json.dumps({
            "category": "HUECO",
            "severity": "ALTA",
            "confidence": 0.88,
            "summary": "Hueco detectado en calzada principal.",
            "keywords": ["hueco", "calzada"],
        })
        return valid_json, 700, 100

    monkeypatch.setattr(ai_r, "_call_gemini_multimodal", mock_gemini)
    monkeypatch.setattr(ai_r, "_call_groq_multimodal", mock_groq)

    contract, meta = ai_r.classify_evidence_with_router(
        description="Prueba de acumulación de tokens con fallback",
        latitude=3.45,
        longitude=-76.53,
    )

    assert contract is not None, "El contrato debió ser exitoso tras el fallback a Groq"
    assert meta["fallback_used"] is True
    # Acumulación exacta obligatoria: 600 (Gemini inválido) + 800 (Groq válido) = 1400 conocidos
    assert meta["prompt_tokens"] == 1200, f"prompt_tokens fue {meta['prompt_tokens']}, esperado 1200"
    assert meta["completion_tokens"] == 200, f"completion_tokens fue {meta['completion_tokens']}, esperado 200"
    assert meta["total_tokens"] == 1400, (
        f"Violación M-02: total_tokens fue {meta['total_tokens']}, esperado 1400 (600 Gemini + 800 Groq)."
    )


def test_g2_1_1_m02_token_accumulation_three_invalid_responses(monkeypatch):
    """
    Reproduce el contraejemplo M-02 de acumulación ante fallo total con tokens conocidos:
    Tres proveedores devuelven '{}', cada uno con 500 prompt + 100 completion = 600 tokens.
    Verificación:
    El router reporta total_tokens = 1800 conocidos (3 x 600), en lugar de sustituir
    los tokens conocidos por 1280 estimados o cero.
    """
    from app import ai_router as ai_r
    ai_r.reset_all_circuits()

    def mock_invalid_adapter(**kwargs):
        return "{}", 500, 100

    monkeypatch.setattr(ai_r, "_call_gemini_multimodal", mock_invalid_adapter)
    monkeypatch.setattr(ai_r, "_call_groq_multimodal", mock_invalid_adapter)

    contract, meta = ai_r.classify_evidence_with_router(
        description="Prueba de tres respuestas inválidas con tokens conocidos",
        latitude=3.45,
        longitude=-76.53,
    )

    assert contract is None, "Debió fallar la clasificación al no haber esquema válido"
    assert meta["all_failed"] is True
    # Tres intentos con 600 tokens cada uno = 1800 tokens conocidos
    assert meta["total_tokens"] == 1800, (
        f"Violación M-02: total_tokens fue {meta['total_tokens']}, esperado 1800 conocidos (3 x 600)"
    )


def test_g2_1_1_m02_agent_unknown_consumption_reported_as_estimated_not_zero(monkeypatch):
    """
    Reproduce el contraejemplo M-02 de consumo desconocido en agente completo:
    Los adaptadores de turno lanzan AIProviderError NETWORK_ERROR en los tres nodos.
    Verificación:
    El agente no puede determinar el consumo remoto exacto, por lo que reporta:
    total_tokens_used > 0 (estimación conservadora del prompt enviado),
    tokens_estimated=True, y unknown_consumption=True.
    Bajo ninguna circunstancia se reporta 0 exacto sin marca estimada.
    """
    def mock_network_error(**kwargs):
        raise AIProviderError("NETWORK_ERROR", "Error de red simulado", retryable=False)

    monkeypatch.setattr("app.agent._call_agent_turn_gemini", mock_network_error)
    monkeypatch.setattr("app.agent._call_agent_turn_groq", mock_network_error)

    res = run_civia_agent(
        "Consulta de prueba con caída de red total",
        max_iterations=1,
        max_tokens_budget=6000,
    )

    assert res["degraded_sql_mode"] is True
    assert res["tokens_estimated"] is True, "Violación M-02: tokens_estimated debió ser True ante consumo desconocido"
    assert res["unknown_consumption"] is True, "Violación M-02: unknown_consumption debió ser True"
    assert res["total_tokens_used"] > 0, (
        f"Violación M-02: total_tokens_used fue {res['total_tokens_used']}. "
        f"El agente reportó 0 exacto para un consumo desconocido."
    )
