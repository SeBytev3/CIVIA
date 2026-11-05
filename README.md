# CIVIA — Plataforma de Reportes Ciudadanos Asistidos por IA (Cali y Valle del Cauca)

Equipo: **Stefania Córdoba y Sebastian Espinosa** · Universidad Cooperativa de Colombia · Ingeniería de Aplicaciones con IA (Momento 2).

CIVIA es una aplicación web progresiva (PWA) conectada a una API FastAPI, PostgreSQL 17 y un sistema agéntico resiliente multimodal (`Gemini` → `Groq` → `Gemini`) para registrar, analizar, confirmar y gestionar reportes ciudadanos viales y ambientales (**Huecos**, **Basuras**, **Tala arbórea** y **Quemas**).

---

## Requisitos del sistema
- **Sistema Operativo:** Windows 11 (64-bit) con soporte para virtualización habilitado en BIOS/UEFI.
- **Herramientas base del host:**
  - **Git para Windows** (v2.40+).
  - **Docker Desktop** (v4.30+) con el backend **WSL2** activo (`wsl --status` en ejecución).
- **Recursos mínimos recomendados:**
  - 4 GB de memoria RAM libre asignada a Docker/WSL2.
  - 10 GB de espacio libre en disco para imágenes, volúmenes de PostgreSQL y almacenamiento local de fotos.
- **Aislamiento absoluto:** **No se requiere** instalar Node.js, npm ni Python globalmente en el computador evaluador. Toda la compilación, dependencias y ejecución ocurren estrictamente dentro de los contenedores Docker oficiales (`node:22-alpine`, `python:3.13-slim`, `postgres:17-alpine`, `nginx:1.27-alpine`).
- **Claves API de Inteligencia Artificial (opcionales para el arranque y pruebas sintéticas, requeridas para análisis multimodal en vivo):**
  - `GOOGLE_API_KEY_PRIMARY` (Google AI Studio - Gemini).
  - `GOOGLE_API_KEY_SECONDARY` (Google AI Studio - segundo modelo Gemini de respaldo).
  - `GROQ_API_KEY` (Groq Cloud - proveedor independiente Qwen / Whisper).

---

## Arranque desde un clon limpio en un comando

> [!IMPORTANT]
> **Rama de entrega aprobada:** La versión auditada y aprobada por Codex (G2.1.8, contratos F1–F8) se encuentra en la rama **`fix/auditoria-final`** (commit `cf48e71` y su cierre documental). Hasta que se efectúe la fusión formal en `main`, asegúrate de hacer checkout a esta rama tras clonar.

Abre PowerShell en Windows 11 y ejecuta:

```powershell
# 1. Clonar el repositorio
git clone https://github.com/SeBytev3/CIVIA.git
cd CIVIA

# 2. Situarse en la rama aprobada por auditoria
git checkout fix/auditoria-final

# 3. Preparar el entorno e iniciar los servicios
# (El script genera automaticamente un ADMIN_TOKEN unico y robusto con CSPRNG si no existe)
.\scripts\run.ps1
```

*(En entornos basados en Unix / macOS / WSL2 directo, el equivalente es `./run.sh`).*

### Procedimiento manual equivalente (paso a paso)

Si prefieres no usar los scripts automáticos:

1. **Copiar plantilla de configuración:**
   ```powershell
   Copy-Item .env.example .env
   ```
2. **Generar credencial administrativa segura (`ADMIN_TOKEN`):**
   ```powershell
   python -c "import pathlib, re, secrets; p=pathlib.Path('.env'); p.write_text(re.sub(r'(?m)^ADMIN_TOKEN=.*$', f'ADMIN_TOKEN={secrets.token_urlsafe(32)}', p.read_text()))"
   ```
   > **Política de `ADMIN_TOKEN`:** No existe ninguna credencial predeterminada ni modo demo predecible. El sistema exige una cadena generada por CSPRNG (`secrets.token_urlsafe(32)`, `>= 32` caracteres, `>= 12` caracteres únicos, sin secuencias ni términos contextuales como "demo", "admin", "test" o "2026"). Si falta o es débil, el backend falla inmediatamente al iniciar (*fail-closed*).
3. **Levantar los contenedores:**
   ```powershell
   docker compose up --build -d
   ```
4. **Inicialización automática:** Al arrancar, el contenedor `api` aplica de forma idempotente las migraciones SQL (`backend/migrations/001_initial_schema.sql` y `002_add_operation_records.sql`) y siembra 10 reportes sintéticos de prueba en Cali (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`, con `is_synthetic = true`).

---

### URLs de los servicios

| Servicio | URL | Descripción |
|---|---|---|
| **PWA Ciudadana** | http://localhost:5173 | Interfaz React 19 + TypeScript + Vite + Leaflet (mapa interactivo de Cali) servida por Nginx |
| **API Backend** | http://localhost:8000 | FastAPI REST API con validación estricta y seguridad por capas |
| **Salud del Backend** | http://localhost:8000/health | Verificación JSON de conectividad a PostgreSQL, migraciones listas y catálogo de modelos |
| **Documentación OpenAPI** | http://localhost:8000/docs | Documentación Swagger interactiva de todos los endpoints REST públicos y administrativos |

---

## Variables de entorno y configuración (`.env.example`)

Todas las variables se configuran en el archivo `.env` en la raíz del proyecto. **NUNCA subas el archivo `.env` a Git ni compartas tus claves privadas.**

| Variable | Descripción | Valor por defecto / Requisito |
|---|---|---|
| `POSTGRES_DB` | Nombre de la base de datos PostgreSQL | `civia` |
| `POSTGRES_USER` | Usuario administrador de la base de datos | `civia` |
| `POSTGRES_PASSWORD` | Contraseña local de la base de datos | `local_dev_change_me` *(debe coincidir con DATABASE_URL)* |
| `DATABASE_URL` | Cadena de conexión SQL directa para el backend | `postgresql://civia:local_dev_change_me@db:5432/civia` |
| `ADMIN_TOKEN` | Token secreto obligatorio para observabilidad y endpoints `/api/admin/*` | Generado con CSPRNG (`secrets.token_urlsafe(32)`) por `.\scripts\run.ps1` |
| `GOOGLE_API_KEY_PRIMARY` | Clave Google AI Studio para modelo primario | Requerida para análisis multimodal real (Gemini) |
| `GOOGLE_API_KEY_SECONDARY` | Clave Google AI Studio para modelo terciario | Opcional (respaldo independiente de Gemini) |
| `GROQ_API_KEY` | Clave Groq Cloud para modelo de respaldo independiente | Requerida para fallback real (Qwen 2.5 27B / Whisper) |
| `AI_PRIMARY_MODEL` | Modelo primario multimodal | `gemini-3.8-flash` |
| `AI_FALLBACK_MODEL` | Modelo de respaldo independiente | `qwen/qwen3.8-27b` |
| `AI_TERTIARY_MODEL` | Tercer modelo alternativo | `gemini-3.6-flash` |
| `AI_TIMEOUT_SECONDS` | Tiempo límite por llamada a proveedores de IA | `15` segundos |
| `AI_MAX_RETRIES` | Reintentos acotados con backoff exponencial y jitter | `2` reintentos |
| `AGENT_MAX_ITERATIONS` | Límite #1: máximo de turnos del agente por consulta | `5` iteraciones |
| `AGENT_MAX_TOKENS` | Límite #2: presupuesto estricto de tokens por sesión | `6000` tokens |
| `FALLA_FORZADA` | Inyección de fallas en caliente (`429`, `503`, `TIMEOUT`, `INVALID_JSON`, `TOTAL`) | Vacío en operación normal |
| `AUTO_SEED_SYNTHETIC` | Creación automática de 10 reportes sintéticos de prueba | `true` |

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

## Mantenimiento, diagnóstico y solución de problemas en Windows 11

### 1. Comandos de ciclo de vida seguro (No destructivos)

- **Verificar estado de los contenedores:**
  ```powershell
  docker compose ps
  ```
- **Monitorear registros (logs) en tiempo real:**
  ```powershell
  # Logs combinados de todos los servicios:
  docker compose logs -f

  # Logs específicos del backend API o de la base de datos:
  docker compose logs -f api
  docker compose logs -f db
  docker compose logs -f frontend
  ```
- **Reiniciar servicios conservando los datos:**
  ```powershell
  # Reinicio directo de contenedores:
  docker compose restart

  # O detención y reanudación segura (los datos en volúmenes persisten intactos):
  docker compose down
  docker compose up -d
  ```
- **Reconstruir imágenes tras cambios de código:**
  ```powershell
  docker compose build --no-cache
  docker compose up -d
  ```

---

### 2. Comandos destructivos (Uso exclusivo para reinicio total)

> [!CAUTION]
> **Pérdida irreversible de datos locales:** El comando `docker compose down -v` elimina por completo los volúmenes de almacenamiento (`civia_postgres` y `civia_uploads`), borrando todos los reportes, fotos y trazabilidad acumulados. **NO utilices este comando como solución rutinaria.**
> ```powershell
> # ÚNICAMENTE si deseas resetear el sistema a su estado inicial de fábrica:
> docker compose down -v
> docker compose up --build -d
> ```

---

### 3. Solución de problemas frecuentes en Windows 11

1. **Conflicto de puertos (`5173`, `8000` o `5432` ocupados):**
   Si otro proceso o una instancia previa está escuchando en los puertos requeridos, identifícalo con:
   ```powershell
   Get-NetTCPConnection -LocalPort 5173, 8000, 5432 -ErrorAction SilentlyContinue | Format-Table -Property LocalPort, OwningProcess, State
   # O mediante comando clásico:
   netstat -ano | findstr ":5173 :8000 :5432"
   ```
   Detén la instancia anterior con `docker compose down` o termina el proceso conflictivo antes de iniciar CIVIA.

2. **Docker Desktop o motor WSL2 no responden:**
   - Comprueba el estado de WSL2:
     ```powershell
     wsl --status
     ```
   - Si el subsistema está bloqueado, apágalo limpiamente y reinícialo:
     ```powershell
     wsl --shutdown
     ```
   - Abre Docker Desktop y espera a que el icono en la bandeja del sistema indique `Engine running`.

3. **Error al validar configuración de entorno (`.env`):**
   Comprueba que Docker Compose interprete las variables correctamente sin errores de sintaxis:
   ```powershell
   docker compose config
   ```
   Si muestra advertencias sobre `ADMIN_TOKEN`, asegúrate de que `.env` contenga una clave no vacía de al menos 32 caracteres generada por `.\scripts\run.ps1`.

4. **Política de ejecución restringida de scripts en PowerShell (`PSSecurityException`):**
   Si Windows 11 bloquea la ejecución de `.\scripts\run.ps1`, ejecuta:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
   # O utiliza directamente:
   docker compose up --build -d
   ```

5. **Límite de cuota o latencia en proveedores gratuitos de IA:**
   Si Google AI Studio o Groq devuelven `429 (Too Many Requests)` durante pruebas continuas, el sistema conmuta automáticamente al siguiente nivel de la cadena (`Gemini` → `Groq` → `Gemini`). También puedes ejecutar las suites en modo determinista local sin consumir cuota:
   ```powershell
   docker compose exec -T api python eval/evaluar.py --mode deterministic
   ```

---

## Guía detallada para clonación e instalación en otro computador

Para una guía paso a paso completa con capturas conceptuales, checklist de sustentación académica para el profesor y protocolo de verificación reproducible en un segundo computador limpio, consulta:
- **[`docs/guia_instalacion_otro_pc.md`](docs/guia_instalacion_otro_pc.md)**

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
