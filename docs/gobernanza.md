# CIVIA — Ficha de gobernanza · Momento 3

**Equipo:** Stefania Córdoba y Sebastian Espinosa · **Versión analizada:** CIVIA 1.1.1 (`main`, referencia `ced4ea4a9b1d48595ac4de554a0ef96e1c7a335b`) · **Fecha:** 21 de noviembre de 2026.

> Ficha de cinco preguntas operativas ajustada a la rúbrica del Momento 3. No se dispone de un formulario de preguntas distinto en los materiales revisados. Las capacidades y límites siguientes describen el sistema actual y separan los riesgos residuales de las mejoras futuras. CIVIA es un proyecto académico; no representa a una autoridad municipal.

## 1. ¿Para qué usamos IA y qué decisiones dejamos fuera de ella?

CIVIA usa IA para clasificar evidencia fotográfica y descripciones, transcribir notas de voz y ofrecer un asistente que consulta información mediante herramientas tipadas. El reporte se radica con reglas deterministas **antes** de invocar modelos. La creación del radicado, validación de archivos, autenticación, permisos, idempotencia, consultas relacionales por filtros y cambios administrativos no dependen del LLM. Se eligió PostgreSQL/SQL directo —no RAG— porque los datos son estructurados y las preguntas por estado, comuna o radicado requieren resultados exactos.

La IA no tiene autoridad para cerrar un incidente, cambiar roles, enviar datos a terceros arbitrarios o declarar una acción institucional oficial. Sus análisis son propuestas sujetas a reglas y revisión humana.

**Evidencia:** `backend/app/agent.py` (`TOOL_DISPATCH`, `tool_proponer_actualizacion_critica`), `backend/app/main.py` (rutas API), `backend/app/analysis_queue.py` y `docs/decisiones.md` (SQL directo y decisiones históricas).

## 2. ¿Quién puede operar CIVIA y quién responde por cada decisión?

| Actor | Facultades autorizadas | Restricción de gobernanza |
|---|---|---|
| `CITIZEN` | Radicar, seguir y consultar reportes propios; revisar su clasificación cuando el flujo lo permite | No gestiona cuentas ni casos ajenos |
| `CASE_ADMIN` | Revisar, asignar, gestionar casos y decidir propuestas autorizadas | No administra usuarios ni la configuración técnica global |
| `WEB_ADMIN` | Administrar cuentas, observabilidad, colas y simulación de fallos, además de tareas de casos | Debe proteger accesos, evidencias y trazabilidad |
| Modelo Gemini/Groq | Producir sugerencias o respuestas validadas | No recibe credenciales administrativas ni permisos de ejecución autónoma |
| Equipo desarrollador | Documentar decisiones, corregir defectos y liberar versiones | Los cambios siguen `dev → PR/CI → main` |

Estas responsabilidades son **operativas**, no una determinación legal de quién asumiría responsabilidad por un daño. Ante un incidente, el operador humano que toma la decisión administrativa y el equipo que mantiene la plataforma deben investigar y documentar su actuación; no puede atribuirse toda la responsabilidad al proveedor del modelo.

**Evidencia:** `backend/app/identity.py` (enumeración de roles y dependencias `require_case_admin`/`require_web_admin`); `backend/app/main.py` (protección de operaciones); `docs/ROLES_Y_PERMISOS.md`.

## 3. ¿Qué datos usamos, a quién afectan y cómo reducimos el riesgo?

Activos: cuentas, sesiones, radicados, fotografías, voz, coordenadas, descripciones, eventos, notas internas, propuestas, auditoría y claves de API. Contenido no confiable: texto ciudadano, imágenes, audio, transcripciones y resultados del modelo. Las respuestas públicas y las llamadas a proveedores externos son posibles rutas de exposición.

Se aplican sesiones revocables y RBAC, alcance por titular, validación Pydantic, selección de herramientas, proyección SQL minimizada, transporte TLS en flujos indicados, sanitización y secretos fuera del bundle. Las herramientas no aceptan identidades o privilegios dictados por el modelo.

**Riesgos residuales reconocidos:** la imagen o el audio pueden contener información sensible aportada voluntariamente; los contenedores tienen salida general de red aunque el adaptador IA limita destinos; la instalación antigua conserva una contraseña propietaria que necesita rotación segura; no hay validación documentada de la PWA desde un teléfono físico. Estos límites constan en `docs/seguridad.md` y `docs/estado.md`.

## 4. ¿Dónde se exige la supervisión humana, exactamente?

Las operaciones críticas propuestas por el agente pasan por `tool_proponer_actualizacion_critica` (`backend/app/agent.py`), que prepara una solicitud en `pending_approvals` sin cambiar directamente el registro de negocio. La decisión se efectúa por `POST /api/admin/approvals/{approval_id}/decide` (`backend/app/main.py`), protegida mediante rol administrativo de caso y validaciones transaccionales. Una sugerencia no ejecuta una decisión, y una petición de chat no reemplaza la sesión del administrador. La aplicación comprueba estado, vigencia y versión para impedir decisiones obsoletas o repetidas.

**Demostración exigible:** crear una propuesta con cuenta ciudadana → confirmar que el reporte no cambió → intentar aprobar sin autorización (rechazo) → decidir con `CASE_ADMIN` → comprobar historial y versión. No utilizar los 80 reportes históricos ni información privada para la prueba.

## 5. ¿Qué hacemos cuando el modelo se equivoca, falla o produce un daño?

**Detectar y contener:** `WEB_ADMIN` revisa estado del worker, trazas saneadas, incidentes y circuit breakers; puede aislar temporalmente una integración problemática mediante controles del sistema. **Conservar:** la radicación queda registrada antes de la inferencia, con trabajo durable asociado; si los dos proveedores fallan, se agenda un reintento y eventualmente `DEAD_LETTER` sin borrar el reporte. **Revisar:** un administrador de casos contrasta evidencia, clasificación y decisiones; ninguna recomendación de IA se convierte automáticamente en gestión crítica. **Corregir y dejar rastro:** registrar incidente, causa, alcance, impacto, mitigación, versión afectada, pruebas y decisión de corregir o aceptar el riesgo. **Informar:** mostrar al ciudadano estados reales, sin fingir análisis final ni traslado a autoridades.

**Evidencia:** `backend/app/analysis_queue.py` (`QUEUED`, `PROCESSING`, `RETRY_SCHEDULED`, `DEAD_LETTER`, lease/fence), `backend/app/analysis_worker.py`, `docs/RESILIENCIA.md`, `docs/seguridad.md`, `docs/estado.md`.

## Matriz de decisiones y riesgos abiertos

| Riesgo/decisión | Tratamiento adoptado | Estado |
|---|---|---|
| Fallo Gemini en generación HTTP 403 | Groq independiente, reintentos acotados, cola y revisión humana | Groq observado en vivo; Gemini pendiente de habilitar |
| Prompt injection indirecta | Reducir contenido expuesto al agente y herramientas permitidas; autorización fuera del LLM | Prueba defensiva sintética documentada; no se garantiza invulnerabilidad |
| Egreso de contenedores | Destinos restringidos en adaptador de inferencia, sin red arbitraria controlada por el modelo | Aislamiento de red total pendiente para producción pública |
| Credencial propietaria histórica | Migración privada y coordinada, sin borrar volúmenes | Pendiente |
| Integración con autoridades | No afirmar despacho oficial sin convenio e infraestructura | Fuera del alcance académico |

## Verificación rápida para el jurado

- Mostrar el control de rol en `backend/app/identity.py` y el endpoint `admin_decide_approval` en `backend/app/main.py`.
- Mostrar una propuesta antes/después de una aprobación humana; revelar únicamente datos sintéticos.
- Simular indisponibilidad IA en un entorno de prueba: radicado existente, trabajo de cola y recuperación sin duplicados.
- Mostrar riesgos aceptados con razones, no promesas de seguridad absoluta.

**Referencias:** [Rúbrica oficial](https://ingenieria-aplicaciones-ia.netlify.app/momento3_rubrica) · [Seguridad](seguridad.md) · [Resiliencia](RESILIENCIA.md) · [Estado](estado.md) · [Roles](ROLES_Y_PERMISOS.md) · [Decisiones](decisiones.md).
