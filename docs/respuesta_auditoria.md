# CIVIA — Respuesta argumentada a auditorías · Momento 3

**Equipo:** Stefania Córdoba y Sebastian Espinosa · **Fecha:** 21 de noviembre de 2026 · **Versión objetivo:** CIVIA 1.1.1.

> **Alcance y procedencia:** el repositorio contiene auditorías técnicas independientes de Codex con hallazgos reproducibles en versiones anteriores. **No se entregó el acta de una auditoría cruzada realizada por otro equipo de clase**. Por tanto, este documento responde a hallazgos internos reales y deja explícita la obligación de incorporar sin alteraciones cada observación del equipo auditor cuando se reciba. No se atribuyen estos hallazgos a otro estudiante ni se simula una respuesta institucional.

## Metodología

1. Se leen `docs/auditoria_codex.md`, `docs/auditoria_codex_final.md`, `docs/auditoria_codex_g1*.md`, `docs/auditoria_codex_g2*.md` y `docs/seguridad.md`.
2. Se identifican fallos demostrados en un **commit histórico**, su efecto sobre CIVIA y el control actual que lo aborda.
3. Se clasifica cada respuesta como **corregido según evidencia posterior**, **limitación aceptada con justificación** o **pendiente de verificación**. Un PASS de una suite no demuestra que nunca pueda reaparecer el fallo.
4. La revisión actual se basa en código y evidencias publicadas. No se afirma una nueva auditoría ejecutada en el equipo del profesor.

## Matriz de respuesta a hallazgos internos

| ID / hallazgo | Evidencia y riesgo histórico | Respuesta y decisión | Evidencia actual / límite |
|---|---|---|---|
| C-01 — credencial administrativa débil/predeterminada | `auditoria_codex_final.md` reprodujo acceso administrativo con configuración insegura | **Corregido para instalación nueva:** bootstrap genera secretos con CSPRNG; usuarios tienen sesiones y roles, y el legado no habilita acceso ciudadano | `backend/app/identity.py`, scripts de bootstrap y pruebas; rotación de credencial **histórica** PostgreSQL sigue pendiente |
| A-01 — edición o confirmación de reporte ajeno | Auditorías antiguas mostraron que un identificador público no basta para autorizar | **Corregido según pruebas posteriores:** identidad autenticada, titularidad y recursos protegidos por API | `backend/app/identity.py`, `backend/app/main.py`, pruebas de propietario/RBAC; verificar despliegues heredados tras migración |
| A-02 / M-03 — escritura tardía tras timeout | `auditoria_codex_final.md` y G2 probaron mutaciones después del deadline | **Corregido en los contraejemplos auditados:** contexto temporal, verificación de transacción y cancelación supervisada | `docs/auditoria_codex_g2_1_8_cf48e71.md` informa PASS F8 con límites; no afirmar garantía absoluta bajo toda falla de infraestructura |
| A-03 — salida IA inventada o fuera de esquema | El modelo devolvía categoría/confianza inválida | **Corregido según contratos:** validación estricta Pydantic; entradas inválidas no se convierten silenciosamente en análisis válido | `backend/app/ai_router.py`, pruebas de esquema; validación de sintaxis no garantiza veracidad semántica |
| A-04 — información técnica y personal expuesta | Cadenas y campos anidados se filtraban en respuestas/trazas | **Corregido según pruebas F1/F2:** sanitización, respuestas por rol y límites de salida | `docs/auditoria_codex_g2_1_8_cf48e71.md` informa PASS; persiste riesgo de datos sensibles incluidos en evidencia cargada por el usuario |
| A-05 — abuso de cuota y bloqueo de API | Pruebas antiguas encontraron límites eludibles | **Mejorado:** presupuesto local, rate limits, cuotas y cola con capacidad acotada | `backend/app/inference_transport.py`, `backend/app/analysis_queue.py`; no garantizar resistencia a DDoS de gran escala |
| A-06 — radicación duplicada en reintentos | Mismo intento podía generar dos UUID | **Corregido según pruebas:** clave de idempotencia persistida y creación del reporte desacoplada de inferencia/traza | `backend/app/main.py`, cola transaccional; un usuario debe preservar la misma clave al reenviar el mismo intento |
| A-07 — propuesta obsoleta sobrescribe gestión | Un cambio posterior quedaba pisado por aprobación tardía | **Corregido en pruebas de versión y concurrencia:** propuesta con estado/version y revisión humana | `backend/app/agent.py` y endpoint `/api/admin/approvals/{approval_id}/decide` |
| M-01 — audio ficticio o malformado | Extensiones/firmas suplantadas podían aceptarse | **Mejorado:** validación de formato, cabeceras, tamaño, duración y controles de evidencia | `backend/app/security.py` y pruebas; formatos no soportados deben rechazarse, no fingirse transcritos |
| M-02 — exceso de tokens/iteraciones | Límite verificable solo al final de la llamada | **Mejorado:** reserva de presupuesto, caps de servidor y rechazo temprano | `backend/app/agent.py` e `inference_transport.py`; costos externos reales dependen de la cuota y tarifas del proveedor |
| M-04 — múltiples sondas HALF_OPEN | Circuit breaker permitía llamadas simultáneas durante recuperación | **Corregido en pruebas específicas:** control de concurrencia y estados del circuito | `backend/app/ai_router.py` y auditorías G2.1.x |
| M-06 — IP falsificada a través de proxy | Cabeceras X-Forwarded-For permitían evasión del límite | **Mejorado:** confianza de proxy limitada y gateway controlado | Prueba del proxy Docker en CI; todo nuevo modo de red requiere verificar su configuración |
| M-07 / N-03 — pruebas contaminan datos ajenos | Teardown limpiaba filas fuera de su ejecución | **Corregido según evidencia:** bases descartables, propiedad de datos de test y aislamiento Compose | CI de Linux AMD64/ARM64, clones limpios; prohibido `down -v` en despliegue habitual |
| B-01 — dependencias no reproducibles | Instalación condicionada por herramientas/paquetes del host | **Mejorado:** Docker, archivos de dependencias y CI multi-arquitectura | Windows AMD64 y CI Linux AMD64/ARM64 comprobados; macOS no probado |
| B-02 — salud falsa cuando BD falla | Health 200 aunque dependencias no respondieran | **Mejorado:** healthchecks y pruebas de proxy/Compose | `docs/estado.md`; distinguir salud API y disponibilidad de proveedor de IA |
| B-03 — archivos huérfanos y colisiones de radicado | Foto persistida sin reporte y códigos potencialmente duplicados | **Corregido según pruebas de transacción/almacenamiento:** evidencia inmutable e idempotencia | `backend/app/main.py`, `backend/app/security.py`, pruebas de radicación y reversión |
| F1–F8 — operación segura ante pérdida de respuesta, replay, SQL causal y privacidad | Auditorías G2.1.8 detectaron filtración de capacidad, reejecución y confusión del origen de timeout | **Corregido dentro del alcance auditado:** `auditoria_codex_g2_1_8_cf48e71.md` informa PASS F1–F8 | El dictamen se refiere al commit `cf48e71...`; la versión 1.1.1 añade pruebas, pero no implica prueba exhaustiva contra toda amenaza futura |

## Respuesta a límites aceptados de la versión 1.1.1

| Riesgo abierto | Decisión | Justificación / compromiso verificable |
|---|---|---|
| Gemini muestra catálogo pero genera 403 | **Aceptado temporalmente** | Groq validado, cola y reintentos; no se presenta a Gemini como operativo. Diagnóstico de proyecto/cuotas antes de reintentar |
| La red Docker tiene salida general | **Aceptado solo para la demostración local** | Adaptador de inferencia limita destinos; un despliegue público requeriría aislamiento efectivo del egreso |
| Credencial PostgreSQL antigua de instalación habitual | **Pendiente operativo relevante** | Rotar coordinadamente sin resetear volumen, documentar respaldo y prueba de restauración |
| PWA HTTPS en teléfono físico, Docker macOS | **No verificado** | No declarar estas comprobaciones aprobadas |
| Auditoría cruzada del equipo externo | **Sin acta proporcionada** | Anexar íntegros hallazgos recibidos y responder cada uno con ruta de código, evidencia y aceptación de riesgo cuando corresponda |

## Plantilla para incorporar la auditoría cruzada realmente recibida

**Equipo auditor:** PENDIENTE DE DOCUMENTAR.\
**Fecha y commit auditado:** PENDIENTE.\
**Evidencia original:** enlace o acta del equipo auditor: PENDIENTE.

| Hallazgo literal del otro equipo | Evidencia / reproducción | Respuesta: arreglamos o asumimos y por qué | Archivo/línea o prueba | Estado |
|---|---|---|---|---|
| **PENDIENTE — no inventar hallazgos** | — | — | — | — |

> La rúbrica considera válida una aceptación de riesgo argumentada; **no** califica igual inventar que un tercero auditó el proyecto. Si no hubo auditoría cruzada, registrar esa limitación y buscar la revisión real del curso.

## Trazabilidad adicional

- [Auditoría inicial](auditoria_codex.md), [auditoría final 1.0](auditoria_codex_final.md), [G2](auditoria_codex_g2.md), [cierre F1–F8](auditoria_codex_g2_1_8_cf48e71.md).
- [Seguridad 1.1.1](seguridad.md), [gobernanza](gobernanza.md), [estado](estado.md).
- [Rúbrica oficial](https://ingenieria-aplicaciones-ia.netlify.app/momento3_rubrica).
