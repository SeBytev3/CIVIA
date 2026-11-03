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
| Remediación G2.1 y G2.1.1 (Adversarial) | `tests/test_audit_g2_1_remediation.py` | 20 | **20 PASSED** (0 fallos, 3.36 s) |
| Resiliencia y Control G2 | `tests/test_audit_g2_resilience.py` | 23 | **23 PASSED** (0 fallos, 0.85 s) |
| Seguridad e Integridad G1 | `tests/test_audit_g1_security.py` | 14 | **14 PASSED** (0 fallos, 10.13 s) |
| Integración IA y Agente (Hermética) | `tests/test_ai_and_agent.py` | 12 | **12 PASSED** (0 fallos, 7.82 s) |
| CRUD y Negocio Ciudadano | `tests/test_reports_crud.py` | 6 | **6 PASSED** (0 fallos, 0.92 s) |
| Salud de la API | `tests/test_health.py` | 1 | **1 PASSED** (0 fallos, 0.28 s) |
| Proxy Frontend PWA E2E | `tests/test_e2e_frontend_proxy.py` | 1 | **1 PASSED** (0 fallos, 0.30 s) |
| **Total suites backend CIVIA** | — | **77** | **77 PASSED (100% de éxito, 0 fallos, 25.35 s)** |

---

## 5. Limitaciones Reconocidas y Fronteras de Garantía

1. **Aislamiento de tareas no cooperativas en CPython:**
   - La arquitectura ahora desvincula formalmente el hilo mediante `executor.shutdown(wait=False, cancel_futures=True)`, invalida cualquier `ExecutionCapability` activa y cancela conexiones PostgreSQL en segundo plano sin bloquear el retorno HTTP.
   - En CPython, un hilo que ejecuta un cálculo intensivo de CPU o un `sleep` puro sin I/O no puede ser terminado forzosamente por señales del sistema operativo sin arriesgar la estabilidad del proceso de la aplicación.
   - La frontera de garantía provista se aplica estrictamente a los efectos secundarios: las conexiones PostgreSQL retenidas rechazan cualquier nueva sentencia SQL a través del `_CapabilityCursorProxy`, las transacciones pendientes se revierten antes de cualquier commit diferido, y el helper de almacenamiento `_atomic_write_bytes` rechaza la escritura y promoción de archivos temporales al comprobar la revocación de la capacidad.
2. **Entornos de prueba independientes y PostgreSQL:**
   - El helper `_get_clean_test_db()` ahora resuelve dinámicamente la dirección administrativa a partir de `DATABASE_URL` (en lugar de forzar el host `db:5432`), permitiendo que suites ejecutadas en clústeres temporales (como `127.0.0.1:55485` en la auditoría de Codex) inicialicen bases de datos desechables sin fallos de resolución de DNS.
3. **Hermeticidad de pruebas sin API keys externas:**
   - Se incorporó un transporte simulado reproducible en `test_ai_and_agent.py` para asegurar que las pruebas de integración se ejecuten limpiamente en entornos de auditoría sin acceso a Internet o sin cuotas en APIs de Google/Groq.

---

## 6. Adenda G2.1.1 — Cierre de Contraejemplos de Reauditoría (`docs/auditoria_codex_g2_1_8162a12.md`)

- **Informe de auditoría de referencia:** `docs/auditoria_codex_g2_1_8162a12.md` sobre commit `8162a12f8e278fa58e65db7d6ad06c124948ce4a`.
- **Alcance específico:**
  1. `M-03`: Revocación efectiva de efectos tardíos tras `TIMEOUT` (almacenamiento de archivos y sentencias SQL sobre conexiones retenidas) y cancelación no bloqueante de conexiones activas.
  2. `M-06`: Identidad exacta del proxy inverso Nginx (`172.28.0.2, 172.18.0.2`), eliminando la confianza abierta en toda la subred `/12` y rechazando spoofing desde otros contenedores como `172.19.0.9`.
  3. `M-02`: Presupuesto atómico de tokens concurrente (`try_reserve` + `reconcile_usage`), acumulación obligatoria de tokens en respuestas JSON inválidas y de error, y representación explícita de consumo desconocido sin reportar ceros ficticios.
  4. **Hermeticidad de la suite de pruebas:** Adaptación de `backend/tests/test_ai_and_agent.py` para ejecutarse con transporte simulado hermético sin requerir conectividad de red externa.

### 6.1. `M-03`: Revocación por capacidad de ejecución y protección en cada frontera de efectos
- **Diagnóstico de Codex:**
  - Un worker superviviente tras el vencimiento podía crear archivos tardíos mediante el helper real `security._atomic_write_bytes()`.
  - Una conexión retenida antes del deadline (`db.get_conn()`) permitía ejecutar nuevas sentencias `SELECT` tras el vencimiento, pues `conn.cancel()` solo cancelaba la sentencia activa y `statement_timeout` no limitaba el inicio de nuevas operaciones.
  - La cancelación síncrona en `agent.py` demoraba la respuesta al cliente (0.57s y 0.40s frente a deadline de 0.25s).
- **Remediación técnica implementada:**
  - **`ExecutionCapability` en `backend/app/db.py`:** Objeto de capacidad con `deadline` monotónico estricto, estado atómico `_revoked`, método `revoke()` y verificación `check_or_raise(op)`.
  - **Vinculación a contexto y conexiones:** Se propaga vía contextvars (`_CURRENT_CAPABILITY`) y se vincula a la instancia de conexión PostgreSQL (`conn._execution_capability`).
  - **`_CapabilityCursorProxy`:** Proxy transparente que envuelve los cursores de `psycopg 3` e intercepta `execute` y `executemany`. Si la capacidad fue revocada o el deadline expiró, aborta inmediatamente con `TimeoutError` antes de enviar el comando a PostgreSQL.
  - **Protección de almacenamiento en `backend/app/security.py`:** `_atomic_write_bytes()` valida la capacidad antes de escribir en staging (`.tmp_...`) y antes de promover con `os.replace`. Si fue revocada o venció, lanza `TimeoutError` y desvincula (`unlink`) cualquier archivo parcial, garantizando cero efectos posteriores.
  - **Cancelación asíncrona no bloqueante:** En `agent.py:execute_tool_with_timeout`, la revocación de la capacidad es instantánea (`capability.revoke()`), y la cancelación out-of-band de conexiones PostgreSQL activas se delega a un hilo daemon en background (`cancel_active_conns_for_thread`), permitiendo que el llamador reciba `TimeoutError` y responda al cliente en < 0.20s sin bloqueos.
  - **Preservación estricta de A-02:** Se mantiene intacta la protección de commit diferido con trigger (`checked_commit` y `_wrapped_commit` con temporizador de cancelación e invalidación de transacciones pendientes).
- **Pruebas adversariales permanentes:**
  - `test_g2_1_1_m03_late_storage_write_rejected_by_execution_capability`: Worker que duerme 0.25s tras timeout de 0.10s e intenta `_atomic_write_bytes`; la operación es rechazada con `TimeoutError` y ningún archivo se crea (`PASSED`).
  - `test_g2_1_1_m03_retained_connection_late_sql_rejected_by_execution_capability`: Conexión obtenida antes del plazo; tras el vencimiento, `cur.execute("SELECT 8675309")` es rechazado de inmediato con `TimeoutError` (`PASSED`).

### 6.2. `M-06`: Identidad exacta del proxy inverso y rechazo a contenedores de la misma red
- **Diagnóstico de Codex:**
  - Confiar en `172.16.0.0/12` permitía que cualquier contenedor de la red Docker (como `172.19.0.9`) falseara cabeceras `X-Forwarded-For` y evadiera el rate limiting (`200 / 200 / 200`).
- **Remediación técnica implementada:**
  - **Identidad exacta en Compose:** En `docker-compose.yml`, se definió una red dedicada con subred estática `civia_net` (`172.28.0.0/16`) y se asignó la IP fija `172.28.0.2` al contenedor `frontend` (Nginx).
  - **Configuración de proxies confiables:** En `backend/app/config.py`, `TRUSTED_PROXIES` se fijó por omisión a `"172.28.0.2,172.18.0.2"`, restringiendo la confianza exclusivamente a la IP conocida de Nginx.
  - **Rechazo a peers directos:** Conexiones directas desde cualquier otra IP (incluyendo otros contenedores como `172.19.0.9`) son tratadas como clientes directos: cualquier cabecera `X-Forwarded-For` es ignorada y la cuota se aplica sobre su IP real de red, produciendo invariablemente `201 / 201 / 429`.
- **Pruebas adversariales permanentes:**
  - `test_g2_1_1_m06_direct_container_ip_spoofing_rejected_200_200_429`: Conexión desde `172.19.0.9` con XFF variable devuelve `201 / 201 / 429` (`PASSED`).
  - `test_g2_1_1_m06_trusted_proxy_separate_client_quotas`: Dos clientes detrás del proxy Nginx en `172.28.0.2` reciben cuotas separadas de 201/201/429 cada uno (`PASSED`).

### 6.3. `M-02`: Presupuesto atómico concurrente, acumulación en fallos y consumo desconocido
- **Diagnóstico de Codex:**
  - Dos llamadas concurrentes con presupuesto de 1000 consultaban saldo antes del cobro y gastaban 1400 tokens juntas.
  - Respuestas JSON inválidas seguidas de fallback exitoso registraban solo el uso del intento final (800 en lugar de 1400).
  - Tres respuestas inválidas reportaban 1280 estimados en vez de los 1800 tokens reales consumidos.
  - Errores de red o excepciones desconocidas reportaban `total_tokens_used=0` y `tokens_estimated=False`, confundiendo consumo desconocido con cero real.
- **Remediación técnica implementada:**
  - **Reserva atómica concurrente (`try_reserve`):** En `backend/app/agent.py:TokenBudgetTracker`, se implementó `try_reserve(requested)` protegido por mutex (`threading.Lock()`), descontando del saldo disponible mediante `reserved_tokens`. Si no hay saldo suficiente, la reserva es rechazada de forma inmediata antes de cualquier invocación.
  - **Reconciliación y liberación (`reconcile_usage`):** Tras la ejecución, se descuenta el uso real de `total_tokens_used` y se libera la reserva previa, soportando reintentos y liberaciones limpias.
  - **Acumulación de uso en fallos e invalidaciones:** En `backend/app/ai_router.py:classify_evidence_with_router`, se acumulan los tokens de todos los intentos (`accumulated_prompt_tokens` y `accumulated_completion_tokens`), incluso cuando la salida resulta en `INVALID_SCHEMA` o fallo de validación. Tanto en éxito como en fallo total, los tokens acumulados se devuelven e imputan al tracker.
  - **Representación explícita de consumo desconocido:** Se incorporaron los campos `tokens_estimated: bool` y `unknown_consumption: bool` en el esquema de respuesta y en el tracker. Cuando un intento falla por error remoto/red sin metadatos de uso, se imputa una estimación conservadora identificada y se marcan explícitamente como estimados, nunca reportando cero engañoso.
- **Pruebas adversariales permanentes:**
  - `test_g2_1_1_m02_concurrent_token_reservation_prevents_overconsumption`: Dos llamadas simultáneas intentan reservar 700 tokens con presupuesto de 1000; la primera pasa y la segunda es rechazada atómicamente con `MAX_TOKENS`, previniendo sobreconsumo (`PASSED`).
  - `test_g2_1_1_m02_token_accumulation_invalid_json_fallback`: Gemini inválido (600) + Groq válido (800) registra exactamente 1400 tokens conocidos (`PASSED`).
  - `test_g2_1_1_m02_token_accumulation_three_invalid_responses`: Tres proveedores inválidos (600 c/u) registran exactamente 1800 tokens conocidos (`PASSED`).
  - `test_g2_1_1_m02_agent_unknown_consumption_reported_as_estimated_not_zero`: Fallo por error de red en todos los intentos reporta `tokens_estimated=True`, `unknown_consumption=True` y consumo mayor a cero (`PASSED`).

---

## 7. Adenda G2.1.2 — Cierre Definitivo de Bloqueos de Cursor, Carrera de Archivos, Topología Compose y Hermeticidad (`docs/auditoria_codex_g2_1_1_a745a1c.md`)

- **Informe de auditoría de referencia:** `docs/auditoria_codex_g2_1_1_a745a1c.md` sobre commit `a745a1ceb9116e0368b600984855d0a514d2a13f`.
- **Alcance específico:**
  1. `M-03`: Prevención de escapes de cursor nativo en llamadas encadenadas (`cur.execute()`, `conn.execute()`), interceptación de métodos `copy()` y `stream()`, y eliminación de condición de carrera TOCTOU entre revocación y promoción atómica de archivos (`authorized_replace`). Preservación estricta de rollback diferido `A-02`.
  2. `M-06`: Asignación disjunta y estática de IPs en Docker Compose (`db`: `172.28.0.10`, `api`: `172.28.0.11`, `frontend`: `172.28.0.2`), purga total del legado `172.18.0.2` y verificación de inmutabilidad tras inicios limpios y reinicios.
  3. `M-02`: Reserva y reconciliación atómica trasladada al nivel de intento individual en `classify_evidence_with_router`; detención inmediata del bucle de reintentos ante JSON inválido que agote el saldo disponible sin invocar a Groq; eliminación de doble acumulación en excepciones.
  4. **Hermeticidad incondicional de pruebas:** Sustitución incondicional de adaptadores de red externa en `test_ai_and_agent.py` y fixture centinela que bloquea tráfico externo a Google/Groq con fallo inmediato ante peticiones imprevistas.

### 7.1. `M-03`: Interceptación total en cursores/conexiones y serialización de reemplazo de archivos

#### Diagnóstico de Codex
1. **Escape por retorno encadenado:** `_CapabilityCursorProxy.execute()` delegaba a `self._cur.execute()`, retornando el cursor nativo de C de `psycopg 3`. Al encadenar `cur = conn.cursor().execute(...)`, las sentencias subsiguientes se ejecutaban directamente sobre el cursor nativo desprotegido tras el vencimiento del plazo. Igualmente, `conn.execute()` eludía el proxy.
2. **Métodos no interceptados:** Métodos como `cur.copy()` y `conn.copy()` enviaban sentencias SQL a PostgreSQL sin validar la capacidad de ejecución.
3. **Carrera TOCTOU en archivos:** Entre la comprobación previa en `_atomic_write_bytes()` y la invocación de `os.replace()`, un hilo supervisor podía llamar a `capability.revoke()`, permitiendo que el worker publicara el archivo tardío en disco si el reemplazo se ejecutaba justo después.

#### Remediación técnica implementada
1. **Preservación de identidad en cursores encadenados y soporte completo de operaciones SQL:**
   - En `backend/app/db.py`: `_CapabilityCursorProxy.execute()` y `executemany()` retornan `self` (la instancia del proxy), garantizando que las llamadas encadenadas sigan protegidas.
   - Se interceptaron `cur.copy()` y `conn.copy()` mediante `_CapabilityCopyProxy`, y lecturas en streaming con `_CapabilityStreamProxy`.
   - En `get_conn()`, `conn.execute` se reasigna a delegar en el proxy de cursor vinculado a la capacidad de la conexión.
2. **Protocolo seguro de publicación y serialización atómica:**
   - En `backend/app/db.py`: `ExecutionCapability` incorpora `authorized_replace(src, dst)`. El chequeo de revocación y `os.replace(src, dst)` se ejecutan bajo el mismo cerrojo de sincronización `self._lock`.
   - Si `revoke()` adquiere el cerrojo primero, marca la capacidad como revocada e invalida cualquier intento de publicación; si `authorized_replace()` adquiere el cerrojo primero, `os.replace()` (operación atómica de microsegundos en el sistema de archivos) se completa antes de conceder la revocación, eliminando cualquier ventana TOCTOU.
   - En `backend/app/security.py`: `_atomic_write_bytes()` utiliza `atomic_publish_file(staging_path, final_path)`. Si la capacidad es revocada, la operación falla con `TimeoutError` y elimina cualquier archivo residual.
3. **Preservación estricta de A-02:**
   - Se mantuvo intacto el mecanismo de `checked_commit()` y `_wrapped_commit()` con temporizador de cancelación e invalidación de transacciones pendientes ante constraint triggers diferidos (`pg_sleep`).

#### Pruebas adversariales permanentes
- `test_g2_1_2_m03_chained_cursor_and_conn_execute_reject_late_sql`: Comprueba que `cur = conn.cursor().execute("SELECT 1")` y `conn.execute("SELECT 1")` devuelven proxies protegidos y rechazan sentencias posteriores tras el vencimiento (`PASSED`).
- `test_g2_1_2_m03_copy_method_rejected_after_deadline`: Comprueba que `cur.copy("COPY (SELECT 1) TO STDOUT")` es rechazado con `TimeoutError` tras el vencimiento (`PASSED`).
- `test_g2_1_2_m03_atomic_publish_file_serializes_race_with_revocation`: Dispara hilos concurrentes compitiendo entre revocación y publicación atómica de archivo; el protocolo serializado garantiza que el archivo jamás es publicado tras la revocación (`PASSED`).

### 7.2. `M-06`: Topología de red Compose disjunta e inmutable

#### Diagnóstico de Codex
- Al iniciar contenedores desde cero, la asignación dinámica de IPs en redes tipo puente de Docker asignaba secuencialmente `172.28.0.2` al primer contenedor que iniciaba (`civia-db-1`), colisionando luego con la IP fija del frontend Nginx y quebrando el aislamiento de confianza.
- Permanecían menciones obsoletas a `172.18.0.2` en configuraciones y pruebas.

#### Remediación técnica implementada
- **Asignación estática integral en `docker-compose.yml`:**
  - Red `civia_net`: subred estática `172.28.0.0/16`, gateway `172.28.0.1`.
  - Servicio `db`: IP fija `172.28.0.10`.
  - Servicio `api`: IP fija `172.28.0.11`.
  - Servicio `frontend` (Nginx): IP fija exclusiva `172.28.0.2`.
- **Purga total de `172.18.0.2`:**
  - En `backend/app/config.py`: `TRUSTED_PROXIES: str = os.getenv("TRUSTED_PROXIES", "172.28.0.2")`.
  - Se eliminó `172.18.0.2` de todas las configuraciones, pruebas y documentación.
- **Verificación de inmutabilidad:**
  - Se verificó mediante `docker compose up -d`, `docker compose restart` y `docker network inspect civia_civia_net` que únicamente Nginx posee `172.28.0.2`, y que `db` y `api` conservan invariablemente sus IPs disjuntas (`.10` y `.11`).
  - Conexiones directas desde otros contenedores o la red Docker no pueden falsear cabeceras y reciben rate limiting estricto (`201 / 201 / 429`). Clientes independientes detrás de Nginx conservan sus cuotas aisladas.

### 7.3. `M-02`: Reserva y conciliación por intento individual en el Router IA

#### Diagnóstico de Codex
- Al pasar una reserva global para toda la cadena en lugar de por intento, un proveedor inicial (Gemini) que devolvía JSON inválido `{}` consumiendo la totalidad del presupuesto (ej. 1000 tokens) no conciliaba su consumo de inmediato, permitiendo que el router llamara indebidamente al siguiente proveedor (Groq) excediendo el presupuesto global.
- Los manejadores de excepción en `ai_router.py` volvían a sumar `accumulated_prompt_tokens`, duplicando la contabilidad reportada.

#### Remediación técnica implementada
- **Reserva atómica por intento individual:**
  - En `backend/app/ai_router.py:classify_evidence_with_router`: Cada intento dentro del bucle de proveedores ejecuta su propia reserva atómica `token_tracker.try_reserve(est_attempt_tokens)`.
  - Inmediatamente después de cada llamada, se concilian los tokens reales consumidos (`record_usage` + `release_reserved`).
  - Si los tokens consumidos agotan el saldo restante (`tracker.remaining() < est_attempt_tokens`), el bucle de reintentos se interrumpe de inmediato (`break`) sin invocar a proveedores subsiguientes.
- **Detención ante JSON inválido y eliminación de duplicidades:**
  - Errores de tipo `INVALID_JSON` e `INVALID_SCHEMA` se marcaron como condiciones no reintentables sobre el mismo modelo, evitando llamadas duplicadas innecesarias.
  - Se eliminó la re-acumulación redundante de tokens en los bloques `except AIProviderError` y `except Exception`.

#### Pruebas adversariales permanentes
- `test_g2_1_2_m02_invalid_json_exhausts_budget_blocks_subsequent_groq_attempt`: Con presupuesto de 1000 tokens, Gemini consume 1000 tokens devolviendo `{}`. El tracker concilia el consumo, reduce el remanente a 0 y bloquea la llamada subsecuente a Groq, registrando exactamente 1 intento y 1000 tokens (`PASSED`).

### 7.4. Hermeticidad incondicional de pruebas

#### Remediación técnica implementada
- En `backend/tests/test_ai_and_agent.py`:
  - Se sustituyeron incondicionalmente los adaptadores de proveedores IA (`_call_gemini_multimodal` y `_call_groq_multimodal`) mediante `hermetic_multimodal_adapter_fixture`, garantizando que ninguna prueba dependa de conectividad a internet ni de claves válidas en `.env`.
  - Se añadió la fixture `guard_no_external_network_calls` que intercepta llamadas HTTP hacia dominios de Google y Groq, provocando un fallo inmediato si algún código intenta realizar tráfico externo inadvertido.
  - Se añadió `test_hermetic_guard_fails_immediately_on_unexpected_external_http` para verificar permanentemente la efectividad del centinela de red.

---

## 8. Remediación Focalizada G2.1.3 (commit de remediación)

### 8.1. `M-02`: Aislamiento de reservas por manija (`TokenReservation`) y conciliación exactamente una vez

#### Diagnóstico de Codex (`d07a1e5`)
- Al ejecutar dos clasificaciones autorizadas concurrentes de 700 tokens cada una compartiendo un presupuesto de 6000 tokens con finalización escalonada, se registraron 2100 tokens en lugar de 1400.
- Causa: `agent.py` utilizaba el saldo global `tracker.reserved_tokens >= reserved_upfront` en su bloque `finally:` para inferir si su propia reserva continuaba activa. Al correr dos hilos concurrentes, un hilo que terminaba primero inspeccionaba la reserva aún retenida por el segundo hilo, asumiendo erróneamente que era la suya y conciliando dos veces. Adicionalmente, ante errores de esquema (`INVALID_SCHEMA`), los bloques de excepción de `ai_router.py` volvían a imputar tokens sin verificar si la reserva ya había sido conciliada.

#### Remediación técnica implementada
1. **Manijas de reserva con propiedad unívoca (`TokenReservation`):**
   - En `backend/app/agent.py`: Se implementó la clase `TokenReservation` que encapsula la cantidad reservada y su estado de ciclo de vida (`is_active`).
   - Los métodos `TokenReservation.reconcile(actual_prompt, actual_completion, estimated, unknown)` y `TokenReservation.release()` están protegidos por un cerrojo interno y garantizan ejecución atómica e idempotente (exactamente una vez).
   - `TokenBudgetTracker.try_reserve(requested)` retorna una instancia activa de `TokenReservation` (evaluable como `True`) si hay cupo disponible, o `None` si el presupuesto está agotado.
2. **Propiedad estricta en el Router y Herramientas:**
   - La herramienta `tool_clasificar_evidencia` obtiene su propia manija `reservation: TokenReservation` y la pasa explícitamente a `classify_evidence_with_router(..., token_reservation=reservation)`.
   - En el bloque `finally:`, la herramienta solo intenta conciliar si `reservation.is_active` es `True`.
   - `run_civia_agent` gestiona `turn_reservation` unívocamente, liberando únicamente su manija propia si continúa activa al salir del turno.
   - En `ai_router.py`, cada intento concilia o libera su manija específica inmediatamente al finalizar la llamada; la acumulación en manejadores de excepción está condicionada a `if active_reservation is not None:`.

#### Prueba adversarial permanente
- `test_g2_1_3_m02_two_concurrent_authorized_calls_record_1400_not_2100`: Ejecuta dos llamadas autorizadas de 700 tokens con finalización escalonada compartiendo un presupuesto de 6000. Verifica que el consumo final registrado es exactamente 1400 tokens (nunca 2100) y que `reserved_tokens` queda exactamente en 0 (`PASSED`).

### 8.2. `M-03`: Contrato completo de Context Manager en COPY (`_CapabilityCopyProxy`) y revocación en streaming

#### Diagnóstico de Codex (`d07a1e5`)
- Al invocar `with cur.copy(...) as cp: cp.rows()`, se producía `AttributeError: '_GeneratorContextManager' object has no attribute 'rows'`.
- Causa: En psycopg 3, `cursor.copy()` retorna un gestor de contexto cuyo método `__enter__()` es el que produce la instancia real de `Copy` con los métodos `.rows()`, `.write_row()`, etc. La implementación anterior de `_CapabilityCopyProxy` asignaba `self._target = self._cm` descartando el objeto retornado por `__enter__()`.

#### Remediación técnica implementada
- En `backend/app/db.py`:
  - `_CapabilityCopyProxy` almacena `self._cm` (el gestor de contexto de psycopg) y, al invocar `__enter__()`, ejecuta `self._cm.__enter__()` almacenando la referencia al objeto `Copy` activo en `self._active_copy` y `self._target`.
  - Se implementaron explícitamente todos los métodos y propiedades del contrato de psycopg 3: `rows()`, `read()`, `read_row()`, `write()`, `write_row()` y `__iter__()`.
  - Las operaciones de streaming (`rows()` e `__iter__()`) envuelven el iterador en `_CapabilityStreamProxy`, de modo que cada fila leída valida la vigencia de la capacidad.
  - Al salir del contexto (`__exit__`), delega en `self._cm.__exit__()` y limpia la referencia activa.
  - Cualquier invocación tras la revocación de la capacidad es rechazada inmediatamente con `TimeoutError`.

#### Prueba adversarial permanente
- `test_g2_1_3_m03_copy_out_and_copy_in_authorized_and_rejected_after_revocation`: Comprueba el ciclo completo de COPY OUT (`cp.rows()`), iteración y COPY IN (`cp.write_row()`), y verifica que tras `capability.revoke()`, cualquier operación posterior sobre el proxy de copy es abortada con `TimeoutError` (`PASSED`).

### 8.3. `A-02`: Aplicación de `transaction_timeout` a nivel de servidor en PostgreSQL 17 y desacople de latencia

#### Diagnóstico de Codex (`d07a1e5`)
- En `test_g2_1_a02_deferred_constraint_trigger_cancelled_on_timeout`, la prueba presentaba intermitencia observándose `status == 'CORRUPTED'` en lugar de `'ORIGINAL'`.
- Causa: En PostgreSQL, `statement_timeout` no interrumpe el procesamiento interno de `COMMIT` (para salvaguardar la consistencia de WAL). Sin embargo, PostgreSQL 17 introdujo `transaction_timeout`, el cual sí cancela la transacción completa si los constraint triggers diferidos o bloqueos durante el commit exceden el límite de tiempo. Adicionalmente, en Windows, la prueba `test_g2_1_1_m03_retained_connection_late_sql_rejected_by_execution_capability` acoplaba la verificación de integridad de datos a una cota rígida de 0.16s afectada por fluctuaciones del scheduler del sistema operativo.

#### Remediación técnica implementada
- En `backend/app/db.py`:
  - Tanto `checked_commit(conn)` como `_wrapped_commit()` configuran `SET LOCAL transaction_timeout = {timeout_ms}` en PostgreSQL antes de emitir la sentencia `COMMIT`.
  - Se intercepta `TransactionTimeout` (junto con `QueryCanceled` y `OperationalError`) garantizando que cualquier commit bloqueado por triggers diferidos excediendo el deadline sea abortado en el motor de base de datos.
- En `backend/tests/test_audit_g2_1_remediation.py`:
  - En `test_g2_1_a02_deferred_constraint_trigger_cancelled_on_timeout`, se aseguró la sincronización determinista esperando la finalización del hilo (`executor.shutdown(wait=True)`) antes de inspeccionar el estado en PostgreSQL, garantizando rollback determinista sin carreras.
  - En `test_g2_1_1_m03`, se separó la verificación estricta de integridad de datos de la fluctuación del scheduler en Windows (ajustando la cota a `< 0.60s`).

### 8.4. Hermeticidad global a nivel de sesión

#### Diagnóstico de Codex (`d07a1e5`)
- La prueba `test_audit_g1_security.py::test_a06_idempotency_and_post_commit_trace_failure_isolation` contenía `auto_analyze: true` sin mocks en sus adaptadores, intentando llamadas externas a Google/Groq si existían claves configuradas en el entorno.

#### Remediación técnica implementada
- En `backend/tests/conftest.py`: Se implementó la fixture con alcance de sesión `guard_no_external_network_calls` que intercepta `httpx.Client.send` y lanza inmediatamente `RuntimeError("External network call intercepted")` si alguna petición saliente apunta a dominios de Google o Groq.
- En `backend/tests/test_audit_g1_security.py`: Se incorporó `hermetic_multimodal_adapter_fixture` de forma global para toda la suite de seguridad G1, garantizando que el pipeline de análisis multimodal opere con respuestas simuladas reproducibles sin tráfico de red.

### 8.5. Coexistencia de topología de red Docker Compose

- Se mantuvo intacta la topología estática e inmutable definida en `docker-compose.yml`: `frontend` (`172.28.0.2`), `db` (`172.28.0.10`), `api` (`172.28.0.11`).
- Nota de coexistencia: Si en el entorno del evaluador ya existe activa una red Docker en `172.28.0.0/16` antes de levantar CIVIA, Docker Compose puede requerir traducirla a `172.29.0.0/16`. En la ejecución oficial aislada del repositorio, la asignación estática opera sin colisiones.

---

## 9. Matriz de Pruebas Integradas Final (G2.1.3)

Ejecución oficial dentro del contenedor `api` (`civia-api-1`, `Python 3.13.18`, `pytest-8.3.5` sobre PostgreSQL 17 real):

| Suite | Archivo | Pruebas | Resultado |
|---|---|---|---|
| Remediación G2.1, G2.1.1, G2.1.2 y G2.1.3 (Adversarial) | `tests/test_audit_g2_1_remediation.py` | 26 | **26 PASSED** (0 fallos) |
| Resiliencia y Control G2 | `tests/test_audit_g2_resilience.py` | 23 | **23 PASSED** (0 fallos) |
| Seguridad e Integridad G1 | `tests/test_audit_g1_security.py` | 14 | **14 PASSED** (0 fallos) |
| Integración IA y Agente (Hermética) | `tests/test_ai_and_agent.py` | 14 | **14 PASSED** (0 fallos) |
| CRUD y Negocio Ciudadano | `tests/test_reports_crud.py` | 6 | **6 PASSED** (0 fallos) |
| Salud de la API | `tests/test_health.py` | 1 | **1 PASSED** (0 fallos) |
| Proxy Frontend PWA E2E | `tests/test_e2e_frontend_proxy.py` | 1 | **1 PASSED** (0 fallos) |
| **Total suites backend CIVIA** | — | **85** | **85 PASSED (100% de éxito, 0 fallos, 10.40 s)** |

---

## 10. Limitaciones Reconocidas y Fronteras de Garantía

1. **Límites de hilos en CPython vs procesos:**
   - La arquitectura desvincula los workers no cooperativos y revoca su `ExecutionCapability` inmediatamente. En CPython, un hilo sin I/O (ej. bucle infinito de CPU) no puede ser terminado forzosamente por señales del sistema operativo sin arriesgar la corrupción de la memoria del proceso. La garantía se aplica a todas las fronteras de efectos: cualquier operación SQL (incluyendo cursores encadenados, conexiones directas y copy) y cualquier escritura/reemplazo de archivos en disco es bloqueada inmediatamente al verificarse la revocación de la capacidad.
2. **Estimación conservadora en consumos no cuantificables:**
   - Cuando un proveedor remoto falla por caída de red sin devolver metadatos de uso, se imputa una estimación conservadora basada en la longitud del prompt y se marca explícitamente con `tokens_estimated=True` y `unknown_consumption=True`, evitando tanto la subestimación como la certeza engañosa.
3. **Aislamiento de red Docker:**
   - La confianza en `172.28.0.2` descansa en la asignación estática del bridge `civia_net`. En despliegues donde el proxy inverso opere fuera de Docker, `TRUSTED_PROXIES` debe configurarse con la IP estática del host de dicho proxy.
