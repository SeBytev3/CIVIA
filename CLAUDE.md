# CIVIA — Guía de Ejecución y Evaluación Autónoma para Claude Code y Agentes de IA

Este documento contiene las instrucciones precisas para que cualquier agente autónomo (**Claude Code, Gemini CLI, Antigravity, Codex, ChatGPT**) descargue, despliegue, pruebe y valide la plataforma CIVIA sin intervención humana.

---

## 1. Identificación del Proyecto
- **Repositorio:** `https://github.com/SeBytev3/CIVIA.git`
- **Rama principal y definitiva:** `main`
- **Etiqueta oficial:** `v1.0.0-academic`
- **Tecnologías:** FastAPI (Python 3.13), React 19 + TypeScript + Vite, PostgreSQL 17, Nginx 1.27, Docker Compose.
- **Área geográfica:** Santiago de Cali y Valle del Cauca, Colombia.

---

## 2. Un Solo Comando de Despliegue
En la raíz del proyecto, ejecutar:

### En Windows 11 (PowerShell):
```powershell
.\scripts\run.ps1
```

### En Linux / macOS / WSL:
```bash
chmod +x ./scripts/run.sh && ./scripts/run.sh
```

El script realiza de manera completamente autónoma:
1. Comprueba la salud del motor de Docker y la disponibilidad de puertos (`8000` y `5173`).
2. Copia `.env.example` a `.env` si no existe.
3. Genera credenciales aleatorias seguras y un `ADMIN_TOKEN` criptográfico único mediante CSPRNG de 32 bytes (base64url).
4. Construye y arranca los contenedores (`docker compose up --build -d`).
5. Espera a que la base de datos PostgreSQL 17 aplique migraciones e inserte el catálogo sintético de prueba inmutable.
6. Expone la PWA en `http://localhost:5173` y la API en `http://localhost:8000`.

---

## 3. Verificación de Salud Inmediata
Ejecutar la siguiente llamada HTTP para comprobar la salud de los servicios:

```bash
curl -s http://localhost:8000/health
```
**Respuesta esperada (HTTP 200):**
```json
{"status":"ok","phase":"mvp","db":{"connected":true,"schema_ready":true}}
```

Comprobar que el frontend responde:
```bash
curl -I -s http://localhost:5173
# HTTP/1.1 200 OK
```

---

## 4. Ejecución Hermética de Pruebas
Para correr la suite completa de 155 pruebas backend:

```powershell
docker compose exec -T api pytest -m "not live" -v
```

*(O de forma directa mediante contenedor efímero):*
```powershell
docker run --rm -v "${PWD}\backend:/app" -v "${PWD}\frontend:/frontend" -v "${PWD}\eval:/app/eval" --network civia_civia_net -e DATABASE_URL=postgresql://civia:local_dev_change_me@civia-db-1:5432/civia civia-api pytest -m "not live"
```
**Resultado esperado:**
`155 passed, 1 deselected, 0 failed`.

---

## 5. Recorrido de Demostración del Agente Evaluador
1. **PWA Ciudadana (`http://localhost:5173`):**
   - Pestaña **Mapa y Reportes:** Visualización de incidentes georreferenciados en Cali. Al hacer clic en un marcador o tarjeta, se despliega el panel de inspección con la fotografía escalada sin recortes (`objectFit: contain`) y distintivo ético visible si es dato sintético.
   - Pestaña **+ Nuevo Reporte:** 
     - Selección de captura con cámara web (`getUserMedia`) o subida de archivo (JPEG, PNG, WEBP).
     - Botones de muestras sintéticas de prueba demo fotorrealistas (HUECO, BASURAS, TALA, QUEMA, OTRO).
     - Coordenadas GPS del dispositivo o selección sobre el mapa de Cali.
     - Envío seguro: genera código de radicado único `CIV-2026-...` y navega automáticamente a seguimiento.
   - Pestaña **Seguimiento Radicado:** Búsqueda en PostgreSQL por radicado, con diagnóstico sugerido por IA y panel de confirmación humana ciudadana.
   - Pestaña **Asistente Agéntico:** Consulta en lenguaje natural con herramientas tipadas y SQL directo bajo 4 límites efectivos (vueltas, tokens, timeout, aprobación humana).
   - Pestaña **Observabilidad Admin:** Ingrese el `ADMIN_TOKEN` generado en `.env` para ver el estado de los interruptores de circuito, latencias y aprobar/rechazar propuestas de actualización crítica.

---

## 6. Documentación Canónica de la API REST y Swagger UI
- **Swagger UI interactivo:** `http://localhost:8000/docs`
- **Especificación OpenAPI cruda:** `http://localhost:8000/openapi.json`
- **Documento canónico exhaustivo:** [`docs/API.md`](docs/API.md) detalla los 23 endpoints organizados en 8 tags temáticos, esquemas Pydantic v2, códigos HTTP, flujo React-FastAPI, persistencia PostgreSQL 17 y seguridad por token HMAC.

---

## 7. Estado Oficial de Despliegue en la Nube
> **DESPLIEGUE LOCAL LISTO; URL PÚBLICA PENDIENTE DE INFRAESTRUCTURA**  
> La aplicación se entrega completamente dockerizada y reproducible en cualquier host Windows 11 o Linux. No se ha desplegado a una URL pública de terceros para no incurrir en costos privados no asignados, ni exponer secretos en infraestructuras gratuitas sin PostgreSQL dedicado y persistente.
