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

## Próxima tarea para Antigravity
- Ejecutar Fase B: migraciones SQL automáticas e idempotentes, esquema PostgreSQL de reportes y trazas de IA/auditoría, API CRUD de reportes con validación de seguridad de imágenes y coordenadas, y fixtures de prueba + tests automatizados.
