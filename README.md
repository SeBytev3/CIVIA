# CIVIA — Despliegue para Profesores y Agentes de IA

Equipo: **Stefania Córdoba y Sebastian Espinosa** · Universidad Cooperativa de Colombia · Ingeniería de Aplicaciones con IA (Momento 2).

CIVIA (Ciudad Inteligente y Vigilancia Ambiental) es una plataforma integral para la captura, georreferenciación, diagnóstico asistido por IA, confirmación humana y seguimiento de incidentes urbanos y ambientales en Santiago de Cali y el Valle del Cauca (**Huecos**, **Basuras**, **Tala arbórea** y **Quemas**).

La arquitectura combina una Aplicación Web Progresiva (PWA) moderna en React 19, una API REST FastAPI en Python 3.13 con validación estricta, persistencia transaccional en PostgreSQL 17 y un enrutador multimodal resiliente de tres niveles (`Gemini` → `Groq` → `Gemini`).

---

## 🚀 Despliegue Rápido y Autónomo para Evaluadores y Agentes de IA

Si eres un profesor evaluador o estás utilizando un agente autónomo de IA (**Claude Code, Gemini CLI, Antigravity, ChatGPT, Codex**), copia y pega el siguiente prompt:

> **Prompt de evaluación para agentes autónomos:**  
> *"Clona el repositorio oficial `https://github.com/SeBytev3/CIVIA.git` en la rama predeterminada `main`. Ejecuta `.\scripts\run.ps1` (en Windows 11 PowerShell) o `./scripts/run.sh` (en Linux/macOS). Verifica que `http://localhost:5173` responda con código 200 y que `http://localhost:8000/health` reporte status 'ok' con PostgreSQL conectado y esquema listo. Luego, accede a la aplicación web, toma una fotografía con la cámara o selecciona una muestra de prueba, ingresa una descripción y coordenadas en Cali, y verifica la persistencia y consulta del radicado en PostgreSQL tras recargar."*

### Despliegue en un solo comando:

```powershell
# 1. Clonar el repositorio oficial (rama predeterminada: main)
git clone https://github.com/SeBytev3/CIVIA.git
cd CIVIA

# 2. Iniciar todos los servicios (genera automáticamente credenciales seguras si no existen)
.\scripts\run.ps1
```

*(En Linux / macOS / WSL: `chmod +x ./scripts/run.sh && ./scripts/run.sh`)*

---

## Requisitos del sistema

- **Sistema Operativo:** Windows 11 (64-bit) con soporte para virtualización habilitado en BIOS/UEFI (o Linux x86_64 / macOS).
- **Herramientas base del host:**
  - **Git** (v2.40+).
  - **Docker Desktop** (v4.30+) con el backend **WSL2** activo en Windows (o Docker Engine 24+ con Docker Compose v2 en Linux).
- **Recursos mínimos recomendados:**
  - 4 GB de memoria RAM libre asignada a Docker/WSL2.
  - 10 GB de espacio libre en disco para imágenes, volúmenes de PostgreSQL y almacenamiento local de fotos.
  - Puertos de red libres en el host: `8000` (API Backend) y `5173` (Frontend PWA).
- **Aislamiento absoluto:** **No se requiere** instalar Node.js, npm ni Python globalmente en el computador evaluador. Toda la compilación, dependencias y ejecución ocurren estrictamente dentro de los contenedores Docker oficiales (`node:22-alpine`, `python:3.13-slim`, `postgres:17-alpine`, `nginx:1.27-alpine`).
- **Claves API de Inteligencia Artificial (OPCIONALES):**
  - **El sistema funciona 100% en modo local (MVP) sin requerir ninguna clave de API externa.** La captura de cámara, subida de fotos, georreferenciación en Cali, radicación, persistencia en PostgreSQL 17, catálogo de evidencias fotorrealistas y la suite completa de 154 pruebas herméticas no requieren conexión externa.
  - Si se proporcionan claves en `.env` (`GOOGLE_API_KEY_PRIMARY`, `GOOGLE_API_KEY_SECONDARY`, `GROQ_API_KEY`), el agente multimodal y el análisis automático en vivo se activan automáticamente.

---

## Arranque desde un clon limpio en un comando

> [!IMPORTANT]
> **Rama oficial de entrega:** La versión final, remediada y auditada se encuentra publicada en la rama principal y predeterminada **`main`**.

Abre PowerShell en Windows 11 y ejecuta:

```powershell
# 1. Clonar el repositorio
git clone https://github.com/SeBytev3/CIVIA.git
cd CIVIA

# 2. Iniciar los servicios
.\scripts\run.ps1
```

*(En entornos basados en Unix / macOS / WSL2 directo: `./scripts/run.sh`).*

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
| **PWA Ciudadana** | `http://localhost:5173` | Interfaz React 19 + TypeScript + Vite + Leaflet (mapa interactivo de Cali) servida por Nginx |
| **API Backend** | `http://localhost:8000` | FastAPI REST API con validación estricta y seguridad por capas |
| **Salud del Backend** | `http://localhost:8000/health` | Verificación JSON de conectividad a PostgreSQL, migraciones listas y catálogo de modelos |
| **Documentación OpenAPI** | `http://localhost:8000/docs` | Documentación Swagger interactiva de todos los endpoints REST públicos y administrativos |

---

## Procedimiento de Prueba Interactiva para el Evaluador

1. **Acceder a la aplicación:** Abre tu navegador web en `http://localhost:5173`.
2. **Crear un nuevo reporte:**
   - Navega a la pestaña **"+ Nuevo Reporte"**.
   - **Fotografía:** Puedes activar la cámara web con un clic y capturar una foto real, subir una imagen JPEG/PNG/WEBP desde tu explorador de archivos, o seleccionar una de las muestras sintéticas fotorrealistas de demostración.
   - **Ubicación:** Haz clic en el mapa de Santiago de Cali para posicionar el incidente, o usa el botón *"Usar mi ubicación actual"*.
   - **Descripción y título:** Ingresa el detalle del problema vial o ambiental.
   - Pulsa **"Enviar Reporte Ciudadano"**.
3. **Verificación de radicado:**
   - La plataforma confirmará el reporte y asignará un código único de radicado (ej. `CIV-2026-XXXX`).
   - Se abrirá la vista de detalle con la foto servida de forma inmutable, escalada en `objectFit: contain` sin recortes.
4. **Consultar y verificar persistencia:**
   - Ve a la pestaña **"Seguimiento Radicado"** e ingresa el código generado.
   - Recarga el navegador (`Ctrl + F5`) para comprobar que los datos y la evidencia fotográfica persisten íntegramente en PostgreSQL 17.
5. **Explorar el catálogo sintético inicial:**
   - En la pestaña **"Mapa y Reportes"**, examina los 10 reportes precargados (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`).
   - Cada reporte de prueba cuenta con su distintivo visible de procedencia ética: *"ℹ Imagen generada con IA · Simulación"* y almacenamiento inmutable versionado por contenido.

---

## Variables de entorno y configuración (`.env.example`)

Todas las variables se configuran en el archivo `.env` en la raíz del proyecto. **NUNCA subas el archivo `.env` a Git ni compartas tus claves privadas.**

| Variable | Descripción | Valor por defecto / Requisito |
|---|---|---|
| `POSTGRES_DB` | Nombre de la base de datos PostgreSQL | `civia` |
| `POSTGRES_USER` | Usuario administrador de la base de datos | `civia` |
| `POSTGRES_PASSWORD` | Contraseña local de la base de datos | Generada aleatoriamente por `run.ps1` / `run.sh` |
| `DATABASE_URL` | Cadena de conexión SQL directa para el backend | `postgresql://civia:<password>@db:5432/civia` |
| `ADMIN_TOKEN` | Token secreto obligatorio para observabilidad y endpoints `/api/admin/*` | Generado con CSPRNG (`secrets.token_urlsafe(32)`) |
| `GOOGLE_API_KEY_PRIMARY` | Clave Google AI Studio para modelo primario | Opcional (análisis multimodal en vivo con Gemini) |
| `GOOGLE_API_KEY_SECONDARY` | Clave Google AI Studio para modelo terciario | Opcional (respaldo de Gemini) |
| `GROQ_API_KEY` | Clave Groq Cloud para modelo de respaldo independiente | Opcional (fallback con Qwen 2.5 27B / Whisper) |
| `AI_PRIMARY_MODEL` | Modelo primario multimodal | `gemini-3.8-flash` |
| `AI_FALLBACK_MODEL` | Modelo de respaldo independiente | `qwen/qwen3.8-27b` |
| `AI_TERTIARY_MODEL` | Tercer modelo alternativo | `gemini-3.5-flash-lite` |
| `AI_TIMEOUT_SECONDS` | Tiempo límite por llamada a proveedores de IA | `15` segundos |
| `AI_MAX_RETRIES` | Reintentos acotados con backoff exponencial y jitter | `2` reintentos |
| `AGENT_MAX_ITERATIONS` | Límite #1: máximo de turnos del agente por consulta | `5` iteraciones |
| `AGENT_MAX_TOKENS` | Límite #2: presupuesto estricto de tokens por sesión | `6000` tokens |
| `FALLA_FORZADA` | Inyección de fallas en caliente (`429`, `503`, `TIMEOUT`, `INVALID_JSON`, `TOTAL`) | Vacío en operación normal |
| `AUTO_SEED_SYNTHETIC` | Creación automática de 10 reportes sintéticos de prueba | `true` |

---

## Ejecución de pruebas automatizadas y suite de evaluación

### 1. Suite Hermética de Backend (`pytest`)
Ejecuta la suite hermética de 154 pruebas automáticas (contratos de seguridad F1-F8, invariantes A-L de almacenamiento inmutable, procedencia ética de servidor, ledger de auditoría, resiliencia `429`/`503`/`TIMEOUT`/`TOTAL`, y los 4 límites del agente):

```powershell
docker compose exec -T api pytest -m "not live" -v
```

*(Resultado verificado: **154 passed, 1 deselected, 0 failed**).*

### 2. Pruebas E2E de Interfaz de Usuario (Playwright)
Para ejecutar la suite de navegador de doble flujo (cámara real en vivo + muestra sintética oficial con persistencia):

```powershell
cd frontend
npm install
npm run test:e2e
```

*(Resultado verificado: **2 passed (100%)**).*

### 3. Suite de evaluación formal (6 casos dorados SQL + 15 consultas representativas)
Para ejecutar la evaluación formal y regenerar `eval/resultados/reporte_evaluacion.json` y `eval/resultados/reporte_evaluacion.md`:

```powershell
# Verificación determinista rápida (SQL dorado + matriz de resiliencia y guardrails):
docker compose exec -T api python eval/evaluar.py --mode deterministic

# Suite completa con llamadas en vivo al router Gemini -> Groq -> Gemini:
docker compose exec -T api python eval/evaluar.py --mode all --pause 1.5
```

### 4. Simulación de fallos controlados (`FALLA_FORZADA`)
Puedes inyectar fallos controlados en caliente desde la **Consola de Observabilidad y Resiliencia** en `http://localhost:5173` (autenticando con `ADMIN_TOKEN`), o mediante API:

```powershell
# Simular HTTP 429 en proveedor primario (conmuta automáticamente a Groq):
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/admin/fault-injection" `
  -Headers @{"X-Admin-Token"="$env:ADMIN_TOKEN"; "Content-Type"="application/json"} `
  -Body '{"mode":"429","reset_circuits":true}'

# Simular caída total de proveedores (guarda reportes en PENDING_ANALYSIS sin exponer errores):
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/admin/fault-injection" `
  -Headers @{"X-Admin-Token"="$env:ADMIN_TOKEN"; "Content-Type"="application/json"} `
  -Body '{"mode":"TOTAL","reset_circuits":true}'

# Restaurar operación normal:
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/admin/fault-injection" `
  -Headers @{"X-Admin-Token"="$env:ADMIN_TOKEN"; "Content-Type"="application/json"} `
  -Body '{"mode":"NONE","reset_circuits":true}'
```

---

## Mantenimiento, diagnóstico y ciclo de vida seguro

- **Verificar estado de los contenedores:**
  ```powershell
  docker compose ps
  ```
- **Monitorear registros (logs) en tiempo real:**
  ```powershell
  docker compose logs -f api
  docker compose logs -f db
  docker compose logs -f frontend
  ```
- **Reiniciar servicios conservando los datos:**
  ```powershell
  docker compose restart
  ```
- **Detener servicios sin borrar datos:**
  ```powershell
  docker compose down
  ```
  *(Los volúmenes `civia_postgres` y `civia_uploads` persisten intactos).*

---

## Arquitectura de Resiliencia y Documentación del Proyecto

1. **Flujo vertical ciudadano**: Captura de descripción, fotografía (`JPEG`/`PNG`/`WEBP` <= 5 MB, >= 32x32 px, sin metadatos EXIF), audio opcional y coordenadas GPS en Cali. Almacenamiento en PostgreSQL 17 y contrato estricto `AIAnalysisContract`.
2. **Router resiliente de 3 niveles (`Gemini` → `Groq` → `Gemini`)**: Reintentos acotados con *backoff* exponencial + *jitter*, *circuit breaker* por proveedor/modelo y reparación de JSON.
3. **Agente con herramientas tipadas y 4 límites**: `consultar_reportes`, `obtener_reporte`, `clasificar_evidencia` y `proponer_actualizacion_critica`. Límites verificables de iteraciones, tokens, timeout y aprobación humana obligatoria en `pending_approvals` (la IA jamás escribe directamente en la tabla `reports`).

### Documentación de referencia
- [`CLAUDE.md`](CLAUDE.md): Guía de ejecución autónoma para Claude Code y agentes de IA.
- [`GEMINI.md`](GEMINI.md): Guía de ejecución para modelos y agentes Gemini / Antigravity.
- [`docs/AI_DEPLOY.md`](docs/AI_DEPLOY.md): Protocolo de despliegue y auditoría asistido por IA.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): Arquitectura de despliegue local y análisis de opciones cloud.
- [`docs/guia_instalacion_otro_pc.md`](docs/guia_instalacion_otro_pc.md): Guía de instalación y sustentación para el profesor en otra máquina Windows 11 o Linux.
- [`docs/arquitectura.md`](docs/arquitectura.md): Arquitectura C4, flujo vertical y esquema de datos.
- [`docs/decisiones.md`](docs/decisiones.md): Justificación de SQL directo vs. NO RAG, diseño del agente y métricas reales.
- [`docs/checklist_rubrica.md`](docs/checklist_rubrica.md): Mapeo verificable contra los criterios de evaluación del Momento 2.
- [`docs/guion_sustentacion.md`](docs/guion_sustentacion.md): Guion de sustentación en vivo (demo + preguntas).
- [`docs/estado.md`](docs/estado.md): Registro de avance y pruebas por fase.
- [`docs/entrega_final.md`](docs/entrega_final.md): Informe oficial de entrega académica final.

---

## Estado Oficial de Despliegue en la Nube
> **DESPLIEGUE LOCAL LISTO; URL PÚBLICA PENDIENTE DE INFRAESTRUCTURA**  
> Ver análisis detallado en [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). La aplicación es 100% reproducible en local o VM mediante un solo comando, garantizando la persistencia íntegra de PostgreSQL 17 y la privacidad de las evidencias sin incurrir en costos privados ni depender de capas gratuitas efímeras.
