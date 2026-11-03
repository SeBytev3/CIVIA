# CIVIA — verificación independiente G2.1.3

Fecha: 2026-11-02, America/Bogota.

**Commit exacto congelado:** `4a99705622dbb53204d1dba9057637952822fb04`, rama `fix/auditoria-final`. Referencias: `docs/auditoria_codex_g2_1_2_d07a1e5.md` y adenda G2.1.3 de `docs/remediacion_g2_1.md`.

**Dictamen global: NO APROBADO.** M-02 y COPY pasan los contraejemplos pendientes. **A-02 FAIL:** se confirmaron escrituras después del TIMEOUT en PostgreSQL 17 real, con conexiones registradas, tanto por checked_commit como por _wrapped_commit. **Hermeticidad FAIL:** persisten intentos a proveedores con claves sintéticas y el fixture del proyecto permite que el producto absorba su excepción.

Se revisaron exclusivamente los cuatro defectos solicitados y las regresiones mínimas. No se revisó ni ejecutó Autopilot, ni se modificó producción. Sin commits, push, merge o cambio de rama.

## Matriz

| Control | Resultado | Evidencia ejecutada |
|---|---|---|
| M-02 — conciliación concurrente | **PASS en el alcance solicitado** | Dos clasificaciones reales del código mediante executor, presupuesto 6000, 700 cada una y finalización escalonada: 700 tras la primera, **1400 finales**, reserva final **0**. Ocho conciliaciones concurrentes de la misma manija: solo una aplicada. |
| M-03 — COPY funcional | **PASS en el alcance solicitado** | PostgreSQL 17: COPY IN con write_row persiste dos filas; COPY OUT con rows e iteración devuelve datos. rows, iteradores y write_row rechazan nuevas operaciones después de revoke. Cursores encadenados y publicación serializada conservan sus PASS. |
| A-02 — integridad | **FAIL** | Cuatro repeticiones finales, con conexiones registradas y variaciones controladas de planificación: el llamador recibe TimeoutError a 0,254–0,266 s; el commit se confirma a 0,326–0,337 s, para deadline **0,25** y trigger diferido **0,18**. Estado final **CHANGED**, no ORIGINAL. |
| Hermeticidad | **FAIL** | Claves vacías: cero intentos inesperados. Claves sintéticas: **seis intentos** Google/Groq desde test_agent_tools_and_unanswerable_query. Ninguno salió a red; el fixture los bloqueó, pero su excepción fue absorbida. Sin la aserción independiente, ese test pasa. |
| G1, regresión mínima | **PASS en suite ejecutada** | Sus 14 pruebas pasan con claves vacías y sintéticas; el mock multimodal G1 corrige los intentos que aparecían en la auditoría anterior. |
| N-02, regresión mínima | **PASS, transporte simulado** | Primario 429 → Groq; Groq 400 → Gemini terciario. Adaptadores reales con MockTransport y trazas PostgreSQL coinciden en orden/modelo. |
| M-06, regresión mínima | **PASS de configuración y pruebas existentes** | Configuración de proxy/Compose sin cambios respecto de d07a1e5; pruebas de confianza/cuota pasan. No se repitió el despliegue histórico ni se afirma un nuevo arranque con la subred original. |

Los PASS se limitan a los comportamientos descritos, sin certificar proveedores externos ni código arbitrario.

## Entorno congelado y desechable

El árbol original estaba limpio y HEAD coincidía con el commit solicitado. Se importó únicamente la copia obtenida con git archive, en:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-4a99-eda646f3cf4e4e6cb14d7334592bb7ff`

Se utilizó **PostgreSQL 17.11 real**, imagen local postgres:17-alpine, en el contenedor exclusivo `civia_4a99_pg`, red `civia_4a99_pgnet` y volumen `civia_4a99_pgdata`. Puerto publicado únicamente en `127.0.0.1:55491`. Bases nuevas: `test_4a99_independent`, `test_4a99_blank`, `test_4a99_synthetic` y bases que crean los tests dentro de ese mismo servidor. No se conectó a servicios habituales.

CPython 3.13.18, psycopg 3.2.6 y dependencias del backend reutilizadas. Los binarios PostgreSQL portables de la auditoría anterior ya no estaban disponibles; el intento inicial de usarlos falló antes de abrir un servidor. Se sustituyó esa preparación por el contenedor exclusivo y no se contó como fallo del producto.

No se copió .env ni se usaron claves reales. Proveedores, respuestas y consumos fueron sintéticos; las transacciones, COPY, triggers, cancelaciones y lecturas SQL son reales. Administradores efímeros CSPRNG sin imprimirlos. Uploads y TEMP/TMP dentro de la raíz de auditoría. Los scripts y resultados se conservan fuera de producción.

## 1. A-02 — prioridad: escritura tardía confirmada

### Qué sí comprueba la corrección

`checked_commit` y `_wrapped_commit` envían SET LOCAL transaction_timeout antes de COMMIT. En repeticiones normales el motor sí aborta transacciones; no es una configuración ficticia.

`transaction_checks.py` ejecutó **18 casos** independientes sobre filas propias, con constraint trigger `AFTER UPDATE DEFERRABLE INITIALLY DEFERRED` que duerme **0,18 s** al escribir CHANGED, con deadline total **0,25 s**:

- Seis secuenciales, esperas previas de 0,08 / 0,15 / 0,20 s y ambos métodos.
- Cuatro concurrentes con cuatro trabajadores y filas distintas.
- Cuatro con el Timer de cancelación Python sustituido por un objeto inerte, para aislar el efecto real del límite de servidor; no se simula SQL ni commit.
- Cuatro con pausa de planificación de 0,13 s antes de transmitir SET LOCAL, usando entradas a commit más tardías.

Los 18 conservaron ORIGINAL. En los cuatro casos sin Timer de Python se observó TimeoutError y ORIGINAL; el log real de PostgreSQL registra **terminating connection due to transaction timeout**. Esto confirma la eficacia del GUC en esos casos, separadamente del cancel del cliente.

Cada estado se lee desde otra conexión al terminar el trabajador, sin sleep fijo de asentamiento. Que estas repeticiones pasen no cubre el intervalo obsoleto del siguiente caso.

### Secuencia reproducible que falla

Archivos: `registered_scheduling.py`, `registered_scheduling_results.json`.

La prueba usa la herramienta y executor reales, conexiones registradas (get_conn en wrapped; registro explícito en checked), el trigger real de 0,18 s y deadline 0,25. Se introducen únicamente dos pausas de planificación deterministas en el reproductor:

1. **0,13 s** entre calcular el tiempo restante y transmitir el SET LOCAL que ya contiene ese valor calculado.
2. **0,15 s** antes de despachar la cancelación asíncrona del llamador, simulando retraso de planificación de ese hilo. Se conserva su función real después de la pausa. El Timer interno de commit no se desactiva en estas repeticiones.

No se altera la respuesta de PostgreSQL, el resultado de commit ni la consulta de verificación. No es una carga masiva ni una carrera contra otro sistema: es una variación local controlada de planificación, requerida por esta revisión.

Ejemplo checked_commit, fila 61:

```text
deadline absoluto del llamador:       0,2500 s
entrada a commit:                    0,0125 s
valor calculado: transaction_timeout = 237 ms
pausa antes de transmitir SET:        0,1300 s
SET termina de aplicarse:             0,1440 s
llamador recibe TimeoutError:         0,2662 s
otra conexión observa:               ORIGINAL
worker confirma COMMIT:              0,3345 s
otra conexión, tras terminar worker:  CHANGED
```

El intervalo de 237 ms se instala cuando ya transcurrieron unos 144 ms. No representa el saldo real del deadline original. El Timer interno también se inicia después de SET usando el saldo calculado antes de la pausa. Cuando la cancelación asíncrona del llamador se retrasa, ambos límites dejan espacio para completar el trigger y confirmar después del TIMEOUT.

| Fila | Método | SET calculado | SET aplicado a | TIMEOUT del llamador | COMMIT confirmado | Estado final |
|---|---|---:|---:|---:|---:|---|
| 61 | checked_commit | 237 ms | 0,1440 s | 0,2662 s | **0,3345 s** | **CHANGED** |
| 62 | _wrapped_commit | 230 ms | 0,1524 s | 0,2619 s | **0,3368 s** | **CHANGED** |
| 63 | checked_commit | 239 ms | 0,1420 s | 0,2538 s | **0,3265 s** | **CHANGED** |
| 64 | _wrapped_commit | 237 ms | 0,1450 s | 0,2646 s | **0,3312 s** | **CHANGED** |

En las cuatro, el primer SELECT independiente todavía veía ORIGINAL y el SELECT tras el evento de fin del trabajador veía CHANGED. No se esperó artificialmente para ocultar una escritura incorrecta: precisamente se comprobaron ambos momentos. Una nueva conexión psql confirmó después que las cuatro filas seguían CHANGED.

Una exploración previa sin registro explícito de la conexión raw también encontró escrituras tardías, pero **no se utiliza como base del FAIL**: la tabla anterior sí incluye conexiones registradas y ambos caminos del proyecto.

### Causa y corrección estrictamente necesaria

Referencias: `backend/app/db.py:350-395` y `:441-485`.

El saldo se calcula antes de un viaje a la BD, pero se instala como intervalo relativo después. El temporizador de cancelación usa ese mismo saldo antiguo al arrancar más tarde. No se garantiza un deadline absoluto mediante un límite relativo rebajado únicamente antes de una espera que puede demorarse.

**Corrección necesaria:** que el límite efectivo del motor quede anclado al vencimiento original y no se prolongue al configurar/reconfigurar el GUC. Establecer la restricción antes del trabajo crítico, revalidar tras las esperas y abortar si ya no puede asegurarse el saldo; alinear la cancelación con el deadline absoluto, no con un intervalo antiguo. Si el diseño necesita un plazo absoluto evaluado en BD, debe implementarlo explícitamente y verificar el desfase/tiempo de transporte. No basta con esperar al hilo ni con cambiar la cota de latencia del test.

Los datos anteriores prueban la escritura tardía. No se presenta como fallo de durabilidad WAL ni se atribuye a un usuario remoto acceso SQL: el defecto está en la garantía transaccional de las herramientas bajo la planificación reproducida.

**A-02 FAIL.** El tiempo de respuesta y la integridad son propiedades distintas: recibir TimeoutError a tiempo no deshace un commit que el trabajador confirma después.

## 2. M-02 — propiedad y conciliación exactamente una vez

Se repitió el contraejemplo anterior usando dos herramientas de clasificación reales mediante ThreadPoolExecutor, un tracker compartido con presupuesto **6000** y proveedor multimodal simulado que declara **600+100=700** por llamada.

Ambas llamadas entran al router y se retienen con eventos. Se libera primero una mientras la otra conserva su reserva:

| Punto | Uso acumulado | Reserva pendiente |
|---|---:|---:|
| Tras terminar la primera clasificación | **700** | **732**, propiedad de la segunda |
| Tras terminar la segunda | **1400** | **0** |

Las dos completaron análisis; no reaparecieron 2100 tokens. Las 732 reservadas corresponden a la estimación del payload, no al uso simulado de 700, que se concilia después.

`TokenReservation` proporciona identificadores distintos, referencia al tracker propietario y lock propio para su estado. La herramienta pasa su manija al router y su finally solo considera esa manija, no las reservas globales de otros trabajadores (`agent.py:52-108`, `:517-533`).

Prueba independiente adicional: dos reservas de 700; ocho hilos intentan conciliar la primera simultáneamente. **Una** conciliación devuelve True, las restantes no cargan uso. Uso=700, reserva pendiente=700 de la segunda. Liberar la primera ya conciliada devuelve False; liberar la segunda devuelve True una vez y False después; estado final uso=700/reserva=0. Se verificaron IDs distintos y tracker propietario correcto.

**PASS** para el doble cargo, idempotencia y coordinación solicitados. No se añadieron hallazgos sobre otros aspectos del presupuesto fuera del alcance.

## 3. M-03 — COPY funcional y revocación

`copy_and_reservations.py` ejecutó PostgreSQL real con una tabla sintética propia:

- COPY IN, capacidad vigente: write_row inserta `(1,A)` y `(2,B)` y commit válido.
- COPY OUT, capacidad vigente: `list(cp.rows())` devuelve las dos filas.
- Iteración directa sobre cp devuelve los chunks `1\tA\n` y `2\tB\n`.
- Iterador rows adquirido antes de revoke: permite la primera fila y el siguiente next lanza **TimeoutError**.
- Iterador de chunks adquirido antes de revoke: su siguiente next lanza **TimeoutError**.
- COPY IN abierto con capacidad vigente: write_row posterior a revoke lanza **TimeoutError**. La transacción de esa prueba se cierra sin commit y la tabla conserva solo las dos filas válidas iniciales.

Se corrige el AttributeError anterior: el proxy conserva ahora el objeto Copy obtenido de __enter__ y envuelve los iteradores para comprobar cada avance (`db.py:114-183`).

Regresiones mínimas, sin repetir la auditoría histórica: execute encadenado y conn.execute siguen devolviendo proxies y rechazan SQL revocado. Publicación de archivo con replace real y revoke concurrentes conserva el orden **replaced → revoked**, termina ambos hilos y rechaza una nueva escritura tras revocación. No se exige terminar un hilo arbitrario de CPython; se comprobó la frontera de efectos solicitada.

**PASS** en el alcance COPY/cursores/publicación. Esto no cancela el FAIL independiente de persistencia A-02.

## 4. Hermeticidad y suite completa

Se ejecutaron todos los tests backend congelados con claves vacías y sintéticas, en bases separadas. El contador independiente envuelve Client.send **después de instalarse las fixtures**, para detectar incluso intentos que estas bloqueen. HTTPTransport/socket no locales permanecen bloqueados. No se usaron claves reales ni se permitió salir a proveedores.

El guard independiente convierte cualquier intento inesperado en fallo al terminar el test, fuera del manejo de excepciones del producto. Se separa la petición deliberada del test que verifica el propio guard, que es un control positivo, no tráfico inesperado.

| Modo | Resultado con el criterio independiente | Intentos inesperados Google/Groq |
|---|---|---:|
| Claves vacías | **83 passed, 2 skipped**, 11,37 s | **0** |
| Claves sintéticas | **83 passed, 1 failed, 1 skipped**, 11,49 s | **6** |

Los intentos sintéticos proceden de `test_ai_and_agent.py::test_agent_tools_and_unanswerable_query`: dos consultas, cada una intenta Gemini → Groq → Gemini. Sus adaptadores de **turno de agente** no están sustituidos por la fixture multimodal.

El fixture global `backend/tests/conftest.py:101-119` sí bloquea cada envío, pero lanza **RuntimeError**, que el producto captura para degradar a SQL. No se alcanza el transporte externo. Una barrera que el producto absorbe no hace fallar por sí misma la prueba ordinaria.

### Comprobación de que la excepción puede ser neutralizada

Se repitió únicamente ese test con claves sintéticas y el mismo fixture congelado, conservando el contador pero desactivando **solo la aserción final del auditor**:

**1 passed**, 1,22 s; **los mismos seis intentos registrados**; cero solicitudes a red real.

Así se distingue el fallo del criterio independiente del resultado habitual: las aserciones del test original pueden pasar aunque el producto haya absorbido el bloqueo. La prueba intencional que verifica el guard también pasa, pero solo demuestra que la excepción existe, no que sea imposible absorberla en otro recorrido.

**Correcciones mínimas:** simular incondicionalmente también los adaptadores de turnos principales del agente en la suite ordinaria. Hacer que la violación de red sea un fallo de test que no pueda neutralizarse dentro del producto, por ejemplo mediante el control/finalizador de intentos fuera del request, o un mecanismo de fallo pytest adecuado. Conservar el control positivo del guard y distinguirlo de intentos accidentales.

Omisiones: E2E busca el servicio local `frontend` desde pytest host y se omite; no se desplegó otro frontend por quedar fuera de los cuatro defectos. La prueba live opcional se omite sin clave y no hace inferencia real cuando tiene marcador sintético. Warnings: deprecación AnyIO y, en el pase sintético, aviso de Pluggy por la aserción de auditoría al terminar el hook; no son defectos de CIVIA.

## Regresiones mínimas

- **G1:** sus 14 pruebas pasan en ambos modos; no se observan intentos de proveedor desde esa suite, a diferencia de d07a1e5. No se repitieron ataques históricos innecesarios.
- **N-02:** cuatro escenarios de transporte simulado y trazas reales PostgreSQL: primario 429 → Groq; 400 de Groq → Gemini terciario; JSON inválido primario → Groq; turno de agente 429 → Groq. Se preservan orden y modelo efectivo, sin Gemini oculto. No se verificó disponibilidad real de modelos.
- **M-06:** configuración Compose, confianza de proxy y escritor de archivos no cambiaron respecto de d07a1e5; las pruebas existentes de IP y cuota pasan. Este PASS es de regresión mínima por tests/diff, no una nueva certificación de la topología Docker desplegada.

## Evidencia conservada y reproducción

En la raíz temporal indicada:

| Script | Evidencia |
|---|---|
| functional_checks.py | functional_results.json: 1400 exactos, cursores y serialización de archivos |
| copy_and_reservations.py | copy_reservation_results.json: COPY IN/OUT, revocación e idempotencia de reservas |
| transaction_checks.py | transaction_results.json, transaction.log: 18 repeticiones, concurrencia y prueba del servidor sin Timer |
| registered_scheduling.py | registered_scheduling_results.json: cuatro escrituras tardías con registro de conexiones |
| scheduling_check.py | scheduling_results.json: exploración previa, no base del dictamen final |
| run_suite.py, network_guard.py | suite_blank.log, suite_synthetic.log, network_blank.json, network_synthetic.json |
| control aislado del guard | guard_swallow.log, guard_swallow_results.json |
| n02_probe.py | n02_results.json, n02.log |
| servidor real | postgres_timeout_events.log; tablas sintéticas mientras duró el contenedor |

La copia congelada es head.zip/src. Scripts importan `src` y `src/backend`, DATABASE_URL de puerto 55491/base correspondiente, claves vacías o marcador sintético, y uploads/TEMP propios. Los reproductores con creación de tabla/trigger requieren una base nueva para repetir desde cero. No se editaron los módulos auditados ni sus tests; las pausas y contadores son instrumentación temporal externa.

Los casos prioritarios registran el instante de cálculo/aplicación de SET LOCAL y el retorno exitoso del COMMIT real. Se verifica por conexión independiente inmediatamente al retorno del llamador y al evento de fin del worker, sin un sleep de asentamiento que sustituya la comprobación.

## Dictamen y correcciones necesarias

1. **A-02:** eliminar la ampliación efectiva del plazo al instalar un intervalo de tiempo restante obsoleto. Repetir las cuatro secuencias registradas hasta demostrar ORIGINAL sin depender de la puntualidad del cancel del cliente.
2. **Hermeticidad:** mocks para turnos principales y guard con fallo no neutralizable por el producto.

No se proponen cambios adicionales fuera de los defectos demostrados. M-02 y COPY quedan reconocidos como corregidos en el alcance ejecutado. **G2.1.3 NO APROBADO; G2.1 no debe declararse cerrado ni recomendarse avanzar como bloque aprobado mientras persista A-02.**

## Cierre y huellas

Se detuvo y eliminó únicamente el contenedor PostgreSQL `civia_4a99_pg`, su volumen y su red exclusivos. Las evidencias JSON/scripts permanecen en la raíz temporal. El único archivo nuevo del repositorio original es este informe y HEAD conserva el SHA auditado. No se tocaron servicios habituales ni se publicaron cambios.

SHA256:

| Archivo | Huella |
|---|---|
| head.zip | `92A753BC8DB99338270864071AE710EEA82D5E2CF4C2CD5F30579C5464853198` |
| registered_scheduling_results.json | `B44583F8F66050261BB66EDBEF658ACD0D55B9DEE2B0FCCB4841B982F2CB5202` |
| transaction_results.json | `5E26AD41AC542C47B55AB5EEDCE7ACDC6E0A0C75E25B3F3AF167863197B135D6` |
| functional_results.json | `DF723C9C6E632B6CE9189DB4D309932265CDCCD45540C819EB0D63A52424BF67` |
| copy_reservation_results.json | `66AA5D558AA4B270B7342F8136E8A1CA31FCA6D1C288562FA93379B2D10C83D2` |
| network_synthetic.json | `30354BF19E64634C4A8E49ABBD846A008E3DDF95CAA5F804EA8771B50337BA76` |
| guard_swallow_results.json | `502F0EB0DE22DB7F2F4E0B31DB91B410ECC5AB6BAB690ACE56F3E2BA8139AAF1` |
