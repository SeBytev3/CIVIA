# CIVIA — auditoría independiente G2.1.1

Fecha: 2026-11-02, America/Bogota.

**Commit congelado:** `a745a1ca01356253659b8db97b38fcf30ef5a260`, rama `fix/auditoria-final`. Base comparada en los módulos auditados: `8162a12f8e278fa58e65db7d6ad06c124948ce4a`.

Referencias leídas: `docs/auditoria_codex_g2_1_8162a12.md`, `docs/remediacion_g2_1.md`, `docs/estado.md` y contrato AGENTS. No se revisó ni ejecutó Autopilot.

**Dictamen: G2.1.1 NO APROBADO.** Hay fallos reproducidos en M-03, M-06 y M-02. Se mantienen los PASS de los contraejemplos A-02, N-02 y G1 repetidos, sin extrapolarlos a garantías universales.

## Matriz del commit auditado

| Control | Resultado | Evidencia ejecutada | Bloqueo restante |
|---|---|---|---|
| M-03 | **FAIL** | Cursor proxy retenido y escritura con capacidad ya revocada bloquean correctamente; worker sin BD retorna alrededor de 0,115 s; handler final/literal 0,10 responden 200. | El retorno nativo de execute y el método copy permiten SQL vencido. Carrera revoke/replace publica un archivo después de revocar. |
| M-06 | **FAIL** | Otro cliente 172.28.0.9 recibe 200/200/429; Nginx real, tras corregir exclusivamente la topología desechable, sanea cabeceras y separa clientes. | Compose limpio entrega .2 a PostgreSQL y Nginx no arranca; esa identidad de BD es tratada como proxy y permite 200/200/200 con XFF variable. 172.18.0.2 sigue confiado sin asignación en la nueva topología. |
| M-02 | **FAIL** | Dos reservas de 700 con saldo 1000: una rechazada; integración concurrente: un análisis, 700 tokens. Gemini inválido 600 + Groq 800 = 1400; tres inválidos = 1800; executor conserva tracker y total 1640. | Solo se reserva una vez alrededor del router. Con saldo 1000 y primer intento consumiendo 1000, se inicia Groq y se llega a 1800. Los reintentos desconocidos tampoco reciben reserva individual. |
| A-02, regresión | **PASS, caso reproducido** | Trigger diferido real de 0,18 s en PostgreSQL 17.6; commit iniciado antes del plazo 0,25; otra conexión conserva ORIGINAL después de terminar el worker. | No implica prohibición de todas las sentencias tardías: véase M-03. |
| N-02, regresión | **PASS, transporte simulado** | 429 primario → Groq; 400 Groq → Gemini terciario; orden/modelos coinciden con trazas PostgreSQL. | No se verificó disponibilidad real ni inferencia externa. |
| G1, regresión | **PASS en controles reproducidos** | Autorización, capacidad de edición, idempotencia concurrente, trazas, aprobaciones obsoletas/ABA/concurrentes, archivos parciales y centinelas de pruebas/evaluación. | No certifica otros módulos fuera del alcance. |
| Hermeticidad declarada de test_ai_and_agent.py | **FAIL como garantía general** | Sus 12 pruebas pasan sin claves en la suite. Con clave sintética, el test vertical intenta Google; la intercepción bloquea la red, pero el fixture disimula el fallo y el test pasa. | El fixture aún llama al proveedor original si encuentra una clave. |

## Entorno, aislamiento y evidencia

El árbol estaba limpio, HEAD coincidía con el SHA solicitado y se congeló mediante git archive. No se cambió de rama. Solo se añade este informe al repositorio original; todos los scripts y ajustes experimentales están fuera de producción.

Raíz conservada:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-a745-14f47a8fb56a48a79e3a6c1a736380e8`

Contiene `head.zip`, `src`, reproductores, logs y JSON. Se inicializó **PostgreSQL 17.6 real**, nuevo PGDATA en esa raíz, escuchando únicamente en `127.0.0.1:55487`. Bases propias: `test_a745_independent`, `test_a745_suite`, `test_a745_g1`, `civia_a745_probe` y `eval_a745_independent`, más bases creadas por la suite en el mismo clúster. El nombre no desechable civia_a745_probe es deliberado para comprobar aislamiento/rechazo; no corresponde al entorno habitual. TEMP/TMP y uploads se fijaron dentro de la raíz.

CPython 3.13.18 y dependencias del backend reutilizadas de la auditoría anterior. Se utilizaron únicamente datos sintéticos, claves vacías o marcadores sintéticos y proveedores sustituidos/HTTP MockTransport. Administradores CSPRNG efímeros sin imprimirlos. No se copió `.env` ni se usaron API keys reales.

Esta vez Docker sí estaba disponible: Engine **29.9.2**, Compose **5.6.1**. Se desplegó el proyecto exclusivo `civia_a745_audit`, construyendo la imagen API desde la copia congelada. Sus volúmenes y su PostgreSQL 17-alpine fueron nuevos. Se conservaron subred e identidades del Compose; se cambiaron únicamente puertos publicados para evitar los servicios habituales, nombres/datos de prueba y el cuerpo del agente, sustituido por una respuesta sintética para aislar la prueba de cuota. El CMD conserva las opciones efectivas Uvicorn `--no-proxy-headers --forwarded-allow-ips ""`. El frontend usa una imagen local existente, montando el nginx.conf exacto congelado. La prueba acredita Nginx y red reales, no una reconstrucción del bundle frontend de este commit.

Posteriormente se fijaron IP de BD/API **solo en un override experimental desechable** para poder arrancar Nginx y probar sus cabeceras. Se distingue expresamente ese experimento del despliegue original fallido. No se alteraron redes, contenedores o volúmenes habituales.

## M-03 — revocación incompleta en fronteras públicas

### Controles que sí funcionan

`edges.py` despacha un worker real con ThreadPoolExecutor. Obtiene conexión/cursor antes de dormir 0,45 s, con timeout 0,10. El cursor conservado como `_CapabilityCursorProxy` rechaza `execute` después del vencimiento con TimeoutError. Un helper de archivos llamado con capacidad ya revocada también rechaza sin crear destino.

El agente completo con worker iniciado de 0,45 s retorna TIMEOUT a **0,115 s**, sin esperar a que termine el sleep. Sustituir la cancelación por una función que duerme 0,50 s no bloquea al llamador: **0,1066 s**. La petición literal de 0,10 y el último manejador HTTP de TimeoutError devuelven **200**, sin 500. El router sigue rechazando JSON válido recibido después del plazo de 0,15 s.

Estos resultados son mejoras reales. No se exige poder matar un hilo arbitrario en CPython; se exige que los efectos del hilo superviviente pasen por barreras efectivas.

### FAIL 1: execute devuelve el cursor nativo sin protección

`backend/app/db.py:90-108` comprueba la capacidad en execute/executemany, pero devuelve `self._cur.execute(...)`. Psycopg devuelve el propio cursor nativo. Por tanto la API pública y habitual permite retenerlo sin inspeccionar atributos privados:

```python
with db.get_conn() as conn:
    cursor = conn.cursor().execute("SELECT 1")
    time.sleep(0.45)
    cursor.execute("SELECT 8675309 AS marker")
    value = cursor.fetchone()["marker"]
```

También ocurre con `cursor = conn.execute("SELECT 1")`, porque Connection.execute devuelve el resultado de cursor.execute.

Resultados reales PostgreSQL con timeout 0,10:

| Ruta retenida | Resultado después del vencimiento | Retorno del llamador |
|---|---|---:|
| Proxy original de conn.cursor() | TimeoutError, correcto | 0,1563 s |
| Retorno de cursor.execute() | **8675309** | 0,1488 s |
| Retorno de conn.execute() | **8675309** | 0,2634 s |

Los workers dormían 0,45 s; en las rutas que retornaron antes, el SQL se ejecutó después de que el llamador ya recibiera TIMEOUT. No hubo modificación de psycopg ni acceso a `_cur` en el ataque.

### FAIL 2: copy se delega sin barrera

`__getattr__` expone el método nativo copy, no interceptado por el proxy:

```python
with cursor.copy("COPY (SELECT 8675309) TO STDOUT") as copy:
    value = bytes(copy.read())
```

Ejecutado sobre el proxy retenido tras dormir 0,45 s, devuelve **8675309** después del deadline 0,10. La cancelación de una conexión ociosa no impide enviar otra sentencia.

Se probó además `COPY (SELECT nextval('audit_late_sequence')) TO STDOUT` en una secuencia exclusivamente sintética: con deadline 0,25 y cursor retenido, devuelve 1; otra conexión observa **is_called=true** pese al cierre sin commit. PostgreSQL no revierte nextval. Esto acredita un efecto SQL no transaccional posterior al deadline, **no** un cambio tardío de un reporte ciudadano ni una inyección SQL desde HTTP. En esta repetición el retorno del llamador fue 0,5308 s; no se presenta como efecto posterior al retorno, sino posterior al deadline. Un primer intento de esta prueba con 0,10 no llegó a demostrar el efecto y no se contó como evidencia positiva.

### FAIL 3: carrera revoke → os.replace

`security.py:124-125` comprueba la capacidad y después llama a os.replace. El lock de ExecutionCapability se libera al terminar la comprobación; no cubre la promoción.

Reproductor determinista: se conserva el os.replace real y se intercala una barrera a su entrada. El worker completa staging y pasa la comprobación. Otro hilo llama `capability.revoke()` y comprueba `is_valid()==False`. Se libera la barrera y se ejecuta el replace real.

**Resultado: events=[promoted], destino race.txt existente**, promoción realizada después de terminar revoke. No se fuerza una excepción ni se sustituye el resultado de os.replace; la instrumentación controla únicamente el intercalado. No hay limpieza compensatoria porque la función retorna éxito.

Esto es TOCTOU entre autorización y efecto; las dos comprobaciones independientes no son exclusión mutua con revocación. Un sleep puro sobreviviente sin efectos no sería una vulnerabilidad; estos efectos sí se demostraron.

**Correcciones mínimas:** mantener protegido el cursor devuelto (retornar el proxy), cubrir copy y demás métodos de envío utilizados/admitidos sin delegación irrestricta; hacer indivisible la autorización/promoción respecto de revoke mediante un protocolo de efectos y supervisión acotado. Un lock sostenido durante I/O puede retrasar revoke: documentar y acotar esa decisión o dejar la promoción al supervisor. No presentar el proxy como sandbox para código arbitrario capaz de llamar directamente a psycopg/os.

### Regresión A-02: PASS del commit diferido

`core_probe.py` creó un constraint trigger PostgreSQL `AFTER UPDATE DEFERRABLE INITIALLY DEFERRED`, con pg_sleep(0,18) al escribir el marcador. La herramienta actualiza, espera 0,08 y entra a commit; deadline 0,25.

| Método | Entrada a commit | Retorno | Consulta desde otra conexión tras terminar worker y esperar 0,20 s |
|---|---:|---:|---|
| conn.commit envuelto | 0,1119 s | 0,4118 s | ORIGINAL |
| checked_commit | 0,1107 s | 0,3065 s | ORIGINAL |

Ambos empiezan dentro del plazo, cruzan el límite durante el trigger y abortan con TimeoutError. No aparece commit tardío. No se usaron mocks de SQL/commit. Los tiempos muestran que la cancelación no convierte todo caso con BD en una respuesta estrictamente menor a 0,20 s; el test de cancelación artificial bloqueante separado sí confirmó su desacoplamiento.

## M-06 — identidad configurada versus asignación Docker real

### FAIL de despliegue e identidad

Compose define frontend=172.28.0.2, una subred 172.28.0.0/16, y deja BD/API con asignación dinámica. No reserva esa dirección frente a la asignación dinámica del contenedor que arranca primero.

Se ejecutaron **dos arranques limpios** del proyecto desechable, eliminando exclusivamente sus volúmenes/red entre ellos. En ambos:

1. PostgreSQL arranca primero y obtiene **172.28.0.2/16**.
2. API obtiene **172.28.0.3/16** y queda saludable.
3. Frontend no puede arrancar: **failed to set up container networking: Address already in use**.

Docker network inspect confirmó la relación entre nombre de contenedor e IP; no se dedujo de los valores estáticos. Desde un cliente efímero compartiendo **el espacio de red del contenedor de BD propio** (`docker run --network container:civia_a745_audit-db-1 ...`), se enviaron tres solicitudes al API variando XFF: **200/200/200**. No es Nginx; el servidor lo considera confiable porque su peer real es .2. Otro cliente de la misma red, .9: **200/200/429**.

Se usa el namespace de una BD de auditoría para demostrar el peer real; no se ejecutó código en una BD habitual ni se afirma que un ciudadano de Internet pueda ocupar esa IP. El fallo de asignación afecta reproducibilidad, y confiar en la IP sin asegurar su propietario convierte a ese contenedor distinto en proveedor de identidad.

### Dirección adicional 172.18.0.2

`config.py:39` y `docker-compose.yml:34` mantienen `172.28.0.2,172.18.0.2`. La nueva topología solo asigna el frontend en 172.28.0.2; **172.18.0.2 es innecesaria y no está vinculada a ese servicio**.

Con configuración Docker/Uvicorn efectiva, aplicación ASGI real y peer 172.18.0.2: sin XFF **200/200/429**, con XFF variable **200/200/200**. Este caso demuestra la confianza de la aplicación; no se afirma que esa IP tenga conectividad directa al API dentro de la nueva red aislada ni que pueda falsificarse el peer TCP desde Internet. Es una superficie de confianza residual técnicamente sustentada, separada del ataque Docker real anterior.

### Controles positivos y Nginx real

Peers ASGI público, loopback, 10/8, 172.19.0.9 y 172.28.0.9: **200/200/429** aun variando XFF. Uvicorn mantiene proxy_headers=False.

Para ejecutar el proxy después del fallo, **solo el override experimental** asignó BD=.10 y API=.11. Frontend mantuvo .2. Los tres servicios quedaron saludables; network inspect confirmó las identidades. Clientes Docker reales:

| Origen y recorrido | Tres peticiones con XFF y X-Real-IP hostiles variables |
|---|---|
| .9 → API directo | **200/200/429** |
| .20 → Nginx → API | **200/200/429** |
| .21 → Nginx → API | **200/200/429** |

Las dos últimas filas conservaron cuotas independientes. Nginx real sobrescribió cabeceras con remote_addr, según el nginx.conf congelado. **Estos PASS dependen de corregir la topología de prueba; no acreditan que el Compose original arranque.**

**Correcciones mínimas:** excluir las IP estáticas del pool dinámico (o asignar IP explícitas disjuntas a BD/API/frontend), conservar una única dirección autorizada y eliminar 172.18.0.2. Repetir arranque desde red vacía y verificar propietario real de cada IP antes de dar por válida la frontera de confianza.

## M-02 — reservas concurrentes corregidas, no por intento

### Pruebas ejecutadas

| Escenario independiente | Resultado |
|---|---|
| Dos try_reserve(700) simultáneos, presupuesto 1000 | **Una aceptada, una rechazada; 700 reservados** |
| Dos clasificaciones reales concurrentes con tracker compartido y executor | **Una llamada al proveedor, un análisis, 700 usados; segunda MAX_TOKENS; reserva final 0** |
| Agente completo: dos turnos de 20 y clasificación de 1600 | **1640**, tracker presente en worker |
| Presupuesto 200, entrada textual estimada 394 más imagen/salida | **Cero llamadas**, MAX_TOKENS |
| Gemini inválido 500+100 y Groq válido 700+100 | **1400 conocidos**, sin duplicación |
| Tres respuestas inválidas de 500+100 | **1800 conocidos**, sin duplicación |
| Excepción construyendo prompt, antes de reserva | ValueError; uso 0, reserva 0, sin marcar consumo desconocido de una llamada no iniciada |
| Excepción del router después de reservar | RuntimeError; **732 estimados, unknown=true, reserva 0** |
| Respuesta sin metadatos de uso | **732 estimados**, sin cero ficticio |
| Consumo real 1600 con presupuesto 1000/reserva 732 | **1600 registrados una vez**, reserva 0; siguiente clasificación MAX_TOKENS |
| Error desconocido inicial + éxito conocido de 800 | **800 conocidos, unknown=true**; no se inventa uso exacto del intento fallido |

La conciliación no trunca el uso real a la reserva ni lo duplica. Que un proveedor simulado devuelva más que la estimación no demuestra por sí solo una carrera de reservas: es una limitación de estimación/salida acotada que debe distinguirse del siguiente fallo preventivo.

### FAIL: reserva única cubre varios intentos sin comprobar saldo entre ellos

`agent.py:415-456` reserva 732 para el payload sintético antes de llamar al router; solo reconcilia en finally al terminar **toda la cadena**. `ai_router.py:590-784` acumula consumo pero no recibe tracker ni reserva por intento.

Reproductor con presupuesto **1000**:

1. Gemini devuelve `{}` con **900+100=1000** tokens conocidos.
2. El router valida, descarta el contrato y llama a Groq.
3. Groq devuelve contrato válido con **700+100=800**.

**Resultado: dos llamadas, análisis completado, 1800 usados; ambos adaptadores ven remaining=268**. Al iniciar Groq, el consumo ya conocido del primer intento agota todo el presupuesto, aunque el tracker todavía no lo sabe. La prevención por intento exigida falla; contabilizar 1800 al final no evita esa llamada.

Con 503 reintentable y éxito posterior sin metadatos: dos llamadas reales al adaptador simulado, ambas ven **268**, y se imputa solo **una reserva estimada de 732** al final. Se marca unknown/estimated cuando corresponde, lo cual es una mejora de honestidad, pero no se hace reserva preventiva ni estimación independiente de cada intento. No se afirma que un HTTP 503 necesariamente consuma tokens: su consumo es desconocido.

En turnos principales también se reserva antes del bucle de proveedores; los errores no reciben una conciliación/reserva individual antes de pasar al siguiente. Este riesgo está sustentado por código; el contraejemplo ejecutado y suficiente para FAIL es el router multimodal anterior.

**Cambio mínimo:** mover o propagar reserva/reconciliación al nivel de cada intento del router y de cada proveedor del turno. Imputar el uso conocido incluso si falla el contrato antes de decidir el siguiente intento; retener/estimar el consumo desconocido con una marca explícita. Reservar entrada y una salida realmente acotada antes del siguiente envío. Mantener las reservas atómicas y sumas correctas ya verificadas.

## Suite existente y hermeticidad

Suite backend congelada completa, sin claves y con bloqueo externo en el runner de auditoría:

**75 passed, 1 failed, 1 skipped**, 25,33 s; un warning de deprecación AnyIO.

- FAIL: `test_audit_g2_resilience.py::test_m06_trusted_proxy_client_ip`, línea 306. Todavía espera que el gateway 172.18.0.1 pueda suministrar identidad; la configuración nueva correctamente lo trata como peer directo. Es una expectativa desactualizada, **no una vulnerabilidad por rechazar ese gateway**. No se reproduce la afirmación documental de 77 PASS.
- E2E frontend omitido en el pytest host porque busca `http://frontend:80`; las pruebas Docker/Nginx independientes posteriores sí se ejecutaron, con la salvedad de topología descrita.
- G1 14, G2.1/G2.1.1 20 y test_ai_and_agent 12 pasaron dentro de esta ejecución. No se usaron sus PASS como sustituto de los contraejemplos independientes.

### El fixture «hermético» todavía puede contactar proveedores

`backend/tests/test_ai_and_agent.py:27-86` usa un simulador inmediatamente solo cuando api_key está vacía. Con cualquier valor no vacío llama al adaptador original y, si este falla, reemplaza el resultado por uno sintético. Es un fallback de test, no aislamiento hermético de red.

Reproductor independiente `hermetic_run.py` + `hermetic_plugin.py`:

- Tres claves fijadas a marcadores sintéticos no válidos, nunca claves reales.
- Intercepción de httpx.Client.send: toda solicitud a Google/Groq se registra por **hostname solamente** y se bloquea antes del envío.
- Se ejecuta únicamente `test_vertical_flow_create_analyze_confirm_and_query` sin modificar el archivo del proyecto.
- **1 passed**, pero el plugin registra **un intento a generativelanguage.googleapis.com**. La excepción del bloqueo es absorbida y el fixture devuelve un análisis simulado.

No hubo tráfico externo. La prueba no depende de que una clave funcione para pasar, pero sí intenta servicios externos según el entorno y puede ocultar sus fallos; por ello no es realmente hermética.

**Cambio mínimo:** sustituir incondicionalmente los adaptadores/transporte en esa suite; separar explícitamente las pruebas opcionales de integración real. Añadir una aserción que falle si se intenta red externa en las pruebas unitarias/de integración hermética.

## Regresiones preservadas

**N-02:** adaptadores HTTP reales con MockTransport; primario 429 → Groq; Groq 400 → segundo Gemini configurado; JSON inválido → Groq; agente con 429 → Groq. Cada llamada tiene traza PostgreSQL con proveedor/modelo correspondiente; no aparece Gemini oculto previo a Groq. No se usaron proveedores reales.

**G1:** reproductores propios sobre bases/archivos nuevos verificaron:

- Tokens vacíos/demo/débiles no arrancan y admin 401; suite incluye además patrón contextual.
- Estado anónimo 401; confirmación sin capacidad/ajena 403; capacidad ausente del GET; reconstrucción pública no recupera capacidad original; edición tras decisión administrativa 409.
- Reintentos secuenciales/concurrentes con misma clave crean una fila; campos modificados 409; fallo de trazas postcommit sigue devolviendo 201 sin duplicar.
- Propuestas obsoletas y heredadas sin versión tras ABA rechazadas; decisiones concurrentes consistentes.
- Fallos de INSERT, audio, replay y escritura parcial: cero archivos huérfanos de alta. Los 500 de fallo inyectado antes del alta no son un 500 postcommit ni fallo del handler TIMEOUT.
- Pytest con escritor externo concurrente conserva centinelas; modo estricto rechaza base de nombre no desechable. Evaluador real limitado a Q13 y fallback determinista conserva registros/decisiones ajenas y limpia solo su aprobación. Ese 1/1 no se presenta como inferencia ni evaluación humana.

La carrera de promoción de M-03 no invalida el PASS limitado de limpieza compensatoria G1: son condiciones distintas y se mantuvieron diferenciadas.

## Evidencia reproducible conservada

En la raíz temporal indicada:

| Scripts | Evidencia |
|---|---|
| core_probe.py | core_results.json, core.log: PostgreSQL diferido, HTTP, router y tracker completo |
| edges.py | edges_results.json: cursores, copy, carrera replace/revoke, reservas y excepciones |
| sql_effect.py | sql_effect_results.json: secuencia sintética PostgreSQL |
| accounting_exact.py, retry_probe.py | exact_results.json, retry_results.json |
| proxy_probe.py | proxy_results.json: matriz ASGI/configuración Uvicorn |
| docker_audit.py, docker_probe.py | docker_original_failure.log, docker_original_network.json, docker_results.json: Compose original fallido y peer real de BD |
| docker_fixed_topology.py, nginx_probe.py | nginx_results.json: experimento con BD/API disjuntas y Nginx real |
| suite_runner.py | suite.log |
| hermetic_run.py, hermetic_plugin.py | hermetic_results.json, hermetic.log |
| n02_probe.py | n02_results.json |
| g1_regression.py, g1_sentinel_regression.py | g1_results.json, sentinel_observations.json, g1.log, sentinels.log |

Los scripts importan desde `<raiz>/src/backend`, con DATABASE_URL correspondiente a cada base del clúster nuevo, UPLOAD_DIR y TEMP/TMP bajo la raíz, PYTHONUTF8=1 y claves vacías salvo la prueba sintética de hermeticidad. Los reproductores que crean triggers/secuencias requieren base nueva para repetir desde cero. No se modificó ningún módulo de la copia auditada para que pasaran las pruebas; los overrides Docker son experimentos externos explícitos.

Comandos principales:

```text
git archive a745a1c -o <raiz>/head.zip
initdb -D <raiz>/pgdata -U audit --auth=trust --encoding=UTF8 --no-locale
pg_ctl -D <raiz>/pgdata -l <raiz>/postgres.log -o "-h 127.0.0.1 -p 55487" -w start
python <raiz>/core_probe.py <raiz>
python <raiz>/edges.py <raiz>
python <raiz>/accounting_exact.py <raiz>
python <raiz>/retry_probe.py <raiz>
python <raiz>/docker_audit.py <raiz>
python <raiz>/docker_probe.py <raiz>
python <raiz>/suite_runner.py <raiz>
python <raiz>/hermetic_run.py <raiz>
```

El Dockerfile del commit y nginx.conf se usaron desde la copia congelada; el ajuste temporal de puertos y fake del agente no cambian identidad de red ni rate limiter. El segundo experimento de topología sí cambia asignación de BD/API y se ha informado como tal. Se repitió después el arranque original limpio para conservar el fallo y confirmar su reproducibilidad.

## Cambios mínimos pendientes y criterio final

1. Cerrar escapes públicos de cursor y serializar autorización/promoción frente a revoke, manteniendo cancelación y rollback.
2. Reservar correctamente las identidades Docker para que Nginx sea realmente .2; eliminar el proxy heredado innecesario.
3. Reservar/conciliar por intento, incluyendo errores y fallback, antes del siguiente envío.
4. Hacer herméticos los mocks y actualizar la expectativa del test de gateway sin volver a confiar en él.

No se prescribe detener forzosamente hilos arbitrarios como condición de seguridad ni se afirma explotación remota de APIs internas por un ciudadano. Los FAIL se apoyan en fronteras concretas reproducidas, incluido tráfico Docker real. **Los tres controles no pasan: G2.1.1 permanece NO APROBADO.**

## Cierre y huellas

Se detuvo el PostgreSQL portable y se eliminaron únicamente los contenedores, red y volúmenes del proyecto `civia_a745_audit`. Se conservaron scripts y evidencia en la raíz temporal. HEAD permanece en el SHA auditado y el único archivo nuevo del repositorio original es este informe; no hubo commits, push, merge ni cambios de producción.

SHA256 de evidencias principales:

| Archivo | SHA256 |
|---|---|
| head.zip | `EDF363487B67638ACF8416561B92F0EE15868D85DD7ADCBC15D7D8D0B6E58F4E` |
| edges_results.json | `B95B971B9A7268A5F7510666AC2017A4B6EA7C2B5B28F513ED7714B66520DE2E` |
| exact_results.json | `DB5E22520948D715E7EC164518F2E39266E3CCE4B48DF16EDCFEF96D0EBE8D95` |
| docker_original_network.json | `3B36F4EB7D7D2BE90C2EEB50A32DBD839351134FE81AE375C7812C06FFC1B60A` |
| docker_original_failure.log | `56FE831FF55011E38B25656DBC4108E38294567CEADFE4A797CC25C981FDF8E4` |
| docker_results.json | `2982EDC276AE034D4D62605AAF26FB868390E2E86FF1BEB5A832982B93B74061` |
| nginx_results.json | `7A494DFA7E3EFD1D396030108965E13B2014CAA84F66A3C20F8476B5350DB9F4` |
| hermetic_results.json | `E44DAA76F1E98B3DD3EA10A605F59F4A52450AEC31C574877AE1D9AAE1762965` |
