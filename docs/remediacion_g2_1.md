# Remediación G2.1 — Cierre de Hallazgos Residuales Prioritarios de Auditoría

- **Proyecto:** CIVIA — Momento Evaluativo 2 (Ingeniería de Aplicaciones con IA)
- **Equipo:** Stefania Córdoba y Sebastian Espinosa
- **Rama activa:** `fix/auditoria-final`
- **Informe de auditoría de referencia:** `docs/auditoria_codex_g2.md` sobre commit `4774236ef9e54a97b8c0ffb64c7b84d8778857f4`
- **Base de datos de prueba:** PostgreSQL 17 real (`postgres:17-alpine`) en Docker Compose, bases de datos desechables por prueba (`test_g2_1_*`)
- **Alcance estricto de este bloque:** Remediación integral de las cuatro prioridades asignadas:
  1. `A-02`: Escrituras posteriores a TIMEOUT (fase de commit, trigger diferido y cancelación activa).
  2. `M-03`: Deadline integral y fallback honesto degradado sin HTTP 500.
  3. `M-06`: Confianza en proxies y anti-spoofing en rate limiting.
  4. `M-02`: Presupuesto de tokens dinámico y contabilidad de herramientas multimodales anidadas.

---

## 1. Prioridad 1 — `A-02`: Escrituras posteriores a TIMEOUT

### Diagnóstico del contraejemplo de Codex
Codex demostró que en una herramienta con límite de 0.25 s, un `UPDATE` que entraba a `conn.commit()` a 0.1978 s (dentro del plazo) pero que experimentaba una demora en el servidor (como un constraint trigger `AFTER UPDATE DEFERRABLE INITIALLY DEFERRED` ejecutando `pg_sleep(0.18)`):
1. No era cancelado por `statement_timeout`, dado que en PostgreSQL `statement_timeout` no interrumpe la fase de commit una vez iniciada.
2. La llamada de la herramienta retornaba por timeout a 0.2526 s levantando `TimeoutError`.
3. El hilo secundario del worker continuaba ejecutándose en segundo plano (`shutdown(wait=False)`).
4. El commit finalizaba exitosamente a 0.4034 s y la fila cambiaba a `DEFERRED LATE COMMIT` en la base de datos después de haberse declarado el timeout al cliente.

### Remediación técnica implementada
1. **Cancelación activa out-of-band durante el commit:**
   - En `backend/app/db.py`, tanto `_wrapped_commit()` como `checked_commit(conn)` calculan el saldo de tiempo monotónico remanente: `rem_sec = dl_check - time.monotonic()`.
   - Si `rem_sec <= 0`: aborta inmediatamente invocando `conn.rollback()` y levanta `TimeoutError`.
   - Si `rem_sec > 0`: programa un temporizador daemon `timer = threading.Timer(rem_sec, conn.cancel)` inmediatamente antes de delegar en el commit original. Si el commit cruza el plazo, el temporizador envía un paquete oficial de cancelación a PostgreSQL, abortando el commit en el motor y haciendo rollback automático.
   - Atrapa `psycopg.errors.QueryCanceled` y `OperationalError`, garantiza `conn.rollback()` y traduce la excepción a `TimeoutError`.
2. **Registro de conexiones por hilo y sincronización de finalización:**
   - En `backend/app/db.py`, se implementó un registro thread-safe de conexiones abiertas: `register_active_conn`, `unregister_active_conn` y `cancel_active_conns_for_thread(thread_id)`.
   - En `backend/app/agent.py`, `execute_tool_with_timeout`:
     - Registra el identificador del hilo del worker (`worker_tid`).
     - Al expirar el deadline (`FuturesTimeoutError`), invoca `cancel_active_conns_for_thread(worker_tid)` para abortar cualquier query o commit en PostgreSQL.
     - Espera la terminación del hilo con `executor.shutdown(wait=True, cancel_futures=True)`. Dado que la conexión fue cancelada, el worker se desbloquea en milisegundos, captura el error y realiza rollback.

### Evidencia de prueba adversarial
- Archivo: `backend/tests/test_audit_g2_1_remediation.py`
  - `test_g2_1_a02_deferred_constraint_trigger_cancelled_on_timeout`: crea en una base aislada un constraint trigger diferido con `pg_sleep(0.18)` y ejecuta un worker con deadline de 0.25 s y espera previa de 0.15 s. Comprueba que se levanta `TimeoutError` y que una conexión independiente posterior verifica que la fila conserva su valor `ORIGINAL` (`PASSED`).
  - `test_g2_1_a02_active_conn_cancellation_on_slow_worker`: comprueba que ante una herramienta que ejecuta `pg_sleep(1.0)` con timeout de 0.15 s, la conexión es cancelada activamente y la herramienta no se completa (`PASSED`).

---

## 2. Prioridad 2 — `M-03`: Deadline integral y fallback honesto

### Diagnóstico de Codex
1. El parámetro `total_timeout_seconds` del cliente no se acotaba contra `settings.AI_TIMEOUT_SECONDS`, permitiendo solicitar tiempos de hasta 30 s frente al default de 15 s del servidor.
2. Cuando el agente alcanzaba el deadline en un turno con límite ajustado (ej. 0.10 s o 0.11 s), invocaba `_deterministic_sql_fallback_answer` sin historial, el cual intentaba ejecutar consultas SQL con el contexto ya vencido, levantando `TimeoutError` no manejado y devolviendo HTTP 500 en `/api/agent/query`.
3. En `ai_router.py:606-610`, se imponía un piso fijo de 0.5 s por llamada (`effective_timeout = max(0.5, ...)`). Con límite global de 0.15 s, un transporte simulado con retardo de 0.25 s recibía autorización del read timeout y el router aceptaba tardíamente el contrato a 0.3061 s sin comprobar el vencimiento posterior.

### Remediación técnica implementada
1. **Acotamiento server-side irrevocable:**
   - En `backend/app/agent.py`: `eff_total_timeout = min(float(settings.AI_TIMEOUT_SECONDS), max(0.1, float(total_timeout_seconds if total_timeout_seconds is not None else settings.AI_TIMEOUT_SECONDS)))`.
2. **Degradación honesta sin trabajo de BD fuera de plazo:**
   - En `backend/app/agent.py`:
     - En `_deterministic_sql_fallback_answer`: si `get_deadline_context()` indica que el deadline expiró o restan <= 0.05 s, retorna de inmediato la respuesta degradada honesta sin intentar abrir conexiones SQL.
     - Cualquier llamada SQL dentro del fallback está envuelta en bloque `try ... except Exception`.
     - Si `guardrail_triggered == "TIMEOUT"` y no se ejecutaron herramientas previas, devuelve directamente la degradación honesta sin invocar herramientas.
     - Se encapsuló la ejecución en `try ... except TimeoutError` para garantizar que nunca escape una excepción no manejada.
   - En `backend/app/main.py`: `/api/agent/query` atrapa `TimeoutError` y responde con HTTP 200, `"guardrail_triggered": "TIMEOUT"` y respuesta honesta degradada, eliminando los códigos HTTP 500.
3. **Eliminación del floor de 0.5 s y verificación post-llamada en el router:**
   - En `backend/app/ai_router.py`:
     - Se eliminó el `max(0.5, ...)`, pasando a `effective_timeout = min(per_call_timeout, remaining_for_call)`.
     - Si `remaining_for_call <= 0.01 s` o `effective_timeout <= 0.005 s`, interrumpe antes de la llamada.
     - Verificación posterior: tras la llamada HTTP, calcula el tiempo transcurrido total (`post_elapsed`). Si `post_elapsed > total_timeout`, levanta `AIProviderError("TIMEOUT")` y rechaza el resultado recibido fuera de tiempo.

### Evidencia de prueba adversarial
- Archivo: `backend/tests/test_audit_g2_1_remediation.py`
  - `test_g2_1_m03_agent_capping_total_timeout_server_side`: comprueba que solicitar 60 s es acotado por la configuración del servidor (`PASSED`).
  - `test_g2_1_m03_agent_expired_deadline_returns_honest_degradation_without_http500`: comprueba que con límite de 0.11 s y llamada lenta `/api/agent/query` devuelve HTTP 200 con respuesta honesta degradada y `"guardrail_triggered": "TIMEOUT"` (`PASSED`).
  - `test_g2_1_m03_router_respects_remaining_deadline_without_05s_floor`: comprueba que con timeout de 0.15 s y transporte simulado de 0.20 s el router rechaza el contrato recibido fuera de plazo (`PASSED`).

---

## 3. Prioridad 3 — `M-06`: Confianza en proxies y anti-spoofing

### Diagnóstico de Codex
Uvicorn se iniciaba con `--proxy-headers --forwarded-allow-ips=*` en el Dockerfile. `ProxyHeadersMiddleware` de Uvicorn confiaba universalmente en cualquier dirección IP remota y sustituía `scope['client']` con el valor de la cabecera `X-Forwarded-For`. Por consiguiente, un cliente conectando directamente a la API en el puerto 8000 podía falsificar su identidad simplemente enviando `X-Forwarded-For` diferentes, eludiendo el rate limiter (200 / 200 / 200 en lugar de 200 / 200 / 429).

### Remediación técnica implementada
1. **Eliminación de la confianza universal en Uvicorn:**
   - En `backend/Dockerfile`: se eliminó `--proxy-headers --forwarded-allow-ips=*`. El comando de arranque es `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.
2. **Sobrescritura segura en el proxy inverso de borde:**
   - En `frontend/nginx.conf`: Nginx es el único terminador público y fija explícitamente `proxy_set_header X-Forwarded-For $remote_addr;` y `proxy_set_header X-Real-IP $remote_addr;`, impidiendo que cabeceras maliciosas enviadas por clientes externos lleguen al backend.
3. **Validación explícita de peer antes de inspeccionar cabeceras:**
   - En `backend/app/config.py`: se incorporó `TRUSTED_PROXIES = "127.0.0.1,::1,172.16.0.0/12,10.0.0.0/8"`.
   - En `backend/app/security.py`: `get_trusted_client_ip()` inspecciona primero la IP real del peer TCP (`request.client.host`). Si el peer NO es un proxy confiable explícito, retorna la IP del peer directamente e ignora por completo cualquier cabecera `X-Forwarded-For` o `X-Real-IP`.

### Evidencia de prueba adversarial
- Archivo: `backend/tests/test_audit_g2_1_remediation.py`
  - `test_g2_1_m06_untrusted_peer_cannot_spoof_client_ip`: verifica que un cliente no confiable (`198.51.100.2`) enviando `X-Forwarded-For: 203.0.113.195` es resuelto invariablemente como `198.51.100.2` (`PASSED`).
  - `test_g2_1_m06_rate_limiter_not_bypassed_by_varying_xff`: verifica sobre middleware Uvicorn con `trusted_hosts=['127.0.0.1']` que tres solicitudes consecutivas variando `X-Forwarded-For` obtienen `200`, `200` y `429` (`PASSED`).

---

## 4. Prioridad 4 — `M-02`: Presupuesto de tokens dinámico y contabilidad multimodal

### Diagnóstico de Codex
1. El agente utilizaba una reserva estática de 60 tokens, ignorando que el prompt del sistema (`AGENT_SYSTEM_PROMPT`), los esquemas de herramientas y el historial consumían más de 1000 tokens de entrada. Con un presupuesto de 100 tokens, el agente lanzaba el turno y consumía 1020 tokens antes de activar `MAX_TOKENS` a posteriori.
2. La herramienta `tool_clasificar_evidencia` ejecutaba clasificación multimodal consumiendo ~1600 tokens sin registrar dicho gasto en el presupuesto ni en el `total_tokens_used` del agente.

### Remediación técnica implementada
1. **Contabilidad compartida mediante `TokenBudgetTracker`:**
   - En `backend/app/agent.py`, se implementó la clase `TokenBudgetTracker` thread-safe, propagada mediante `contextvars.ContextVar("_ACTIVE_TOKEN_TRACKER")`.
2. **Reserva dinámica fundada en el payload:**
   - Función `estimate_prompt_tokens()`: calcula el total de caracteres del prompt del sistema, especificación JSON de herramientas e historial completo, estimando conservadoramente a razón de 3.0 caracteres por token.
   - Antes de invocar al modelo: comprueba `tracker.remaining() < (est_prompt_tokens + 20)`. Si el presupuesto restante no cubre la entrada más un margen de salida útil (20 tokens), activa inmediatamente `guardrail_triggered = "MAX_TOKENS"` sin realizar llamadas ni gastar tokens.
   - Cota de salida: acota `call_max_tokens = min(700, max(1, rem_tokens - est_prompt_tokens))`.
3. **Contabilidad e interrupción en herramientas de IA anidadas:**
   - En `tool_clasificar_evidencia`: consulta el tracker activo. Si el saldo restante es menor a 150 tokens, aborta antes de ejecutar el clasificador retornando `guardrail_triggered = "MAX_TOKENS"`.
   - Si se ejecuta, recupera los tokens consumidos de la metadata del router y los registra en el tracker compartido con `tracker.record_usage()`.
   - Si el proveedor no reporta tokens, se calculan tokens estimados y se marca `tokens_estimated = True`.
4. **Métricas transparentes en la respuesta:**
   - La respuesta del agente reporta el gasto integral: `total_tokens_used`, `prompt_tokens_used`, `completion_tokens_used` y `tokens_estimated`.

### Evidencia de prueba adversarial
- Archivo: `backend/tests/test_audit_g2_1_remediation.py`
  - `test_g2_1_m02_dynamic_prompt_token_estimation_triggers_max_tokens_before_call`: comprueba que con presupuesto de 100 tokens el agente interrumpe de inmediato activando `MAX_TOKENS` con 0 tokens gastados (`PASSED`).
  - `test_g2_1_m02_nested_multimodal_classification_accounted_in_agent_budget`: comprueba que los 1600 tokens de una llamada multimodal dentro de `tool_clasificar_evidencia` se debitan del presupuesto y se contabilizan en el tracker (`PASSED`).

---

## 5. Matriz de Resultados y Regresiones

Ejecución oficial dentro del contenedor `api` (`Python 3.13.18`, `pytest-8.3.5`):

| Suite | Archivo | Pruebas | Resultado |
|---|---|---|---|
| Seguridad e Integridad G1 | `tests/test_audit_g1_security.py` | 14 | **14 PASSED** (0 fallos) |
| Resiliencia y Control G2 | `tests/test_audit_g2_resilience.py` | 23 | **23 PASSED** (0 fallos) |
| Remediación Adversarial G2.1 | `tests/test_audit_g2_1_remediation.py` | 9 | **9 PASSED** (0 fallos) |
| Salud de la API | `tests/test_health.py` | 1 | **1 PASSED** (0 fallos) |
| CRUD y Negocio Ciudadano | `tests/test_reports_crud.py` | 6 | **6 PASSED** (0 fallos) |
| Flujo Multimodal e IA | `tests/test_ai_and_agent.py` | 12 | **12 PASSED** (0 fallos) |
| **Total integrado** | — | **65** | **65 PASSED (100% de éxito, 0 fallos)** |

Evaluación E2 (`eval/evaluar.py`):
- 6 casos dorados verificados.
- 15 consultas de evaluación ejecutadas.
- P50 = 2767.0 ms, P90 = 6380.4 ms.
- Cero regresiones en trazas de observabilidad, orden de resiliencia N-02 (Gemini -> Groq -> Gemini) ni mitigaciones G1.
