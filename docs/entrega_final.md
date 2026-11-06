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
- **Documentación Swagger:** `http://localhost:8000/docs` (especificación canónica en [`docs/API.md`](API.md))

---

## C. Matriz de Validación y Pruebas de Entrega

La versión de entrega final ha sido sometida a un riguroso protocolo de pruebas multicapa:

### 1. Suite Hermética de Backend (Pytest)
- **Total pruebas ejecutadas:** 156
- **Pruebas aprobadas:** **155 PASSED** (100% de la suite hermética)
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
- **Suites ejecutadas:** 2 suites completas (`test_e2e_final.cjs` y `test_citizen_ux_suite.cjs`).
- **Aprobación:** **100% PASSED** (0 fallos).
- **Suite E2E 1 — Cámara Real en Vivo y Evidencia Sintética Oficial (`test_e2e_final.cjs`):**
  - *Flujo 1 (Cámara real):* Emulación de cámara web (`getUserMedia`), captura de fotograma JPEG real, envío a la API, radicación única, comprobación `is_synthetic = false`, descarga y verificación HTTP 200 de la foto, y persistencia tras recarga en PostgreSQL 17.
  - *Flujo 2 (Muestra sintética):* Carga de muestra oficial con franja ética, envío, verificación `is_synthetic = true`, renderizado en `objectFit: contain` sin recortes y persistencia en base de datos.
- **Suite E2E 2 — Refinamiento UX/UI, Accesibilidad y Trazabilidad Ciudadana (`test_citizen_ux_suite.cjs`):**
  - *Lenguaje empático:* Supresión total de jerga técnica y errores API visibles al ciudadano.
  - *Flujo vertical post-envío:* Desplazamiento automático accesible hacia el banner de éxito con foco accesible (`tabIndex={-1}`), radicado destacado grande y botón interactivo *"Copiar radicado"* con confirmación visual.
  - *Limpieza de formulario:* Liberación de cámara/micrófono y reseteo de inputs exclusivamente tras confirmación de éxito en servidor.
  - *Trazabilidad de eventos:* Línea de tiempo cronológica accesible (`report_events`) con hitos de registro, análisis y gestión institucional.
  - *Aviso transparente:* Notificación visible informando que el correo a entidades externas no está habilitado (`external_delivery_status: 'NOT_ENABLED'`) y que el reporte permanece guardado de forma permanente.
  - *Bandeja administrativa:* Panel protegido (`admin_notifications`) con contadores de pendientes, filtros y actualización de asignación.
  - *Cierre limpio de detalles:* Botón *"✕ Cerrar detalle"* con restauración de foco al elemento de origen sin desconfigurar filtros ni mapas.
  - *Contraste y diseño:* Verificación de contraste WCAG AA (>= 4.5:1) en hover de botones y pruebas tanto en Desktop (1366x768) como en Móvil (390x844).

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

### 4. Matriz de Correspondencia de Documentación Integral
| DOCUMENTO | ESTADO ANTERIOR | CORRECCIÓN | FUENTE DE VERIFICACIÓN | ESTADO FINAL |
|---|---|---|---|---|
| `README.md` | Conteos de 154 pruebas; sin clasificación de limitaciones A-D. | Actualizado a 155 pruebas herméticas; incorporada sección "Limitaciones conocidas de la versión académica" con 4 categorías A-D. | `backend/tests/`, `docker compose exec api pytest` | Actualizado y sincronizado al 100% |
| `AGENTS.md` | Protocolo evaluador sin mención a nuevos contratos de veracidad. | Sincronizado el comando de evaluación autónoma para evaluadores externos. | `AGENTS.md` | Vigente y riguroso |
| `CLAUDE.md` | Conteo de 154 pruebas herméticas. | Actualizado a 155 pruebas herméticas (`155 passed, 1 deselected, 0 failed`). | `pytest -m "not live"` | Actualizado al 100% |
| `GEMINI.md` | Conteo de 154 pruebas herméticas. | Actualizado a 155 pruebas herméticas (`155 passed, 1 deselected, 0 failed`). | `pytest -m "not live"` | Actualizado al 100% |
| `docs/AI_DEPLOY.md` | Conteo de 154 pruebas herméticas. | Actualizado a 155 pruebas herméticas (`155 passed, 1 deselected, 0 failed`). | `docker run ... pytest` | Actualizado al 100% |
| `docs/DEPLOYMENT.md` | Análisis cloud sin referencia a nuevos puertos desacoplados. | Reafirmado dictamen de despliegue local listo y puertos desacoplados para pruebas aisladas. | `docker-compose.yml` | Vigente y documentado |
| `docs/guia_instalacion_otro_pc.md` | Mockup desactualizado de JSON de `/health` y conteo de 154 pruebas. | Actualizado JSON exacto de `/health` (`{"status":"ok","phase":"mvp","db":{"connected":true,"schema_ready":true}}`) y 155 pruebas. | `http://localhost:8000/health` | Actualizado y verificado |
| `docs/checklist_rubrica.md` | Referencia a `generate_synthetic_evidence_png` obsoleta de prototipo anterior. | Sustituida por catálogo fotográfico fotorrealista `DEMO_ASSETS_DIR` y Content-Addressed Storage. | `backend/app/seed.py` | Corregido y conforme |
| `docs/guion_sustentacion.md` | Mención de modelos placeholder (`Gemini 2.5 Flash`, `Llama 4`). | Sustituida por la cadena real configurada: `Gemini 3.8 Flash` → `Groq Qwen 3.8 27B` → `Gemini 3.5 Flash Lite`. | `backend/app/config.py` | Sincronizado con `.env.example` |
| `docs/decisiones.md` | Contenía enlaces absolutos `file:///c:/Users/...`. | Reemplazados todos los enlaces por rutas relativas portables. | `grep / Select-String` | Limpio y portable |
| `docs/auditoria_codex.md` | Contenía enlaces absolutos `file:///c:/Users/...`. | Reemplazados todos los enlaces por rutas relativas portables. | `grep / Select-String` | Limpio y portable |
| `docs/estado.md` | Registraba hasta el pulido UI y hotfix Paint. | Incorporado el ciclo completo CIVIA 1.0 de cierre definitivo (veracidad, privacidad, clon limpio y documentación). | `docs/estado.md` | Completo y cronológico |
| `docs/entrega_final.md` | Conteo de 154 pruebas; sin matriz de documentación. | Actualizado a 155 pruebas herméticas; incorporada la Matriz de Correspondencia Documental. | Repositorio completo | Versión oficial definitiva |

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
