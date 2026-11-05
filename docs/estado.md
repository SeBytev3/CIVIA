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

### Bloque G2.1 — Cierre Definitivo de Hallazgos Residuales M-03, M-06 y M-02 (`docs/auditoria_codex_g2_1.md`) completado (2026-11-02)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`M-03` (Worker no cooperativo desacoplado, endpoint 0.10s y manejador sin HTTP 500)**:
     - `backend/app/agent.py`: `execute_tool_with_timeout` ejecuta el worker en hilo desacoplado con copia de contexto, elimina el retraso artificial de `future.exception(timeout=0.15)` y utiliza `executor.shutdown(wait=False, cancel_futures=True)`. La función aborta conexiones PostgreSQL activas y retorna de inmediato `TimeoutError` en < 0.20s sin esperar la finalización de tareas de CPU o sleeps no cooperativos (resolviendo el bloqueo de 0.4564s observado por Codex).
     - `backend/app/main.py`: Se importó `uuid` en el módulo, asegurando que el manejador final de `TimeoutError` devuelva HTTP 200 con `guardrail_triggered="TIMEOUT"` y un `trace_group_id` UUID válido (eliminando el `NameError` y HTTP 500 detectado por Codex).
     - `backend/app/schemas.py`: Se actualizaron las cotas a `total_timeout_seconds ge=0.10` y `tool_timeout_seconds ge=0.05`, permitiendo peticiones HTTP literales de 0.10s con HTTP 200 (sin 422).
  2. **`M-06` (Anti-spoofing en loopback, redes privadas y Uvicorn)**:
     - `backend/Dockerfile`: Comando de arranque actualizado a `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--forwarded-allow-ips", ""]`, desactivando `ProxyHeadersMiddleware` de Uvicorn en loopback.
     - `docker-compose.yml`: Se fijó `FORWARDED_ALLOW_IPS: ""` y `TRUSTED_PROXIES: ${TRUSTED_PROXIES:-172.16.0.0/12}`.
     - `backend/app/config.py`: `TRUSTED_PROXIES` restringido por omisión a `"172.16.0.0/12"` (únicamente el proxy inverso Nginx en la red Docker), eliminando permanentemente `127.0.0.1`, `::1` y `10.0.0.0/8`.
     - `backend/app/security.py`: `get_trusted_proxy_networks()` no tiene fallback a loopback. Conexiones directas desde peer público (`198.51.100.2`), loopback (`127.0.0.1`) o privado directo (`10.20.30.40`) ignoran `X-Forwarded-For` y reciben rate-limiting estricto por su IP TCP real (`200 / 200 / 429`), sin vías de evasión.
  3. **`M-02` (Propagación de tracker al executor y reserva multimodal previa)**:
     - `backend/app/agent.py`: `execute_tool_with_timeout` propaga `_ACTIVE_TOKEN_TRACKER` mediante `contextvars.copy_context().run(_worker)` y asignación explícita dentro del hilo de trabajo, resolviendo la pérdida de contexto que reportaba 40 tokens en lugar de 1640.
     - `backend/app/agent.py`: `tool_clasificar_evidencia` calcula dinámicamente el costo estimado del prompt multimodal (`build_classification_prompt` / 3.0 + 258 foto + 80 salida). Con presupuesto de 200 tokens y costo estimado de ~394+, interrumpe antes de la llamada activando `MAX_TOKENS` con 0 llamadas al router y 0 tokens gastados. Al autorizarse la llamada, los tokens multimodales (ej. 1600) se suman al tracker del agente, reportando exactamente 1640 tokens en total.
  4. **`_get_clean_test_db` en suites de prueba**:
     - Actualizado en `tests/test_audit_g2_1_remediation.py` para parsear dinámicamente `DATABASE_URL` (en lugar de forzar `host=db`), garantizando ejecución limpia tanto en Docker como en clústeres temporales externos de auditoría (`127.0.0.1:55483`).
- **Verificación de suites en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest tests/test_audit_g1_security.py tests/test_audit_g2_resilience.py tests/test_audit_g2_1_remediation.py tests/test_reports_crud.py tests/test_health.py tests/test_e2e_frontend_proxy.py -v`:
    - **`57 PASSED`** (100% de éxito, 0 fallos en 13.47 s).
    - `test_audit_g2_1_remediation.py`: 12/12 passed (A-02, M-03 worker no cooperativo, M-03 HTTP final, M-03 literal 0.10s, M-06 anti-spoofing completo, M-02 reserva previa y M-02 propagación a hilo).
    - Cero regresiones en controles aprobados G1, A-02 o N-02. Cero commits en `main` ni push remoto.

### Bloque G2.1.1 — Cierre Definitivo de Contraejemplos Residuales M-03, M-06 y M-02 (`docs/auditoria_codex_g2_1_8162a12.md`) completado (2026-11-02)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`M-03` (Capacidad revocable de ejecución, cursor proxy y protección de almacenamiento)**:
     - `backend/app/db.py`: Se implementó `ExecutionCapability` con deadline monotónico y estado atómico `_revoked`. Se vincula a contextvars (`_CURRENT_CAPABILITY`) y a la conexión (`conn._execution_capability`).
     - `backend/app/db.py`: Se incorporó `_CapabilityCursorProxy` sobre los cursores de `psycopg 3`, interceptando llamadas `execute` y `executemany` para levantar inmediatamente `TimeoutError` si la capacidad fue revocada o expiró el plazo, impidiendo que una conexión retenida ejecute SQL tras el deadline.
     - `backend/app/security.py`: `_atomic_write_bytes` valida la capacidad antes de escribir en staging y antes de promover con `os.replace`. Si venció o fue revocada, levanta `TimeoutError` y desvincula cualquier archivo parcial, eliminando escrituras tardías.
     - `backend/app/agent.py`: `execute_tool_with_timeout` revoca la capacidad inmediatamente y delega la cancelación de conexiones PostgreSQL a un hilo daemon de fondo (`cancel_active_conns_for_thread`), permitiendo que el llamador retorne en < 0.20s sin bloqueos síncronos. Se preservan estrictamente los controles de rollback de commit diferido de A-02.
  2. **`M-06` (Identidad exacta del proxy Nginx en red Compose y rechazo de spoofing desde otros contenedores)**:
     - `docker-compose.yml`: Se configuró una red dedicada `civia_net` (`172.28.0.0/16`) con IP estática asignada al frontend `172.28.0.2`.
     - `backend/app/config.py`: `TRUSTED_PROXIES` restringido a `"172.28.0.2,172.18.0.2"`, eliminando la confianza abierta en toda la subred `/12`.
     - Conexiones directas desde otros contenedores (como `172.19.0.9`) o clientes de la misma red son tratadas como directas: cualquier cabecera `X-Forwarded-For` es descartada y la cuota se aplica sobre su IP real de red (`201 / 201 / 429`). Clientes legítimos detrás de Nginx en `172.28.0.2` conservan cuotas independientes.
  3. **`M-02` (Presupuesto atómico de tokens, acumulación en fallos e identificación de consumo desconocido)**:
     - `backend/app/agent.py`: `TokenBudgetTracker` implementa reserva atómica `try_reserve(requested)` con lock de exclusión mutua y conciliación con `reconcile_usage`, impidiendo sobreconsumo por concurrencia.
     - `backend/app/ai_router.py`: `classify_evidence_with_router` acumula el uso de tokens de todos los intentos (`accumulated_prompt_tokens`, `accumulated_completion_tokens`), incluso ante esquemas inválidos (`INVALID_SCHEMA`), registrando la totalidad de tokens conocidos consumidos en la cadena de reintentos (ej. 600 + 800 = 1400 tokens; 3 inválidos = 1800 tokens).
     - `backend/app/schemas.py` y `agent.py`: Se añadieron `tokens_estimated` y `unknown_consumption`. Si los intentos fallan por error de red o remoto sin metadatos, se imputa una estimación conservadora identificada y se señala el consumo como desconocido/estimado, sin reportar cero ficticio.
  4. **Hermeticidad de la suite de pruebas**:
     - `backend/tests/test_ai_and_agent.py`: Incorporado transporte simulado hermético para asegurar que las 12 pruebas de integración del agente y router se ejecuten exitosamente y de forma determinista en entornos de auditoría sin claves API externas ni acceso a internet.
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -v`:
    - **`77 PASSED`** (100% de éxito, 0 fallos, 1 warning en 25.35 s).
    - `test_audit_g2_1_remediation.py`: 20/20 passed (12 de G2.1 + 8 de G2.1.1).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 12/12 passed.
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02 o N-02. Cero commits en `main` ni push remoto.

### Bloque G2.1.2 — Cierre Definitivo de Bloqueos de Cursor, Carrera de Archivos, Topología Compose y Hermeticidad (`docs/auditoria_codex_g2_1_1_a745a1c.md`) completado (2026-11-02)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`M-03` (Preservación de identidad de proxies de cursor en llamadas encadenadas, `copy()`, `stream()` y serialización en promoción de archivos)**:
     - `backend/app/db.py`: `_CapabilityCursorProxy.execute()` y `executemany()` retornan `self`, evitando que llamadas encadenadas (`conn.cursor().execute(...)`) devuelvan el cursor nativo de psycopg desprotegido. Se envolvieron `cur.copy()` y `conn.copy()` con `_CapabilityCopyProxy` y se protegieron lecturas en streaming. En `get_conn()`, `conn.execute` se delegó directamente al proxy protegido de la capacidad.
     - `backend/app/db.py` y `security.py`: `ExecutionCapability.authorized_replace(src, dst)` y `atomic_publish_file()` ejecutan la comprobación de revocación y `os.replace` bajo el cerrojo `self._lock`, eliminando la carrera TOCTOU entre revocación y publicación de archivos. Si la capacidad fue revocada, el archivo temporal se elimina y se levanta `TimeoutError`. Se preservan estrictamente los controles de rollback de commit diferido de A-02.
  2. **`M-06` (Asignación estática de IPs en Compose y purga de IP heredada)**:
     - `docker-compose.yml`: Red `civia_net` con subred `172.28.0.0/16` y asignación disjunta y estática: `frontend` (Nginx) en `172.28.0.2`, `db` en `172.28.0.10` y `api` en `172.28.0.11`.
     - `backend/app/config.py`: `TRUSTED_PROXIES` fijado a `"172.28.0.2"`. Se purgó completamente `172.18.0.2` del código y de las suites.
     - Verificado mediante `docker network inspect` y reinicios limpios que `172.28.0.2` pertenece única y exclusivamente a Nginx. Conexiones directas desde otros contenedores o la red reciben rate limiting estricto (`201 / 201 / 429`), y clientes independientes detrás de Nginx conservan cuotas aisladas.
  3. **`M-02` (Reserva y conciliación de tokens por intento individual en el Router IA)**:
     - `backend/app/ai_router.py`: `classify_evidence_with_router` realiza la reserva atómica `token_tracker.try_reserve(est_attempt_tokens)` por intento individual dentro del bucle de proveedores. Concilia inmediatamente el uso real al finalizar el intento y, si los tokens consumidos agotan el saldo disponible (`remaining < est_attempt`), interrumpe de inmediato (`break`) sin invocar a proveedores subsiguientes (como Groq).
     - Se marcaron `INVALID_JSON` e `INVALID_SCHEMA` como errores no reintentables sobre el mismo modelo y se eliminó la duplicación redundante de acumulación de tokens en bloques de excepción.
  4. **Hermeticidad incondicional de pruebas**:
     - `backend/tests/test_ai_and_agent.py`: Adaptadores de proveedores IA reemplazados incondicionalmente mediante `hermetic_multimodal_adapter_fixture`. Fixture `guard_no_external_network_calls` que intercepta llamadas HTTP externas a dominios de Google y Groq y falla inmediatamente ante tráfico imprevisto (`test_hermetic_guard_fails_immediately_on_unexpected_external_http`).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -v`:
    - **`83 PASSED`** (100% de éxito, 0 fallos, 1 warning en 9.39 s).
    - `test_audit_g2_1_remediation.py`: 24/24 passed (incluyendo los 4 nuevos tests de regresión G2.1.2).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 14/14 passed.
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02 o N-02. Cero commits en `main` ni push remoto.

### Bloque G2.1.3 — Cierre de Reserva Concurrente, Contrato COPY, Transaction Timeout y Hermeticidad Global (`docs/auditoria_codex_g2_1_2_d07a1e5.md`) completado (2026-11-02)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`M-02` (Aislamiento de reservas por manija `TokenReservation` y conciliación exactamente una vez)**:
     - `backend/app/agent.py`: Se implementó la clase `TokenReservation` con propiedad unívoca y métodos `reconcile()` y `release()` atómicos e idempotentes (`is_active`). `TokenBudgetTracker.try_reserve()` devuelve un objeto `TokenReservation` específico.
     - `backend/app/agent.py` y `ai_router.py`: `tool_clasificar_evidencia` y `run_civia_agent` operan exclusivamente sobre sus manijas de reserva individuales. En los bloques `finally:`, solo se concilia/libera si la manija propia está activa, eliminando la colisión donde dos clasificaciones concurrentes de 700 tokens con presupuesto compartido de 6000 registraban 2100 tokens en lugar de 1400. En `ai_router.py`, los manejadores de excepción verifican `if active_reservation is not None:` antes de imputar tokens en fallos de esquema.
     - Prueba permanente `test_g2_1_3_m02_two_concurrent_authorized_calls_record_1400_not_2100` añadida y verificada (`PASSED`).
  2. **`M-03` (Contrato completo de Context Manager en COPY `_CapabilityCopyProxy` y revocación en streaming)**:
     - `backend/app/db.py`: `_CapabilityCopyProxy` ahora retiene el generador gestor de contexto de psycopg 3 (`self._cm`) e invoca `__enter__()` produciendo la instancia real de `Copy` con soporte íntegro para `rows()`, `read()`, `read_row()`, `write()`, `write_row()` e `__iter__()`.
     - Las lecturas por filas delegan en `_CapabilityStreamProxy`, validando la capacidad fila por fila e interrumpiendo con `TimeoutError` si se supera el deadline o se revoca la capacidad.
     - Prueba permanente `test_g2_1_3_m03_copy_out_and_copy_in_authorized_and_rejected_after_revocation` añadida y verificada (`PASSED`).
  3. **`A-02` (Aplicación de `transaction_timeout` a nivel de servidor en PostgreSQL 17 y desacople de latencia)**:
     - `backend/app/db.py`: Tanto `checked_commit(conn)` como `_wrapped_commit()` configuran `SET LOCAL transaction_timeout = {timeout_ms}` en PostgreSQL antes de ejecutar `COMMIT`, asegurando que constraint triggers diferidos lentos sean cancelados directamente por el motor de base de datos con `TransactionTimeout`.
     - `backend/tests/test_audit_g2_1_remediation.py`: Sincronización determinista con `executor.shutdown(wait=True)` en la prueba de triggers diferidos, y desacople de la verificación de integridad de datos respecto a fluctuaciones del scheduler de hilos en Windows (`< 0.60s`).
  4. **Hermeticidad global a nivel de sesión**:
     - `backend/tests/conftest.py`: Fixture de sesión `guard_no_external_network_calls` que intercepta `httpx.Client.send` y lanza `RuntimeError` ante cualquier intento de tráfico hacia dominios de Google o Groq.
     - `backend/tests/test_audit_g1_security.py`: Incorporado `hermetic_multimodal_adapter_fixture` de forma global para toda la suite de seguridad G1, garantizando que `test_a06` con `auto_analyze: true` no intente llamadas salientes.
  5. **Coexistencia de red Docker Compose**:
     - Preservada la topología fija (`frontend` en `172.28.0.2`, `db` en `172.28.0.10`, `api` en `172.28.0.11`).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -v`:
    - **`85 PASSED`** (100% de éxito, 0 fallos en 10.40 s).
    - `test_audit_g2_1_remediation.py`: 26/26 passed (incluyendo los 2 nuevos tests adversariales G2.1.3).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 14/14 passed.
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02 o N-02. Cero commits en `main` ni push remoto.

### Bloque G2.1.4 — Cierre de Integridad Transaccional A-02 y Hermeticidad Total de Turnos de Agente (`docs/auditoria_codex_g2_1_3_4a99705.md`) completado (2026-11-03)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`A-02` (Integridad transaccional absoluta y eliminación de commits tardíos tras pausas de planificación)**:
     - `backend/app/db.py`: Tanto en `checked_commit(conn)` como en `_wrapped_commit()`, se re-evalúa el saldo disponible contra el deadline monotónico inmediatamente antes de iniciar `COMMIT` (`rem_sec_commit = dl_check - time.monotonic()`). Si expiró (`rem_sec_commit <= 0`), aborta y ejecuta `conn.rollback()` de inmediato sin emitir `COMMIT`.
     - Si el tiempo disponible disminuyó durante la espera o planificación previa (`rem_ms_effective < timeout_ms`), se ajusta dinámicamente el límite en PostgreSQL antes de emitir `COMMIT` mediante `SELECT set_config('transaction_timeout', '{rem_ms_effective}', true);`, anclando la expiración en el motor al saldo real del deadline original y garantizando que triggers diferidos lentos sean abortados a nivel de servidor por `TransactionTimeout`.
     - El temporizador `threading.Timer` se inicializa con el saldo final monotónico exacto recalculado inmediatamente antes de invocar `conn.commit()`.
     - Pruebas permanentes: `test_g2_1_4_a02_reproduction_scheduling_pause_and_delayed_cancel_preserves_original` para los cuatro casos (61, 62, 63 y 64) con pausa de planificación de 0.13 s y retraso de cancelación de 0.15 s; verifican que el worker aborta con `TimeoutError`, cero commits son confirmados y el estado final permanece estrictamente `ORIGINAL` (**PASSED**).
  2. **Hermeticidad total de la suite**:
     - `backend/tests/conftest.py`: Se implementó la fixture `hermetic_agent_turn_adapter_fixture` (`autouse=True`) que sustituye incondicionalmente `_call_agent_turn_gemini` y `_call_agent_turn_groq` por un emulador determinista, garantizando que ninguna consulta conversacional intente tráfico externo.
     - `backend/tests/conftest.py`: La fixture `guard_no_external_network_calls` acumula intentos salientes en `unexpected_attempts` e invoca `pytest.fail()` en su teardown si se detecta cualquier intento imprevisto, impidiendo que el producto capture y absorba excepciones de red.
     - `backend/tests/test_ai_and_agent.py`: `test_optional_live_provider_multimodal_connectivity` marcado como prueba opcional separada (`@pytest.mark.live`).
     - Prueba permanente: `test_g2_1_4_hermetic_suite_zero_external_attempts_synthetic_and_empty` comprueba cero intentos tanto con claves sintéticas como con claves vacías (**PASSED**).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -v`:
    - **`90 PASSED`** (100% de éxito, 0 fallos, 1 warning en 10.87 s).
    - `test_audit_g2_1_remediation.py`: 31/31 passed (incluyendo los 5 nuevos tests G2.1.4).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 14/14 passed.
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02, N-02, M-02, M-03 COPY o M-06. Cero commits en `main` ni push remoto.

## Verificación local independiente G2.1.7 — 2026-11-03

- Checkout comprobado por comandos: `492b0415bd1642d077ce7ce48ea2e2cb1c5b26c6`, rama `fix/auditoria-final`, árbol inicialmente limpio.
- Migraciones 004/005 y `backend/app/db.py` leídos; hashes y evidencias en `docs/auditoria_codex_g2_1_7_492b041.md`.
- **Auditoría dinámica bloqueada:** `docker compose ps` falla al conectar con `dockerDesktopLinuxEngine` (código 1). No se confirmó disponibilidad de API, PostgreSQL 17 ni frontend. Sin dictamen de aceptación técnica.
- Lint y tests del producto no ejecutados: no se cumplió la condición previa para la auditoría aislada. Los 105 PASS anteriores no son resultados reproducidos por esta revisión.
- Sin cambios de producción, servicios o datos habituales; sin Autopilot, commits, push ni merge. Cambios limitados al informe y esta anotación.

## Auditoría independiente G2.1.7 reanudada — 2026-11-03

- Docker nuevamente disponible: API, PostgreSQL y frontend habituales saludables. HEAD sigue en `492b041`, rama `fix/auditoria-final`; solo cambios documentales del intento previo al empezar.
- Copia congelada de Git y PostgreSQL **17.11** exclusivo en red interna sin puertos publicados. Código de producción intacto. Evidencia fuera del checkout en `C:\Users\Jhoesp\AppData\Local\Temp\civia-492b041-04bcac63ba274f3093fa56dac5d17406`.
- **Dictamen: NO APROBADO.** Corrigen atomicidad del executor, deduplicación y propagación PENDING; persisten mutación crítica sin ledger, transición ABORTED→COMMITTED por helper, aborto deducido de observación fallida, UNKNOWN sin resolución pese a evidencia propia, exposición de metadatos, entrega/replay de token incompletos y atribución falsa de cancelaciones externas dentro del margen de 50 ms.
- Suites con claves vacías: **104 PASS, 1 SKIP, 1 live excluida**, 21,46 s; claves sintéticas: **104 PASS, 1 SKIP, 1 live excluida**, 18,12 s. Incluyen las siete pruebas G2.1.7 y regresiones M-02, COPY, M-06, G1 y N-02. E2E frontend omitido por aislamiento; sin intentos externos inesperados reportados por la guardia hermética.
- Se conserva el primer pase mal configurado del auditor: 103 PASS, 1 FAIL (`eval` fuera de PYTHONPATH), 1 SKIP, 1 excluida; se corrigió solo el entorno y se repitió en base nueva. No se alteraron pruebas.
- `compileall` pasó; no equivale a lint. No se encontró configuración/comando de lint Python del proyecto. `git diff --check` valida los cambios documentales.
- Se eliminaron únicamente runner, PostgreSQL, volumen exclusivo y red exclusiva del auditor tras verificar sus IDs. Los tres servicios habituales siguen saludables. Sin Autopilot, commits, push, merge ni cambio de rama.
- Informe con matriz, evidencias, cambios mínimos y recomendación de simplificar temporalmente escrituras asíncronas: `docs/auditoria_codex_g2_1_7_492b041.md`. No se inició remediación ni otra fase de desarrollo.

### Bloque G2.1.5 — Resolución Definitiva de Integridad Transaccional A-02 y Normalización de Excepciones (`docs/auditoria_codex_g2_1_4_95eecba.md`) completado (2026-11-03)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en la sección 10 de [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`A-02` (Sincronización dinámica de vencimiento en el dominio temporal del servidor PostgreSQL)**:
     - `backend/app/db.py`: Eliminado el paso de enteros milimétricos relativos calculados previamente en Python. Ahora se transmite a PostgreSQL el epoch objetivo absoluto (`target_epoch = time.time() + rem_sec`).
     - PostgreSQL calcula dinámicamente en SQL mediante `clock_timestamp()` el remanente real:
       `set_config('transaction_timeout', GREATEST(1, CEIL((%s - EXTRACT(EPOCH FROM clock_timestamp())) * 1000))::text, true)`
       absorbiendo cualquier pausa de planificación o red entre Python y la BD. Si el plazo ya expiró al momento de ejecución, PostgreSQL ejecuta inmediatamente `pg_cancel_backend(pg_backend_pid())`.
  2. **Unificación arquitectónica de `checked_commit` y `_wrapped_commit`**:
     - `_wrapped_commit()` en `get_conn` delega íntegramente en `checked_commit(conn)`, invocando la referencia nativa `conn._orig_commit`. Ambos métodos ejecutan la misma lógica rigurosa de protección, reevaluación monotónica y validación de supervisor post-commit.
  3. **Límites tempranos a nivel de sesión**:
     - `get_conn` configura preventivamente `transaction_timeout` a nivel de conexión anclado al target epoch del servidor.
  4. **Normalización del contrato de excepciones en `agent.py`**:
     - En `backend/app/agent.py:execute_tool_with_timeout`, tanto en `_worker` como en `future.result`, se traducen de forma exhaustiva `psycopg.errors.QueryCanceled`, `TransactionTimeout`, `AdminShutdown` y fallos operacionales de cancelación a `TimeoutError`.
  5. **Pruebas permanentes de regresión**:
     - `test_g2_1_a02_balanced_config_checks_cases_81_84_prevent_late_writes`: reproduce los casos 81 a 84 con pausas de 40 ms, 5 ms y 40 ms, con y sin Timer, confirmando estado `ORIGINAL` en el 100% de los casos (**PASSED**).
     - `test_g2_1_a02_legitimate_commits_within_deadline`: confirma que transacciones legítimas dentro del plazo persisten `CHANGED` sin demoras (**PASSED**).
     - `test_g2_1_a02_cases_61_64_scheduling_delay`: verifica la resistencia ante pausas de 0.13 s (**PASSED**).
     - `test_g2_1_a02_active_conn_cancellation_on_slow_worker`: verifica cancelación de workers lentos y tipo de excepción `TimeoutError` (**PASSED**).
### Bloque G2.1.6 — Rediseño del Contrato Transaccional A-02 y Registro Durable (`docs/auditoria_codex_g2_1_5_cdc646b.md`) completado (2026-11-03)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en la sección 13 de [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`A-02` (Eliminación de falsos rollbacks post-commit y estados unívocos `COMMITTED`, `ABORTED`, `PENDING`, `UNKNOWN`)**:
     - `backend/app/db.py:checked_commit`: Se eliminó el lanzamiento de `TimeoutError` post-commit. Si el commit nativo retornó éxito, PostgreSQL confirmó la transacción de forma definitiva; mentir al llamador reportando un timeout mientras la base de datos persistió el cambio queda formalmente erradicado.
     - Registro en vuelo `_IN_FLIGHT_COMMITS` durante la ejecución nativa de commit.
     - `backend/app/agent.py`: Cuando el supervisor agota su plazo de espera mientras la transacción está en confirmación nativa, levanta `OperationPendingError` con `status="PENDING"` e identificador durable, sin presumir rollback ficticio ni cancelar la conexión que está confirmando.
  2. **Registro durable de operaciones e idempotencia (`operation_records`)**:
     - Migración `backend/migrations/004_operation_records.sql` con tabla `operation_records`: `operation_id UUID PRIMARY KEY`, `idempotency_key`, `operation_type`, `target_id`, `status CHECK ('PENDING', 'COMMITTED', 'ABORTED', 'UNKNOWN')`, `proposed_payload`, `result_payload`, `backend_pid`, `created_at`, `updated_at`.
     - `register_operation_intent`: Registra la intención durablemente en autocommit antes de ejecutar.
     - En `checked_commit`: Actualización atómica de estado a `COMMITTED` dentro de la transacción protegida por `SAVEPOINT op_rec_sp`.
     - Idempotencia en herramientas críticas (`tool_proponer_actualizacion_critica`): retornos consistentes ante reintentos con la misma clave de idempotencia sin duplicar solicitudes en `pending_approvals`.
  3. **Normalización determinista de excepciones de infraestructura**:
     - `backend/app/db.py:is_deadline_cancellation`: `AdminShutdown` y SQLSTATE `57P01` son explícitamente excluidos de cancelaciones de plazo, garantizando que terminaciones de backend por administrador o caídas de infraestructura no se disfracen de `TimeoutError` ni activen el guardrail `TIMEOUT`.
  4. **Reconciliación y Endpoint Público**:
     - `backend/app/db.py:reconcile_operation`: Inspecciona el `backend_pid` en `pg_stat_activity` y el recurso objetivo para resolver deterministamente operaciones `PENDING` a `COMMITTED` o `ABORTED`.
     - `backend/app/main.py`: Endpoint `GET /api/operations/{operation_id}` y adaptación de respuesta en `/api/agent/query` con `guardrail_triggered="OPERATION_PENDING"` para trazabilidad ciudadana.
  5. **Pruebas permanentes de regresión**:
     - `test_g2_1_6_admin_shutdown_not_masked_as_timeout`: `pg_terminate_backend` (57P01) preservado como error administrativo (**PASSED**).
     - `test_g2_1_6_in_flight_commit_returns_operation_pending_on_supervisor_timeout`: supervisor reporta `PENDING` en commit en vuelo y resuelve a `ABORTED` (**PASSED**).
     - `test_g2_1_6_clock_offset_cases_102_109_truthful_pending_and_committed`: casos 102/109 con desfase de reloj (+100 ms) reportan verazmente `PENDING` al llamador y persisten `COMMITTED` en BD (**PASSED**).
     - `test_g2_1_6_idempotent_proposal_replay`: idempotencia sin duplicados en `pending_approvals` (**PASSED**).
     - `test_g2_1_6_reconciliation_of_disconnected_operation`: reconciliación determinista de operaciones huérfanas (**PASSED**).
     - `test_g2_1_6_api_endpoint_operations_status`: API `GET /api/operations/{operation_id}` (**PASSED**).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest tests -m "not live"`:
    - **`98 PASSED, 1 deselected`** (100% de éxito, 0 fallos, 1 warning en 15.24 s).
    - `test_audit_g2_1_remediation.py`: 40/40 passed (incluyendo los 6 nuevos tests G2.1.6).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 13/13 passed (1 deselected live).
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02, N-02, M-02, M-03 COPY o M-06. Cero commits en `main` ni push remoto.

---

## Bloque G2.1.7 — Endurecimiento Fail-Closed, Autorización y Reconciliación del Registro Transaccional (`docs/auditoria_codex_g2_1_6_f6fe4f6.md`) completado (2026-11-03)
- **Documentación de diseño**: Especificada previamente en [`docs/diseno_g2_1_7.md`](diseno_g2_1_7.md) y en la sección 16 de [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **P0 — Atomicidad obligatoria del registro (Fail-Closed)**:
     - `backend/app/db.py:checked_commit`: Eliminado definitivamente el uso de `SAVEPOINT op_rec_sp`. La actualización `UPDATE operation_records SET status = 'COMMITTED', updated_at = clock_timestamp() WHERE operation_id = %s AND status = 'PENDING'` se ejecuta directamente en la misma transacción que el negocio y exige `cur.rowcount == 1`. Si el marcador falla por un trigger, tabla ausente o bloqueo, se ejecuta `conn.rollback()` y se aborta la transacción completa. Jamás se confirma negocio si el marcador falla.
     - `register_operation_intent`: Falla cerrado propagando excepciones si `operation_records` no existe o no puede persistir, impidiendo que la herramienta ejecute negocio sin trazabilidad durable.
  2. **P0 — Reconciliación basada en evidencia propia e inmutabilidad monótona**:
     - Migración `backend/migrations/005_operation_records_hardening.sql`: Vincula `pending_approvals` con `operation_id UUID REFERENCES operation_records(operation_id) ON DELETE SET NULL` e índice dedicado.
     - `backend/app/db.py:reconcile_operation`: Verifica evidencia en `pending_approvals` por `operation_id` exacto; jamás infiere `COMMITTED` por la existencia de otra propuesta genérica sobre el mismo `report_id`.
     - Si `backend_pid` es `None` (el worker aún no abre conexión o está esperando), `reconcile_operation` conserva `PENDING` (o `UNKNOWN`), erradicando falsos `ABORTED` prematuros comunicados por API antes de que el worker termine `COMMITTED`.
     - Estados terminales `COMMITTED` y `ABORTED` son estrictamente inmutables.
  3. **P0 — Autorización del endpoint y protección de información**:
     - `backend/app/main.py:get_operation_status`: Implementa autenticación mediante `X-Admin-Token` o `X-Operation-Token` (token de consulta opaco de 32 bytes validado con hash SHA-256 en tiempo constante vía `hmac.compare_digest`).
     - `backend/app/schemas.py:OperationStatusResponse`: `idempotency_key` eliminado del esquema público; `result_payload` y errores detallados solo se exponen a invocadores autorizados (propietario o admin). Consultas anónimas reciben únicamente el estado general de procesamiento (`PENDING`, `COMMITTED`, `ABORTED`), impidiendo la filtración de notas privadas o claves reutilizables.
  4. **P0 — Idempotencia concurrente real y deduplicación atómica**:
     - Restricción única `uq_operation_records_scoped UNIQUE (requester_id, operation_type, idempotency_key)` en `operation_records`.
     - Reclamo atómico en PostgreSQL con `INSERT ... ON CONFLICT (requester_id, operation_type, idempotency_key) DO UPDATE SET updated_at = operation_records.updated_at RETURNING *, (xmax = 0) AS is_new_claim`.
     - Validación de huella canónica de payload (`canonical_payload_hash`): si la clave se reutiliza con un payload diferente, se eleva `IdempotencyConflictError` (HTTP 409 Conflict).
     - Si la clave ya fue comprometida (`COMMITTED`), retorna el resultado durable sin reejecutar el negocio (incluso si `result_payload` está vacío, reconstruyendo la confirmación con `operation_id` estable).
     - En `pending_approvals`: índice único parcial `idx_pending_approvals_active_proposal ON pending_approvals (report_id) WHERE status = 'PENDING' AND proposed_action = 'UPDATE_REPORT_STATUS'` e inserción atómica `ON CONFLICT DO NOTHING`, impidiendo propuestas concurrentes duplicadas para el mismo reporte a nivel de motor SQL.
  5. **P1 — Propagación íntegra de OPERATION_PENDING**:
     - `backend/app/agent.py:execute_tool_with_timeout`: Captura `OperationPendingError` antes de `FuturesTimeoutError`, impidiendo su degradación a `TimeoutError` ordinario y preservando el `operation_id` durable.
     - Diferenciación entre herramientas transaccionales (con reclamo duradero en `operation_records`) y consultas de sólo lectura (`consultar_reportes`, `obtener_reporte`), garantizando que consultas de lectura lentas reporten limpiamente `TIMEOUT` mientras transacciones en vuelo reportan `OPERATION_PENDING`.
  6. **P1 — Procedencia causal de cancelaciones PostgreSQL**:
     - `backend/app/db.py:is_deadline_cancellation`: Verifica que cancelaciones `25P04` (`TransactionTimeout`) o `57014` (`QueryCanceled`) solo se atribuyan al deadline local si el tiempo transcurrido es mayor o igual al plazo de la herramienta (`time.monotonic() >= deadline - 0.05`) o la capacidad fue revocada. Políticas ajenas de conexión (ej. `transaction_timeout=50ms` de sesión con deadline de 2s) preservan el error original `OperationalError` / `TransactionTimeout`.
  7. **Pruebas permanentes de regresión**:
     - `test_g2_1_7_fail_closed_marker_failure_aborts_business_transaction` (**PASSED**).
     - `test_g2_1_7_missing_migration_004_fails_closed` (**PASSED**).
     - `test_g2_1_7_reconcile_only_on_exact_operation_id_evidence` (**PASSED**).
     - `test_g2_1_7_concurrent_idempotency_claim_single_execution` (**PASSED**).
     - `test_g2_1_7_idempotency_payload_conflict_raises_error` (**PASSED**).
     - `test_g2_1_7_committed_without_result_replay_reconstructs` (**PASSED**).
     - `test_g2_1_7_foreign_transaction_timeout_preserves_error` (**PASSED**).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -m "not live"`:
    - **`105 PASSED, 1 deselected`** (100% de éxito, 0 fallos, 1 warning en 25.33 s).
    - `test_audit_g2_1_remediation.py`: 47/47 passed (incluyendo los 7 nuevos tests G2.1.7).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 13/13 passed (1 deselected live).
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02, N-02, M-02, M-03 COPY o M-06. Cero commits en `main` ni push remoto.

---

## Bloque G2.1.8 — Inmutabilidad Terminal, Autorización Estricta y Reconciliación Determinista (`docs/auditoria_codex_g2_1_7_492b041.md`) completado (2026-11-04)
- **Documentación de diseño**: Especificada en la sección 17 de [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **Inmutabilidad estricta de estados terminales**:
     - Migración `backend/migrations/006_operation_records_terminal_states.sql`: Crea la función de trigger `prevent_terminal_operation_state_mutation()` y el trigger `trg_prevent_terminal_operation_state_mutation` a nivel de motor en PostgreSQL. Cualquier intento de actualizar filas con `status IN ('COMMITTED', 'ABORTED')` hacia un estado diferente aborta la transacción con excepción SQL.
     - `backend/app/db.py:mark_operation_committed`: Cláusula `WHERE operation_id = %s AND status != 'ABORTED'`. Valida explícitamente el estado previo y lanza `RuntimeError` si la operación ya estaba abortada, impidiendo resucitaciones ilegales sin evidencia.
     - `mark_operation_aborted`: Cláusula `WHERE status IN ('PENDING', 'UNKNOWN')`.
  2. **Autorización estricta y prueba de posesión de tokens (sin almacenamiento reversible)**:
     - Se descartó AES-GCM en favor de capacidades deterministas basadas en hashes SHA-256 unidireccionales (`query_token_hash`, `edit_token_hash`).
     - Al generar una operación agéntica transaccional en `OPERATION_PENDING`, se entrega el token unívoco al emisor legítimo a través del campo `query_token` en `AgentQueryResponse` (`backend/app/schemas.py`).
     - Replays sin posesión de credencial:
       - Para operaciones privadas (`operation_type = 'ADMIN_PRIVATE'` o con `target_id`), consultas no autorizadas o anónimas reciben HTTP 404 (anti-enumeración).
       - Consultas anónimas a operaciones públicas devuelven únicamente el estado general (`PENDING`, `COMMITTED`, `ABORTED`) con `target_id` y `result_payload` redactados a `None`.
       - Replays agénticos anónimos de operaciones `COMMITTED` devuelven el estado previo pero jamás revelan payloads privados ni claves secretas (`secret_key`).
       - Replays de operaciones `ABORTED` retornan de inmediato la confirmación de aborto sin despachar nuevos workers en segundo plano.
       - Replays de operaciones `UNKNOWN` levantan inmediatamente `OperationPendingError` sin invocar workers redundantes.
  3. **Atomicidad de mutaciones REST síncronas administrativas**:
     - `backend/app/repository.py:update_report_status`: Se integró la inserción directa en `operation_records` (con `status = 'COMMITTED'`, `requester_id = 'admin'`, `operation_type = 'UPDATE_REPORT_STATUS'`) dentro de la MISMA transacción PostgreSQL que actualiza la tabla `reports`.
     - Si la tabla `operation_records` no existe (ej. falta de migración 004) o si la inserción en el ledger falla, la transacción realiza un rollback conjunto y la función eleva excepción; el endpoint `PATCH /api/reports/{id}/status` retorna HTTP 500 y el estado del reporte permanece intacto en base de datos.
  4. **Eliminación del margen de 50 ms en procedencia causal (`is_deadline_cancellation`)**:
     - `backend/app/db.py:is_deadline_cancellation`: Se removió el margen especulativo `- 0.05`. La clasificación como cancelación local ahora exige estrictamente que la capacidad local esté revocada (`not cap.is_valid()`) o que el tiempo monotónico actual haya superado el deadline (`time.monotonic() >= dl`).
     - Timeouts externos (ej. `statement_timeout` o `transaction_timeout` de 20 ms dentro de un deadline local mayor) retornan `classified_local: false`, erradicando falsas clasificaciones.
  5. **Principio de incertidumbre en reconciliación**:
     - `backend/app/db.py:reconcile_operation`: Si la inspección de `pg_stat_activity` falla por cualquier excepción técnica de red o base de datos, se marca `stat_failed = True` y la función preserva el estado en `PENDING` o `UNKNOWN` sin alterar `operation_records`. Jamás se infiere `ABORTED` ante fallos de observación.
  6. **Pruebas permanentes de regresión adversarial (`backend/tests/test_audit_g2_1_8_adversarial.py`)**:
     - `test_adversarial_terminal_state_sql_trigger_prevents_mutation`: El trigger SQL en PostgreSQL rechaza mutaciones de estados terminales (`COMMITTED` y `ABORTED`) (**PASSED**).
     - `test_adversarial_helper_mark_operation_committed_rejects_aborted`: `mark_operation_committed` rechaza transicionar `ABORTED -> COMMITTED` con `RuntimeError` (**PASSED**).
     - `test_adversarial_rest_status_mutation_joint_atomic_rollback`: Fallo en `operation_records` realiza rollback conjunto y preserva el estado del reporte (**PASSED**).
     - `test_adversarial_rest_status_mutation_records_in_ledger`: Mutación REST exitosa persiste atómicamente el registro en `operation_records` (**PASSED**).
     - `test_adversarial_deadline_cancellation_no_50ms_tolerance`: Cancelación PostgreSQL externa con tiempo remanente antes del deadline devuelve `classified_local: False` (**PASSED**).
     - `test_adversarial_observation_failure_leaves_pending`: Fallo de observación en `reconcile_operation` no altera la base de datos a `ABORTED` (**PASSED**).
     - `test_adversarial_private_operation_unauthorized_yields_404`: Consulta no autorizada a operación privada retorna HTTP 404 (**PASSED**).
     - `test_adversarial_hijack_attempt_fails`: Replay no autorizado sin token no entrega payload sensible ni permite secuestro (**PASSED**).
     - `test_adversarial_agent_query_pending_delivers_query_token`: Respuesta agéntica `OPERATION_PENDING` entrega el `query_token` unívoco (**PASSED**).
- **Verificación oficial en clúster PostgreSQL 17.11 desechable y runner aislado**:
  - `pytest /audit/src/backend/tests/test_audit_g2_1_8_adversarial.py`: **`9 passed in 1.99s`** (100% éxito).
  - Verificación suite completa modo `BLANK` (sin claves API): **`114 passed, 1 skipped, 1 warning in 18.73s`**.
  - Verificación suite completa modo `SYNTHETIC` (claves sintéticas): **`114 passed, 1 skipped, 1 warning in 18.76s`**.
  - Verificación scripts independientes de Codex:
    - `boundaries.py`: Exit code 0 (10/10 checks exitosos, incluyendo `external_timeout_margin_*` con `classified_local: false` y `rest_mutation_missing_ledger` con HTTP 500 y rollback verificado).
    - `error_provenance.py`: `external_25P04_margin`, `real_admin_shutdown` y `real_undefined_table` con `classified_local: false`.
    - `api_restart_check.py`: Exit code 0 (`durable_before_process_kill: PENDING`, `fresh_api_result: {http: 200, status: COMMITTED}`, `durable_after: COMMITTED`).
    - `independent.py`: Exit code 0 (aislamiento de claims, anti-enumeración 404, replays ABORTED/UNKNOWN sin workers espurios).
    - `test_e2e_frontend_proxy.py`: 1 passed (comprobación E2E contra proxy frontend PWA real).
  - Cero regresiones en controles aprobados G1, A-02, N-02, M-02, M-03 COPY o M-06. Cero commits en `main` ni push remoto.
