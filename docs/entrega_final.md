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
| **Archivos huérfanos ante rollback SQL** | Escritura directa en disco antes de la confirmación de la transacción en PostgreSQL. | Staging atómico en temporales `.tmp_{uuid}` y publicación con `os.replace` solo tras `conn.commit()`. Limpieza garantizada en `except`. | `test_update_synthetic_catalog_photos_zero_orphans_on_rollback` PASSED. Trigger aborta y deja 0 archivos huérfanos. |
| **Caché rancia tras actualización** | URL estática servida con `Cache-Control: max-age=3600`. El navegador servía la versión antigua sin consultar al servidor. | `photo_url` versionada con `?v={photo_sha256[:16]}`. En `main.py`, soporte ETag/304 y `Cache-Control: public, max-age=31536000, immutable` para URLs versionadas y `max-age=0, must-revalidate` para la URL canónica. | `test_photo_endpoint_versioning_etag_and_caching` PASSED. HTTP 304 verificado con `If-None-Match`. |
| **Procedencia ética eludida en reporte ciudadano** | Muestras sintéticas generadas podían enviarse sin marca si ya existía descripción. La imagen se recortaba con `objectFit: cover`. | Backend impone `is_synthetic = True` si el hash de la foto coincide con el catálogo sintético conocido. Frontend utiliza `objectFit: contain` sobre fondo oscuro y muestra distintivo HTML exterior `ℹ Imagen generada con IA · Simulación`. | `test_synthetic_photo_ethical_provenance_enforced_on_server` PASSED. Verificación visual Playwright PASSED. |
| **Muestra OTRO duplicada** | `sample_otro.jpg` copiaba DEMO0009 (socavón de HUECO). | Se generó una escena fotorrealista propia e independiente de poste ladeado y cableado urbano en Cali mediante subagente de IA. | `test_sample_otro_is_independent_and_distinct` PASSED. SHA-256 único y distinto. |

---

## 3. Matriz de Pruebas y Resultados de Aceptación

### A. Suite Hermética Backend (Pytest)
- **Total pruebas ejecutadas:** 146
- **Pruebas pasadas (GREEN):** **145 PASSED**
- **Pruebas deseleccionadas:** 1 (marcador `live` de IA en vivo)
- **Fallos:** **0 FAILED**
- **Tiempo de ejecución:** 24.34 segundos
- **Cobertura:** Seguridad de tokens, ledger de estados, autorización de edición, idempotencia, resiliencia a fallas 429/503/timeout, circuit breaker, agente agéntico con 4 límites, catálogo fotográfico, ETag/caché, procedencia ética y persistencia PostgreSQL.

### B. Pruebas de Interfaz de Usuario y Flujo E2E (Playwright en Chromium / Edge)
- **Acceso PWA:** HTTP 200, título y componentes cargados correctamente.
- **Captura con cámara web en tiempo real:** Activación de visor `<video>` con `getUserMedia`, disparo de foto a `<canvas>`, generación de archivo JPEG y apagado estricto de pistas (`track.stop()`) al cerrar o cambiar de pestaña.
- **Selección de muestras sintéticas:** Carga de activo local, asignación de categoría y descripción demo, presentación de distintivo HTML `ℹ Imagen generada con IA · Simulación`.
- **Envío y persistencia:** Envío multipart a `/api/reports`, creación en base de datos, retorno de radicado `CIV-2026-5A30F0B466`.
- **Recarga y consulta de radicado:** Recarga completa de la página en el navegador; consulta exitosa del radicado en PostgreSQL con recuperación intacta de los datos y la fotografía sin recortes.
- **Errores de consola:** Cero errores críticos de JavaScript.

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
