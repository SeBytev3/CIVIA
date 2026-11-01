# Arquitectura implementada — CIVIA

**Estado:** Fases A, B, C y D implementadas y verificadas mediante Docker Compose y suite de pruebas automatizadas.

## Componentes principales
- **Frontend (`frontend/`, puerto `5173`)**:
  - React 19 + TypeScript + Vite compilado en contenedor multi-stage (`node:22-alpine` -> `nginx:1.27-alpine`).
  - PWA instalable con `manifest.webmanifest`, `sw.js` e icono vectorial.
  - Mapa interactivo de Cali con Leaflet, filtros combinados y búsqueda espacial por radio Haversine.
  - Nginx actúa como proxy inverso para `/api/*` y `/health` hacia `http://api:8000`, evitando rutas absolutas o problemas CORS en cualquier máquina.
- **Backend (`backend/`, puerto `8000`)**:
  - FastAPI (`Python 3.13-slim`) con migraciones SQL automáticas e idempotentes al arranque (`app/db.py` + `migrations/001_initial_schema.sql`).
  - Validación de seguridad (`app/security.py`): verificación de firmas binarias (*magic bytes*) para imágenes y audio, dimensiones `32x32..8192x8192`, eliminación de metadatos EXIF, sanitización de HTML/PII y *rate limiting* por IP.
  - Router de IA desacoplado (`app/ai_router.py`): orden `gemini-3.8-flash` (Google) → `qwen/qwen3.8-27b` (Groq) → `gemini-3.6-flash` (Google), con *circuit breaker*, *backoff* con *jitter*, reparación acotada de JSON y validación Pydantic (`AIAnalysisContract`).
  - Agente con herramientas tipadas (`app/agent.py`): `consultar_reportes`, `obtener_reporte`, `clasificar_evidencia` y `proponer_actualizacion_critica`, gobernado por 4 límites efectivos (iteraciones, tokens, *timeout* por herramienta y aprobación humana en `pending_approvals`).
  - Observabilidad protegida (`app/observability.py`): registro de trazas sanitizadas en tabla `ai_traces`, cálculo de latencias `P50`/`P90` y costo estimado en USD, accesible únicamente con cabecera `X-Admin-Token`.
- **Base de datos (`db`, PostgreSQL 17 Alpine)**:
  - Consultas SQL directas parametrizadas e índices B-Tree + fórmula Haversine espacial (sin RAG ni dependencia de PostGIS).

## Flujo Vertical Ciudadano
1. El ciudadano ingresa descripción, fotografía (y nota de voz opcional) y coordenadas GPS o punto en el mapa de Cali.
2. El backend valida seguridad, elimina EXIF, persiste el reporte en PostgreSQL y ejecuta clasificación multimodal mediante el router resiliente.
3. Si algún proveedor responde válidamente, el reporte pasa a `ANALYZED_PENDING_CONFIRMATION`; si todos fallan, permanece seguro en `PENDING_ANALYSIS` sin exponer fallos internos.
4. El ciudadano revisa la sugerencia de la IA y confirma o edita la categoría/severidad (`PATCH /api/reports/{id}/confirm`), pasando a `CONFIRMED`.
5. Cualquier ciudadano consulta el estado por código de radicado (`CIV-2026-...`), y los operadores gestionan trazas y aprobaciones humanas en la zona protegida.
