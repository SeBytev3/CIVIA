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

1. Copia `.env.example` como `.env` en la raíz del proyecto, genera localmente `ADMIN_TOKEN` con `secrets.token_urlsafe(32)` y completa las claves API (nunca imprimas el secreto en logs ni subas `.env` a Git):
   ```powershell
   Copy-Item .env.example .env
   # Procedimiento estándar: generar ADMIN_TOKEN con CSPRNG (sin imprimirlo en consola):
   python -c "import pathlib, re, secrets; p=pathlib.Path('.env'); p.write_text(re.sub(r'(?m)^ADMIN_TOKEN=.*$', f'ADMIN_TOKEN={secrets.token_urlsafe(32)}', p.read_text()))"
   # Alternativamente, .\scripts\run.ps1 (PowerShell) o ./run.sh (Bash) generan ADMIN_TOKEN con CSPRNG automáticamente si está vacío.
   ```
   > **Política de `ADMIN_TOKEN`:** No existe ninguna credencial predeterminada ni ruta de demostración en desarrollo o producción. El servidor exige por defecto el formato URL-safe base64 de `secrets.token_urlsafe(32)` (`>= 32` caracteres, `>= 12` caracteres únicos, sin secuencias, repeticiones ni términos contextuales del proyecto/rol/año/Demo/Test). Si un gestor externo de secretos requiere caracteres fuera de base64url, puede declararse explícitamente `ADMIN_TOKEN_ALLOW_CUSTOM_FORMAT=true` manteniendo todas las demás restricciones; ten en cuenta que ningún filtro sobre cadenas puede demostrar matemáticamente la entropía criptográfica de un valor arbitrario.
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
| `ADMIN_TOKEN` | Credencial administrativa obligatoria generada con CSPRNG (`secrets.token_urlsafe(32)`) por instalación para observabilidad y operaciones administrativas (`X-Admin-Token`) | *(sin valor por defecto; falla al iniciar si falta o presenta patrones predecibles)* |

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

## Orquestador Autónomo de Desarrollo y Auditoría (CIVIA Autopilot)

CIVIA incluye un sistema de orquestación autónomo que elimina la intermediación manual del desarrollador entre **Antigravity CLI (`agy`)** con Gemini 3.8 Flash High como desarrollador y **Codex CLI (`codex exec`)** como auditor independiente.

### 1. Iniciar con un único comando
El usuario puede lanzar el flujo autónomo con una sola línea en PowerShell 7:

```powershell
pwsh -File scripts/civia-autopilot.ps1
```

El orquestador coordina automáticamente el ciclo:
1. Lectura de memoria persistente (`PROJECT_SPEC.md`, `DEVELOPER.md`, `AUDITOR.md`, `ACCEPTANCE.md`).
2. Entrega de contexto y prompts a Antigravity CLI.
3. Ejecución de pruebas automatizadas deterministas (`pytest`).
4. Generación de checkpoint commit en Git si las pruebas básicas pasan.
5. Creación de un **Git worktree congelado y aislado** para auditoría.
6. Invocación de Codex CLI en modo no interactivo de solo lectura (`--sandbox read-only`).
7. Validación de informe estructurado JSON (`PASS`, `FAIL`, `PARCIAL`).
8. Cierre de hallazgos y avance o reintento de ciclo con realimentación contextual.

### 2. Opciones y Modos de Ejecución
- **Modo Simulación determinista (sin consumir tokens ni requerir CLIs externos):**
  ```powershell
  pwsh -File scripts/civia-autopilot.ps1 -Simulate
  ```
- **Diagnóstico de Preflight del entorno:**
  ```powershell
  pwsh -File scripts/civia-autopilot.ps1 -PreflightOnly
  ```
- **Fijar bloque, hallazgo o límite de ciclos:**
  ```powershell
  pwsh -File scripts/civia-autopilot.ps1 -Block G2.1 -Finding M-03 -MaxCycles 3
  ```
- **Reiniciar memoria de estado:**
  ```powershell
  pwsh -File scripts/civia-autopilot.ps1 -ResetState
  ```

### 3. Suite de Verificación del Orquestador (11 escenarios)
Para comprobar los 11 escenarios de fallo, recuperación, límites de ciclos, detección de estancamiento y guardrails de seguridad del orquestador:

```powershell
python -m pytest orchestrator/tests/test_orchestrator_scenarios.py -v
```

### 4. Políticas de Seguridad y Guardrails
- **Bases de datos desechables:** Ninguna prueba se ejecuta sobre la base habitual (`civia`).
- **Aislamiento en Git Worktrees:** Codex jamás muta el código del árbol de trabajo de desarrollo.
- **Sin credenciales en logs:** Sanitización y redacción automática de tokens, llaves API y contraseñas.
- **Límites de autonomía:** Bloqueo terminante de `git push`, merge hacia `main` y sentencias destructivas. Máximo de 5 ciclos por hallazgo y detección de ciclos sin progreso (*zero diff*).
- **Reportes:** Registro persistente en `orchestrator/state.json`, `orchestrator/reports/execution_report.md` y `execution_report.json`.

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
