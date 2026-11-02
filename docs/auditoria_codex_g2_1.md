# CIVIA — reauditoría independiente de G2.1

Fecha: 2026-11-02, America/Bogota. Referencia: `docs/auditoria_codex_g2.md`.

**Commit exacto:** `5b36fb55f87dc49e3256f9814cddb47e3cb3b800`, rama `fix/auditoria-final`.
**Base comparada:** `4774236ef9e54a97b8c0ffb64c7b84d8778857f4`.

## Dictamen limitado a las cuatro prioridades

**G2.1 NO APROBADO: 1 PASS, 2 FAIL y 1 PARCIAL.**

La cancelación real del commit diferido corrige el contraejemplo A-02. El agente ya degrada sin 500 en el recorrido normal de vencimiento y el router rechaza la respuesta posterior al plazo, pero no hay garantía integral de tiempo: un worker no cooperativo se espera indefinidamente y el último manejador HTTP de TimeoutError contiene un NameError. El presupuesto de herramientas no se propaga al hilo real de ejecución, y la confianza efectiva en IP todavía permite evadir la cuota desde conexiones directas locales/privadas.

No se alteró producción ni se cambió de rama; no se crearon ni publicaron commits. Solo se añade este informe. No se revisaron ni se repitieron los otros hallazgos G2 fuera de A-02, M-03, M-06 y M-02.

## Versión, copia y aislamiento

El árbol original estaba limpio al comenzar. Se leyó la remediación G2.1, se contrastó el diff con 4774236 y se congeló HEAD con git archive en:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-g21-7f7fa18e4c3e4cdab6ec27276f8ba39e\src`.

Se inicializó otro clúster **PostgreSQL 17.6 real**, nuevo, escuchando solo en `127.0.0.1:55483`; bases desechables `test_g21_independent` y `test_g21_suite`. PGDATA, uploads y TEMP/TMP quedaron bajo esa raíz temporal. No se usó la BD habitual, no se copió .env y no se utilizaron datos privados ni claves reales. El código importado fue el de la copia archivada. Se reutilizaron CPython 3.13.18 y las dependencias directas exactas del proyecto, sin cambios de requirements en G2.1.

Los resultados de modelo/uso de tokens y las demoras HTTP fueron sintéticos. Las conexiones, transacciones, triggers, cancelaciones y consultas de verificación PostgreSQL fueron reales, no mocks. No hubo llamadas a proveedores externos ni cargas masivas.

Docker no está disponible. Para M-06 se cargó Uvicorn Config con las opciones extraídas del CMD real del Dockerfile y se ejecutó su middleware real. Nginx se contrastó por lectura y mediante cabeceras equivalentes a la sobrescritura que entrega. No se afirma haber ejecutado contenedores o Nginx real.

## Matriz de resultados

Todas las filas corresponden a `5b36fb55f87dc49e3256f9814cddb47e3cb3b800`.

| Hallazgo | Dictamen | Evidencia ejecutada | Garantía o bloqueo pendiente |
|---|---|---|---|
| A-02 | **PASS** | Trigger PostgreSQL diferido de 0,18 s; commit iniciado a 0,1965 s con límite 0,25 s: TimeoutError, worker terminado y valor ORIGINAL conservado. checked_commit también se canceló al empezar dentro del plazo. | Se acredita el contraejemplo real solicitado; no se certifica cualquier fallo de infraestructura. Las duraciones de cancelación exceden ligeramente el plazo; se consideran en M-03. |
| M-03 | **PARCIAL** | Agente directo 0,10 s retorna degradación TIMEOUT; API con timeout efectivo 0,10 s devuelve 200. Router con plazo 0,15 s rechaza contrato a 0,4058 s y read timeout ≈0,15. | Worker bloqueante iniciado tarda 0,4564 s con límite 0,10. Manejador HTTP final de TimeoutError produce 500 por uuid no importado. Literal HTTP 0,10 sigue rechazado por esquema con 422. |
| M-06 | **FAIL** | Con opciones reales de Docker/Uvicorn, peer público: XFF variable 200/200/429. Peer loopback o privado directo: XFF variable **200/200/200** frente a 200/200/429 sin XFF. | Persisten vías directas de evasión; el backend publicado en loopback todavía confía en esas cabeceras. La sobrescritura Nginx sí bloquea el caso a través del borde simulado. |
| M-02 | **FAIL** | Reserva principal: estima 1270 para saldo 100 y hace cero llamadas. Despacho real multimodal: tracker ausente en worker, total declarado 40 frente a 1640 esperados. Con tracker explícito, saldo 200 inicia clasificación con entrada estimada 394 y registra 1600 después. | Falta propagar contexto de presupuesto al executor y reservar la entrada multimodal antes de llamar. La prueba directa del helper no demuestra integración. |

## A-02 — commit diferido real que cruza el deadline

Se reprodujo el mecanismo exacto de G2, introduciendo únicamente en la BD desechable un constraint trigger `AFTER UPDATE DEFERRABLE INITIALLY DEFERRED` que ejecuta `pg_sleep(0.18)` cuando la nota es el marcador sintético. La fila comienza con human_override_note=ORIGINAL. No se alteró el esquema de producción.

### conn.commit del proyecto

La herramienta utiliza get_conn, actualiza la fila y espera 0,15 s antes de commit. Límite de execute_tool_with_timeout: 0,25 s.

| Dato observado | Valor |
|---|---|
| Entrada a commit | 0,1965 s, antes del plazo |
| Tiempo hasta retorno de la herramienta | 0,3283 s |
| Excepción observada en trabajador/llamador | TimeoutError |
| Worker terminado al retornar | Sí |
| Valor leído mediante otra conexión tras esperar | **ORIGINAL** |

No apareció evento de commit exitoso. La cancelación activa abortó la transacción que antes persistía después del TIMEOUT. Se esperó adicionalmente para comprobar que el cambio no apareciera más tarde.

### checked_commit

Se repitió con el helper checked_commit y espera previa ajustada a 0,08 s para asegurar que el commit empezara dentro del plazo en este entorno. Entrada a commit **0,1307 s**, límite **0,25 s**, trigger diferido **0,18 s**: la finalización sin cancelar habría cruzado el deadline. Retorno a **0,3213 s**, TimeoutError, worker terminado y fila **ORIGINAL**.

Una primera repetición de checked_commit había llegado al helper después del deadline y fue rechazada antes de entrar. No se utilizó ese caso como demostración de cancelación dentro de commit; por eso se ejecutó la repetición anterior.

También se probó SQL lento `pg_sleep(1.0)` con límite 0,10 s: el trabajador terminó cancelado, QueryCanceled, retorno a 0,2541 s. No se infiere de esto un retorno estricto a 0,10 s.

**Código contrastado:** `backend/app/db.py:129-203` instala timers de cancelación y rollback; `agent.py:475-511` cancela conexiones registradas del worker y espera su finalización. PASS se limita a la garantía de no persistir la escritura tardía en estos contraejemplos reales, no a una promesa de exactitud temporal universal.

## M-03 — degradación corregida, deadline integral todavía parcial

### Timeout de 0,10 segundos y HTTP

Se inyectó un turno de modelo de 0,15 s, manteniendo ejecución y consultas reales del agente:

- `run_civia_agent(..., total_timeout_seconds=0.10)` ejecuta un turno y retorna respuesta honesta con guardrail TIMEOUT; no escapa TimeoutError.
- Para comprobar el endpoint con **deadline efectivo 0,10**, se fijó la cota del servidor AI_TIMEOUT_SECONDS=0.10 y se envió un valor HTTP válido 0.11. El mínimo aplicado por el agente es 0.10: resultado **HTTP 200**, guardrail TIMEOUT y mensaje de procesamiento no completado. No se abre SQL de respaldo con el plazo vencido.
- Una petición literal `total_timeout_seconds=0.10` recibe **422**, porque schemas.py conserva `gt=0.1`. No se contó ese rechazo de validación como éxito de ejecución ni se ocultó sustituyéndolo por 0.11 sin la cota efectiva anterior.

### Router: resultado fuera del plazo de 0,15

Se utilizó MockTransport en el adaptador real. La respuesta JSON válida llega tras 0,25 s, para un presupuesto de 0,15. El request recibió read timeout **0,149988... s**, sin el piso anterior de 0,5. Como MockTransport no impone por sí mismo los timeouts de sockets, el caso también prueba la verificación posterior al retorno.

Resultado a 0,4058 s: **contract=None, all_failed=true**. La respuesta tardía ya no se acepta como análisis exitoso. El tiempo adicional incluye registro de traza en PostgreSQL. No se presenta esta demora sintética como latencia real de proveedor.

### Bloqueo pendiente: worker no cooperativo

Se comprobó que una herramienta comenzara realmente antes de vencer el plazo. Para aislar el executor de los tiempos de persistencia de trazas, solo se sustituyó `_safe_record_trace`; la herramienta y el executor reales no se cambiaron. La herramienta activa un evento started y duerme 0,45 s, sin conexiones que cancelar.

Resultado: started=true, deadline **0,10 s**, duración **0,4564 s**, guardrail TIMEOUT. `executor.shutdown(wait=True)` espera el trabajo completo aunque no pueda cancelarlo. Una espera no acotada no constituye un límite temporal integral; una tarea que no retornara podría retener la solicitud indefinidamente. La corrección de A-02 no debe presentarse como interrupción universal de CPU, sleeps, librerías o I/O no cooperativos.

### Bloqueo pendiente: último manejador HTTP

Se inyectó TimeoutError en la frontera `main.run_civia_agent` para recorrer el handler final añadido por G2.1. Resultado **HTTP 500**. El log protegido identifica NameError y el código muestra su causa: `main.py:548` usa `uuid.uuid4()` pero el módulo solo importa `UUID`, no `uuid`.

Es una prueba específica del último manejo de errores; **no significa que el timeout normal anterior siga devolviendo 500**, pues ese recorrido dio 200. Pero el fallback defensivo prometido tampoco funciona cuando se necesita.

**Correcciones mínimas:** acotar/aislar herramientas no cooperativas con un protocolo de cancelación y persistencia seguro; no esperar indefinidamente al worker dentro de la petición; arreglar el handler de TimeoutError y alinear el límite HTTP si se pretende admitir literalmente 0,10. Mantener el rechazo de respuestas tardías y la degradación sin SQL vencido, que sí pasaron.

## M-06 — middleware Uvicorn con configuración efectiva

Se leyó el CMD del Dockerfile y se construyó `uvicorn.Config` con sus opciones reales, sin introducir la whitelist del test de Antigravity manualmente. En un entorno limpio, sin FORWARDED_ALLOW_IPS externo:

```text
CMD: uvicorn app.main:app --host 0.0.0.0 --port 8000
proxy_headers: true
forwarded_allow_ips: 127.0.0.1
TRUSTED_PROXIES: 127.0.0.1,::1,172.16.0.0/12,10.0.0.0/8
```

Eliminar las banderas no equivale a desactivar proxy_headers: Uvicorn mantiene el valor predeterminado anterior. Se ejecutó su ProxyHeadersMiddleware con esa configuración alrededor de la API real. Solo se sustituyó el cuerpo del agente por una respuesta sintética, sin IA. Cuota local: dos peticiones.

| Peer TCP sintético | Tres solicitudes sin XFF | Tres solicitudes variando XFF |
|---|---|---|
| Público 198.51.100.2 | 200 / 200 / 429 | **200 / 200 / 429** |
| Loopback 127.0.0.1 | 200 / 200 / 429 | **200 / 200 / 200** |
| Privado directo 10.20.30.40 | 200 / 200 / 429 | **200 / 200 / 200** |

En loopback, Uvicorn sustituye primero request.client y la comprobación posterior ya ve la IP falsa. En el peer privado, Uvicorn no lo sustituye, pero get_trusted_client_ip confía en la red 10.0.0.0/8 y acepta la cabecera. No se requirieron credenciales administrativas.

Con peer de proxy 172.18.0.2 y cabeceras fijadas como ahora hace Nginx (`X-Forwarded-For` y `X-Real-IP` sustituidos por la IP del cliente), las tres solicitudes dan **200/200/429**. La corrección en el borde es real y el ataque público original quedó bloqueado en ese recorrido. FAIL permanece por la entrada directa al backend, que Compose sigue publicando en loopback; no se afirma una evasión remota a través del Nginx endurecido.

**Corrección mínima:** distinguir entrada de proxy de entrada directa. Desactivar el parseo Uvicorn si la aplicación va a usar el peer original, o establecer una confianza única y estricta para el proxy real; no considerar cualquier cliente local o de rangos privados como proxy autorizado. Cerrar/restringir el bypass de backend si la garantía depende de pasar siempre por Nginx. Repetir la matriz pública, loopback y privada, no únicamente la fila pública.

## M-02 — reserva principal correcta, integración multimodal fallida

### Reserva del turno principal: PASS del subcontrol

Con query sintética y saldo **100**, `estimate_prompt_tokens` calcula **1270** para sistema, herramientas e historial. Se observaron **cero llamadas** al modelo, total_tokens_used=0 y MAX_TOKENS. Esto corrige el contraejemplo principal de G2.

### Contabilidad real a través del executor: FAIL

Se ejecutó el agente completo con presupuesto 6000 y herramienta real clasificar_evidencia. El primer turno pide esa herramienta; el segundo produce texto. Cada turno declara uso sintético 10 prompt + 10 completion. El adaptador multimodal declara **1500+100=1600** y la herramienta persiste la sugerencia mediante PostgreSQL real.

Se instrumentó la presencia del tracker **dentro del worker**, sin modificarlo:

| Dato | Observado |
|---|---|
| Turnos de agente | 2 |
| Clasificaciones multimodales | 1 |
| Tracker presente en el worker | **False** |
| Total esperado con esos usos declarados | **1640** |
| total_tokens_used devuelto | **40** |

`agent.py:475-493` propaga el deadline al nuevo hilo, pero no `_ACTIVE_TOKEN_TRACKER`. ThreadPoolExecutor no hereda ese ContextVar automáticamente en el entorno Python 3.13 probado. La prueba del proyecto llama al helper directamente con un tracker fijado en el mismo hilo: ese test puede pasar mientras el recorrido auténtico falla.

### Reserva de la entrada multimodal: FAIL incluso con tracker explícito

Se invocó la herramienta con tracker correctamente fijado, max_budget=200 y reporte real. Su prompt de clasificación requiere **394 tokens estimados con la misma heurística de caracteres/3 usada por el agente**, sin sumar imagen. Aun así se inició una llamada multimodal; la función solo comprueba saldo menor que 150.

Resultado: una llamada, análisis completado y tracker registra **1600** después, excediendo el presupuesto 200. Es uso sintético reportado, no consumo de una cuenta real. Demuestra la falta de reserva **previa** aun bajo la estimación que el propio proyecto adoptó.

**Corrección mínima:** propagar el contexto de presupuesto al executor mediante copia explícita de contexto o un argumento por ejecución; compartirlo de forma segura entre herramientas. Reservar antes de cada clasificación entrada/imagen/salida según el payload y el saldo, no un umbral fijo de 150. Registrar el uso solo después no evita iniciar llamadas cuyo costo estimado ya excede el presupuesto. Incluir pruebas del agente completo, no solo del helper directo.

## Suite de Antigravity y límites de sus resultados

Se intentó ejecutar únicamente `backend/tests/test_audit_g2_1_remediation.py`, sin editarlo, sobre test_g21_suite. Resultado: **8 passed y 1 fallo de preparación**, 10,26 s, un warning de deprecación AnyIO.

La prueba del commit diferido usa `_get_clean_test_db`, que ignora DATABASE_URL y abre una dirección Docker fija con host `db`. En este entorno ese nombre no resolvió, por lo que **no se estableció ninguna conexión a esa dirección ni a una BD habitual**. No se redirigió esa llamada a producción para hacer pasar el test. No se reproducen sus “9 PASSED” declarados.

En su lugar, A-02 se reprodujo independientemente en el clúster nuevo y con commit diferido real, como exige la tarea. Los ocho PASS de la suite tampoco invalidan las brechas independientes: el test de IP cubre peer público, y el de tracker llama al helper sin pasar por su hilo real.

El primer intento de un reproductor propio tuvo un error de preparación al usar un carácter `%` literal con parámetros SQL vacíos. Se corrigió exclusivamente el script temporal y se repitió; no se editó código del proyecto y no se presenta ese error como defecto del producto.

## Evidencia y cierre pendiente

En la raíz temporal indicada se conservaron `core_probe.py`, `core_results.json`, `checked_probe.py`, `checked_commit_result.json`, `proxy_probe.py`, `proxy_results.json`, `suite_runner.py` y logs con datos sintéticos. No se imprimieron ni guardaron claves reales.

Criterios pendientes para aceptar G2.1:

1. M-02: el agente completo debe devolver al menos el total de usos sintéticos propios + multimodales y no invocar clasificador con estimación de entrada superior al saldo.
2. M-06: el mismo peer directo no debe obtener más cuota variando XFF, incluidos loopback y privados contemplados por la configuración.
3. M-03: no debe quedar una espera no acotada del worker dentro del timeout global, y la ruta final de TimeoutError debe responder sin 500. Mantener los subcontroles ya aprobados de deadline y degradación.

El PASS de A-02 se conserva para el commit diferido probado. Los otros controles permanecen abiertos conforme a sus FAIL/PARCIAL. No se extiende esta auditoría a G1 ni al resto de G2.

## Cierre y huellas

Se detuvo correctamente PostgreSQL temporal al terminar, sin borrar evidencias ni tocar otros servidores. El repositorio original conserva HEAD 5b36fb55f87dc49e3256f9814cddb47e3cb3b800 y solo presenta este informe como archivo nuevo. No hubo cambios de producción ni publicaciones.

SHA256:

- head.zip: `031AC0D806CE5305E70FD1C326EC49284C1CB8D67C63029B9AA3C2DECCFBC55A`.
- core_results.json: `F0C68A9821EA1E0D8ABFD2B56A6DBEB0C1CBC0186B59D845D87B2589DB9C69C8`.
- checked_commit_result.json: `DE834CDE76736382C9D748EB105701B304FA5818F7666F4980240B0EC6FA5C67`.
- proxy_results.json: `5F28D180AF1E19C166D6E0731C1820D92852121C3286FDD2B253FFFBCC18F9F3`.
