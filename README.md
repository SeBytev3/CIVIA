# CIVIA — Plataforma de Reportes Ciudadanos Asistidos por IA (Cali y Valle del Cauca)

Equipo: **Stefania Córdoba y Sebastian Espinosa** · Universidad Cooperativa de Colombia · Ingeniería de Aplicaciones con IA (Momento 2).

CIVIA es una aplicación web progresiva (PWA) conectada a una API FastAPI, PostgreSQL 17 y un sistema agéntico resiliente multimodal (`Gemini` → `Groq` → `Gemini`) para registrar, analizar, confirmar y gestionar reportes ciudadanos viales y ambientales (**Huecos**, **Basuras**, **Tala arbórea** y **Quemas**).

---

## Requisitos
- **Docker Desktop** con Docker Compose v2 (en Windows 11, con backend WSL2 activo).
- **No se requiere** instalar Node.js ni Python globalmente en el computador del evaluador (toda la compilación y ejecución ocurre dentro de los contenedores).
- Tres claves API en el archivo `.env` local:
  - `GOOGLE_API_KEY_PRIMARY`
  - `GOOGLE_API_KEY_SECONDARY`
  - `GROQ_API_KEY`

---

## Arranque desde un clon limpio en un comando

1. Copia `.env.example` como `.env` en la raíz del proyecto y completa las claves API (nunca subas `.env` a Git):
   ```powershell
   Copy-Item .env.example .env
   ```
2. Levanta todos los servicios (`db`, `api` y `frontend` PWA) con un solo comando:
   ```powershell
   docker compose up --build -d
   ```
   *(También puedes usar `.\scripts\run.ps1` en PowerShell o `./run.sh` en Bash).*
3. Al iniciar, el backend aplica automáticamente las migraciones SQL idempotentes (`backend/migrations/001_initial_schema.sql`) y carga 10 reportes sintéticos identificados de demostración en Cali (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`, marcados con `is_synthetic = true`).

### URLs de la aplicación
- **Interfaz Ciudadana PWA (React + TypeScript + Vite + Leaflet)**: http://localhost:5173
- **Salud del Backend API**: http://localhost:8000/health
- **Documentación interactiva OpenAPI**: http://localhost:8000/docs

---

## Variables de entorno (`.env.example`)

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `POSTGRES_DB` | Base de datos PostgreSQL | `civia` |
| `POSTGRES_USER` | Usuario de PostgreSQL | `civia` |
| `POSTGRES_PASSWORD` | Contraseña local de BD | `local_dev_change_me` |
| `DATABASE_URL` | Cadena de conexión SQL | `postgresql://civia:local_dev_change_me@db:5432/civia` |
| `GOOGLE_API_KEY_PRIMARY` | Clave Google AI Studio primaria | *(requerida para IA real)* |
| `GOOGLE_API_KEY_SECONDARY` | Clave Google AI Studio secundaria | *(opcional / respaldo)* |
| `GROQ_API_KEY` | Clave proveedor independiente Groq | *(requerida para fallback real)* |
| `AI_PRIMARY_MODEL` | Modelo primario multimodal | `gemini-3.8-flash` |
| `AI_FALLBACK_MODEL` | Modelo de respaldo independiente (Groq) | `qwen/qwen3.8-27b` |
| `AI_TERTIARY_MODEL` | Tercer modelo alternativo (Google) | `gemini-3.6-flash` |
| `AI_TIMEOUT_SECONDS` | Timeout de operación IA | `15` |
| `AI_MAX_RETRIES` | Reintentos acotados por proveedor | `2` |
| `AGENT_MAX_ITERATIONS` | Límite #1: máximo de vueltas del agente | `5` |
| `AGENT_MAX_TOKENS` | Límite #2: presupuesto máximo de tokens | `6000` |
| `FALLA_FORZADA` | Simulación de fallos (`429`, `503`, `TIMEOUT`, `INVALID_JSON`, `GROQ_FAIL`, `TOTAL`) | *(vacío = operación normal)* |
| `AUTO_SEED_SYNTHETIC` | Semilla automática de datos sintéticos identificados | `true` |
| `ADMIN_TOKEN` | Token para zona de observabilidad protegida (`X-Admin-Token`) | `civia-admin-demo-2026` |

---

## Ejecución de pruebas automatizadas

Con los contenedores en ejecución, ejecuta la suite completa de pruebas unitarias, de integración, seguridad, resiliencia (`429`, `503`, `TIMEOUT`, `INVALID_JSON`, `GROQ_FAIL`, `TOTAL`) y los 4 límites del agente:

```powershell
docker compose exec -T api pytest -v
```

Para comprobar el frontend servible desde otro contenedor dentro de la red de Docker:

```powershell
docker compose exec -T frontend wget -q -O - http://127.0.0.1:80/health
```

---

## Reset de datos y mantenimiento

- **Detener conservando los datos**: `docker compose down`
- **Reiniciar desde cero (elimina volúmenes de BD y fotos)**: `docker compose down -v`
- **Restablecer únicamente los reportes sintéticos de demostración**:
  ```powershell
  Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/admin/seed?force_reset=true" -Headers @{"X-Admin-Token"="civia-admin-demo-2026"}
  ```

---

## Arquitectura de Resiliencia y Agente

1. **Flujo vertical ciudadano**:
   - Captura de descripción, fotografía (`JPEG`/`PNG`/`WEBP` <= 5 MB, >= 32x32 px, sin metadatos EXIF), nota de voz opcional (<= 60s / <= 5 MB) y coordenadas GPS o selección en mapa de Cali.
   - Almacenamiento en PostgreSQL + clasificación multimodal con contrato estricto `AIAnalysisContract`.
   - Separación explícita entre diagnóstico sugerido por IA (`ai_category` / `ai_severity`) y confirmación o corrección humana (`final_category` / `final_severity`, `human_confirmed`).
2. **Router resiliente de 3 niveles (`Gemini` → `Groq` → `Gemini`)**:
   - Reintentos acotados con *backoff* exponencial + *jitter*, *circuit breaker* por proveedor/modelo y reparación acotada de JSON inválido.
   - Si fallan todos los proveedores (`FALLA_FORZADA=TOTAL`), el reporte se conserva en `PENDING_ANALYSIS` sin exponer *tracebacks*, errores HTTP ni nombres de proveedores al ciudadano.
3. **Agente con herramientas tipadas y 4 límites verificables**:
   - Herramientas: `consultar_reportes`, `obtener_reporte`, `clasificar_evidencia` y `proponer_actualizacion_critica`.
   - Cuatro límites: (1) máximo de iteraciones, (2) presupuesto de tokens, (3) *timeout* por herramienta y global, y (4) confirmación humana obligatoria en `pending_approvals` para cualquier escritura crítica (la IA jamás modifica la tabla `reports` directamente).

Referencias adicionales: `docs/arquitectura.md`, `docs/decisiones.md`, `docs/estado.md`.
