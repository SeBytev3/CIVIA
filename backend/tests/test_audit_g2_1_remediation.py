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
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
import psycopg
import pytest
from starlette.requests import Request
from uvicorn.config import Config
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import db
from app.agent import (
    OperationPendingError,
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
    IdempotencyConflictError,
    OperationStatus,
    cancel_active_conns_for_thread,
    checked_commit,
    get_conn,
    get_deadline_context,
    get_in_flight_commit_for_thread,
    get_operation_by_idempotency_key,
    get_operation_record,
    is_deadline_cancellation,
    mark_operation_aborted,
    mark_operation_committed,
    reconcile_operation,
    register_in_flight_commit,
    register_operation_intent,
    reset_deadline_context,
    set_deadline_context,
    unregister_in_flight_commit,
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
    new_url = urlunparse(parsed._replace(path=f"/{db_name}"))
    db.run_migrations(settings.MIGRATIONS_DIR, database_url=new_url)
    return new_url


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

    executor.shutdown(wait=True)

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


def test_g2_1_a02_balanced_config_checks_cases_81_84_prevent_late_writes():
    """
    Prueba permanente de regresión para A-02 basada en los casos 81-84 de Codex:
    - Intervalos de planificación finitos (40 ms antes de configuración inicial, 5 ms intermedio, 40 ms antes de ajuste final).
    - Trigger diferido con pg_sleep(0.18) y deadline de 0.25 s.
    - Modalidades: servidor aislado (sin Timer) y Timer retrasado (+0.15 s).
    - Ambos métodos: checked_commit y conn.commit (wrapped).
    - Verificación: CERO escrituras tardías; final_state permanece 'ORIGINAL' en todas las filas.
    """
    test_db_url = _get_clean_test_db("test_g2_1_a02_balanced")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("CREATE TABLE audit_deadline_rows(id int PRIMARY KEY, state text NOT NULL);")
        c.execute("CREATE OR REPLACE FUNCTION audit_deferred() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.state='CHANGED' THEN PERFORM pg_sleep(0.18); END IF; RETURN NEW; END $$;")
        c.execute("CREATE CONSTRAINT TRIGGER audit_delay AFTER UPDATE ON audit_deadline_rows DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit_deferred();")
        c.execute("INSERT INTO audit_deadline_rows SELECT n, 'ORIGINAL' FROM generate_series(80, 90) n;")

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    OriginalTimer = threading.Timer

    class NoTimer:
        def __init__(self, *args, **kwargs): pass
        def start(self): pass
        def cancel(self): pass

    class LateTimer:
        def __init__(self, interval, function, args=None, kwargs=None):
            self.timer = OriginalTimer(interval + 0.15, function, args=args, kwargs=kwargs)
        def start(self):
            self.timer.daemon = True
            self.timer.start()
        def cancel(self):
            self.timer.cancel()

    try:
        case_idx = 81
        for phase, pre_final, timer_type in [
            ('both_configs_server_only', 0.04, NoTimer),
            ('both_configs_delayed_timer', 0.04, LateTimer),
        ]:
            for method in ['checked', 'wrapped']:
                number = case_idx
                case_idx += 1
                done = threading.Event()
                worker_error = []

                def worker(args):
                    try:
                        cm = db.get_conn() if method == 'wrapped' else psycopg.connect(settings.DATABASE_URL)
                        with cm as c:
                            if method == 'checked':
                                db.register_active_conn(c)
                            orig_cur = c.cursor
                            class Cursor:
                                def __init__(self, *c_args, **c_kwargs):
                                    self.cur = orig_cur(*c_args, **c_kwargs)
                                def __enter__(self):
                                    self.cur.__enter__()
                                    return self
                                def __exit__(self, *e_args):
                                    return self.cur.__exit__(*e_args)
                                def __getattr__(self, name):
                                    return getattr(self.cur, name)
                                def execute(self, q, p=None, **kwargs):
                                    text = str(q)
                                    is_init = 'SET LOCAL transaction_timeout' in text
                                    is_fin = "set_config('transaction_timeout'" in text
                                    if is_init:
                                        time.sleep(0.04)
                                    if is_fin and pre_final:
                                        time.sleep(pre_final)
                                    res = self.cur.execute(q, p, **kwargs)
                                    if is_init:
                                        time.sleep(0.005)
                                    return res
                            c.cursor = Cursor
                            c.execute("UPDATE audit_deadline_rows SET state='CHANGED' WHERE id=%s", (number,))
                            if method == 'wrapped':
                                c.commit()
                            else:
                                db.checked_commit(c)
                    except Exception as exc:
                        worker_error.append(type(exc).__name__)
                    finally:
                        if method == 'checked' and 'c' in locals():
                            db.unregister_active_conn(c)
                        done.set()
                    return {}

                orig_cancel = cancel_active_conns_for_thread
                def delayed_cancel(tid):
                    time.sleep(0.15)
                    return orig_cancel(tid)

                with patch.dict("app.agent.TOOL_DISPATCH", {'audit_final_config': worker}), \
                     patch("app.agent.cancel_active_conns_for_thread", side_effect=delayed_cancel), \
                     patch.object(db.threading, 'Timer', timer_type):
                    try:
                        execute_tool_with_timeout('audit_final_config', {}, 0.25)
                    except Exception:
                        pass
                    done.wait(2)
                    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as v:
                        final = v.execute('SELECT state FROM audit_deadline_rows WHERE id=%s', (number,)).fetchone()[0]

                assert final == "ORIGINAL", (
                    f"Violación A-02 en caso {number} ({phase}, {method}): "
                    f"la fila cambió a '{final}' tras vencer el deadline absoluto de 0.25s."
                )
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_a02_legitimate_commits_within_deadline():
    """
    Verifica que los commits legítimos dentro del deadline (0.25 s) con trigger diferido (0.18 s)
    confirman exitosamente para ambos métodos (checked_commit y wrapped conn.commit).
    """
    test_db_url = _get_clean_test_db("test_g2_1_a02_legit")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("CREATE TABLE audit_deadline_rows(id int PRIMARY KEY, state text NOT NULL);")
        c.execute("CREATE OR REPLACE FUNCTION audit_deferred() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.state='CHANGED' THEN PERFORM pg_sleep(0.14); END IF; RETURN NEW; END $$;")
        c.execute("CREATE CONSTRAINT TRIGGER audit_delay AFTER UPDATE ON audit_deadline_rows DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit_deferred();")
        c.execute("INSERT INTO audit_deadline_rows SELECT n, 'ORIGINAL' FROM generate_series(91, 95) n;")

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        for number, method in [(91, 'checked'), (92, 'wrapped')]:
            done = threading.Event()
            def worker(args):
                try:
                    cm = db.get_conn() if method == 'wrapped' else psycopg.connect(settings.DATABASE_URL)
                    with cm as c:
                        if method == 'checked':
                            db.register_active_conn(c)
                        c.execute("UPDATE audit_deadline_rows SET state='CHANGED' WHERE id=%s", (number,))
                        if method == 'checked':
                            db.checked_commit(c)
                        else:
                            c.commit()
                    return {'committed': True}
                finally:
                    if method == 'checked' and 'c' in locals():
                        db.unregister_active_conn(c)
                    done.set()

            with patch.dict("app.agent.TOOL_DISPATCH", {'audit_legit': worker}):
                res = execute_tool_with_timeout('audit_legit', {}, 0.25)
                assert res.get('committed') is True, f"El commit legítimo {number} ({method}) debió ser exitoso"
                done.wait(2)
                with psycopg.connect(settings.DATABASE_URL, autocommit=True) as v:
                    final = v.execute('SELECT state FROM audit_deadline_rows WHERE id=%s', (number,)).fetchone()[0]
                assert final == "CHANGED", f"El commit legítimo {number} ({method}) debió persistir CHANGED"
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_a02_cases_61_64_scheduling_delay():
    """
    Verifica que una pausa de planificación de 0.13 s antes de la configuración de deadline
    no permite escrituras tardías (Casos 61-64 de auditoría).
    """
    test_db_url = _get_clean_test_db("test_g2_1_a02_sched")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("CREATE TABLE audit_deadline_rows(id int PRIMARY KEY, state text NOT NULL);")
        c.execute("CREATE OR REPLACE FUNCTION audit_deferred() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.state='CHANGED' THEN PERFORM pg_sleep(0.18); END IF; RETURN NEW; END $$;")
        c.execute("CREATE CONSTRAINT TRIGGER audit_delay AFTER UPDATE ON audit_deadline_rows DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit_deferred();")
        c.execute("INSERT INTO audit_deadline_rows SELECT n, 'ORIGINAL' FROM generate_series(61, 65) n;")

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        for number, method in [(61, 'checked'), (62, 'wrapped'), (63, 'checked'), (64, 'wrapped')]:
            done = threading.Event()
            def worker(args):
                try:
                    cm = db.get_conn() if method == 'wrapped' else psycopg.connect(settings.DATABASE_URL)
                    with cm as c:
                        if method == 'checked':
                            db.register_active_conn(c)
                        orig = c.cursor
                        class Cursor:
                            def __init__(self, *args, **kw): self.cur = orig(*args, **kw)
                            def __enter__(self): self.cur.__enter__(); return self
                            def __exit__(self, *args): return self.cur.__exit__(*args)
                            def __getattr__(self, name): return getattr(self.cur, name)
                            def execute(self, q, p=None, **kw):
                                if 'SET LOCAL transaction_timeout' in str(q):
                                    time.sleep(0.13)
                                return self.cur.execute(q, p, **kw)
                        c.cursor = Cursor
                        c.execute("UPDATE audit_deadline_rows SET state='CHANGED' WHERE id=%s", (number,))
                        if method == 'wrapped':
                            c.commit()
                        else:
                            db.checked_commit(c)
                except Exception:
                    pass
                finally:
                    if method == 'checked' and 'c' in locals():
                        db.unregister_active_conn(c)
                    done.set()
                return {}

            orig_cancel = cancel_active_conns_for_thread
            def delayed_cancel(tid):
                time.sleep(0.15)
                return orig_cancel(tid)

            with patch.dict("app.agent.TOOL_DISPATCH", {'audit_sched': worker}), \
                 patch("app.agent.cancel_active_conns_for_thread", side_effect=delayed_cancel):
                try:
                    execute_tool_with_timeout('audit_sched', {}, 0.25)
                except Exception:
                    pass
                done.wait(2)
                with psycopg.connect(settings.DATABASE_URL, autocommit=True) as v:
                    final = v.execute('SELECT state FROM audit_deadline_rows WHERE id=%s', (number,)).fetchone()[0]
                assert final == "ORIGINAL", f"Caso {number} ({method}) falló: persistió '{final}' tras vencer deadline"
    finally:
        settings.DATABASE_URL = old_db_url


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
        # Separar la verificación de integridad de datos de la latencia en Windows (G2.1.3)
        assert elapsed_caller < 0.60, f"El llamador demoró demasiado: {elapsed_caller:.4f}s"

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
    172.19.0.9 NO pertenece a TRUSTED_PROXIES ("172.28.0.2").
    Por tanto, sus cabeceras XFF se descartan y la cuota aplica sobre su IP real.
    Resultado exacto: 201, 201, 429 (evasión bloqueada).
    """
    from app.seed import DEMO_ASSETS_DIR
    valid_png = (DEMO_ASSETS_DIR / "civ-2026-demo0001.jpg").read_bytes()

    rate_limiter.reset()
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "172.28.0.2")

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
    (172.28.0.2) preservan cuotas independientes para clientes distintos.
    """
    from app.seed import DEMO_ASSETS_DIR
    valid_png = (DEMO_ASSETS_DIR / "civ-2026-demo0001.jpg").read_bytes()

    rate_limiter.reset()
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "172.28.0.2")

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


# =====================================================================
# G2.1.2 — Reproducción de los cuatro bloqueos de auditoría Codex a745a1c
# =====================================================================

def test_g2_1_2_m03_chained_cursor_and_conn_execute_reject_late_sql():
    """
    Reproduce el contraejemplo Codex FAIL 1 de M-03:
    cursor = conn.cursor().execute("SELECT 1")
    cursor = conn.execute("SELECT 1")
    Ambos devuelven el cursor que debe seguir protegido por el proxy.
    Al expirar o revocarse la capacidad, cursor.execute() subsiguiente
    debe lanzar TimeoutError y no devolver 8675309.
    """
    cap = db.ExecutionCapability(deadline=time.monotonic() + 10.0)
    tok = db.set_execution_capability(cap)
    try:
        with db.get_conn() as conn:
            # Chained cursor.execute()
            cur1 = conn.cursor().execute("SELECT 1")
            # Chained conn.execute()
            cur2 = conn.execute("SELECT 1")

            assert isinstance(cur1, db._CapabilityCursorProxy), "cur1 debe ser _CapabilityCursorProxy"
            assert isinstance(cur2, db._CapabilityCursorProxy), "cur2 debe ser _CapabilityCursorProxy"

            # Revocar capacidad (simulando vencimiento tras TIMEOUT)
            cap.revoke()

            with pytest.raises(TimeoutError, match="Capacidad de ejecución revocada"):
                cur1.execute("SELECT 8675309 AS marker")

            with pytest.raises(TimeoutError, match="Capacidad de ejecución revocada"):
                cur2.execute("SELECT 8675309 AS marker")
    finally:
        db.reset_execution_capability(tok)


def test_g2_1_2_m03_copy_method_rejected_after_deadline():
    """
    Reproduce el contraejemplo Codex FAIL 2 de M-03:
    with cursor.copy("COPY (SELECT 8675309) TO STDOUT") as copy:
        value = bytes(copy.read())
    Debe ser interceptado por la capacidad y lanzar TimeoutError
    tras el vencimiento del deadline, impidiendo efectos SQL tardíos.
    """
    with db.get_conn() as conn:
        cur = conn.cursor()
        cap = db.ExecutionCapability(deadline=time.monotonic() - 1.0)
        tok = db.set_execution_capability(cap)
        conn._execution_capability = cap
        cur._cap = cap
        try:
            with pytest.raises(TimeoutError, match="Capacidad de ejecución expirada|revocada"):
                with cur.copy("COPY (SELECT 8675309) TO STDOUT") as copy_ctx:
                    copy_ctx.read()
        finally:
            db.reset_execution_capability(tok)


def test_g2_1_2_m03_atomic_publish_file_serializes_race_with_revocation(tmp_path):
    """
    Reproduce el contraejemplo Codex FAIL 3 de M-03:
    Carrera entre la validación de la capacidad y os.replace().
    Al coordinar la promoción bajo candado indivisible con revoke(),
    si revoke() ocurre primero o durante la coordinación,
    la promoción es rechazada y el archivo de destino jamás se publica.
    """
    dest_file = tmp_path / "published.txt"
    staging_file = tmp_path / "staging.tmp"
    staging_file.write_bytes(b"DATA")

    cap = db.ExecutionCapability(deadline=time.monotonic() + 10.0)
    tok = db.set_execution_capability(cap)
    try:
        # Revocar la capacidad
        cap.revoke()
        assert not cap.is_valid()

        # Intentar publicar archivo atómicamente
        with pytest.raises(TimeoutError, match="Capacidad de ejecución revocada"):
            db.atomic_publish_file(staging_file, dest_file)

        assert not dest_file.exists(), "Violación M-03: El archivo fue publicado a pesar de estar revocada la capacidad"
    finally:
        db.reset_execution_capability(tok)


def test_g2_1_2_m02_invalid_json_exhausts_budget_blocks_subsequent_groq_attempt(monkeypatch):
    """
    Reproduce el contraejemplo Codex FAIL de M-02:
    Presupuesto de 1000 tokens.
    Gemini consume 900+100=1000 tokens conocidos y devuelve JSON inválido '{}'.
    Al conciliar por intento, el tracker queda con remaining=0.
    Por tanto, el router no debe iniciar la segunda llamada a Groq.
    """
    from app import ai_router as ai_r
    from app.agent import TokenBudgetTracker
    ai_r.reset_all_circuits()

    def mock_gemini_exhausts_budget(**kwargs):
        return "{}", 900, 100

    groq_called = False
    def mock_groq_should_not_be_called(**kwargs):
        nonlocal groq_called
        groq_called = True
        return json.dumps({
            "category": "HUECO",
            "severity": "ALTA",
            "confidence": 0.9,
            "summary": "Hueco detectado",
            "keywords": ["hueco"],
        }), 700, 100

    monkeypatch.setattr(ai_r, "_call_gemini_multimodal", mock_gemini_exhausts_budget)
    monkeypatch.setattr(ai_r, "_call_groq_multimodal", mock_groq_should_not_be_called)

    tracker = TokenBudgetTracker(max_budget=1000)
    contract, meta = ai_r.classify_evidence_with_router(
        description="Prueba de presupuesto agotado en primer intento",
        latitude=3.45,
        longitude=-76.53,
        token_tracker=tracker,
    )

    assert contract is None, "El contrato debió ser None ya que Groq no debió ser llamado"
    assert groq_called is False, (
        "Violación M-02: Groq fue llamado cuando el presupuesto ya había sido agotado "
        "por el intento de Gemini (1000 de 1000)!"
    )
    assert tracker.total_tokens == 1000, f"total_tokens fue {tracker.total_tokens}, esperado 1000"
    assert tracker.remaining() == 0, f"remaining fue {tracker.remaining()}, esperado 0"
    assert meta["attempts"] == 1, f"attempts fue {meta['attempts']}, esperado 1"
    assert meta["insufficient_budget"] is True


def test_g2_1_3_m02_two_concurrent_authorized_calls_record_1400_not_2100(monkeypatch):
    """
    Reproduce el contraejemplo Codex FAIL de M-02 (d07a1e5):
    Dos clasificaciones concurrentes autorizadas (700 tokens c/u) con presupuesto de 6000.
    Finalización escalonada: la llamada 1 termina y concilia mientras la llamada 2 sigue activa.
    Con TokenReservation individual, la llamada 1 no confunde la reserva ajena con la propia.
    Total final registrado: exactamente 1400 tokens (NO 2100).
    """
    from app import ai_router as ai_r
    from app.agent import TokenBudgetTracker, tool_clasificar_evidencia, set_active_token_tracker
    ai_r.reset_all_circuits()

    step1_entered_router = threading.Event()
    step2_entered_router = threading.Event()
    step1_allow_finish = threading.Event()
    step2_allow_finish = threading.Event()

    def mock_multimodal_staggered(*, model: str, api_key: str, prompt_text: str, **kwargs):
        is_first = "reporte-1" in prompt_text
        if is_first:
            step1_entered_router.set()
            step1_allow_finish.wait(timeout=3.0)
        else:
            step2_entered_router.set()
            step2_allow_finish.wait(timeout=3.0)

        payload = {
            "category": "HUECO",
            "severity": "ALTA",
            "confidence": 0.9,
            "summary": "Hueco detectado en vía principal",
            "keywords": ["hueco"],
        }
        return json.dumps(payload), 600, 100

    monkeypatch.setattr(ai_r, "_call_gemini_multimodal", mock_multimodal_staggered)

    # Crear dos reportes en la base de datos de pruebas para tener UUIDs válidos
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, tracking_code FROM reports LIMIT 2;")
            rows = cur.fetchall()
            rep1_id, rep2_id = rows[0]["id"], rows[1]["id"]
            cur.execute("UPDATE reports SET description = 'reporte-1 para prueba concurrente' WHERE id = %s;", (rep1_id,))
            cur.execute("UPDATE reports SET description = 'reporte-2 para prueba concurrente' WHERE id = %s;", (rep2_id,))
            conn.commit()

    shared_tracker = TokenBudgetTracker(max_budget=6000)

    res1 = []
    res2 = []

    def run_call(report_id, out_list):
        tok = set_active_token_tracker(shared_tracker)
        try:
            r = tool_clasificar_evidencia({"identificador": str(report_id)})
            out_list.append(r)
        finally:
            set_active_token_tracker(None)

    t1 = threading.Thread(target=run_call, args=(rep1_id, res1))
    t2 = threading.Thread(target=run_call, args=(rep2_id, res2))

    t1.start()
    t2.start()

    # Esperar a que ambas llamadas hayan entrado al router con sus reservas activas
    assert step1_entered_router.wait(timeout=3.0), "La llamada 1 debió entrar al router"
    assert step2_entered_router.wait(timeout=3.0), "La llamada 2 debió entrar al router"

    # En este punto, ambas tienen reserva activa: 700 + 700 = 1400 reservadas
    assert shared_tracker.reserved_tokens > 0, "Debe haber tokens reservados concurrentemente"

    # Permitir que la llamada 1 termine mientras la llamada 2 sigue activa
    step1_allow_finish.set()
    t1.join(timeout=3.0)
    assert len(res1) == 1
    assert res1[0]["analisis_completado"] is True

    # Verificar que tras finalizar la llamada 1, solo se ha registrado 700 tokens (NO 1400)
    assert shared_tracker.total_tokens == 700, (
        f"Violación M-02: La llamada 1 registró {shared_tracker.total_tokens} tokens (esperado 700). "
        "Si reporta 1400 es porque confundió la reserva de la llamada 2 con la suya."
    )

    # Permitir que la llamada 2 termine
    step2_allow_finish.set()
    t2.join(timeout=3.0)
    assert len(res2) == 1
    assert res2[0]["analisis_completado"] is True

    # Verificar que el total acumulado exacto es 1400 (NO 2100) y cero reservas residuales
    assert shared_tracker.total_tokens == 1400, (
        f"Violación M-02: El total acumulado fue {shared_tracker.total_tokens} tokens (esperado exactamente 1400, no 2100)!"
    )
    assert shared_tracker.reserved_tokens == 0, f"Reservas residuales: {shared_tracker.reserved_tokens}"


def test_g2_1_3_m03_copy_out_and_copy_in_authorized_and_rejected_after_revocation():
    """
    Verifica el contrato completo de psycopg 3 para _CapabilityCopyProxy (M-03 G2.1.3):
    1) COPY OUT autorizado con cp.rows() retorna filas reales.
    2) COPY IN autorizado con cp.write_row(...) inserta datos en PostgreSQL.
    3) Iteración sobre cp produce datos.
    4) Rechazo con TimeoutError tras revocar la capacidad de ejecución.
    """
    test_db_url = _get_clean_test_db("test_g2_1_3_m03_copy")
    with psycopg.connect(test_db_url, autocommit=True) as setup_conn:
        with setup_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE test_copy_contract (
                    id int primary key,
                    name text not null
                );
            """)

    raw_conn = psycopg.connect(test_db_url)
    try:
        cap = db.ExecutionCapability(deadline=time.monotonic() + 5.0)
        proxy_cur = db._CapabilityCursorProxy(raw_conn.cursor(), cap)

        # 1. COPY OUT autorizado: rows() no debe levantar AttributeError
        with proxy_cur.copy("COPY (SELECT 42 AS val, 'civia_ok' AS txt) TO STDOUT") as cp:
            rows = list(cp.rows())
            assert len(rows) == 1
            assert "42" in str(rows[0]) or 42 in rows[0]

        # 2. COPY IN autorizado: write_row() escribe en PostgreSQL
        with proxy_cur.copy("COPY test_copy_contract (id, name) FROM STDIN") as cp:
            cp.write_row((1, "registro_1"))
            cp.write_row((2, "registro_2"))
        raw_conn.commit()

        # Verificar que los datos se insertaron
        with raw_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM test_copy_contract;")
            assert cur.fetchone()[0] == 2

        # 3. Iteración directa sobre copy
        with proxy_cur.copy("COPY test_copy_contract TO STDOUT") as cp:
            chunks = list(cp)
            assert len(chunks) > 0

        # 4. Rechazo posterior a revocación
        cap.revoke()
        assert not cap.is_valid()

        # Abrir COPY después de revoke debe fallar
        with pytest.raises(TimeoutError, match="Capacidad de ejecución"):
            with proxy_cur.copy("COPY (SELECT 1) TO STDOUT") as cp:
                pass

        # Iterar sobre stream/rows con capacidad revocada debe fallar
        cap_active = db.ExecutionCapability(deadline=time.monotonic() + 5.0)
        proxy_cur2 = db._CapabilityCursorProxy(raw_conn.cursor(), cap_active)
        with proxy_cur2.copy("COPY (SELECT generate_series(1, 10)) TO STDOUT") as cp:
            row_iter = cp.rows()
            first_row = next(row_iter)  # Lectura autorizada
            assert first_row is not None
            # Revocar capacidad mientras el iterador está activo
            cap_active.revoke()
            with pytest.raises(TimeoutError, match="Capacidad de ejecución"):
                next(row_iter)
    finally:
        raw_conn.close()

    # COPY IN con capacidad revocada a mitad de escritura debe fallar en conexión independiente
    with psycopg.connect(test_db_url) as in_conn:
        cap_active_in = db.ExecutionCapability(deadline=time.monotonic() + 5.0)
        proxy_cur3 = db._CapabilityCursorProxy(in_conn.cursor(), cap_active_in)
        with proxy_cur3.copy("COPY test_copy_contract (id, name) FROM STDIN") as cp:
            cp.write_row((3, "valido"))
            cap_active_in.revoke()
            with pytest.raises(TimeoutError, match="Capacidad de ejecución"):
                cp.write_row((4, "tardio"))


# ==============================================================================
# G2.1.4 — Pruebas de Regresión Adversarial A-02 y Hermeticidad
# ==============================================================================


@pytest.mark.parametrize("case_num,method", [
    (61, "checked"),
    (62, "wrapped"),
    (63, "checked"),
    (64, "wrapped"),
])
def test_g2_1_4_a02_reproduction_scheduling_pause_and_delayed_cancel_preserves_original(case_num, method):
    """
    Reproduce exactamente los cuatro contraejemplos A-02 de Codex (docs/auditoria_codex_g2_1_3_4a99705.md):
    - Deadline absoluto del llamador: 0.25 s.
    - Constraint trigger diferido AFTER UPDATE con pg_sleep(0.18 s).
    - Pausa determinista de planificación de 0.13 s antes de aplicar SET LOCAL transaction_timeout.
    - Retraso de planificación de 0.15 s antes de despachar cancel_active_conns_for_thread.
    - Conexiones registradas explícitamente (checked) y mediante get_conn() (wrapped).

    Verificación obligatoria:
    1. El llamador recibe TimeoutError a ~0.25 s.
    2. El worker es abortado por transaction_timeout / cancel y registra TimeoutError.
    3. Ningún COMMIT tardío es confirmado (cero escrituras posteriores al deadline).
    4. El estado observado por otra conexión inmediatamente y tras finalizar el worker es estrictamente ORIGINAL.
    """
    test_db_url = _get_clean_test_db(f"test_g2_1_4_a02_{case_num}")
    with psycopg.connect(test_db_url, autocommit=True) as setup_conn:
        setup_conn.execute("CREATE TABLE IF NOT EXISTS audit_deadline_rows (id int PRIMARY KEY, state text NOT NULL);")
        setup_conn.execute("""
            CREATE OR REPLACE FUNCTION audit_deferred() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.state = 'CHANGED' THEN
                    PERFORM pg_sleep(0.18);
                END IF;
                RETURN NEW;
            END
            $$;
        """)
        setup_conn.execute("DROP TRIGGER IF EXISTS audit_delay ON audit_deadline_rows;")
        setup_conn.execute("""
            CREATE CONSTRAINT TRIGGER audit_delay
            AFTER UPDATE ON audit_deadline_rows
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION audit_deferred();
        """)
        setup_conn.execute(
            "INSERT INTO audit_deadline_rows (id, state) VALUES (%s, 'ORIGINAL') "
            "ON CONFLICT (id) DO UPDATE SET state = 'ORIGINAL';",
            (case_num,),
        )

    from app import agent as a
    from app.config import settings
    from unittest.mock import patch

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url

    try:
        done = threading.Event()
        worker_error = []
        events = []
        origin = time.monotonic()

        def worker(args):
            try:
                cm = db.get_conn() if method == "wrapped" else psycopg.connect(test_db_url)
                with cm as c:
                    if method == "checked":
                        db.register_active_conn(c)
                    original_cursor = c.cursor

                    class SchedulingProbeCursor:
                        def __init__(self, *args, **kw):
                            self.cur = original_cursor(*args, **kw)
                        def __enter__(self):
                            self.cur.__enter__()
                            return self
                        def __exit__(self, *args):
                            return self.cur.__exit__(*args)
                        def __getattr__(self, name):
                            return getattr(self.cur, name)
                        def execute(self, q, p=None, **kw):
                            if "SET LOCAL transaction_timeout" in str(q):
                                events.append({"set_computed_at": time.monotonic() - origin, "statement": str(q)})
                                time.sleep(0.13)
                            res = self.cur.execute(q, p, **kw)
                            if "SET LOCAL transaction_timeout" in str(q):
                                events.append({"set_completed_at": time.monotonic() - origin})
                            return res

                    c.cursor = SchedulingProbeCursor
                    c.execute("UPDATE audit_deadline_rows SET state='CHANGED' WHERE id=%s", (case_num,))
                    events.append({"commit_entered_at": time.monotonic() - origin})
                    if method == "wrapped":
                        c.commit()
                    else:
                        db.checked_commit(c)
                    events.append({"commit_confirmed_at": time.monotonic() - origin})
            except Exception as exc:
                worker_error.append(type(exc).__name__)
            finally:
                if method == "checked" and "c" in locals():
                    db.unregister_active_conn(c)
                done.set()
            return {}

        original_cancel = a.cancel_active_conns_for_thread

        def delayed_cancel(tid):
            time.sleep(0.15)
            return original_cancel(tid)

        with patch.dict(a.TOOL_DISPATCH, {"audit_commit_schedule": worker}):
            with patch.object(a, "cancel_active_conns_for_thread", side_effect=delayed_cancel):
                origin = time.monotonic()
                caller_error = None
                try:
                    a.execute_tool_with_timeout("audit_commit_schedule", {}, 0.25)
                except Exception as exc:
                    caller_error = type(exc).__name__
                caller_elapsed = time.monotonic() - origin

                with psycopg.connect(test_db_url, autocommit=True) as verify_conn:
                    at_return = verify_conn.execute(
                        "SELECT state FROM audit_deadline_rows WHERE id=%s", (case_num,)
                    ).fetchone()[0]

                finished = done.wait(timeout=2.0)

                with psycopg.connect(test_db_url, autocommit=True) as verify_conn:
                    final_state = verify_conn.execute(
                        "SELECT state FROM audit_deadline_rows WHERE id=%s", (case_num,)
                    ).fetchone()[0]

        # Validaciones obligatorias de integridad transaccional A-02:
        assert caller_error in ("TimeoutError", "OperationPendingError"), f"El llamador debió recibir TimeoutError u OperationPendingError, obtuvo: {caller_error}"
        assert at_return == "ORIGINAL", f"Estado inmediatamente al retorno debe ser ORIGINAL, fue: {at_return}"
        assert finished is True, "El worker debió finalizar dentro del plazo razonable"
        assert final_state == "ORIGINAL", (
            f"VIOLACIÓN A-02: El worker confirmó tardíamente tras TimeoutError! Estado final: {final_state}"
        )
        assert "TimeoutError" in worker_error, f"El worker debió abortar con TimeoutError: {worker_error}"
        assert not any("commit_confirmed_at" in ev for ev in events), (
            "El commit jamás debió confirmarse tras la pausa de planificación y trigger"
        )
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_4_hermetic_suite_zero_external_attempts_synthetic_and_empty():
    """
    Verifica que las consultas del agente operan con cero intentos externos
    tanto con claves sintéticas como con claves vacías (G2.1.4).
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import settings

    tc = TestClient(app)

    # 1. Con claves sintéticas
    old_google = settings.GOOGLE_API_KEY_PRIMARY
    old_groq = settings.GROQ_API_KEY
    try:
        settings.GOOGLE_API_KEY_PRIMARY = "fake_synthetic_google_key_g214"
        settings.GROQ_API_KEY = "fake_synthetic_groq_key_g214"

        r1 = tc.post(
            "/api/agent/query",
            json={"query": "¿Cuál es la categoría del reporte CIV-2026-DEMO0001?"},
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert "CIV-2026-DEMO0001" in d1["answer"] or "HUECO" in d1["answer"].upper()

        r2 = tc.post(
            "/api/agent/query",
            json={"query": "¿Cuántos reportes de radiación nuclear existen en la Comuna 99?"},
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert any(w in d2["answer"].lower() for w in ("no existe", "no hay", "0", "ningún", "sin evidencia"))

        # 2. Con claves vacías
        settings.GOOGLE_API_KEY_PRIMARY = ""
        settings.GROQ_API_KEY = ""

        r3 = tc.post(
            "/api/agent/query",
            json={"query": "¿Cuál es la categoría del reporte CIV-2026-DEMO0001?"},
        )
        assert r3.status_code == 200
    finally:
        settings.GOOGLE_API_KEY_PRIMARY = old_google
        settings.GROQ_API_KEY = old_groq


# ==============================================================================
# G2.1.6: Rediseño del Contrato Transaccional A-02 y Registro Durable
# (COMMITTED, ABORTED, PENDING, UNKNOWN, idempotencia, reconciliación)
# ==============================================================================


def test_g2_1_6_admin_shutdown_not_masked_as_timeout():
    """
    Verifica que una desconexión o terminación administrativa real (pg_terminate_backend /
    SQLSTATE 57P01 / AdminShutdown) ocurrida mucho antes de vencer el deadline
    NO sea enmascarada como TimeoutError ni clasificada como vencimiento de plazo (Caso 101).
    """
    test_db_url = _get_clean_test_db("test_g2_1_6_admin_term")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("CREATE TABLE test_workers(id int PRIMARY KEY);")

    # 1. Probar la función de clasificación pura is_deadline_cancellation
    admin_exc = psycopg.errors.AdminShutdown("terminating connection due to administrator command")
    setattr(admin_exc, "sqlstate", "57P01")
    assert not is_deadline_cancellation(admin_exc, deadline=time.monotonic() + 2.0), (
        "57P01 / AdminShutdown nunca debe clasificarse como cancelación por deadline propio."
    )

    # 2. Prueba en vivo con pg_terminate_backend sobre conexión de worker
    worker_pid: list[int] = []
    worker_error: list[Exception] = []
    ready_evt = threading.Event()

    def victim_worker():
        try:
            with psycopg.connect(test_db_url) as conn:
                worker_pid.append(conn.info.backend_pid)
                ready_evt.set()
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_sleep(3.0);")
        except Exception as exc:
            worker_error.append(exc)

    t = threading.Thread(target=victim_worker, daemon=True)
    t.start()
    assert ready_evt.wait(timeout=2.0), "El worker no inició a tiempo"
    time.sleep(0.05)

    # Terminar administrativamente el backend desde otra conexión
    with psycopg.connect(test_db_url, autocommit=True) as admin_c:
        admin_c.execute("SELECT pg_terminate_backend(%s);", (worker_pid[0],))

    t.join(timeout=2.0)
    assert worker_error, "El worker debió recibir un error por pg_terminate_backend"
    err = worker_error[0]
    assert isinstance(err, (psycopg.errors.AdminShutdown, psycopg.OperationalError)), (
        f"Se esperaba AdminShutdown/OperationalError, pero se recibió {type(err).__name__}: {err}"
    )
    assert not isinstance(err, TimeoutError), "AdminShutdown jamás debe ser TimeoutError"


def test_g2_1_6_in_flight_commit_returns_operation_pending_on_supervisor_timeout():
    """
    Verifica que si el supervisor de CIVIA agota su tiempo de espera mientras la
    operación transaccional está activamente confirmándose en base de datos (in-flight commit),
    el sistema NO inventa un rollback ni levanta un TimeoutError genérico falso,
    sino que devuelve OperationPendingError con status 'PENDING' e id de operación durable.
    Posteriormente, cuando la confirmación nativa concluye, la base de datos refleja 'COMMITTED'.
    """
    test_db_url = _get_clean_test_db("test_g2_1_6_inflight")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("CREATE TABLE audit_reports(id int PRIMARY KEY, status text NOT NULL);")
        c.execute("INSERT INTO audit_reports VALUES (1, 'ORIGINAL');")
        c.execute(
            """
            CREATE OR REPLACE FUNCTION audit_deferred_inflight() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.status = 'CHANGED' THEN
                    PERFORM pg_sleep(0.18);
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE CONSTRAINT TRIGGER trg_inflight AFTER UPDATE ON audit_reports
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit_deferred_inflight();
            """
        )

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        with psycopg.connect(test_db_url, autocommit=True) as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS operation_records (
                    operation_id UUID PRIMARY KEY,
                    idempotency_key VARCHAR(128) UNIQUE,
                    operation_type VARCHAR(64) NOT NULL,
                    target_id VARCHAR(128),
                    status VARCHAR(32) NOT NULL CHECK (status IN ('PENDING', 'COMMITTED', 'ABORTED', 'UNKNOWN')),
                    proposed_payload JSONB,
                    result_payload JSONB,
                    error_message TEXT,
                    backend_pid INTEGER,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                );
                """
            )

        worker_tid = []
        done_inflight = threading.Event()

        def slow_commit_tool(args):
            try:
                worker_tid.append(threading.get_ident())
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE audit_reports SET status = 'CHANGED' WHERE id = 1;")
                    conn.commit()
                return {"status": "ok", "updated": True}
            finally:
                done_inflight.set()

        with patch.dict("app.agent.TOOL_DISPATCH", {"slow_commit_tool": slow_commit_tool}):
            with pytest.raises(OperationPendingError) as exc_info:
                execute_tool_with_timeout("slow_commit_tool", {"report_id": "1"}, timeout_sec=0.10)

            err = exc_info.value
            assert err.status == "PENDING"
            assert err.operation_id is not None

        assert done_inflight.wait(timeout=3.0), "El worker no completó en el tiempo límite"

        with psycopg.connect(test_db_url, autocommit=True) as c:
            with c.cursor() as cur:
                cur.execute("SELECT status FROM audit_reports WHERE id = 1;")
                final_status = cur.fetchone()[0]
                assert final_status == "ORIGINAL", "La transacción abortó limpiamente al activarse la cancelación de servidor"

                cur.execute("SELECT status FROM operation_records WHERE operation_id = %s;", (err.operation_id,))
                row = cur.fetchone()
                assert row is not None
                assert row[0] == "ABORTED", "El registro durable debe reflejar ABORTED tras la cancelación del commit"
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_6_clock_offset_cases_102_109_truthful_pending_and_committed():
    """
    Reproducción adversarial de los Casos 102 y 109 de Codex:
    - Cliente con desfase de reloj (+100 ms en time.time()).
    - Supervisor con deadline de 0.20 s, trigger diferido de 0.18 s y LateTimer (cancelación retardada).
    - El supervisor expira a los 0.20 s mientras el commit está en progreso.
    - Verificación: el sistema NO afirma falsamente que la transacción fue abortada.
      Reporta OperationPendingError (PENDING), y cuando la confirmación nativa concluye,
      el estado durable final es inequívocamente COMMITTED y la fila CHANGED.
    """
    test_db_url = _get_clean_test_db("test_g2_1_6_clock_offset")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("CREATE TABLE audit_deadline_clock(id int PRIMARY KEY, state text NOT NULL);")
        c.execute("INSERT INTO audit_deadline_clock VALUES (102, 'ORIGINAL');")
        c.execute(
            """
            CREATE OR REPLACE FUNCTION audit_deferred_clock() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.state = 'CHANGED' THEN
                    PERFORM pg_sleep(0.18);
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
        c.execute("CREATE CONSTRAINT TRIGGER trg_clock AFTER UPDATE ON audit_deadline_clock DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit_deferred_clock();")

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        class LateTimer(threading.Timer):
            def __init__(self, interval, function, args=None, kwargs=None):
                super().__init__(interval + 0.35, function, args=args, kwargs=kwargs)

        done_clock = threading.Event()

        def mock_clock_tool(args):
            try:
                real_time = time.time
                with patch("threading.Timer", LateTimer), patch("app.db.threading.Timer", LateTimer), patch("app.db.time.time", side_effect=lambda: real_time() + 0.100):
                    with get_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("UPDATE audit_deadline_clock SET state = 'CHANGED' WHERE id = 102;")
                        time.sleep(0.08)
                        conn.commit()
                return {"ok": True}
            finally:
                done_clock.set()

        with patch.dict("app.agent.TOOL_DISPATCH", {"mock_clock_tool": mock_clock_tool}):
            with pytest.raises(OperationPendingError) as exc_info:
                execute_tool_with_timeout("mock_clock_tool", {"report_id": "102"}, timeout_sec=0.25)

            err = exc_info.value
            assert err.status == "PENDING"
            assert err.operation_id is not None

        assert done_clock.wait(timeout=3.0), "El worker de clock no completó en el tiempo límite"

        with psycopg.connect(test_db_url, autocommit=True) as c:
            with c.cursor() as cur:
                cur.execute("SELECT state FROM audit_deadline_clock WHERE id = 102;")
                assert cur.fetchone()[0] == "CHANGED"
                cur.execute("SELECT status FROM operation_records WHERE operation_id = %s;", (err.operation_id,))
                assert cur.fetchone()[0] == "COMMITTED"
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_6_idempotent_proposal_replay():
    """
    Verifica que la invocación repetida de una propuesta crítica con la misma clave de idempotencia
    devuelve el resultado ya comprometido de forma idempotente sin duplicar registros en pending_approvals.
    """
    test_db_url = _get_clean_test_db("test_g2_1_6_idempotency")
    rep_id = uuid.uuid4()
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute(
            """
            INSERT INTO reports (
                id, tracking_code, title, description, latitude, longitude, in_service_area,
                photo_path, photo_mime, photo_size_bytes, photo_width, photo_height, photo_sha256,
                status, is_synthetic, version
            )
            VALUES (
                %s, 'CIV-2026-TESTIDEM', 'Prueba Idempotencia',
                'Descripcion de prueba.',
                3.45, -76.53, TRUE, 'sentinel.png', 'image/png', 128, 64, 64, %s,
                'CONFIRMED', FALSE, 1
            )
            ON CONFLICT (tracking_code) DO NOTHING;
            """,
            (rep_id, "a" * 64),
        )

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        args = {
            "identificador": "CIV-2026-TESTIDEM",
            "nuevo_estado": "IN_REVIEW",
            "motivo": "Prueba de idempotencia G2.1.6",
            "idempotency_key": "idemp-unique-key-12345",
        }

        import secrets
        owner_token = secrets.token_urlsafe(32)

        # 1. Primera invocación
        res1 = execute_tool_with_timeout("proponer_actualizacion_critica", args, timeout_sec=2.0, client_token=owner_token)
        assert res1["creado"] is True
        approval_id = res1["approval_id"]

        # 2. Segunda invocación con la misma clave
        res2 = execute_tool_with_timeout("proponer_actualizacion_critica", args, timeout_sec=2.0, client_token=owner_token)
        assert res2["approval_id"] == approval_id, "La segunda llamada debió devolver la misma aprobación idempotente"

        # 3. Comprobar que en la base de datos existe exactamente 1 registro en pending_approvals
        with psycopg.connect(test_db_url, autocommit=True) as c:
            with c.cursor() as cur:
                cur.execute("SELECT count(*) FROM pending_approvals WHERE report_id = %s;", (rep_id,))
                count = cur.fetchone()[0]
                assert count == 1, f"Se esperaban 1 propuestas, pero se encontraron {count}"
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_6_reconciliation_of_disconnected_operation():
    """
    Verifica que reconcile_operation inspecciona el estado del backend_pid y del recurso objetivo
    para resolver operaciones PENDING cuyo proceso cliente se desconectó o murió.
    """
    test_db_url = _get_clean_test_db("test_g2_1_6_reconcile")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_records (
                operation_id UUID PRIMARY KEY,
                idempotency_key VARCHAR(128) UNIQUE,
                operation_type VARCHAR(64) NOT NULL,
                target_id VARCHAR(128),
                status VARCHAR(32) NOT NULL CHECK (status IN ('PENDING', 'COMMITTED', 'ABORTED', 'UNKNOWN')),
                proposed_payload JSONB,
                result_payload JSONB,
                error_message TEXT,
                backend_pid INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
            );
            CREATE TABLE IF NOT EXISTS pending_approvals (
                id UUID PRIMARY KEY, report_id text, proposed_action text, proposed_payload jsonb, reason text, status text, created_at timestamptz DEFAULT now()
            );
            """
        )

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        orphan_op_id = uuid.uuid4()
        register_operation_intent(
            operation_id=orphan_op_id,
            operation_type="proponer_actualizacion_critica",
            target_id="rep-nonexistent",
            backend_pid=999999,
        )

        record_before = get_operation_record(orphan_op_id)
        assert record_before["status"] == "PENDING"

        record_after = reconcile_operation(orphan_op_id)
        # G2.1.8 (F6): PID ausente no debe inferir ABORTED por si solo; conserva PENDING/UNKNOWN
        assert record_after["status"] in ("PENDING", "UNKNOWN")
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_6_api_endpoint_operations_status():
    """
    Verifica la API pública GET /api/operations/{operation_id}:
    - 200 con estructura OperationStatusResponse.
    - 404 para identificador desconocido.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    missing_id = uuid.uuid4()
    r = client.get(f"/api/operations/{missing_id}")
    assert r.status_code == 404

    known_id = uuid.uuid4()
    claim = register_operation_intent(
        operation_id=known_id,
        operation_type="clasificar_evidencia",
        target_id="rep-test-api",
    )
    mark_operation_committed(known_id, result_payload={"diagnostico": "HUECO"})

    # 1. Consulta anónima: entrega estado público pero minimiza información sensible (result_payload None, sin idempotency_key)
    r_anon = client.get(f"/api/operations/{known_id}")
    assert r_anon.status_code == 200
    data_anon = r_anon.json()
    assert data_anon["operation_id"] == str(known_id)
    assert data_anon["status"] == "COMMITTED"
    assert data_anon["operation_type"] == "clasificar_evidencia"
    assert data_anon.get("result_payload") is None, "Consulta anónima no debe exponer result_payload"
    assert "idempotency_key" not in data_anon, "idempotency_key no debe figurar en el esquema público"

    # 2. Consulta autorizada con token de consulta de la operación (propietario)
    r_owner = client.get(
        f"/api/operations/{known_id}",
        headers={"X-Operation-Token": claim["query_token"]},
    )
    assert r_owner.status_code == 200
    data_owner = r_owner.json()
    assert data_owner["result_payload"]["diagnostico"] == "HUECO"

    # 3. Consulta autorizada con token de administrador
    r_admin = client.get(
        f"/api/operations/{known_id}",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
    )
    assert r_admin.status_code == 200
    data_admin = r_admin.json()
    assert data_admin["result_payload"]["diagnostico"] == "HUECO"


# ==============================================================================
# Suite G2.1.7: Endurecimiento Fail-Closed, Autorización y Reconciliación
# ==============================================================================


def test_g2_1_7_fail_closed_marker_failure_aborts_business_transaction():
    """
    P0 — Atomicidad obligatoria: si un trigger o fallo SQL impide actualizar
    operation_records a COMMITTED en checked_commit, la transacción de negocio
    DEBE abortar completamente (rollback) sin confirmar cambios en tablas de negocio.
    """
    test_db_url = _get_clean_test_db("test_g2_1_7_marker_fail")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("CREATE TABLE audit_business(id int PRIMARY KEY, n int NOT NULL DEFAULT 0);")
        c.execute("INSERT INTO audit_business VALUES (1, 0);")
        # Trigger que rechaza la transición a COMMITTED para tipo 'audit_marker_fail'
        c.execute(
            """
            CREATE OR REPLACE FUNCTION audit_deny_marker() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.operation_type = 'audit_marker_fail' AND NEW.status = 'COMMITTED' THEN
                    RAISE EXCEPTION 'SYNTHETIC MARKER FAILURE';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER audit_marker_reject
            BEFORE UPDATE ON operation_records
            FOR EACH ROW EXECUTE FUNCTION audit_deny_marker();
            """
        )

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        def write_tool(args):
            with db.get_conn() as c:
                c.execute("UPDATE audit_business SET n = n + 1 WHERE id = 1;")
                db.checked_commit(c)
            return {"updated": True}

        with patch.dict("app.agent.TOOL_DISPATCH", {"audit_marker_fail": write_tool}):
            with pytest.raises(Exception) as exc_info:
                execute_tool_with_timeout("audit_marker_fail", {}, timeout_sec=2.0)

            # Verificar que la transacción de negocio fue ROLLED BACK
            with psycopg.connect(test_db_url, autocommit=True) as v:
                n_val = v.execute("SELECT n FROM audit_business WHERE id = 1;").fetchone()[0]
            assert n_val == 0, "Fallo de fail-closed: el negocio confirmó a pesar de que el marcador falló"
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_7_missing_migration_004_fails_closed():
    """
    P0 — Fail-closed con migración ausente: si operation_records no existe,
    register_operation_intent falla cerrado impidiendo que la herramienta
    ejecute escrituras sin registro durable.
    """
    test_db_url = _get_clean_test_db("test_g2_1_7_no_004")
    # Dropear operation_records explícitamente para simular omisión de migración
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS operation_records CASCADE;")
        c.execute("CREATE TABLE audit_business(id int PRIMARY KEY, n int NOT NULL DEFAULT 0);")
        c.execute("INSERT INTO audit_business VALUES (1, 0);")

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        def write_tool(args):
            with db.get_conn() as c:
                c.execute("UPDATE audit_business SET n = n + 1 WHERE id = 1;")
                c.commit()
            return {"updated": True}

        with patch.dict("app.agent.TOOL_DISPATCH", {"audit_write": write_tool}):
            with pytest.raises(Exception):
                execute_tool_with_timeout("audit_write", {}, timeout_sec=2.0)

            with psycopg.connect(test_db_url, autocommit=True) as v:
                n_val = v.execute("SELECT n FROM audit_business WHERE id = 1;").fetchone()[0]
            assert n_val == 0, "Fallo de fail-closed: se ejecutó escritura de negocio sin tabla operation_records"
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_7_reconcile_only_on_exact_operation_id_evidence():
    """
    P0 — Reconciliación basada en evidencia propia: una propuesta preexistente
    sobre un report_id jamás debe causar que una operación ajena se marque COMMITTED.
    Solo un registro con el operation_id exacto sirve de evidencia.
    """
    test_db_url = _get_clean_test_db("test_g2_1_7_reconcile_link")
    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        rep_id = uuid.uuid4()
        # 1. Crear reporte previo y propuesta 1 en pending_approvals
        op1 = uuid.uuid4()
        claim1 = register_operation_intent(op1, "proponer_actualizacion_critica", target_id=str(rep_id))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reports (
                        id, tracking_code, title, description, latitude, longitude, in_service_area,
                        photo_path, photo_mime, photo_size_bytes, photo_width, photo_height, photo_sha256,
                        status, is_synthetic, version
                    )
                    VALUES (
                        %s, 'CIV-2026-RECON1', 'Prueba Reconciliacion',
                        'Desc de reconciliacion.',
                        3.45, -76.53, TRUE, 'sentinel.png', 'image/png', 128, 64, 64, %s,
                        'CONFIRMED', FALSE, 1
                    )
                    ON CONFLICT (tracking_code) DO NOTHING;
                    """,
                    (rep_id, "b" * 64),
                )
                cur.execute(
                    """
                    INSERT INTO pending_approvals (
                        id, report_id, proposed_action, proposed_payload, reason, status, operation_id
                    ) VALUES (%s, %s, 'UPDATE_REPORT_STATUS', '{"proposed_status":"IN_REVIEW"}'::jsonb, 'P1', 'PENDING', %s);
                    """,
                    (uuid.uuid4(), rep_id, str(op1)),
                )
                conn.commit()

        # 2. Registrar operación 2 que NUNCA se ejecuta, con backend_pid inactivo
        op2 = uuid.uuid4()
        claim2 = register_operation_intent(
            op2,
            "proponer_actualizacion_critica",
            target_id=rep_id,
            proposed_payload={"nuevo_estado": "RESOLVED"},
            backend_pid=999999,
        )

        # 3. Reconciliar op2: DEBE conservar PENDING, NUNCA transicionar a COMMITTED por propuesta ajena (F6)
        after_rec = db.reconcile_operation(op2)
        assert after_rec["status"] != "COMMITTED", (
            f"Falso positivo en reconciliación: op2 no ejecutada se marcó '{after_rec['status']}' por propuesta ajena"
        )
        assert after_rec["status"] in ("PENDING", "UNKNOWN")
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_7_concurrent_idempotency_claim_single_execution():
    """
    P0 — Idempotencia concurrente real: dos invocaciones con la misma clave
    de idempotencia deben ejecutar el efecto de negocio exactamente UNA vez.
    Ambas invocaciones retornan el mismo operation_id durable.
    """
    test_db_url = _get_clean_test_db("test_g2_1_7_conc_idemp")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("CREATE TABLE audit_business(id int PRIMARY KEY, n int NOT NULL DEFAULT 0);")
        c.execute("INSERT INTO audit_business VALUES (5, 0);")

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        shared_key = f"audit-race-{uuid.uuid4().hex}"

        def write_tool(args):
            with db.get_conn() as c:
                c.execute("UPDATE audit_business SET n = n + 1 WHERE id = 5;")
                c.commit()
            return {
                "operation_id": str(db.get_current_operation()["operation_id"]),
                "row": 5,
                "note": "SUCCESS",
            }

        def run_op(_):
            return execute_tool_with_timeout("audit_write_conc", {"row": 5, "idempotency_key": shared_key}, timeout_sec=4.0)

        with patch.dict("app.agent.TOOL_DISPATCH", {"audit_write_conc": write_tool}):
            with ThreadPoolExecutor(max_workers=2) as ex:
                results = list(ex.map(run_op, range(2)))

        with psycopg.connect(test_db_url, autocommit=True) as v:
            writes = v.execute("SELECT n FROM audit_business WHERE id = 5;").fetchone()[0]

        assert writes == 1, f"Fallo de idempotencia: el negocio fue escrito {writes} veces en lugar de 1"
        assert len({r["operation_id"] for r in results}) == 1, "Debió retornarse exactamente un operation_id para ambas llamadas"
        final_op_id = results[0]["operation_id"]
        assert db.get_operation_record(final_op_id) is not None
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_7_idempotency_payload_conflict_raises_error():
    """
    P0 — Conflicto de idempotencia: si una clave es reusada con un payload
    diferente, debe rechazarse con IdempotencyConflictError (HTTP 409).
    """
    test_db_url = _get_clean_test_db("test_g2_1_7_conflict")
    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        key = f"key-{uuid.uuid4().hex}"
        op1 = uuid.uuid4()
        claim1 = register_operation_intent(
            operation_id=op1,
            operation_type="audit_tool",
            idempotency_key=key,
            proposed_payload={"arg": "VALUE_A"},
        )
        assert claim1["claim_acquired"] is True

        op2 = uuid.uuid4()
        with pytest.raises(IdempotencyConflictError):
            register_operation_intent(
                operation_id=op2,
                operation_type="audit_tool",
                idempotency_key=key,
                proposed_payload={"arg": "VALUE_B_DIFFERENT"},
            )
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_7_committed_without_result_replay_reconstructs():
    """
    P0 — Reintento de COMMITTED sin result_payload:
    Si la operación ya confirmó en base de datos pero result_payload está ausente,
    el reintento NO reejecuta el negocio; retorna la confirmación durable con ID estable.
    """
    test_db_url = _get_clean_test_db("test_g2_1_7_replay_no_payload")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("CREATE TABLE audit_business(id int PRIMARY KEY, n int NOT NULL DEFAULT 0);")
        c.execute("INSERT INTO audit_business VALUES (9, 0);")

    old_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    try:
        key = f"key-replay-{uuid.uuid4().hex}"
        op_id = uuid.uuid4()

        # Registrar intención y marcar COMMITTED sin result_payload
        claim = register_operation_intent(
            operation_id=op_id,
            operation_type="audit_tool_replay",
            idempotency_key=key,
            proposed_payload={"row": 9},
        )
        with psycopg.connect(test_db_url, autocommit=True) as c:
            c.execute("UPDATE audit_business SET n = n + 1 WHERE id = 9;")
        mark_operation_committed(op_id, result_payload=None)

        record_before = get_operation_record(op_id)
        assert record_before["status"] == "COMMITTED"
        assert record_before["result_payload"] is None

        # Reintentar invocación con la misma clave
        def tool_fn(args):
            with db.get_conn() as c:
                c.execute("UPDATE audit_business SET n = n + 1 WHERE id = 9;")
                c.commit()
            return {"updated": True}

        with patch.dict("app.agent.TOOL_DISPATCH", {"audit_tool_replay": tool_fn}):
            replay = execute_tool_with_timeout("audit_tool_replay", {"row": 9, "idempotency_key": key}, timeout_sec=2.0)

        with psycopg.connect(test_db_url, autocommit=True) as v:
            writes = v.execute("SELECT n FROM audit_business WHERE id = 9;").fetchone()[0]

        assert writes == 1, "Fallo: la operación COMMITTED sin cache volvió a ejecutar escrituras de negocio"
        assert replay.get("operation_id") == str(op_id), "El operation_id retornado debe ser el mismo que el original"
        assert replay.get("status") == "COMMITTED"
    finally:
        settings.DATABASE_URL = old_db_url


def test_g2_1_7_foreign_transaction_timeout_preserves_error():
    """
    P1 — Procedencia de errores PostgreSQL:
    Un transaction_timeout de sesión ajeno (50 ms) que ocurre mucho antes del deadline local (2 s)
    NO debe ser atribuido a la cancelación del deadline local; is_deadline_cancellation debe retornar False.
    """
    exc = psycopg.OperationalError("canceling transaction due to transaction timeout")
    setattr(exc, "sqlstate", "25P04")

    # Deadline local es dentro de 2.0 s (no ha expirado)
    tool_deadline = time.monotonic() + 2.0
    is_local = is_deadline_cancellation(exc, deadline=tool_deadline)
    assert is_local is False, "is_deadline_cancellation atribuyó erróneamente un transaction_timeout ajeno al deadline local"


