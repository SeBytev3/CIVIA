# CIVIA — Protocolo de Despliegue y Verificación Asistido por IA

Este documento describe el procedimiento operativo estándar para agentes de inteligencia artificial y evaluadores automáticos que requieran clonar, desplegar y auditar la plataforma CIVIA.

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
# En Windows (PowerShell):
.\scripts\run.ps1
```

```bash
# En Linux / macOS / Bash:
./scripts/run.sh
```

El script se encarga de:
- Inicializar `.env` a partir de `.env.example`.
- Generar un `ADMIN_TOKEN` seguro mediante CSPRNG de 32 bytes en formato base64url.
- Construir las imágenes Docker de backend (`civia-api`) y frontend (`civia-frontend`).
- Levantar la base de datos `civia-db` en PostgreSQL 17.
- Aplicar migraciones SQL automáticas e idempotentes.
- Sembrar los 10 reportes de catálogo sintético con metadatos fotorrealistas en Cali.

---

## 3. Matriz de Endpoints y Verificación de Servicios
| Componente | Dirección | Validación esperada |
|---|---|---|
| Frontend PWA | `http://localhost:5173` | Código HTTP 200, interfaz React con mapa de Cali |
| Backend API | `http://localhost:8000/health` | `{"status":"ok","phase":"mvp","db":{"connected":true,"schema_ready":true}}` |
| Documentación Swagger | `http://localhost:8000/docs` | Código HTTP 200, esquema OpenAPI interactivo |

---

## 4. Validación Automatizada del Flujo Ciudadano
Un agente puede verificar el flujo de extremo a extremo mediante el script Playwright:

```powershell
node scripts/test_e2e_final.cjs
```

Este script valida:
1. Acceso y renderizado del mapa Leaflet.
2. Captura con cámara web en tiempo real (`getUserMedia` con dispositivo emulado).
3. Selección de muestra sintética fotográfica independiente con distintivo ético.
4. Envío de reporte multipart a la API.
5. Inserción del registro en PostgreSQL y retorno de radicado `CIV-2026-...`.
6. Presentación del detalle con fotografía en `objectFit: contain` (sin recortar la franja ética de simulación).
7. Recarga de la página y consulta del radicado persistido en base de datos.

---

## 5. Ejecución de la Suite Hermética de Pruebas
Para verificar la ausencia de regresiones en los contratos de seguridad F1–F8 y resiliencia:

```powershell
docker run --rm -v "${PWD}\backend:/app" -v "${PWD}\frontend:/frontend" -v "${PWD}\eval:/app/eval" --network civia_civia_net -e DATABASE_URL=postgresql://civia:local_dev_change_me@civia-db-1:5432/civia civia-api pytest -m "not live"
```

**Resultado esperado:**
`145 passed, 1 deselected, 0 failed`.
