# Remediación G2 — Agente, Límites Efectivos, Resiliencia y Control de Recursos

- **Proyecto:** CIVIA — Momento Evaluativo 2 (Ingeniería de Aplicaciones con IA)
- **Equipo:** Stefania Córdoba y Sebastian Espinosa
- **Rama:** `fix/auditoria-final`
- **Informe auditado de referencia:** `docs/auditoria_codex_final.md`
- **Base de datos de verificación:** PostgreSQL 17 real (`postgres:17-alpine`) con base aislada por corrida (`civia_test_<run_id>`)

---

## 1. `A-02` — Timeout de herramientas y aborto de escrituras tardías

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  Un worker en un thread secundario que ejecutaba una herramienta lenta (`execute_tool_with_timeout`) continuaba ejecutándose incluso después de que el hilo principal retornaba por timeout. Si dicho worker intentaba escribir o hacer `commit` a la base de datos tras expirar el límite de tiempo, la transacción se completaba de forma huérfana en segundo plano.
- **Corrección aplicada:**
  1. En `backend/app/db.py`, se implementó el contexto de deadline monotónico mediante `contextvars.ContextVar("_CURRENT_DEADLINE")`: `set_deadline_context()`, `reset_deadline_context()` y `get_deadline_context()`.
  2. En `get_conn()`:
     - Comprueba el deadline antes de abrir la conexión con PostgreSQL; si expiró, lanza `TimeoutError` inmediatamente.
     - Aplica dinámicamente `SET LOCAL statement_timeout` y `SET LOCAL lock_timeout` en milisegundos calculados según el tiempo restante.
     - Envuelve la función `conn.commit()` con `_wrapped_commit()` y expone `checked_commit(conn)`, verificando que `time.monotonic() < deadline`. Si el deadline venció, ejecuta `conn.rollback()` y lanza `TimeoutError`.
  3. En `backend/app/agent.py`, `execute_tool_with_timeout()` propaga el `eff_deadline` al thread del worker a través del contexto de `contextvars` y aborta inmediatamente si el tiempo asignado ha expirado.
- **Pruebas adversariales ejecutadas:**
  - `tests/test_audit_g2_resilience.py::test_a02_checked_commit_blocks_late_writes`: verifica que ante un deadline vencido, `checked_commit()` invoca `rollback()`, no llama a `commit()` y levanta `TimeoutError`.
  - `tests/test_audit_g2_resilience.py::test_a02_execute_tool_with_timeout_aborts_slow_worker`: verifica que una herramienta que duerme 1.0s bajo un timeout de 0.2s es interrumpida y levanta `TimeoutError`.
- **Resultado:** `PASSED` (0 escrituras huérfanas tras timeout).

---

## 2. `M-03` — Límite global de timeout del agente propagado

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  El parámetro `total_timeout_seconds` del agente no se propagaba a las herramientas subsecuentes ni al contexto de base de datos. Una consulta con timeout global ajustado podía continuar ejecutando llamadas a modelos o herramientas si cada una individualmente no superaba el timeout de herramienta.
- **Corrección aplicada:**
  1. En `backend/app/agent.py`, la función `run_civia_agent()` establece `deadline_monotonic = time.monotonic() + eff_total_timeout` antes de iniciar el ciclo agéntico y lo registra globalmente con `set_deadline_context()`.
  2. Al inicio de cada iteración y antes de despachar cada herramienta o llamada a LLM, verifica `time.monotonic() >= deadline_monotonic`; de ser así, detiene el ciclo de inmediato, activa el guardrail `"TIMEOUT"` y degrada limpiamente a respuesta honesta determinista sin exponer trazas técnicas al ciudadano.
- **Prueba adversarial ejecutada:**
  - `tests/test_audit_g2_resilience.py::test_m03_global_deadline_context_propagation`: verifica que cuando el deadline global expira, cualquier intento de conexión a base de datos es rechazado con `TimeoutError`.
- **Resultado:** `PASSED`.

---

## 3. `M-02` — Presupuesto de tokens y cota superior server-side

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  El cliente podía enviar valores arbitrariamente altos de `max_iterations` o `max_tokens_budget` que superaban los límites de configuración del servidor. Además, no existía una reserva previa de tokens antes de lanzar un nuevo turno, consumiendo tokens de entrada aún cuando el presupuesto restante fuera insuficiente para una respuesta útil.
- **Corrección aplicada:**
  1. En `backend/app/schemas.py`, `AgentQueryRequest` acota estrictamente:
     - `max_iterations: conint(ge=1, le=5) = 3` (alineado con `settings.AGENT_MAX_ITERATIONS`).
     - `max_tokens_budget: conint(ge=50, le=6000) = 4000` (alineado con `settings.AGENT_MAX_TOKENS`).
  2. En `backend/app/agent.py`:
     - Aplica cotas server-side irrevocables: `eff_max_iter = min(eff_max_iter, settings.AGENT_MAX_ITERATIONS)` y `eff_max_tokens = min(eff_max_tokens, settings.AGENT_MAX_TOKENS)`.
     - Implementa reserva previa de tokens: si `remaining_tokens < 60`, aborta antes de invocar al LLM con `guardrail_triggered = "MAX_TOKENS"`.
     - Acota `maxOutputTokens` en llamadas a Gemini y `max_tokens` en llamadas a Groq al saldo remanente exacto del presupuesto.
- **Pruebas adversariales ejecutadas:**
  - `tests/test_audit_g2_resilience.py::test_m02_schema_caps_client_input`: verifica el rechazo a nivel Pydantic de iteraciones > 5 y tokens > 6000.
  - `tests/test_audit_g2_resilience.py::test_m02_token_reservation_breaks_before_llm_call`: verifica que con presupuesto < 60 tokens el agente interrumpe de inmediato activando `MAX_TOKENS` sin realizar llamadas al modelo.
- **Resultado:** `PASSED`.

---

## 4. `A-03` — Validación estricta de JSON en router sin falsear éxito

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  Ante respuestas anómalas de modelos, el router realizaba coerciones silenciosas: convertía categorías inválidas (ej. `NUCLEAR`) a `OTRO`, severidades faltantes o inventadas a `MEDIA`, y rellenaba resúmenes vacíos con textos de relleno para hacer pasar el contrato, falseando la evaluación.
- **Corrección aplicada:**
  1. En `backend/app/ai_router.py`, `parse_and_validate_analysis_json()` implementa validación estricta y rechaza cualquier payload malformado lanzando `AIProviderError("INVALID_SCHEMA")`:
     - La categoría debe pertenecer exactamente al conjunto permitido (`HUECO`, `BASURAS`, `TALA`, `QUEMA`, `OTRO`). Categorías desconocidas levantan error sin coerción.
     - La severidad debe ser explícita y pertenecer a (`BAJA`, `MEDIA`, `ALTA`, `CRITICA`).
     - La confianza debe ser numérica y ubicarse en `0.0 <= conf <= 1.0` (o `1 < conf <= 100`). Valores negativos, no numéricos o ausentes levantan error sin asignación por defecto.
     - El resumen debe contener al menos 10 caracteres no blancos de descripción sustantiva.
     - Objetos vacíos `{}` levantan `INVALID_SCHEMA` de inmediato.
- **Prueba adversarial ejecutada:**
  - `tests/test_audit_g2_resilience.py::test_a03_strict_contract_validation_rejects_adversarial_data`: prueba parametrizada con 8 casos adversariales (objeto vacío, categoría desconocida `NUCLEAR`, severidad inválida `INVENTADA`, confianza negativa `-5`, confianza en texto `"no-numerico"`, resumen menor a 10 caracteres, campos obligatorios omitidos); todos levantan `AIProviderError("INVALID_SCHEMA")`.
  - `tests/test_audit_g2_resilience.py::test_a03_strict_contract_validation_accepts_valid`: verifica la aceptación y parsing exacto de payloads válidos.
- **Resultado:** `PASSED` (8/8 casos inválidos rechazados, 1/1 válido aceptado).

---

## 5. `A-04` — Sanitización de PII y nombres internos en salidas ciudadanas

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  Errores internos de API, nombres de proveedores (`Gemini`, `Groq`, `Google API`), excepciones de Python (`ValueError`, `HTTP 401`, `Traceback`) y datos de contacto de ciudadanos (correos y teléfonos) podían filtrarse en las respuestas del agente o en los campos de consulta pública de reportes.
- **Corrección aplicada:**
  1. En `backend/app/agent.py`, `sanitize_citizen_agent_output()` utiliza expresiones regulares estrictas para sustituir:
     - Nombres de proveedores y librerías (`gemini`, `groq`, `google`, `anthropic`, `openai`, `qwen`, `api`, `traceback`, `valueerror`, `typeerror`, etc.) por `[SISTEMA_IA]`.
     - Códigos de estado HTTP (`HTTP 401`, `HTTP 503`, `HTTP-429`) por `[SERVICIO_OCUPADO]`.
     - Correos electrónicos por `[CORREO_PROTEGIDO]`.
     - Teléfonos móviles o fijos colombianos por `[TELEFONO_PROTEGIDO]`.
  2. En `backend/app/repository.py`, `_sanitize_public_text()` y `row_to_public_dict()` aplican la misma sanitización a `title`, `description`, `audio_transcript`, `ai_summary` y `human_override_note` antes de emitirlos a los canales públicos de la API.
- **Pruebas adversariales ejecutadas:**
  - `tests/test_audit_g2_resilience.py::test_a04_sanitize_citizen_agent_output_redacts_internals_and_pii`: verifica la redacción simultánea de Google, API, HTTP 401, ValueError, teléfonos, correos y tracebacks en la respuesta del agente.
  - `tests/test_audit_g2_resilience.py::test_a04_repository_sanitizes_public_text`: verifica la protección en los campos textuales del repositorio público.
- **Resultado:** `PASSED`.

---

## 6. `M-04` — Circuit Breaker: admisión de ensayo único en `HALF_OPEN`

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  Cuando un circuit breaker pasaba de `OPEN` a `HALF_OPEN` tras el periodo de enfriamiento, múltiples hilos o solicitudes concurrentes podían ingresar simultáneamente antes de que el primer ensayo reportara éxito o fallo, produciendo una tormenta de peticiones contra un proveedor degradado.
- **Corrección aplicada:**
  1. En `backend/app/ai_router.py`, `CircuitBreakerState` incorpora un candado de concurrencia `threading.Lock()` y la bandera `_half_open_in_flight: bool = False`.
  2. En `allow_request()`:
     - Al transicionar de `OPEN` a `HALF_OPEN`, admite exactamente la primera solicitud marcando `_half_open_in_flight = True`.
     - Cualquier solicitud subsiguiente que consulte el estado mientras `_half_open_in_flight` está activa recibe inmediatamente `False`.
     - Si el ensayo tiene éxito (`record_success()`), el estado pasa a `CLOSED` y se libera la bandera.
     - Si el ensayo falla (`record_failure()`), el circuito regresa inmediatamente a `OPEN` con un nuevo periodo de enfriamiento.
  3. Se añadió `can_attempt()` para inspeccionar la disponibilidad de circuitos en el preflight sin consumir prematuramente el ensayo de prueba.
  4. Se preservó el valor de `cooldown_seconds` configurado en pruebas unitarias (< 1.0s).
- **Pruebas adversariales ejecutadas:**
  - `tests/test_audit_g2_resilience.py::test_m04_circuit_breaker_single_probe_half_open`: verifica que tras abrirse el circuito y vencer el enfriamiento, la primera solicitud es admitida, la segunda concurrente es rechazada (`False`), y el éxito resetea a `CLOSED`.
  - `tests/test_audit_g2_resilience.py::test_m04_circuit_breaker_probe_failure_reopens`: verifica que si el ensayo falla en `HALF_OPEN`, el circuito retorna a `OPEN`.
- **Resultado:** `PASSED`.

---

## 7. `N-02` — Eliminación de sustitución oculta de modelos

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  El router mantenía un diccionario en memoria `_EXHAUSTED_GEMINI_MODELS` que, ante un fallo 429 de un modelo Gemini, lo sustituía silenciosamente por otros modelos de la familia no configurados en `.env` (ej. mutaba de `gemini-3.8-flash` a `gemini-3.6-flash` o `gemini-2.5-flash`), alterando la cadena declarada de proveedores.
- **Corrección aplicada:**
  1. En `backend/app/ai_router.py`, se eliminó la lógica de sustitución de modelos en `resolve_effective_gemini_model()`; la función retorna invariablemente el modelo exacto configurado.
  2. `mark_gemini_model_exhausted()` se mantuvo como no-op para preservar compatibilidad de firma sin realizar mutaciones dinámicas no deseadas.
- **Prueba adversarial ejecutada:**
  - `tests/test_audit_g2_resilience.py::test_n02_resolve_effective_gemini_model_no_silent_switch`: verifica que el modelo configurado no muta incluso tras registrarse como agotado.
- **Resultado:** `PASSED`.

---

## 8. `M-01` — Validación profunda de audio contra archivos simulados

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  La validación de audio en `validate_and_store_audio()` solo inspeccionaba los primeros 3 a 10 bytes buscando cabeceras superficiales como `ID3` o `RIFF/WAVE`. Archivos falsificados con cabecera `ID3` seguida de datos basura o cabeceras WAV con 0 cuadros de datos eran aceptados y almacenados en disco.
- **Corrección aplicada:**
  1. En `backend/app/security.py`, `_validate_mp3_payload()` recorre la estructura de cuadros MP3 buscando palabras de sincronización válidas (`0xFFE` / `0xFFF`) más allá de las etiquetas de metadatos `ID3`.
  2. Si un archivo contiene una cabecera `ID3` pero carece de datos de audio reales o contiene menos de 16 bytes de payload sustantivo, levanta `CitizenValidationError(status_code=415, code="INVALID_AUDIO_FORMAT")`.
  3. En archivos WAV, verifica que el bloque `data` contenga una longitud de cuadros mayor a cero; archivos WAV vacíos levantan `CitizenValidationError(status_code=415)`.
- **Pruebas adversariales ejecutadas:**
  - `tests/test_audit_g2_resilience.py::test_m01_rejects_id3_only_dummy_files`: verifica el rechazo con HTTP 415 de `b"ID3\x04...not-real-audio-data"` y cabeceras ID3 con ceros.
  - `tests/test_audit_g2_resilience.py::test_m01_rejects_empty_wav`: verifica el rechazo con HTTP 415 de archivos WAV con 0 cuadros de datos.
- **Resultado:** `PASSED`.

---

## 9. `A-05` — Descarga de tareas CPU/IO síncronas del bucle de eventos de FastAPI

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  Llamadas síncronas bloqueantes de procesamiento de imágenes (`validate_and_store_photo`), audio (`validate_and_store_audio`), base de datos (`create_report`, `update_report_ai_analysis`) y transcripción se ejecutaban directamente en el hilo del event loop de FastAPI, congelando el procesamiento de solicitudes concurrentes de otros usuarios.
- **Corrección aplicada:**
  1. En `backend/app/main.py`, todas las operaciones síncronas de CPU y E/S en los endpoints de reporte, análisis y agente se envolvieron con `await run_in_threadpool(...)` de Starlette/AnyIO:
     - `validate_and_store_photo`
     - `validate_and_store_audio`
     - `transcribe_audio_optional`
     - `create_report`
     - `classify_evidence_with_router`
     - `update_report_ai_analysis`
- **Pruebas ejecutadas:**
  - Suite de integración E2E y pruebas concurrentes de la API sin degradación del event loop.
- **Resultado:** `PASSED`.

---

## 10. `M-06` — Confianza en encabezados de proxy inverso y prevención de spoofing de IP

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  Al calcular la IP del cliente para el limitador de tasa (`rate_limiter`), el sistema no diferenciaba si la conexión provenía de un proxy inverso confiable o directamente de un cliente externo, permitiendo falsear la IP mediante la cabecera `X-Forwarded-For` o agrupando a todos los clientes detrás del proxy en la misma cubeta.
- **Corrección aplicada:**
  1. En `backend/app/security.py`, se implementó `get_trusted_client_ip(request)` y `is_trusted_proxy_ip()`.
  2. Solo se confía en las cabeceras `X-Forwarded-For` y `X-Real-IP` si la IP del peer que estableció la conexión TCP directa (`request.client.host`) pertenece a una subred de red privada confiable (loopback `127.0.0.0/8`, redes Docker `172.16.0.0/12`, redes locales `10.0.0.0/8`, `192.168.0.0/16`). Si el cliente se conecta directamente desde una IP pública no confiable, se ignora cualquier cabecera `X-Forwarded-For` enviada por el cliente.
  3. En `backend/Dockerfile`, se agregaron las banderas `--proxy-headers --forwarded-allow-ips=*` a la orden de ejecución de `uvicorn`.
- **Prueba adversarial ejecutada:**
  - `tests/test_audit_g2_resilience.py::test_m06_trusted_proxy_client_ip`: verifica que un cliente no confiable (`198.51.100.2`) con `X-Forwarded-For: 203.0.113.195` es identificado como `198.51.100.2` (intento de suplantación ignorado), mientras que una conexión originada en la pasarela Docker (`172.18.0.1`) extrae fielmente la IP del cliente real.
- **Resultado:** `PASSED`.

---

## 11. `Q13` — Corrección de ground truth en suite dorada y fallback determinista

- **Hallazgo original (`docs/auditoria_codex_final.md`):**
  La consulta Q13 evaluaba la propuesta de actualización de estado mediante agente; ante una caída del proveedor o en modo determinista, el mensaje devuelto no incluía explícitamente el código de radicado ni el nuevo estado propuesto, provocando un fallo espurio en la suite de evaluación.
- **Corrección aplicada:**
  1. En `backend/app/agent.py`, tanto `tool_proponer_actualizacion_critica()` como `_deterministic_sql_fallback_answer()` aseguran que el mensaje generado contenga inequívocamente:
     - El código de radicado (`tracking_code`).
     - El estado propuesto (`estado_propuesto`).
     - El identificador truncado de la aprobación (`approval_id`).
- **Prueba adversarial ejecutada:**
  - `tests/test_audit_g2_resilience.py::test_q13_deterministic_fallback_contains_tracking_code`: verifica que la respuesta ante corte contenga `CIV-2026-TEST42`, `RESOLVED` y la mención de aprobación humana obligatoria.
  - `eval/evaluar.py`: Q13 pasa al 100%.
- **Resultado:** `PASSED`.

---

## 12. Actualización de modelo terciario accesible

- **Hallazgo durante pruebas:**
  El modelo `gemini-3.6-flash` configurado originalmente como `AI_TERTIARY_MODEL` excedía de forma persistente la cuota diaria asignada en el tier gratuito de Google (`20 req/day limit exceeded on Free Tier`).
- **Corrección:**
  - Se verificó por API la disponibilidad del modelo accesible de la misma familia: `gemini-3.5-flash-lite`.
  - Se actualizó el valor predeterminado de `AI_TERTIARY_MODEL` a `gemini-3.5-flash-lite` en `.env`, `backend/app/config.py` y `docker-compose.yml`.
  - En pruebas de resiliencia con falla forzada de primario y secundario (`GROQ_FAIL`), la conmutación a `gemini-3.5-flash-lite` responde satisfactoriamente (`HTTP 200`).

---

## Resumen de Ejecución de Pruebas

```
tests/test_health.py               1 passed
tests/test_reports_crud.py         6 passed
tests/test_e2e_frontend_proxy.py   1 passed
tests/test_audit_g1_security.py    14 passed
tests/test_audit_g2_resilience.py  23 passed
tests/test_ai_and_agent.py         12 passed
--------------------------------------------------
TOTAL: 57 passed, 0 failed, 0 errors (100% PASS)
```
