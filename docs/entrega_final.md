# CIVIA — Informe Oficial de Entrega Académica Final (Momento 2)

**Equipo de desarrollo:** Stefania Córdoba y Sebastian Espinosa  
**Asignatura:** Ingeniería de Aplicaciones con IA — Momento 2  
**Institución:** Universidad Cooperativa de Colombia  
**Fecha de entrega:** Noviembre de 2026  
**Repositorio oficial GitHub:** `https://github.com/SeBytev3/CIVIA.git`  
**Rama principal de entrega:** `main`  
**Etiqueta oficial de release:** `v1.0.0-academic`  
**Estado general:** **ENTREGA ACADÉMICA LISTA — MAIN PUBLICADA Y CLON LIMPIO VALIDADO**

---

## A. Repositorio Oficial y Trazabilidad en GitHub

- **URL del Repositorio:** [https://github.com/SeBytev3/CIVIA.git](https://github.com/SeBytev3/CIVIA.git)
- **Rama predeterminada y funcional:** `main`
- **Etiqueta anotada de release:** `v1.0.0-academic`
- **Commits auditados y certificados:**
  - Base de remediación Codex F1–F8: `cf48e71`
  - Cierre inmutable de catálogo, bootstrap autónomo y pruebas adversariales A-L: `7a9944b`
  - Consolidación documental y release final: commit en `main`.

---

## B. Procedimiento de Instalación y Despliegue en un Solo Comando

El proyecto se despliega de forma autónoma tanto para evaluadores humanos como para agentes de inteligencia artificial (**Claude Code, Gemini CLI, Antigravity, ChatGPT, Codex**).

### 1. Comando Único de Arranque
Desde una terminal en un computador con Git y Docker Desktop / Engine:

```powershell
# En Windows 11 (PowerShell):
git clone https://github.com/SeBytev3/CIVIA.git
cd CIVIA
.\scripts\run.ps1
```

```bash
# En Linux / macOS / WSL:
git clone https://github.com/SeBytev3/CIVIA.git
cd CIVIA
chmod +x ./scripts/run.sh && ./scripts/run.sh
```

### 2. Acciones que ejecuta el Bootstrap Automático:
1. **Verificación preventiva:** Confirma que Docker y Compose estén activos y que los puertos `8000` (API) y `5173` (Frontend) estén disponibles.
2. **Generación de credenciales seguras (CSPRNG):** Crea un archivo `.env` basado en `.env.example` y genera contraseñas aleatorias seguras y un `ADMIN_TOKEN` criptográfico único (`secrets.token_urlsafe(32)`), sin imprimir secretos en pantalla.
3. **Orquestación hermética:** Construye y arranca los contenedores (`civia-db-1`, `civia-api-1`, `civia-frontend-1`).
4. **Migraciones y Catálogo Inmutable:** Aplica migraciones SQL idempotentes y siembra el catálogo de 10 reportes sintéticos de prueba con evidencias fotorrealistas de alta fidelidad en Santiago de Cali (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`).

### 3. Endpoints de Verificación Inmediata:
- **PWA Ciudadana:** `http://localhost:5173` (HTTP 200)
- **Salud del Backend:** `http://localhost:8000/health` (`{"status":"ok","phase":"mvp","db":{"connected":true,"schema_ready":true}}`)
- **Documentación Swagger:** `http://localhost:8000/docs`

---

## C. Matriz de Validación y Pruebas de Entrega

La versión de entrega final ha sido sometida a un riguroso protocolo de pruebas multicapa:

### 1. Suite Hermética de Backend (Pytest)
- **Total pruebas ejecutadas:** 155
- **Pruebas aprobadas:** **154 PASSED** (100% de la suite hermética)
- **Pruebas deseleccionadas:** 1 (marcador `live` que requiere claves de inferencia en vivo)
- **Fallos:** **0 FAILED**
- **Tiempo de ejecución:** 27.15 segundos
- **Contratos validados:**
  - Contratos de auditoría Codex F1 a F8 (fuga de capacidades, token CSPRNG, cancelaciones SQL, control de límites, ledger de estados y serialización transaccional).
  - Almacenamiento inmutable Content-Addressed (`synthetic_{code}_{sha[:16]}.jpg`).
  - Las 12 pruebas adversariales de catálogo sintético (Casos A a L: interrupciones tras staging, fallos de reemplazo en disco, fallos en commit SQL, concurrencia de actualizadores, corrupción de igual longitud, idempotencia repetida, migración PNG->JPEG, activos faltantes y no interferencia con reportes ciudadanos).
  - Procedencia ética forzada en servidor y visualización en `objectFit: contain`.
  - Caché versionada inmutable con soporte ETag y HTTP 304.
  - Resiliencia ante fallos inyectados: `429`, `503`, `TIMEOUT`, `INVALID_JSON`, `TOTAL`.

### 2. Pruebas de Interfaz y Flujo de Extremo a Extremo (Playwright E2E)
- **Total pruebas ejecutadas:** 2
- **Aprobadas:** **2 PASSED (100%)**
- **Test 1 — Flujo de Fotografía Real de Cámara en Vivo:**
  - Emulación de cámara web (`getUserMedia`).
  - Captura de cuadro a `<canvas>` y envío de fotografía JPEG real a la API.
  - Obtención de código de radicado único.
  - Verificación en servidor de procedencia ciudadana real (`is_synthetic = false`).
  - Descarga y verificación HTTP 200 de la imagen almacenada.
  - Recarga de la página y comprobación de persistencia íntegra en PostgreSQL 17.
- **Test 2 — Flujo de Muestra Sintética Oficial:**
  - Carga de muestra oficial con distintivo de simulación ética.
  - Envío a la API y obtención de radicado.
  - Verificación en servidor de procedencia sintética certificada (`is_synthetic = true`).
  - Verificación de renderizado en `objectFit: contain` sin recortes de la franja ética.
  - Recarga y persistencia en base de datos.

### 3. Prueba de Clon Limpio en Directorio Temporal Aislado
- **Directorio de prueba:** Carpeta temporal independiente (`%TEMP%\civia_clean_...`).
- **Aislamiento:** Clonación pura desde GitHub, sin copiar `.env`, `node_modules` ni volúmenes previos.
- **Puertos y red aislada:** API en `18000`, Frontend en `15173`, subred `10.240.0.0/24`.
- **Hitos verificados:**
  1. Arranque exitoso de los 3 contenedores.
  2. Salud confirmada en `/health` (DB conectada y esquema listo).
  3. Catálogo sintético verificado y fotos fotorrealistas servidas (> 100 KB cada una).
  4. Creación de un nuevo reporte ciudadano con foto y georreferenciación.
  5. Reinicio completo de contenedores (`docker compose restart`).
  6. Persistencia confirmada de reporte y fotografía (re-codificada limpia según privacidad A-02).
  7. Destrucción limpia y completa de recursos desechables (`down -v`).
- **Tiempo total de ejecución:** **29.1 segundos (100% PASS)**.

---

## D. Declaración de Limitaciones Honestas y Estado en la Nube

### Estado Oficial Cloud
> **DESPLIEGUE LOCAL LISTO; URL PÚBLICA PENDIENTE DE INFRAESTRUCTURA**

### Justificación Técnica y Académica
1. **Persistencia e Integridad:** CIVIA requiere una base de datos PostgreSQL 17 transaccional y persistente, junto con un volumen de almacenamiento local para evidencias fotográficas y trazas de observabilidad.
2. **Capas gratuitas de nube:** Los servicios gratuitos en la nube (como Render, Koyeb o Railway en capas libres) imponen suspensión automática por inactividad (*cold sleep*), borrado de volúmenes efímeros en cada despliegue y límites de ancho de banda que destruyen la persistencia de las fotos y reportes evaluados.
3. **Privacidad y Costos:** No se expuso una URL pública no autenticada para evitar consumo no supervisado de cuotas en proveedores de IA y para no incurrir en gastos privados no presupuestados.
4. **Reproducibilidad:** La solución basada en Docker Compose y scripts de un solo comando (`run.ps1` / `run.sh`) garantiza que cualquier evaluador en Windows 11, Linux o macOS pueda levantar la plataforma completa exactamente en las mismas condiciones, de forma 100% determinista y sin costo.

---

## E. Veredicto Oficial

**ENTREGA ACADÉMICA LISTA — MAIN PUBLICADA Y CLON LIMPIO VALIDADO**

La plataforma CIVIA cumple a cabalidad con todos los criterios de evaluación del Momento 2:
- Flujo vertical ciudadano completo (captura de foto/cámara, GPS, radicación, persistencia y consulta).
- Agente inteligente con SQL directo tipado y cuatro límites verificables.
- Enrutamiento multimodal resiliente con fallback independiente (`Gemini` → `Groq` → `Gemini`).
- Catálogo sintético ético con almacenamiento inmutable Content-Addressed.
- Seguridad por capas (CSPRNG, ETag, headers seguros, sanitización de PII y EXIF).
- Despliegue en un solo comando y reproducibilidad autónoma garantizada.
