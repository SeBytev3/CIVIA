# CIVIA — auditoría independiente del Bloque G2

Fecha: 2026-11-02, America/Bogota. Referencias: docs/auditoria_codex_final.md y docs/remediacion_g2.md.

**Commit exacto auditado:** `4774236ef9e54a97b8c0ffb64c7b84d8778857f4`, rama `fix/auditoria-final`. Incluye la implementación G2 `5367e87` y el ajuste de pruebas `4774236`. Base de comparación: G1.2 `b76e634690bf7b4bb36b2ada9a994833241d9795`.

## Dictamen

**G2 NO APROBADO: 7 FAIL, 2 PARCIAL y 1 PASS** en los diez hallazgos priorizados. Se comprobaron mejoras reales, pero una herramienta puede persistir una escritura después de TIMEOUT; el presupuesto de tokens sigue siendo superable; existen fugas ciudadanas, validación insuficiente de audio, admisión simultánea de sondas del circuit breaker y evasión de rate limit mediante las cabeceras que Uvicorn acepta.

La sustitución oculta de modelos sí quedó corregida en los recorridos HTTP simulados: el 429 primario pasó a Groq, y solo tras fallar Groq se intentó el Gemini terciario configurado. Cada llamada tuvo su fila de traza con proveedor/modelo coincidente.

Las suites G1/G2 del proyecto obtuvieron **37 passed**. Ese resultado no cierra los contraejemplos independientes de este informe. Las regresiones propias de autorización, idempotencia y aislamiento G1 no se reprodujeron en los recorridos ejecutados.

No se modificó producción, no se cambió de rama, no se crearon commits ni se publicó. Solo se añade este informe.

## Estado, aislamiento y límites

El árbol original estaba limpio. Se inspeccionó el diff contra b76e634 y se congeló HEAD con git archive en:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-g2-612196a25ee6412aba98a9ade41967b1\src`.

Se inicializó un clúster **PostgreSQL 17.6 real**, nuevo, escuchando solo en `127.0.0.1:55481`. Bases exclusivas: test_g2_independent, test_g2_core, test_g2_suite, test_g2_g1, eval_g2_independent y civia_prod_probe, más la base aleatoria creada por pytest al verificar aislamiento. La última también es desechable y pertenece al clúster nuevo, no es una BD habitual.

PGDATA, uploads y TEMP/TMP quedaron bajo la misma raíz temporal. Se reutilizaron CPython 3.13.18 y las dependencias directas exactas de requirements.txt, que no cambió. No se copió .env ni se utilizaron datos privados. Todas las claves reales estuvieron ausentes/vacías. Los adaptadores HTTP recibieron, cuando hizo falta, literales sintéticos únicamente con MockTransport; no se hicieron llamadas a proveedores externos. El runner de las suites añadió bloqueo de conexiones Python fuera de loopback. No hubo cargas masivas: solo solicitudes locales pequeñas y concurrencia de pocos hilos.

Docker no está disponible. No se ejecutó Compose ni Nginx real; la prueba de IP usó el middleware Uvicorn real con las mismas opciones de confianza del Dockerfile y cabeceras equivalentes a las que añade Nginx. No se verificaron acceso real, preflight, capacidades o tarifas de los modelos nombrados en la configuración.

## Matriz por hallazgo

Todas las filas corresponden al commit completo `4774236ef9e54a97b8c0ffb64c7b84d8778857f4`.

| Hallazgo | Estado | Evidencia independiente ejecutada | Bloqueo restante |
|---|---|---|---|
| A-02 | **FAIL** | Conexión/commit intentados tras vencimiento se bloquean. Pero un commit iniciado a 0,1978 s cruza el plazo de 0,25 s y termina a 0,4034 s: herramienta ya había devuelto TIMEOUT a 0,2526 s; la fila cambia después. | La comprobación previa a commit no protege la fase de commit ni resuelve el resultado del worker antes de declarar timeout. |
| M-02 | **FAIL** | Cap servidor de cinco vueltas y presupuesto 50 sin llamada funcionan. Presupuesto 100 consume 1020 antes de MAX_TOKENS; herramienta multimodal consume otros 1600 mientras el agente declara solo 40 de su presupuesto 200. | Reserva fija de entrada y ausencia de contabilidad de IA anidada; tope posterior al gasto. |
| M-03 | **FAIL** | Agente con límite 0,10 s lanza TimeoutError al volver al SQL de respaldo; endpoint con límite 0,11 s devuelve 500. Router con plazo 0,15 s configura lectura de 0,5 s y acepta contrato a 0,3061 s. | Fallback usa contexto vencido; floor de timeout y falta de comprobación posterior permiten exceder deadline. |
| A-03 | **PARCIAL** | `{}`, enums desconocidos, confianza ausente/negativa/booleana/ilegible se rechazan; válido conserva 0,9. Resumen de diez puntos se acepta como análisis válido. | Contrato estructural mejorado, pero la condición declarada de resumen sustantivo no se exige. No se fabricó confianza en los casos probados. |
| A-04 | **FAIL** | Transcript/summary técnicos se redactan. Clasificación→persistencia→respuesta 201 deja intacto `Google API HTTP 401 user@example.org` dentro de ai_keywords. Agent/query 200 también lo devuelve en argumentos/resultados de tools_invoked. | DTO público incompleto; sanitización no aplicada a todas las estructuras/canales. |
| A-05 | **PARCIAL** | Durante clasificador síncrono sintético de 0,30 s, heartbeat de 0,02 s tarda 0,0275 s y el alta real devuelve 201. | Offload comprobado; persisten lectura completa previa al rechazo, ausencia de cuota global/disco y rate limit eludible por M-06. No se midió capacidad bajo carga. |
| M-01 | **FAIL** | ID3 corto falso se rechaza. OGG/WEBM de firma+relleno, MP3 falso con dos bytes de sincronización y WAV truncado de 44 bytes se aceptan y almacenan con duración inventada/derivada de cabecera. | Sin parseo/decodificación suficiente ni duración real para formatos comprimidos; WAV no comprueba muestras existentes. |
| M-04 | **FAIL** | Circuito aislado admite una de seis llamadas. Dos workers usando el preflight del router son admitidos a la vez sobre el mismo circuito sin terminar el primero. | El helper vuelve a poner HALF_OPEN y borra la bandera in-flight de una sonda activa. |
| M-06 | **FAIL** | Función aislada ignora XFF desde peer público. Con middleware `trusted_hosts='*'`, ese mismo peer se convierte en la IP falsa. Cuota dos: sin XFF 200/200/429; variando XFF 200/200/200. | Uvicorn modifica request.client antes de la comprobación del endpoint; confianza universal y cadena Nginx manipulable. |
| N-02 | **PASS** | Transporte HTTP real de los adaptadores, simulado: Gemini primario 429→Groq 200; si Groq 400→Gemini terciario. Filas SQL de traza coinciden con cada llamada y modelo. También se comprobó agente y JSON inválido primario. | Disponibilidad real de modelos no verificada, por prohibición de usar claves reales. No se observó sustitución oculta. |

## A-02 — escritura real posterior a TIMEOUT

No se aceptó como prueba suficiente que execute_tool_with_timeout lance TimeoutError o que un MagicMock reciba rollback. Se consultó PostgreSQL desde otra conexión después de que el trabajador terminara.

### Casos que sí se protegen

- Herramienta duerme antes de abrir conexión, límite 0,05 s: retorna por timeout a 0,0617 s; al intentar conectar después recibe TimeoutError; no escribe.
- Herramienta abre conexión y actualiza dentro de la transacción, pero duerme antes de commit: retorna a 0,0645 s; commit tardío genera TimeoutError y rollback; no persiste la nota.

Estas mejoras de db.get_conn y contextvars son reales.

### Contraejemplo de la fase de commit

Se creó únicamente en la BD desechable un constraint trigger `AFTER UPDATE DEFERRABLE INITIALLY DEFERRED`. Al ver una nota sintética específica ejecuta `pg_sleep(0.18)` durante commit. Así se reproduce demora de esa fase sin ralentizar artificialmente la comprobación del cliente ni simular SQL.

La herramienta utilizó **get_conn y conn.commit del proyecto**, bajo execute_tool_with_timeout:

1. Límite: 0,25 s.
2. UPDATE sobre un reporte sintético y espera de 0,15 s antes de commit.
3. Entrada a commit observada: 0,1978 s, todavía dentro del plazo.
4. La petición de herramienta retornó TIMEOUT: 0,2526 s. Otra conexión aún ve nota null.
5. Commit terminó: 0,4034 s. Después, otra conexión ve `DEFERRED LATE COMMIT` persistido.

La demora del trigger es una condición de prueba introducida en el clúster aislado, **no se afirma que el esquema de producción contenga ese trigger**. Demuestra que la garantía temporal implementada no cubre un commit que cruza el plazo: esperar por red/servidor/I/O no equivale a ejecutar otra comprobación del reloj dentro del wrapper Python.

Ubicación: `backend/app/db.py:94-135`, `backend/app/agent.py:397-426`. statement_timeout se fija con el saldo al abrir conexión y aplica por sentencia, no como deadline absoluto de la transacción. El saldo no se reajusta para commit. El wrapper verifica antes de llamar orig_commit, mientras `shutdown(wait=False)` permite continuar al trabajador.

Corrección prioritaria: propagar el saldo hasta las últimas operaciones SQL/commit y definir cancelación y resolución del resultado transaccional. No declarar abortada una escritura si el trabajador todavía puede confirmarla. Una comprobación Python previa no acredita la afirmación de “cero escrituras huérfanas”. Si el resultado es incierto, debe reconciliarse antes de afirmar que no se aplicó. Cualquier aislamiento del worker debe proteger también su protocolo de persistencia, no solo terminar un hilo.

## M-02 — tokens: cotas reales y brechas restantes

`agent.py:770-771` sí aplica el mínimo entre máximo solicitado y configuración: solicitar 99 vueltas terminó con cap cinco. Con presupuesto 50 no se invocó modelo y se activó MAX_TOKENS.

Pero `agent.py:799-829` reserva una constante de **60 tokens** para una entrada que contiene sistema, herramientas e historial. En un turno sintético que reporta 1000 de entrada y 20 de salida, presupuesto 100 produce uso 1020; max_output_tokens=40 no limita la entrada. El límite vuelve a actuar después del gasto. El uso fue sintético declarado por el transporte/turno de prueba: **no es costo ni consumo real de una cuenta**.

En otra ejecución, con presupuesto 200:

- Dos turnos del agente: 10+10 cada uno; el agente y sus trazas declaran 40.
- La herramienta real clasificar_evidencia ejecuta clasificación multimodal, persiste sugerencia en PostgreSQL y recibe uso sintético **1500+100=1600**.
- El presupuesto y total_tokens_used del agente no incluyen esos 1600.

Ubicación: `agent.py:278-312,799-857`; el router interno genera otro trace_group_id y no comparte presupuesto. Se necesita contabilidad compartida por ejecución, reserva de entrada fundada en el payload y límite de salida según el saldo, incluyendo reintentos/errores y herramientas IA. Un token usage ausente no puede interpretarse silenciosamente como gasto cero garantizado.

## M-03 — deadlines y fallback

Un turno sintético tarda 0,15 s con límite de agente 0,10 s. El agente detecta vencimiento, pero llama a `_deterministic_sql_fallback_answer` sin historia; ese fallback intenta SQL con el contexto ya vencido. Resultado real: **TimeoutError no manejado**, 0,1517 s, en vez de respuesta degradada. Al ejecutar `/api/agent/query` con límite permitido 0,11 s, devuelve **HTTP 500** con mensaje genérico. El manejador evita filtrar el error técnico, pero no cumple la degradación prometida.

Ubicación: `agent.py:939-945,1052-1069`, `db.py:106-112`. Debe poder terminar con respuesta honesta sin iniciar más trabajo de BD fuera del plazo; no resolverlo extendiendo silenciosamente el límite.

El router tiene otra brecha: `ai_router.py:606-610` impone mínimo de **0,5 s** por llamada aunque el saldo sea menor. Se configuró límite global 0,15 s y un MockTransport que responde después de 0,25 s. El request llevó read timeout 0,5 s, por lo que la demora simulada estaba dentro del timeout que el propio adaptador autorizaba. El router devolvió contrato válido a **0,3061 s**. No comprueba vencimiento antes de aceptar ese resultado. No es una medición de latencia de proveedor externo.

Se requiere deadline compartido y comprobación antes/después de red y herramientas, sin floors mayores al saldo; backoff/trazas/fallback deben consumir el mismo plazo. El cliente todavía puede solicitar total_timeout_seconds de hasta 30 frente a default servidor 15: se observó por lectura que eff_total_timeout no toma el mínimo con configuración, aunque las vueltas/tokens sí lo hacen.

## A-03 — contrato JSON

Se ejecutó el parser real con:

- `{}` → INVALID_SCHEMA.
- Categoría NUCLEAR o severidad INVENTADA → INVALID_SCHEMA.
- Confianza ausente, negativa, booleana o texto ilegible → INVALID_SCHEMA.
- Contrato válido → conserva confianza 0,9 y resumen, sin rellenar datos.

La mejora frente a la auditoría final está comprobada: los campos críticos ya no se inventan. En transporte, JSON sintácticamente inválido del primario también provoca fallback y traza correspondiente.

Queda un control parcial respecto de la semántica declarada: sustituyendo summary por diez puntos (`..........`), manteniendo los otros campos, el parser devuelve contrato válido. `ai_router.py:317-325` solo revisa tipo y longitud tras strip, no contenido sustantivo. No se sostiene que un validador determinista pueda comprobar toda interpretación visual; sí debe distinguir esta respuesta sin descripción útil antes de señalar análisis válido. Rechazar relleno evidente y añadir esos negativos es el mínimo pendiente. La normalización de porcentajes de confianza está documentada en la remediación; no se la presenta aquí como confianza inventada.

## A-04 — canales públicos incompletamente protegidos

La cadena sintética `Google API HTTP 401 ValueError user@example.org` se redacta correctamente en audio_transcript y ai_summary públicos. Sin embargo:

1. Se entregó al adaptador un contrato permitido con keyword `Google API HTTP 401 user@example.org`. POST normal con auto_analyze=true recorrió clasificación, commit y serialización reales. Resultado **201**, keyword íntegro en la respuesta pública.
2. Un turno simulado pidió obtener_reporte con identificador que contiene esa misma cadena. Se ejecutó la herramienta real de búsqueda y la API devolvió **200**. La respuesta answer estaba filtrada, pero `tools_invoked[].args.identificador` y `result.identificador_buscado` la conservaron íntegra.

Todos los contactos de prueba son sintéticos. No se afirma que un proveedor real haya filtrado el contenido: se acredita que el servidor deja pasar un resultado de modelo permitido por el contrato y sus estructuras auxiliares.

Ubicación: `repository.py:59-66,94`; `agent.py:926,970,1057`; main devuelve tools_invoked sin DTO restringido. Aplicar una regex solo al texto principal no protege listas/dicts. Se requiere esquema público explícito y minimización en todos los campos/recorridos, sin publicar argumentos y resultados técnicos completos.

## A-05 — event loop corregido, control agregado incompleto

Se hizo POST real con PNG sintético y PostgreSQL, sustituyendo solo la clasificación por una función síncrona que duerme 0,30 s. En el mismo event loop se programó un heartbeat de 0,02 s: terminó a **0,0275 s**, mientras la petición finalizó **201**. Esto contrasta con la congelación anterior y verifica run_in_threadpool en el recorrido importante.

No se cierra todo A-05. Por lectura: main.py:201-204 sigue leyendo completos los archivos antes de validarlos; el limitador actúa después del parseo multipart; no se implementó cuota global de IA/disco ni cola/semaforización global propia, y el rate limit se puede eludir como se probó en M-06. El límite Nginx no protege una entrada directa al backend. No se realizaron cargas masivas ni se inventan métricas de capacidad. El offload es una corrección real, no prueba por sí mismo de resistencia al agotamiento agregado.

## M-01 — audio inválido aceptado

| Archivo sintético | Resultado real |
|---|---|
| ID3 versión 4 + relleno corto, caso previo | Rechazado 415. |
| `OggS` + ceros hasta 1024 bytes | Aceptado y guardado, duración 0,1 s. |
| Firma EBML/WEBM + ceros hasta 1024 bytes | Aceptado y guardado, duración 0,1 s. |
| `0xFF 0xFB` + ceros hasta 1024 bytes, sin tramas MP3 completas | Aceptado y guardado, duración 0,1 s. |
| WAV de 44 bytes: cabecera declara 16000 bytes de muestras, no incluye ninguna | Aceptado y guardado, duración declarada 1,0 s. |

Ubicación: security.py:226-270 busca solo un patrón de sincronía MP3, no recorre/valida tramas completas; :315-320 estima comprimidos por tamaño. Para WAV, :300-310 consulta getnframes de la cabecera sin verificar que las muestras existan. Fijar prefijos/tamaños mínimos no prueba audio reproducible ni duración. Se necesita inspección/decodificación real acotada y verificar bytes/muestras y duración para cada formato aceptado.

## M-04 — concurrencia del circuit breaker

Prueba positiva: seis hilos sincronizados sobre un CircuitBreakerState OPEN cuyo cooldown venció; solo **uno** obtiene permiso. El candado de allow_request funciona.

Prueba de integración con el preflight real del router:

1. Tres circuitos OPEN, sin permiso de intento aún.
2. Primer worker llama ensure_at_least_one_circuit_openable, obtiene permiso del circuito más antiguo y mantiene la sonda en vuelo, sin comunicar éxito/fallo.
3. Segundo worker, mientras el primero sigue en vuelo, vuelve a llamar ese helper y pide permiso.
4. **Ambos son admitidos** sobre el mismo circuito.

El helper (`ai_router.py:161-173`) fuerza HALF_OPEN y `_half_open_in_flight=False` incluso si el circuito seleccionado ya tiene una sonda activa. Además permite saltar cooldown cuando todos están abiertos. Debe reservar atómicamente una sola sonda y no resetear la propiedad del ensayo de otro worker. La suite probó el objeto aislado, no este recorrido que lo invalida.

## M-06 — IP efectiva detrás del middleware

Se usó Uvicorn ProxyHeadersMiddleware real con `trusted_hosts='*'`, equivalente a `--proxy-headers --forwarded-allow-ips=*` del Dockerfile. Peer sintético público: 198.51.100.2.

| Recorrido | IP observada por endpoint |
|---|---|
| Función get_trusted_client_ip sin middleware, XFF falso 203.0.113.99 | 198.51.100.2: correcto. |
| Con middleware configurado como Docker, mismo XFF falso | **203.0.113.99**. |
| Cadena que Nginx añadiría: `203.0.113.99, 198.51.100.2` | **203.0.113.99**. |

No basta el test unitario de get_trusted_client_ip: Uvicorn ya sustituyó request.client antes de que la función compruebe confianza. Para acreditar impacto se fijó cuota local en dos y se sustituyó únicamente el agente por respuesta sintética sin IA:

- Mismo peer, tres peticiones sin XFF: **200 / 200 / 429**.
- Mismo peer, variando XFF en tres direcciones: **200 / 200 / 200**.

No se probó Nginx en contenedor ni un despliegue público. Se verificó el middleware efectivo y la evasión con la configuración que el Dockerfile entrega. La publicación loopback limita exposición remota directa, pero no corrige el contrato de confianza de una entrada a través del proxy.

Corrección: whitelist del proxy real, no wildcard; fijar/sanear cabeceras en el borde, delimitar correctamente la cadena de confianza y evitar reinterpretar una identidad ya sustituida sin conocer el peer TCP original. Confiar en todas las redes privadas tampoco identifica inequívocamente al proxy.

## N-02 — orden de proveedores y trazas

Se empleó httpx.MockTransport en los **adaptadores reales**, no FALLA_FORZADA antes de red ni solo una prueba de resolve_effective_gemini_model. Cada request registró proveedor/modelo solicitado; las trazas se leyeron realmente de PostgreSQL.

| Caso | Orden de requests | Trazas verificadas |
|---|---|---|
| Clasificación: primario 429, Groq 200 | google:gemini-3.8-flash → groq:qwen/qwen3.8-27b | Dos filas: HTTP_429 y éxito, mismos modelos. |
| Primario 429, Groq 400, terciario 200 | google:gemini-3.8-flash → groq:qwen/qwen3.8-27b → google:gemini-3.5-flash-lite | Tres filas, un intento por llamada, modelos coincidentes. |
| JSON inválido primario, Groq 200 | Google primario → Groq | Dos filas, INVALID_JSON y éxito. |
| Turno de agente: primario 429, Groq 200 | Google primario → Groq | Dos filas, HTTP_429 y éxito, modelos coincidentes. |

No apareció otro Gemini antes de Groq. En el agente attempt_number sigue representando la vuelta (ambas filas tienen 1), no un número global de llamada; se conserva una fila por intento efectivo. No se afirma haber validado acceso real al modelo terciario ni sus capacidades: las respuestas fueron sintéticas y no se usaron claves reales.

## Regresiones G1

Además de la suite oficial, se reejecutaron reproductores independientes adaptando solo rutas/puerto de auditoría:

- Autorización: status anónimo 401; confirm sin token/incorrecto/ajeno 403; replay público crea otro UUID y no recupera la capacidad original; edición posterior a gestión administrativa 409.
- Idempotencia: misma clave secuencial/concurrente, una fila y un UUID; modificación de descripción/comuna/dirección 409; fallo de trazas, 201 y una fila.
- Aprobaciones G1: nuevas/heredadas obsoletas rechazadas, carrera consistente.
- Archivos G1: fallo SQL/audio/replay y escritura parcial dejan cero archivos nuevos.
- Aislamiento: pytest real sobre configuración ficticia no-test se redirige; centinelas fuente intactos. Escritor externo en otro proceso crea reporte/aprobación y cambia demo a IN_REVIEW/versión 2: ambos registros y estado sobreviven. Modo estricto rechaza fuente con exit 4.
- Evaluación Q13 limitada al recorrido de limpieza: conserva registros externos y elimina únicamente aprobación propia. Usa respaldo SQL, no inferencia real; su PASS de contenido no es una evaluación de modelos G2.

**Sin regresiones observadas en esos controles G1.** El fallo temporal de A-02 es una condición G2 distinta de la validación de versión/propiedad G1.

## Ejecuciones del proyecto y límites de su evidencia

Runner independiente con conectividad Python externa bloqueada y BD desechable:

`pytest backend/tests/test_audit_g1_security.py backend/tests/test_audit_g2_resilience.py -q --tb=short`

Resultado final: **37 passed**, un warning AnyIO, **8,46 s** (14 G1 y 23 G2). El primer intento del runner omitió src del path e hizo fallar la importación eval.evaluar: 36 passed/1 failed. Se corrigió exclusivamente el script temporal de auditoría y se repitió; no se presenta ese fallo del ejecutor como regresión del producto.

Las pruebas declaradas de A-02 se limitan a un mock de checked_commit y una herramienta que duerme y lanza timeout; no comprueban persistencia tardía real. Las de circuit breaker verifican el objeto sin el helper que reinicia su estado. La de IP verifica la función sin el middleware que cambia el peer. Por ello su aprobación no contradice los resultados adversariales.

No se ejecutó la suite completa dependiente de proveedores, no se reproducen los “57 passed” de la remediación y no se inventan métricas reales de tokens/costo/latencia de red.

## Prioridad de correcciones y aceptación

1. Resolver el resultado de las escrituras al vencer timeout y proteger la fase transaccional completa; repetir commit que cruza el deadline, no solo commit iniciado tarde.
2. Quitar confianza universal de Uvicorn y demostrar que el mismo peer no cambia su cuota mediante XFF.
3. Cerrar ai_keywords/tools_invoked y los demás canales de salida mediante DTO público y minimización uniforme.
4. Compartir presupuesto real de tokens/deadline entre agente, herramientas, router, reintentos y trazas; terminar sin SQL adicional si venció el plazo; eliminar floors mayores al saldo.
5. Corregir reserva half-open integrada y validar audio/contenedores/duración de forma real y acotada.
6. Completar negativos semánticos del contrato y límites agregados de recursos.

G2 no debe declararse aprobado hasta repetir estos contraejemplos con resultado seguro. No se recomienda inferirlo del número de pruebas aprobadas.

## Reproductores y evidencias

En la raíz temporal indicada: probe_core_final.py/core_observations.json; probe_transport.py/transport_observations.json; probe_additional.py/additional_observations.json; g1_regression.py/g1_observations.json; g1_sentinel_regression.py/sentinel_observations.json; suite_runner.py. Los scripts contienen datos sintéticos y no claves reales.

La prueba core se repitió en una base nueva para conservar sus resultados separados de los de G1; el informe usa las duraciones de esa ejecución final. Las duraciones pueden variar. Las fuentes archivadas y SQL/archivos de evidencia quedaron para inspección; no se garantiza permanencia futura del directorio temporal. Este informe conserva procedimiento, condiciones y resultados sin confundir ejecución real de PostgreSQL con respuestas sintéticas de IA.

## Cierre y huellas

Se detuvo correctamente PostgreSQL temporal al finalizar. No se borraron archivos de evidencia ni se tocaron otros servidores/volúmenes. HEAD original permaneció en 4774236ef9e54a97b8c0ffb64c7b84d8778857f4; git status solo muestra este informe nuevo. No se publicaron commits.

SHA256:

- head.zip: `0FCF2CADDEE7419129C882C51297A89A0738287F1B8DE82D70E8D523E7C5E1F7`.
- core_observations.json: `6A735852349CE39F3056CFEF5733AB5B505E3F25A67478D6CF974067B2A3EB09`.
- transport_observations.json: `7818D023530ED76F080F378F57B24C219B82AAF96101BAFC57628996991FBFDD`.
- additional_observations.json: `95BA2BDA34792820AABB5B30FE0A215D964B4091289EC38193DE8BD19D6517EF`.
- g1_observations.json: `43694D4ED44910E1E9B545F1EEB13B11EAC58946E617C42CBE65AF27206D76B8`.
- sentinel_observations.json: `64B800762EAF066DC596A40CA1120695C26E2F6832C5216A6259FB6DDA2BDFFB`.
