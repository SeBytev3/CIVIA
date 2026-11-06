# Auditoría técnica independiente de CIVIA — fases A, B, C y D

Fecha: 2026-11-01 (America/Bogota). Auditor: Codex. Equipo: Stefania Córdoba y Sebastian Espinosa, Universidad Cooperativa de Colombia.

## Dictamen

**No se recomienda publicar el estado auditado.** Hay una credencial administrativa predeterminada incorporada al cliente, escrituras operativas sin autorización, límites temporales inefectivos y aceptación de análisis vacíos como exitosos. Las vueltas están acotadas por solicitud; tokens y tiempo tienen brechas; la aprobación humana se implementa para una herramienta concreta, pero puede eludirse mediante una ruta pública.

Existe implementación real de React, FastAPI, SQL parametrizado, recodificación de imágenes, herramientas con descripciones, cadena de proveedores, circuit breaker y dependencias de autenticación administrativa. Esto no demuestra que las fases estén terminadas ni que el flujo completo funcione desde un checkout limpio.

## Alcance y límites

Se leyeron AGENTS.md, README.md, docs/arquitectura.md, docs/decisiones.md y docs/estado.md; frontend, backend, agentes, migración, pruebas, Dockerfiles, Compose, scripts de arranque y documentación de evaluación. Se inspeccionó el checkout local del repositorio indicado; no se comparó con el estado remoto.

HEAD al comenzar: `91bff47b3a8b`. Estado inicial: `eval/casos_dorados.json` sin seguimiento. Durante la lectura aparecieron modificaciones ajenas en `backend/app/agent.py` y `backend/app/repository.py`. No fueron realizadas por esta auditoría ni se revirtieron. Se tomó una copia temporal estable, sin `.env`, para ejecutar las comprobaciones. Las líneas de esos dos módulos corresponden a dicha copia, que incorpora cambios ajenos de respuesta SQL y conservación del estado tras análisis.

SHA256 auditados:

- `backend/app/agent.py`: `787B10BC6F36B1B7B8D73F3FB9837A2EE52339EB6910A257A2BFD0C27BFB9F2C`.
- `backend/app/repository.py`: `B26C007D3D484BAA6FED08C26C07A134CE871757B730538BBC5D1720509114FC`.

Copia y reproductores temporales: `C:\Users\Jhoesp\AppData\Local\Temp\civia-audit-7857f6273e14493ab7f55e4ad2e7e2a7`. No se garantiza su permanencia; los reproductores principales se incluyen al final.

No se modificó código de producción, no se cambió de rama, no se crearon commits ni se publicó. No se ejecutaron pruebas contra datos persistentes del equipo: sus fixtures borran registros no sintéticos. No se imprimieron ni copiaron secretos al informe o a los reproductores. Las claves locales se usaron en memoria únicamente para consultar catálogos.

**EJECUTADO** indica reproducción local; **AISLADO**, dobles de prueba sin transacciones reales; **ESTÁTICO**, conclusión de lectura; **PENDIENTE**, comprobación no realizada. Compose publica actualmente solo en loopback: las severidades consideran el impacto para quien pueda acceder al servicio, sin afirmar que exista un despliegue público comprometido.

## Pruebas ejecutadas

| Comprobación | Resultado independiente | Limitación |
|---|---|---|
| `docker compose ps` / `docker compose config --quiet` | No ejecutables: Docker no disponible; tampoco en ruta estándar de Docker Desktop | Compose, imágenes, healthchecks y PostgreSQL 17 no verificados |
| Backend con Python 3.14.10 del host, solo wheels | Instalación falló: Pillow 11.1.0 sin wheel compatible | No prueba fallo de Docker, que usa Python 3.13 |
| CPython 3.13.18 aislado + requirements exactos | Instalación aprobada: FastAPI 0.120.0, Uvicorn 0.38.0, psycopg/binary 3.2.6, multipart 0.0.20, Pillow 11.1.0, pytest 8.3.5 y httpx 0.28.1 | Windows, no imagen Linux; transitivas resueltas hoy |
| `pytest backend/tests -q --tb=no` en copia | **1 passed, 1 skipped, 18 errors**, 25,75 s | BD apuntada deliberadamente a loopback puerto 1, sin servidor; errores de preparación, no 18 aserciones funcionales fallidas |
| Dos funciones unitarias existentes invocadas directamente | Reparación JSON y redacción de secretos aprobaron | Fixture automático de BD omitido expresamente; no se suman al resultado pytest |
| `npm install --no-audit --no-fund --package-lock=false`; `npm run build` | TypeScript y Vite 6.4.5 aprobaron; 34 módulos, JS 421,68 kB | Node 26.12.1 del host, no Node 22 Docker; sin navegador |
| `npm audit --json`, lock generado solo en copia | 0 vulnerabilidades conocidas reportadas | Primer intento sin lock devolvió ENOLOCK; no certifica backend/imágenes |
| Catálogo Google, ambas claves locales | Cada clave listó 50 modelos e incluyó ambos IDs configurados | No se ejecutó inferencia real, visión, JSON ni tool calling |
| Catálogo Groq, clave local | HTTP 403 | No acredita disponibilidad, validez de clave, existencia del modelo ni capacidades |
| Escaneo de historial local | 6 commits, 71 blobs únicos; único candidato: literal ficticio en test_ai_and_agent.py | Patrones Google/Groq y claves privadas; no cubre objetos remotos/no alcanzables ni otros formatos |
| `.env` | No versionado; claves presentes; token administrativo igual al predeterminado | Valores no impresos ni copiados |
| Timeout de hilo | Límite 0,01 s; excepción a 0,152 s; efecto lateral completado | Herramienta sintética de 0,15 s |
| Timeout global | Presupuesto 0,01 s; duración 0,182 s; ejecutó herramienta | Modelo/herramienta simulados; llamada directa |
| Presupuesto tokens | Límite 50; uso 1700; luego MAX_TOKENS | Uso simulado, sin gasto real |
| JSON vacío | `{}` produjo OTRO / MEDIA / confianza 0,8 / resumen de éxito | Parser real |
| Audio falso | `b'ID3not-an-audio'` aceptado, duración 1 s | Temporal y sintético |
| Salida del agente | Texto técnico sintético pasó íntegro, sin herramientas | Modelo simulado, agente real |
| Administración | Sin token 401; token configurado predeterminado 200 | Consulta BD de observabilidad simulada |
| Estado sin autenticación | HTTP 200, RESOLVED y función de escritura invocada | Repositorio/serialización simulados; sin cambios en BD |
| Retry tras persistencia | Dos HTTP 500 y dos inserciones simuladas | Fallo inducido después del alta; no duplicados reales en PostgreSQL |
| PNG con EXIF sintético | Metadato de descripción no persistió tras recodificación | Un caso; no prueba exhaustiva de EXIF/GPS/ICC |

La prueba E2E existente se omitió porque `http://frontend:80` no estaba accesible. Comprueba recursos HTTP/proxy, no cámara, GPS, grabación, instalación PWA ni interacción en navegador. **No se reprodujo el resultado histórico de “20 passed”.**

### Fallback ejecutado con proveedores simulados

Se usó el router real, sustituyendo HTTP, persistencia de trazas y espera de backoff; circuitos reiniciados entre casos.

| Falla | Resultado | Intentos |
|---|---|---|
| 429 primario | Fallback independiente entrega contrato | 3: dos HTTP_429 y éxito |
| 503 primario | Fallback independiente entrega contrato | 3: dos HTTP_503 y éxito |
| TIMEOUT primario | Fallback independiente entrega contrato | 3: dos TIMEOUT y éxito |
| INVALID_JSON primario | Fallback independiente entrega contrato | 2: INVALID_JSON y éxito |
| GROQ_FAIL | Tercer nivel entrega contrato | 3: dos HTTP_503 y éxito |
| TOTAL | `None`, `all_failed=true` | 3 fallos; no fabrica contrato |

Esto acredita decisiones de enrutamiento, **no disponibilidad real, espera de red ni persistencia integrada del reporte pendiente**.

## Hallazgos CRÍTICOS

### C-01 — Credencial administrativa predeterminada distribuida al cliente

**Archivos/líneas:** `backend/app/config.py:41`, `docker-compose.yml:30`, `frontend/src/App.tsx:168`, `.env.example:20`, `backend/app/main.py:124-131,446-497`.

**Riesgo:** el bundle entrega el valor que el backend acepta si no se configura otro. Permite leer trazas, decidir propuestas, activar caída total de IA y restablecer datos sintéticos. La dependencia existe, pero el secreto es público. La instalación local conserva ese valor. Los bindings loopback limitan exposición remota directa; no se afirma explotación real.

**Evidencia EJECUTADA/AISLADA:** observabilidad sin cabecera 401; con el valor configurado predeterminado 200, sustituyendo la consulta por `{}`. No se leyeron trazas privadas. Las operaciones que comparten esa credencial se verificaron por lectura.

**Corrección:** quitar el valor del cliente y del fallback del servidor; exigir secreto aleatorio al arrancar y rotar el existente; usar sesiones/roles administrativos antes de publicar. Derivar actor de la identidad autenticada.

**Requisitos afectados:** prioridades AGENTS 3, 5 y 7; escritura crítica y observabilidad protegida.

## Hallazgos ALTOS

### A-01 — Modificación de cualquier reporte sin autorización ni propiedad

**Archivos/líneas:** `backend/app/main.py:364-413`; `backend/app/schemas.py:50-62`; `backend/app/repository.py:226-280`.

**Riesgo:** PATCH `/api/reports/{id}/status` acepta `human_approved=true` sin token ni sesión. El listado público entrega UUID. Cualquier cliente puede resolver/rechazar reportes y eludir aprobaciones. `/confirm` también permite alterar clasificación ajena, incluso tras gestión operativa. Un booleano del solicitante no acredita autorización humana.

**Evidencia EJECUTADA/AISLADA:** PATCH sin cabeceras, payload `{"status":"RESOLVED","human_approved":true}`, devolvió 200 e invocó escritura simulada. Sin cambio de BD real. Código sin Depends ni propiedad.

**Corrección:** roles para gestión operativa; credencial por reporte o sesión propietaria para confirmación; transiciones y control de versión en SQL. Probar que un tercero no puede modificar un UUID público.

**Requisitos:** prioridades 2, 3 y 5; seguimiento y aprobación humana efectiva.

### A-02 — Timeout de herramienta espera al hilo y permite efectos después del plazo

**Archivos/líneas:** `backend/app/agent.py:344-358,848-875`; `backend/tests/test_ai_and_agent.py`, función `test_four_agent_guardrails_enforced`.

**Riesgo:** future.result(timeout) está dentro de `with ThreadPoolExecutor`; la salida espera shutdown(wait=True). Una herramienta bloqueada conserva la petición y puede escribir tras vencer el plazo. El test existente solo comprueba la etiqueta TIMEOUT, no duración ni efectos.

**Evidencia EJECUTADA:** sleep de 0,15 s, timeout 0,01 s: excepción a 0,152 s, efecto lateral completado.

**Corrección:** deadline propagado a HTTP/SQL, statement_timeout/lock_timeout y transacciones que no escriban tras el plazo; proceso/trabajador aislado cuando se requiera cancelación fuerte. shutdown(wait=False) no detiene un hilo. Medir tiempo y efectos tardíos.

**Requisitos:** prioridades 3 y 6; timeout efectivo.

### A-03 — JSON sin evidencia se transforma en análisis exitoso con confianza inventada

**Archivos/líneas:** `backend/app/ai_router.py:151-226`; `backend/app/schemas.py:21-44`.

**Riesgo:** se fabrican categoría OTRO, severidad MEDIA, resumen y confianza 0,8 antes de Pydantic. Un objeto vacío o con campos erróneos impide fallback y aparenta análisis válido.

**Evidencia EJECUTADA:** `parse_and_validate_analysis_json('{}')` retorna OTRO/MEDIA/0,8 y “Evidencia ciudadana analizada.”. Ninguna salida del modelo sustenta esa confianza.

**Corrección:** validar campos originales obligatorios; reparar sintaxis sin inventar semántica; INVALID_SCHEMA y fallback para omisiones/enums desconocidos. Probar `{}`, tipos incorrectos y confianza ausente.

**Requisitos:** prioridades 2, 5 y 6; contrato estructurado y no simular éxito.

### A-04 — Respuestas del agente y transcripciones sin política de contenido ciudadano

**Archivos/líneas:** `backend/app/agent.py:809-845,862-889`; `backend/app/main.py:429-442`; `backend/app/ai_router.py:600-633`; `backend/app/repository.py:18-68`; `frontend/src/App.tsx:597,1329`.

**Riesgo:** turn_text pasa sin validación de evidencia, PII o detalles técnicos. Puede responder sin herramientas pese al prompt. Transcripciones/resúmenes no pasan por minimización de PII del formulario; audio_transcript es público. tools_invoked devuelve argumentos/resultados completos, no un DTO reducido.

**Evidencia EJECUTADA/AISLADA:** salida simulada “Gemini HTTP 429 traceback usuario@example.org” llegó intacta con cero herramientas. Prueba ausencia de barrera, no una fuga real de API. Lectura confirma publicación de transcripción.

**Corrección:** contrato público, redacción de PII y exclusión de detalles técnicos para todos los canales; requerir evidencia al afirmar hechos de BD; delimitar contenido no confiable en prompts. No depender solo del prompt o de una lista de palabras.

**Límite positivo:** React usa nodos de texto y Leaflet textContent; no se encontró HTML arbitrario ejecutable en esos recorridos. No se afirma XSS.

**Requisitos:** prioridades 3 y 5; no exponer proveedores/errores internos ni inventar datos.

### A-05 — Operaciones IA públicas sin cuotas y bloqueo del event loop durante el alta

**Archivos/líneas:** `backend/app/main.py:149-242,245-281,415-443`; `backend/app/security.py:260-279`; `frontend/nginx.conf:5-18`; `backend/app/db.py:17`.

**Riesgo ESTÁTICO:** rate limit solo en altas y después del parseo multipart. Analyze/agente consumen modelos, hilos, BD y trazas sin cuota. El alta async llama directamente psycopg, Pillow, HTTP síncrono y sleeps, bloqueando el event loop del único proceso. Se leen archivos completos antes del límite de 5 MB. Nginx limita a 12 MB, pero la API separada no comparte esa barrera global. Sin cuota de disco ni trabajo IA agregado.

**Reproducción propuesta, NO ejecutada en carga:** alta con proveedor lento mientras se mide health; repetir analyze/agente sobre un reporte sintético. No se agotaron recursos ni se midió capacidad.

**Corrección:** análisis fuera del event loop, colas/semáforos acotados, cuotas en todos los endpoints costosos, límite de cuerpo previo al parseo, lectura incremental y límites de disco/SQL.

**Requisitos:** prioridades 1, 3, 5 y 6; disponibilidad y recursos.

### A-06 — Alta no idempotente y fallos de observabilidad después del commit

**Archivos/líneas:** `backend/app/main.py:188-241`; `backend/app/repository.py:93-150`; `backend/app/ai_router.py:515-588`; `backend/app/observability.py:63-105`; `frontend/src/App.tsx:327-383`.

**Riesgo:** commit antes del análisis. Si registrar traza falla, el router puede intentar otra traza en el catch y propagar otra excepción. El ciudadano recibe fallo genérico con reporte ya guardado. Reenvío crea UUID nuevo; no hay idempotency key ni restricción por operación. La misma situación ocurre si se pierde la respuesta tras commit. El hash de foto no deduplica solicitudes.

**Evidencia EJECUTADA/AISLADA:** dos envíos idénticos con alta simulada exitosa y fallo posterior produjeron dos HTTP 500 y dos inserciones simuladas. Orden de commits y propagación de trazas: ESTÁTICO; no se dañó una BD real.

**Corrección:** idempotencia durable y UNIQUE por operación, devolver radicado tras persistencia, análisis diferido, observabilidad degradable sin invalidar el resultado ciudadano. Probar replay concurrente y desconexión tras commit.

**Requisitos:** prioridades 2, 5 y 6; persistencia, duplicación y degradación honesta.

### A-07 — Aprobaciones reutilizables y decisiones concurrentes inconsistentes

**Archivo/líneas:** `backend/app/agent.py:944-994`.

**Riesgo ESTÁTICO:** lectura sin FOR UPDATE, actualización sin `status='PENDING'`, y reaplicación del cambio cada vez que approve=true. No compara previous_status. Una aprobación vieja sobrescribe gestiones posteriores; aprobar y luego rechazar puede dejar propuesta REJECTED y reporte modificado. decided_by es libre.

**Reproducción propuesta, NO ejecutada con BD:** aprobar propuesta, gestionar reporte de nuevo y reaplicar esa aprobación; repetir decisiones opuestas simultáneas. SQL carece de condiciones para impedirlo.

**Corrección:** UPDATE condicional RETURNING/bloqueo, decisión de un solo uso, control de versión del reporte y actor autenticado en una transacción. Pruebas reales de concurrencia.

**Requisitos:** prioridad 3; integridad y aprobación humana.

## Hallazgos MEDIOS

### M-01 — Audio comprimido: firma superficial y duración siempre truncada al máximo

**Archivo/líneas:** `backend/app/security.py:183-255`.

**Riesgo:** MP3/OGG/WEBM requieren solo prefijo. La duración estimada usa min(60,...): nunca supera la validación. Un audio largo con bitrate bajo o contenido arbitrario pasa. WAV tiene cálculo distinto.

**Evidencia EJECUTADA:** `ID3not-an-audio` aceptado como MP3 de 1 s, sin transcripción real.

**Corrección:** parser real de contenedor/códec, duración medida y rechazo de corrupción; límites de muestras/canales y decodificación aislada acotada.

**Requisitos:** prioridades 2 y 7; multimodalidad y recursos.

### M-02 — Presupuestos elevados por el cliente y tokens controlados después del consumo

**Archivos/líneas:** `backend/app/schemas.py:100-105`; `backend/app/agent.py:660-662,680-707,731,807-810`; maxOutputTokens/max_tokens de llamadas agénticas.

**Riesgo:** cliente público eleva defaults de 5 a 10 vueltas, 6000 a 20000 tokens y 15 a 30 s; hay máximos HTTP, pero no mínimo con política del servidor. La salida de 700 tokens no se ajusta al saldo. El agente no suma consumo de clasificación ejecutada como herramienta ni uso de respuestas fallidas/ilegibles.

**Evidencia EJECUTADA/AISLADA:** presupuesto 50, uso 1700, luego MAX_TOKENS. El test existente también permite consumir 60 con límite 50.

**Corrección:** cliente solo puede reducir máximos; reservar entrada/salida, ajustar salida al saldo e incluir herramientas/reintentos/uso incierto. Distinguir límite duro de indicador posterior.

**Requisitos:** prioridad 3; límite de tokens y costo.

### M-03 — Sin deadline integral para router, herramientas, fallback y SQL

**Archivos/líneas:** `backend/app/ai_router.py:452-453,484-588`; `backend/app/agent.py:680-707,848-861,899-900`; `backend/app/db.py:17`.

**Riesgo:** clasificación admite hasta 2 intentos primarios y 3 por respaldo, hasta 8 llamadas de 6 s más esperas/trazas, sin deadline de 15 s. Timeout HTTP es por fases de I/O. Agente concede al menos 1 s aun sin saldo y no comprueba tiempo antes de cada herramienta; fallback SQL fuera del límite. SQL solo limita conexión, no sentencia.

**Evidencia EJECUTADA/AISLADA:** plazo 0,01 s, turno 0,03 s y herramienta 0,15 s terminaron a 0,182 s. No se midió una espera real de proveedores.

**Corrección:** deadline monotónico único propagado a cada operación; no iniciar trabajo sin saldo, limitar SQL y medir tiempo de pared con varias herramientas/fallback.

**Requisitos:** prioridades 3, 5 y 6.

### M-04 — Circuit breaker mutable sin único ensayo half-open

**Archivo/líneas:** `backend/app/ai_router.py:30-92,465-485,546-565`.

**Riesgo ESTÁTICO:** estado global compartido entre hilos sin sincronización. Tras cooldown múltiples solicitudes pueden entrar HALF_OPEN; éxito/fallo concurrentes dejan estado dependiente del orden. Clasificación y agente comparten circuito por proveedor/modelo, aunque una falla sea específica de capacidad. Se reintenta dentro del intento aun después de abrir el circuito.

**Reproducción propuesta:** barrera concurrente y circuito OPEN con cooldown vencido; falta exclusión de ensayo. Sin prueba de carga ejecutada.

**Corrección:** sincronización, único ensayo half-open, alcance por capacidad y semántica explícita de reintentos en curso; pruebas de carrera.

**Requisitos:** prioridad 5; resiliencia.

### M-05 — Métricas por eventos no equivalen a consultas completas ni evaluación formal

**Archivos/líneas:** `backend/app/observability.py:10-17,35-38,122-173`; `backend/app/ai_router.py:622-632`; `docs/decisiones.md`, Medición; `eval/README.md`.

**Riesgo ESTÁTICO:** P50/P90 sobre intentos, incluidos circuitos abiertos de 0 ms, no consultas completas. Latencia excluye parte de reintentos/herramientas/esperas. Tarifas sin fuente/fecha; Whisper usa tokens sintéticos, sin unidad de audio acreditada. Resumen carga todas las trazas en memoria. Sin evaluar.py ni evidencia de 15 consultas/precisión manual. JSON dorado no versionado no prueba verificación humana.

**Evidencia:** SQL/fórmulas inspeccionados; no se validaron tarifas actuales ni se inventaron métricas. decisiones reconoce medición pendiente.

**Corrección:** traza raíz por consulta, duración total y uso agregado; precios con fuente/fecha/unidad; agregación SQL, retención y evaluación formal revisada a mano.

**Requisitos:** prioridad 6; medición/trazas, suite dorada.

### M-06 — Identidad IP no definida de forma confiable detrás del proxy

**Archivos/líneas:** `frontend/nginx.conf:14-17`; `backend/app/main.py:162-163`; `backend/app/security.py:260-279`; `backend/Dockerfile:11`.

**Riesgo ESTÁTICO/CONDICIONAL:** Nginx añade X-Forwarded-For del cliente y backend usa request.client.host sin configurar explícitamente proxies confiables. Con confianza por defecto limitada a loopback puede agrupar a ciudadanos por IP del contenedor Nginx. Habilitar confianza universal para corregirlo introduciría falsificación por cabeceras. No se demostró bypass IP en el despliegue actual. Limitador en memoria no se comparte entre procesos ni elimina claves inactivas.

**Evidencia PENDIENTE:** comprobar IP por Nginx/acceso directo con cabecera falsificada en Compose.

**Corrección:** confiar solo en proxy real, sobrescribir cabeceras no confiables, evitar bypass directo y usar cuotas compartidas/acotadas. Probar dos clientes y XFF controlado.

**Requisitos:** prioridad 5; disponibilidad y recursos.

### M-07 — Suite destructiva sobre volumen normal y dependiente de APIs reales

**Archivos/líneas:** `backend/tests/test_ai_and_agent.py:28-43`; `backend/tests/test_reports_crud.py:17-30`; `backend/tests/test_e2e_frontend_proxy.py:16-19`; README, pruebas.

**Riesgo ESTÁTICO:** comando recomendado usa BD/volumen normal. Teardowns borran TODOS los reportes no sintéticos y aprobaciones, y modifican demo. Pueden quedar archivos/trazas; ejecutar en paralelo interfiere con datos. Inyectar falla primaria no hace determinista al respaldo real. E2E omite si no encuentra frontend. Fixture BD bloquea incluso unidad pura.

**Evidencia EJECUTADA:** 18 errores de preparación y skip sin infraestructura; DELETE sin filtro run_id confirmado por lectura. No se ejecutaron borrados reales.

**Corrección:** BD/volumen exclusivo, protección de entorno antes de borrar, fixtures aislados, transporte simulado en unidad y contrato, integración opt-in sin skip silencioso en CI. Añadir negativos de autorización, tiempo, duplicación y concurrencia.

**Requisitos:** prioridades 1, 6 y 7.

## Hallazgos BAJOS

### B-01 — Dependencias y variables incompletamente reproducibles

**Archivos/líneas:** `frontend/package.json`; `frontend/Dockerfile:3-5`; `backend/requirements.txt`; `docker-compose.yml:17-30`; `.env.example:19`; README.

**Riesgo ESTÁTICO:** sin lock npm versionado, Docker instala rangos; requirements no fija transitivas/hashes; imágenes con tags mutables. AUTO_SEED_SYNTHETIC figura en ejemplo pero Compose no la transmite: false en `.env` no deshabilita el default true del backend. Tampoco se documentan/transmiten todas las opciones de uploads/rate limit.

**Evidencia:** build actual aprobó con Vite 6.4.5; git ls-files sin lock; comparación settings/Compose. No se afirma incompatibilidad de React 19 en la resolución probada.

**Corrección:** lock y npm ci, política de bloqueo backend/imágenes, transmitir variables y probar otro equipo. No cambiar modelos sin preflight.

**Requisitos:** prioridades 1 y 7.

### B-02 — Health siempre HTTP 200 y errores de inicialización absorbidos

**Archivos/líneas:** `backend/app/main.py:64-78,133-140`; `backend/app/db.py:65-88`; `docker-compose.yml:38-45`.

**Riesgo ESTÁTICO:** migración/seed fallidos no impiden arranque; health retorna status ok y 200 aun con connected/schema_ready falsos. Healthcheck solo abre URL; frontend puede arrancar sin esquema.

**Evidencia EJECUTADA:** test_health simple aprobó sin BD; no exige readiness. Comportamiento de inicialización comprobado por lectura.

**Corrección:** readiness 503 sin BD/esquema, liveness separado y arranque fallido ante migración fallida.

**Requisitos:** prioridad 1.

### B-03 — Archivos huérfanos y códigos con solo 32 bits y año fijo

**Archivos/líneas:** `backend/app/main.py:188-214`; `backend/app/security.py:167-170,246-249`; `backend/app/repository.py:71-73,93-94`; migración, UNIQUE tracking_code.

**Riesgo ESTÁTICO:** foto escrita antes de validar audio/commit queda huérfana si fallan. No se verifica tamaño recodificado antes de insertar, aunque SQL impone 5 MB. Código usa ocho hexadecimales y año fijo 2026: colisiones UNIQUE sin regeneración, año incorrecto a futuro.

**Reproducción propuesta:** foto válida/audio inválido deja foto; UUID distintos con mismo prefijo generan código idéntico. No se hicieron inserciones ni agotamiento reales.

**Corrección:** staging/limpieza compensatoria, control de tamaño final, código más amplio con retry de colisión y año de creación.

**Requisitos:** prioridades 1, 2 y 7.

## Herramientas y frontera de escritura IA

Las cuatro herramientas tienen JSON Schema y descripciones, pero despacho recibe dict sin validación uniforme mediante modelos tipados: faltan rangos, enums y rechazo de argumentos extra. Groq sustituye argumentos JSON ilegibles por `{}`. Esquema enviado al proveedor no equivale a validación en servidor.

Proponer_actualizacion_critica solo inserta propuestas: separación real positiva. Sin embargo, clasificar_evidencia invoca update_report_ai_analysis (`agent.py:264-272`), por lo que una llamada elegida por el agente sí causa escrituras de campos IA en reports. En la copia auditada se conservan categorías finales humanas y estados gestionados; el cambio ajeno en repository reduce una regresión de la lectura inicial. La frase “IA jamás modifica reports” requiere delimitar campos/permisos/mediación. Persistir sugerencias automáticamente debe declararse como excepción, sin confundirla con aprobar estado final.

Recomendación: DTO por herramienta con extra=forbid, rangos y resultados validados; autorización de efectos y deduplicación de propuestas. Un turno puede pedir varias herramientas y repetir propuestas sin identificador durable de intención.

## Correspondencia académica/documental

| Requisito | Evidencia | Dictamen |
|---|---|---|
| Checkout limpio/un comando | Compose, Dockerfiles, scripts, README | Ejecución Docker/segundo equipo pendiente; B-01/B-02 |
| Alta/foto/GPS/almacenamiento/análisis/consulta | Recorridos reales; build aprobado | Integración BD/IA/navegador pendiente; A-01/A-03/A-06 |
| Agente genuino | Tool calling nativo y despacho implementados | Uso de evidencia no forzado en respuesta final |
| Cuatro límites efectivos | Vueltas, tokens, timeout, propuestas | No acreditados integralmente; A-01/A-02/A-07/M-02/M-03 |
| SQL directo/NO RAG | Parámetros SQL y justificación razonable | Verificado por lectura; sin EXPLAIN ni medición espacial |
| Gemini → Groq → Gemini | Cadena y rutas aisladas ejecutadas | Orden verificado; Groq 403 y capacidades reales pendientes |
| Fallos técnicos protegidos | Manejadores genéricos/token | Barreras insuficientes: C-01/A-04 |
| 429/503/timeout/JSON/total | Router aislado ejecutado | Enrutamiento aprobado; integración pendiente |
| 5 preguntas manuales/una irresoluble/15 consultas | Instrucciones eval y JSON no versionado | Sin evidencia de revisión humana ni métricas formales |
| Sintéticos/privacidad | Semilla marcada, imágenes generadas, basename/UUID, recodificación | Controles reales; audio/transcripciones requieren corrección |
| P50/P90/costo/trazas | Cálculo por evento | No equivale a evaluación por consulta; M-05 |

No se encontró SQL con valores de usuario interpolados en los recorridos revisados; los fragmentos dinámicos los construye código y los valores usan parámetros. No se hizo fuzzing exhaustivo ni pentest de red.

No se encontraron claves reales versionadas mediante los patrones inspeccionados; no certifica que nunca se expusieran fuera del historial local. No se atribuye compromiso de claves de proveedores. El token administrativo público sí está activo en la configuración local.

No se confirmó arranque Linux ni instalación PWA en dispositivos específicos. MediaRecorder no negocia formato y etiqueta el blob como WEBM; requiere prueba de compatibilidad en navegadores de demo.

## Orden de corrección y aceptación

1. Rotar/retirar token del cliente y exigir autorización/propiedad en escrituras.
2. Rechazar contratos incompletos y proteger salida/transcripciones.
3. Corregir deadlines, cuotas, bloqueo del event loop y aislamiento de observabilidad.
4. Añadir idempotencia y aprobaciones de un solo uso con pruebas PostgreSQL concurrentes.
5. Validar audio y proxy/IP; fijar dependencias, readiness y variables.
6. Ejecutar Compose desde checkout limpio en Windows 11/otro equipo; validar visión/JSON/tools con imágenes sintéticas por modelo accesible; repetir suite segura y evaluación formal de 15 consultas.

Este informe registra resultados independientes; no valida afirmaciones históricas de docs/estado.md ni marca las fases como terminadas. No se modificó dicho archivo para preservar el alcance de revisión y los cambios concurrentes.

## Apéndice — reproductores ejecutados

Guardar cada bloque como script temporal. Requieren Python 3.13 con backend/requirements.txt y PYTHONPATH apuntando al directorio backend auditado. No requieren PostgreSQL ni claves: sustituyen las llamadas externas y las escrituras por dobles. No invocar el lifespan contra una BD de trabajo. El audio/foto de prueba usa directorios temporales y datos sintéticos.

El primer script mide tiempos, aceptación de JSON/audio, salida pública, tokens, autenticación, retry posterior a persistencia y las seis rutas de fallback. El PATCH inicial se detiene deliberadamente en serialización: acredita que llegó a la escritura. El segundo script aporta la reproducción equivalente con respuesta pública válida y HTTP 200. Para el segundo, pasar como primer argumento la raíz del checkout/copia que contiene backend/tests.

```python
import json,time,tempfile,pathlib,uuid,io
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
from app import agent as a, ai_router as r, main as m
from app.security import validate_and_store_audio
from app.config import settings

def emit(name,**data): print(json.dumps({'probe':name,**data},ensure_ascii=False))
state=[]
def slow(args):
    time.sleep(.15); state.append('effect'); return {}
with patch.dict(a.TOOL_DISPATCH,{'audit_slow':slow}):
    t=time.perf_counter()
    try: a.execute_tool_with_timeout('audit_slow',{},.01)
    except TimeoutError: emit('thread_timeout',requested_seconds=.01,elapsed_seconds=round(time.perf_counter()-t,3),side_effect_completed=bool(state))
emit('empty_json',contract=r.parse_and_validate_analysis_json('{}').model_dump())
with tempfile.TemporaryDirectory() as d:
    x=validate_and_store_audio(b'ID3not-an-audio',upload_dir=pathlib.Path(d))
    emit('fake_audio',accepted=True,duration=x['audio_duration_seconds'])
chain=[{'provider':'google','model':'audit','api_key':'fake','tier':'primary'}]
with patch.object(a,'get_provider_chain',return_value=chain),patch.object(a,'record_ai_trace'),patch.object(a,'_call_agent_turn_gemini',return_value=('Gemini HTTP 429 traceback usuario@example.org',[],100,100)):
    r.reset_all_circuits()
    out=a.run_civia_agent('consulta sin evidencia')
    emit('unfiltered_answer',answer=out['answer'],tools=len(out['tools_invoked']))
with patch.object(a,'get_provider_chain',return_value=chain),patch.object(a,'record_ai_trace'),patch.object(a,'_call_agent_turn_gemini',return_value=('respuesta',[],1000,700)),patch.object(a,'_deterministic_sql_fallback_answer',return_value='fallback'):
    r.reset_all_circuits(); out=a.run_civia_agent('consulta',max_tokens_budget=50)
    emit('token_overshoot',budget=50,used=out['total_tokens_used'],guardrail=out['guardrail_triggered'])
def turn(**kw):
    time.sleep(.03)
    return None,[{'name':'audit_slow','args':{}}],1,1
with patch.object(a,'get_provider_chain',return_value=chain),patch.object(a,'record_ai_trace'),patch.object(a,'_call_agent_turn_gemini',side_effect=turn),patch.dict(a.TOOL_DISPATCH,{'audit_slow':slow}),patch.object(a,'_deterministic_sql_fallback_answer',return_value='fallback'):
    r.reset_all_circuits(); t=time.perf_counter(); out=a.run_civia_agent('consulta',total_timeout_seconds=.01)
    emit('global_timeout',budget=.01,elapsed=round(time.perf_counter()-t,3),guardrail=out['guardrail_triggered'])
client=TestClient(m.app,raise_server_exceptions=False)
with patch.object(m,'get_observability_summary',return_value={}):
    emit('admin_auth',without_token=client.get('/api/admin/observability').status_code,documented_default=client.get('/api/admin/observability',headers={'X-Admin-Token':settings.ADMIN_TOKEN}).status_code)
with patch.object(m,'get_report_raw',return_value={'id':'fake'}),patch.object(m,'update_report_status',return_value={'id':'fake'}) as update,patch.object(m,'row_to_public_dict',side_effect=RuntimeError('audit serialization stop')):
    client.patch('/api/reports/'+str(uuid.uuid4())+'/status',json={'status':'RESOLVED','human_approved':True})
    emit('unauthenticated_status',write_function_called=update.called)
# Both report inserts are simulated: no database or private uploads are used.
buf=io.BytesIO(); Image.new('RGB',(32,32)).save(buf,format='PNG')
with tempfile.TemporaryDirectory() as d,patch.object(settings,'UPLOAD_DIR',pathlib.Path(d)),patch.object(m,'create_report',side_effect=lambda **kw:{'id':uuid.uuid4()}) as create,patch.object(m,'classify_evidence_with_router',side_effect=RuntimeError('audit trace storage failure')):
    m.rate_limiter.reset(); statuses=[]
    for _ in range(2): statuses.append(client.post('/api/reports',data={'description':'Evidencia sintetica de prueba','latitude':'3.4','longitude':'-76.5'},files={'photo':('audit.png',buf.getvalue(),'image/png')}).status_code)
    emit('retry_after_persist',http_statuses=statuses,inserts_simulated=create.call_count)
valid=json.dumps({'category':'HUECO','severity':'ALTA','confidence':.9,'summary':'Evidencia sintetica de hueco','keywords':[]})
for mode in ['429','503','TIMEOUT','INVALID_JSON','GROQ_FAIL','TOTAL']:
    r.reset_all_circuits();r.set_runtime_fault_override(mode);calls=[];traces=[]
    def provider(**kw): calls.append(kw['model']); return valid,20,10
    with patch.object(r,'_call_gemini_multimodal',side_effect=provider),patch.object(r,'_call_groq_multimodal',side_effect=provider),patch.object(r,'record_ai_trace',side_effect=lambda **kw:traces.append(kw)),patch.object(r.time,'sleep'):
        contract,meta=r.classify_evidence_with_router(description='sintetico',latitude=3.4,longitude=-76.5,image_bytes=None,image_mime=None)
        emit('router_'+mode,success=contract is not None,tier=meta.get('tier'),attempts=meta['attempts'],error_codes=[x.get('error_code') for x in traces if not x['success']])
r.set_runtime_fault_override('NONE');r.reset_all_circuits()

```

```python
from unittest.mock import patch
from fastapi.testclient import TestClient
from datetime import datetime,timezone
import uuid,json
from app import main as m
from app.config import settings
rid=uuid.uuid4(); now=datetime.now(timezone.utc)
public=dict(id=rid,tracking_code='CIV-2026-AUDIT',title='Prueba sintetica',description='Evidencia sintetica',latitude=3.4,longitude=-76.5,in_service_area=True,photo_url='/photo',photo_mime='image/png',photo_width=32,photo_height=32,human_confirmed=False,status='RESOLVED',status_message='Reporte atendido y resuelto.',created_at=now,updated_at=now)
with patch.object(m,'get_report_raw',return_value={'id':rid}),patch.object(m,'update_report_status',return_value={'id':rid}) as update,patch.object(m,'row_to_public_dict',return_value=public):
    response=TestClient(m.app).patch(f'/api/reports/{rid}/status',json={'status':'RESOLVED','human_approved':True})
    print(json.dumps({'probe':'unauthenticated_status_valid_response','http_status':response.status_code,'write_called':update.called,'status':response.json()['status']}))
# Execute existing pure tests without their module's database autouse fixture.
import importlib.util,pathlib,sys
spec=importlib.util.spec_from_file_location('audit_existing_tests',pathlib.Path(sys.argv[1])/'backend/tests/test_ai_and_agent.py'); tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
for name in ['test_bounded_json_repair_and_schema_validation','test_secret_sanitization_never_leaks_keys']:
    getattr(tests,name)();print(json.dumps({'existing_unit_function':name,'passed':True,'database_fixture_bypassed':True}))

```

La imagen con EXIF se verificó así, con Pillow 11.1.0:

```python
import io,tempfile,pathlib,json
from PIL import Image
from app.security import validate_and_store_photo
im=Image.new('RGB',(32,32)); exif=Image.Exif(); exif[270]='SYNTHETIC_PRIVATE_METADATA'; b=io.BytesIO(); im.save(b,format='PNG',exif=exif)
with tempfile.TemporaryDirectory() as d:
    meta=validate_and_store_photo(b.getvalue(),upload_dir=pathlib.Path(d))
    with Image.open(pathlib.Path(d)/meta['photo_path']) as cleaned:
        print(json.dumps({'probe':'png_exif','metadata_retained':cleaned.getexif().get(270)=='SYNTHETIC_PRIVATE_METADATA'}))

```

### Cambios concurrentes observados al cerrar

El árbol de trabajo siguió cambiando por actividad ajena después de congelar la copia: aparecieron modificaciones en ai_router.py, main.py, Compose y App.tsx, así como evaluar.py, resultados y documentos de sustentación. **Este informe no audita esas revisiones posteriores ni sus resultados.** La ausencia del evaluador mencionada en M-05 y en la tabla académica corresponde a la copia congelada, no afirma que continúe ausente en el árbol al entregar. Se requiere contrastar las correcciones posteriores con los hashes/recorridos aquí documentados y repetir las pruebas pertinentes; no se consideran resueltos por el solo hecho de existir cambios.


---

## Remediación aplicada en Fase F1 (Post-auditoría)

Tras la revisión del informe anterior (`HEAD 91bff47b3a8b`), se aplicaron y verificaron con pruebas en contenedor (`20 passed` en `pytest -v` y suite `eval/evaluar.py`) las siguientes correcciones:

- **`C-01` (Token administrativo en frontend)**: Se eliminó el valor prellenado `civia-admin-demo-2026` del estado de [`frontend/src/App.tsx`](frontend/src/App.tsx) (`useState("")`) y se implementó comparación en tiempo constante `hmac.compare_digest` en `verify_admin_token` ([`backend/app/main.py`](backend/app/main.py)).
- **`A-02` (Timeout de herramienta esperando `shutdown(wait=True)`)**: En [`backend/app/agent.py`](backend/app/agent.py) (`execute_tool_with_timeout`) se reemplazó el bloque `with ThreadPoolExecutor` por `executor.shutdown(wait=False, cancel_futures=True)` en `finally`, garantizando retorno inmediato al vencer `timeout_sec`.
- **`A-03` (JSON vacío `{}` aceptado como análisis exitoso)**: En [`backend/app/ai_router.py`](backend/app/ai_router.py) (`parse_and_validate_analysis_json`) se exige la presencia de `category`/`categoria` y `summary`/`resumen` no vacíos antes de validar el contrato; un objeto `{}` lanza `AIProviderError("INVALID_SCHEMA")` y está cubierto por `test_bounded_json_repair_and_schema_validation`.
- **`A-04` (Política de contenido ciudadano en salida del agente)**: Se añadió `sanitize_citizen_agent_output` en [`backend/app/agent.py`](backend/app/agent.py) para redactar secretos, PII, nombres de proveedores internos y códigos HTTP antes de entregar la respuesta al ciudadano.
- **`A-07` (Aprobaciones reutilizables)**: En [`backend/app/agent.py`](backend/app/agent.py) (`decide_pending_approval`) se añadió bloqueo `SELECT ... FOR UPDATE` y condición `WHERE id = %s AND status = 'PENDING'` para garantizar transición atómica de un solo uso.
- **`M-01` (Validación de audio comprimido y duración)**: En [`backend/app/security.py`](backend/app/security.py) (`_detect_audio_magic` y `validate_and_store_audio`) se exige longitud mínima de cabecera/trama (`>= 64` bytes y versión ID3v2 válida) y se eliminó el truncamiento `min(60.0, ...)` previo a la verificación del límite de 60 segundos.
- **`M-05` (Suite formal `eval/evaluar.py` y casos dorados)**: Se implementaron [`eval/casos_dorados.json`](eval/casos_dorados.json) (6 casos verificados contra SQL) y [`eval/evaluar.py`](eval/evaluar.py) (15 consultas representativas con métricas reales `P50`, `P90`, tokens y costos en [`eval/resultados/reporte_evaluacion.json`](eval/resultados/reporte_evaluacion.json)).
- **`B-01` y `B-03` (`AUTO_SEED_SYNTHETIC` en Compose y limpieza de fotos huérfanas)**: Se propagó `AUTO_SEED_SYNTHETIC` en [`docker-compose.yml`](docker-compose.yml) y se añadió eliminación compensatoria de la fotografía si falla la validación del archivo de audio opcional en [`backend/app/main.py`](backend/app/main.py).
