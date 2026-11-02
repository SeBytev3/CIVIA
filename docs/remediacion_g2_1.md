# Remediación G2.1 — Cierre Definitivo de Hallazgos Residuales de Auditoría (M-03, M-06, M-02)

- **Proyecto:** CIVIA — Momento Evaluativo 2 (Ingeniería de Aplicaciones con IA)
- **Equipo:** Stefania Córdoba y Sebastian Espinosa
- **Rama activa:** `fix/auditoria-final`
- **Informe de auditoría de referencia:** `docs/auditoria_codex_g2_1.md` sobre commit `5b36fb55f87dc49e3256f9814cddb47e3cb3b800`
- **Base de datos de prueba:** PostgreSQL 17 real (`postgres:17-alpine`) en Docker Compose, bases de datos desechables creadas dinámicamente mediante `DATABASE_URL` (`test_g2_1_*`)
- **Alcance estricto de este bloque:** Remediación integral y verificación adversarial de las tres deficiencias residuales señaladas por Codex:
  1. `M-03`: Deadline integral, aislamiento de workers no cooperativos, manejador final sin HTTP 500 y soporte literal para 0.10 s en esquema.
  2. `M-06`: Distinción estricta de proxy vs entrada directa, desactivación de `proxy_headers` en Uvicorn y cierre de evasión en loopback y rangos privados.
  3. `M-02`: Propagación de `_ACTIVE_TOKEN_TRACKER` al executor y reserva dinámica de tokens multimodales previa a la invocación del router.

---

## 1. Prioridad 2 — `M-03`: Deadline integral y fallback honesto

### Diagnóstico de Codex (`docs/auditoria_codex_g2_1.md`)
1. **Worker no cooperativo:** Una herramienta que duerme 0.45 s sin conexiones PostgreSQL retenía la solicitud durante 0.4564 s ante un límite de 0.10 s, debido a que `executor.shutdown(wait=True)` y `future.exception(timeout=0.15)` esperaban la finalización completa del hilo.
2. **Manejador final HTTP con `NameError`:** Al inyectar `TimeoutError` en `main.run_civia_agent`, el endpoint `/api/agent/query` devolvía HTTP 500 porque `main.py:548` utilizaba `uuid.uuid4()`, pero el módulo solo importaba `from uuid import UUID` (no el módulo `uuid`).
3. **Rechazo por esquema de timeout 0.10 s:** Una petición HTTP con `total_timeout_seconds=0.10` recibía HTTP 422, dado que `schemas.py` mantenía `gt=0.1`.

### Remediación técnica implementada
1. **Aislamiento y no retención de workers no cooperativos:**
   - En `backend/app/agent.py:execute_tool_with_timeout`:
     - Se eliminó el retraso bloqueante de `future.exception(timeout=0.15)`.
     - En el bloque `finally:`, se invoca `executor.shutdown(wait=False, cancel_futures=True)`.
     - Al expirar `timeout_sec`, se cancelan las conexiones PostgreSQL activas (`cancel_active_conns_for_thread`) y la función levanta de inmediato `TimeoutError` sin esperar la finalización de tareas de CPU o sleeps no cooperativos (duración < 0.20 s frente al límite de 0.10 s).
     - Si el worker intenta interactuar con la BD posteriormente, `get_conn()` y `checked_commit()` abortan inmediatamente por vencimiento del deadline context.
2. **Manejador HTTP final con importación correcta:**
   - En `backend/app/main.py`: se incorporó `import uuid` en los imports de nivel superior.
   - Ante `TimeoutError`, el manejador genera un `trace_group_id` UUID válido mediante `str(uuid.uuid4())`, retornando HTTP 200 con `guardrail_triggered="TIMEOUT"` y respuesta degradada honesta sin trazas técnicas ni HTTP 500.
3. **Alineación de esquema para soporte de 0.10 s:**
   - En `backend/app/schemas.py`: se ajustó la restricción de `total_timeout_seconds` a `ge=0.10` y `tool_timeout_seconds` a `ge=0.05`.

### Evidencia de prueba adversarial
- Archivo: `backend/tests/test_audit_g2_1_remediation.py`
  - `test_g2_1_m03_uncooperative_worker_does_not_block_timeout`: herramienta no cooperativa con `time.sleep(0.45)` y límite de 0.10 s retorna `TimeoutError` en 0.102 s (< 0.22 s) (`PASSED`).
  - `test_g2_1_m03_endpoint_literal_010_timeout_and_error_handler`: petición HTTP literal con `total_timeout_seconds=0.10` es aceptada (HTTP 200) y ante `TimeoutError` responde con UUID válido y guardrail TIMEOUT sin HTTP 500 (`PASSED`).
  - `test_g2_1_m03_agent_capping_total_timeout_server_side`: acotamiento de timeout del cliente frente al servidor (`PASSED`).
  - `test_g2_1_m03_router_respects_remaining_deadline_without_05s_floor`: rechazo de respuestas del router fuera de plazo (`PASSED`).

---

## 2. Prioridad 3 — `M-06`: Confianza en proxies y anti-spoofing en rate limiting

### Diagnóstico de Codex (`docs/auditoria_codex_g2_1.md`)
1. **Sobrescritura por Uvicorn en loopback:** `CMD ["uvicorn", "app.main:app", ...]` sin banderas explícitas mantenía `proxy_headers: True` y `forwarded_allow_ips: '127.0.0.1'` por omisión en Uvicorn. Al conectar desde loopback, `ProxyHeadersMiddleware` sustituía `scope['client']` por el `X-Forwarded-For` enviado, permitiendo evadir la cuota con peticiones consecutivas (200 / 200 / 200).
2. **Confianza excesiva en redes privadas:** `TRUSTED_PROXIES` contenía `10.0.0.0/8`, por lo que conexiones directas desde `10.20.30.40` eran tratadas como proxys autorizados y aceptaban cabeceras falseadas.
3. **Fallback a loopback en `security.py`:** `get_trusted_proxy_networks()` tenía un fallback que agregaba `127.0.0.1/32` si la lista quedaba vacía.

### Remediación técnica implementada
1. **Desactivación explícita de `proxy_headers` en Uvicorn:**
   - En `backend/Dockerfile`: `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--forwarded-allow-ips", ""]`.
   - En `docker-compose.yml`: se fijó `FORWARDED_ALLOW_IPS: ""` en el servicio `api`.
2. **Restricción estricta de la red del proxy:**
   - En `backend/app/config.py`: se fijó `TRUSTED_PROXIES: str = os.getenv("TRUSTED_PROXIES", "172.16.0.0/12")`. Se eliminaron permanentemente `127.0.0.1`, `::1` y `10.0.0.0/8`.
   - En `backend/app/security.py`: `get_trusted_proxy_networks()` lee `TRUSTED_PROXIES` sin fallback a loopback.
3. **Matriz de confianza en resolución de IP:**
   - Conexiones directas desde `198.51.100.2` (público), `127.0.0.1` (loopback) o `10.20.30.40` (privado directo) NO coinciden con `TRUSTED_PROXIES`.
   - `get_trusted_client_ip()` ignora por completo cualquier cabecera `X-Forwarded-For` o `X-Real-IP` y asigna la cuota a la IP real del peer TCP. Tres peticiones consecutivas con XFF variable devuelven invariablemente `200 / 200 / 429`.
   - Conexiones a través del proxy inverso Nginx (`172.18.0.2`, dentro de `172.16.0.0/12`) son de confianza: Nginx sobrescribe `X-Real-IP` con la IP del cliente real y el rate limiter bloquea al cliente en la 3ª petición (`200 / 200 / 429`).

### Evidencia de prueba adversarial
- Archivo: `backend/tests/test_audit_g2_1_remediation.py`
  - `test_g2_1_m06_dockerfile_cmd_disables_uvicorn_proxy_headers`: valida que el CMD del Dockerfile incluye `--no-proxy-headers` y `--forwarded-allow-ips ""` (`PASSED`).
  - `test_g2_1_m06_anti_spoofing_full_matrix_public_loopback_private_proxy`: reproduce la matriz completa de 4 escenarios de Codex (público, loopback, privado y proxy Docker Nginx), verificando que en todos los casos tres solicitudes con XFF variable resultan en `200 / 200 / 429` (`PASSED`).
- Archivo: `backend/tests/test_audit_g2_resilience.py`
  - `test_m06_trusted_proxy_client_ip`: actualizado para validar proxy Docker con múltiples saltos y conexión directa en loopback (`PASSED`).

---

## 3. Prioridad 4 — `M-02`: Presupuesto de tokens dinámico y contabilidad multimodal

### Diagnóstico de Codex (`docs/auditoria_codex_g2_1.md`)
1. **Pérdida de contexto en el executor:** `agent.py:475-493` no propagaba `_ACTIVE_TOKEN_TRACKER` al hilo de ejecución de `ThreadPoolExecutor`. Dentro del worker thread, `tracker is None`, por lo que una llamada a `clasificar_evidencia` que consumía 1600 tokens no se sumaba al tracker del agente y retornaba 40 tokens en lugar de 1640.
2. **Falta de reserva previa en clasificación multimodal:** Con `max_budget=200`, el prompt de clasificación multimodal requería ~394 tokens estimados de entrada (más imagen y salida). La función solo comprobaba `tracker.remaining() < 150`, por lo que permitía iniciar la llamada y registraba un gasto posterior de 1600 tokens, desbordando el presupuesto asignado.

### Remediación técnica implementada
1. **Propagación explícita de contexto al executor:**
   - En `backend/app/agent.py:execute_tool_with_timeout`:
     - Se captura `active_tracker = _ACTIVE_TOKEN_TRACKER.get()`.
     - Se ejecuta el worker con copia de contexto: `ctx = contextvars.copy_context(); future = executor.submit(ctx.run, _worker)`.
     - Adicionalmente, dentro de `_worker()`, se fija explícitamente `tok_tracker = _ACTIVE_TOKEN_TRACKER.set(active_tracker)`.
     - Esto garantiza que cualquier herramienta ejecutada en el worker thread acceda exactamente a la misma instancia thread-safe de `TokenBudgetTracker`.
2. **Reserva dinámica previa basada en payload antes de invocar al router:**
   - En `backend/app/agent.py:tool_clasificar_evidencia`:
     - Se calcula el prompt multimodal antes de la llamada con `build_classification_prompt`.
     - Se calculan los tokens estimados: `est_input_tokens = ceil(len(prompt)/3.0)` + `est_image_tokens (258 si hay foto)` + `est_output_tokens (80)`.
     - Si `tracker.remaining() < est_total_multimodal`: interrumpe de inmediato retornando `guardrail_triggered = "MAX_TOKENS"`, `analisis_completado = False` y mensaje transparente de saldo insuficiente, realizando CERO llamadas al router IA.
3. **Contabilidad integral reflejada en el agente:**
   - Al completarse la clasificación, `tracker.record_usage(p_tok, c_tok)` se registra en el tracker compartido.
   - El agente finaliza devolviendo la suma de sus propios turnos más la herramienta multimodal (ej. 20 + 1600 + 20 = 1640 tokens).

### Evidencia de prueba adversarial
- Archivo: `backend/tests/test_audit_g2_1_remediation.py`
  - `test_g2_1_m02_multimodal_classification_budget_reservation_prior_to_call`: con `max_budget=200`, calcula el costo de entrada (~394+), comprueba saldo insuficiente, activa `MAX_TOKENS` y verifica 0 llamadas al router y 0 tokens gastados (`PASSED`).
  - `test_g2_1_m02_full_agent_propagates_token_tracker_to_worker_thread`: ejecuta `run_civia_agent` completo con turno que invoca `clasificar_evidencia`. Comprueba que el worker thread hereda el tracker y que el total devuelto por el agente es exactamente 1640 tokens (`PASSED`).
  - `test_g2_1_m02_dynamic_prompt_token_estimation_triggers_max_tokens_before_call`: comprobación de estimación dinámica previa en el turno del agente con presupuesto de 100 tokens (`PASSED`).

---

## 4. Matriz de Pruebas Integradas y Estado de Suites

Ejecución oficial dentro del contenedor `api` (`civia-api-1`, `Python 3.13.18`, `pytest-8.3.5` sobre PostgreSQL 17 real):

| Suite | Archivo | Pruebas | Resultado |
|---|---|---|---|
| Remediación G2.1 (Adversarial) | `tests/test_audit_g2_1_remediation.py` | 12 | **12 PASSED** (0 fallos, 2.45 s) |
| Resiliencia y Control G2 | `tests/test_audit_g2_resilience.py` | 23 | **23 PASSED** (0 fallos, 0.85 s) |
| Seguridad e Integridad G1 | `tests/test_audit_g1_security.py` | 14 | **14 PASSED** (0 fallos, 10.13 s) |
| CRUD y Negocio Ciudadano | `tests/test_reports_crud.py` | 6 | **6 PASSED** (0 fallos, 0.92 s) |
| Salud de la API | `tests/test_health.py` | 1 | **1 PASSED** (0 fallos, 0.28 s) |
| Proxy Frontend PWA E2E | `tests/test_e2e_frontend_proxy.py` | 1 | **1 PASSED** (0 fallos, 0.30 s) |
| **Total suites de auditoría y seguridad** | — | **57** | **57 PASSED (100% de éxito, 0 fallos)** |

---

## 5. Limitaciones Reconocidas y Fronteras de Garantía

1. **Aislamiento de tareas no cooperativas en CPython:**
   - La arquitectura ahora desvincula formalmente el hilo mediante `executor.shutdown(wait=False, cancel_futures=True)` y cancela las conexiones PostgreSQL activas vía timer out-of-band y paquete de cancelación.
   - En CPython, un hilo que ejecuta un sleep puro o un cálculo intensivo de CPU sin llamadas al sistema operativo o a sockets de red no puede ser destruido de forma instantánea por señales sin riesgo de corrupción del intérprete.
   - La garantía provista es de frontera de aplicación: el llamador recibe `TimeoutError` en < 0.20 s, la conexión HTTP responde con la degradación honesta oportuna, y las conexiones de BD quedan invalidadas para impedir que el worker escriba tardíamente si llegara a despertar tras el vencimiento.
2. **Entornos de prueba independientes y PostgreSQL:**
   - El helper `_get_clean_test_db()` ahora resuelve dinámicamente la dirección administrativa a partir de `DATABASE_URL` (en lugar de forzar el host `db:5432`), permitiendo que suites ejecutadas en clústeres temporales (como `127.0.0.1:55483` en la auditoría de Codex) inicialicen bases de datos desechables sin fallos de resolución de DNS.
