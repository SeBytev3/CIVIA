# CIVIA — aceptación focalizada G2.1.5

Fecha: 2026-11-03, America/Bogota.

**Commit exacto congelado:** `cdc646bdb9794de1a43125fbad28f8958208ea44`, rama `fix/auditoria-final`. Se leyó el informe anterior `docs/auditoria_codex_g2_1_4_95eecba.md`, la sección 10 de `docs/remediacion_g2_1.md` y el bloque G2.1.5 de `docs/estado.md`.

**A-02: FAIL. Dictamen global: NO APROBADO.** Los casos anteriores 61–64 y 81–84 pasan y la suite ordinaria está verde en este entorno. Sin embargo, se confirmaron modificaciones después del TIMEOUT en tres condiciones directamente relacionadas con el nuevo mecanismo: desfase de reloj, pausa durante la conversión monotónico→epoch y temporizador PostgreSQL ya activo. La comprobación post-commit lanza TimeoutError, pero los datos ya están confirmados.

No se revisó ni ejecutó Autopilot. No se modificó producción ni las aserciones existentes. Sin commits, push, merge o cambio de rama.

## Matriz

| Control | Resultado | Evidencia ejecutada |
|---|---|---|
| A-02 | **FAIL** | Casos 102 y 109: cliente adelantado 100 ms, TIMEOUT a ≈0,259 s y COMMIT confirmado a **0,2916/0,2931 s**; estado final CHANGED. Caso 104: pausa de muestreo sin desfase, COMMIT a **0,2793 s**. Casos 151–152: timer PostgreSQL preexistente, COMMIT a **0,2942/0,2857 s**. Deadline **0,25 s**, trigger diferido **0,18 s**. |
| Normalización de excepciones | **PARCIAL, pendiente** | Cancelaciones del deadline y test existente pasan. UndefinedTable se preserva. Pero una terminación administrativa real, SQLSTATE 57P01, a **0,0338 s** de un plazo de 2 s se presenta como TimeoutError. |
| Suite ordinaria | **PASS en el entorno ejecutado** | Claves vacías: **91 passed, 1 skipped, 1 deselected**. Claves sintéticas: **91 passed, 1 skipped, 1 deselected**. Cero intentos externos inesperados en ambos modos. |
| M-02 | **PASS, regresión mínima** | Dos clasificaciones concurrentes de 700: **1400** exactos; reservas pendientes **0**. |
| M-03 COPY y revocación | **PASS, regresión mínima** | COPY IN/OUT funcional, iteradores y write_row bloqueados después de revoke; solo dos filas válidas persistidas. |
| G1, N-02 y M-06 | **PASS en pruebas/configuración ejecutadas** | Suite G1 sin fallos; orden/modelos/trazas N-02 preservados; configuración y tests M-06 sin cambios relevantes. No se repitieron despliegues históricos. |

La suite verde no sustituye las pruebas de aceptación independientes de los escenarios nuevos solicitados.

## Entorno y aislamiento

Árbol original limpio al comenzar, HEAD igual al SHA solicitado. Copia congelada mediante git archive en:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-cdc6-0b5ef98a52164f4ab9580cd85c03bc4e`

PostgreSQL **17.11 real**, imagen local postgres:17-alpine; contenedor `civia_cdc6_pg`, red `civia_cdc6_pgnet` y volumen `civia_cdc6_pgdata`, exclusivos. Puerto solo en `127.0.0.1:55495`; bases nuevas `test_cdc6_independent`, `test_cdc6_blank`, `test_cdc6_synthetic` y las bases desechables que crean los tests dentro de ese servidor.

CPython 3.13.18, psycopg 3.2.6 y dependencias del backend reutilizadas. Uploads, TEMP/TMP y scripts bajo la raíz temporal. Sin .env, claves reales o datos privados. Proveedores simulados y bloqueo externo de red; los administradores de tests se generaron con CSPRNG sin imprimirlos. SQL, COPY, trigger, cancelación y COMMIT son reales. Un primer intento de conexión ocurrió antes de que PostgreSQL terminara su arranque; tras pg_isready se prepararon las bases. No se contó como defecto del producto.

## 1. Implementación y semántica efectiva

### Qué cambió

`checked_commit` convierte el saldo monotónico a epoch con `time.time() + rem_sec`; el servidor resta su clock_timestamp. El wrapper de get_conn delega en ese helper y conserva el commit nativo en `_orig_commit`. get_conn instala además un transaction_timeout temprano, de alcance de sesión (`set_config(..., false)`).

Con relojes alineados y sin pausa entre las muestras de tiempo, esta expresión deduce efectivamente la demora de envío SQL. Las reproducciones anteriores ahora abortan. No obstante, el epoch combina dos relojes y dos muestras no atómicas, y actualizar el GUC no equivale a modificar el temporizador ya armado de la transacción actual.

Referencias: `backend/app/db.py:350-471`, particularmente `:364`, `:408`, `:447-468`; get_conn `:475-548`, particularmente `:528-538`.

### transaction_timeout en una transacción que ya empezó

Pruebas reales independientes, registrando el tiempo monotónico de cada operación y el SQLSTATE:

| Secuencia | Comportamiento PostgreSQL observado |
|---|---|
| Abrir transacción; esperar 120 ms; configurar 80 ms | Configuración a **0,1239 s**; otra consulta de 40 ms termina; TransactionTimeout **25P04** a **0,2071 s**. No se toma como origen el inicio antiguo de la transacción. |
| Configurar 80 ms; esperar 40 ms; cambiar a 200 ms | SHOW informa 200ms, pero la transacción termina por **25P04 a 0,0854 s**, según el temporizador inicial. |
| Configurar 200 ms; esperar 40 ms; cambiar a 80 ms | SHOW informa 80ms; una consulta termina a **0,1488 s**, más tarde del supuesto nuevo límite a ≈0,125 s. La terminación llega a **0,2060 s**, según el temporizador inicial. |

En las condiciones probadas, el primer temporizador activo no se rearma al modificar el valor dentro de esa misma transacción. **Leer un GUC más corto no demuestra que el timer activo se haya acortado.** Esto es especialmente relevante cuando ya existe un límite de sesión al abrir la transacción.

No se extrapoló desde documentación o mocks: se observó el backend PostgreSQL 17.11 y su error 25P04.

### Rama de plazo vencido con pg_cancel_backend

Se actualizó una fila sintética sin commit y se ejecutó la rama exacta con epoch ya pasado. Resultado: **QueryCanceled, SQLSTATE 57014**, transacción en error; no retornó una confirmación utilizable ni se continuó con commit. Otra conexión conserva **ORIGINAL**.

Esta rama funciona en la reproducción. No compensa los casos en los que un epoch desplazado concede tiempo de más ni los temporizadores ya activos.

## 2. Reproducciones anteriores y commits válidos

Se repitieron los scripts de la auditoría previa, sin cambiar sus aserciones ni el trigger:

- **61–64:** pausa 0,13 s antes de la configuración y cancelación Python retrasada 0,15 s; ambos helpers conservan ORIGINAL después de finalizar el worker.
- **81–84:** pausas 40 ms / 5 ms / 40 ms, servidor aislado o Timer retrasado; ambos helpers conservan ORIGINAL.
- Repeticiones secuenciales/concurrentes y casos sin Timer Python: conservación de ORIGINAL, con cancelaciones reales de servidor.
- Pausa de 0,13 s después de la última configuración y antes de COMMIT: ORIGINAL, sin confirmar escritura tardía en ese recorrido alineado.

Commits legítimos con trigger 0,18 s y deadline 0,25 s:

| Método | COMMIT nativo confirmado | Estado |
|---|---:|---|
| checked_commit, caso 105 | **0,2322 s** | CHANGED, helper retorna normalmente |
| _wrapped_commit, caso 112 | **0,2413 s** | CHANGED, helper retorna normalmente |

Al acercar el inicio al límite o superarlo, los casos 106–107 y 113–114 abortaron y conservaron ORIGINAL. No se afirmó poder resolver el orden de eventos a precisión infinitesimal; los casos fallidos siguientes cruzan el plazo por decenas de milisegundos y tienen verificación SQL independiente.

## 3. Escrituras tardías confirmadas

### Método de observación

Se envolvió únicamente la referencia nativa de commit de cada conexión de prueba para registrar **inicio y retorno exitoso reales**, antes de las comprobaciones post-commit del helper. Se registraron los epochs enviados y, tras aplicar la configuración, una consulta independiente dentro de esa conexión leyó clock_timestamp y current_setting. Estas lecturas confirman valores del GUC, sin presumir que describen el timer ya armado.

El llamador usa execute_tool_with_timeout real con límite 0,25 s. El Timer está activo pero con 0,15 s de retraso de planificación controlado; la cancelación asíncrona del supervisor conserva el mismo retraso. Esto reproduce un worker que sobrevive al TIMEOUT y permite evaluar la barrera del servidor sin depender de la puntualidad del cliente.

Cada caso lee el estado desde otra conexión inmediatamente al retorno del llamador y después de que el evento indique que **el worker terminó**. No se usa un sleep fijo para dar por definitivos los datos ni se infiere rollback de una excepción.

### A. Desfase aislado del reloj del cliente: +100 ms

No se cambió el reloj del host ni del contenedor. Solo el objeto de reloj utilizado por `app.db` devolvió epoch con +0,100 s; monotonic, el reloj del supervisor, la medición y el servidor permanecieron sin alterar. Es una prueba controlada de la comparación entre dominios temporales pedida por el usuario.

| Caso | Método | Configuraciones reconocidas por el servidor | Inicio COMMIT | TIMEOUT al llamador | COMMIT nativo confirmado | Estado al retorno / definitivo |
|---|---|---|---:|---:|---:|---|
| 102 | checked | 257ms a 0,0956 s; 255ms a 0,0974 s | 0,0977 s | **0,2591 s** | **0,2916 s** | ORIGINAL → **CHANGED** |
| 109 | wrapped | 255ms a 0,0975 s; 253ms a 0,0992 s | 0,0995 s | **0,2589 s** | **0,2931 s** | ORIGINAL → **CHANGED** |

El cliente transmite un epoch posterior al deadline real del supervisor. PostgreSQL calcula correctamente la diferencia contra **ese objetivo equivocado**. El cálculo SQL no detecta el desfase ni lo convierte en un deadline monotónico compartido.

El desfase negativo de 100 ms provocó abortos anticipados y conservó ORIGINAL, no una extensión. No se afirma que exista un desfase real en la instalación habitual: se demuestra que el código no impone ni valida la hipótesis necesaria para su garantía.

### B. Sin desfase: pausa al muestrear time.time

Caso **104, checked_commit**: reloj cliente/servidor sin offset. Se intercalan 40 ms antes de que `db.time.time()` lea el reloj real. Esto representa una pausa de planificación entre calcular rem_sec con monotonic y obtener la siguiente muestra de epoch. No se alteró la hora del sistema.

```text
0,0480 s  se envía la primera configuración, tras la pausa de muestreo
0,0524 s  servidor confirma configuración; current_setting = 240ms
0,0930 s  se envía el ajuste, tras otra pausa de muestreo
0,0956 s  servidor confirma configuración; current_setting = 197ms
0,0959 s  empieza COMMIT nativo y su trigger de 0,18 s
0,2500 s  deadline del supervisor
0,2595 s  el llamador recibe TIMEOUT; otra conexión aún lee ORIGINAL
0,2793 s  COMMIT nativo retorna éxito
           checked_commit lanza TimeoutError post-commit
           worker finalizado; otra conexión lee CHANGED
```

`time.time() + rem_sec` utiliza un saldo calculado antes de la pausa. El epoch ya queda extendido antes de viajar al servidor. En el caso wrapped equivalente, el límite temprano instalado por get_conn preservó ORIGINAL; **no se generaliza el fallo de este caso a ese método**. A-02 falla porque checked_commit sí confirmó fuera del plazo.

### C. Transacción con un timer previo de 1000 ms

Solo las conexiones de esta prueba arrancan con `options='-c transaction_timeout=1000'`; no se cambia la configuración global ni la de servicios habituales. Los relojes están alineados. El primer BEGIN arma ese límite; los helpers intentan reducirlo mediante su expresión epoch, pero la semántica observada de PostgreSQL no rearma el timer de esa transacción.

| Caso | Método | Inicio COMMIT | TIMEOUT al llamador | COMMIT nativo confirmado | Definitivo |
|---|---|---:|---:|---:|---|
| 151 | checked | 0,0996 s | **0,2633 s** | **0,2942 s** | **CHANGED** |
| 152 | wrapped | 0,1009 s | **0,2556 s** | **0,2857 s** | **CHANGED** |

En ambos, el primer SELECT al retorno aún veía ORIGINAL. La lectura después de terminar el trabajador y una verificación psql posterior vieron CHANGED. Este caso no depende de desfase de relojes ni de convertir un número relativo antes de una pausa: depende del timer activo al iniciar la transacción.

### Por qué el post-check no corrige la persistencia

En todos los fallos anteriores, el worker termina con **TimeoutError** porque las líneas post-commit de `db.py:463-468` comprueban supervisor/capacidad/deadline. Sin embargo la referencia nativa de COMMIT **ya retornó éxito**, y otra conexión observa el cambio. No queda una transacción pendiente que rollback pueda deshacer.

**A-02 FAIL:** se cumple exactamente el criterio de rechazo solicitado: el llamador informa TIMEOUT y la operación confirma posteriormente una modificación.

## 4. Normalización de excepciones

### Comportamientos correctos

- `test_g2_1_a02_active_conn_cancellation_on_slow_worker`: pasa en ambas suites y en una ejecución aislada, sin cambiar aserciones.
- Tres repeticiones independientes de SELECT pg_sleep(1) con deadline 0,10 s reciben cancelación PostgreSQL **TransactionTimeout / 25P04**, normalizada a **TimeoutError**; retornos ≈0,105–0,113 s.
- Consulta a tabla inexistente: **UndefinedTable / 42P01** permanece como tal.

### Error ajeno al deadline que sí se clasifica incorrectamente

Se terminó desde otra conexión **únicamente el backend PostgreSQL de un worker desechable propio**, mediante pg_terminate_backend(pid), mucho antes de su plazo de 2 s.

Resultado a **0,0338 s**:

- Error original real: **AdminShutdown, SQLSTATE 57P01**.
- Error al llamador: **TimeoutError**.
- El plazo de 2 s no había vencido; no fue una cancelación de su deadline.

`agent.py:664-675` y `:698-724` convierten AdminShutdown sin comprobar la procedencia de la cancelación. La captura por clase, y en otros errores por texto que contiene timeout, no garantiza la distinción solicitada entre límite propio e incidencia ajena.

**Normalización PARCIAL:** se corrigió la discrepancia QueryCanceled del test anterior, pero se necesita preservar los errores de infraestructura/administración que no proceden del deadline. El cambio mínimo es clasificar por causa/SQLSTATE y procedencia de la cancelación propia, no convertir indiscriminadamente el apagado de un backend en vencimiento.

## 5. Suite ordinaria y regresiones mínimas

Se ejecutó `tests -m "not live"` en procesos/bases separados. Proveedores simulados y contador independiente instalado después de fixtures; bloqueo de transportes externos. No se accedió a Google/Groq.

| Modo | Resultado | Tiempo | Intentos inesperados Google/Groq | Control positivo esperado |
|---|---|---:|---:|---:|
| Claves vacías | **91 passed, 1 skipped, 1 deselected** | 14,64 s | **0** | 1 |
| Claves sintéticas inválidas | **91 passed, 1 skipped, 1 deselected** | 15,49 s | **0** | 1 |

El control positivo del centinela se contabiliza por separado. La prueba live se excluyó explícitamente. E2E frontend se omite porque espera un servicio de Compose desde pytest host; no se presenta como ejecutado. Warning de deprecación AnyIO sin efecto en los resultados. No se reproduce «92 passed» del entorno de Antigravity porque aquí no se ejecutó ese frontend.

Regresiones preservadas:

- **M-02:** dos clasificaciones simultáneas con finalización escalonada: 700 después de la primera, 1400 al final, reservas 0. Idempotencia de manija, una sola conciliación entre ocho intentos concurrentes.
- **M-03:** COPY IN/OUT devuelve datos válidos; rows, chunks y write_row revocados levantan TimeoutError; solo persisten las dos filas autorizadas. Cursores y publicación serializada conservan sus comprobaciones.
- **G1:** 14 tests existentes pasan en ambos modos.
- **N-02:** orden y trazas reales PostgreSQL coinciden con llamadas simuladas 429 Gemini → Groq y terciario solo después de fallo Groq. No se probó accesibilidad externa real.
- **M-06:** configuración sin cambios relevantes y pruebas existentes aprobadas. No se repitió despliegue Docker de la aplicación.

## Limitación arquitectónica y alternativa mínima

Se está intentando equiparar **el presupuesto de espera del supervisor** con **la decisión transaccional del servidor** mediante relojes independientes y cancelaciones asíncronas. El epoch ayuda con el transporte, pero requiere una hipótesis de sincronización que no se verifica; el timer PostgreSQL tiene semántica propia; la cancelación puede llegar después de la confirmación. Una excepción posterior a COMMIT no cambia ese resultado.

No recomiendo otra sucesión de set_config/checks post-commit. La alternativa mínima coherente es **dejar de declarar cancelación definitiva por el simple vencimiento del supervisor**: esperar confirmación efectiva de aborto/commit antes de declarar la operación cancelada; si debe retornarse antes, informar operación pendiente/resultado desconocido y resolverla mediante estado durable/idempotencia, sin prometer que TIMEOUT implica ausencia de commit. Si el requisito exige además que cancelación y commit compitan con un orden estricto, esa decisión debe coordinarse transaccionalmente en el servidor bajo una única autoridad temporal, no inferirse desde una excepción del cliente.

Esto no requiere rediseñar reservas, COPY, proxy o centinela. Requiere decidir y aplicar el contrato de finalización de las escrituras. La normalización debe conservar, adicionalmente, los errores administrativos ajenos al límite propio.

Con el contrato obligatorio de esta auditoría, **NO APROBADO**. No corresponde recomendar el cierre de G2.1 mientras persista la confirmación posterior al TIMEOUT demostrada.

## Evidencia conservada

En la raíz temporal indicada:

| Scripts/resultados | Finalidad |
|---|---|
| registered_scheduling.py, registered_scheduling_results.json | Casos 61–64 |
| balanced_config_checks.py, balanced_config_results.json | Casos 81–84 |
| transaction_checks.py, transaction_results.json | Repeticiones secuenciales/concurrentes y servidor aislado |
| final_config_checks.py, final_config_results.json | Pausas después de configurar y antes de COMMIT |
| clock_commit_checks.py, clock_commit_results.json | Epochs, clock_timestamp/GUC, commit nativo, desfases y muestreo |
| prearmed_transaction_checks.py, prearmed_results.json | Timer previo y confirmación tardía |
| semantics_normalization.py, semantics_normalization_results.json | Semántica real, self-cancel y clasificación de errores |
| run_suite.py, network_guard.py, suite_blank.log, suite_synthetic.log, network_blank.json, network_synthetic.json | Suite y hermeticidad |
| focused_normalization.log | Test de cancelación pedido, aislado |
| functional_results.json, copy_reservation_results.json, n02_results.json | Regresiones mínimas |
| final_states.txt, postgres_timeout_events.log | Lecturas psql definitivas y mensajes de servidor |
| head.zip / src | Copia exacta congelada |

Cada script usa PYTHONPATH de la copia, URL del puerto 55495/base correspondiente y archivos propios. Los que crean tablas/trigger necesitan base nueva para repetir. Las pausas, clocks y observadores se inyectan únicamente desde scripts externos; no se editan módulos ni se simula el resultado del commit. Los tiempos de configuración son acuses/lecturas posteriores de ejecución, no una afirmación de medir un ciclo exacto de CPU del backend. Los commits confirmados y estados definitivos se verifican por separado.

## Cierre y huellas

Se detuvo y eliminó únicamente `civia_cdc6_pg`, su red y volumen exclusivos. Scripts y resultados permanecen en la raíz temporal. HEAD conserva el SHA auditado y el único archivo nuevo del repositorio original es este informe. Sin modificaciones de producción, servicios habituales o publicaciones.

SHA256:

| Archivo | Huella |
|---|---|
| head.zip | `CC28DECF4380401DE859821F69EE82CC37083D88DF5A2393C9AB4FCA0BDC14A3` |
| clock_commit_results.json | `501263D4F4412CB74FE53CB20B0A49ED9093ECFC4362F31CF5286E66F9BC7E12` |
| prearmed_results.json | `05E2314227A6F6051C869FB1346E20868FCA6404360575E0F1D085FAC6B668B3` |
| semantics_normalization_results.json | `B70F0FBED4B844D9CAB243D28DB25BD2CEFB99BE110D930FF8C4286651F98E23` |
| network_blank.json / network_synthetic.json | `501CB2994A70F33C4ECFD26E43D446384AD4FA391D8944DEEEDD06239FFD3E3E` |
| final_states.txt | `3247C2ACBD80A94E9DDCD48AB9EC3F361BB1350661571B33DFECEBE0656B5F92` |
