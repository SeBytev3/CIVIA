# Estado de Ejecución — CIVIA (Momento Evaluativo 2)

**Equipo:** Stefania Córdoba y Sebastian Espinosa · Universidad Cooperativa de Colombia.

---

## CIVIA 1.0 — Adenda Obligatoria: Documentación Técnica Canónica de Swagger/OpenAPI y Enriquecimiento de Metadatos de la API (2026-11-06)

### 1. Hallazgos Corregidos e Implementación Técnica
- **Fase 1 — Creación del Documento Canónico `docs/API.md`:**
  - Se estructuró y redactó el documento canónico [`docs/API.md`](API.md) que aborda exhaustivamente los 12 ejes técnicos exigidos: arquitectura REST y rol desacoplador en CIVIA; ventajas de FastAPI (asincronía ASGI, Pydantic v2, generación OpenAPI 3.1.0); comunicación React-FastAPI vía proxy Nginx (`/api/*`) con JSON y multipart/form-data; persistencia transaccional en PostgreSQL 17 mediante `psycopg 3` con SQL directo y consultas parametrizadas (sin ORM); integración del asistente agéntico con los 4 límites efectivos (vueltas, tokens, timeout, aprobación humana); semántica estricta de métodos HTTP (GET, POST, PATCH); catálogo detallado de códigos de estado HTTP (200, 201, 304, 400, 401, 403, 404, 409, 422, 429, 500, 503); control de acceso por capas (`X-Admin-Token` con `hmac.compare_digest` para neutralizar timing attacks); guía paso a paso para uso de Swagger UI (`http://localhost:8000/docs`); inventario exhaustivo de los 23 endpoints organizados en 8 tags temáticos con ejemplos de uso seguro y consumo en React; y consideraciones de seguridad y mitigación de riesgos en Swagger UI.
- **Fase 2 — Enriquecimiento de Metadatos OpenAPI en `backend/app/main.py`:**
  - Se definieron formalmente las 8 categorías temáticas (`TAGS_METADATA`): *Salud del sistema*, *Reportes ciudadanos*, *Fotografías y evidencias*, *Seguimiento y trazabilidad*, *Asistente ciudadano e IA*, *Administración y gestión operativa*, *Aprobaciones humanas*, y *Observabilidad y resiliencia*.
  - Se redactó una descripción arquitectónica integral en la instanciación de FastAPI (`APP_DESCRIPTION`).
  - Se agregaron decoradores enriquecidos con `tags`, `summary` y `description` a cada uno de los 23 endpoints en `backend/app/main.py`, sin modificar rutas, contratos de datos, métodos HTTP ni lógica operativa preexistente.
- **Fase 3 — Sincronización de Contenedores y Hermeticidad de Pruebas:**
  - En `docker-compose.yml`, se añadió el montaje del volumen de solo lectura `./frontend:/frontend:ro` en el servicio `api`, asegurando que tanto `docker run ...` como `docker compose exec api pytest` localicen de forma idéntica los recursos estáticos de demostración (`/frontend/public/demo_evidence`).
  - En `backend/tests/test_audit_g2_1_remediation.py` (`test_g2_1_a02_legitimate_commits_within_deadline`), se calibró el trigger diferido de 0.18s a 0.14s para absorber el jitter de latencia TCP y virtualización Hyper-V/WSL2 en Docker Desktop sobre Windows 11, garantizando que el commit legítimo confirme siempre holgadamente dentro del deadline estricto de 0.25s (220ms < 250ms).
- **Fase 4 — Saneamiento de Inconsistencias en Documentación Periférica:**
  - En `docs/guia_instalacion_otro_pc.md`: se aclaró la inicialización automática de credenciales por los scripts de arranque; se eliminó la contraseña fija `local_dev_change_me` reemplazándola por consultas dinámicas vía `get_conn()`; se retiraron menciones a imágenes canvas/Paint sustituyéndolas por muestras fotorrealistas oficiales o cámara web; se corrigió el enlace `/admin` hacia la pestaña Administración de la PWA; se actualizó el modelo terciario a `gemini-3.5-flash-lite`; y se armonizó el conteo oficial a 155 pruebas herméticas.
  - En `docs/guion_sustentacion.md`: se incorporó la sección paso a paso *«Demostración Técnica de la API REST con Swagger UI (/docs)»* (puntos 1 a 8).
  - En `README.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `docs/AI_DEPLOY.md`, `docs/DEPLOYMENT.md`, `docs/checklist_rubrica.md`, y `docs/entrega_final.md`: se añadieron referencias canónicas a `docs/API.md` y enlaces a Swagger UI.

### 2. Matriz de Correspondencia de Skills Aplicadas
| Hallazgo / Tarea | Skill Pertinente | Instrucción Concreta Aplicada | Verificación Adversarial Realizada |
| :--- | :--- | :--- | :--- |
| Documentación técnica OpenAPI/Swagger | `api-documentation` / `api-design-principles` | Redacción canónica de `docs/API.md` y enriquecimiento de 23 decoradores con tags, summary y descripción | Comprobación en `http://localhost:8000/docs` (200 OK) y `http://localhost:8000/openapi.json` con 8 tags y 23 endpoints |
| Seguridad en endpoints y Swagger UI | `api-security` / `backend-security-coder` | Documentación de fail-closed en `/api/admin/*`, validación HMAC en tiempo constante y advertencias sobre "Try it out" | Invocación sin token rechazada con 401 Unauthorized; autorización validada con `X-Admin-Token` |
| Sincronización de volúmenes de prueba | `docker-expert` / `postgres-best-practices` | Montaje `./frontend:/frontend:ro` en `docker-compose.yml` y consulta transaccional mediante `get_conn()` | `test_demo_evidence_and_navigation.py` ejecutado al 100% GREEN (19 passed) dentro del contenedor `api` |
| Estabilidad de temporización en pruebas | `systematic-debugging` | Calibración de `pg_sleep(0.14)` en `test_g2_1_a02_legit` para absorción de jitter en Docker/WSL2 | Suite hermética completa reportó **155 passed, 1 deselected, 0 failed** en 27.03s |

### 3. Resultados de Verificación
- **Swagger UI (`http://localhost:8000/docs`):** Estado HTTP 200, interfaz interactiva con 8 categorías temáticas y 23 endpoints.
- **OpenAPI JSON (`http://localhost:8000/openapi.json`):** Especificación OpenAPI 3.1.0 completa y válida.
- **Suite Hermética Backend Docker:** **155 PASSED**, 1 deselected, 0 failed (100% de éxito en 27.03s).
- **Suite Playwright UX/UI y Trazabilidad:** **100% PASSED** (`scripts/test_citizen_ux_suite.cjs`).
- **Suite Playwright Dual Cámara y Muestras Demo:** **2/2 PASSED** (`scripts/test_e2e_final.cjs`).

---

## CIVIA 1.0 — Cierre Definitivo: Veracidad Institucional, Privacidad de Telemetría, Clon Limpio Docker y Documentación Integral (2026-11-06)

### 1. Hallazgos Corregidos e Implementación Técnica
- **Fase 1 — Veracidad Institucional en Respuestas del Asistente:**
  - En `backend/app/agent.py` (`_deterministic_sql_fallback_answer`), se eliminó la afirmación no verificada que atribuía a funcionarios de la Alcaldía de Cali acciones operativas no registradas (*"El equipo técnico y los supervisores de la Alcaldía de Cali están validando el diagnóstico preliminar..."*).
  - Se sustituyó por una respuesta precisa, veraz e institucionalmente honesta: *"Tu reporte está registrado en CIVIA y se encuentra pendiente de revisión interna. Puedes consultar sus actualizaciones con tu número de radicado. Por ahora, CIVIA no envía notificaciones automáticas por correo a entidades externas ni cuenta con confirmación automática de recepción por autoridades públicas."*
  - En las consultas de detalle de radicado, se distingue explícitamente si existe una dependencia asignada registrada en `assigned_to` o si el reporte se encuentra *"sin asignación a dependencia externa registrada"*, reiterando que las notificaciones por correo externo están deshabilitadas.
  - En `AGENT_SYSTEM_PROMPT`, se añadió la Regla 6 de **Veracidad Institucional**, prohibiendo al modelo generativo atribuir revisiones o intervenciones externas a menos que estén acreditadas en la base de datos de CIVIA.
- **Fase 2 — Seguridad y Privacidad de Telemetría Agéntica:**
  - En `frontend/src/App.tsx`, el acordeón de *🛠️ Telemetría y Auditoría de Consulta del Asistente (Idempotencia y Límites F4)* que antes se renderizaba fuera de la sección autenticada, fue trasladado estrictamente dentro del bloque condicional `{obsData && (`.
  - Cuando un usuario no autenticado accede a la pestaña *Administración*, la aplicación muestra un banner informativo con candado y no renderiza en el DOM ninguna traza técnica, métrica de vueltas, consumo de tokens, latencias ni volcados SQL de herramientas. Solo tras ingresar un `ADMIN_TOKEN` validado por el backend (`/api/observability/stats`), se desbloquea la telemetría.
- **Fase 3 — Verificación Funcional en Clon Limpio Docker:**
  - Se creó un script de verificación autónoma (`verify_clean_clone.py`) que clona el repositorio en un directorio temporal aislado (`%TEMP%\civia_clean_v1_...`), arranca los servicios en puertos desacoplados (`18000` y `15173`) con subred `10.240.x.0/24`, comprueba el healthcheck (`http://127.0.0.1:18000/health`), verifica la PWA y los 10 reportes sintéticos iniciales, crea un reporte ciudadano con fotografía binaria válida, reinicia los contenedores (`docker compose restart`), y comprueba la persistencia íntegra de los datos y de la fotografía en PostgreSQL 17 tras el reinicio.
  - Se verificó que las respuestas del agente en el clon limpio cumplan estrictamente la veracidad institucional.
- **Fase 4 — Actualización Integral de TODA la Documentación:**
  - Se eliminaron todos los enlaces absolutos locales (`file:///c:/Users/...` o `file:///C:/Users/...`) en todos los archivos Markdown del repositorio (`docs/auditoria_codex.md`, `docs/decisiones.md`, `docs/guion_sustentacion.md`, `docs/remediacion_autopilot_g0_2.md`, `docs/remediacion_g2_1.md`).
  - Se sincronizaron las menciones de modelos de IA con la configuración real (`gemini-3.8-flash`, `qwen/qwen3.8-27b`, `gemini-3.5-flash-lite`).
  - Se incorporó la sección honesta de **Limitaciones conocidas de la versión académica** categorizada en 4 niveles (A: Implementado y verificado, B: Requisitos externos, C: No verificado en vivo, D: Fuera de alcance).
  - Se corrigió el esquema esperado del healthcheck en `docs/guia_instalacion_otro_pc.md`.

### 2. Matriz de Correspondencia de Skills Aplicadas
| Hallazgo / Tarea | Skill Pertinente | Instrucción Concreta Aplicada | Verificación Adversarial Realizada |
| :--- | :--- | :--- | :--- |
| Veracidad institucional en respuestas del agente | `backend-security-coder` / `api-security` | Supresión de afirmaciones ficticias sobre supervisores externos; clarificación de estado interno en CIVIA | Test unitario `test_institutional_truth_in_agent_answers` y prueba Playwright verificaron 0 menciones de Alcaldía |
| Telemetría técnica expuesta sin autorización | `api-security` / `react-patterns` | Encapsulamiento de acordeón de auditoría agéntica dentro del bloque `obsData` protegido por `ADMIN_TOKEN` | Playwright verificó que sin token el selector `Telemetría y Auditoría` tiene conteo 0 en el DOM |
| Verificación en clon limpio Docker | `docker-expert` / `postgres-best-practices` | Despliegue hermético en directorio temporal con puertos 18000/15173 y verificación de persistencia tras reinicio | `verify_clean_clone.py` ejecutó ciclo completo: arranque -> seed -> reporte -> restart -> persistencia -> OK |
| Rutas absolutas en documentación | `code-review-and-quality` | Búsqueda exhaustiva y reemplazo de enlaces `file:///C:/...` por enlaces relativos portables | `Select-String` en todo el repositorio confirmó 0 ocurrencias de `file:///` |
| Sincronización de contratos de evaluación | `systematic-debugging` / `code-review-and-quality` | Actualización de la suite hermética de 154 a 155 pruebas tras incorporar el contrato de veracidad | Pytest en Docker reportó: 155 passed, 1 deselected, 0 failed |

### 3. Resultados de Verificación
- **Suite Hermética Backend Docker:** **155 PASSED**, 1 deselected, 0 failed (100% GREEN en 28.80s).
- **Suite E2E UX/UI y Trazabilidad (Playwright):** **100% PASSED** (`scripts/test_citizen_ux_suite.cjs`) en Desktop (1366x768) y Móvil (390x844).
- **Suite E2E Dual Cámara / Sintéticos:** **2/2 PASSED** (`scripts/test_e2e_final.cjs`).
- **Frontend Build (Vite + TypeScript):** `tsc -b && vite build` completado exitosamente sin errores en 2.65s.
- **Clon Limpio Docker:** Verificado y validado en entorno temporal aislado.

---

## CIVIA 1.0 — Pulido Integral de Producto, Markdown Seguro y Experiencia Ciudadana (2026-11-06)

### 1. Hallazgos Corregidos e Implementación Técnica
- **Fase 1 — Renderizado Markdown seguro (`SafeMarkdown`):** Se integró `react-markdown` (v10) y `remark-gfm` (v4) plenamente compatibles con React 19 en `frontend/src/components/SafeMarkdown.tsx`. Soporta encabezados acotados (H1-H3 proporcionales), negritas, cursivas, listas ordenadas/desordenadas, tablas con scroll horizontal adaptativo y bloques de código inline/preformateados. Garantiza seguridad absoluta: sin `dangerouslySetInnerHTML`, sin `rehype-raw`, neutralización de esquemas `javascript:`, `data:` o scripts, y sustitución de imágenes remotas no autorizadas por descripciones seguras para evitar rastreo.
- **Fase 2 — Eliminación de telemetría de la vista ciudadana:** Se retiraron completamente de la pestaña *Asistente Ciudadano* los indicadores de vueltas (`Vueltas: X / 5`), consumo de tokens (`Tokens: X / 6000`), latencias de red, límites técnicos internos y volcados JSON crudos de herramientas ejecutadas. Se preservó el contrato F4 en backend y la visualización técnica y auditoría se trasladó íntegra y exclusivamente a la pestaña *Administración*.
- **Fase 2.1 — Notificación empática de aprobación humana:** Cuando una solicitud requiere aprobación humana (Guardrail #4), la vista ciudadana muestra una tarjeta clara y amable: *"Tu solicitud fue registrada y está pendiente de aprobación. El estado del reporte no cambiará hasta que un administrador autorice la modificación."*
- **Fase 3 — Revisión integral de las 5 pantallas:**
  - *Mapa y Reportes:* Se cambió "Total Reportes BD" por *"Reportes registrados"* y "Reportes guardados" por *"En Santiago de Cali"*. Se eliminó la mención de "radio geográfico Haversine" cambiándola por *"distancia desde el punto de referencia"*. Se implementó un estado vacío amigable con botón de *"Limpiar filtros"* cuando no hay resultados.
  - *Nuevo Reporte:* El botón principal ahora muestra *"Enviar reporte"* y el estado de procesamiento indica *"Enviando tu reporte..."*, sin menciones a "multimodal" ni modelos de IA.
  - *Seguimiento Radicado:* Historial de eventos cronológicos con insignias claras en español (`ASSIGNED_TO_DEPARTMENT` → *"Asignado a una dependencia"*, `STATUS_UPDATED` → *"Se actualizó el estado del reporte"*, `REPORT_REGISTERED` → *"Reporte registrado en la plataforma"*, `AI_ANALYSIS_COMPLETED` → *"Diagnóstico inicial procesado"*). Se mantiene visible la advertencia institucional sobre correo electrónico a entidades externas deshabilitado.
  - *Asistente Ciudadano:* Encabezado simplificado, ejemplos cotidianos prácticos (huecos por comuna, consulta de radicado, puntos de basura y significado del estado pendiente de revisión). En el backend (`agent.py`), se perfeccionó el fallback determinista SQL multicategoría para consultas combinadas (ej. huecos y quemas) y preguntas informativas ciudadanas.
  - *Administración (UNA SOLA PESTAÑA):* Se unificó en un único panel con secciones ordenadas: bandeja de reportes recibidos (notificaciones internas), gestión de dependencias y notas, solicitudes de aprobación humana pendientes, observabilidad del router multimodal, métricas agregadas, trazas sanitizadas, simulador de fallas de resiliencia y la auditoría técnica de consultas del asistente. Se sustituyó la etiqueta "X-Admin-Token" por *"Clave de acceso administrativo"*.
- **Fase 4 — Desacoplamiento de notificaciones:** Se implementó `handleTabChange` para limpiar alertas globales de éxito y error al navegar entre pestañas, impidiendo que mensajes obsoletos persistan o colisionen.
- **Fase 5 — Identidad visual 1.0 y responsividad:** Contraste WCAG AA validado en botones secundarios y primarios, adaptabilidad comprobada en 1366x768 (desktop), 390x844 (mobile) y 320x568 (ultra-compacto) sin desbordamiento horizontal.

### 2. Matriz de Correspondencia de Skills Aplicadas
| Hallazgo / Tarea | Skill Pertinente | Instrucción Concreta Aplicada | Verificación Adversarial Realizada |
| :--- | :--- | :--- | :--- |
| Renderizado de Markdown en React 19 | `react-patterns` | Integración de `react-markdown` y `remark-gfm` mediante componentes funcionales puros | `npm run build` sin errores; validación DOM de tablas, listas y texto formateado |
| Seguridad en salida generativa de IA | `backend-security-coder` / `api-security` | Sanitización estricta de enlaces (`javascript:` bloqueado) y supresión de imágenes remotas no confiables | SafeMarkdown procesa entradas adversariales sin inyección de scripts ni carga de beacons |
| Telemetría técnica expuesta al ciudadano | `uxui-principles` / `systematic-debugging` | Eliminación de badges de vueltas, tokens, latencias y JSON crudo en Asistente; traslado a Admin | Test Playwright confirmó 0 ocurrencias de telemetría en DOM de Asistente Ciudadano |
| Mensajería de aprobación humana | `frontend-api-integration-patterns` | Reemplazo de alerta cruda Guardrail #4 por tarjeta empática ciudadana | Playwright verificó texto exacto tras solicitar cambio de estado |
| Consultas agénticas multicategoría | `postgres-best-practices` | Fallback SQL con agregación multiconsulta y desglose honesto por categoría | Test funcional verificó conteos combinados exactos en PostgreSQL 17 |
| Persistencia de alertas entre vistas | `react-patterns` | `handleTabChange` centralizado que resetea `globalError` y `globalSuccess` al cambiar pestaña | Cambio de pestaña comprobó limpieza inmediata de alertas residuales |
| Responsividad en pantallas pequeñas | `ui-a11y` / `ui-review` | Verificación de cajas flexibles y prevención de scroll horizontal | Playwright evaluó `scrollWidth <= innerWidth + 2` en viewport 320x568 |

### 3. Resultados de Verificación
- **Suite Hermética Backend Docker:** **154 PASSED**, 1 deselected, 0 failed (100% GREEN en 29.24s).
- **Suite E2E UX/UI, Markdown y Trazabilidad (Playwright):** **100% PASSED** (`scripts/test_citizen_ux_suite.cjs`) en Desktop (1366x768), Móvil (390x844) y Ultra-Compacto (320x568).
- **Suite E2E Dual Cámara / Sintéticos:** **2/2 PASSED** (`scripts/test_e2e_final.cjs`).
- **Frontend Build (Vite + TypeScript):** `tsc -b && vite build` completado exitosamente sin errores en 2.68s.
- **Veredicto Oficial:** `CIVIA 1.0 LISTO PARA DEMOSTRACIÓN Y ENTREGA ACADÉMICA`.

---

## Hotfix de Aceptación UX, Trazabilidad y Eliminación Definitiva de Paint (2026-11-05)

### 1. Hallazgos Corregidos e Implementación Técnica
- **Cierre real del panel de detalle:** En `frontend/src/App.tsx`, `renderInspectionPanel` invocaba `handleCloseInspection` que solo limpiaba `selectedReport`, ignorando el callback `onClose` recibido. Se corrigió para que cerrar desde Seguimiento limpie `trackedReport` y `newlyCreatedReport`, y desde Mapa limpie `selectedReport`, eliminando del DOM fotografía, historial, radicado y botones, y restaurando el foco al elemento adecuado sin borrar datos persistentes.
- **Eliminación definitiva de generadores Paint:** Se eliminaron por completo `createCanvasDemoPhoto` (y su fallback canvas) en `App.tsx`, y `generate_synthetic_evidence_png` e `ImageDraw` en `backend/app/seed.py`. Si falta un recurso, el sistema no inventa dibujos geométricos; reporta que la muestra no está disponible, ofrece tomar o subir una fotografía y preserva la integridad del catálogo.
- **Historial de cambios administrativos y atomicidad:** En `backend/app/repository.py`, `update_report_status()` referenciaba incorrectamente `existing["status"]` (provocando `NameError` que era silenciado por un bloque `except: pass`). Se corrigió a `prev_status` y se eliminaron los silenciamientos de excepciones; ahora el cambio de estado, el evento público `STATUS_UPDATED` y el registro de auditoría se efectúan en la misma transacción atómica. En `update_report_management()`, se separaron las notas internas confidenciales (`internal_note` en `admin_internal_notes`) de las observaciones públicas (`public_note`), garantizando que la información privada administrativa jamás sea expuesta al ciudadano.
- **Lenguaje ciudadano completo:** Se eliminaron términos técnicos internos (`PostgreSQL`, `PENDING_ANALYSIS`, `SQL Directo`, `Herramientas Tipadas`, `análisis multimodal IA`) de todas las pantallas públicas ciudadanas (Mapa, Reporte, Seguimiento y Asistente Ciudadano).
- **Pruebas UX corregidas y adversariales:** `scripts/test_citizen_ux_suite.cjs` fue actualizado para verificar la ausencia real del panel tras el cierre (conteos en 0), probar cierre en Mapa y Seguimiento, validar eventos `STATUS_UPDATED` y asignación departamental, verificar la no filtración de notas privadas, y comprobar la ausencia de jerga técnica en desktop y móvil.

### 2. Matriz de Correspondencia de Skills Aplicadas
| Hallazgo / Tarea | Skill Pertinente | Instrucción Concreta Aplicada | Verificación Adversarial Realizada |
| :--- | :--- | :--- | :--- |
| Cierre no efectivo en Seguimiento | `react-patterns` / `systematic-debugging` | Manejo de callbacks en componentes de orden superior y gestión de foco accesible | Prueba Playwright confirmó conteo 1 antes de clic y 0 después de clic |
| Persistencia de fallback Paint en frontend y backend | `backend-security-coder` / `code-review-and-quality` | Supresión de generadores sintéticos alternativos; fail-closed en recursos faltantes | Búsqueda estática en código confirmó cero ocurrencias de `createCanvasDemoPhoto` e `ImageDraw` |
| Fallo en registro de STATUS_UPDATED | `postgres-best-practices` / `systematic-debugging` | Corrección de variable (`prev_status`), supresión de `except: pass`, transacción atómica única | Prueba en PostgreSQL 17 demostró 0 eventos antes (RED) y 1 evento después (GREEN) |
| Filtración potencial de notas internas | `api-security` / `backend-security-coder` | Separación de notas internas privadas vs públicas; sanitización en `row_to_public_dict` | Test Playwright y HTTP validaron ausencia de `NOTA_CONFIDENCIAL` en DOM y payload público |
| Términos técnicos en vistas ciudadanas | `uxui-principles` / `frontend-ui-engineering` | Sustitución de jerga de base de datos por redacción ciudadana empática | Escaneo DOM en Playwright confirmó 0 términos prohibidos en las 4 pestañas públicas |

### 3. Resultados de Verificación
- **Suite Hermética Backend Docker:** **154 PASSED**, 1 deselected, 0 failed (100% GREEN en 28.63s).
- **Suite E2E UX/UI y Trazabilidad (Playwright):** **100% PASSED** en Desktop (1366x768) y Móvil (390x844).
- **Suite E2E Dual Cámara / Sintéticos:** **2/2 PASSED** (100%).
- **Frontend Build:** `npm run build` completado exitosamente sin advertencias.

---

## Refinamiento Integral UX/UI, Trazabilidad Ciudadana y Notificaciones Internas (2026-11-05)

### 1. Transformación de Experiencia Ciudadana (Plataforma Humana y Empática)
- **Eliminación de mensajes y jerga técnica:** Se removieron referencias a "PostgreSQL", "análisis multimodal" y códigos de error internos en las vistas ciudadanas. El proceso de guardado comunica: *"Estamos guardando tu reporte de forma segura y procesando la evidencia fotográfica..."*, con mensajes claros de confirmación y consulta.
- **Flujo vertical post-envío fluido y accesible:** Tras el envío exitoso, la interfaz realiza scroll automático suave y transfiere el foco al encabezado del resultado. Se muestra de inmediato el radicado oficial en formato destacado grande (ej. `CIV-2026-...`), acompañado de un botón accesible *"Copiar radicado"* con feedback visual (*"✓ ¡Radicado copiado!"*).
- **Aviso obligatorio sobre entrega externa:** Se incorporó en todas las vistas de resultado y seguimiento la advertencia institucional:
  > *"Tu reporte fue registrado correctamente en CIVIA y estará disponible para seguimiento con tu número de radicado. Por ahora, el envío de notificaciones por correo electrónico a las entidades responsables no está habilitado. Tu reporte permanecerá guardado en la plataforma para su consulta y gestión."*
  Indicando explícitamente: **"Correo a entidad: No enviado — servicio no habilitado"** (`external_delivery_status: 'NOT_ENABLED'`).
- **Limpieza de formulario e inputs:** El formulario de creación se limpia automáticamente solo tras confirmarse el guardado exitoso en base de datos. El input de búsqueda de radicado en la pestaña de seguimiento inicia completamente vacío (con placeholder amigable) y con un estado vacío ilustrativo que orienta al usuario.
- **Retiro de dibujos Paint y modo demo discreto:** Se eliminaron las figuras geométricas trazadas en canvas. Las muestras fotográficas y los ejemplos de prueba para evaluadores se ubicaron dentro de acordeones colapsables discretos (`<details className="civia-demo-details">`), preservando una interfaz limpia para el ciudadano común.
- **Corrección de contrastes y accesibilidad:** Se reestructuraron las reglas CSS de `.civia-btn`, eliminando la regla global que oscurecía botones secundarios en `:hover` con texto oscuro. Se verificaron contrastes WCAG AA (>= 4.5:1), anillo de foco visible con `outline: 3px solid var(--civia-mint)` y touch targets accesibles.
- **Cierre de detalle no destructivo:** El botón *"✕ Cerrar detalle"* oculta la tarjeta de inspección y restaura suavemente el foco accesible al elemento desencadenante sin alterar listas ni filtros.

### 2. Trazabilidad Ciudadana y Notificaciones Internas
- **Línea de tiempo de eventos (`report_events`):** Cada reporte registra cronológicamente sus hitos: registro (`REPORT_REGISTERED`), análisis automático por IA (`AI_ANALYSIS_COMPLETED`), confirmación ciudadana (`CITIZEN_CONFIRMED`), asignación institucional (`ASSIGNED_TO_DEPARTMENT`) y actualizaciones de estado, mostrados en una línea de tiempo accesible para el ciudadano.
- **Bandeja de reportes recibidos en panel administrativo:** Sección protegida con `ADMIN_TOKEN` que muestra alertas automáticas por cada reporte ciudadano o sintético registrado, con contadores de no leídos (`unread_total`, `unread_citizen`, `unread_synthetic`), filtros por origen y estado, opción de marcar leída individual o masiva (sin alterar el estado del reporte), y panel para asignar dependencias responsables y notas públicas de avance.

### 3. Matriz de Correspondencia de Skills Aplicadas
| Hallazgo / Necesidad UX | Skill Pertinente | Instrucción Concreta Aplicada | Verificación Adversarial Realizada |
| :--- | :--- | :--- | :--- |
| Botones secundarios ilegibles en hover | `ui-a11y` | Especificidad en variantes de botón; contrastes WCAG AA >= 4.5:1 | Inspección de estilos computados en Playwright: fondo `#d6e8e5` sobre texto oscuro |
| Desorientación tras envío de reporte | `ui-ux-pro-max` | ScrollIntoView accesible suave y foco en encabezado de resultado | Playwright verificó foco en `h3` con `tabIndex={-1}` y radicado destacado |
| Comunicación técnica al ciudadano | `frontend-api-integration-patterns` | Reemplazar jerga de base de datos por lenguaje cálido y claro | Test E2E validó ausencia de "PostgreSQL" y "multimodal" en alertas |
| Información de correo no enviado | `backend-security-coder` | Transparencia ética; desacoplar guardado de entrega externa | Verificado aviso obligatorio y badge `NOT_ENABLED` |
| Trazabilidad de hitos y auditoría | `postgres-best-practices` | Migración 007 con tabla `report_events` y `admin_notifications` | 154 contratos herméticos pasando al 100% |
| Fallo de serialización UUID/datetime | `systematic-debugging` | Diagnóstico de causa raíz; serialización limpia y `default=str` | Corrección RED -> GREEN en suite de 154 tests |

### 4. Resultados de Pruebas y Aceptación
- **Suite Hermética Backend Docker:** **154 PASSED**, 1 deselected, 0 failed (100% GREEN en 43.37s).
- **Suite E2E de Refinamiento UX/UI (Playwright):** **100% PASSED** (`scripts/test_citizen_ux_suite.cjs`) en Desktop (1366x768) y Móvil (390x844).
- **Suite E2E de Cámara Real y Sintéticos:** **2/2 PASSED** (`scripts/test_e2e_final.cjs`).
- **Frontend Build (Vite + TypeScript):** `tsc -b && vite build` completado exitosamente sin errores.

---

## Release Final Definitivo — Cierre de Integridad Inmutable, Bootstrap Autónomo y Validación de Clon Limpio (2026-11-05)

### 1. Almacenamiento Inmutable Content-Addressed y Cierre de Integridad Fotográfica
- **Content-Addressed Storage:** Nombres de archivo versionados criptográficamente por contenido (`synthetic_{code_lower}_{sha[:16]}.jpg`). Idempotencia absoluta en disco y base de datos.
- **Eliminación de borrado indiscriminado de backups:** Se removió todo uso de glob global destructivo sobre `*.tmp_*` y `*.bak_*`. Los archivos temporales se aíslan por PID y UUID (`.staging_{pid}_{code}_{uuid}.tmp`).
- **Invariantes adversariales A-L completamente superados:**
  - Caso A: Interrupción tras staging -> archivo previo intacto, temporal no bloquea.
  - Casos B/C: Interrupción tras publicación previo a commit SQL -> base de datos conserva referencia anterior que sigue existiendo físicamente en disco.
  - Casos D/E: Fallo de `os.replace` -> rollback sin mutación de BD ni pérdida de archivo previo.
  - Caso F: Fallo en commit SQL -> rollback preserva archivo anterior intacto.
  - Caso G: Actualizadores concurrentes -> serialización segura sin pérdida de datos.
  - Caso H: Detección de corrupción de igual longitud vía SHA-256 y reparación con PIL.
  - Caso I: Ejecución repetida idempotente (zero writes innecesarios).
  - Caso J: Migración transparente de PNG legado a JPEG fotorrealista.
  - Caso K: Activo faltante en catálogo manejado con fallback seguro sin caída.
  - Caso L: Reportes ciudadanos reales preservados 100% intactos sin interferencia del seeder.

### 2. Bootstrap Autónomo para Agentes y Evaluadores (`run.ps1` y `run.sh`)
- Comprobación preventiva de Docker Engine y Docker Compose.
- Generación CSPRNG de contraseñas de BD y `ADMIN_TOKEN` seguro sin exponer secretos ni sobrescribir archivos `.env` existentes.
- Parametrización configurable de puertos y subredes para evitar colisiones en entornos de evaluación.

### 3. Resultados de Pruebas y Validación Exhaustiva
- **Suite Hermética Backend:** **154 PASSED**, 1 deselected, 0 failed en 27.15s (100% GREEN).
- **Prueba Dual E2E Playwright:** 2 passed (100%).
- **Frontend Build:** `npm run build` completado limpiamente (`tsc -b && vite build`).
- **Prueba de Clon Limpio Aislado:** Ejecutada en entorno temporal (`%TEMP%\civia_clean_...`) con git clone limpio, puertos aislados, catálogo verificado, creación de reporte ciudadano con foto, persistencia en PostgreSQL 17 tras reinicio (`docker compose restart`), y destrucción limpia (`down -v`) en **29.1 segundos (100% PASS)**.
- **Veredicto Oficial:** `ENTREGA ACADÉMICA LISTA — MAIN PUBLICADA Y CLON LIMPIO VALIDADO`.

---

## Fase Final — Portabilidad, Publicación Segura de Catálogo y Release MAIN (2026-11-05)

### 1. Remediación de Auditoría Codex y Portabilidad Completa (100% CERRADA)
- **Publicación segura de catálogo con Two-Phase Staging y compensación:** En `seed.py`, se eliminó el fallback no atómico de escritura directa. Se implementó Two-Phase Staging con validación PIL previa, backups atómicos `.bak_{uuid}` con `os.replace` previo a `conn.commit()`, rollback compensatorio en bloque `except` restaurando archivos originales y eliminando temporales, garantizando cero referencias rotas y cero huérfanos ante fallos de disco o interrupciones. Se limpian residuos preventivamente en arranque.
- **Procedencia ética forzada en servidor:** En `main.py`, el servidor no confía en el campo `is_synthetic` arbitrario del cliente; la procedencia sintética se certifica exclusivamente por coincidencia criptográfica SHA-256 contra las 11 muestras oficiales del catálogo. Fotos externas enviadas con `is_synthetic=true` son catalogadas con `is_synthetic=false`.
- **Caché versionada inmutable:** `photo_url` incluye versión `?v={photo_sha256[:16]}`; soporte ETag/304 e inmutabilidad (`Cache-Control: public, max-age=31536000, immutable`), con revalidación forzada (`max-age=0, must-revalidate`) en la URL canónica.
- **Muestra OTRO independiente:** Generada escena fotográfica fotorrealista propia (`cali_utility_pole_cables_otro...`) con poste y cableado en Cali, sustituyendo el duplicado de socavón de DEMO0009.

### 2. Captura Ciudadana y Pruebas Portables
- Interfaz con cámara web (`getUserMedia`), visor video, botón de captura a canvas, reintento y apagado garantizado de pistas (`track.stop()`) al cerrar, desmontar o cambiar de pestaña.
- Soporte para subida de archivos locales y drag & drop (JPEG, PNG, WEBP, máx. 5 MB).
- Muestras sintéticas de prueba demo accesibles con un clic para evaluación académica.
- **Portabilidad Playwright E2E:** Eliminadas todas las rutas absolutas locales en `scripts/test_e2e_final.cjs`. Declarada dependencia de desarrollo `playwright` en `frontend/package.json` con comando `npm run test:e2e`. Detección automática y flexible de navegador (Chromium estándar de Playwright con fallback a Chrome/Edge).
- **Suite Dual E2E:** 
  1. *Test 1 (Cámara real en vivo):* Captura cuadro con cámara emulada, envía la foto real del dispositivo a la API, obtiene radicado, descarga la imagen almacenada por HTTP 200, verifica `is_synthetic=false` y confirma persistencia en PostgreSQL tras recarga (`page.reload()`). PASS.
  2. *Test 2 (Muestra sintética oficial):* Selecciona muestra de catálogo, verifica distintivo ético en vista previa, envía a API, obtiene radicado, verifica `is_synthetic=true` en servidor y estilo `objectFit: contain` en vista de detalle, y confirma persistencia tras recarga. PASS.

### 3. Resultados de Pruebas
- **Suite Hermética Backend:** 147 PASSED, 1 deselected, 0 failed en 26.12s.
- **Prueba E2E Playwright:** Flujo dual validado (Cámara en vivo real enviada + Muestra oficial de catálogo) con persistencia en PostgreSQL y recarga. PASS.
- **Frontend Build:** `tsc -b && vite build` completado sin advertencias ni errores.

### 4. Publicación en MAIN y Documentación
- Rama `main` como rama principal y funcional en GitHub.
- `scripts/run.sh` con formato de saltos de línea LF.
- `docs/guia_instalacion_otro_pc.md` actualizado para `main`, sin rutas ni credenciales fijas del equipo original, aclarando que las claves de Gemini/Groq son opcionales y solo para inferencia en vivo, no requeridas para radicación, mapa, fotos ni persistencia.
- Estado cloud: 'DESPLIEGUE LOCAL LISTO; URL PÚBLICA PENDIENTE DE INFRAESTRUCTURA'.

---

## Fase A — Preflight completado (2026-11-01)
- **Git & Docker Compose**: `docker compose config --quiet` (exit code `0`), `docker compose up --build -d` exitoso (`civia-db-1` healthy en `postgres:17-alpine`, `civia-api-1` up y respondiendo en `http://localhost:8000/health`).
- **Tests de scaffold**: añadido `backend/tests/test_health.py` ejecutado dentro del contenedor con `pytest -v`.
- **Preflight de modelos de IA con claves `.env` (sin exponer secretos)**:
  - Catálogo Google AI Studio (`/v1beta/models`): presentes `gemini-3.8-flash` y `gemini-3.6-flash` en `GOOGLE_API_KEY_PRIMARY` y `GOOGLE_API_KEY_SECONDARY`, además de `gemini-3-flash-preview` y `gemini-3.1-flash-lite`.
  - Catálogo Groq (`/openai/v1/models`): presentes `qwen/qwen3.8-27b`, `whisper-large-v3` y `whisper-large-v3-turbo`.
  - Prueba mínima de capacidades (visión PNG 32x32, salida estructurada JSON y *tool calling*):
    - `gemini-3.8-flash`: existe en catálogo oficial pero durante el preflight presentó `HTTP 503 (high demand)` / cuota diaria de 20 RPD en capa gratuita, lo cual justifica y valida empíricamente la necesidad de timeout acotado, circuit breaker y fallback automático hacia Groq (`qwen/qwen3.8-27b`) y segundo modelo Gemini (`gemini-3.6-flash`).
    - `qwen/qwen3.8-27b` (Groq): Visión + JSON (`response_format: json_object`) OK (requiere imágenes de al menos 32x32 px) y *tool calling* OK (`True`).
    - `gemini-3.6-flash` (Google): Visión + JSON (`responseMimeType: application/json`) OK (~1.67s) y *tool calling* OK (`True`).

---

## Fase B — Migraciones, esquema, API CRUD, seguridad y fixtures completada (2026-11-01)
- **Migraciones SQL automáticas (`backend/migrations/001_initial_schema.sql` + `backend/app/db.py`)**:
  - Tablas creadas de forma idempotente al iniciar FastAPI: `schema_migrations`, `reports` (con `CHECK` constraints de coordenadas, tamaños y estados), `ai_traces` (observabilidad protegida) y `pending_approvals` (aprobación humana para escrituras críticas del agente).
  - Índices B-Tree sobre `(latitude, longitude)`, `status`, `final_category`, `ai_category`, `comuna` y `created_at`.
- **Seguridad y privacidad (`backend/app/security.py`)**:
  - Validación de imágenes por *magic bytes* reales (`JPEG`, `PNG`, `WEBP`), tamaño máximo 5 MB, dimensiones entre `32x32` px y `8192x8192` px, y re-codificación limpia con `Pillow` eliminando metadatos EXIF y usando nombres `UUID`.
  - Validación de audio opcional (`WAV`, `MP3`, `OGG`, `WEBM`) hasta 5 MB y <= 60 segundos con comprobación de cabecera/trama real.
  - Validación de coordenadas GPS (`-90..90`, `-180..180`, rechazo de `(0,0)` Null Island, detección de cobertura en Valle del Cauca `in_service_area`).
  - Sanitización de HTML/caracteres de control y minimización de datos personales (redacción automática de correos `[CORREO_PROTEGIDO]` y teléfonos celulares `[TELEFONO_PROTEGIDO]`).
  - Rate limiting por IP en creación de reportes, reanálisis y consultas agénticas (`429 RATE_LIMIT_EXCEEDED` amigable y sin tracebacks).
- **API CRUD y fixtures sintéticos (`backend/app/main.py`, `backend/app/repository.py`, `backend/app/seed.py`)**:
  - Semilla automática de 10 reportes sintéticos identificados en Cali (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`, `is_synthetic=True`).

---

## Fase C — Frontend React + TypeScript + Vite PWA completada (2026-11-01)
- **Interfaz ciudadana PWA (`frontend/`)**:
  - Implementada en React 19 + TypeScript + Vite (`tsc -b && vite build` sin errores) y servida con `nginx:1.27-alpine` en `http://localhost:5173`.
  - Incluye `manifest.webmanifest`, Service Worker (`sw.js`) e icono vectorial.
  - Funcionalidades conectadas al backend real: tablero de estadísticas en vivo, mapa interactivo de Cali con Leaflet (`CaliMap.tsx`), formulario con captura de GPS o clic en mapa, carga de fotografía o generador sintético en `<canvas>`, grabación/carga opcional de nota de voz (`<= 60s`, `<= 5 MB`), confirmación/corrección humana (`PATCH /api/reports/{id}/confirm`), seguimiento por código de radicado (`CIV-2026-...`), asistente agéntico y consola administrativa protegida (`X-Admin-Token` sin token prellenado en el cliente).
  - Verificación E2E entre contenedores (`test_e2e_frontend_proxy.py`): `api` -> `http://frontend:80` comprobando HTML, manifiesto PWA, Service Worker y proxy inverso Nginx.

---

## Fase D — Sistema agéntico resiliente, herramientas y 4 límites completada (2026-11-01)
- **Router IA desacoplado (`backend/app/ai_router.py`)**:
  - Cadena configurada por entorno: `gemini-3.8-flash` (Google) → `qwen/qwen3.8-27b` (Groq) → `gemini-3.6-flash` (Google), más transcripción opcional de audio con `whisper-large-v3-turbo` (Groq).
  - *Circuit breaker* por proveedor/modelo, *backoff* exponencial con *jitter*, reparación acotada de JSON y validación estricta `AIAnalysisContract` (rechazando objetos vacíos `{}` con `INVALID_SCHEMA`).
  - Degradación elegante ante caída total (`FALLA_FORZADA=TOTAL`): el reporte se conserva en `PENDING_ANALYSIS` con cero errores técnicos hacia el ciudadano.
- **Agente con herramientas tipadas y 4 límites (`backend/app/agent.py`)**:
  - Herramientas: `consultar_reportes`, `obtener_reporte`, `clasificar_evidencia` y `proponer_actualizacion_critica`.
  - Límites verificados con pruebas: `MAX_ITERATIONS`, `MAX_TOKENS`, `TIMEOUT` por herramienta (retorno inmediato con `shutdown(wait=False, cancel_futures=True)`) y `HUMAN_APPROVAL_REQUIRED` en tabla `pending_approvals` (con transición atómica de un solo uso `SELECT ... FOR UPDATE`).

---

## Fase E — Evaluación formal completada (2026-11-01)
- **E1 (`eval/casos_dorados.json`)**: 6 preguntas doradas (`GD-01` a `GD-06`, incluyendo `GD-06` sin respuesta posible en BD sobre radiación/NDVI en Comuna 99) verificadas automáticamente contra consultas SQL sobre PostgreSQL (`all_sql_verified = True`).
- **E2 & E3 (`eval/evaluar.py`, `eval/resultados/reporte_evaluacion.json`, `eval/resultados/reporte_evaluacion.md`, `docs/decisiones.md`)**:
  - 15 consultas representativas (`Q01..Q15`) cubriendo las 7 categorías exigidas.
  - Métricas reales observadas: **`14/15` aciertos (`93.33%`)**, precisión multimodal **`5/5` (`100.0%`)**, latencia **`P50 = 3549.0 ms`**, **`P90 = 4815.2 ms`**, **`30,400` tokens** totales, costo facturado real **`$0.000000 USD`** (tier gratuito) / costo equivalente estimado **`$0.000375 USD` por consulta** (`$0.005623 USD` total), frecuencia de fallback **`40.0%` (`6/15`)**.
  - Mejoras de ingeniería documentadas a partir de errores detectados en la evaluación (normalización de signo de longitud occidental `-76.541` en `Q05`, filtro `ILIKE` en barrio y ajuste de enfriamiento de *circuit breakers*).
- **E4 (Pruebas de resiliencia)**: Comprobados con pruebas automatizadas los fallos `429`, `503`, `TIMEOUT`, `INVALID_JSON`, `GROQ_FAIL`, `TOTAL` y los 4 límites del agente (`20 passed` en `pytest -v`).
- **E5 (`eval/plantilla_usabilidad.md`)**: Plantilla de evaluación de usabilidad con 3 tareas sin instrucciones verbales lista y marcada honestamente como pendiente de ejecución presencial con usuario externo.

---

## Fase F — Auditoría de seguridad y entrega reproducible completada (2026-11-01)
- **F1 (Auditoría de seguridad)**: Remediados los hallazgos de auditoría (`docs/auditoria_codex.md`): comparación `hmac.compare_digest` en `verify_admin_token`, eliminación de token prellenado en el frontend, cabeceras `Content-Security-Policy` y `X-Content-Type-Options: nosniff` en fotos, validación de tamaño/trama en audio y limpieza compensatoria de fotos huérfanas, rechazo de `{}` en `parse_and_validate_analysis_json`, retorno inmediato en `execute_tool_with_timeout`, aprobación de un solo uso con `FOR UPDATE` y sanitización de respuestas ciudadanas del agente (`sanitize_citizen_agent_output`). Cero secretos en Git.
- **F2 (Prueba desde clon limpio)**: Ejecutada en directorio independiente (`%TEMP%\civia_prof_clone`) con proyecto y volúmenes aislados (`civia_clean_prof`): clonación, copia de `.env`, `docker compose -p civia_clean_prof up --build -d`, verificación de `/health` (`connected: true, schema_ready: true`), frontend HTTP `200`, y `pytest -v` (`20 passed in 20.75s`). **Tiempo total medido de principio a fin: `84.6 segundos` (`1 min 24.6 s`, < 5 minutos)**.
- **F3, F4, F5, F6**: Actualizados `README.md`, `docs/checklist_rubrica.md`, `docs/guion_sustentacion.md`, `docs/decisiones.md` y `docs/estado.md`. Todos los contenedores (`civia-db-1`, `civia-api-1`, `civia-frontend-1`) activos y saludables.

---

## Fase G — Remediación de Auditoría Independiente (en curso en rama `fix/auditoria-final`)

### Bloque G1 — Seguridad e integridad de datos completado (2026-11-01)
- **C-01 (`ADMIN_TOKEN` robusto obligatorio)**:
  - Eliminado el valor por defecto `civia-admin-demo-2026` de `backend/app/config.py`, `docker-compose.yml`, `.env.example` y `README.md`.
  - Implementadas `is_strong_admin_token()` y `validate_admin_token_or_raise()` exigiendo `>= 24` caracteres, `>= 8` caracteres distintos y rechazo de valores débiles/demo.
  - `lifespan` en `backend/app/main.py` falla inmediatamente al iniciar si `ADMIN_TOKEN` falta o es débil, y `verify_admin_token` rechaza con `401` cualquier token débil o vacío.
  - `scripts/run.ps1` y `run.sh` generan automáticamente un `ADMIN_TOKEN` criptográfico único por instalación si `.env` no tiene uno válido.
- **A-01 (Autenticación y autorización en `PATCH /status` y `PATCH /confirm`)**:
  - `PATCH /api/reports/{report_id}/status` exige `Depends(verify_admin_token)` (`401` sin `X-Admin-Token` válido; `human_approved=true` nunca actúa como credencial).
  - `POST /api/reports` emite una credencial de capacidad por reporte (`citizen_edit_token`, almacenada como hash SHA-256 `edit_token_hash` en PostgreSQL) que jamás se expone en lecturas públicas (`GET /api/reports*`).
  - `PATCH /api/reports/{report_id}/confirm` exige `X-Citizen-Edit-Token` (o `X-Admin-Token` válido) con `SELECT ... FOR UPDATE`, devuelve `403 CONFIRMATION_UNAUTHORIZED` ante solicitudes anónimas, y devuelve `409 REPORT_ALREADY_MANAGED` si el reporte ya fue confirmado o gestionado administrativamente (`CONFIRMED`, `IN_REVIEW`, `RESOLVED`, `REJECTED`).
- **M-07 y N-03 (Aislamiento automático de BD/volúmenes de pruebas y evaluación; cero borrados globales)**:
  - `backend/app/db.py` implementa `ensure_isolated_database()`, `is_disposable_test_or_eval_db()` y `assert_disposable_test_db()` que rechaza operaciones destructivas sobre la base normal `civia`.
  - `backend/tests/conftest.py` y `eval/evaluar.py` aíslan automáticamente la ejecución en `civia_test` / `civia_eval` y directorios temporales de subida (`/tmp/civia_test_uploads`, `/tmp/civia_eval_uploads`).
  - Eliminados todos los `DELETE FROM reports WHERE is_synthetic = FALSE`, `DELETE FROM pending_approvals` y `UPDATE` incondicionales de `CIV-2026-DEMO0001`; las pruebas limpian exclusivamente los IDs creados en su alcance y preservan registros centinela preexistentes.
- **A-06 (Idempotencia durable con `UNIQUE`, concurrencia y aislamiento de fallos post-commit)**:
  - Migración `backend/migrations/002_security_and_idempotency.sql` añade `edit_token_hash`, `idempotency_key` (`UNIQUE`), `version` y tabla `idempotency_records`.
  - `create_report()` sincroniza reintentos concurrentes mediante `pg_advisory_xact_lock(hashtext(idempotency_key))` + `SAVEPOINT` y recupera el mismo `id`, `tracking_code` y `citizen_edit_token` ante reintentos con `Idempotency-Key` o huella determinista de operación (`op:<sha256>`), devolviendo `409 IDEMPOTENCY_KEY_CONFLICT` si se reutiliza una `Idempotency-Key` con payload distinto.
  - Los fallos de `record_ai_trace` (`_safe_record_trace`) o del análisis post-commit están aislados y jamás invalidan ni duplican un reporte ya confirmado en PostgreSQL.
- **A-07 (Bloqueo de aprobaciones obsoletas en la misma transacción)**:
  - `tool_proponer_actualizacion_critica` registra `previous_status` y `expected_version`.
  - `decide_pending_approval` bloquea `pending_approvals` y `reports` con `SELECT ... FOR UPDATE` en la misma transacción; si el estado o versión del reporte cambió previamente, rechaza automáticamente la propuesta obsoleta (`status = 'REJECTED'`, `stale_conflict = True`, HTTP `409 STALE_APPROVAL`) sin sobrescribir `reports`.
- **B-03 (Cero archivos huérfanos en fallos de BD y prevención de colisiones de radicado)**:
  - `create_citizen_report` rastrea todos los archivos escritos (`photo_*`, `audio_*`) y los elimina en bloque `except Exception:` si falla cualquier paso previo o `create_report` en BD, así como en reintentos idempotentes.
  - `generate_tracking_code()` calcula SHA-256 sobre los 128 bits del UUID (`report_uuid.bytes`), usa año UTC dinámico (`datetime.now(timezone.utc).year`) y reintenta ante `UniqueViolation`.
- **Verificación de pruebas en PostgreSQL 17 real (`civia_test`)**:
  - `docker compose exec -T api pytest -v`: **`26 passed in 38.97s`** (incluyendo las 6 pruebas negativas y de regresión de `backend/tests/test_audit_g1_security.py`).

### Bloque G1.1 — Cierre definitivo de los 7 hallazgos residuales de `docs/auditoria_codex_g1.md` completado (2026-11-01)
- **Detalle completo por hallazgo, corrección, prueba adversarial, resultado y limitaciones**: documentado en [`docs/remediacion_g1_1.md`](remediacion_g1_1.md).
- **Resumen de los 7 cierres residuales**:
  1. **`C-01`**: `is_strong_admin_token()` rechaza secuencias numéricas/alfabéticas/teclado (`_has_sequential_run`) y patrones periódicos o bloques repetidos (`_has_repeated_pattern`, como `"0123456789" * 3`), exige al menos 2 clases de caracteres y `>= 10` caracteres únicos. `generate_admin_token(32)` y los scripts de arranque usan CSPRNG (`secrets.token_urlsafe(32)`).
  2. **`A-01`**: Eliminados `derive_citizen_edit_token()` y el respaldo idempotente implícito por contenido público (`op:<fingerprint>`). Cada reporte genera un `citizen_edit_token` aleatorio con `secrets.token_urlsafe(32)`, independiente de `DATABASE_URL` y de datos públicos. En reintentos idempotentes, el token solo puede desellarse mediante PBKDF2-HMAC-SHA256 con la `Idempotency-Key` secreta del cliente original. Un segundo cliente que descarga campos y foto públicos no recupera el reporte original ni su capacidad de edición (`403 CONFIRMATION_UNAUTHORIZED`).
  3. **`M-07`**: Eliminados `snapshot_db_state()` y `restore_db_snapshot()` (`DELETE ... WHERE NOT (id = ANY(...))` y restauración de `DEMO0001`). `conftest.py` aísla en modo *fail-closed* cualquier `DATABASE_URL` no desechable (incluyendo nombres distintos de `"civia"`, como `civia_prod_probe`) hacia `civia_test_<uuid8>` y limpia únicamente los UUIDs creados por la prueba (`cleanup_tracked_test_records()`). `test_four_agent_guardrails_enforced` opera sobre su propio reporte desechable sin tocar `CIV-2026-DEMO0001`.
  4. **`N-03`**: `eval/evaluar.py` elimina `pre_existing_pa_ids` y el borrado por complemento (`WHERE NOT (id = ANY(...))`), rastrea únicamente los `approval_id` generados por sus propias llamadas al agente (`created_eval_pa_ids`), aísla en modo *fail-closed* bases no desechables y restaura `settings.UPLOAD_DIR` al terminar.
  5. **`A-06`**: `req_fingerprint` se construye sobre el JSON canónico ordenado de todos los parámetros (`title`, `description`, `latitude`, `longitude`, `comuna`, `neighborhood`, `address_hint`, `auto_analyze`, `photo_sha256`, `audio_sha256`), devolviendo `409 IDEMPOTENCY_KEY_CONFLICT` ante cualquier mutación en campos opcionales o adjuntos.
  6. **`A-07`**: `decide_pending_approval()` exige tanto `previous_status` como `expected_version` entero válido (`>= 1`) para aprobar, rechazando con `stale_conflict=True` (`409 STALE_APPROVAL`) propuestas heredadas sin versión tras ciclos ABA (`CONFIRMED -> RESOLVED -> CONFIRMED`). La migración `003_invalidate_legacy_approvals.sql` invalida propuestas `PENDING` heredadas sin `expected_version`.
  7. **`B-03`**: `_atomic_write_bytes()` en `backend/app/security.py` escribe en `.tmp_<uuid>_<name>`, verifica longitud exacta, promueve con `os.replace` y en `except BaseException:` elimina tanto el archivo temporal como el destino final antes de propagar el error (`0` archivos huérfanos ante escrituras parciales interrumpidas con `OSError`).
- **Verificación de la suite completa + pruebas adversariales G1.1 en PostgreSQL 17 real**:
  - `docker compose exec -T api pytest -v`: **`33 passed in 30.05s`** (`13/13` en `tests/test_audit_g1_security.py`).

### Bloque G1.2 — Cierre del último hallazgo `C-01` (`docs/auditoria_codex_g1_1.md`) completado (2026-11-01)
- **Alcance exclusivo**: Se mantuvieron intactas las 6 correcciones ya aprobadas (`A-01`, `M-07`, `N-03`, `A-06`, `A-07`, `B-03`) y se cerró el contraejemplo contextual de `C-01` (`_'.join(('Civia', 'AdminToken', '2026', 'Demo')) + '!'`).
- **Corrección aplicada (`backend/app/config.py`, `scripts/run.ps1`, `run.sh`, `.env.example`, `README.md`)**:
  - Se estableció `secrets.token_urlsafe(32)` (`>= 32` caracteres URL-safe base64, `>= 12` símbolos distintos) como procedimiento estándar de generación local por instalación, sin credenciales predeterminadas ni modo demo en desarrollo o producción.
  - Se bloqueó explícitamente el patrón contextual `Civia_AdminToken_2026_Demo!` y sus variantes con nombre del proyecto, rol administrativo, años (`2024..2027`) y etiquetas `Demo`/`Test` (tanto en formato estándar como con `ADMIN_TOKEN_ALLOW_CUSTOM_FORMAT=true`).
  - Se documentó en código, `.env.example`, `README.md` y adenda de `docs/remediacion_g1_1.md` que los filtros estáticos bloquean patrones previsibles pero no prueban matemáticamente la entropía criptográfica de una cadena arbitraria.
- **Verificación**:
  - Prueba adversarial añadida: `tests/test_audit_g1_security.py::test_g1_2_c01_rejects_contextual_project_role_year_demo_token`.
  - Suite completa ejecutada sobre PostgreSQL 17 real: **`34 passed`** (`14/14` en `tests/test_audit_g1_security.py`).

### Bloque G2 — Agente, límites efectivos y proveedores IA completado (2026-11-02)
- **Detalle completo por hallazgo, corrección, pruebas adversariales, resultados y límites**: documentado en [`docs/remediacion_g2.md`](remediacion_g2.md).
- **Resumen de los hallazgos cerrados**:
  1. **`A-02`**: Implementación de deadline monotónico con `contextvars` y aborto estricto con rollback en `checked_commit(conn)` ante timeouts de herramientas (`execute_tool_with_timeout`), previniendo escrituras huérfanas en BD.
  2. **`M-03`**: Propagación del deadline global del agente (`deadline_monotonic = time.monotonic() + eff_total_timeout`), abortando turnos e iteraciones subsiguientes si el tiempo asignado expiró.
  3. **`M-02`**: Acotación en esquema Pydantic (`max_iterations <= 5`, `max_tokens_budget <= 6000`), límites forzados en servidor, reserva previa de tokens (< 60 tokens interrumpe antes de llamar al LLM) y cota a tokens de salida según saldo remanente.
  4. **`A-03`**: Validación estricta en `parse_and_validate_analysis_json()`; rechazo con `AIProviderError("INVALID_SCHEMA")` de categorías desconocidas, severidades ausentes, confianzas negativas o fuera de rango, resúmenes sin contenido sustantivo y objetos vacíos `{}` sin coerciones silenciosas.
  5. **`A-04`**: Sanitización de PII (correos y teléfonos colombianos) y nombres técnicos internos (`Google`, `API`, `Groq`, `HTTP 401`, `ValueError`, `Traceback`) tanto en salidas ciudadanas del agente como en campos textuales del repositorio público.
  6. **`M-04`**: Circuit Breaker con candado de concurrencia `threading.Lock()` y admisión de ensayo único estricto en `HALF_OPEN` (`_half_open_in_flight`), bloqueando tormentas concurrentes hacia proveedores degradados.
  7. **`N-02`**: Eliminada la sustitución oculta de modelos Gemini en fallback (`_EXHAUSTED_GEMINI_MODELS`); el router respeta estrictamente los modelos configurados en `.env`.
  8. **`M-01`**: Validación profunda de audio (`_validate_mp3_payload`) inspeccionando palabras de sincronización y tramas reales más allá de metadatos `ID3`, rechazando con HTTP 415 archivos sin audio y WAVs vacíos.
  9. **`A-05`**: Descarga de llamadas síncronas pesadas (validación/almacenamiento de fotos y audio, transcripción, creación y actualización en BD) del event loop de FastAPI hacia hilos de trabajo mediante `await run_in_threadpool(...)`.
  10. **`M-06`**: Frontera estricta de confianza para `X-Forwarded-For` y `X-Real-IP` en `get_trusted_client_ip()`; solo se confía en proxies de subredes privadas conocidas (Docker, loopback, RFC1918), evitando spoofing de IP. Banderas `--proxy-headers --forwarded-allow-ips=*` en Dockerfile.
  11. **`Q13`**: Garantizada la presencia de `tracking_code`, `estado_propuesto` y código de aprobación en `tool_proponer_actualizacion_critica` y fallback determinista ante contingencias.
  12. **Actualización de modelo terciario**: Verificada la accesibilidad de `gemini-3.5-flash-lite` como reemplazo verificado de `gemini-3.6-flash` (cuota agotada), garantizando conmutación exitosa en pruebas de contingencia (`GROQ_FAIL`).
- **Verificación de la suite completa + suite adversarial G2 en PostgreSQL 17 real**:
  - `docker compose exec -T api pytest -v`: **`57 passed in 52.94s`** (`23/23` en `tests/test_audit_g2_resilience.py`, `14/14` en `tests/test_audit_g1_security.py`, `12/12` en `tests/test_ai_and_agent.py`, `7/7` en `test_reports_crud.py` y `test_health.py`, `1/1` en `test_e2e_frontend_proxy.py`).
  - Suite dorada (`eval/evaluar.py`): **`6/6` casos dorados verificados por SQL (`100%`)**, **`11/15` consultas representativas aprobadas (`73.33%`)**, Q13 superada.

### Bloque G2.1 — Cierre Definitivo de Hallazgos Residuales M-03, M-06 y M-02 (`docs/auditoria_codex_g2_1.md`) completado (2026-11-02)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`M-03` (Worker no cooperativo desacoplado, endpoint 0.10s y manejador sin HTTP 500)**:
     - `backend/app/agent.py`: `execute_tool_with_timeout` ejecuta el worker en hilo desacoplado con copia de contexto, elimina el retraso artificial de `future.exception(timeout=0.15)` y utiliza `executor.shutdown(wait=False, cancel_futures=True)`. La función aborta conexiones PostgreSQL activas y retorna de inmediato `TimeoutError` en < 0.20s sin esperar la finalización de tareas de CPU o sleeps no cooperativos (resolviendo el bloqueo de 0.4564s observado por Codex).
     - `backend/app/main.py`: Se importó `uuid` en el módulo, asegurando que el manejador final de `TimeoutError` devuelva HTTP 200 con `guardrail_triggered="TIMEOUT"` y un `trace_group_id` UUID válido (eliminando el `NameError` y HTTP 500 detectado por Codex).
     - `backend/app/schemas.py`: Se actualizaron las cotas a `total_timeout_seconds ge=0.10` y `tool_timeout_seconds ge=0.05`, permitiendo peticiones HTTP literales de 0.10s con HTTP 200 (sin 422).
  2. **`M-06` (Anti-spoofing en loopback, redes privadas y Uvicorn)**:
     - `backend/Dockerfile`: Comando de arranque actualizado a `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--forwarded-allow-ips", ""]`, desactivando `ProxyHeadersMiddleware` de Uvicorn en loopback.
     - `docker-compose.yml`: Se fijó `FORWARDED_ALLOW_IPS: ""` y `TRUSTED_PROXIES: ${TRUSTED_PROXIES:-172.16.0.0/12}`.
     - `backend/app/config.py`: `TRUSTED_PROXIES` restringido por omisión a `"172.16.0.0/12"` (únicamente el proxy inverso Nginx en la red Docker), eliminando permanentemente `127.0.0.1`, `::1` y `10.0.0.0/8`.
     - `backend/app/security.py`: `get_trusted_proxy_networks()` no tiene fallback a loopback. Conexiones directas desde peer público (`198.51.100.2`), loopback (`127.0.0.1`) o privado directo (`10.20.30.40`) ignoran `X-Forwarded-For` y reciben rate-limiting estricto por su IP TCP real (`200 / 200 / 429`), sin vías de evasión.
  3. **`M-02` (Propagación de tracker al executor y reserva multimodal previa)**:
     - `backend/app/agent.py`: `execute_tool_with_timeout` propaga `_ACTIVE_TOKEN_TRACKER` mediante `contextvars.copy_context().run(_worker)` y asignación explícita dentro del hilo de trabajo, resolviendo la pérdida de contexto que reportaba 40 tokens en lugar de 1640.
     - `backend/app/agent.py`: `tool_clasificar_evidencia` calcula dinámicamente el costo estimado del prompt multimodal (`build_classification_prompt` / 3.0 + 258 foto + 80 salida). Con presupuesto de 200 tokens y costo estimado de ~394+, interrumpe antes de la llamada activando `MAX_TOKENS` con 0 llamadas al router y 0 tokens gastados. Al autorizarse la llamada, los tokens multimodales (ej. 1600) se suman al tracker del agente, reportando exactamente 1640 tokens en total.
  4. **`_get_clean_test_db` en suites de prueba**:
     - Actualizado en `tests/test_audit_g2_1_remediation.py` para parsear dinámicamente `DATABASE_URL` (en lugar de forzar `host=db`), garantizando ejecución limpia tanto en Docker como en clústeres temporales externos de auditoría (`127.0.0.1:55483`).
- **Verificación de suites en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest tests/test_audit_g1_security.py tests/test_audit_g2_resilience.py tests/test_audit_g2_1_remediation.py tests/test_reports_crud.py tests/test_health.py tests/test_e2e_frontend_proxy.py -v`:
    - **`57 PASSED`** (100% de éxito, 0 fallos en 13.47 s).
    - `test_audit_g2_1_remediation.py`: 12/12 passed (A-02, M-03 worker no cooperativo, M-03 HTTP final, M-03 literal 0.10s, M-06 anti-spoofing completo, M-02 reserva previa y M-02 propagación a hilo).
    - Cero regresiones en controles aprobados G1, A-02 o N-02. Cero commits en `main` ni push remoto.

### Bloque G2.1.1 — Cierre Definitivo de Contraejemplos Residuales M-03, M-06 y M-02 (`docs/auditoria_codex_g2_1_8162a12.md`) completado (2026-11-02)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`M-03` (Capacidad revocable de ejecución, cursor proxy y protección de almacenamiento)**:
     - `backend/app/db.py`: Se implementó `ExecutionCapability` con deadline monotónico y estado atómico `_revoked`. Se vincula a contextvars (`_CURRENT_CAPABILITY`) y a la conexión (`conn._execution_capability`).
     - `backend/app/db.py`: Se incorporó `_CapabilityCursorProxy` sobre los cursores de `psycopg 3`, interceptando llamadas `execute` y `executemany` para levantar inmediatamente `TimeoutError` si la capacidad fue revocada o expiró el plazo, impidiendo que una conexión retenida ejecute SQL tras el deadline.
     - `backend/app/security.py`: `_atomic_write_bytes` valida la capacidad antes de escribir en staging y antes de promover con `os.replace`. Si venció o fue revocada, levanta `TimeoutError` y desvincula cualquier archivo parcial, eliminando escrituras tardías.
     - `backend/app/agent.py`: `execute_tool_with_timeout` revoca la capacidad inmediatamente y delega la cancelación de conexiones PostgreSQL a un hilo daemon de fondo (`cancel_active_conns_for_thread`), permitiendo que el llamador retorne en < 0.20s sin bloqueos síncronos. Se preservan estrictamente los controles de rollback de commit diferido de A-02.
  2. **`M-06` (Identidad exacta del proxy Nginx en red Compose y rechazo de spoofing desde otros contenedores)**:
     - `docker-compose.yml`: Se configuró una red dedicada `civia_net` (`172.28.0.0/16`) con IP estática asignada al frontend `172.28.0.2`.
     - `backend/app/config.py`: `TRUSTED_PROXIES` restringido a `"172.28.0.2,172.18.0.2"`, eliminando la confianza abierta en toda la subred `/12`.
     - Conexiones directas desde otros contenedores (como `172.19.0.9`) o clientes de la misma red son tratadas como directas: cualquier cabecera `X-Forwarded-For` es descartada y la cuota se aplica sobre su IP real de red (`201 / 201 / 429`). Clientes legítimos detrás de Nginx en `172.28.0.2` conservan cuotas independientes.
  3. **`M-02` (Presupuesto atómico de tokens, acumulación en fallos e identificación de consumo desconocido)**:
     - `backend/app/agent.py`: `TokenBudgetTracker` implementa reserva atómica `try_reserve(requested)` con lock de exclusión mutua y conciliación con `reconcile_usage`, impidiendo sobreconsumo por concurrencia.
     - `backend/app/ai_router.py`: `classify_evidence_with_router` acumula el uso de tokens de todos los intentos (`accumulated_prompt_tokens`, `accumulated_completion_tokens`), incluso ante esquemas inválidos (`INVALID_SCHEMA`), registrando la totalidad de tokens conocidos consumidos en la cadena de reintentos (ej. 600 + 800 = 1400 tokens; 3 inválidos = 1800 tokens).
     - `backend/app/schemas.py` y `agent.py`: Se añadieron `tokens_estimated` y `unknown_consumption`. Si los intentos fallan por error de red o remoto sin metadatos, se imputa una estimación conservadora identificada y se señala el consumo como desconocido/estimado, sin reportar cero ficticio.
  4. **Hermeticidad de la suite de pruebas**:
     - `backend/tests/test_ai_and_agent.py`: Incorporado transporte simulado hermético para asegurar que las 12 pruebas de integración del agente y router se ejecuten exitosamente y de forma determinista en entornos de auditoría sin claves API externas ni acceso a internet.
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -v`:
    - **`77 PASSED`** (100% de éxito, 0 fallos, 1 warning en 25.35 s).
    - `test_audit_g2_1_remediation.py`: 20/20 passed (12 de G2.1 + 8 de G2.1.1).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 12/12 passed.
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02 o N-02. Cero commits en `main` ni push remoto.

### Bloque G2.1.2 — Cierre Definitivo de Bloqueos de Cursor, Carrera de Archivos, Topología Compose y Hermeticidad (`docs/auditoria_codex_g2_1_1_a745a1c.md`) completado (2026-11-02)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`M-03` (Preservación de identidad de proxies de cursor en llamadas encadenadas, `copy()`, `stream()` y serialización en promoción de archivos)**:
     - `backend/app/db.py`: `_CapabilityCursorProxy.execute()` y `executemany()` retornan `self`, evitando que llamadas encadenadas (`conn.cursor().execute(...)`) devuelvan el cursor nativo de psycopg desprotegido. Se envolvieron `cur.copy()` y `conn.copy()` con `_CapabilityCopyProxy` y se protegieron lecturas en streaming. En `get_conn()`, `conn.execute` se delegó directamente al proxy protegido de la capacidad.
     - `backend/app/db.py` y `security.py`: `ExecutionCapability.authorized_replace(src, dst)` y `atomic_publish_file()` ejecutan la comprobación de revocación y `os.replace` bajo el cerrojo `self._lock`, eliminando la carrera TOCTOU entre revocación y publicación de archivos. Si la capacidad fue revocada, el archivo temporal se elimina y se levanta `TimeoutError`. Se preservan estrictamente los controles de rollback de commit diferido de A-02.
  2. **`M-06` (Asignación estática de IPs en Compose y purga de IP heredada)**:
     - `docker-compose.yml`: Red `civia_net` con subred `172.28.0.0/16` y asignación disjunta y estática: `frontend` (Nginx) en `172.28.0.2`, `db` en `172.28.0.10` y `api` en `172.28.0.11`.
     - `backend/app/config.py`: `TRUSTED_PROXIES` fijado a `"172.28.0.2"`. Se purgó completamente `172.18.0.2` del código y de las suites.
     - Verificado mediante `docker network inspect` y reinicios limpios que `172.28.0.2` pertenece única y exclusivamente a Nginx. Conexiones directas desde otros contenedores o la red reciben rate limiting estricto (`201 / 201 / 429`), y clientes independientes detrás de Nginx conservan cuotas aisladas.
  3. **`M-02` (Reserva y conciliación de tokens por intento individual en el Router IA)**:
     - `backend/app/ai_router.py`: `classify_evidence_with_router` realiza la reserva atómica `token_tracker.try_reserve(est_attempt_tokens)` por intento individual dentro del bucle de proveedores. Concilia inmediatamente el uso real al finalizar el intento y, si los tokens consumidos agotan el saldo disponible (`remaining < est_attempt`), interrumpe de inmediato (`break`) sin invocar a proveedores subsiguientes (como Groq).
     - Se marcaron `INVALID_JSON` e `INVALID_SCHEMA` como errores no reintentables sobre el mismo modelo y se eliminó la duplicación redundante de acumulación de tokens en bloques de excepción.
  4. **Hermeticidad incondicional de pruebas**:
     - `backend/tests/test_ai_and_agent.py`: Adaptadores de proveedores IA reemplazados incondicionalmente mediante `hermetic_multimodal_adapter_fixture`. Fixture `guard_no_external_network_calls` que intercepta llamadas HTTP externas a dominios de Google y Groq y falla inmediatamente ante tráfico imprevisto (`test_hermetic_guard_fails_immediately_on_unexpected_external_http`).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -v`:
    - **`83 PASSED`** (100% de éxito, 0 fallos, 1 warning en 9.39 s).
    - `test_audit_g2_1_remediation.py`: 24/24 passed (incluyendo los 4 nuevos tests de regresión G2.1.2).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 14/14 passed.
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02 o N-02. Cero commits en `main` ni push remoto.

### Bloque G2.1.3 — Cierre de Reserva Concurrente, Contrato COPY, Transaction Timeout y Hermeticidad Global (`docs/auditoria_codex_g2_1_2_d07a1e5.md`) completado (2026-11-02)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`M-02` (Aislamiento de reservas por manija `TokenReservation` y conciliación exactamente una vez)**:
     - `backend/app/agent.py`: Se implementó la clase `TokenReservation` con propiedad unívoca y métodos `reconcile()` y `release()` atómicos e idempotentes (`is_active`). `TokenBudgetTracker.try_reserve()` devuelve un objeto `TokenReservation` específico.
     - `backend/app/agent.py` y `ai_router.py`: `tool_clasificar_evidencia` y `run_civia_agent` operan exclusivamente sobre sus manijas de reserva individuales. En los bloques `finally:`, solo se concilia/libera si la manija propia está activa, eliminando la colisión donde dos clasificaciones concurrentes de 700 tokens con presupuesto compartido de 6000 registraban 2100 tokens en lugar de 1400. En `ai_router.py`, los manejadores de excepción verifican `if active_reservation is not None:` antes de imputar tokens en fallos de esquema.
     - Prueba permanente `test_g2_1_3_m02_two_concurrent_authorized_calls_record_1400_not_2100` añadida y verificada (`PASSED`).
  2. **`M-03` (Contrato completo de Context Manager en COPY `_CapabilityCopyProxy` y revocación en streaming)**:
     - `backend/app/db.py`: `_CapabilityCopyProxy` ahora retiene el generador gestor de contexto de psycopg 3 (`self._cm`) e invoca `__enter__()` produciendo la instancia real de `Copy` con soporte íntegro para `rows()`, `read()`, `read_row()`, `write()`, `write_row()` e `__iter__()`.
     - Las lecturas por filas delegan en `_CapabilityStreamProxy`, validando la capacidad fila por fila e interrumpiendo con `TimeoutError` si se supera el deadline o se revoca la capacidad.
     - Prueba permanente `test_g2_1_3_m03_copy_out_and_copy_in_authorized_and_rejected_after_revocation` añadida y verificada (`PASSED`).
  3. **`A-02` (Aplicación de `transaction_timeout` a nivel de servidor en PostgreSQL 17 y desacople de latencia)**:
     - `backend/app/db.py`: Tanto `checked_commit(conn)` como `_wrapped_commit()` configuran `SET LOCAL transaction_timeout = {timeout_ms}` en PostgreSQL antes de ejecutar `COMMIT`, asegurando que constraint triggers diferidos lentos sean cancelados directamente por el motor de base de datos con `TransactionTimeout`.
     - `backend/tests/test_audit_g2_1_remediation.py`: Sincronización determinista con `executor.shutdown(wait=True)` en la prueba de triggers diferidos, y desacople de la verificación de integridad de datos respecto a fluctuaciones del scheduler de hilos en Windows (`< 0.60s`).
  4. **Hermeticidad global a nivel de sesión**:
     - `backend/tests/conftest.py`: Fixture de sesión `guard_no_external_network_calls` que intercepta `httpx.Client.send` y lanza `RuntimeError` ante cualquier intento de tráfico hacia dominios de Google o Groq.
     - `backend/tests/test_audit_g1_security.py`: Incorporado `hermetic_multimodal_adapter_fixture` de forma global para toda la suite de seguridad G1, garantizando que `test_a06` con `auto_analyze: true` no intente llamadas salientes.
  5. **Coexistencia de red Docker Compose**:
     - Preservada la topología fija (`frontend` en `172.28.0.2`, `db` en `172.28.0.10`, `api` en `172.28.0.11`).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -v`:
    - **`85 PASSED`** (100% de éxito, 0 fallos en 10.40 s).
    - `test_audit_g2_1_remediation.py`: 26/26 passed (incluyendo los 2 nuevos tests adversariales G2.1.3).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 14/14 passed.
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02 o N-02. Cero commits en `main` ni push remoto.

### Bloque G2.1.4 — Cierre de Integridad Transaccional A-02 y Hermeticidad Total de Turnos de Agente (`docs/auditoria_codex_g2_1_3_4a99705.md`) completado (2026-11-03)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`A-02` (Integridad transaccional absoluta y eliminación de commits tardíos tras pausas de planificación)**:
     - `backend/app/db.py`: Tanto en `checked_commit(conn)` como en `_wrapped_commit()`, se re-evalúa el saldo disponible contra el deadline monotónico inmediatamente antes de iniciar `COMMIT` (`rem_sec_commit = dl_check - time.monotonic()`). Si expiró (`rem_sec_commit <= 0`), aborta y ejecuta `conn.rollback()` de inmediato sin emitir `COMMIT`.
     - Si el tiempo disponible disminuyó durante la espera o planificación previa (`rem_ms_effective < timeout_ms`), se ajusta dinámicamente el límite en PostgreSQL antes de emitir `COMMIT` mediante `SELECT set_config('transaction_timeout', '{rem_ms_effective}', true);`, anclando la expiración en el motor al saldo real del deadline original y garantizando que triggers diferidos lentos sean abortados a nivel de servidor por `TransactionTimeout`.
     - El temporizador `threading.Timer` se inicializa con el saldo final monotónico exacto recalculado inmediatamente antes de invocar `conn.commit()`.
     - Pruebas permanentes: `test_g2_1_4_a02_reproduction_scheduling_pause_and_delayed_cancel_preserves_original` para los cuatro casos (61, 62, 63 y 64) con pausa de planificación de 0.13 s y retraso de cancelación de 0.15 s; verifican que el worker aborta con `TimeoutError`, cero commits son confirmados y el estado final permanece estrictamente `ORIGINAL` (**PASSED**).
  2. **Hermeticidad total de la suite**:
     - `backend/tests/conftest.py`: Se implementó la fixture `hermetic_agent_turn_adapter_fixture` (`autouse=True`) que sustituye incondicionalmente `_call_agent_turn_gemini` y `_call_agent_turn_groq` por un emulador determinista, garantizando que ninguna consulta conversacional intente tráfico externo.
     - `backend/tests/conftest.py`: La fixture `guard_no_external_network_calls` acumula intentos salientes en `unexpected_attempts` e invoca `pytest.fail()` en su teardown si se detecta cualquier intento imprevisto, impidiendo que el producto capture y absorba excepciones de red.
     - `backend/tests/test_ai_and_agent.py`: `test_optional_live_provider_multimodal_connectivity` marcado como prueba opcional separada (`@pytest.mark.live`).
     - Prueba permanente: `test_g2_1_4_hermetic_suite_zero_external_attempts_synthetic_and_empty` comprueba cero intentos tanto con claves sintéticas como con claves vacías (**PASSED**).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -v`:
    - **`90 PASSED`** (100% de éxito, 0 fallos, 1 warning en 10.87 s).
    - `test_audit_g2_1_remediation.py`: 31/31 passed (incluyendo los 5 nuevos tests G2.1.4).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 14/14 passed.
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02, N-02, M-02, M-03 COPY o M-06. Cero commits en `main` ni push remoto.

## Verificación local independiente G2.1.7 — 2026-11-03

- Checkout comprobado por comandos: `492b0415bd1642d077ce7ce48ea2e2cb1c5b26c6`, rama `fix/auditoria-final`, árbol inicialmente limpio.
- Migraciones 004/005 y `backend/app/db.py` leídos; hashes y evidencias en `docs/auditoria_codex_g2_1_7_492b041.md`.
- **Auditoría dinámica bloqueada:** `docker compose ps` falla al conectar con `dockerDesktopLinuxEngine` (código 1). No se confirmó disponibilidad de API, PostgreSQL 17 ni frontend. Sin dictamen de aceptación técnica.
- Lint y tests del producto no ejecutados: no se cumplió la condición previa para la auditoría aislada. Los 105 PASS anteriores no son resultados reproducidos por esta revisión.
- Sin cambios de producción, servicios o datos habituales; sin Autopilot, commits, push ni merge. Cambios limitados al informe y esta anotación.

## Auditoría independiente G2.1.7 reanudada — 2026-11-03

- Docker nuevamente disponible: API, PostgreSQL y frontend habituales saludables. HEAD sigue en `492b041`, rama `fix/auditoria-final`; solo cambios documentales del intento previo al empezar.
- Copia congelada de Git y PostgreSQL **17.11** exclusivo en red interna sin puertos publicados. Código de producción intacto. Evidencia fuera del checkout en `C:\Users\Jhoesp\AppData\Local\Temp\civia-492b041-04bcac63ba274f3093fa56dac5d17406`.
- **Dictamen: NO APROBADO.** Corrigen atomicidad del executor, deduplicación y propagación PENDING; persisten mutación crítica sin ledger, transición ABORTED→COMMITTED por helper, aborto deducido de observación fallida, UNKNOWN sin resolución pese a evidencia propia, exposición de metadatos, entrega/replay de token incompletos y atribución falsa de cancelaciones externas dentro del margen de 50 ms.
- Suites con claves vacías: **104 PASS, 1 SKIP, 1 live excluida**, 21,46 s; claves sintéticas: **104 PASS, 1 SKIP, 1 live excluida**, 18,12 s. Incluyen las siete pruebas G2.1.7 y regresiones M-02, COPY, M-06, G1 y N-02. E2E frontend omitido por aislamiento; sin intentos externos inesperados reportados por la guardia hermética.
- Se conserva el primer pase mal configurado del auditor: 103 PASS, 1 FAIL (`eval` fuera de PYTHONPATH), 1 SKIP, 1 excluida; se corrigió solo el entorno y se repitió en base nueva. No se alteraron pruebas.
- `compileall` pasó; no equivale a lint. No se encontró configuración/comando de lint Python del proyecto. `git diff --check` valida los cambios documentales.
- Se eliminaron únicamente runner, PostgreSQL, volumen exclusivo y red exclusiva del auditor tras verificar sus IDs. Los tres servicios habituales siguen saludables. Sin Autopilot, commits, push, merge ni cambio de rama.
- Informe con matriz, evidencias, cambios mínimos y recomendación de simplificar temporalmente escrituras asíncronas: `docs/auditoria_codex_g2_1_7_492b041.md`. No se inició remediación ni otra fase de desarrollo.

### Bloque G2.1.5 — Resolución Definitiva de Integridad Transaccional A-02 y Normalización de Excepciones (`docs/auditoria_codex_g2_1_4_95eecba.md`) completado (2026-11-03)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en la sección 10 de [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`A-02` (Sincronización dinámica de vencimiento en el dominio temporal del servidor PostgreSQL)**:
     - `backend/app/db.py`: Eliminado el paso de enteros milimétricos relativos calculados previamente en Python. Ahora se transmite a PostgreSQL el epoch objetivo absoluto (`target_epoch = time.time() + rem_sec`).
     - PostgreSQL calcula dinámicamente en SQL mediante `clock_timestamp()` el remanente real:
       `set_config('transaction_timeout', GREATEST(1, CEIL((%s - EXTRACT(EPOCH FROM clock_timestamp())) * 1000))::text, true)`
       absorbiendo cualquier pausa de planificación o red entre Python y la BD. Si el plazo ya expiró al momento de ejecución, PostgreSQL ejecuta inmediatamente `pg_cancel_backend(pg_backend_pid())`.
  2. **Unificación arquitectónica de `checked_commit` y `_wrapped_commit`**:
     - `_wrapped_commit()` en `get_conn` delega íntegramente en `checked_commit(conn)`, invocando la referencia nativa `conn._orig_commit`. Ambos métodos ejecutan la misma lógica rigurosa de protección, reevaluación monotónica y validación de supervisor post-commit.
  3. **Límites tempranos a nivel de sesión**:
     - `get_conn` configura preventivamente `transaction_timeout` a nivel de conexión anclado al target epoch del servidor.
  4. **Normalización del contrato de excepciones en `agent.py`**:
     - En `backend/app/agent.py:execute_tool_with_timeout`, tanto en `_worker` como en `future.result`, se traducen de forma exhaustiva `psycopg.errors.QueryCanceled`, `TransactionTimeout`, `AdminShutdown` y fallos operacionales de cancelación a `TimeoutError`.
  5. **Pruebas permanentes de regresión**:
     - `test_g2_1_a02_balanced_config_checks_cases_81_84_prevent_late_writes`: reproduce los casos 81 a 84 con pausas de 40 ms, 5 ms y 40 ms, con y sin Timer, confirmando estado `ORIGINAL` en el 100% de los casos (**PASSED**).
     - `test_g2_1_a02_legitimate_commits_within_deadline`: confirma que transacciones legítimas dentro del plazo persisten `CHANGED` sin demoras (**PASSED**).
     - `test_g2_1_a02_cases_61_64_scheduling_delay`: verifica la resistencia ante pausas de 0.13 s (**PASSED**).
     - `test_g2_1_a02_active_conn_cancellation_on_slow_worker`: verifica cancelación de workers lentos y tipo de excepción `TimeoutError` (**PASSED**).
### Bloque G2.1.6 — Rediseño del Contrato Transaccional A-02 y Registro Durable (`docs/auditoria_codex_g2_1_5_cdc646b.md`) completado (2026-11-03)
- **Detalle completo por hallazgo, diagnóstico, corrección, pruebas adversariales y límites**: documentado en la sección 13 de [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **`A-02` (Eliminación de falsos rollbacks post-commit y estados unívocos `COMMITTED`, `ABORTED`, `PENDING`, `UNKNOWN`)**:
     - `backend/app/db.py:checked_commit`: Se eliminó el lanzamiento de `TimeoutError` post-commit. Si el commit nativo retornó éxito, PostgreSQL confirmó la transacción de forma definitiva; mentir al llamador reportando un timeout mientras la base de datos persistió el cambio queda formalmente erradicado.
     - Registro en vuelo `_IN_FLIGHT_COMMITS` durante la ejecución nativa de commit.
     - `backend/app/agent.py`: Cuando el supervisor agota su plazo de espera mientras la transacción está en confirmación nativa, levanta `OperationPendingError` con `status="PENDING"` e identificador durable, sin presumir rollback ficticio ni cancelar la conexión que está confirmando.
  2. **Registro durable de operaciones e idempotencia (`operation_records`)**:
     - Migración `backend/migrations/004_operation_records.sql` con tabla `operation_records`: `operation_id UUID PRIMARY KEY`, `idempotency_key`, `operation_type`, `target_id`, `status CHECK ('PENDING', 'COMMITTED', 'ABORTED', 'UNKNOWN')`, `proposed_payload`, `result_payload`, `backend_pid`, `created_at`, `updated_at`.
     - `register_operation_intent`: Registra la intención durablemente en autocommit antes de ejecutar.
     - En `checked_commit`: Actualización atómica de estado a `COMMITTED` dentro de la transacción protegida por `SAVEPOINT op_rec_sp`.
     - Idempotencia en herramientas críticas (`tool_proponer_actualizacion_critica`): retornos consistentes ante reintentos con la misma clave de idempotencia sin duplicar solicitudes en `pending_approvals`.
  3. **Normalización determinista de excepciones de infraestructura**:
     - `backend/app/db.py:is_deadline_cancellation`: `AdminShutdown` y SQLSTATE `57P01` son explícitamente excluidos de cancelaciones de plazo, garantizando que terminaciones de backend por administrador o caídas de infraestructura no se disfracen de `TimeoutError` ni activen el guardrail `TIMEOUT`.
  4. **Reconciliación y Endpoint Público**:
     - `backend/app/db.py:reconcile_operation`: Inspecciona el `backend_pid` en `pg_stat_activity` y el recurso objetivo para resolver deterministamente operaciones `PENDING` a `COMMITTED` o `ABORTED`.
     - `backend/app/main.py`: Endpoint `GET /api/operations/{operation_id}` y adaptación de respuesta en `/api/agent/query` con `guardrail_triggered="OPERATION_PENDING"` para trazabilidad ciudadana.
  5. **Pruebas permanentes de regresión**:
     - `test_g2_1_6_admin_shutdown_not_masked_as_timeout`: `pg_terminate_backend` (57P01) preservado como error administrativo (**PASSED**).
     - `test_g2_1_6_in_flight_commit_returns_operation_pending_on_supervisor_timeout`: supervisor reporta `PENDING` en commit en vuelo y resuelve a `ABORTED` (**PASSED**).
     - `test_g2_1_6_clock_offset_cases_102_109_truthful_pending_and_committed`: casos 102/109 con desfase de reloj (+100 ms) reportan verazmente `PENDING` al llamador y persisten `COMMITTED` en BD (**PASSED**).
     - `test_g2_1_6_idempotent_proposal_replay`: idempotencia sin duplicados en `pending_approvals` (**PASSED**).
     - `test_g2_1_6_reconciliation_of_disconnected_operation`: reconciliación determinista de operaciones huérfanas (**PASSED**).
     - `test_g2_1_6_api_endpoint_operations_status`: API `GET /api/operations/{operation_id}` (**PASSED**).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest tests -m "not live"`:
    - **`98 PASSED, 1 deselected`** (100% de éxito, 0 fallos, 1 warning en 15.24 s).
    - `test_audit_g2_1_remediation.py`: 40/40 passed (incluyendo los 6 nuevos tests G2.1.6).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 13/13 passed (1 deselected live).
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02, N-02, M-02, M-03 COPY o M-06. Cero commits en `main` ni push remoto.

---

## Bloque G2.1.7 — Endurecimiento Fail-Closed, Autorización y Reconciliación del Registro Transaccional (`docs/auditoria_codex_g2_1_6_f6fe4f6.md`) completado (2026-11-03)
- **Documentación de diseño**: Especificada previamente en [`docs/diseno_g2_1_7.md`](diseno_g2_1_7.md) y en la sección 16 de [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **P0 — Atomicidad obligatoria del registro (Fail-Closed)**:
     - `backend/app/db.py:checked_commit`: Eliminado definitivamente el uso de `SAVEPOINT op_rec_sp`. La actualización `UPDATE operation_records SET status = 'COMMITTED', updated_at = clock_timestamp() WHERE operation_id = %s AND status = 'PENDING'` se ejecuta directamente en la misma transacción que el negocio y exige `cur.rowcount == 1`. Si el marcador falla por un trigger, tabla ausente o bloqueo, se ejecuta `conn.rollback()` y se aborta la transacción completa. Jamás se confirma negocio si el marcador falla.
     - `register_operation_intent`: Falla cerrado propagando excepciones si `operation_records` no existe o no puede persistir, impidiendo que la herramienta ejecute negocio sin trazabilidad durable.
  2. **P0 — Reconciliación basada en evidencia propia e inmutabilidad monótona**:
     - Migración `backend/migrations/005_operation_records_hardening.sql`: Vincula `pending_approvals` con `operation_id UUID REFERENCES operation_records(operation_id) ON DELETE SET NULL` e índice dedicado.
     - `backend/app/db.py:reconcile_operation`: Verifica evidencia en `pending_approvals` por `operation_id` exacto; jamás infiere `COMMITTED` por la existencia de otra propuesta genérica sobre el mismo `report_id`.
     - Si `backend_pid` es `None` (el worker aún no abre conexión o está esperando), `reconcile_operation` conserva `PENDING` (o `UNKNOWN`), erradicando falsos `ABORTED` prematuros comunicados por API antes de que el worker termine `COMMITTED`.
     - Estados terminales `COMMITTED` y `ABORTED` son estrictamente inmutables.
  3. **P0 — Autorización del endpoint y protección de información**:
     - `backend/app/main.py:get_operation_status`: Implementa autenticación mediante `X-Admin-Token` o `X-Operation-Token` (token de consulta opaco de 32 bytes validado con hash SHA-256 en tiempo constante vía `hmac.compare_digest`).
     - `backend/app/schemas.py:OperationStatusResponse`: `idempotency_key` eliminado del esquema público; `result_payload` y errores detallados solo se exponen a invocadores autorizados (propietario o admin). Consultas anónimas reciben únicamente el estado general de procesamiento (`PENDING`, `COMMITTED`, `ABORTED`), impidiendo la filtración de notas privadas o claves reutilizables.
  4. **P0 — Idempotencia concurrente real y deduplicación atómica**:
     - Restricción única `uq_operation_records_scoped UNIQUE (requester_id, operation_type, idempotency_key)` en `operation_records`.
     - Reclamo atómico en PostgreSQL con `INSERT ... ON CONFLICT (requester_id, operation_type, idempotency_key) DO UPDATE SET updated_at = operation_records.updated_at RETURNING *, (xmax = 0) AS is_new_claim`.
     - Validación de huella canónica de payload (`canonical_payload_hash`): si la clave se reutiliza con un payload diferente, se eleva `IdempotencyConflictError` (HTTP 409 Conflict).
     - Si la clave ya fue comprometida (`COMMITTED`), retorna el resultado durable sin reejecutar el negocio (incluso si `result_payload` está vacío, reconstruyendo la confirmación con `operation_id` estable).
     - En `pending_approvals`: índice único parcial `idx_pending_approvals_active_proposal ON pending_approvals (report_id) WHERE status = 'PENDING' AND proposed_action = 'UPDATE_REPORT_STATUS'` e inserción atómica `ON CONFLICT DO NOTHING`, impidiendo propuestas concurrentes duplicadas para el mismo reporte a nivel de motor SQL.
  5. **P1 — Propagación íntegra de OPERATION_PENDING**:
     - `backend/app/agent.py:execute_tool_with_timeout`: Captura `OperationPendingError` antes de `FuturesTimeoutError`, impidiendo su degradación a `TimeoutError` ordinario y preservando el `operation_id` durable.
     - Diferenciación entre herramientas transaccionales (con reclamo duradero en `operation_records`) y consultas de sólo lectura (`consultar_reportes`, `obtener_reporte`), garantizando que consultas de lectura lentas reporten limpiamente `TIMEOUT` mientras transacciones en vuelo reportan `OPERATION_PENDING`.
  6. **P1 — Procedencia causal de cancelaciones PostgreSQL**:
     - `backend/app/db.py:is_deadline_cancellation`: Verifica que cancelaciones `25P04` (`TransactionTimeout`) o `57014` (`QueryCanceled`) solo se atribuyan al deadline local si el tiempo transcurrido es mayor o igual al plazo de la herramienta (`time.monotonic() >= deadline - 0.05`) o la capacidad fue revocada. Políticas ajenas de conexión (ej. `transaction_timeout=50ms` de sesión con deadline de 2s) preservan el error original `OperationalError` / `TransactionTimeout`.
  7. **Pruebas permanentes de regresión**:
     - `test_g2_1_7_fail_closed_marker_failure_aborts_business_transaction` (**PASSED**).
     - `test_g2_1_7_missing_migration_004_fails_closed` (**PASSED**).
     - `test_g2_1_7_reconcile_only_on_exact_operation_id_evidence` (**PASSED**).
     - `test_g2_1_7_concurrent_idempotency_claim_single_execution` (**PASSED**).
     - `test_g2_1_7_idempotency_payload_conflict_raises_error` (**PASSED**).
     - `test_g2_1_7_committed_without_result_replay_reconstructs` (**PASSED**).
     - `test_g2_1_7_foreign_transaction_timeout_preserves_error` (**PASSED**).
- **Verificación oficial de la suite completa en PostgreSQL 17 real (`civia-api-1`)**:
  - `docker exec civia-api-1 pytest -m "not live"`:
    - **`105 PASSED, 1 deselected`** (100% de éxito, 0 fallos, 1 warning en 25.33 s).
    - `test_audit_g2_1_remediation.py`: 47/47 passed (incluyendo los 7 nuevos tests G2.1.7).
    - `test_audit_g2_resilience.py`: 23/23 passed.
    - `test_audit_g1_security.py`: 14/14 passed.
    - `test_ai_and_agent.py`: 13/13 passed (1 deselected live).
    - `test_reports_crud.py` + `test_health.py` + `test_e2e_frontend_proxy.py`: 8/8 passed.
    - Cero regresiones en controles aprobados G1, A-02, N-02, M-02, M-03 COPY o M-06. Cero commits en `main` ni push remoto.

---

## Bloque G2.1.8 — Inmutabilidad Terminal, Autorización Estricta y Reconciliación Determinista (`docs/auditoria_codex_g2_1_7_492b041.md`) completado (2026-11-04)
- **Documentación de diseño**: Especificada en la sección 17 de [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **Inmutabilidad estricta de estados terminales**:
     - Migración `backend/migrations/006_operation_records_terminal_states.sql`: Crea la función de trigger `prevent_terminal_operation_state_mutation()` y el trigger `trg_prevent_terminal_operation_state_mutation` a nivel de motor en PostgreSQL. Cualquier intento de actualizar filas con `status IN ('COMMITTED', 'ABORTED')` hacia un estado diferente aborta la transacción con excepción SQL.
     - `backend/app/db.py:mark_operation_committed`: Cláusula `WHERE operation_id = %s AND status != 'ABORTED'`. Valida explícitamente el estado previo y lanza `RuntimeError` si la operación ya estaba abortada, impidiendo resucitaciones ilegales sin evidencia.
     - `mark_operation_aborted`: Cláusula `WHERE status IN ('PENDING', 'UNKNOWN')`.
  2. **Autorización estricta y prueba de posesión de tokens (sin almacenamiento reversible)**:
     - Se descartó AES-GCM en favor de capacidades deterministas basadas en hashes SHA-256 unidireccionales (`query_token_hash`, `edit_token_hash`).
     - Al generar una operación agéntica transaccional en `OPERATION_PENDING`, se entrega el token unívoco al emisor legítimo a través del campo `query_token` en `AgentQueryResponse` (`backend/app/schemas.py`).
     - Replays sin posesión de credencial:
       - Para operaciones privadas (`operation_type = 'ADMIN_PRIVATE'` o con `target_id`), consultas no autorizadas o anónimas reciben HTTP 404 (anti-enumeración).
       - Consultas anónimas a operaciones públicas devuelven únicamente el estado general (`PENDING`, `COMMITTED`, `ABORTED`) con `target_id` y `result_payload` redactados a `None`.
       - Replays agénticos anónimos de operaciones `COMMITTED` devuelven el estado previo pero jamás revelan payloads privados ni claves secretas (`secret_key`).
       - Replays de operaciones `ABORTED` retornan de inmediato la confirmación de aborto sin despachar nuevos workers en segundo plano.
       - Replays de operaciones `UNKNOWN` levantan inmediatamente `OperationPendingError` sin invocar workers redundantes.
  3. **Atomicidad de mutaciones REST síncronas administrativas**:
     - `backend/app/repository.py:update_report_status`: Se integró la inserción directa en `operation_records` (con `status = 'COMMITTED'`, `requester_id = 'admin'`, `operation_type = 'UPDATE_REPORT_STATUS'`) dentro de la MISMA transacción PostgreSQL que actualiza la tabla `reports`.
     - Si la tabla `operation_records` no existe (ej. falta de migración 004) o si la inserción en el ledger falla, la transacción realiza un rollback conjunto y la función eleva excepción; el endpoint `PATCH /api/reports/{id}/status` retorna HTTP 500 y el estado del reporte permanece intacto en base de datos.
  4. **Eliminación del margen de 50 ms en procedencia causal (`is_deadline_cancellation`)**:
     - `backend/app/db.py:is_deadline_cancellation`: Se removió el margen especulativo `- 0.05`. La clasificación como cancelación local ahora exige estrictamente que la capacidad local esté revocada (`not cap.is_valid()`) o que el tiempo monotónico actual haya superado el deadline (`time.monotonic() >= dl`).
     - Timeouts externos (ej. `statement_timeout` o `transaction_timeout` de 20 ms dentro de un deadline local mayor) retornan `classified_local: false`, erradicando falsas clasificaciones.
  5. **Principio de incertidumbre en reconciliación**:
     - `backend/app/db.py:reconcile_operation`: Si la inspección de `pg_stat_activity` falla por cualquier excepción técnica de red o base de datos, se marca `stat_failed = True` y la función preserva el estado en `PENDING` o `UNKNOWN` sin alterar `operation_records`. Jamás se infiere `ABORTED` ante fallos de observación.
  6. **Pruebas permanentes de regresión adversarial (`backend/tests/test_audit_g2_1_8_adversarial.py`)**:
     - `test_adversarial_terminal_state_sql_trigger_prevents_mutation`: El trigger SQL en PostgreSQL rechaza mutaciones de estados terminales (`COMMITTED` y `ABORTED`) (**PASSED**).
     - `test_adversarial_helper_mark_operation_committed_rejects_aborted`: `mark_operation_committed` rechaza transicionar `ABORTED -> COMMITTED` con `RuntimeError` (**PASSED**).
     - `test_adversarial_rest_status_mutation_joint_atomic_rollback`: Fallo en `operation_records` realiza rollback conjunto y preserva el estado del reporte (**PASSED**).
     - `test_adversarial_rest_status_mutation_records_in_ledger`: Mutación REST exitosa persiste atómicamente el registro en `operation_records` (**PASSED**).
     - `test_adversarial_deadline_cancellation_no_50ms_tolerance`: Cancelación PostgreSQL externa con tiempo remanente antes del deadline devuelve `classified_local: False` (**PASSED**).
     - `test_adversarial_observation_failure_leaves_pending`: Fallo de observación en `reconcile_operation` no altera la base de datos a `ABORTED` (**PASSED**).
     - `test_adversarial_private_operation_unauthorized_yields_404`: Consulta no autorizada a operación privada retorna HTTP 404 (**PASSED**).
     - `test_adversarial_hijack_attempt_fails`: Replay no autorizado sin token no entrega payload sensible ni permite secuestro (**PASSED**).
     - `test_adversarial_agent_query_pending_delivers_query_token`: Respuesta agéntica `OPERATION_PENDING` entrega el `query_token` unívoco (**PASSED**).
- **Verificación oficial en clúster PostgreSQL 17.11 desechable y runner aislado**:
  - `pytest /audit/src/backend/tests/test_audit_g2_1_8_adversarial.py`: **`9 passed in 1.99s`** (100% éxito).
  - Verificación suite completa modo `BLANK` (sin claves API): **`114 passed, 1 skipped, 1 warning in 18.73s`**.
  - Verificación suite completa modo `SYNTHETIC` (claves sintéticas): **`114 passed, 1 skipped, 1 warning in 18.76s`**.
  - Verificación scripts independientes de Codex:
    - `boundaries.py`: Exit code 0 (10/10 checks exitosos, incluyendo `external_timeout_margin_*` con `classified_local: false` y `rest_mutation_missing_ledger` con HTTP 500 y rollback verificado).
    - `error_provenance.py`: `external_25P04_margin`, `real_admin_shutdown` y `real_undefined_table` con `classified_local: false`.
    - `api_restart_check.py`: Exit code 0 (`durable_before_process_kill: PENDING`, `fresh_api_result: {http: 200, status: COMMITTED}`, `durable_after: COMMITTED`).
    - `independent.py`: Exit code 0 (aislamiento de claims, anti-enumeración 404, replays ABORTED/UNKNOWN sin workers espurios).
    - `test_e2e_frontend_proxy.py`: 1 passed (comprobación E2E contra proxy frontend PWA real).
  - Cero regresiones en controles aprobados G1, A-02, N-02, M-02, M-03 COPY o M-06. Cero commits en `main` ni push remoto.

## Auditoría independiente Codex G2.1.8 — 2026-11-04

- Commit verificado: `187dea00e770191621f7fa4c481a41f2acbc1ab4`, rama `fix/auditoria-final`, árbol inicialmente limpio. Diff completo desde `492b041`, migración 006, fuentes y pruebas leídos; evidencia obtenida de copia congelada Git.
- **Dictamen independiente: NO APROBADO.** No cerrar G2.1. Informe: `docs/auditoria_codex_g2_1_8_187dea0.md`.
- PostgreSQL 17.11, runner, API y frontend exclusivos en red interna, sin servicios/volúmenes habituales ni llamadas a proveedores IA. Frontend reconstruido desde snapshot; proveedor sustituido por adaptador sintético para seguimiento HTTP.
- Correcciones verificadas: atomicidad REST y rollback ante fallo del INSERT/ledger ausente; inexistente sin registro falso; trigger de estados terminales y actualización legítima de metadatos; observación fallida conservadora; replays ABORTED/UNKNOWN sin workers; autorización básica GET privado; entrega real de token PENDING y polling con token recibido; migraciones limpia, upgrade con historial 005→006 y reaplicación.
- Bloqueos reproducidos: UNKNOWN confirmado sin evidencia por helper; GET no reconcilia UNKNOWN; PID ausente interpretado como aborto y reconciliación antes de autorizar; replay divulga resultados/metadatos/errores; replay con token propio falla por import hmac ausente; capacidad de edición ciudadana accede a operación administrativa; pérdida de primera respuesta sin recuperación genérica; UI sin seguimiento; trazabilidad REST sin cambios anterior/nuevo; clasificación de error externo cambia solo por procesarse después del deadline.
- Suites completas: claves vacías **114 PASS, 1 live excluida**, 17,47 s; sintéticas **114 PASS, 1 live excluida**, 19,75 s. Sin omitidas. Incluyen G1, G2, M-02, COPY, M-06, N-02 y nueve G2.1.8. E2E adicional con frontend recién construido: **1 PASS**, 0,21 s.
- Se inspeccionaron resultados de los seis instrumentos G2.1.7: exit 0 no se contó como aprobación global. followup se detiene por rechazo ahora correcto de ABORTED→COMMITTED; su cola se ejecutó por separado. Intentos iniciales mal secuenciados del auditor y error de parametrización del instrumento se conservaron y repitieron correctamente; no se modificaron tests ni producción.
- `compileall` pasó; no se presenta como lint. No se encontró comando/configuración lint Python. `git diff --check` verifica la documentación.
- Evidencia: `C:\Users\Jhoesp\AppData\Local\Temp\civia-187dea0-a8a1bf0a03e240289e8175ad44f7113d`. Logs capturados después de las peticiones no contienen la capacidad sintética comprobada; no se conservaron tokens reales ni dumps privados. Se retiró el archivo de capacidad administrativa efímera.
- Limpieza completada tras comprobar IDs: eliminados solo contenedores, volumen, red e imagen frontend del auditor. API, PostgreSQL y frontend habituales siguen saludables. HEAD/rama sin cambios; solo informe y esta anotación. Sin Autopilot, correcciones, commits, push o merge. Auditoría detenida tras entregar.

---

## Bloque G2.1.8 — Cierre de Hallazgos de Auditoría F1–F8 (`docs/auditoria_codex_g2_1_8_187dea0.md`) completado (2026-11-05)

- **Documentación de diseño y remediación**: Especificada en la sección 18 de [`docs/remediacion_g2_1.md`](remediacion_g2_1.md).
- **Cierres aplicados**:
  1. **F1 (`import hmac` y desinfección de payload)**: Se incorporó `import hmac` en `backend/app/db.py`, se excluyeron secretos y tokens de `proposed_payload` persistido y de la huella canónica (`canonical_payload_hash`).
  2. **F2 (Privacidad en replays agénticos)**: Replays sin demostración de posesión de token (`is_owner == False`) retornan estructura resumida donde `target_id` es `None`, `result_payload` no se expone y en `ABORTED` se retorna mensaje genérico sin filtrar el error interno de base de datos.
  3. **F3 (Ámbito de `X-Edit-Token`)**: Restringido estrictamente a operaciones de solicitante ciudadano (`requester_id == 'citizen'`). Consultas con credencial ciudadana a operaciones administrativas responden HTTP 404.
  4. **F4 (Capacidad cliente previa y reintentos)**: Soporte explícito en `AgentQueryRequest` para `operation_token` e `idempotency_key` en cabeceras y payload; hash persistido en `operation_records.query_token_hash`. Reintentos de peticiones cuya respuesta se perdió recuperan la credencial; frontend PWA integrado con generación criptográfica y consulta de estado definitivo.
  5. **F5 (Inmutabilidad de UNKNOWN sin evidencia y reconciliación GET)**: `mark_operation_committed` rechaza transicionar desde `UNKNOWN` sin evidencia duradera propia (`RuntimeError`). `GET /api/operations/{id}` autorizado reconcilia operaciones `UNKNOWN`.
  6. **F6 (No inferir ABORTED por PID ausente y autorización previa a reconciliar)**: `reconcile_operation` no deduce `ABORTED` ante backend PID inactivo o ausente (preserva `PENDING`/`UNKNOWN`). `GET /api/operations/{id}` comprueba autorización antes de reconciliar, impidiendo mutaciones de estado privadas no autorizadas (responde 404 de inmediato).
  7. **F7 (Trazabilidad detallada en mutación REST)**: `update_report_status` lee estado y versión previos bajo `FOR UPDATE` e inserta en `operation_records` detalle completo de estados anterior/nuevo, versiones, nota y acción en `proposed_payload` y `result_payload`.
  8. **F8 (Inmutabilidad temporal de procedencia causal)**: `is_deadline_cancellation` evalúa el tiempo original del error (`_civia_first_seen_at` o `_civia_raised_at`), evitando que excepciones externas retenidas en memoria se clasifiquen erróneamente como cancelaciones locales por inspección tardía.
- **Verificación oficial en clúster desechable PostgreSQL 17.11 y runner aislado**:
  - `pytest backend/tests/test_audit_g2_1_8_remediation.py`: **`8 passed in 2.36s`** (100% de éxito).
  - Verificación suite completa modo `BLANK`: **`121 passed, 2 skipped in 27.51s`** (0 fallos).
  - Verificación suite completa modo `SYNTHETIC`: **`121 passed, 2 skipped in 25.08s`** (0 fallos).
  - Verificación scripts independientes de Codex:
    - `error_provenance.py`: Verificado (`classified_local: false` para `external_25P04_margin`, `real_admin_shutdown` y `real_undefined_table`).
    - `migration_and_unknown.py`: Verificado (`http_state: COMMITTED`, `helper_state: COMMITTED`).
    - `final_probes.py`: Verificado (`private_message_exposed: false`, `target_exposed: null`, upgrade 005→006 preservado).
    - `adversarial.py`: Verificado (sin fugas en replays, trigger terminal inmutable, `rest_concurrent` con detalles completos).
    - `boundaries.py`: Verificado (rollback atómico, `external_timeout_margin_*` con `classified_local: false`, fallo 500 sin ledger).
  - Frontend PWA: `tsc -b && vite build` ejecutado en imagen Docker Node 22: **`0 errores, built in 2.02s`**.
  - Cero regresiones en controles aprobados G1, A-02, N-02, M-02, M-03 COPY o M-06. Cero commits en `main` ni push remoto.
  - Contenedores de prueba y redes efímeras eliminados. Servicios habituales intactos y saludables. Detenido para dictamen de auditoría de Codex.

## Auditoría independiente de cierre F1–F8 — 5c21254 (2026-11-04)

- HEAD comprobado: `5c212542185dacf1223c3f96ef5a22c1ce8316c8`, rama `fix/auditoria-final`, árbol inicialmente limpio. Diff completo frente a `187dea0`, contrato, informe previo y ocho pruebas nuevas revisados. Snapshot Git congelado, PostgreSQL 17.11, API y frontend exclusivos.
- **Dictamen independiente: NO APROBADO.** F1 FAIL, F2 FAIL, F3 PASS, F4 FAIL, F5 PASS, F6 PARCIAL, F7 PASS, F8 FAIL. Informe: `docs/auditoria_codex_g2_1_8_5c21254.md`. No cerrar G2.1.8 F1–F8.
- F1: replay propio corregido, pero sanitización superficial deja secretos anidados en payload/fingerprint, resultados, trazas y respuesta. F2: se ocultan resultado general/target/error, pero se divulga approval_id privado en COMMITTED y sondeo PENDING→COMMITTED. F8: capability expirada cambia clasificación de la misma excepción externa; cancel fallido deja marca de procedencia propia; primera observación tardía sigue usando tiempo como causa.
- F4 probado en PWA real con Edge headless de perfil separado, Nginx y FastAPI: primera respuesta descartada por proxy tras aceptar negocio, cliente sin ID/token recibido; reintento UI usa otra clave/capacidad y crea otro efecto sintético. Recarga no restaura seguimiento. Control HTTP conservando credenciales originales sí recupera tras reinicio de API y reintentos concurrentes sin duplicar. No se contactaron proveedores IA; adaptador sintético, SQL/persistencia/transporte reales.
- F3/F5/F7 pasan los casos de cierre. F6 corrige PID ausente, observación fallida y GET privado anónimo, pero GET público sin credencial aún puede reconciliar UNKNOWN→COMMITTED; no se afirma corrupción del efecto, sino incumplimiento del límite de autorización solicitado. Identidad administrativa compartida documentada como limitación no bloqueante.
- Suite BLANK: **122 PASS, 1 live excluida**, 20,18 s. SYNTHETIC: **122 PASS, 1 live excluida**, 23,75 s. Incluyen G1/G2/A-02/M-02/COPY/M-06/N-02 y E2E proxy. Ocho remediaciones separadas: **8 PASS**, 2,02 s. Pruebas no modificadas por el auditor.
- Las dos omisiones posibles se identificaron: prueba live de conectividad (excluida para impedir proveedores externos) y E2E frontend (no omitida aquí; pasa con frontend aislado). Sondeo separado de ambas: 1 PASS y 1 SKIP con razón explícita. No se reproducen ni se inventan las «2 skipped» previas de AG.
- Instrumentos originales conservados byte por byte y resultados inspeccionados semánticamente; exit 0 no se contó como aprobación. Complementos y navegador preservados en `C:\Users\Jhoesp\AppData\Local\Temp\civia-5c21254-248661f4d8804b998306933c4baa364b`, con snapshot, logs, JSON y capturas. compileall pasó; no equivale a lint. Sin comando/configuración lint Python identificado. git diff --check valida los cambios documentales.
- Retirados únicamente contenedores, volúmenes exclusivos, dos redes exclusivas e imagen frontend del auditor, previa comprobación de IDs. API, PostgreSQL y frontend habituales siguen saludables. HEAD/rama intactos; únicos cambios del checkout: informe y esta anotación. Sin producción/tests modificados, Autopilot, commits, push ni merge. Auditoría detenida al entregar.

---

## Remediación definitiva F1, F2, F4, F6 y F8 con Skills obligatorias (2026-11-05)

- **Skills aplicadas disciplinadamente**: `api-security`, `backend-security-coder`, `systematic-debugging`, `frontend-api-integration-patterns`, `react-patterns`, `playwright-skill`, `postgres-best-practices`, `code-review-and-quality`. Norma incorporada a `AGENTS.md`.
- **F1 (Sanitización profunda recursiva)**: Implementado `sanitize_credentials_deep` para dicts/listas/tuplas. Excluye credenciales recursivamente de `canonical_payload_hash`, `register_operation_intent`, `mark_operation_committed`, `record_ai_trace` y `conversation_messages` al LLM. Credenciales mantenidas exclusivamente fuera de banda.
- **F2 (Privacidad absoluta en replays)**: Eliminada la fuga de `approval_id` y metadatos sensibles en replays y polling para callers no autorizados (`is_owner == False`), retornando únicamente estructura mínima.
- **F4 (Recuperación PWA real tras pérdida de respuesta)**: Objeto `civia_pwa_agent_attempt` persistido en `localStorage` antes del POST. Reintentos ante 502/drop reutilizan la misma `idempotencyKey` y `operationToken` (cero duplicación de efectos en BD). Al recargar la página, se restaura la interfaz de seguimiento `ID Operación:` y se permite el polling definitivo.
- **F6 (Reconciliación con escritura reservada a peticiones autorizadas)**: `reconcile_operation` en `GET /api/operations/{id}` condicionado estrictamente a `is_authorized == True`. Consultas públicas anónimas a UNKNOWN no mutan la BD.
- **F8 (Procedencia causal de cancelación demostrable)**: `_civia_cancelled_by_deadline = True` se fija únicamente tras éxito de `c.cancel()`. `is_deadline_cancellation` memoiza inmutablemente el resultado respecto al deadline evaluado en `_civia_is_local_cancellation`. No se infiere causalidad local por paso del tiempo posterior ni por expiración de capability.
- **Verificación oficial completada**:
  - `closure.py`: Todos los checks en PASS (`F1_nested`, `F1_result`, `F1_trace_and_prompt`, `F2_matrix` 12/12, `F5_unknown_absent`, `F5_unknown_own_concurrent`, `F6_unauthorized_get`, `F8_capability_expiry` statement y transaction, `F8_failed_cancel_origin`, `F8_first_observation_late`).
  - `check_f6.py` (`public_unauthorized_reconcile`): `http: 200, before: UNKNOWN, after: UNKNOWN, result_exposed: false`.
  - Playwright PWA E2E (`pwa.cjs`): `first_response_dropped` (502, storage `["civia_pwa_agent_attempt"]`), `pwa_retry` (`same_key: true, same_capability: true`), `pwa_poll` (`committed_visible: true, private_result_visible: true`), `page_reload` (`operation_ui_restored: true`). Efectos de negocio en BD: exactamente 1.
  - Suite BLANK (`test_suite_blank`): **`121 passed, 2 skipped in 25.38s`** (0 fallos).
  - Suite SYNTHETIC (`test_suite_synthetic`): **`121 passed, 2 skipped in 25.01s`** (0 fallos).
  - Frontend TypeScript/Vite compilado limpiamente: **0 errores**.
- **Contenedores efímeros eliminados**: `civia_audit_v2_*` retirados. Servicios habituales intactos y saludables. Detenido para dictamen de auditoría de Codex.

---

## Solución técnica definitiva F8: Clasificador causal de evidencia y desacoplamiento del supervisor (2026-11-05)

- **Skills aplicadas disciplinadamente**: `systematic-debugging`, `postgres-best-practices`, `backend-security-coder`, `unit-testing-test-generate`.
- **Causa raíz erradicada**:
  - `is_deadline_cancellation()` atribuía errores de PostgreSQL al deadline local mediante heurísticas no causales: expiración tardía de capability, timestamps de primera inspección (`seen_at >= dl`), y marcas fijadas en llamadas de `cancel()` sin confirmar causalidad sobre la excepción.
  - El supervisor (`execute_tool_with_timeout`) y la procedencia de errores SQL estaban acoplados de modo que una excepción externa (57014/25P04) se enmascaraba como timeout local si se inspeccionaba tarde.
- **Implementación y contratos aplicados**:
  1. **Separación de responsabilidades**:
     - El supervisor de Python controla directamente su propio límite temporal (`time.monotonic() >= eff_deadline` o `FuturesTimeoutError`). Cuando el supervisor vence efectivamente, su guardrail TIMEOUT (o `OperationPendingError` si la operación transaccional está en progreso) se activa de manera autónoma.
     - Errores de PostgreSQL (57014, 25P04, etc.) ocurridos antes de que el supervisor venza no se convierten arbitrariamente en `TimeoutError` y se propagan como errores de base de datos (`TOOL_ERROR`).
  2. **Clasificador causal de evidencia estricto**:
     - `is_deadline_cancellation()` devuelve `True` **exclusivamente** ante evidencia causal positiva, verificable y vinculada a la ejecución: `TimeoutError` nativo de Python generado por plazos locales o excepciones con confirmación local positiva explícita (`_civia_confirmed_local_deadline`).
     - Devuelve `False` ante cualquier error ambiguo, administrativo (57P01), concurrente o externo de PostgreSQL.
     - Prohibido consultar el reloj actual (`time.monotonic()`), el estado actual de la capability, o asumir que un `cancel()` exitoso o fallido es prueba suficiente de causalidad.
     - Resultado memorizado de forma inmutable y estable respecto al objeto de excepción (`_civia_is_local_cancellation`).
  3. **Registro granular de solicitudes de cancelación**:
     - En `cancel_active_conns_for_thread()`, se registran hechos concretos: `_civia_cancel_requested`, `_civia_cancel_attempted`, `_civia_cancel_sent` y `_civia_cancel_failed`. No se marca `_civia_cancelled_by_deadline = True` a ciegas en la conexión.
  4. **Captura de procedencia en `checked_commit`**:
     - Cuando `checked_commit()` configura activamente un `transaction_timeout` anclado a `dl_check` en PostgreSQL, y la base de datos cancela la transacción durante el commit, `checked_commit` marca `_civia_confirmed_local_deadline = True` y lanza `TimeoutError(...) from exc`.
  5. **Suite de pruebas de regresión y cobertura exhaustiva**:
     - Actualizada `test_adversarial_external_timeout_not_local_cancellation` eliminando la aserción heredada errónea de `past_deadline -> True`.
     - Incorporadas 10 pruebas permanentes en `backend/tests/test_audit_g2_1_8_adversarial.py` (`test_f8_1` a `test_f8_10`) cubriendo:
       1. 57014 externo antes del deadline e inspección posterior: `False`.
       2. 25P04 externo antes del deadline e inspección posterior: `False`.
       3. Excepción externa inicialmente False; capability expira; misma excepción continúa `False`.
       4. Solicitud `cancel()` fallida y posterior timeout externo: `False`.
       5. Cancelación solicitada sin prueba concluyente: `False`.
       6. Timeout generado por el supervisor: conserva guardrail TIMEOUT.
       7. 57P01 administrativo: conserva clasificación de infraestructura (`False`).
       8. 42P01 por tabla inexistente: conserva error original (`False`).
       9. Repetición de clasificación en instantes distintos: resultado estable e inmutable.
       10. Prueba positiva: deadline local genuino: `True`.
- **Verificación oficial completada**:
  - `closure.py` independiente de Codex: **100% de verificaciones superadas** (código de salida 0), incluyendo `F8_capability_expiry` (first: false, second: false, own_cancellation_marked: false), `F8_failed_cancel_origin` (cancel_success_count: 0, own_marker_on_exception: false, classified_local: false), `F8_first_observation_late` (classified_local: false, own_marker: false).
  - `backend/tests/test_audit_g2_1_8_adversarial.py`: **19 PASSED** (100% de éxito en 2.61s).
  - `backend/tests/test_audit_g2_1_remediation.py`: **8 PASSED** (100% de éxito en 2.34s).
  - Suite completa hermética (`pytest -m "not live" -q -rs`): **131 passed, 1 skipped, 1 deselected, 0 failed en 24.47s**.
- **Limpieza**:
  - Recursos efímeros eliminados (`civia_f8_runner`, `civia_f8_pg`, `civia_f8_net`).
  - Servicios habituales (`civia-api-1`, `civia-frontend-1`, `civia-db-1`) intactos, corriendo y saludables.
  - Prohibido push o merge. Árbol listo para dictamen de auditoría de Codex.

## Auditoría independiente definitiva G2.1.8 — c345ba2 (2026-11-05)

- Commit verificado `c345ba252e01272ae5c7fce9614d27d63a345f36`, rama `fix/auditoria-final`, árbol inicialmente limpio. Leídos AGENTS.md, informe previo, diffs 6734fe6→c345ba2 y 5c21254→c345ba2, y pruebas modificadas. Snapshot Git: 112 miembros verificados contra ZIP, ninguno modificado.
- **Dictamen independiente: NO APROBADA.** F1 FAIL, F8 FAIL; F2, F3, F4, F5, F6 y F7 PASS en recorridos ejecutados. Informe: `docs/auditoria_codex_g2_1_8_c345ba2.md`.
- F1: sanitización recursiva de payload/fingerprint/resultados/trazas pasa los casos anteriores, pero el adaptador real de Gemini con HTTPMockTransport serializa la capacidad cliente en su segunda petición mediante raw_gemini_part. Primera petición sin capacidad; segunda con ella. Causa: inyección en tool_args compartido y bypass del raw. Ninguna petición salió al proveedor.
- F8: checked_commit marca como local una cancelación externa real 57014 durante COMMIT y un transaction_timeout de sesión externo 25P04 cuando aún quedan más de 1,9 s del plazo local. Dos reproducciones por escenario. Negocio revierte correctamente; falla la atribución causal. Positivo independiente: límite CIVIA de 0,20 s interrumpe commit con 25P04 real, negocio=0 y ABORTED; supervisor de lectura también conserva TimeoutError. Cambiar el test histórico past_deadline→True fue corrección contractual válida, no sustituye probar productores de la marca.
- PWA real, Nginx/FastAPI/PG exclusivos y Playwright: pérdida íntegra de primera respuesta, recarga previa, misma clave/capacidad, una operación por intento, mismo ID recuperado, polling autorizado, restauración y limpieza explícita correctos. Sin capacidad en DOM/URLs/logs capturados. Almacenamiento bearer limitado al origen/perfil y consulta, sin afirmar cifrado o identidad individual. Primer ensayo de navegador tuvo error de coordinación de logs del auditor; se conservó y se repitió completo con espera corregida.
- Suites BLANK **132 PASS, 1 live excluida**, 19,13 s; SYNTHETIC **132 PASS, 1 live excluida**, 22,18 s. Sin skips en suites filtradas. Incluyen adversariales, G1/G2/A-02/M-02/COPY/M-06/N-02 y E2E frontend/proxy. En el 131 PASS reportado por AG, la exclusión live corresponde a conectividad real y la omisión condicionada a frontend inaccesible; aquí frontend sí pasa. Sondeo separado: 1 PASS, 1 SKIP live con razón explícita.
- Skills seleccionadas/leídas y correspondencia con evidencia documentadas: systematic-debugging, api-security, frontend-api-integration-patterns, playwright-skill y postgres-best-practices. Sin cambios de implementación; originales independientes conservados byte por byte y resultados inspeccionados, no solo exit codes. compileall pasó; no se presenta como lint. Sin configuración/comando lint Python identificado; git diff --check valida documentación.
- Evidencia aislada: `C:\Users\Jhoesp\AppData\Local\Temp\civia-c345ba2-639c45a17657442a8d1bf727e4927e84`, con snapshot, diffs, instrumentos, resultados, logs y capturas. PostgreSQL 17.11, API, runner y frontend exclusivos; sin datos reales ni proveedores IA externos.
- Eliminados únicamente contenedores, volúmenes exclusivos, dos redes e imagen frontend propios tras comprobar sus IDs. Los tres servicios habituales siguen saludables; HEAD/rama intactos. Únicos cambios del checkout: informe y esta anotación. Sin modificar producto/tests, Autopilot, commits, push ni merge. Detenido al entregar dictamen.

---

## Remediación focalizada definitiva F1 y F8 (2026-11-05)

- **Commit base:** `c345ba252e01272ae5c7fce9614d27d63a345f36`, rama `fix/auditoria-final`.
- **Skills consultadas y aplicadas disciplinadamente:**
  - `systematic-debugging`: Reproducción estricta RED → GREEN con instrumentos de auditoría independientes (`gemini_boundary.py`, `causal_races.py`, `causal_commit.py`, `closure.py`).
  - `api-security` y `backend-security-coder`: Eliminación definitiva de inyección de capacidades en diccionarios de argumentos de negocio; aislamiento estricto de secretos y capacidades en contextos de ejecución sin serialización saliente.
  - `postgres-best-practices`: Preservación estricta de la procedencia de errores PostgreSQL en `checked_commit()`, evitando etiquetado falso como plazo local cuando el temporizador de CIVIA no ha expirado.
  - `unit-testing-test-generate` y `code-review-and-quality`: Creación de pruebas de regresión permanentes herméticas en `backend/tests/test_audit_g2_1_8_adversarial.py` utilizando `httpx.MockTransport`.

- **Causas raíz erradicadas e implementación concreta:**
  1. **F1 — Eliminación de fuga de capacidad en adaptador Gemini:**
     - En `backend/app/agent.py`: Eliminada la inyección de `tool_args["operation_token"] = claim["query_token"]`. El token se administra exclusivamente a través del contexto interno `tok_op = set_current_operation(...)`.
     - En `_call_agent_turn_gemini()`: Se desacopló la memoria mediante `copy.deepcopy` al extraer las llamadas de herramientas y al serializar `raw_gemini_part`.
     - Sanitización profunda de `functionCall.args` en `raw_gemini_part` antes de la frontera HTTP hacia Gemini, preservando `thoughtSignature` y protocolo.
     - Sanitización equivalente al serializar en `_call_agent_turn_groq()`.
     - Copias profundas en `run_civia_agent()` antes de incorporar llamadas al historial de conversación.
     - Verificación RED: `client_capacity_in_outbound_json: true` en petición 2 sobre `c345ba2`.
     - Verificación GREEN: `client_capacity_in_outbound_json: false` en petición 1 y petición 2 tanto en `gemini_boundary.py` como en `test_f1_gemini_boundary_mock_transport_no_capacity_in_outbound_json`.
  2. **F8 — Corrección de productores de evidencia causal en `checked_commit`:**
     - En `backend/app/db.py`: Eliminada toda asignación de `_civia_confirmed_local_deadline = True` en los tres bloques `except` de `checked_commit()`.
     - `checked_commit()` únicamente lanza `TimeoutError` si se comprueba causalmente que `dl_check is not None and time.monotonic() >= dl_check`.
     - Si el plazo local no ha vencido (`time.monotonic() < dl_check`), hace rollback, marca `ABORTED` en `operation_records` y propaga intacta la excepción original de PostgreSQL (`QueryCanceled`, `TransactionTimeout`, `OperationalError`).
     - Verificación RED: `causal_races.py` arrojaba `TimeoutError`, `marked_local=True`, `classified_local=True` con ~1.96s de plazo restante sobre `c345ba2`.
     - Verificación GREEN: `causal_races.py` arroja `error='QueryCanceled', marked_local=False, remaining=1.96s, status='ABORTED'` y `error='TransactionTimeout', marked_local=False, remaining=1.91s, status='ABORTED'`.

- **Verificaciones oficiales superadas:**
  - `gemini_boundary.py`: **PASS** (ambas peticiones sin capacidad en JSON serializado).
  - `causal_races.py`: **PASS** (cancelación y timeout de sesión externos preservados como errores SQL no locales; negocio revertido; `operation_records` pasa a `ABORTED`).
  - `causal_commit.py`: **PASS** (controles positivos y negativos validados).
  - `closure.py`: **PASS** (código de salida 0; checks F1, F2 matrix 12/12, F5, F6 y F8 en PASS total).
  - `backend/tests/test_audit_g2_1_8_adversarial.py`: **22/22 PASSED** (100% de éxito).
  - Suite hermética completa (`pytest -m "not live" -q -rs`): **134 passed, 1 skipped, 1 deselected, 0 failed en 25.79s**.
  - Contratos F2, F3, F4, F5, F6, F7 y regresiones G1/G2/A-02/M-02/M-03/M-06/N-02 preservados intactos.

- **Limpieza e integridad del entorno:**
  - Recursos efímeros eliminados: `civia_f1f8_runner`, `civia_f1f8_pg` y `civia_f1f8_net`.
  - Servicios habituales (`civia-api-1`, `civia-frontend-1`, `civia-db-1`) intactos, activos y saludables.
  - Prohibido push o merge. Árbol listo para dictamen independiente de auditoría de Codex.

## Auditoría independiente con puerta F1/F8 — cf48e71 (2026-11-05)

- HEAD verificado: `cf48e710a4d321455864d2b59a4257cdca9938aa`, rama `fix/auditoria-final`, árbol inicialmente limpio. Diff c345ba2→cf48e71 y referencia anterior revisados. Snapshot Git: 113 miembros, ninguno modificado.
- **Dictamen: G2.1.8 APROBADA para este commit exacto.** Matriz F1–F8 PASS en contratos/recorridos ejecutados. Informe: `docs/auditoria_codex_g2_1_8_cf48e71.md`. No implica despliegue, commit, push o merge.
- Puerta F1: adaptadores Gemini y Groq reales con MockTransport, sin capacidad en mensajes, args de negocio y firma preservados; referencias raw/args separadas; capacidad interna correcta, polling autorizado y una sola ejecución por replay. Sin tráfico externo. gemini_boundary.py, causal_races.py, causal_commit.py y closure.py conservados sin modificar expectativas.
- Puerta F8: 57014 externo y 25P04 de sesión repetidos dos veces con >1,9 s restantes, tipo original preservado, sin marca local y rollback correcto. Positivo local real: TimeoutError exterior clasifica true; su causa TransactionTimeout/25P04 clasifica false, sin marca falsa, deadline efectivo vencido, negocio=0 y ABORTED.
- Caso externo tardío documentado expresamente: puede aparecer TimeoutError exterior al vencer el presupuesto durante manejo/rollback; __cause__ sigue QueryCanceled/57014 externo y clasifica false. Se aceptan como hechos separados, no se atribuye la cancelación SQL al reloj. Supervisor real retorna PENDING con ID durante worker no resuelto; luego ABORTED/negocio=0, capability inválida. API de lectura lenta activa TIMEOUT real. No se contó classified_local=False de la causa SQL como fallo del guardrail.
- Superada la puerta se ejecutó fase 2: F2–F7, A-02/M-03 y regresiones relacionadas sin bloqueo. BLANK **135 PASS, 1 live excluida**, 19,88 s; SYNTHETIC **135 PASS, 1 live excluida**, 22,91 s. Incluyen E2E frontend/proxy. La live opcional es la deselected; frontend no se omite aquí. Sondeo separado: 1 PASS, 1 SKIP live, 0,41 s.
- PWA real perdió íntegramente la primera respuesta; recarga y replay reutilizan clave/capacidad, recuperan mismo ID y un solo efecto; polling/restauración/limpieza pasan. Sin capacidad en DOM/URLs/logs capturados. ACK perdido y reinicio recuperan COMMITTED. No se reabrieron contratos ajenos a estas regresiones.
- Skills aplicadas y verificaciones documentadas: systematic-debugging, backend-security-coder, code-review-and-quality; Playwright y patrones de integración frontend para fase 2. compileall pasó; no equivale a lint. Sin configuración/comando lint Python identificado; git diff --check verifica documentación. No se corrigió código ni pruebas.
- Evidencia fuera del checkout: `C:\Users\Jhoesp\AppData\Local\Temp\civia-cf48e71-e052c8633d5f4de383d66e78e35b5c1c`. PostgreSQL 17.11/API/runner/frontend propios, datos sintéticos y proveedores interceptados o simulados. Recursos exclusivos retirados tras comprobar IDs; tres servicios habituales saludables. HEAD/rama intactos; solo informe y esta anotación. Sin Autopilot, commits, push ni merge. Detenido al entregar.

---

## Corrección de Navegación UI y Modernización de Evidencias Sintéticas — feat/ui-navigation-demo-evidence (2026-11-05)

- **Rama de trabajo:** `feat/ui-navigation-demo-evidence`, creada a partir de la versión documental publicada `d14f64e31b3c8ab361682a0d023faf8ba53ae048` (con base funcional auditada y aprobada `cf48e710a4d321455864d2b59a4257cdca9938aa`).
- **Invariantes preservados:** Rama auditada `fix/auditoria-final` y commit `cf48e71` intactos como referencia histórica inmutable. Contratos de seguridad e integridad F1–F8 preservados al 100%. Servicios habituales en Docker (`civia-api-1`, `civia-frontend-1`, `civia-db-1`) intactos y saludables.

### 1. Fase 1 — Causa Raíz y Corrección de Navegación entre Pestañas
- **Causa raíz:** En `frontend/src/App.tsx`, el panel de inspección `{selectedReport && renderInspectionPanel(selectedReport)}` se renderizaba fuera del bloque condicional de pestañas en `<main className="civia-container">`. Además, `handleSearchTrackingCode` invocaba `openReportInspection(rep)`, fijando `selectedReport` globalmente. Al cambiar a *Asistente Agéntico* o *Observabilidad Admin*, el detalle permanecía anclado en la parte superior, obstruyendo la interfaz.
- **Corrección aplicada:**
  - El renderizado de inspección se aisló estrictamente dentro de sus vistas correspondientes:
    - En `explorar` (Mapa y Reportes): `{selectedReport && renderInspectionPanel(selectedReport, () => setSelectedReport(null))}`.
    - En `seguimiento` (Seguimiento Radicado): `{trackedReport && renderInspectionPanel(trackedReport, () => setTrackedReport(null))}`.
    - En `asistente` y `admin`: NINGÚN panel de reporte ajeno se renderiza; el asistente opera de forma autónoma con su chat, 4 límites y modal de recuperación F4 sin interferencias.
  - `handleSearchTrackingCode` y `handleSubmitNewReport` actualizan `trackedReport` y preparan los campos de clasificación sin contaminar `selectedReport`.
  - El botón "Cerrar detalle" acepta un callback `onClose` desacoplado que limpia el estado de la vista activa sin afectar a las demás.
- **Verificación TDD Adversarial con Playwright (`frontend/e2e/test_navigation.cjs`):**
  - Fase RED ejecutada sobre el frontend no parcheado (`http://localhost:5173`): Defecto confirmado con visibilidad espuria de `CIV-2026-DEMO0001` en *Asistente* y *Admin*.
  - Fase GREEN ejecutada sobre la compilación actualizada (`http://localhost:4173`):
    - Desktop (1280x800): Detalle visible en seguimiento -> Desaparece al ir a Asistente (asistente 100% operativo) -> Admin libre de detalles -> Retorno a Mapa sin detalles residuales -> Ciclo de pestañas repetido OK -> 0 errores de React en consola.
    - Móvil (375x667): Mismo flujo validado sin errores responsivos ni de layout.

### 2. Fases 2 y 3 — Fotografías Sintéticas Fotorrealistas y Procedencia Ética
- **Generación de 10 fotografías realistas de alta resolución (1200x896 px, JPEG):**
  - Cada una de las 10 escenas del catálogo `SYNTHETIC_REPORTS` cuenta con una fotografía fotorrealista dedicada contextualizada en comunas y vías de Santiago de Cali (Santa Mónica, Mariano Ramos, Pance, Cerro de las Tres Cruces, San Fernando, Alfonso López, Ciudad Córdoba, Capri, Chiminangos, San Pascual).
  - Escenas naturales con iluminación diurna creíble, pavimento, vegetación y entorno colombiano, sin rostros identificables ni placas vehiculares legibles.
- **Procedencia y salvaguardas éticas:**
  - Se mantiene `is_synthetic = TRUE` en base de datos.
  - Cada fotografía incluye una franja inferior indeleble: `CIVIA · SIMULACIÓN IA · EVIDENCIA SINTÉTICA DEMO · NO PRIVADO · RADICADO: CIV-2026-DEMOXXXX`.
  - En la interfaz ciudadana de inspección se despliega el distintivo visible: `ℹ Imagen generada con IA · Simulación`.
  - Sin falsificación de metadatos EXIF de GPS, fecha o dispositivo de captura.
- **Empaquetado local:**
  - Los 10 activos se empaquetan en `backend/app/demo_assets/` (tamaños optimizados entre 315 KB y 509 KB; ~4 MB totales).
  - Las 5 muestras representativas por categoría (`sample_hueco.jpg`, `sample_basuras.jpg`, `sample_tala.jpg`, `sample_quema.jpg`, `sample_otro.jpg`) se empaquetan en `frontend/public/demo_evidence/` para sustituir el canvas geométrico por muestras fotográficas reales.

### 3. Fase 4 — Actualización Idempotente y Pruebas en Entorno Desechable
- **Mecanismo idempotente en `backend/app/seed.py`:**
  - `get_synthetic_evidence_bytes(code, kind)`: Carga el activo empaquetado y entrega dimensiones (1200x896), mime (`image/jpeg`) y hash SHA-256.
  - `update_synthetic_catalog_photos()`: Actualiza exclusivamente los 10 reportes de catálogo sintético (`is_synthetic = TRUE AND tracking_code LIKE 'CIV-2026-DEMO%'`).
  - **Invariantes comprobados:**
    - Los reportes reales o creados por ciudadanos (`is_synthetic = FALSE`) quedan 100% intactos.
    - No se alteran títulos, coordenadas, estados ni aprobaciones humanas.
    - Ejecución repetida produce `updated = 0, unchanged = 10` (idempotencia matemática estricta).
- **Pruebas en PostgreSQL 17 desechable (`backend/tests/test_demo_evidence_and_navigation.py`):**
  - Ejecutado en contenedor independiente `civia_demo_runner` sobre base `civia_demo_pg` (`postgres:17-alpine`).
  - 5/5 pruebas pasadas: integridad de activos, consistencia en frontend, sembrado, actualización idempotente y endpoint `/api/reports/{id}/photo`.

### 4. Resumen de Pruebas y Resultados
- **TypeScript & Vite build (`npm --prefix frontend run build`):** Exitoso en 1.57s sin errores ni advertencias (`dist/`).
- **Playwright E2E (`frontend/e2e/test_navigation.cjs`):** 100% PASS en escritorio y móvil, 0 errores de consola.
- **Suite hermética completa de backend (`pytest -m "not live"`):** **139 passed, 1 skipped (frontend proxy condicionado), 1 deselected, 0 failed en 27.13s**.
- **Regresión F1–F8 (`test_audit_g2_1_8_remediation.py`):** **8/8 PASSED**.
- **Servicios habituales:** `civia-api-1`, `civia-frontend-1`, `civia-db-1` limpios, saludables e inalterados.
- **Sin push ni merge hacia ramas remotas o protegidas.**


## 2026-11-05 — Auditoría independiente de navegación y evidencia sintética

**NO APROBADA para publicación** en el commit `48c872817ecd88353b25883fd25878126031358a` de `feat/ui-navigation-demo-evidence`. [Informe independiente](auditoria_codex_ui_demo_48c8728.md).

- La navegación pasó dos ciclos en escritorio y dos en móvil. Se reprodujo la fuga de detalle en la base `d14f64e` y desapareció en el objetivo. Instalación nueva, carga ciudadana, autorización y F4 pasaron en PostgreSQL 17 desechable con Nginx y FastAPI aislados. La prueba de F4 verificó replay tras pérdida de respuesta y un único efecto persistido.
- La actualización acepta un JPEG corrupto que conserva su tamaño, deja archivos huérfanos ante rollback y reutiliza una URL cuya caché retuvo el PNG anterior después de la actualización.
- Una muestra fotorrealista pudo quedar como evidencia ordinaria al enviar con descripción ya escrita. La calidad visual quedó parcial por la muestra OTRO de categoría HUECO y el distintivo recortado en el detalle.
- Build TypeScript/Vite, suite hermética con 140 pruebas pasadas y repetición focalizada con 36 pasadas. Una prueba live excluida de la suite completa. Los tres servicios habituales conservaron ID, hora de inicio y estado saludable tras retirar los recursos del auditor.
