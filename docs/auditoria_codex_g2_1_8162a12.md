# CIVIA — reauditoría independiente de G2.1, commit 8162a12

Fecha: 2026-11-02, America/Bogota.

**Versión exacta:** `8162a12f8e278fa58e65db7d6ad06c124948ce4a`, rama `fix/auditoria-final`. Referencias leídas: `docs/auditoria_codex_g2_1.md`, `docs/remediacion_g2_1.md` y `docs/estado.md`. Comparación de los módulos pertinentes contra `5b36fb55f87dc49e3256f9814cddb47e3cb3b800`.

**Dictamen: G2.1 NO APROBADO.** M-03 queda PARCIAL; M-06 y M-02, FAIL. A-02, N-02 y los contraejemplos G1 repetidos pasan. Las correcciones de propagación del tracker, literal HTTP 0,10, handler final y desacoplamiento del worker funcionan, pero no cumplen todas las garantías solicitadas.

## Matriz por hallazgo

Todos los resultados corresponden al SHA completo anterior.

| Control | Dictamen | Evidencia ejecutada | Pendiente |
|---|---|---|---|
| M-03 | **PARCIAL** | Worker iniciado de 0,45 s: agente retorna TIMEOUT a 0,1078 s con límite 0,10. Literal HTTP 0,10 y handler final: 200. Router rechaza respuesta posterior a 0,15. | Worker superviviente escribe mediante el helper real de archivos tras el TIMEOUT. Una conexión retenida ejecuta SQL después del deadline. La cancelación PostgreSQL síncrona también puede retrasar el retorno. |
| M-06 | **FAIL** | Docker desactiva proxy_headers. Público, loopback y 10/8: 200/200/429. Nginx saneado y dos clientes distintos: cuotas separadas correctas. | Peer directo 172.19.0.9, que NO es Nginx: XFF variable da **200/200/200**. Se sigue confiando en toda 172.16/12. |
| M-02 | **FAIL** | Agente completo, executor y clasificador reales: tracker presente, total **1640**. Saldo 200 bloquea entrada estimada 394, cero llamadas. | Concurrencia: dos llamadas consumen 1400 con presupuesto 1000. JSON inválido + fallback reporta 800 en vez de 1400. Errores del agente con consumo desconocido se reportan como cero no estimado. Reintentos no reservan saldo. |
| A-02, regresión obligatoria | **PASS, alcance reproducido** | PostgreSQL 17.6, trigger diferido de 0,18 s, commits iniciados dentro del deadline de 0,25 s: rollback; otra conexión conserva ORIGINAL después del TIMEOUT y de terminar el worker. | No equivale a prohibir todo SQL tardío ni a interrumpir cualquier efecto externo; esas brechas permanecen en M-03. |
| N-02, regresión | **PASS, transporte simulado** | Primario 429 → Groq; Groq 400 → Gemini terciario. Adaptadores HTTP reales y trazas SQL coinciden con cada intento/modelo. | No se prueba disponibilidad ni inferencia real de proveedores. |
| G1, regresión | **PASS en controles repetidos** | Autorización, replay público, idempotencia concurrente, trazas fallidas, propuestas obsoletas/ABA/concurrentes, archivos parciales y centinelas de pytest/evaluación. Suite G1: 14 PASS. | No se extiende el dictamen al resto de funcionalidades del producto. |

## Entorno y método

El árbol original estaba limpio y HEAD coincidía con el SHA solicitado. Se congeló el commit mediante `git archive 8162a12` y se importó exclusivamente esa copia, sin checkout sobre la rama del usuario.

Raíz de evidencia:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-8162-888e669b6c4a495f890b109cd7ee94e9`

Contiene `head.zip`, `src`, scripts independientes y resultados JSON. Se creó un clúster **PostgreSQL 17.6 real**, PGDATA nuevo en esa raíz, escuchando solo en `127.0.0.1:55485`. Bases nuevas: `test_8162_independent`, `test_8162_suite`, `test_8162_g1`, `civia_8162_probe` y `eval_8162_independent`; las suites crearon además bases temporales propias en el mismo clúster. `civia_8162_probe` es un nombre sintético deliberadamente no desechable para probar el rechazo/aislamiento automático, nunca la base habitual. Uploads y TEMP/TMP quedaron bajo la raíz de auditoría.

Se reutilizaron los binarios PostgreSQL portables y CPython 3.13.18 con las dependencias del backend de las auditorías anteriores. No se copió `.env`; las tres claves IA se fijaron vacías. Los adaptadores instrumentados recibieron únicamente marcadores sintéticos con HTTP MockTransport o funciones simuladas. No hubo llamadas a proveedores reales. Tokens, respuestas y datos de ciudadanos son sintéticos. Los administradores de pruebas se generaron con CSPRNG sin imprimirlos.

Docker/Nginx no se ejecutaron. Se extrajo el CMD real del Dockerfile, se construyó la configuración efectiva de Uvicorn y se probó la aplicación ASGI con peers inyectados. Se ejecutó la selección real de middleware: **proxy_headers=False**, por lo que no se instala ProxyHeadersMiddleware; no se rodeó la aplicación con opciones más permisivas ni más estrictas que las del Dockerfile. Las cabeceras del recorrido Nginx reproducen la sobrescritura de `frontend/nginx.conf:14-15`. Esto demuestra la decisión de confianza de la aplicación y sus cuotas, no una prueba de red con contenedores desplegados.

No se leyó ni ejecutó CIVIA Autopilot. No se modificó producción, no hubo commits, push, merge ni cambio de rama. Este informe conserva el documento anterior como evidencia histórica.

## M-03 — respuesta oportuna, efectos tardíos todavía posibles

### Subcontroles corregidos

`proxy_probe.py` ejecuta el agente completo con una herramienta incorporada temporalmente a TOOL_DISPATCH. El turno de proveedor simulado solicita esa herramienta; esta activa un evento y duerme 0,45 s. Solo se sustituye `_safe_record_trace` para que la latencia SQL de observabilidad no impida iniciar el worker dentro de los 0,10 s.

- Worker realmente iniciado: true.
- Retorno del agente: **0,1151 s**, guardrail TIMEOUT. En la repetición con efectos tardíos: **0,1078 s**.
- La herramienta sigue ejecutándose después de recibir la respuesta; `shutdown(wait=False, cancel_futures=True)` no cancela un future ya iniciado.
- Petición literal `total_timeout_seconds=0.10`: **HTTP 200**, ya no 422.
- Ruta final: inyección de TimeoutError en `main.run_civia_agent` devuelve **HTTP 200**, guardrail TIMEOUT y UUID válido; el import de uuid corrige el 500 previo.
- Router real con HTTP MockTransport: JSON válido después de dormir 0,25 s para plazo 0,15; read timeout ≈0,14999 s, **contract=None, all_failed=True**, retorno observado 0,2975 s incluyendo trazas. El transporte simulado no impone los timeouts de sockets: esta prueba demuestra especialmente el rechazo posterior al retorno, no una garantía de interrupción del transporte.

Referencias: `backend/app/agent.py:494-529`, `backend/app/main.py` (import uuid y handler final), `backend/app/schemas.py:107`, `backend/app/ai_router.py:655-663`.

### Contraejemplo: worker superviviente y almacenamiento real

En `adversarial.py`, la herramienta duerme 0,45 s; al despertar intenta dos efectos:

```python
with db.get_conn() as conn:
    conn.execute("UPDATE reports SET human_override_note='LATE' WHERE id=%s", (rid,))
    conn.commit()
security._atomic_write_bytes(upload_dir, "late_side_effect.txt", b"SYNTHETIC AFTER DEADLINE")
```

La excepción de la primera operación se captura dentro del reproductor para poder comprobar la segunda. Resultado tras esperar al worker:

- Abrir nueva conexión: **TimeoutError**, como corresponde; nota SQL sigue ORIGINAL.
- Helper de almacenamiento real `security._atomic_write_bytes`: **crea el archivo después del TIMEOUT**.

No se presenta la herramienta añadida como un endpoint ciudadano nuevo ni como explotación de una herramienta inexistente en producción. Sí demuestra que el executor y los helpers compartidos **no garantizan** que un worker superviviente carezca de efectos posteriores: el desacoplamiento por sí solo no es aislamiento. La prueba utiliza el escritor de archivos del producto, sin parchearlo.

### Contraejemplo: conexión retenida ejecuta SQL vencido

Otra herramienta obtiene `db.get_conn()` antes del deadline, duerme 0,45 s y luego ejecuta `SELECT 8675309 AS marker`. La cancelación al vencer ocurre mientras la conexión está ociosa. Observado:

- Retorno del llamador: **0,1712 s**, TimeoutError.
- Después del deadline, **SELECT devuelve 8675309**.
- El posterior commit sí lanza TimeoutError.

`conn.cancel()` no invalida permanentemente la conexión; `statement_timeout` limita cada sentencia, no el instante de inicio de la siguiente. Por tanto la afirmación de remediación «conexiones [...] invalidadas» no se sostiene y no pasa la condición explícita de ausencia de SQL posterior al deadline. Esta prueba no demuestra un commit transaccional tardío: A-02 se conserva por separado.

Además, las cancelaciones síncronas en `agent.py:524,528` pueden demorar el retorno: los casos de commit diferido devolvieron TimeoutError a **0,5734 s** y **0,4093 s** para deadline 0,25. No hay garantía general de retorno estricto aunque el sleep sin BD ya responda oportunamente.

**Cambio mínimo necesario:** mantener las barreras de commit y añadir revocación por ejecución en cada frontera de efectos: sentencias sobre conexiones retenidas, persistencia y publicación de archivos. Preparar archivos en staging y promoverlos solo si el deadline/capacidad siguen vigentes. El cierre/cancelación no debe bloquear indefinidamente la respuesta. Si se pretende garantizarlo para código no cooperativo arbitrario, ejecutarlo en aislamiento terminable y dejar la autorización de efectos en el proceso supervisor; un hilo desacoplado no ofrece esa garantía.

## A-02 — commit diferido PostgreSQL real

`core_probe.py` creó un constraint trigger `AFTER UPDATE DEFERRABLE INITIALLY DEFERRED` sobre una fila sintética de reports. Cuando la nota es el marcador de auditoría, ejecuta `pg_sleep(0.18)`. La herramienta actualiza la fila, duerme 0,08 s y entra a commit, con límite total 0,25 s.

| Método | Entrada a commit | Retorno | Resultado leído desde otra conexión |
|---|---:|---:|---|
| `conn.commit()` envuelto por get_conn | 0,1308 s | 0,5734 s | ORIGINAL |
| `db.checked_commit(conn)` | 0,1367 s | 0,4093 s | ORIGINAL |

En ambos casos el commit **empieza antes** del deadline y su trigger lo cruza; no se confundió el rechazo de un commit iniciado tarde con la cancelación durante commit. Worker terminado, TimeoutError, sin evento de commit exitoso. Se esperó adicionalmente 0,20 s y se leyó mediante una conexión nueva: no apareció la escritura tardía. PostgreSQL, trigger, rollback y consultas son reales.

`db.py:129-203` no cambió frente al commit de referencia. El PASS se limita a esta garantía reproducida de persistencia transaccional. No convierte el paquete de cancelación en revocación permanente de conexiones ni cubre archivos externos.

## M-06 — confianza de proxy todavía excesiva

Configuración efectiva examinada y aplicada:

```text
Docker CMD: uvicorn app.main:app --host 0.0.0.0 --port 8000
            --no-proxy-headers --forwarded-allow-ips ""
proxy_headers=False; forwarded_allow_ips=""
TRUSTED_PROXIES=172.16.0.0/12
```

Cuota dos solicitudes; API real y rate limiter real, únicamente cuerpo del agente sustituido por una respuesta sintética. Se reinicia la cuota entre escenarios.

| Peer | Sin cabeceras | X-Forwarded-For variable |
|---|---|---|
| Público 198.51.100.2 | 200/200/429 | **200/200/429** |
| Loopback 127.0.0.1 | 200/200/429 | **200/200/429** |
| Directo privado 10.20.30.40 | 200/200/429 | **200/200/429** |
| Directo 172.19.0.9, NO Nginx | 200/200/429 | **200/200/200** |
| Nginx 172.18.0.2, XFF y X-Real-IP saneados y constantes | — | **200/200/429** |

Ataque: desde el mismo peer 172.19.0.9 enviar sucesivamente XFF 203.0.113.1, .2 y .3. No hacen falta credenciales. `security.get_trusted_client_ip` acepta cada IP porque el peer pertenece al /12 predeterminado. El CMD endurecido no corrige la confianza posterior en la aplicación.

Dos clientes legítimos distintos detrás de Nginx, 198.51.100.10 y .11, ambos con cabeceras saneadas coherentes: cada uno obtuvo **200/200/429**, sin compartir cuota. Este subcontrol pasa.

Referencias: `backend/app/config.py:38`, `docker-compose.yml:32`, `backend/app/security.py:341-395`, `backend/Dockerfile:12`. No se afirma evasión a través de Nginx saneado ni que un atacante de Internet pueda elegir su peer TCP: el fallo requiere acceso directo desde una dirección del rango confiado. Es precisamente el cliente directo 172/12 exigido en esta revisión.

**Cambio mínimo necesario:** confiar exclusivamente en la identidad/dirección efectiva del proxy, no en todo el /12; fijar esa identidad de forma reproducible en Compose y cerrar o separar la entrada directa. Conservar `--no-proxy-headers` y la sobrescritura Nginx. Repetir las cinco filas incluyendo otro contenedor/cliente de la misma red que no sea proxy.

## M-02 — integración corregida, presupuesto integral abierto

### PASS de los contraejemplos originales

`core_probe.py` ejecutó run_civia_agent → ThreadPoolExecutor → tool_clasificar_evidencia → router/adaptador multimodal reales del código. Se simula únicamente la salida del proveedor; se persiste el análisis en PostgreSQL.

| Prueba | Observado |
|---|---|
| Dos turnos 10+10 cada uno, clasificación 1500+100 | **1640 tokens**; tracker presente dentro del worker |
| Tracker 200; entrada textual estimada 394, más imagen/salida | **0 llamadas**, análisis no completado, MAX_TOKENS |
| Turno principal con saldo 100 frente a entrada estimada 1270 | **0 llamadas**, MAX_TOKENS |

### FAIL: comprobación de saldo no es una reserva

`adversarial.py` comparte un tracker de **1000** entre dos clasificaciones reales despachadas por executors. El proveedor simulado usa una barrera para que ambas llamadas se inicien antes de registrar el uso; cada una devuelve 600+100.

Resultado: **2 llamadas, 2 análisis completados, total 1400**. Ambas leyeron saldo suficiente antes de que ninguna lo descontara. El lock de `record_usage` evita perder incrementos pero no reserva fondos. `agent.py:361` solo consulta remaining; no hay operación atómica comprobar/reservar. El agente actual despacha normalmente sus herramientas en serie; el contraejemplo prueba explícitamente el tracker compartido concurrente solicitado, no afirma que cada petición comparta presupuesto con otros ciudadanos.

### FAIL: intentos inválidos y errores no se agregan

Con router real:

| Secuencia simulada | Uso suministrado / esperado | Total registrado |
|---|---:|---:|
| Gemini devuelve `{}` con 500+100; Groq devuelve contrato válido con 700+100 | **1400 conocidos** | **800** |
| Tres proveedores devuelven `{}`, cada uno 500+100 | **1800 conocidos** | **1280 estimados** |
| HTTP_503 reintentable, luego éxito sin metadatos de uso; saldo inicial 1000 | Consumo primero desconocido; no corresponde afirmar cero | 2 llamadas, ambas ven saldo **1000**; solo al final se cargan **1280 estimados**, ya sobre presupuesto |

`retry_probe.py` ejecuta el bucle de reintento real, no una emulación del router. El caso HTTP_503 no afirma que una respuesta 503 haya consumido necesariamente tokens: demuestra que el consumo es desconocido, no reservado y no representado como tal. El caso de JSON inválido sí tiene consumo conocido y lo pierde.

Causa: `ai_router.py:655-761` valida antes de devolver uso y solo expone el intento exitoso; la ruta all_failed devuelve ceros. La herramienta cobra una estimación fija cuando recibe ceros. Los errores de validación no preservan el uso ya recibido en los adaptadores. La cota de 80 tokens usada en la comprobación multimodal tampoco constituye una reserva atómica ni una garantía sobre cada salida/reintento.

### FAIL: consumo desconocido presentado como cero

Agente completo, con los adaptadores de turno simulados para lanzar AIProviderError NETWORK_ERROR en los tres nodos: **3 intentos, total_tokens_used=0, tokens_estimated=False, degraded_sql_mode=True**. No se conoce el consumo remoto de esos intentos; el resultado no distingue «cero demostrado» de «desconocido». Una excepción inesperada saliendo del router de clasificación también deja el tracker en cero sin marca estimada.

Subcontrol positivo: una clasificación exitosa sin metadatos de uso registra 1280 con estimated=True; ese recorrido concreto no declara cero. No compensa los errores anteriores.

Referencias: `backend/app/agent.py:58-73` (tracker), `:340-388` (comprobación y cargo tardío), `:494-529` (propagación ya corregida), `:981-1048` (éxito versus error de turno); `backend/app/ai_router.py:655-761` (validación, retorno y errores).

**Cambios mínimos necesarios:** operación atómica de reserva antes de cada intento, incluyendo entrada multimodal y salida acotada; reconciliar después con uso real y liberar únicamente lo no consumido. Propagar el mismo tracker/reserva al router para reintentos/fallback. Acumular uso de todas las respuestas, aunque el JSON sea inválido. Representar consumo desconocido como tal o mediante estimación conservadora identificada, nunca cero exacto por defecto. Probar las reservas con barreras concurrentes, no únicamente sumas concurrentes.

## Regresiones N-02 y G1

### N-02

`n02_probe.py` usa HTTP MockTransport conservando los adaptadores HTTP y las trazas PostgreSQL. Resultados:

- 429 primario: Gemini configurado → Groq configurado. Ningún Gemini oculto intermedio.
- 429 primario + 400 Groq: Gemini → Groq → Gemini terciario configurado.
- JSON inválido primario: Gemini → Groq.
- Turno del agente con 429 primario: Gemini → Groq.

En cada caso el número de trazas coincide con llamadas y los modelos/proveedores registrados coinciden con el transporte. En turnos de agente attempt_number representa el turno y puede repetirse entre proveedores; no se ocultaron filas. No se verificó accesibilidad real de los modelos.

### G1, pruebas independientes

`g1_regression.py` y `g1_sentinel_regression.py` se ejecutaron con PostgreSQL y almacenamiento nuevos:

- Tokens faltante, demo, corto, repetido y secuencial: no permiten iniciar; admin 401. Suite del proyecto incluye el patrón contextual C-01 y pasó.
- PATCH status anónimo: 401; confirm sin credencial o con credencial ajena: 403; ninguna capacidad en GET público. Reconstrucción pública crea otro reporte y no recupera el token original. Confirm posterior a decisión administrativa: 409.
- Idempotencia secuencial y dos clientes concurrentes con misma clave: una fila/un UUID; payload o metadatos distintos: 409. Fallo de traza postcommit: 201/201, una sola fila.
- Propuesta obsoleta: rechazada, conserva RESOLVED. Propuesta heredada sin versión tras ABA: rechazada. Dos decisiones reales concurrentes: una resolución consistente.
- Trigger que rechaza INSERT, audio inválido, replay y escritura parcial de 16 bytes seguida de OSError: **cero archivos nuevos huérfanos**. Los 500 de INSERT/I/O inyectados son fallos previos al alta, no regresión postcommit de A-06.
- Proceso externo crea reporte/propuesta y cambia un estado durante pytest: centinelas originales y concurrentes conservados; aislamiento automático efectivo. Modo estricto sobre nombre no desechable: rechaza (exit 4).
- Evaluador real limitado a una consulta Q13 y fallback determinista, con escritor externo concurrente: preserva propuestas previas/concurrentes, reporte concurrente y decisión administrativa; limpia exclusivamente su aprobación. Su 1/1 no se presenta como evaluación de precisión, revisión humana ni inferencia real.

No se observó regresión de los controles G1 reproducidos. La escritura tardía de M-03 es otra garantía: la limpieza de archivos por fallo de una petición de alta continúa funcionando.

## Pruebas del proyecto y límites

1. Suite completa backend, sin claves reales y con red externa bloqueada por el runner de auditoría: **61 passed, 7 failed, 1 skipped**, 26,15 s. Los siete fallos están en `test_ai_and_agent.py`: flujo vertical, cinco escenarios de resiliencia y recuperación tras caída total; esperan análisis exitoso pero, sin proveedores reales disponibles, obtienen PENDING_ANALYSIS. Se registran como ejecución fallida en este entorno, no como siete vulnerabilidades nuevas ni como PASS. La suite no es enteramente hermética sin proveedores simulados propios. E2E frontend/Nginx se omite por no disponer del servicio.
2. Ejecución separada de las tres suites de auditoría G1/G2/G2.1, sin editar tests: **49 passed**, 23,92 s (14 + 23 + 12). El helper de BD G2.1 ahora respeta el host del DATABASE_URL y pudo ejecutar el trigger real.
3. Reproductores independientes descritos arriba: resultados en `core_results.json`, `proxy_results.json`, `adversarial_results.json`, `retry_results.json`, `n02_results.json`, `g1_results.json`, `sentinel_observations.json`.

La red se bloqueó en el runner de pytest y los probes independientes usaron exclusivamente proveedores sustituidos/MockTransport o claves vacías. Ninguna prueba necesitó claves reales. Un warning de deprecación AnyIO/Starlette no afectó estos resultados. No se ejecutó lint ni frontend porque no se cambió código y el alcance es esta reauditoría backend.

## Reproducción y evidencia conservada

Los scripts de auditoría están fuera de producción, en la raíz temporal indicada. Para repetirlos se requiere iniciar ese clúster desechable y fijar PYTHONPATH a `src/backend`, PYTHONUTF8=1, DATABASE_URL al puerto 55485/base correspondiente, UPLOAD_DIR y TEMP/TMP dentro de la raíz; tres claves IA vacías. `core_probe.py` crea el trigger y debe ejecutarse en una base nueva, no repetirse sobre la misma sin preparar otra. `g1_regression.py` también crea un trigger propio. `n02_probe.py`, `adversarial.py` y `retry_probe.py` usan la fila sintética que crea core_probe.

Los comandos ejecutados incluyen:

```text
git archive 8162a12 -o <raiz>/head.zip
initdb -D <raiz>/pgdata -U audit --auth=trust --encoding=UTF8 --no-locale
pg_ctl -D <raiz>/pgdata -l <raiz>/postgres.log -o "-h 127.0.0.1 -p 55485" -w start
python <raiz>/core_probe.py <raiz>
python <raiz>/proxy_probe.py <raiz>
python <raiz>/adversarial.py <raiz>
python <raiz>/retry_probe.py <raiz>
python <raiz>/n02_probe.py <raiz>
python <raiz>/g1_regression.py <raiz>
python <raiz>/g1_sentinel_regression.py <raiz>
python <raiz>/suite_runner.py <raiz>
python <raiz>/focused_suite.py <raiz>
```

Cada script/runner se ejecutó en un proceso con su DATABASE_URL descrito, no con valores del entorno habitual. La carpeta conserva los scripts exactos para inspección y los logs `suite.log`, `focused_suite.log`, `g1.log`, `sentinels.log`. Un primer pase de adversarial.py usaba Path.write_text; se sustituyó únicamente en el reproductor temporal por el helper real `_atomic_write_bytes` y se repitió; los resultados informados son los de la segunda ejecución. No se modificaron los módulos auditados.

## Bloqueos y correcciones mínimas, en prioridad

1. **M-03:** revocar efectos del worker superviviente y comprobar deadline en SQL retenido/almacenamiento; acotar cancelación síncrona. Conservar el rollback real de A-02 y los handlers ya corregidos.
2. **M-06:** reemplazar confianza en todo 172.16/12 por identidad explícita del proxy y separar/restringir acceso directo.
3. **M-02:** reservas atómicas por intento y contabilidad acumulada, incluyendo fallos y consumo desconocido.

Se reconocen los subcontroles corregidos sin cerrar controles parcialmente vulnerables. **El criterio final no se cumple: G2.1 permanece NO APROBADO**, aun pasando las 49 pruebas de auditoría del proyecto.

## Cierre y huellas SHA256

PostgreSQL temporal se detuvo correctamente al finalizar. HEAD sigue en `8162a12f8e278fa58e65db7d6ad06c124948ce4a`; el único cambio del árbol original es este informe nuevo. Se conservaron las evidencias desechables sin tocar otros servidores o archivos de producción.

| Evidencia | SHA256 |
|---|---|
| head.zip | `8F5DD24ED5FDE178055B8DE68D87583E27EFE2D78B8BAA653E75ECF71A5CD3C7` |
| core_results.json | `8AC6B2CFBABBD5B7472570B4431039985FD573CF97251C980D4388E34D2AB0D7` |
| adversarial_results.json | `0F30179FB3BC4043A5E49D03CA51B7D201AD2B907E975D72DB84D9892BBEB6BB` |
| proxy_results.json | `AE96127E03D94705ABA50A8267B900B73E5F86A33EDB8019D0E7DE39F8080624` |
| retry_results.json | `49C9559907ED1A209AADC345FF938CCD9BD07BA8239988ED8D963EE94B758946` |
| n02_results.json | `D5B1F6431DD769CFD9B797414260B6804FC59B68F263F7F36CB13073A71391E1` |
