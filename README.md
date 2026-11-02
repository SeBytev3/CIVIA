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

1. Copia `.env.example` como `.env` en la raíz del proyecto, genera un `ADMIN_TOKEN` único robusto (`>= 24` caracteres) y completa las claves API (nunca subas `.env` a Git):
   ```powershell
   Copy-Item .env.example .env
   # Si usas .\scripts\run.ps1 o ./run.sh, ADMIN_TOKEN se genera automáticamente si está vacío en .env
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
| `ADMIN_TOKEN` | Secreto robusto obligatorio (`>= 24` caracteres) generado por instalación para observabilidad y operaciones administrativas (`X-Admin-Token`) | *(sin valor por defecto; falla al iniciar si falta o es débil)* |

---

## Ejecución de pruebas automatizadas y suite de evaluación

### 1. Pruebas automatizadas (`pytest`)
Con los contenedores en ejecución, ejecuta la suite de 20 pruebas automatizadas (salud, CRUD, validación de archivos/EXIF/GPS/PII, *rate limiting*, resiliencia `429`/`503`/`TIMEOUT`/`INVALID_JSON`/`GROQ_FAIL`/`TOTAL`, los 4 límites del agente y prueba E2E entre contenedores):

```powershell
docker compose exec -T api pytest -v
```

### 2. Suite de evaluación formal (6 casos dorados SQL + 15 consultas representativas)
Para ejecutar la evaluación formal y regenerar `eval/resultados/reporte_evaluacion.json` y `eval/resultados/reporte_evaluacion.md`:

```powershell
# Verificación determinista rápida (SQL dorado + matriz de resiliencia y guardrails):
docker compose exec -T api python eval/evaluar.py --mode deterministic

# Suite completa de 15 consultas con llamadas en vivo al router Gemini -> Groq -> Gemini:
docker compose exec -T api python eval/evaluar.py --mode all --pause 1.5
```

### 3.Cómo simular fallos de proveedores (`FALLA_FORZADA`)
Puedes inyectar fallos controlados en caliente desde la **Consola de Observabilidad y Resiliencia** en http://localhost:5173 (autenticando con `ADMIN_TOKEN`), o mediante API:

```powershell
# Simular HTTP 429 en proveedor primario (conmuta automáticamente a Groq):
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/admin/fault-injection" `
  -Headers @{"X-Admin-Token"="$env:ADMIN_TOKEN"; "Content-Type"="application/json"} `
  -Body '{"mode":"429","reset_circuits":true}'

# Simular caída total de los 3 proveedores (guarda reportes en PENDING_ANALYSIS):
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/admin/fault-injection" `
  -Headers @{"X-Admin-Token"="$env:ADMIN_TOKEN"; "Content-Type"="application/json"} `
  -Body '{"mode":"TOTAL","reset_circuits":true}'

# Restaurar operación normal:
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/admin/fault-injection" `
  -Headers @{"X-Admin-Token"="$env:ADMIN_TOKEN"; "Content-Type"="application/json"} `
  -Body '{"mode":"NONE","reset_circuits":true}'
```

---

## Reset de datos, mantenimiento y solución de problemas en Windows 11

- **Detener conservando los datos**: `docker compose down`
- **Reiniciar desde cero (elimina volúmenes de BD y fotos)**: `docker compose down -v`
- **Restablecer únicamente los reportes sintéticos de demostración (solo en BD de prueba `*_test` / `*_eval`)**:
  ```powershell
  Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/admin/seed?force_reset=true" -Headers @{"X-Admin-Token"="$env:ADMIN_TOKEN"}
  ```
- **Solución de problemas frecuentes en Windows 11**:
  1. *Docker Desktop no responde*: Asegúrate de que el motor WSL2 esté activo (`wsl --status`) y Docker Desktop muestre `Engine running`.
  2. *Puerto `5173` o `8000` ocupado*: Comprueba con `netstat -ano | findstr :5173` o `:8000` que otra instancia previa no esté escuchando y ejecuta `docker compose down` antes de levantar.
  3. *Política de ejecución de PowerShell al usar `.\scripts\run.ps1`*: Puedes ejecutar directamente `docker compose up --build -d` o `powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1`.
  4. *Cuotas de capa gratuita (Google AI Studio / Groq)*: Si alguna clave gratuita alcanza su tope por minuto (RPM), espera 60 segundos o usa `--mode deterministic` en `eval/evaluar.py`.

---

## Arquitectura de Resiliencia, Agente y Documentación del Proyecto

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

### Documentación de referencia
- [`docs/arquitectura.md`](docs/arquitectura.md): Arquitectura C4, flujo vertical y esquema de datos.
- [`docs/decisiones.md`](docs/decisiones.md): Justificación de SQL vs. NO RAG, diseño del agente y métricas reales (`P50`, `P90`, tokens, costos y precisión).
- [`docs/checklist_rubrica.md`](docs/checklist_rubrica.md): Mapeo verificable contra los 5 criterios de evaluación del Momento 2.
- [`docs/guion_sustentacion.md`](docs/guion_sustentacion.md): Guion de sustentación en vivo (6 minutos de demo + 3 minutos de preguntas).
- [`eval/plantilla_usabilidad.md`](eval/plantilla_usabilidad.md): Protocolo de evaluación de usabilidad con usuario externo (3 tareas).
- [`docs/estado.md`](docs/estado.md): Registro de avance y pruebas por fase.
