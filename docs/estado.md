# Estado de Ejecución — CIVIA (Momento Evaluativo 2)

**Equipo:** Stefania Córdoba y Sebastian Espinosa · Universidad Cooperativa de Colombia.

---

## Fase A — Preflight completado (2026-11-01)
- **Git & Docker Compose**: `docker compose config --quiet` (exit code `0`), `docker compose up --build -d` exitoso (`civia-db-1` healthy en `postgres:17-alpine`, `civia-api-1` up y respondiendo en `http://localhost:8000/health`).
- **Tests de scaffold**: añadido `backend/tests/test_health.py` ejecutado dentro del contenedor con `pytest -v`.
- **Preflight de modelos de IA con claves `.env` (sin exponer secretos)**:
  - Catálogo Google AI Studio (`/v1beta/models`): presentes `gemini-3.8-flash` y `gemini-3.6-flash` en `GOOGLE_API_KEY_PRIMARY` y `GOOGLE_API_KEY_SECONDARY`, además de `gemini-3-flash-preview` y `gemini-3.1-flash-lite`.
  - Catálogo Groq (`/openai/v1/models`): presentes `qwen/qwen3.8-27b`, `whisper-large-v3` y `whisper-large-v3-turbo`.
  - Prueba mínima de capacidades (visión PNG 32x32, salida estructurada JSON y *tool calling*):
    - `gemini-3.8-flash`: existe en catálogo oficial pero durante el preflight presentó `HTTP 503 (high demand)` / cuota diaria de 20 RPD en capa gratuita, lo cual justifica y valida empíricamente la necesidad de timeout acotado, circuit breaker y fallback automático hacia Groq (`qwen/qwen3.8-27b`) y segundo modelo Gemini (`gemini-3.6-flash`).
    - `qwen/qwen3.8-27b` (Groq): Visión + JSON (`response_format: json_object`) OK (requiere imágenes de al menos 32x32 px) y *tool calling* OK (`True`).
    - `gemini-3.6-flash` (Google): Visión + JSON (`responseMimeType: application/json`) OK (~1.67s) y *tool calling* OK (`True`).

---

## Fase B — Migraciones, esquema, API CRUD, seguridad y fixtures completada (2026-11-01)
- **Migraciones SQL automáticas (`backend/migrations/001_initial_schema.sql` + `backend/app/db.py`)**:
  - Tablas creadas de forma idempotente al iniciar FastAPI: `schema_migrations`, `reports` (con `CHECK` constraints de coordenadas, tamaños y estados), `ai_traces` (observabilidad protegida) y `pending_approvals` (aprobación humana para escrituras críticas del agente).
  - Índices B-Tree sobre `(latitude, longitude)`, `status`, `final_category`, `ai_category`, `comuna` y `created_at`.
- **Seguridad y privacidad (`backend/app/security.py`)**:
  - Validación de imágenes por *magic bytes* reales (`JPEG`, `PNG`, `WEBP`), tamaño máximo 5 MB, dimensiones entre `32x32` px y `8192x8192` px, y re-codificación limpia con `Pillow` eliminando metadatos EXIF y usando nombres `UUID`.
  - Validación de audio opcional (`WAV`, `MP3`, `OGG`, `WEBM`) hasta 5 MB y <= 60 segundos con comprobación de cabecera/trama real.
  - Validación de coordenadas GPS (`-90..90`, `-180..180`, rechazo de `(0,0)` Null Island, detección de cobertura en Valle del Cauca `in_service_area`).
  - Sanitización de HTML/caracteres de control y minimización de datos personales (redacción automática de correos `[CORREO_PROTEGIDO]` y teléfonos celulares `[TELEFONO_PROTEGIDO]`).
  - Rate limiting por IP en creación de reportes, reanálisis y consultas agénticas (`429 RATE_LIMIT_EXCEEDED` amigable y sin tracebacks).
- **API CRUD y fixtures sintéticos (`backend/app/main.py`, `backend/app/repository.py`, `backend/app/seed.py`)**:
  - Semilla automática de 10 reportes sintéticos identificados en Cali (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`, `is_synthetic=True`).

---

## Fase C — Frontend React + TypeScript + Vite PWA completada (2026-11-01)
- **Interfaz ciudadana PWA (`frontend/`)**:
  - Implementada en React 19 + TypeScript + Vite (`tsc -b && vite build` sin errores) y servida con `nginx:1.27-alpine` en `http://localhost:5173`.
  - Incluye `manifest.webmanifest`, Service Worker (`sw.js`) e icono vectorial.
  - Funcionalidades conectadas al backend real: tablero de estadísticas en vivo, mapa interactivo de Cali con Leaflet (`CaliMap.tsx`), formulario con captura de GPS o clic en mapa, carga de fotografía o generador sintético en `<canvas>`, grabación/carga opcional de nota de voz (`<= 60s`, `<= 5 MB`), confirmación/corrección humana (`PATCH /api/reports/{id}/confirm`), seguimiento por código de radicado (`CIV-2026-...`), asistente agéntico y consola administrativa protegida (`X-Admin-Token` sin token prellenado en el cliente).
  - Verificación E2E entre contenedores (`test_e2e_frontend_proxy.py`): `api` -> `http://frontend:80` comprobando HTML, manifiesto PWA, Service Worker y proxy inverso Nginx.

---

## Fase D — Sistema agéntico resiliente, herramientas y 4 límites completada (2026-11-01)
- **Router IA desacoplado (`backend/app/ai_router.py`)**:
  - Cadena configurada por entorno: `gemini-3.8-flash` (Google) → `qwen/qwen3.8-27b` (Groq) → `gemini-3.6-flash` (Google), más transcripción opcional de audio con `whisper-large-v3-turbo` (Groq).
  - *Circuit breaker* por proveedor/modelo, *backoff* exponencial con *jitter*, reparación acotada de JSON y validación estricta `AIAnalysisContract` (rechazando objetos vacíos `{}` con `INVALID_SCHEMA`).
  - Degradación elegante ante caída total (`FALLA_FORZADA=TOTAL`): el reporte se conserva en `PENDING_ANALYSIS` con cero errores técnicos hacia el ciudadano.
- **Agente con herramientas tipadas y 4 límites (`backend/app/agent.py`)**:
  - Herramientas: `consultar_reportes`, `obtener_reporte`, `clasificar_evidencia` y `proponer_actualizacion_critica`.
  - Límites verificados con pruebas: `MAX_ITERATIONS`, `MAX_TOKENS`, `TIMEOUT` por herramienta (retorno inmediato con `shutdown(wait=False, cancel_futures=True)`) y `HUMAN_APPROVAL_REQUIRED` en tabla `pending_approvals` (con transición atómica de un solo uso `SELECT ... FOR UPDATE`).

---

## Fase E — Evaluación formal completada (2026-11-01)
- **E1 (`eval/casos_dorados.json`)**: 6 preguntas doradas (`GD-01` a `GD-06`, incluyendo `GD-06` sin respuesta posible en BD sobre radiación/NDVI en Comuna 99) verificadas automáticamente contra consultas SQL sobre PostgreSQL (`all_sql_verified = True`).
- **E2 & E3 (`eval/evaluar.py`, `eval/resultados/reporte_evaluacion.json`, `eval/resultados/reporte_evaluacion.md`, `docs/decisiones.md`)**:
  - 15 consultas representativas (`Q01..Q15`) cubriendo las 7 categorías exigidas.
  - Métricas reales observadas: **`14/15` aciertos (`93.33%`)**, precisión multimodal **`5/5` (`100.0%`)**, latencia **`P50 = 3549.0 ms`**, **`P90 = 4815.2 ms`**, **`30,400` tokens** totales, costo facturado real **`$0.000000 USD`** (tier gratuito) / costo equivalente estimado **`$0.000375 USD` por consulta** (`$0.005623 USD` total), frecuencia de fallback **`40.0%` (`6/15`)**.
  - Mejoras de ingeniería documentadas a partir de errores detectados en la evaluación (normalización de signo de longitud occidental `-76.541` en `Q05`, filtro `ILIKE` en barrio y ajuste de enfriamiento de *circuit breakers*).
- **E4 (Pruebas de resiliencia)**: Comprobados con pruebas automatizadas los fallos `429`, `503`, `TIMEOUT`, `INVALID_JSON`, `GROQ_FAIL`, `TOTAL` y los 4 límites del agente (`20 passed` en `pytest -v`).
- **E5 (`eval/plantilla_usabilidad.md`)**: Plantilla de evaluación de usabilidad con 3 tareas sin instrucciones verbales lista y marcada honestamente como pendiente de ejecución presencial con usuario externo.

---

## Fase F — Auditoría de seguridad y entrega reproducible completada (2026-11-01)
- **F1 (Auditoría de seguridad)**: Remediados los hallazgos de auditoría (`docs/auditoria_codex.md`): comparación `hmac.compare_digest` en `verify_admin_token`, eliminación de token prellenado en el frontend, cabeceras `Content-Security-Policy` y `X-Content-Type-Options: nosniff` en fotos, validación de tamaño/trama en audio y limpieza compensatoria de fotos huérfanas, rechazo de `{}` en `parse_and_validate_analysis_json`, retorno inmediato en `execute_tool_with_timeout`, aprobación de un solo uso con `FOR UPDATE` y sanitización de respuestas ciudadanas del agente (`sanitize_citizen_agent_output`). Cero secretos en Git.
- **F2 (Prueba desde clon limpio)**: Ejecutada en directorio independiente (`%TEMP%\civia_prof_clone`) con proyecto y volúmenes aislados (`civia_clean_prof`): clonación, copia de `.env`, `docker compose -p civia_clean_prof up --build -d`, verificación de `/health` (`connected: true, schema_ready: true`), frontend HTTP `200`, y `pytest -v` (`20 passed in 20.75s`). **Tiempo total medido de principio a fin: `84.6 segundos` (`1 min 24.6 s`, < 5 minutos)**.
- **F3, F4, F5, F6**: Actualizados `README.md`, `docs/checklist_rubrica.md`, `docs/guion_sustentacion.md`, `docs/decisiones.md` y `docs/estado.md`. Todos los contenedores (`civia-db-1`, `civia-api-1`, `civia-frontend-1`) activos y saludables.

---

## Fase G — Remediación de Auditoría Independiente (en curso en rama `fix/auditoria-final`)

### Bloque G1 — Seguridad e integridad de datos completado (2026-11-01)
- **C-01 (`ADMIN_TOKEN` robusto obligatorio)**:
  - Eliminado el valor por defecto `civia-admin-demo-2026` de `backend/app/config.py`, `docker-compose.yml`, `.env.example` y `README.md`.
  - Implementadas `is_strong_admin_token()` y `validate_admin_token_or_raise()` exigiendo `>= 24` caracteres, `>= 8` caracteres distintos y rechazo de valores débiles/demo.
  - `lifespan` en `backend/app/main.py` falla inmediatamente al iniciar si `ADMIN_TOKEN` falta o es débil, y `verify_admin_token` rechaza con `401` cualquier token débil o vacío.
  - `scripts/run.ps1` y `run.sh` generan automáticamente un `ADMIN_TOKEN` criptográfico único por instalación si `.env` no tiene uno válido.
- **A-01 (Autenticación y autorización en `PATCH /status` y `PATCH /confirm`)**:
  - `PATCH /api/reports/{report_id}/status` exige `Depends(verify_admin_token)` (`401` sin `X-Admin-Token` válido; `human_approved=true` nunca actúa como credencial).
  - `POST /api/reports` emite una credencial de capacidad por reporte (`citizen_edit_token`, almacenada como hash SHA-256 `edit_token_hash` en PostgreSQL) que jamás se expone en lecturas públicas (`GET /api/reports*`).
  - `PATCH /api/reports/{report_id}/confirm` exige `X-Citizen-Edit-Token` (o `X-Admin-Token` válido) con `SELECT ... FOR UPDATE`, devuelve `403 CONFIRMATION_UNAUTHORIZED` ante solicitudes anónimas, y devuelve `409 REPORT_ALREADY_MANAGED` si el reporte ya fue confirmado o gestionado administrativamente (`CONFIRMED`, `IN_REVIEW`, `RESOLVED`, `REJECTED`).
- **M-07 y N-03 (Aislamiento automático de BD/volúmenes de pruebas y evaluación; cero borrados globales)**:
  - `backend/app/db.py` implementa `ensure_isolated_database()`, `is_disposable_test_or_eval_db()` y `assert_disposable_test_db()` que rechaza operaciones destructivas sobre la base normal `civia`.
  - `backend/tests/conftest.py` y `eval/evaluar.py` aíslan automáticamente la ejecución en `civia_test` / `civia_eval` y directorios temporales de subida (`/tmp/civia_test_uploads`, `/tmp/civia_eval_uploads`).
  - Eliminados todos los `DELETE FROM reports WHERE is_synthetic = FALSE`, `DELETE FROM pending_approvals` y `UPDATE` incondicionales de `CIV-2026-DEMO0001`; las pruebas limpian exclusivamente los IDs creados en su alcance y preservan registros centinela preexistentes.
- **A-06 (Idempotencia durable con `UNIQUE`, concurrencia y aislamiento de fallos post-commit)**:
  - Migración `backend/migrations/002_security_and_idempotency.sql` añade `edit_token_hash`, `idempotency_key` (`UNIQUE`), `version` y tabla `idempotency_records`.
  - `create_report()` sincroniza reintentos concurrentes mediante `pg_advisory_xact_lock(hashtext(idempotency_key))` + `SAVEPOINT` y recupera el mismo `id`, `tracking_code` y `citizen_edit_token` ante reintentos con `Idempotency-Key` o huella determinista de operación (`op:<sha256>`), devolviendo `409 IDEMPOTENCY_KEY_CONFLICT` si se reutiliza una `Idempotency-Key` con payload distinto.
  - Los fallos de `record_ai_trace` (`_safe_record_trace`) o del análisis post-commit están aislados y jamás invalidan ni duplican un reporte ya confirmado en PostgreSQL.
- **A-07 (Bloqueo de aprobaciones obsoletas en la misma transacción)**:
  - `tool_proponer_actualizacion_critica` registra `previous_status` y `expected_version`.
  - `decide_pending_approval` bloquea `pending_approvals` y `reports` con `SELECT ... FOR UPDATE` en la misma transacción; si el estado o versión del reporte cambió previamente, rechaza automáticamente la propuesta obsoleta (`status = 'REJECTED'`, `stale_conflict = True`, HTTP `409 STALE_APPROVAL`) sin sobrescribir `reports`.
- **B-03 (Cero archivos huérfanos en fallos de BD y prevención de colisiones de radicado)**:
  - `create_citizen_report` rastrea todos los archivos escritos (`photo_*`, `audio_*`) y los elimina en bloque `except Exception:` si falla cualquier paso previo o `create_report` en BD, así como en reintentos idempotentes.
  - `generate_tracking_code()` calcula SHA-256 sobre los 128 bits del UUID (`report_uuid.bytes`), usa año UTC dinámico (`datetime.now(timezone.utc).year`) y reintenta ante `UniqueViolation`.
- **Verificación de pruebas en PostgreSQL 17 real (`civia_test`)**:
  - `docker compose exec -T api pytest -v`: **`26 passed in 38.97s`** (incluyendo las 6 pruebas negativas y de regresión de `backend/tests/test_audit_g1_security.py`).

### Bloque G1.1 — Cierre definitivo de los 7 hallazgos residuales de `docs/auditoria_codex_g1.md` completado (2026-11-01)
- **Detalle completo por hallazgo, corrección, prueba adversarial, resultado y limitaciones**: documentado en [`docs/remediacion_g1_1.md`](remediacion_g1_1.md).
- **Resumen de los 7 cierres residuales**:
  1. **`C-01`**: `is_strong_admin_token()` rechaza secuencias numéricas/alfabéticas/teclado (`_has_sequential_run`) y patrones periódicos o bloques repetidos (`_has_repeated_pattern`, como `"0123456789" * 3`), exige al menos 2 clases de caracteres y `>= 10` caracteres únicos. `generate_admin_token(32)` y los scripts de arranque usan CSPRNG (`secrets.token_urlsafe(32)`).
  2. **`A-01`**: Eliminados `derive_citizen_edit_token()` y el respaldo idempotente implícito por contenido público (`op:<fingerprint>`). Cada reporte genera un `citizen_edit_token` aleatorio con `secrets.token_urlsafe(32)`, independiente de `DATABASE_URL` y de datos públicos. En reintentos idempotentes, el token solo puede desellarse mediante PBKDF2-HMAC-SHA256 con la `Idempotency-Key` secreta del cliente original. Un segundo cliente que descarga campos y foto públicos no recupera el reporte original ni su capacidad de edición (`403 CONFIRMATION_UNAUTHORIZED`).
  3. **`M-07`**: Eliminados `snapshot_db_state()` y `restore_db_snapshot()` (`DELETE ... WHERE NOT (id = ANY(...))` y restauración de `DEMO0001`). `conftest.py` aísla en modo *fail-closed* cualquier `DATABASE_URL` no desechable (incluyendo nombres distintos de `"civia"`, como `civia_prod_probe`) hacia `civia_test_<uuid8>` y limpia únicamente los UUIDs creados por la prueba (`cleanup_tracked_test_records()`). `test_four_agent_guardrails_enforced` opera sobre su propio reporte desechable sin tocar `CIV-2026-DEMO0001`.
  4. **`N-03`**: `eval/evaluar.py` elimina `pre_existing_pa_ids` y el borrado por complemento (`WHERE NOT (id = ANY(...))`), rastrea únicamente los `approval_id` generados por sus propias llamadas al agente (`created_eval_pa_ids`), aísla en modo *fail-closed* bases no desechables y restaura `settings.UPLOAD_DIR` al terminar.
  5. **`A-06`**: `req_fingerprint` se construye sobre el JSON canónico ordenado de todos los parámetros (`title`, `description`, `latitude`, `longitude`, `comuna`, `neighborhood`, `address_hint`, `auto_analyze`, `photo_sha256`, `audio_sha256`), devolviendo `409 IDEMPOTENCY_KEY_CONFLICT` ante cualquier mutación en campos opcionales o adjuntos.
  6. **`A-07`**: `decide_pending_approval()` exige tanto `previous_status` como `expected_version` entero válido (`>= 1`) para aprobar, rechazando con `stale_conflict=True` (`409 STALE_APPROVAL`) propuestas heredadas sin versión tras ciclos ABA (`CONFIRMED -> RESOLVED -> CONFIRMED`). La migración `003_invalidate_legacy_approvals.sql` invalida propuestas `PENDING` heredadas sin `expected_version`.
  7. **`B-03`**: `_atomic_write_bytes()` en `backend/app/security.py` escribe en `.tmp_<uuid>_<name>`, verifica longitud exacta, promueve con `os.replace` y en `except BaseException:` elimina tanto el archivo temporal como el destino final antes de propagar el error (`0` archivos huérfanos ante escrituras parciales interrumpidas con `OSError`).
- **Verificación de la suite completa + pruebas adversariales G1.1 en PostgreSQL 17 real**:
  - `docker compose exec -T api pytest -v`: **`33 passed in 30.05s`** (`13/13` en `tests/test_audit_g1_security.py`).

### Bloque G1.2 — Cierre del último hallazgo `C-01` (`docs/auditoria_codex_g1_1.md`) completado (2026-11-01)
- **Alcance exclusivo**: Se mantuvieron intactas las 6 correcciones ya aprobadas (`A-01`, `M-07`, `N-03`, `A-06`, `A-07`, `B-03`) y se cerró el contraejemplo contextual de `C-01` (`_'.join(('Civia', 'AdminToken', '2026', 'Demo')) + '!'`).
- **Corrección aplicada (`backend/app/config.py`, `scripts/run.ps1`, `run.sh`, `.env.example`, `README.md`)**:
  - Se estableció `secrets.token_urlsafe(32)` (`>= 32` caracteres URL-safe base64, `>= 12` símbolos distintos) como procedimiento estándar de generación local por instalación, sin credenciales predeterminadas ni modo demo en desarrollo o producción.
  - Se bloqueó explícitamente el patrón contextual `Civia_AdminToken_2026_Demo!` y sus variantes con nombre del proyecto, rol administrativo, años (`2024..2027`) y etiquetas `Demo`/`Test` (tanto en formato estándar como con `ADMIN_TOKEN_ALLOW_CUSTOM_FORMAT=true`).
  - Se documentó en código, `.env.example`, `README.md` y adenda de `docs/remediacion_g1_1.md` que los filtros estáticos bloquean patrones previsibles pero no prueban matemáticamente la entropía criptográfica de una cadena arbitraria.
- **Verificación**:
  - Prueba adversarial añadida: `tests/test_audit_g1_security.py::test_g1_2_c01_rejects_contextual_project_role_year_demo_token`.
  - Suite completa ejecutada sobre PostgreSQL 17 real: **`34 passed`** (`14/14` en `tests/test_audit_g1_security.py`).

### Bloque G2 — Agente, límites efectivos y proveedores IA completado (2026-11-02)
- **Detalle completo por hallazgo, corrección, pruebas adversariales, resultados y límites**: documentado en [`docs/remediacion_g2.md`](remediacion_g2.md).
- **Resumen de los hallazgos cerrados**:
  1. **`A-02`**: Implementación de deadline monotónico con `contextvars` y aborto estricto con rollback en `checked_commit(conn)` ante timeouts de herramientas (`execute_tool_with_timeout`), previniendo escrituras huérfanas en BD.
  2. **`M-03`**: Propagación del deadline global del agente (`deadline_monotonic = time.monotonic() + eff_total_timeout`), abortando turnos e iteraciones subsiguientes si el tiempo asignado expiró.
  3. **`M-02`**: Acotación en esquema Pydantic (`max_iterations <= 5`, `max_tokens_budget <= 6000`), límites forzados en servidor, reserva previa de tokens (< 60 tokens interrumpe antes de llamar al LLM) y cota a tokens de salida según saldo remanente.
  4. **`A-03`**: Validación estricta en `parse_and_validate_analysis_json()`; rechazo con `AIProviderError("INVALID_SCHEMA")` de categorías desconocidas, severidades ausentes, confianzas negativas o fuera de rango, resúmenes sin contenido sustantivo y objetos vacíos `{}` sin coerciones silenciosas.
  5. **`A-04`**: Sanitización de PII (correos y teléfonos colombianos) y nombres técnicos internos (`Google`, `API`, `Groq`, `HTTP 401`, `ValueError`, `Traceback`) tanto en salidas ciudadanas del agente como en campos textuales del repositorio público.
  6. **`M-04`**: Circuit Breaker con candado de concurrencia `threading.Lock()` y admisión de ensayo único estricto en `HALF_OPEN` (`_half_open_in_flight`), bloqueando tormentas concurrentes hacia proveedores degradados.
  7. **`N-02`**: Eliminada la sustitución oculta de modelos Gemini en fallback (`_EXHAUSTED_GEMINI_MODELS`); el router respeta estrictamente los modelos configurados en `.env`.
  8. **`M-01`**: Validación profunda de audio (`_validate_mp3_payload`) inspeccionando palabras de sincronización y tramas reales más allá de metadatos `ID3`, rechazando con HTTP 415 archivos sin audio y WAVs vacíos.
  9. **`A-05`**: Descarga de llamadas síncronas pesadas (validación/almacenamiento de fotos y audio, transcripción, creación y actualización en BD) del event loop de FastAPI hacia hilos de trabajo mediante `await run_in_threadpool(...)`.
  10. **`M-06`**: Frontera estricta de confianza para `X-Forwarded-For` y `X-Real-IP` en `get_trusted_client_ip()`; solo se confía en proxies de subredes privadas conocidas (Docker, loopback, RFC1918), evitando spoofing de IP. Banderas `--proxy-headers --forwarded-allow-ips=*` en Dockerfile.
  11. **`Q13`**: Garantizada la presencia de `tracking_code`, `estado_propuesto` y código de aprobación en `tool_proponer_actualizacion_critica` y fallback determinista ante contingencias.
  12. **Actualización de modelo terciario**: Verificada la accesibilidad de `gemini-3.5-flash-lite` como reemplazo verificado de `gemini-3.6-flash` (cuota agotada), garantizando conmutación exitosa en pruebas de contingencia (`GROQ_FAIL`).
- **Verificación de la suite completa + suite adversarial G2 en PostgreSQL 17 real**:
  - `docker compose exec -T api pytest -v`: **`57 passed in 52.94s`** (`23/23` en `tests/test_audit_g2_resilience.py`, `14/14` en `tests/test_audit_g1_security.py`, `12/12` en `tests/test_ai_and_agent.py`, `7/7` en `test_reports_crud.py` y `test_health.py`, `1/1` en `test_e2e_frontend_proxy.py`).
  - Suite dorada (`eval/evaluar.py`): **`6/6` casos dorados verificados por SQL (`100%`)**, **`11/15` consultas representativas aprobadas (`73.33%`)**, Q13 superada.

### Bloque G2.1 — Remediación obligatoria de los cuatro hallazgos prioritarios de auditoría completado (2026-11-02)
- **Detalle completo por hallazgo, diagnóstico, corrección y contraejemplos**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`A-02` (Escrituras posteriores a TIMEOUT cerradas)**: Temporizador activo de cancelación `threading.Timer(rem_sec, conn.cancel)` durante la fase de commit en PostgreSQL, atrapando `QueryCanceled` y forzando rollback inmediato ante demoras por triggers diferidos (`pg_sleep(0.18)`). Cancelación activa out-of-band `cancel_active_conns_for_thread(tid)` y sincronización `shutdown(wait=True)` al abortar herramientas lentas.
  2. **`M-03` (Deadline integral y degradación honesta sin HTTP 500)**: Acotamiento server-side irrevocable `eff_total_timeout = min(AI_TIMEOUT_SECONDS, ...)`. Eliminación del piso de 0.5 s en el router (`effective_timeout = min(per_call_timeout, remaining_for_call)`) y verificación post-llamada para rechazar contratos vencidos. Fallback determinista inmediato y honesto sin abrir conexiones SQL cuando el deadline está vencido, eliminando excepciones no manejadas y respondiendo HTTP 200 con `"guardrail_triggered": "TIMEOUT"`, nunca HTTP 500.
  3. **`M-06` (Confianza en proxies y anti-spoofing en rate limiting)**: Eliminado `--forwarded-allow-ips=*` de Uvicorn en Dockerfile. Nginx configurado para fijar de borde `proxy_set_header X-Forwarded-For $remote_addr;`. `get_trusted_client_ip` verifica primero que el peer TCP pertenezca a la lista explícita de `TRUSTED_PROXIES` antes de evaluar cabeceras, impidiendo eludir el rate limit mediante cabeceras manipuladas (429 verificado en la 3ra solicitud bajo Uvicorn `ProxyHeadersMiddleware`).
  4. **`M-02` (Presupuesto de tokens dinámico y contabilidad multimodal anidada)**: Implementada la clase `TokenBudgetTracker` compartida por contexto entre turnos del agente y herramientas. Estimación dinámica de tokens de entrada (`estimate_prompt_tokens()`) sobre el payload real (sistema + herramientas + historial), activando `MAX_TOKENS` antes de llamar al modelo si el presupuesto restante es insuficiente (< `est_prompt + 20`), impidiendo gastar 1020 tokens con presupuesto 100. Contabilidad y control de presupuesto en `tool_clasificar_evidencia` (1600 tokens multimodal deducidos del presupuesto compartido).
- **Verificación de suites en PostgreSQL 17 real (`civia-db-1`)**:
  - `docker compose exec -T api pytest -v`: **`65 passed in 67.01s`** (100% aprobadas, 0 fallos):
    - `tests/test_audit_g1_security.py`: 14 passed.
    - `tests/test_audit_g2_resilience.py`: 23 passed.
    - `tests/test_audit_g2_1_remediation.py`: 9 passed.
    - `tests/test_ai_and_agent.py`: 12 passed.
    - `tests/test_reports_crud.py`: 6 passed.
    - `tests/test_health.py`: 1 passed.
  - Evaluación E2 (`eval/evaluar.py`): completada con éxito (P50 = 2767.0 ms, P90 = 6380.4 ms). Cero regresiones en N-02 ni mitigaciones G1.
