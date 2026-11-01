# Estado de ejecución

2026-11-01: creado esqueleto inicial. No se han ejecutado builds ni tests Docker en el computador del usuario. Funcionalidad disponible en el scaffold: `/health`; ningún endpoint de reporte o proveedor de IA aún.

## Fase A — Preflight completado (2026-11-01)
- **Git & Docker Compose**: `docker compose config --quiet` (exit code `0`), `docker compose up --build -d` exitoso (`civia-db-1` healthy en `postgres:17-alpine`, `civia-api-1` up y respondiendo `{"status":"ok","phase":"scaffold"}` en `http://localhost:8000/health`).
- **Tests de scaffold**: añadido `backend/tests/test_health.py` ejecutado dentro del contenedor con `pytest -v`.
- **Preflight de modelos de IA con claves `.env` (sin exponer secretos)**:
  - Catálogo Google AI Studio (`/v1beta/models`): presentes `gemini-3.8-flash` y `gemini-3.6-flash` en `GOOGLE_API_KEY_PRIMARY` y `GOOGLE_API_KEY_SECONDARY` (nota: dos claves de un mismo proyecto comparten cuota de proyecto).
  - Catálogo Groq (`/openai/v1/models`): presentes `qwen/qwen3.8-27b`, `whisper-large-v3` y `whisper-large-v3-turbo`.
  - Prueba mínima de capacidades (visión PNG 32x32, salida estructurada JSON y *tool calling*):
    - `gemini-3.8-flash`: existe en catálogo oficial pero durante el preflight presentó `HTTP 503 (high demand)` / timeout de lectura (>15s), lo cual justifica y valida empíricamente la necesidad de timeout acotado, circuit breaker y fallback automático hacia Groq (`qwen/qwen3.8-27b`) y segundo modelo Gemini (`gemini-3.6-flash`).
    - `qwen/qwen3.8-27b` (Groq): Visión + JSON (`response_format: json_object`) OK (requiere imágenes de al menos 32x32 px) y *tool calling* OK (`True`).
    - `gemini-3.6-flash` (Google): Visión + JSON (`responseMimeType: application/json`) OK (~1.67s) y *tool calling* OK (`True`) tanto con `GOOGLE_API_KEY_PRIMARY` como con `GOOGLE_API_KEY_SECONDARY`.

## Fase B — Migraciones, esquema, API CRUD, seguridad y fixtures completada (2026-11-01)
- **Migraciones SQL automáticas (`backend/migrations/001_initial_schema.sql` + `backend/app/db.py`)**:
  - Tablas creadas de forma idempotente al iniciar FastAPI: `schema_migrations`, `reports` (con `CHECK` constraints de coordenadas, tamaños y estados), `ai_traces` (observabilidad protegida) y `pending_approvals` (aprobación humana para escrituras críticas del agente).
  - Índices B-Tree sobre `(latitude, longitude)`, `status`, `final_category`, `ai_category`, `comuna` y `created_at`.
- **Seguridad y privacidad (`backend/app/security.py`)**:
  - Validación de imágenes por *magic bytes* reales (`JPEG`, `PNG`, `WEBP`), tamaño máximo 5 MB, dimensiones entre `32x32` px (compatible con visión multimodal Groq/Gemini) y `8192x8192` px, y re-codificación limpia con `Pillow` eliminando metadatos EXIF y usando nombres `UUID`.
  - Validación de audio opcional (`WAV`, `MP3`, `OGG`, `WEBM`) hasta 5 MB y <= 60 segundos.
  - Validación de coordenadas GPS (`-90..90`, `-180..180`, rechazo de `(0,0)` Null Island, detección de cobertura en Valle del Cauca `in_service_area`).
  - Sanitización de HTML/caracteres de control y minimización de datos personales (redacción automática de correos `[CORREO_PROTEGIDO]` y teléfonos celulares `[TELEFONO_PROTEGIDO]`).
  - Rate limiting por IP en creación de reportes (`429 RATE_LIMIT_EXCEEDED` amigable y sin tracebacks).
- **API CRUD y fixtures sintéticos (`backend/app/main.py`, `backend/app/repository.py`, `backend/app/seed.py`)**:
  - Endpoints operativos: `GET /health`, `POST /api/reports`, `GET /api/reports` (con filtros por categoría, severidad, estado, comuna, texto y búsqueda espacial Haversine `lat`/`lon`/`radius_km`), `GET /api/reports/stats`, `GET /api/reports/by-code/{tracking_code}`, `GET /api/reports/{id}`, `GET /api/reports/{id}/photo`, `PATCH /api/reports/{id}/confirm`, `PATCH /api/reports/{id}/status` y `POST /api/admin/seed`.
  - Semilla automática de 10 reportes sintéticos identificados en Cali (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`, `is_synthetic=True`).
- **Pruebas ejecutadas (`backend/tests/test_reports_crud.py`)**: suite `pytest` ejecutada dentro del contenedor contra PostgreSQL 17 real.

## Fase C — Frontend React + TypeScript + Vite PWA completada (2026-11-01)
- **Interfaz ciudadana PWA (`frontend/`)**:
  - Implementada en React 19 + TypeScript + Vite (`tsc -b && vite build` sin errores) y servida con `nginx:1.27-alpine` en `http://localhost:5173`.
  - Incluye `manifest.webmanifest`, Service Worker (`sw.js`) e icono vectorial.
  - Funcionalidades conectadas al backend real:
    - Panel de estadísticas en vivo desde `GET /api/reports/stats`.
    - Mapa interactivo de Cali con Leaflet (`CaliMap.tsx`), marcadores por categoría y filtro espacial por radio Haversine.
    - Formulario de reporte ciudadano con captura de GPS del navegador, selección manual en mapa de Cali, carga de fotografía (o generador de foto sintética en `<canvas>`), y grabación o carga opcional de nota de voz (`<= 60s`, `<= 5 MB`).
    - Vista de análisis asistido por IA separada de la confirmación/corrección humana (`PATCH /api/reports/{id}/confirm`).
    - Seguimiento por código de radicado (`CIV-2026-...`) con línea de tiempo de estados reales.
    - Asistente agéntico interactivo y panel protegido de Observabilidad/Aprobaciones/Inyección de fallas (`X-Admin-Token`).
  - Verificación E2E entre contenedores (`test_e2e_frontend_proxy.py`): `api` -> `http://frontend:80` comprobando HTML, manifiesto PWA, Service Worker y proxy inverso Nginx hacia `/health` y `/api/reports/stats`.

## Fase D — Sistema agéntico resiliente, herramientas y 4 límites completada (2026-11-01)
- **Router IA desacoplado (`backend/app/ai_router.py`)**:
  - Cadena configurada por entorno: `gemini-3.8-flash` (Google) → `qwen/qwen3.8-27b` (Groq) → `gemini-3.6-flash` (Google), más transcripción opcional de audio con `whisper-large-v3-turbo` (Groq).
  - *Circuit breaker* por proveedor/modelo, *backoff* exponencial con *jitter*, reparación acotada de JSON y validación estricta `AIAnalysisContract`.
  - Degradación elegante ante caída total (`FALLA_FORZADA=TOTAL`): el reporte se conserva en `PENDING_ANALYSIS` con cero errores técnicos hacia el ciudadano.
- **Agente con herramientas tipadas y 4 límites (`backend/app/agent.py`)**:
  - Herramientas: `consultar_reportes`, `obtener_reporte`, `clasificar_evidencia` y `proponer_actualizacion_critica`.
  - Límites verificados con pruebas: `MAX_ITERATIONS`, `MAX_TOKENS`, `TIMEOUT` por herramienta y `HUMAN_APPROVAL_REQUIRED` en tabla `pending_approvals`.
- **Observabilidad protegida (`backend/app/observability.py`)**:
  - Registro en `ai_traces` con redacción automática de secretos (`sanitize_secret_text`), cálculo de latencias `P50`/`P90` y costo estimado en USD.
- **Pruebas ejecutadas (`pytest -v` en contenedor `api`)**: `20 passed` (`test_health.py`, `test_reports_crud.py`, `test_ai_and_agent.py`, `test_e2e_frontend_proxy.py`).

## Próxima tarea para Antigravity
- Ejecutar Fase E (Suite de evaluación formal `eval/casos_dorados.json` con 5 preguntas verificadas manualmente incluyendo 1 sin respuesta, script `eval/evaluar.py` con 15 consultas representativas, registro de métricas reales P50/P90/precisión/costo en `docs/decisiones.md`) y Fase F (Empaquetado final reproducible, checklist de rúbrica y guion de sustentación 6+3 min).
