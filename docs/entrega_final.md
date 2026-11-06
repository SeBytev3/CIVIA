# CIVIA — Informe Oficial de Entrega Académica Final (Momento 2)

**Equipo de desarrollo:** Stefania Córdoba y Sebastian Espinosa  
**Asignatura:** Ingeniería de Aplicaciones con IA — Momento 2  
**Institución:** Universidad Cooperativa de Colombia  
**Fecha de corte:** Noviembre de 2026  
**Repositorio oficial GitHub:** `https://github.com/SeBytev3/CIVIA.git`  
**Rama principal de entrega:** `main`  
**Commit base funcional auditado y aprobado:** `cf48e71`  
**Estado general:** **APROBADO PARA PUBLICACIÓN Y EVALUACIÓN FINAL**

---

## 1. Resumen Ejecutivo de la Entrega

CIVIA (Ciudad Inteligente y Vigilancia Ambiental con IA) es una plataforma integral diseñada para la recepción, análisis multimodal, confirmación humana y gestión de reportes de anomalías urbanas y ambientales en Santiago de Cali y el Valle del Cauca.

El sistema resuelve un flujo vertical completo:
1. **Captura ciudadana flexible:** Soporte para captura directa con cámara web de dispositivo (`getUserMedia`), subida de archivos locales (JPEG, PNG, WEBP), drag & drop, o selección de muestras fotográficas sintéticas de prueba demo.
2. **Georreferenciación:** Captura GPS nativa del navegador o selección interactiva en el mapa Leaflet de Cali con cálculo Haversine.
3. **Persistencia e integridad:** Almacenamiento seguro en PostgreSQL 17 con radicado único `CIV-2026-...` y token de edición propietario para el ciudadano.
4. **Enrutamiento multimodal resiliente:** Cadena de tres niveles (`Gemini` → `Groq` → `Gemini`) con manejo de errores 429, backoff exponencial, circuit breakers y degradación elegante a `PENDING_ANALYSIS` ante falla total, sin exponer detalles técnicos al ciudadano.
5. **Confirmación y supervisión humana:** Separación estricta entre diagnóstico asistido por IA y clasificación confirmada por humanos.
6. **Agente de consulta con SQL directo y 4 límites estrictos:** Consulta en lenguaje natural a la base de datos sin RAG innecesario, protegido por límites de vueltas (5), tokens (6000), timeout (15s) y aprobación humana obligatoria en `pending_approvals` para escrituras críticas.
7. **Observabilidad técnica y administración:** Zona protegida mediante `ADMIN_TOKEN` seguro generado con CSPRNG.

---

## 2. Remediación Integral de Hallazgos de Auditoría Independiente

Se cerraron de forma definitiva y verificable todos los hallazgos señalados en las auditorías de Codex:

| Hallazgo / Vector | Causa Raíz Identificada | Solución Implementada | Verificación Adversarial |
|---|---|---|---|
| **Corrupción de igual longitud en catálogo** | `seed.py` solo comparaba existencia y tamaño `st_size`. Archivos con bytes alterados no se reparaban. | Validación por SHA-256 de bytes reales en disco y decodificación con PIL (`Image.verify()`). | `test_update_synthetic_catalog_photos_detects_same_length_corruption` PASSED. Detecta y restaura archivo corrompido (`updated=1`, `unchanged=9`). |
| **Archivos huérfanos y atomicidad de publicación en catálogo** | `seed.py` hacía commit SQL antes de `os.replace` y mantenía un fallback inseguro de `write_bytes`. | Eliminado el fallback directo. Implementado Two-Phase Staging coordinado: staging en temporales validado con PIL, backup atómico a `.bak_{uuid}` con `os.replace`, publicación atómica antes de `conn.commit()`, y reversión total desde backups en `except`. Limpieza garantizada de residuos en arranque. | `test_update_synthetic_catalog_photos_fs_failure_compensates_and_rolls_back`, `test_update_synthetic_catalog_photos_recovers_after_interruption` y `test_update_synthetic_catalog_photos_zero_orphans_on_rollback` PASSED. Cero referencias rotas y cero huérfanos. |
| **Caché rancia tras actualización** | URL estática servida con `Cache-Control: max-age=3600`. El navegador servía la versión antigua sin consultar al servidor. | `photo_url` versionada con `?v={photo_sha256[:16]}`. En `main.py`, soporte ETag/304 e inmutabilidad (`Cache-Control: public, max-age=31536000, immutable`) para URLs versionadas y `max-age=0, must-revalidate` para la URL canónica. | `test_photo_endpoint_versioning_etag_and_caching` PASSED. HTTP 304 verificado con `If-None-Match`. |
| **Procedencia ética eludida en reporte ciudadano** | Muestras sintéticas generadas podían enviarse sin marca si ya existía descripción. El cliente podía enviar `is_synthetic=true` en cualquier foto arbitraria. La imagen se recortaba con `objectFit: cover`. | Backend no confía en `is_synthetic` provisto por el cliente: impone `is_synthetic = True` exclusivamente si el hash de la foto coincide con las 11 muestras oficiales conocidas del catálogo. Fotos externas arbitrarias con `is_synthetic=true` son catalogadas como `is_synthetic = False`. Frontend utiliza `objectFit: contain` sobre fondo oscuro y muestra distintivo HTML exterior `ℹ Imagen generada con IA · Simulación`. | `test_synthetic_photo_ethical_provenance_enforced_on_server` PASSED (evaluando casos de catálogo y fotos externas arbitrarias). Verificación visual Playwright PASSED. |
| **Muestra OTRO duplicada** | `sample_otro.jpg` copiaba DEMO0009 (socavón de HUECO). | Se generó una escena fotorrealista propia e independiente de poste ladeado y cableado urbano en Cali mediante subagente de IA. | `test_sample_otro_is_independent_and_distinct` PASSED. SHA-256 único y distinto. |

---

## 3. Matriz de Pruebas y Resultados de Aceptación

### A. Suite Hermética Backend (Pytest)
- **Total pruebas ejecutadas:** 148
- **Pruebas pasadas (GREEN):** **147 PASSED**
- **Pruebas deseleccionadas:** 1 (marcador `live` de IA en vivo)
- **Fallos:** **0 FAILED**
- **Tiempo de ejecución:** 26.12 segundos
- **Cobertura:** Seguridad de tokens, ledger de estados, autorización de edición, idempotencia, resiliencia a fallas 429/503/timeout, circuit breaker, agente agéntico con 4 límites, catálogo fotográfico con Two-Phase Staging y compensación por rollback de FS/BD, ETag/caché inmutable, procedencia ética certificada en servidor y persistencia PostgreSQL.

### B. Pruebas de Interfaz de Usuario y Flujo Dual E2E Portable (Playwright)
- **Portabilidad garantizada:** `playwright` declarado en `devDependencies` de `frontend/package.json` con script `npm run test:e2e`. Cero rutas absolutas fijas en `scripts/test_e2e_final.cjs`. Detección automática y flexible de Chromium estándar con fallback a Google Chrome o Microsoft Edge.
- **Test 1 — Fotografía Ciudadana Real con Cámara en Vivo:**
  - Activación de cámara emulada mediante `getUserMedia`.
  - Captura de cuadro a `<canvas>` y generación de fotografía JPEG real del dispositivo.
  - Envío de la fotografía real a `/api/reports`.
  - Generación y recepción de radicado ciudadano (ej. `CIV-2026-CA1BFF8D95`).
  - Verificación en servidor de procedencia ciudadana real (`is_synthetic = false`).
  - Descarga y verificación HTTP 200 de la imagen almacenada en `/api/reports/{id}/photo` (12916 bytes válidos).
  - Recarga del navegador (`page.reload()`) y confirmación de persistencia íntegra en PostgreSQL.
- **Test 2 — Muestra Sintética Oficial de Catálogo:**
  - Carga de muestra oficial (ej. Poste / Cables), asignación de categoría y descripción.
  - Verificación de distintivo ético exterior HTML `ℹ Imagen generada con IA · Simulación` en vista previa.
  - Envío a API y obtención de radicado (ej. `CIV-2026-C263227696`).
  - Verificación en servidor de procedencia sintética ética certificada (`is_synthetic = true`).
  - Verificación de renderizado visual con regla CSS `objectFit: contain` sobre fondo oscuro, preservando íntegra la franja de simulación ética sin recortes.
  - Recarga de página y confirmación de persistencia.
- **Errores de consola:** Cero errores de JavaScript.

---

## 4. Estado de Despliegue en la Nube

> **ESTADO OFICIAL: DESPLIEGUE LOCAL LISTO; URL PÚBLICA PENDIENTE DE INFRAESTRUCTURA**

### Justificación
La plataforma CIVIA requiere una base de datos relacional PostgreSQL 17 con almacenamiento transaccional y persistencia de evidencias fotográficas en disco o bucket de almacenamiento de objetos. Los servicios gratuitos en la nube imponen suspensión de instancias por inactividad (*cold sleep*), discos efímeros no persistentes y no garantizan SSL ni SLA para bases de datos relacionales sin costo.

Por tanto, el proyecto se entrega completamente contenedorizado (`docker-compose.yml`, `scripts/run.ps1`, `scripts/run.sh`) garantizando reproducibilidad exacta en cualquier máquina anfitriona Windows 11 o Linux en un solo comando, con cero costos para los evaluadores y máxima privacidad de los datos.

---

## 5. Instrucciones de Evaluación para el Profesor

Para evaluar el proyecto de manera directa:
1. Clonar el repositorio oficial:
   ```powershell
   git clone https://github.com/SeBytev3/CIVIA.git
   cd CIVIA
   ```
2. Ejecutar el script de arranque:
   ```powershell
   .\scripts\run.ps1
   ```
3. Abrir el navegador en `http://localhost:5173`.
4. Seguir los pasos de demostración:
   - Crear un reporte con la cámara o una muestra sintética.
   - Observar el diagnóstico de IA y confirmar la clasificación.
   - Probar el Asistente Agéntico en la pestaña correspondiente.
   - Ingresar a la Zona Admin con el `ADMIN_TOKEN` visible en `.env`.
