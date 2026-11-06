# Guía de Instalación en Otro Computador Windows 11 y Demostración Académica

**Proyecto:** CIVIA — Plataforma de Reportes Ciudadanos Asistidos por IA (Cali y Valle del Cauca)  
**Equipo:** Stefania Córdoba y Sebastian Espinosa  
**Asignatura:** Ingeniería de Aplicaciones con IA (Momento 2) · Universidad Cooperativa de Colombia  
**Rama principal y oficial de entrega:** `main`  
**Estado:** Release Académico Final Verificado y Aprobado

---

## 1. Requisitos del computador evaluador

Para garantizar que CIVIA se ejecute de manera fluida y reproducible en un segundo equipo independiente:

- **Sistema Operativo:** Windows 11 Home, Pro o Enterprise (64-bit, versión 22H2 o superior).
- **Virtualización de hardware:** Habilitada en BIOS/UEFI (Intel VT-x o AMD-V).
- **Memoria RAM:** Mínimo 8 GB en el sistema físico (al menos 4 GB disponibles para el subsistema WSL2 / Docker Desktop).
- **Espacio en disco:** Mínimo 10 GB libres en la unidad principal (C:) para el motor de Docker, imágenes base de Linux y volúmenes de PostgreSQL.
- **Conectividad:** Acceso a Internet durante el primer arranque para la descarga de imágenes oficiales de Docker Hub (`node:22-alpine`, `python:3.13-slim`, `postgres:17-alpine`, `nginx:1.27-alpine`).

> [!NOTE]
> **Sin dependencias globales:** **NO** es necesario instalar Node.js, npm, Python ni PostgreSQL en el sistema operativo Windows 11 del evaluador. Toda la pila de compilación, ejecución de backend, servidor web y base de datos opera de forma hermética dentro de contenedores Docker.

---

## 2. Instalación de herramientas base (Git y Docker Desktop)

Si el computador de destino es un equipo limpio sin herramientas previas:

1. **Instalar Git para Windows:**
   - Descarga el instalador oficial desde [git-scm.com/download/win](https://git-scm.com/download/win).
   - Ejecuta el instalador manteniendo las opciones recomendadas por defecto (asegúrate de que la opción *"Git from the command line and also from 3rd-party software"* esté seleccionada).
   - Abre PowerShell y comprueba:
     ```powershell
     git --version
     # Salida esperada: git version 2.4x.x...
     ```

2. **Instalar Docker Desktop con WSL2:**
   - Descarga el instalador desde [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/).
   - Durante la instalación, asegúrate de marcar la casilla **"Use WSL 2 instead of Hyper-V (recommended)"**.
   - Al finalizar, reinicia el equipo si el instalador lo solicita.

---

## 3. Configuración inicial de Docker Desktop y WSL2

1. Abre PowerShell como Administrador o usuario estándar y verifica el estado de WSL:
   ```powershell
   wsl --status
   ```
   Si WSL no está actualizado, ejecuta:
   ```powershell
   wsl --update
   ```
2. Inicia **Docker Desktop** desde el Menú Inicio de Windows.
3. En la interfaz gráfica de Docker Desktop:
   - Ve a **Settings (icono de engranaje)** → **General** → Asegúrate de que **"Use the WSL 2 based engine"** esté activado.
   - Ve a **Settings** → **Resources** → **WSL Integration** → Verifica que esté activada la integración con tu distribución predeterminada (generalmente `Ubuntu` o `docker-desktop`).
4. Espera a que el icono de Docker en la barra de tareas de Windows se ponga de color verde o azul estable (`Engine running`).
5. Comprueba en PowerShell:
   ```powershell
   docker compose version
   # Salida esperada: Docker Compose version v2.x.x...
   ```

---

## 4. Clonación del repositorio y selección de la rama aprobada

> [!IMPORTANT]
> La versión final de entrega académica se encuentra publicada y disponible directamente en la rama predeterminada **`main`** de GitHub.

Abre PowerShell y ejecuta:

```powershell
# 1. Crear o ubicarse en una carpeta de trabajo (ej. C:\Desarrollo o C:\Proyectos)
New-Item -ItemType Directory -Force -Path C:\CIVIA_EVAL | Set-Location

# 2. Clonar el repositorio público
git clone https://github.com/SeBytev3/CIVIA.git
Set-Location CIVIA

# 3. Confirmar que se encuentra en la rama main
git status
# Salida esperada: On branch main
```

---

## 5. Preparación del archivo de configuración `.env`

1. **Inicialización automática por script de arranque (Recomendado):**
   Los scripts oficiales de despliegue (`.\scripts\run.ps1` en Windows 11 o `./scripts/run.sh` en Linux/macOS) detectan si `.env` existe; si no existe, lo crean automáticamente a partir de `.env.example` y generan credenciales criptográficas seguras (incluyendo un `ADMIN_TOKEN` aleatorio de alta entropía mediante CSPRNG) sin requerir intervención manual.
2. **Preparación manual opcional (con generación criptográfica de secretos):**
   Si prefieres preparar el archivo `.env` antes de ejecutar el arranque (el script `run.ps1` lo hace automáticamente):
   ```powershell
   Copy-Item .env.example .env
   python -c "import pathlib, re, secrets; p=pathlib.Path('.env'); pw=secrets.token_hex(16); text=re.sub(r'(?m)^POSTGRES_PASSWORD=.*$', f'POSTGRES_PASSWORD={pw}', p.read_text()); text=re.sub(r'(?m)^DATABASE_URL=.*$', f'DATABASE_URL=postgresql://civia:{pw}@db:5432/civia', text); text=re.sub(r'(?m)^ADMIN_TOKEN=.*$', f'ADMIN_TOKEN={secrets.token_urlsafe(32)}', text); p.write_text(text)"
   ```
3. **Claves de Inteligencia Artificial (OPCIONALES — Solo requeridas para inferencia multimodal en vivo):**
   - **NO son necesarias para evaluar el sistema:** La captura con cámara web real, la subida de fotos, la georreferenciación, la radicación, la persistencia en PostgreSQL 17, el seguimiento, la consulta en mapa y la suite hermética de 168 pruebas automáticas operan al 100% de forma determinista y local en **Modo MVP Local** sin ninguna clave externa.
   - **Detección interactiva:** Al ejecutar `.\scripts\run.ps1` o `./scripts/run.sh`, el sistema detecta si las claves faltan. Si la terminal es interactiva, permite ingresarlas con caracteres enmascarados o pulsar Enter para continuar en Modo MVP Local.
   - **Configuración posterior sin reiniciar la base de datos:** Si desea configurar o rotar las claves después del despliegue inicial sin perder datos ni reinstalar PostgreSQL, ejecute:
     ```powershell
     .\scripts\setup_ai_keys.ps1
     ```
     *(En Linux / macOS: `./scripts/setup_ai_keys.sh`)*.  
     Este script actualiza el archivo `.env` de forma protegida y recrea únicamente el servicio de la API (`docker compose up -d --no-deps api`) en menos de 3 segundos.
   - **Validación de proveedores:** Compruebe que las variables llegaron al contenedor con:
     ```powershell
     docker compose exec -T api python -m app.validate_providers
     # O con validación de ping en vivo:
     docker compose exec -T api python -m app.validate_providers --live
     ```

---

## 6. Inicio de los contenedores en un comando

Ejecuta el script de inicio para Windows:

```powershell
.\scripts\run.ps1
```

*(O de forma equivalente: `docker compose up --build -d`).*

El proceso descargará las imágenes oficiales, compilará la PWA en Vite/React, preparará el entorno de FastAPI y levantará los 3 servicios:
1. `civia-db-1`: PostgreSQL 17 Alpine en red estricta interna `172.28.0.10`.
2. `civia-api-1`: FastAPI en `172.28.0.11`, puerto expuesto `127.0.0.1:8000`.
3. `civia-frontend-1`: Nginx Alpine en `172.28.0.2`, puerto expuesto `127.0.0.1:5173`.

---

## 7. Validación del Healthcheck del Backend

Antes de abrir el navegador, valida que el backend y PostgreSQL hayan completado sus migraciones y estén saludables:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health" | ConvertTo-Json
```

**Respuesta esperada:**
```json
{"status":"ok","phase":"mvp","db":{"connected":true,"schema_ready":true}}
```

---

## 8. Acceso a la PWA Ciudadana

Abre tu navegador web (Google Chrome, Microsoft Edge o Firefox) e ingresa a:
👉 **`http://localhost:5173`**

Verás la interfaz ciudadana de CIVIA:
- Tablero de estadísticas viales y ambientales en vivo.
- Mapa geográfico interactivo de Cali (Leaflet) centrado en la ciudad.
- Formulario de radicación ciudadana.
- Buscador y seguimiento de reportes por código de radicado.

---

## 9. Prueba funcional ciudadana (Paso a Paso)

1. En la PWA (`http://localhost:5173`), localiza la sección **"Nuevo Reporte Ciudadano"**.
2. **Ubicación GPS:** Haz clic sobre cualquier punto del mapa de Cali (por ejemplo en el centro, Comuna 2 o San Antonio) o pulsa el botón *"Usar mi ubicación actual"*. Comprueba que las coordenadas se completen automáticamente dentro del Valle del Cauca.
3. **Fotografía:** Puedes pulsar el botón de cámara web para capturar una foto real del dispositivo, seleccionar una imagen desde tu disco, o pulsar una de las muestras sintéticas fotorrealistas de demostración.
4. **Categoría y Descripción:**
   - Categoría: Selecciona `Hueco`.
   - Título: `Bache pronunciado en vía principal`.
   - Descripción: `Hueco de aproximadamente 50 cm de diámetro en carril derecho frente a la estación de transporte.`
5. Pulsa **"Enviar Reporte Ciudadano"**.
6. **Resultado verificado:**
   - La aplicación responderá con un código de radicado oficial: ej. `CIV-2026-XXXX`.
   - El nuevo reporte aparecerá inmediatamente reflejado en el mapa de Cali con un marcador interactivo.

---

## 10. Prueba del Asistente Agéntico con IA

1. En la PWA, desplázate a la sección **"Asistente Ciudadano CIVIA"**.
2. Escribe una consulta en lenguaje natural:
   > *"¿Cuáles son los reportes de basuras registrados en Cali?"*
3. Observa la respuesta:
   - El agente ejecuta la herramienta tipada `consultar_reportes` con `{ category: "BASURAS" }`.
   - Responde con un resumen claro en lenguaje natural, identificando los radicados existentes sin exponer metadatos técnicos ni tracebacks.
4. Prueba la pregunta de control dorada sin respuesta posible (GD-06):
   > *"¿Qué reportes de radiación nuclear o satélite existen en la Comuna 99?"*
5. **Resultado verificado:**
   - El agente no alucina ni inventa datos; responde honestamente que no existen reportes sobre radiación ni Comuna 99 en la base de datos de Cali.

---

## 11. Prueba de Administración, Aprobación Humana y Observabilidad

1. En la barra superior de la PWA, ingresa a la pestaña **"Administración"** (la navegación en CIVIA se gestiona fluidamente como una Single Page Application mediante pestañas).
2. Ingresa el `ADMIN_TOKEN` generado en tu archivo `.env`.  
   Para copiarlo directamente al portapapeles **sin imprimirlo en pantalla ni exponerlo en grabaciones o logs**, ejecuta:  
   - En Windows PowerShell:  
     ```powershell
     powershell -Command "Get-Content .env | Select-String '^ADMIN_TOKEN=' | ForEach-Object { $_.Line.Split('=',2)[1].Trim() } | Set-Clipboard; Write-Host 'ADMIN_TOKEN copiado al portapapeles.'"
     ```  
   - En Linux / macOS / WSL:  
     ```bash
     grep '^ADMIN_TOKEN=' .env | cut -d'=' -f2- | tr -d '\r\n' | (pbcopy 2>/dev/null || xclip -selection clipboard 2>/dev/null || wl-copy 2>/dev/null || echo "[Copie la línea ADMIN_TOKEN de .env]")
     ```
3. **Módulo de Aprobación Humana (`pending_approvals`):**
   - Cuando el agente propone una acción crítica (ej. cambiar el estado de un reporte mediante `proponer_actualizacion_critica`), la IA **NO** escribe directamente en la tabla `reports`.
   - La propuesta queda en estado `PENDING` en la consola administrativa.
   - Como administrador humano, pulsa **"Aprobar"** o **"Rechazar"**.
   - Comprueba que la transición sea de un solo uso (`SELECT ... FOR UPDATE`), atómica y que la propuesta pase a `APPROVED` / `REJECTED`, actualizando recién en ese momento el estado del reporte.
4. **Consola de Observabilidad y Resiliencia:**
   - Observa las métricas de latencia P50/P90, consumo de tokens y estado de los circuit breakers.
   - Prueba la **Inyección de Fallas en caliente**: selecciona `FALLA_FORZADA = 429` y observa cómo el sistema conmuta automáticamente de Gemini a Groq sin interrupción del servicio ciudadano.

---

## 12. Verificación de persistencia de datos tras reinicio

Para comprobar que los datos no residen en memoria volátil:

```powershell
# 1. Reiniciar todos los servicios
docker compose restart

# 2. Validar que la API vuelva a estar activa
Invoke-RestMethod -Uri "http://localhost:8000/health"

# 3. Consultar los reportes en la base de datos
docker compose exec -T api python -c "from app.db import get_conn; conn = get_conn(); print('Total reportes persistidos:', conn.execute('SELECT count(*) FROM reports;').fetchone()[0])"
```

El conteo incluirá los 10 reportes sintéticos iniciales más los reportes nuevos creados durante tu prueba.

---

## 13. Comandos de diagnóstico y depuración

| Diagnóstico | Comando en PowerShell |
|---|---|
| **Estado de contenedores** | `docker compose ps` |
| **Logs de la API Backend** | `docker compose logs --tail=50 -f api` |
| **Logs de la Base de Datos** | `docker compose logs --tail=50 db` |
| **Logs del Servidor Nginx** | `docker compose logs --tail=50 frontend` |
| **Ejecutar suite hermética de 155 pruebas** | `docker compose exec -T api pytest -m "not live" -v` |
| **Ejecutar pruebas E2E de navegador (opcional)** | `cd frontend && npm install && npm run test:e2e` |
| **Ejecutar evaluación formal** | `docker compose exec -T api python eval/evaluar.py --mode deterministic` |
| **Explorar API REST interactiva (Swagger UI)** | Navegar a `http://localhost:8000/docs` (especificación en [docs/API.md](API.md)) |

---

## 14. Procedimiento para detener los servicios sin borrar datos

Cuando termines la demostración:

```powershell
# Detención segura que CONSERVA todos los datos, fotos y reportes:
docker compose down
```

> [!CAUTION]
> **Nunca uses `docker compose down -v` de forma rutinaria**, ya que el parámetro `-v` destruye los volúmenes de PostgreSQL y fotos.

---

## 15. Checklist de demostración para el profesor (Rúbrica Momento 2)

| # | Criterio de la Rúbrica | Acción en la Demostración | Tiempo estimado | Verificación |
|---|---|---|---|---|
| **1** | **Despliegue limpio en un comando** | Ejecutar `.\scripts\run.ps1` desde un checkout limpio. Mostrar `docker compose ps` con los 3 contenedores activos (`healthy`). | 1.5 min | Salud en `/health` responde `true`. |
| **2** | **Flujo vertical ciudadano** | Crear reporte en la PWA: GPS interactivo en Cali, muestra oficial del catálogo sintético fotorrealista o captura en vivo de cámara web, descripción y obtención de radicado `CIV-2026-XXXX`. | 2.0 min | Reporte visible de inmediato en el mapa de Leaflet y persistido en PostgreSQL. |
| **3** | **Agente con herramientas y 4 límites** | Consultar reportes viales y ambientales en el chat. Realizar pregunta de control GD-06 (sin respuesta). Mostrar que la IA no inventa datos y respeta límites de vueltas, tokens y timeout. | 2.0 min | Tool calling tipado hacia SQL directo (sin RAG); respuesta honesta en GD-06. |
| **4** | **Aprobación humana para escritura crítica** | Agente propone cambio de estado (`proponer_actualizacion_critica`). Ingresar a la pestaña Administración con `ADMIN_TOKEN` y aprobar manualmente la propuesta. | 1.5 min | Invariante: La IA jamás escribe directamente en la tabla `reports`. |
| **5** | **Resiliencia y Circuit Breakers** | Activar `FALLA_FORZADA = 429` en la consola administrativa. Realizar una consulta y mostrar la conmutación transparente a Groq (`qwen/qwen3.8-27b`). | 1.0 min | Cero tracebacks o errores HTTP expuestos al ciudadano; observabilidad registrada en `ai_traces`. |
| **6** | **Evaluación formal y métricas reales** | Mostrar `eval/resultados/reporte_evaluacion.md`: 6 casos dorados SQL (`100%`), 15 consultas P50/P90 (`93.3%` acierto), costo estimado y cero secretos. | 1.0 min | Suite hermética de 155 pruebas automáticas pasando al 100% (cero fallos). |

---

## 16. Distinción honesta: Funcionalidades implementadas vs. Propuestas futuras

Para mantener la máxima transparencia académica:

### Totalmente implementado y verificable hoy:
- Flujo vertical completo: captura, georreferenciación en Valle del Cauca, validación de fotos (dimensiones, tipos MIME, remoción EXIF), notas de voz, almacenamiento en PostgreSQL 17.
- Sistema agéntico resiliente de 3 niveles: Google Gemini (`gemini-3.8-flash`) → Groq Cloud (`qwen/qwen3.8-27b`) → Google Gemini (`gemini-3.5-flash-lite`).
- Arquitectura SQL directa (justificación formal de NO RAG documentada en `docs/decisiones.md`).
- Los 4 límites estrictos del agente: iteraciones (5), presupuesto de tokens (6000), timeouts granulares y aprobación humana obligatoria para escrituras críticas.
- Protocolo de recuperación PWA ante desconexión o pérdida de primera respuesta con persistencia de claves de idempotencia y deduplicación.
- Seguridad por capas: sin credenciales en frontend ni logs, validación fail-closed de `ADMIN_TOKEN`, cookies y cabeceras CSP/nosniff.

### Propuestas a futuro (No simuladas ni falsificadas):
- **Imágenes satelitales en tiempo real e índices NDVI:** El sistema no consulta satélites militares o comerciales en tiempo real; ante preguntas sobre radiación o índices satelitales ficticios en Cali, el agente responde honestamente que no existen dichos registros en la base de datos municipal.
- **Modelos predictivos prospectivos de degradación de pavimentos:** La categorización actual se basa en visión computacional y análisis multimodal sobre la evidencia fotográfica suministrada, no en modelos de simulación geológica prospectiva a 5 años.

---

## 17. Declaración de estado de verificación externa

> [!NOTE]
> Esta guía ha sido verificada en la rama principal `main`, incluyendo la prueba de clonación limpia en carpeta temporal aislada y validación de 168 pruebas herméticas. La instalación física desde cero en un segundo computador portátil Windows 11 queda formalmente dispuesta para su ejecución por parte del evaluador o del equipo durante la sesión de sustentación académica, siguiendo exactamente los pasos descritos en este documento.
