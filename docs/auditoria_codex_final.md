# CIVIA — segunda auditoría independiente y seguridad de entrega

Fecha: 2026-11-01, America/Bogota. Auditor: Codex. Equipo: Stefania Córdoba y Sebastian Espinosa, Universidad Cooperativa de Colombia.

## Dictamen: NO LISTO

El HEAD local incorpora correcciones reales, pero conserva autorización eludible, una credencial administrativa pública válida por defecto, escrituras posteriores al timeout y altas duplicadas. Las aprobaciones de un solo uso funcionan en concurrencia real; una propuesta obsoleta todavía sobrescribe decisiones posteriores. Tanto pytest como el evaluador pueden borrar datos ajenos a la ejecución si se siguen las instrucciones actuales sobre la BD habitual.

Además, **los commits finales no están publicados en las referencias anunciadas por origin**. El clon nuevo obtenido de GitHub continúa en la versión anterior. No es aceptable presentar una prueba de una copia local como prueba de entrega del HEAD publicado.

No se modificó código de producción, no se cambió la rama original, no se hizo merge, commit ni push. Solo se añade este informe. No se usaron imágenes, audios ni registros privados ni se imprimieron secretos.

## 1. Identificación del estado y aislamiento

### Control de versiones ejecutado

| Comprobación | Resultado |
|---|---|
| `git status --short` inicial | Árbol limpio |
| HEAD local | `a14e895fa3ba0b1504e5b7d9d9bbf9d07472647c` |
| Últimos commits | a14e895, 60cf068, 91bff47, 74da146, 0a4221a, 2fd73f0, d7819e1, a32fbfb |
| `git remote -v` | origin, fetch/push: https://github.com/SeBytev3/CIVIA.git |
| `git ls-remote origin` | HEAD y refs/heads/main: `91bff47b3a8bb56e089f9760e09c223a64f208af`; sin otras referencias anunciadas |
| origin/main local | También 91bff47; no estaba desactualizado respecto de la consulta remota |
| `git rev-list --left-right --count origin/main...HEAD` | `0 2`: HEAD local dos commits adelantado, ninguno atrasado |
| `git merge-base --is-ancestor 60cf068 origin/main` | Exit 1 |
| Mismo comando para a14e895 | Exit 1 |
| Clon independiente `--depth 1 --single-branch --branch main` | HEAD 91bff47; no contiene eval/evaluar.py |

Conclusión: **60cf068 y a14e895 no están publicados en main ni en otra referencia que origin anuncie al momento de comprobarlo**. No se investigó la existencia de objetos huérfanos por hash: eso no haría reproducible un clon normal. La diferencia local comprende 20 archivos, 2563 inserciones y 121 eliminaciones. No se actualizaron refs del repositorio original mediante fetch.

### Copia y PostgreSQL independientes

Se congeló exactamente HEAD con `git archive HEAD` y se extrajo en:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-final-0806e1c24ba0437d8ef5212760d7c218\src`.

Se instalaron las dependencias directas exactas de backend/requirements.txt en un entorno CPython 3.13.18 separado. Se obtuvo un servidor **PostgreSQL 17.6 real**, mediante el paquete portátil `@embedded-postgres/windows-x64@17.6.0-beta.15`, y se inicializó un clúster nuevo en el mismo directorio temporal: pgdata, escucha únicamente en 127.0.0.1:55473. Bases exclusivas `civia_audit_final` y `civia_audit_suite`; uploads exclusivos final_uploads/suite_uploads. No se conectó a la BD o volumen habitual de CIVIA. No se usó un emulador SQL. Este montaje no sustituye la prueba Linux/Docker.

Todas las variables de claves de proveedores se dejaron vacías en los procesos de pruebas. Las pruebas de transporte usan respuestas sintéticas y no ejecutan inferencia de pago. El archivo .env del proyecto no fue copiado ni utilizado. La falta de ADMIN_TOKEN se comprobó expresamente en una prueba de arranque completo; el valor predeterminado no se reproduce aquí.

Docker no está disponible en el entorno de auditoría. Por tanto, **no se verificó docker compose up, los healthchecks de los contenedores, Nginx real ni el despliegue completo de ninguno de los commits**.

Los scripts probes.py, more_probes.py, last_probes.py y admin_after_probe.py y sus resultados están en el directorio temporal anterior. Las primeras ejecuciones auxiliares tuvieron dos fallos de preparación corregidos sin tocar fuentes: el paquete portátil no incluye createdb.exe (se crearon las BD con psycopg) y una lectura del reproductor necesitó UTF-8 en Windows. Los resultados citados corresponden a ejecuciones posteriores completas.

Huellas SHA256:

- head.zip: `4A2434F9149BD85BAEE992A8947C06018AC6AF43AF9E5403B0D4E412BFE0ED67`.
- observations.json: `448802D6B7DCC744F735B703C0F1718B5AB19861EF75B7963A05B0785CFD05D0`.
- more_observations.json: `A38A0A2681FA29B489F41298BAF071FC8BBADA894EEFD88CD064DE6DABF69CA3`.

## 2. Matriz de los 18 hallazgos anteriores

Se leyó íntegramente docs/auditoria_codex.md y se conservaron sus identificadores. La clasificación se aplica al hallazgo completo: una prueba negativa aprobada sobre una parte no cierra las restantes. Resultado: **10 CORREGIDOS PARCIALMENTE, 8 NO CORREGIDOS, 0 cerrados íntegramente**. Las partes que no pudieron ejecutarse se señalan explícitamente; no se confunden con aprobación.

| ID | Estado actual | Evidencia ejecutada y límite pendiente | Archivos/líneas en HEAD |
|---|---|---|---|
| C-01 | CORREGIDO PARCIALMENTE | El cliente ya no precarga token. Sin ADMIN_TOKEN configurado, arranque completo y operación admin devuelven 200 con el valor público; un token de un carácter también se acepta. Sin cabecera/valor vacío: 401. No exige robustez ni falla al arrancar. | config.py:41; main.py:65-79,125-134; Compose:31; App.tsx:168 |
| A-01 | NO CORREGIDO | PATCH status sin credencial: false→400, true→200 y commit real. Confirmación de tercero→200. Después de aprobar por endpoint administrativo, otra confirmación anónima modifica categoría/severidad/nota. El UUID sigue siendo el único selector. | main.py:378-427; repository.py:226-279 |
| A-02 | CORREGIDO PARCIALMENTE | Devuelve pronto: 0,0225 s para límite 0,02. Pero un hilo iniciado cambia RESOLVED→REJECTED en PostgreSQL tras el retorno. cancel_futures no cancela trabajo iniciado. | agent.py:365-381 |
| A-03 | CORREGIDO PARCIALMENTE | `{}` ahora rechaza INVALID_SCHEMA. Con categoría y resumen, acepta falta de severidad/confianza y fabrica MEDIA/0,8; categoría NUCLEAR y confianza ilegible se convierten en OTRO/0,8. Confianza -5 se acepta como 0. | ai_router.py:183-265 |
| A-04 | CORREGIDO PARCIALMENTE | Payload antiguo Gemini/HTTP 429/traceback/correo se redacta en respuesta final de modelo. Google API HTTP 401 ValueError permanece. Transcripción y resumen técnico/PII sintético pasan íntegros por GET público. Sigue respondiendo sin herramienta; salidas SQL no usan el mismo filtro. | agent.py:38-51,848-870,878-910,967-983; repository.py:50-61; ai_router.py:651-685 |
| A-05 | CORREGIDO PARCIALMENTE | Nuevo límite agente: llamadas 1–30→200, 31→429 y solo 30 invocaciones; analyze también tiene control por lectura. Persiste alta async con trabajo síncrono: temporizador de 0,02 s despertó a 0,3455 s con clasificador sintético de 0,3 s. Sin cuotas globales/disco y lectura completa de archivos. | main.py:152-247,254-256,430-432; security.py:260-279 |
| A-06 | NO CORREGIDO | Dos altas idénticas con misma Idempotency-Key→201/201, UUID diferentes. Error real del flujo de trazas después del commit→500/500 y dos filas nuevas persistidas. | main.py:210-247; repository.py:93-150; ai_router.py:560-638; observability.py:63-105 |
| A-07 | CORREGIDO PARCIALMENTE | FOR UPDATE y estado PENDING: replay no reaplica; carrera approve/reject devuelve una sola decisión; approve/approve escribe una vez, medido con trigger. Propuesta creada antes de RESOLVED todavía lo reemplaza por IN_REVIEW. | agent.py:1011-1066 |
| M-01 | CORREGIDO PARCIALMENTE | Antiguo ID3 corto rechaza. ID3 versión 4 con ceros de relleno (100 bytes, sin audio) se acepta con 1 s. Quitó clamp a 60 pero duración sigue derivada del tamaño, no del contenedor/códec. | security.py:183-256 |
| M-02 | NO CORREGIDO | Límite 50 devuelve consumo simulado 1700 antes de MAX_TOKENS; cliente eleva iteraciones a 10 pese al default 5. No reserva saldo ni suma IA anidada. | schemas.py:100-105; agent.py:720-722,746-767,793-796,874-876 |
| M-03 | NO CORREGIDO | Deadline 0,02 s, modelo lento 0,05 s y herramienta 0,10 s: 0,1798 s y herramienta iniciada. Router sigue sin deadline total; SQL sin statement_timeout. | agent.py:740-767,915-950,967; ai_router.py:498-638; db.py:17 |
| M-04 | NO CORREGIDO | Circuito con cooldown vencido acepta tres allow_request seguidos en HALF_OPEN. Sin exclusión/sincronización. El helper nuevo no crea un único ensayo y no revalida capacidades; véase N-02. | ai_router.py:30-123 |
| M-05 | CORREGIDO PARCIALMENTE | Existe evaluación de 15 consultas y percentiles de tiempo de pared; sumas guardadas se reproducen. Panel sigue midiendo eventos. Atribución de modelos/fallback/consumo y facturación no es confiable; revisión humana pendiente. | observability.py:11-17,122-173; evaluar.py:250-309,340-374,439-508 |
| M-06 | NO CORREGIDO | Middleware Uvicorn real con peer de proxy no confiable: dos XFF distintos producen la misma IP 172.18.0.8. Configuración Nginx/Uvicorn no cambió. No se probó Nginx en contenedor ni se afirma bypass XFF en ese despliegue. | nginx.conf:14-17; backend/Dockerfile:11; main.py:165-166; security.py:260-279 |
| M-07 | NO CORREGIDO | UNA prueba unitaria existente aprueba y su teardown borra un reporte centinela no sintético, una aprobación ajena y cambia demo RESOLVED→CONFIRMED. README sigue usando volumen normal. | tests/test_ai_and_agent.py:24-37; test_reports_crud.py:16-25; README, pruebas |
| B-01 | CORREGIDO PARCIALMENTE | AUTO_SEED_SYNTHETIC ahora se transmite en Compose. Sin lock npm, transitivas/hashes backend ni imágenes inmutables. Build local aprueba; arranque Docker no verificable. | Compose:30; frontend/Dockerfile:3-5; package.json; requirements.txt |
| B-02 | NO CORREGIDO | Con salud BD false/false, GET health devuelve HTTP 200 y status ok. Arranque sigue absorbiendo excepciones. | main.py:65-79,136-144; db.py:65-88; Compose healthcheck |
| B-03 | CORREGIDO PARCIALMENTE | Foto+audio inválido→415 y cero fotos nuevas: corrección verificada. Fallo al insertar→500 y una foto huérfana. Dos UUID distintos con mismo prefijo siguen dando mismo código; año 2026 fijo. | main.py:198-206,210; security.py:170,250; repository.py:71-73 |

Los nombres de módulos sin prefijo en la tabla pertenecen a backend/app, salvo rutas indicadas. Las pruebas negativas que aún permiten la acción insegura se consideran fallidas como controles de seguridad, aunque el reproductor haya terminado correctamente.

## 3. Comprobaciones prioritarias con PostgreSQL real

### Autorización y confirmación después de decisión administrativa

Se creó evidencia PNG sintética por POST normal y se usó el UUID devuelto. Sin cabeceras:

1. PATCH status con human_approved=false devuelve 400.
2. Mismo PATCH con true devuelve 200; se consulta PostgreSQL y consta RESOLVED.
3. PATCH confirm anónimo devuelve 200 y escribe QUEMA/CRITICA.
4. Prueba adicional: crear propuesta, aprobar mediante `/api/admin/approvals/{id}/decide` con token configurado y después confirmar desde cliente sin token. Ambas peticiones devuelven 200; reporte queda RESOLVED, pero categoría final QUEMA y nota de tercero.

Conservar la palabra RESOLVED no protege la decisión administrativa completa: se alteran clasificación, severidad y nota. No hay propietario, capacidad secreta de edición ni identidad validada. Un UUID público identifica el recurso y no demuestra autorización. Añadir un booleano de confirmación tampoco la demuestra.

### Token

La prueba adicional usó el lifespan completo y confirmó `ADMIN_TOKEN` ausente del entorno. La operación protegida funcionó usando la configuración predeterminada. La comparación hmac evita una comparación ordinaria de cadenas, pero no sustituye exigir un secreto robusto. Se verificó también aceptación de token de un carácter y rechazo de token vacío/sin cabecera. No se muestran valores de credenciales.

### Timeout y escritura tardía

La herramienta sintética esperó 0,20 s y ejecutó update_report_status contra la base aislada. execute_tool_with_timeout lanzó TimeoutError a los 0,0225 s con plazo 0,02. En ese momento el reporte estaba RESOLVED; al terminar el trabajador quedó REJECTED. **Se acreditó una escritura posterior al vencimiento, no solo la supervivencia de un hilo**.

Solución mínima efectiva: deadline monotónico propagado a cada HTTP y operación SQL; statement_timeout/lock_timeout según saldo; abrir transacción y bloquear/validar versión y vigencia antes de escribir; no confirmar si expiró la operación. Las herramientas con efectos no deben hacer commit autónomo después de que el orquestador descarte su resultado. Para trabajo no cooperativo, proceso o worker aislado con protocolo de cancelación y persistencia controlada. Cancelar una Future en ejecución no detiene el código; cambiar únicamente wait no cumple el requisito.

### Persistencia e idempotencia

Los duplicados se reprodujeron con repositorio real, no mocks de inserción. Dos POST idénticos enviaron la misma cabecera Idempotency-Key: ambas respuestas 201 y dos UUID diferentes. En otra prueba solo se sustituyó record_ai_trace para lanzar un error sintético; el resto del alta y los commits fueron reales. Se obtuvieron 500/500 y dos filas nuevas, porque guardar trazas puede fallar después de persistir el reporte.

Hace falta una clave durable UNIQUE por operación, resultado recuperable ante replay concurrente y separación del alta respecto de análisis/observabilidad. Deduplicar solo por foto no resuelve reintentos de la misma intención ni distingue incidentes legítimos con imágenes iguales.

### Aprobaciones, replay y concurrencia

Se usaron conexiones independientes y ThreadPoolExecutor con barrera para competir por una misma propuesta. Un trigger temporal de auditoría contó UPDATE reales sobre reports:

- Aprobar, cambiar luego el reporte y redecidir la misma propuesta no reescribió el reporte: permaneció RESOLVED y la decisión original APPROVED.
- Carrera approve/reject: ambos retornaron REJECTED en esa ejecución; cero escrituras del reporte y una sola decisión final.
- Carrera approve/approve: ambos retornaron APPROVED; **una sola escritura real**, no dos.
- Propuesta nueva de IN_REVIEW creada cuando el reporte era CONFIRMED; luego gestión posterior a RESOLVED; al aprobar por primera vez la propuesta vieja, terminó IN_REVIEW.

El bloqueo y la condición PENDING son correcciones verificadas. Falta proteger versión/updated_at y estado esperado del reporte en la misma transacción. Devolver 200 con decisión anterior en replay puede documentarse como idempotencia; no debe atribuirse al último actor una nueva aprobación.

## 4. Pruebas de la entrega y riesgo de pérdida de datos

### Suite existente sin modificaciones

Ejecutada con PostgreSQL 17.6 aislado, Python 3.13.18, dependencias directas exactas y sin claves:

`python -m pytest src/backend/tests -q --tb=short`

Resultado: **7 failed, 12 passed, 1 skipped**, 14,06 s, un warning de deprecación de AnyIO.

Los siete fallos son vertical_flow, los cinco casos de fallback y la reanudación tras caída total: esperan análisis exitoso aunque no hay claves. No se presentan como fallos de disponibilidad de un proveedor real. La comprobación E2E de frontend se omite por no existir `http://frontend:80`. No se ha reproducido “20 passed” ni una inferencia real multimodal; sí se pudieron ejecutar las pruebas de BD, CRUD y límites que no necesitan proveedores.

### Prueba del teardown con centinelas

En la base aislada se insertaron un reporte no sintético de prueba, una aprobación no perteneciente al test y se dejó DEMO0001 en RESOLVED. Se ejecutó únicamente:

`pytest backend/tests/test_ai_and_agent.py::test_secret_sanitization_never_leaks_keys -q`

Resultado **1 passed**, exit 0. Después: reporte centinela ausente; aprobación centinela ausente; demo en CONFIRMED. El fixture de módulo hace DELETE sin run_id y modifica datos que no creó. Esta prueba valida el riesgo de borrado sobre datos persistentes; no se expuso ninguna BD habitual.

El evaluador añade otro borrado amplio, descrito en N-03. No basta con aconsejar cuidado: se necesita configuración de prueba separada y una barrera automática que se niegue a ejecutar limpieza en una BD no identificada como desechable.

### Frontend y clon publicado

En la copia de HEAD, `npm install --no-audit --no-fund --package-lock=false` y `npm run build` aprobaron: TypeScript, Vite 6.4.5, 34 módulos, bundle JS 421,73 kB. Host Node 26.12.1; no se verifica Node 22 en Linux ni instalación PWA en navegador. No hay comando lint definido en package.json ni configuración de lint identificada; el build comprueba tipos, no equivale a lint.

El clon publicado en GitHub continúa en 91bff47 y carece del evaluador, las fases E/F y sus correcciones. El README de HEAD describe archivos que el clon de main no tiene. La afirmación de arranque limpio en 84,6 s de docs/estado.md no se reejecutó ni prueba que ese HEAD esté publicado. No se ejecutó push para resolverlo.

## 5. Evaluación de las 15 consultas

### Recalculo de los artefactos guardados

Se conservó el JSON original del git archive antes de ejecutar el evaluador en la copia. Sobre sus 15 filas se recalcularon sumas y percentiles mediante la función del proyecto:

| Dato | Recalculado desde JSON | Alcance real de verificación |
|---|---|---|
| PASS/FAIL | 14/15, 93,33 % por los flags guardados | Aritmética; no exactitud semántica validada a mano |
| P50 | 3549,0 ms | Ordenación de 15 latencias guardadas |
| P90 | 4815,2 ms | Interpolación lineal, índice (15−1)×0,9=12,6 |
| Prompt | 28526 | Suma de filas, no cotejo con cuenta del proveedor |
| Completion | 1874 | Suma de filas |
| Total | 30400 | Prompt+completion coincide |
| Costo equivalente total | 0,005623 USD | Suma redondeada de estimaciones guardadas |
| Costo medio | 0,000375 USD | Total/15 redondeado |
| Fallback marcado | Q04,Q09,Q11,Q12,Q13,Q15: 6/15=40 % | Flags del evaluador; definición problemática |
| Clasificación | 5/5 según categorías guardadas | Muestra sintética con texto descriptivo; no generalización a fotos ciudadanas |

El código mide tiempo de pared alrededor de cada consulta, por lo que el evaluador sí mejora el panel de percentiles por eventos. **No se acreditan retrospectivamente latencias, tokens consumidos ni facturación real mediante volver a sumar un archivo**. No se ejecutaron 15 inferencias reales ni se accedió a facturas. Las latencias nuevas de pruebas offline no sustituyen las históricas.

### Causa reproducible del FAIL Q13

Q13 pide proponer RESOLVED para CIV-2026-DEMO0002. El registro guardado presenta herramienta proponer_actualizacion_critica, guardrail HUMAN_APPROVAL_REQUIRED y una respuesta de propuesta pendiente, pero no incluye el código completo del reporte en el texto. Su regla must_contain_all exige ese radicado.

Se forzó TOTAL localmente y se ejecutó el agente contra PostgreSQL real: creó una propuesta correcta, requires_human_approval=true y degraded_sql_mode=true. La respuesta menciona aprobación/PENDING pero solo el prefijo del UUID de la propuesta; no contiene CIV-2026-DEMO0002. El resultado estructurado de la herramienta sí contiene el código correcto. Evaluación: must_contain_any=true, must_contain_all=false. **El fallo reproducible es omisión del radicado en el mensaje, no ausencia de propuesta ni una violación de aprobación humana en ese caso**.

Los trace_steps históricos de Q13 muestran dos fallos HTTP_429 y ninguna inferencia exitosa; los 0 tokens y la atribución final a Groq no significan que Groq generó la respuesta. No se pudo cotejar la ejecución histórica con la BD original de trazas. La reproducción actual demuestra la misma condición de FAIL con fallback SQL, sin depender de disponibilidad de red.

Corrección mínima: generar mensaje determinista con tracking_code y estado propuesto tomados del resultado validado; evaluar además que existe una propuesta PENDING, el reporte no cambió y no hay duplicación. No relajar la prueba para ocultar el FAIL.

### Inferencia, SQL, síntesis y revisión humana

- Según el JSON histórico, 13 consultas tienen al menos un evento de modelo exitoso. Eso incluye turnos de herramientas y no demuestra que las 13 respuestas finales hayan sido redactadas por un modelo: Q12 tiene eventos exitosos y fallos posteriores.
- Q13 y Q14 no tienen ningún evento de inferencia exitoso. Sus respuestas son compatibles con respaldo determinista SQL, reproducido en esta auditoría.
- Q14 tiene provider/model none, cero trazas y fallback_used=false. Su degradación queda fuera del 40 %. Si se añade solamente ese respaldo SQL omitido, son al menos 7/15=46,67 % de consultas con algún respaldo/degradación bajo una definición amplia. No es una tasa corregida de fallback independiente entre proveedores: hace falta separar esas categorías.
- `get_latest_trace_info` marca fallback por cualquier evento fallido y atribuye provider/model al último éxito, o al último fallo si no hubo éxitos. Por ello el 40 % no representa “Groq respondió al 40 %” ni éxito de conmutación en el 40 %.
- Q08–Q11/Q15 usan imágenes generadas por generate_synthetic_evidence_png según expected_category y descripciones que indican claramente el incidente. Son **insumos sintéticos**. No se les debe llamar fotos reales ni afirmar que una categoría correcta demuestra uso visual en lugar de lectura del texto. El código normal llama a proveedores; la autenticidad de las respuestas históricas no fue verificada contra cuentas externas.
- casos_dorados declara VERIFICADO_POR_SQL y revisión humana externa pendiente. La auditoría ejecutó las seis consultas SQL sobre semilla nueva y obtuvo 6/6; esto **no es revisión manual humana**. El verificador automático tiene además falsos positivos (N-04).

### Ejecución independiente offline del evaluador completo

Se ejecutó evaluar.run_evaluation(mode='all', pause_sec=0), sustituyendo las cuatro funciones de red para fallar siempre con un error local. Conservó SQL, persistencia de trazas, agente, scoring y escritura de resultados reales en la copia temporal. Resultado: **9/15**, cero de cinco clasificaciones aprobadas, Q13 FAIL, y borrado del centinela de aprobación ajena. Es una prueba de degradación determinista y scoring; no se presenta como evaluación de inferencia real.

## 6. Nuevos hallazgos

### N-01 — ALTO: entrega publicada diferente del HEAD evaluado

**Evidencia:** consulta remota y clon independiente en 91bff47 frente a a14e895 local, dos commits adelantados. README/evaluador/fixes solo están en la historia local. **Riesgo:** otro computador obtiene otra aplicación y otra superficie de seguridad.

**Corrección:** después de resolver bloqueos y con autorización de publicación, entregar SHA inmutable alcanzable en GitHub y comprobar clon+README+pruebas sobre exactamente ese SHA. Esta auditoría no autorizó ni ejecutó publicación.

### N-02 — ALTO: cambio oculto de modelo antes de Groq y atribución falsa en trazas

**Archivos/líneas:** ai_router.py:68-85,313-351,560-589; agent.py:420-501.

Ante 429/503, el adaptador llama a un modelo Gemini alternativo hardcodeado **antes de devolver el control al router y antes de intentar Groq**. No está en la cadena configurada ni hay preflight/capability gate en ese recorrido. El modelo configurado se marca agotado durante 300 s. La respuesta sigue devolviendo el ID original y un solo intento, con costo/circuito asociados al modelo equivocado. reset_all_circuits tampoco borra el estado de modelos agotados.

**Reproducción ejecutada:** solo se sustituyó HTTP: primer POST→429, segundo→contrato válido. Secuencia solicitada: gemini-3.8-flash → gemini-3-flash-preview. Resultado del router: model gemini-3.8-flash, attempts=1, fallback_used=false. No se llamó a Groq. Se probó el adaptador real, no el inyector FALLA_FORZADA, que se ejecuta antes del adaptador y no detecta este problema.

**Riesgo:** incumple orden Gemini→Groq→Gemini, aumenta llamadas y plazo, altera tarifas/capacidades y hace inexactas las trazas de evaluación. No se afirma que esos modelos alternativos sean inexistentes: su acceso y sus capacidades no se validaron en esta auditoría.

**Corrección:** todo cambio de modelo debe pasar por router explícito con preflight por rol, deadline y evento por llamada real; registrar modelo efectivo y uso, conservando el intento fallido anterior. Respetar proveedor independiente antes del siguiente Gemini cuando corresponda.

### N-03 — ALTO: evaluador borra aprobaciones ajenas por coincidencia textual

**Archivo/línea:** eval/evaluar.py:437.

DELETE FROM pending_approvals filtra motivos por las palabras atendido o RESOLVED, sin run_id ni IDs de las propuestas creadas. Se insertó una aprobación sintética previa cuyo motivo coincidía y se ejecutó la evaluación offline: **la aprobación ajena fue eliminada**. La ejecución normal recomendada comparte BD del API y monta ./eval con escritura.

**Corrección:** evaluador en BD/volúmenes propios con guardia de entorno; capturar y limpiar solo IDs creados por esa ejecución o usar rollback/esquema desechable. No ejecutar el comando de evaluación sobre datos habituales hasta corregirlo.

### N-04 — MEDIO: verificador dorado y scoring aceptan evidencia insuficiente

**Archivos/líneas:** eval/evaluar.py:69-79,350-357,520; casos_dorados.json.

sql_ok inicia en true. Para casos por radicado solo compara tracking_code; ignora categoría/severidad/comuna/estado esperados. Si no devuelve filas, tampoco entra a la rama y queda true. En conteos ignora los códigos esperados. Reproductor con SELECT de tracking correcto y categoría WRONG→sql_verificado=true; SELECT sin filas para un reporte esperado→true.

tool_ok acepta cualquier herramienta si degraded_sql_mode=true; las comprobaciones de respuesta son subcadenas, no equivalencia semántica ni conteos exactos. En Q14 expected_tool=None no significa “sin requisito” en la expresión: una respuesta real correcta con herramientas y sin degradación no satisface None in tools_called. El encabezado markdown imprime len/len aunque fallen verificaciones.

**Corrección:** comparar todas las columnas/filas/conjuntos esperados, fallar cerrado ante filas ausentes, separar herramienta opcional de obligatoria, validar evidencias y efectos de Q13 y registrar aciertos efectivos. Revisión humana independiente con fecha/autor y respuestas anotadas, sin llamarla SQL manual.

### N-05 — MEDIO: facturación cero etiquetada como observada sin medición

**Archivos/líneas:** eval/evaluar.py:475-478,501,533; observability.py:11-17,35-38.

billed_cost_usd_observed=0.0 y el texto del reporte son constantes. No consultan cuenta/factura ni configuración que acredite tier gratuito. La auditoría solo verificó el cálculo equivalente con tarifas del código; no su vigencia comercial. N-02 hace además que se valoren modelos efectivos bajo ID/tarifa incorrectos. Uso de intentos fallidos o IA anidada puede no agregarse íntegramente.

**Corrección:** facturación desconocida/null salvo evidencia de cuenta; estimaciones con fuente/fecha/unidad y modelo efectivo; conservar uso de cada llamada y vincular trazas anidadas. No presentar $0 como hecho observado por el script.

### N-06 — MEDIO: filtro de comuna amplía resultados por dígitos de direcciones

**Archivo/líneas:** repository.py:311-319.

La normalización numérica de comuna añadió OR neighborhood/address ILIKE '%entrada%'. Con semilla real, comuna='2' devuelve **6 reportes**, mientras igualdad comuna='Comuna 2' tiene **2**: DEMO0001 y DEMO0004. Incluye direcciones/barrios de otras comunas porque contienen el dígito 2. No es inyección SQL: las consultas siguen parametrizadas, pero la semántica del filtro es incorrecta.

**Corrección:** normalizar comuna a identificador canónico y filtrar exclusivamente esa columna; mantener barrio/dirección en filtros independientes. Añadir regresión que compare '2' y 'Comuna 2' y excluya Comuna 20/direcciones numéricas ajenas.

## 7. Bloqueos críticos y corrección mínima por prioridad

1. **Autorización y secreto:** cerrar PATCH status anónimo; propiedad/capacidad secreta para confirmación; impedir cambios a decisiones administrativas sin rol; exigir token robusto al arrancar, rechazar explícitamente credenciales demo y retirarlas de fallbacks. La UI vacía y hmac no cierran estas brechas.
2. **Datos persistentes:** aislar pruebas/evaluación automáticamente, eliminar limpiezas globales y demostrar con centinelas que nunca tocan la BD habitual. Mientras tanto, no recomendar pytest/evaluación en el volumen de aplicación.
3. **Integridad de operaciones:** idempotencia durable tras commit, observabilidad desacoplada, deadline protegido para efectos y validación de versión de propuestas. Repetir negativas en PostgreSQL real, incluida carrera entre decisión y edición.
4. **Contrato y respuesta ciudadana:** rechazar campos ausentes/ilegibles/enums desconocidos; no inventar confianza; aplicar DTO y minimización de PII a todos los canales, incluidos SQL, herramientas, resúmenes y transcripciones. Mantener interpretación humana separada del diagnóstico IA.
5. **Resiliencia y recursos:** quitar sustituciones ocultas, preflight/modelo efectivo por llamada, deadline integral, contabilidad de tokens anidados, único half-open y cuotas compartidas. Corregir alta síncrona dentro del event loop, audio real, proxy trust y readiness.
6. **Evaluación y entrega:** corregir Q13, verificador/scoring/filtro de comuna y categorías de fallback; separar inferencia real de SQL e insumos sintéticos, completar revisión manual y medición trazable. Solo después publicar con autorización y comprobar clon desde GitHub del SHA entregado, dependencias bloqueadas, README y arranque Docker en otro equipo.

No se certifica ausencia de otras vulnerabilidades ni compatibilidad de navegadores. No se repitió escaneo exhaustivo de secretos o vulnerabilidades de dependencias en esta segunda revisión: la verificación de token se realizó sin leer claves reales. Las limitaciones de Docker/proveedores no impiden el dictamen NO LISTO, pues las brechas principales fueron reproducidas con persistencia y concurrencia reales.

## 8. Reproducción segura de la evidencia

Para repetir: crear copia de `git archive a14e895`, clúster PostgreSQL 17 nuevo y dos bases cuyo nombre comience civia_audit_; usar uploads nuevos dentro del directorio temporal. Instalar requirements con Python 3.13, establecer PYTHONUTF8=1, PYTHONPATH a src/backend, DATABASE_URL exclusivamente al clúster de auditoría, y vaciar las tres claves de API. No copiar .env ni montar el volumen habitual. Los scripts de apoyo citados al principio producen observations.json/more_observations.json con datos sintéticos, no secretos. Sus duraciones pueden variar.

El apéndice incorpora los scripts principales y requiere que el argumento sea la raíz temporal que contiene src. Su guardia adicional se incluye para impedir una repetición accidental contra una BD habitual. Los scripts realizan cambios/borrados solo en esa BD de pruebas y dejan resultados sintéticos para inspección; no son tests de producción. Requieren empezar con bases nuevas para evitar colisión de las tablas/funciones temporales de auditoría. Para concurrencia se usan barrera de dos hilos y trigger que cuenta escrituras, no mocks de SQL.

### Script: probes.py
```python
# Guardia para repetición: solo clúster/BD exclusivos y archivos temporales.
import os as _audit_os, sys as _audit_sys
from urllib.parse import urlparse as _audit_urlparse
from pathlib import Path as _AuditPath
_audit_db = _audit_urlparse(_audit_os.environ.get('DATABASE_URL', ''))
assert (_audit_db.hostname, _audit_db.port, _audit_db.path) == ('127.0.0.1', 55473, '/civia_audit_final')
assert _AuditPath(_audit_os.environ['UPLOAD_DIR']).resolve().is_relative_to(_AuditPath(_audit_sys.argv[1]).resolve())
assert not any(_audit_os.environ.get(k) for k in ('GOOGLE_API_KEY_PRIMARY', 'GOOGLE_API_KEY_SECONDARY', 'GROQ_API_KEY'))
import os,sys,json,time,uuid,io,threading,subprocess,importlib.util
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from fastapi.testclient import TestClient
from app import main as m,agent as a,ai_router as r,repository as repo
from app.config import settings
from app.db import get_conn,run_migrations
from app.seed import seed_synthetic_reports
from app.security import validate_and_store_audio,CitizenValidationError
root=Path(sys.argv[1]); observations=[]
def emit(probe,**kw):
    result={'probe':probe,**kw};observations.append(result);print(json.dumps(result,ensure_ascii=False))
def sql(q,params=(),one=False):
    with get_conn() as c:
        cur=c.execute(q,params); rows=cur.fetchall() if cur.description else [];c.commit();return (rows[0] if rows else None) if one else rows
run_migrations();seed_synthetic_reports()
client=TestClient(m.app,raise_server_exceptions=False)
buf=io.BytesIO();Image.new('RGB',(32,32),(120,60,40)).save(buf,format='PNG');img=buf.getvalue()
def create(title='DATO SINTETICO AUDITORIA',auto=False,headers=None):
    m.rate_limiter.reset()
    return client.post('/api/reports',data={'description':title+' evidencia de prueba','latitude':'3.4','longitude':'-76.5','auto_analyze':str(auto).lower()},files={'photo':('audit.png',img,'image/png')},headers=headers or {})
row=create().json();rid=row['id']
no=client.patch(f'/api/reports/{rid}/status',json={'status':'RESOLVED','human_approved':False})
yes=client.patch(f'/api/reports/{rid}/status',json={'status':'RESOLVED','human_approved':True})
confirm=client.patch(f'/api/reports/{rid}/confirm',json={'final_category':'QUEMA','final_severity':'CRITICA'})
emit('authorization',false_status=no.status_code,true_status=yes.status_code,stored_status=repo.get_report_raw(rid)['status'],third_party_confirm=confirm.status_code,category_after_admin=repo.get_report_raw(rid)['final_category'])
with patch.object(m,'get_observability_summary',return_value={}):
    without=client.get('/api/admin/observability').status_code
    default=client.get('/api/admin/observability',headers={'X-Admin-Token':settings.ADMIN_TOKEN}).status_code
    with patch.object(settings,'ADMIN_TOKEN','x'):
        weak=client.get('/api/admin/observability',headers={'X-Admin-Token':'x'}).status_code
    with patch.object(settings,'ADMIN_TOKEN',''):
        empty=client.get('/api/admin/observability').status_code
emit('admin_token',missing_header=without,configuration_default=default,one_character=weak,empty_denied=empty,frontend_default_removed="useState<string>('')" in (root/'src/frontend/src/App.tsx').read_text())
# In-progress worker performs an actual PostgreSQL write after timeout.
started=threading.Event();finished=threading.Event()
def late_write(args):
    started.set();time.sleep(.20);repo.update_report_status(rid,status='REJECTED');finished.set();return {}
with patch.dict(a.TOOL_DISPATCH,{'audit_late_write':late_write}):
    t=time.perf_counter()
    try:a.execute_tool_with_timeout('audit_late_write',{},.02)
    except TimeoutError: elapsed=time.perf_counter()-t
    before=repo.get_report_raw(rid)['status'];finished.wait(2);after=repo.get_report_raw(rid)['status']
emit('timeout_late_write',requested=.02,returned_after=round(elapsed,4),status_at_return=before,status_after_worker=after,worker_finished=finished.is_set())
cases=[{}, {'category':'HUECO','summary':'Resumen sintetico valido'}, {'category':'NUCLEAR','severity':'INVENTADA','confidence':'inventada','summary':'Resumen sintetico valido'}, {'category':'HUECO','severity':'ALTA','summary':'Resumen sintetico valido','confidence':-5}]
for i,data in enumerate(cases):
    try:contract=r.parse_and_validate_analysis_json(json.dumps(data));emit('contract_'+str(i),accepted=True,contract=contract.model_dump())
    except r.AIProviderError as e:emit('contract_'+str(i),accepted=False,error=e.code)
for label,audio in [('previous',b'ID3not-an-audio'),('padded',b'ID3\x04'+b'\0'*96)]:
    try: meta=validate_and_store_audio(audio,upload_dir=root/'audio_probe');emit('audio_'+label,accepted=True,duration=meta['audio_duration_seconds'])
    except CitizenValidationError:emit('audio_'+label,accepted=False)
headers={'Idempotency-Key':'synthetic-audit-same-operation'}
first=create('RETRY SYNTHETIC',headers=headers);second=create('RETRY SYNTHETIC',headers=headers)
emit('idempotency',http=[first.status_code,second.status_code],different_report_ids=first.json()['id']!=second.json()['id'])
count=lambda:sql('SELECT COUNT(*) AS n FROM reports',one=True)['n']
n=count()
with patch.object(r,'record_ai_trace',side_effect=RuntimeError('synthetic trace store failure')):
    failed1=create('POSTCOMMIT SYNTHETIC',auto=True);failed2=create('POSTCOMMIT SYNTHETIC',auto=True)
emit('postcommit_failure',http=[failed1.status_code,failed2.status_code],new_persisted_reports=count()-n)
# Actual row-lock decisions and stale proposals.
def proposal(new_status='IN_REVIEW'):
    return a.tool_proponer_actualizacion_critica({'identificador':rid,'nuevo_estado':new_status,'motivo':'AUDITORIA SINTETICA'})['approval_id']
repo.update_report_status(rid,status='CONFIRMED');aid=proposal('IN_REVIEW');a.decide_pending_approval(aid,approve=True,decided_by='audit')
repo.update_report_status(rid,status='RESOLVED');repeat=a.decide_pending_approval(aid,approve=False,decided_by='audit2')
emit('approval_replay',decision=repeat['status'],report_after_replay=repo.get_report_raw(rid)['status'])
repo.update_report_status(rid,status='CONFIRMED');stale=proposal('IN_REVIEW');repo.update_report_status(rid,status='RESOLVED');a.decide_pending_approval(stale,approve=True,decided_by='audit')
emit('stale_approval',before='RESOLVED',after=repo.get_report_raw(rid)['status'])
sql('CREATE TABLE audit_write_log (report_id uuid)')
sql("CREATE FUNCTION audit_write_counter() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO audit_write_log VALUES (NEW.id); RETURN NEW; END $$")
sql('CREATE TRIGGER audit_count AFTER UPDATE ON reports FOR EACH ROW EXECUTE FUNCTION audit_write_counter()')
aid=proposal('RESOLVED');barrier=threading.Barrier(2)
def decide(approve):barrier.wait();return a.decide_pending_approval(aid,approve=approve,decided_by='concurrent-audit')['status']
with ThreadPoolExecutor(max_workers=2) as ex:
    futures=[ex.submit(decide,x) for x in [True,False]];decisions=[f.result() for f in futures]
writes=sql('SELECT COUNT(*) AS n FROM audit_write_log WHERE report_id=%s',(rid,),one=True)['n']
emit('approval_concurrency',returned_decisions=decisions,report_writes=writes,one_final_decision=len(set(decisions))==1)
# Force an approve/approve race and count actual report updates.
sql('TRUNCATE audit_write_log');aid=proposal('IN_REVIEW');barrier=threading.Barrier(2)
with ThreadPoolExecutor(max_workers=2) as ex:
    futures=[ex.submit(decide,True) for _ in range(2)];decisions=[f.result() for f in futures]
emit('approval_double_approve',returned_decisions=decisions,report_writes=sql('SELECT COUNT(*) AS n FROM audit_write_log WHERE report_id=%s',(rid,),one=True)['n'])
# Current budget and output paths without network, with real trace storage.
chain=[dict(provider='google',model='audit',api_key='fake',tier='primary')]
with patch.object(a,'get_provider_chain',return_value=chain),patch.object(a,'_call_agent_turn_gemini',return_value=('Gemini HTTP 429 traceback user@example.org',[],100,100)):
    r.reset_all_circuits();out=a.run_civia_agent('consulta sintetica');emit('filtered_original_payload',answer=out['answer'],tool_count=len(out['tools_invoked']))
with patch.object(a,'get_provider_chain',return_value=chain),patch.object(a,'_call_agent_turn_gemini',return_value=('Google API HTTP 401 ValueError user@example.org',[],100,100)):
    r.reset_all_circuits();out=a.run_civia_agent('consulta sintetica');emit('filter_bypass',answer=out['answer'])
with patch.object(a,'get_provider_chain',return_value=chain),patch.object(a,'_call_agent_turn_gemini',return_value=('respuesta',[],1000,700)):
    r.reset_all_circuits();out=a.run_civia_agent('consulta sintetica',max_tokens_budget=50,max_iterations=10);emit('token_limit',used=out['total_tokens_used'],budget=out['max_tokens_budget'],iterations_cap=out['max_iterations'],guardrail=out['guardrail_triggered'])
def slow_turn(**kw):time.sleep(.05);return None,[{'name':'audit_slow','args':{}}],1,1
def slow_tool(args):time.sleep(.10);return {'total_encontrados':0}
with patch.object(a,'get_provider_chain',return_value=chain),patch.object(a,'_call_agent_turn_gemini',side_effect=slow_turn),patch.dict(a.TOOL_DISPATCH,{'audit_slow':slow_tool}):
    r.reset_all_circuits();t=time.perf_counter();out=a.run_civia_agent('consulta sintetica',total_timeout_seconds=.02);emit('global_timeout',elapsed=round(time.perf_counter()-t,4),budget=.02,tools_started=len(out['tools_invoked']))
# One synthetic transcript and AI summary, no private data.
sql('UPDATE reports SET audio_transcript=%s,ai_summary=%s WHERE id=%s',('user@example.org HTTP 401 Google API','Google API HTTP 401 user@example.org',rid))
pub=client.get('/api/reports/'+rid).json();emit('public_channels',transcript=pub['audio_transcript'],summary=pub['ai_summary'])
# Multiple half-open callers admitted.
cb=r.CircuitBreakerState('audit','audit',state='OPEN',opened_at=time.monotonic()-20)
emit('half_open',admitted=[cb.allow_request() for _ in range(3)])
# Queue quota negative: 31st agent request should be rejected before invocation.
m.rate_limiter.reset()
with patch.object(m,'run_civia_agent',return_value=dict(answer='sintetico',trace_group_id=str(uuid.uuid4()),tools_invoked=[],iterations_used=1,max_iterations=5,total_tokens_used=0,max_tokens_budget=6000,latency_ms=0)) as fake:
    statuses=[client.post('/api/agent/query',json={'query':'consulta sintetica'}).status_code for _ in range(31)]
    emit('agent_rate_limit',first=statuses[0],last=statuses[-1],model_invocations=fake.call_count)
# Golden SQL and Q13 deterministic path.
spec=importlib.util.spec_from_file_location('audit_eval',root/'src/eval/evaluar.py');ev=importlib.util.module_from_spec(spec);spec.loader.exec_module(ev)
gold=ev.verify_golden_sql_ground_truth(root/'src/eval/casos_dorados.json');emit('golden_sql',total=len(gold),passed=sum(x['sql_verificado'] for x in gold))
q13=next(q for q in ev.build_15_representative_queries() if q['id']=='Q13')
r.reset_all_circuits();r.set_runtime_fault_override('TOTAL');out=a.run_civia_agent(q13['input']);r.set_runtime_fault_override('NONE')
ans=out['answer'].upper();emit('q13',tools=[x['tool'] for x in out['tools_invoked']],approval=out['requires_human_approval'],degraded=out.get('degraded_sql_mode'),must_contain_all=all(t.upper() in ans for t in q13['must_contain_all']),must_contain_any=any(t.upper() in ans for t in q13['must_contain_any']),answer=out['answer'],proposal_tracking=out['tools_invoked'][-1]['result'].get('tracking_code'))
# Prove SQL verifier ignores wrong fields and missing expected rows.
case=dict(id='AUDIT',tipo='audit',es_respondible=True,origen_datos='sintetico',pregunta='audit',sql_comprobacion="SELECT 'CIV-2026-DEMO0004' AS tracking_code, 'WRONG' AS category",respuesta_esperada_sql={'tracking_code':'CIV-2026-DEMO0004','category':'QUEMA'})
case2={**case,'id':'EMPTY','sql_comprobacion':"SELECT tracking_code FROM reports WHERE false"}
path=root/'synthetic_gold.json';path.write_text(json.dumps({'casos_dorados':[case,case2]}));bad=ev.verify_golden_sql_ground_truth(path);emit('golden_verifier_false_positives',accepted_wrong_category=bad[0]['sql_verificado'],accepted_missing_report=bad[1]['sql_verificado'])
(root/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2))

```

### Script: more_probes.py
```python
# Guardia para repetición: solo clúster/BD exclusivos y archivos temporales.
import os as _audit_os, sys as _audit_sys
from urllib.parse import urlparse as _audit_urlparse
from pathlib import Path as _AuditPath
_audit_db = _audit_urlparse(_audit_os.environ.get('DATABASE_URL', ''))
assert (_audit_db.hostname, _audit_db.port, _audit_db.path) == ('127.0.0.1', 55473, '/civia_audit_final')
assert _AuditPath(_audit_os.environ['UPLOAD_DIR']).resolve().is_relative_to(_AuditPath(_audit_sys.argv[1]).resolve())
assert not any(_audit_os.environ.get(k) for k in ('GOOGLE_API_KEY_PRIMARY', 'GOOGLE_API_KEY_SECONDARY', 'GROQ_API_KEY'))
import os,sys,json,subprocess,importlib.util,uuid,io,time,asyncio
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app import main as m,agent as a,ai_router as r,repository as repo
from app.db import get_conn,run_migrations
from app.config import settings
from app.seed import seed_synthetic_reports
from PIL import Image
root=Path(sys.argv[1]);results=[]
def emit(probe,**kw):
    result={'probe':probe,**kw};results.append(result);print(json.dumps(result,ensure_ascii=False))
def sql(q,params=(),one=False):
    with get_conn() as c:
        cur=c.execute(q,params); rows=cur.fetchall() if cur.description else [];c.commit();return (rows[0] if rows else None) if one else rows
client=TestClient(m.app,raise_server_exceptions=False)
spec=importlib.util.spec_from_file_location('audit_eval',root/'src/eval/evaluar.py');ev=importlib.util.module_from_spec(spec);spec.loader.exec_module(ev)
stored=json.loads((root/'src/eval/resultados/reporte_evaluacion.json').read_text());rows=stored['queries_detail'];metrics=stored['metrics_15_queries'];lats=[q['latency_ms'] for q in rows]
recalc=dict(p50=ev.percentile(lats,50),p90=ev.percentile(lats,90),prompt=sum(q['prompt_tokens'] for q in rows),completion=sum(q['completion_tokens'] for q in rows),total=sum(q['total_tokens'] for q in rows),cost=round(sum(q['estimated_cost_usd'] for q in rows),6),fallback_ids=[q['id'] for q in rows if q['fallback_used']],successful_model_queries=[q['id'] for q in rows if any(s['success'] for s in q['trace_steps'])],no_successful_model_queries=[q['id'] for q in rows if not any(s['success'] for s in q['trace_steps'])])
emit('stored_metrics_recalculation',**recalc)
# Hidden same-provider model switch: real adapter, simulated HTTP only.
valid={'candidates':[{'content':{'parts':[{'text':json.dumps(dict(category='HUECO',severity='ALTA',confidence=.9,summary='Evidencia sintetica de prueba',keywords=[]))}]}}],'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':5}}
urls=[]
def post(self,url,**kw):
    urls.append(url.split('/models/')[-1].split(':')[0]);return __import__('httpx').Response(429 if len(urls)==1 else 200,json={} if len(urls)==1 else valid)
r.reset_all_circuits();r._EXHAUSTED_GEMINI_MODELS.clear()
with patch.object(r.httpx.Client,'post',new=post),patch.object(settings,'GOOGLE_API_KEY_PRIMARY','synthetic'):
    contract,meta=r.classify_evidence_with_router(description='sintetico',latitude=3.4,longitude=-76.5,image_bytes=None,image_mime=None)
emit('hidden_model_switch',requested_model_sequence=urls,reported_model=meta['model'],reported_attempts=meta['attempts'],reported_fallback=meta['fallback_used'])
# Health response when database is unavailable.
with patch.object(m,'check_db_health',return_value={'connected':False,'schema_ready':False}):emit('unready_health',http=client.get('/health').status_code,body=client.get('/health').json())
# Nginx forwarded clients share one key unless proxy trust explicitly configured.
async def endpoint(request):return JSONResponse({'host':request.client.host})
wrapped=ProxyHeadersMiddleware(Starlette(routes=[Route('/',endpoint)]))
proxy=TestClient(wrapped,client=('172.18.0.8',40000))
emit('proxy_identity',hosts=[proxy.get('/',headers={'X-Forwarded-For':ip}).json()['host'] for ip in ['198.51.100.1','198.51.100.2']])
# Photo cleanup narrow fix and remaining failure path.
buf=io.BytesIO();Image.new('RGB',(32,32)).save(buf,format='PNG');img=buf.getvalue()
def send(files):
    m.rate_limiter.reset();return client.post('/api/reports',data={'description':'DATO SINTETICO ARCHIVOS AUDIT','latitude':'3.4','longitude':'-76.5','auto_analyze':'false'},files=files)
count_files=lambda:len(list(settings.UPLOAD_DIR.glob('photo_*')))
before=count_files();resp=send({'photo':('audit.png',img,'image/png'),'audio':('bad.wav',b'not audio','audio/wav')});emit('invalid_audio_cleanup',http=resp.status_code,photos_added=count_files()-before)
before=count_files()
with patch.object(m,'create_report',side_effect=RuntimeError('synthetic insert failure')):resp=send({'photo':('audit.png',img,'image/png')})
emit('insert_failure_orphan',http=resp.status_code,photos_added=count_files()-before)
emit('tracking_collision',same_code=repo.generate_tracking_code(uuid.UUID('aaaaaaaa-1111-4111-8111-111111111111'))==repo.generate_tracking_code(uuid.UUID('aaaaaaaa-2222-4222-8222-222222222222')))
# Seed a non-synthetic sentinel and an unrelated pending approval, then execute ONE existing pure unit test.
resp=send({'photo':('audit.png',img,'image/png')});sentinel=resp.json()['id'];demo=repo.get_report_by_tracking_code('CIV-2026-DEMO0001');repo.update_report_status(demo['id'],status='RESOLVED')
aid=a.tool_proponer_actualizacion_critica({'identificador':'CIV-2026-DEMO0001','nuevo_estado':'IN_REVIEW','motivo':'UNRELATED SYNTHETIC SENTINEL'})['approval_id']
proc=subprocess.run([sys.executable,'-m','pytest',str(root/'src/backend/tests/test_ai_and_agent.py')+'::test_secret_sanitization_never_leaks_keys','-q','--tb=short'],capture_output=True,text=True)
(root/'sentinel_pytest.txt').write_text(proc.stdout+'\n'+proc.stderr)
emit('pytest_destroys_sentinels',exit=proc.returncode,citizen_sentinel_exists=repo.get_report_raw(sentinel) is not None,approval_sentinel_exists=bool(sql('SELECT id FROM pending_approvals WHERE id=%s',(aid,))),demo_status_after=repo.get_report_raw(demo['id'])['status'])
# Execute the full evaluator with every model call failing locally: no API calls.
# Protect data by staying in this audit-only database. Insert marker matched by its cleanup.
aid=a.tool_proponer_actualizacion_critica({'identificador':'CIV-2026-DEMO0001','nuevo_estado':'IN_REVIEW','motivo':'UNRELATED SENTINEL ya atendido'})['approval_id']
with patch.object(a,'_call_agent_turn_gemini',side_effect=r.AIProviderError('OFFLINE','synthetic offline',False)),patch.object(a,'_call_agent_turn_groq',side_effect=r.AIProviderError('OFFLINE','synthetic offline',False)),patch.object(r,'_call_gemini_multimodal',side_effect=r.AIProviderError('OFFLINE','synthetic offline',False)),patch.object(r,'_call_groq_multimodal',side_effect=r.AIProviderError('OFFLINE','synthetic offline',False)):
    offline=ev.run_evaluation(mode='all',pause_sec=0)
emit('offline_evaluation',passed=offline['metrics_15_queries']['passed_queries'],total=15,multimodal_passed=sum(q['passed'] for q in offline['queries_detail'] if q['kind']!='agent'),q13_passed=next(q['passed'] for q in offline['queries_detail'] if q['id']=='Q13'),unrelated_approval_deleted=not bool(sql('SELECT id FROM pending_approvals WHERE id=%s',(aid,))))
(root/'more_observations.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))

```

### Script: last_probes.py
```python
# Guardia para repetición: solo clúster/BD exclusivos y archivos temporales.
import os as _audit_os, sys as _audit_sys
from urllib.parse import urlparse as _audit_urlparse
from pathlib import Path as _AuditPath
_audit_db = _audit_urlparse(_audit_os.environ.get('DATABASE_URL', ''))
assert (_audit_db.hostname, _audit_db.port, _audit_db.path) == ('127.0.0.1', 55473, '/civia_audit_final')
assert _AuditPath(_audit_os.environ['UPLOAD_DIR']).resolve().is_relative_to(_AuditPath(_audit_sys.argv[1]).resolve())
assert not any(_audit_os.environ.get(k) for k in ('GOOGLE_API_KEY_PRIMARY', 'GOOGLE_API_KEY_SECONDARY', 'GROQ_API_KEY'))
import asyncio,io,json,time,sys
from unittest.mock import patch
from pathlib import Path
from PIL import Image
import httpx
from app import main as m,repository as repo
from app.db import get_conn
from app.config import settings
with get_conn() as c:
    expected=[r['tracking_code'] for r in c.execute("SELECT tracking_code FROM reports WHERE comuna='Comuna 2' ORDER BY tracking_code").fetchall()]
count,rows=repo.list_reports(comuna='2');print(json.dumps({'probe':'comuna_filter_regression','exact_comuna_2':expected,'numeric_filter_codes':[r['tracking_code'] for r in rows],'numeric_filter_total':count}))
buf=io.BytesIO();Image.new('RGB',(32,32)).save(buf,format='PNG')
def classifier(**kw):time.sleep(.30);return None,{}
async def run():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app),base_url='http://audit') as client:
        delays=[]
        async def heartbeat():
            t=time.perf_counter();await asyncio.sleep(.02);delays.append(time.perf_counter()-t)
        beat=asyncio.create_task(heartbeat());await asyncio.sleep(0)
        m.rate_limiter.reset()
        with patch.object(m,'classify_evidence_with_router',side_effect=classifier):
            response=await client.post('/api/reports',data={'description':'DATO SINTETICO EVENT LOOP AUDIT','latitude':'3.4','longitude':'-76.5','auto_analyze':'true'},files={'photo':('audit.png',buf.getvalue(),'image/png')})
        await beat
        print(json.dumps({'probe':'blocked_event_loop','http':response.status_code,'timer_budget_seconds':.02,'timer_actual_seconds':round(delays[0],4),'simulated_sync_ai_seconds':.30}))
asyncio.run(run())

```

### Script: admin_after_probe.py
```python
# Guardia para repetición: solo clúster/BD exclusivos y archivos temporales.
import os as _audit_os, sys as _audit_sys
from urllib.parse import urlparse as _audit_urlparse
from pathlib import Path as _AuditPath
_audit_db = _audit_urlparse(_audit_os.environ.get('DATABASE_URL', ''))
assert (_audit_db.hostname, _audit_db.port, _audit_db.path) == ('127.0.0.1', 55473, '/civia_audit_final')
assert _AuditPath(_audit_os.environ['UPLOAD_DIR']).resolve().is_relative_to(_AuditPath(_audit_sys.argv[1]).resolve())
assert not any(_audit_os.environ.get(k) for k in ('GOOGLE_API_KEY_PRIMARY', 'GOOGLE_API_KEY_SECONDARY', 'GROQ_API_KEY'))
import json,os
from fastapi.testclient import TestClient
from app import main as m,agent as a,repository as repo
from app.config import settings
report=repo.list_reports(limit=1)[1][0];aid=a.tool_proponer_actualizacion_critica({'identificador':str(report['id']),'nuevo_estado':'RESOLVED','motivo':'SYNTHETIC ADMIN DECISION AUDIT'})['approval_id']
with TestClient(m.app) as c:
    approved=c.post('/api/admin/approvals/'+aid+'/decide',headers={'X-Admin-Token':settings.ADMIN_TOKEN},json={'approve':True,'decided_by':'audit-admin'})
    changed=c.patch('/api/reports/'+str(report['id'])+'/confirm',json={'final_category':'QUEMA','final_severity':'CRITICA','human_override_note':'SYNTHETIC THIRD PARTY'})
    print(json.dumps({'probe':'third_party_after_admin_decision','admin_decision_http':approved.status_code,'unauthorized_confirm_http':changed.status_code,'status_after':changed.json()['status'],'category_after':changed.json()['final_category'],'admin_env_present':bool(os.environ.get('ADMIN_TOKEN'))}))

```

### Cierre del entorno

Al finalizar se detuvo correctamente el servidor PostgreSQL temporal con pg_ctl, sin borrar archivos de evidencia ni tocar otros servidores/volúmenes. La última consulta remota volvió a anunciar main en 91bff47. El árbol original solo muestra docs/auditoria_codex_final.md como archivo nuevo; los fuentes y resultados versionados permanecen intactos.
