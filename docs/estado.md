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
