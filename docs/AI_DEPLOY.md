# CIVIA — Protocolo de Despliegue y Verificación Asistido por IA

Este documento describe el procedimiento operativo estándar para agentes de inteligencia artificial y evaluadores automáticos (**Claude Code, Gemini CLI, Antigravity, ChatGPT, Codex**) que requieran clonar, desplegar y auditar la plataforma CIVIA sin intervención humana.

---

## 1. Verificación de Pre-requisitos del Sistema Anfitrión
El anfitrión debe contar con Docker y Git:
```powershell
docker --version
git --version
```
*No se requiere tener instalados Python ni Node.js en la máquina anfitriona.*

---

## 2. Despliegue en un Solo Paso
Desde la raíz del repositorio en la rama `main`:

```powershell
# En Windows 11 (PowerShell):
.\scripts\run.ps1
```

```bash
# En Linux / macOS / Bash:
chmod +x ./scripts/run.sh && ./scripts/run.sh
```

El script se encarga de forma completamente autónoma de:
- Verificar que el motor de Docker esté en ejecución y que los puertos `8000` y `5173` estén libres.
- Inicializar `.env` a partir de `.env.example` si no existe.
- Generar contraseñas seguras y un `ADMIN_TOKEN` criptográfico único mediante CSPRNG de 32 bytes (base64url) sin imprimir secretos en pantalla.
- Construir las imágenes Docker de backend (`civia-api`) y frontend (`civia-frontend`).
- Levantar la base de datos `civia-db` en PostgreSQL 17.
- Aplicar migraciones SQL automáticas e idempotentes.
- Sembrar de forma inmutable el catálogo de 10 reportes sintéticos de prueba con evidencias fotorrealistas en Cali (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`).

---

## 3. Matriz de Endpoints y Verificación de Servicios
| Componente | Dirección | Validación esperada |
|---|---|---|
| Frontend PWA | `http://localhost:5173` | Código HTTP 200, interfaz React con mapa interactivo de Cali |
| Backend API | `http://localhost:8000/health` | `{"status":"ok","phase":"mvp","db":{"connected":true,"schema_ready":true}}` |
| Documentación Swagger | `http://localhost:8000/docs` | Código HTTP 200, esquema OpenAPI interactivo |

---

## 4. Validación Automatizada del Flujo Ciudadano (Playwright E2E)
Un agente evaluador puede verificar el flujo de extremo a extremo de forma desatendida:

```powershell
cd frontend
npm install
npm run test:e2e
```

Este script ejecuta dos pruebas completas:
1. **Flujo de Fotografía Real de Cámara en Vivo:** Activa cámara web emulada (`getUserMedia`), captura fotograma a canvas, envía la foto real JPEG del dispositivo a la API, recibe radicado, verifica `is_synthetic = false`, comprueba que la imagen se sirva por HTTP 200 y confirma persistencia en PostgreSQL tras recarga del navegador.
2. **Flujo de Muestra Sintética Oficial:** Selecciona muestra oficial del catálogo, comprueba el distintivo exterior de simulación ética, envía a la API, recibe radicado, verifica que el backend impone `is_synthetic = true`, comprueba que se visualice con `objectFit: contain` sin recortes, y confirma persistencia tras recarga.

**Resultado esperado:**
`2 passed (100%)`.

---

## 5. Ejecución de la Suite Hermética de Pruebas Backend
Para verificar los contratos de seguridad F1–F8, el almacenamiento inmutable de catálogo, la procedencia ética forzada en servidor y la resiliencia a fallos:

```powershell
docker compose exec -T api pytest -m "not live" -v
```

*(O de forma aislada sin contenedores activos):*
```powershell
docker run --rm -v "${PWD}\backend:/app" -v "${PWD}\frontend:/frontend" -v "${PWD}\eval:/app/eval" --network civia_civia_net -e DATABASE_URL=postgresql://civia:local_dev_change_me@civia-db-1:5432/civia civia-api pytest -m "not live"
```

**Resultado esperado:**
`154 passed, 1 deselected, 0 failed`.

---

## 6. Estado Oficial de Despliegue en la Nube
> **DESPLIEGUE LOCAL LISTO; URL PÚBLICA PENDIENTE DE INFRAESTRUCTURA**  
> Ver justificación detallada en [`docs/DEPLOYMENT.md`](DEPLOYMENT.md).
