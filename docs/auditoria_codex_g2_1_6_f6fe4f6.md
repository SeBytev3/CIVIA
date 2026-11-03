# CIVIA — aceptación independiente G2.1.6

Fecha: 2026-11-03, America/Bogota.

**Commit exacto:** `f6fe4f61801d701f7cf5cd66d94ca2fd0ee7159a`, rama `fix/auditoria-final`. Se leyeron íntegramente el informe `docs/auditoria_codex_g2_1_5_cdc646b.md`, las secciones 13–15 de `docs/remediacion_g2_1.md`, el bloque G2.1.6 de `docs/estado.md` y `backend/migrations/004_operation_records.sql`.

## Dictamen

**NO APROBADO bajo el NUEVO contrato.** Se acepta conceptualmente que un commit iniciado pueda terminar después del límite del supervisor y que se devuelva PENDING. Ese recorrido funciona en una prueba independiente. Los defectos son otros: se confirma negocio sin marcador obligatorio; una consulta comunica ABORTED antes de que el worker termine COMMITTED; se infiere COMMITTED de una propuesta ajena; hay operaciones sin autorización y reintentos que duplican efectos o pierden su identidad durable.

No se exige rollback inmediato a 0,25 s ni terminación forzosa de hilos. No se revisó, ejecutó o modificó Autopilot. Sin modificaciones de producción, commits, push, merge o cambio de rama. El único archivo nuevo del repositorio original es este informe.

## Matriz solicitada

| Área | Resultado | Evidencia ejecutada |
|---|---|---|
| 1. Estados y atomicidad | **FAIL** | Fallo SQL real al marcar COMMITTED: SAVEPOINT permite confirmar el negocio y devolver éxito, dejando PENDING. Reconciliación posterior lo cambia a ABORTED pese al efecto persistido. Sin migración 004 también se confirma negocio sin registro. |
| 2. Reconciliación y recuperación | **FAIL** | GET devuelve ABORTED mientras un worker aún válido espera; al liberarlo termina COMMITTED. Una operación nunca ejecutada se marca COMMITTED por otra propuesta del mismo reporte. Hay PASS de recuperación cuando el marcador atómico existe. |
| 3. Autorización e idempotencia | **FAIL** | GET anónimo devuelve resultado privado sintético y clave de idempotencia. Misma clave concurrente: dos escrituras, dos IDs, solo un registro durable. Dos propuestas reales duplicadas. Reintento de COMMITTED sin result_payload vuelve a escribir. |
| 4. Propagación PENDING | **FAIL** | Camino normal devuelve OperationPendingError e ID. Dentro del worker, esa subclase se captura como FuturesTimeoutError y se degrada a TimeoutError sin ID; API real responde TIMEOUT/null. Ventana antes del registro en vuelo permite también TIMEOUT sin ID con commit durable. |
| 5. Clasificación de excepciones | **PARCIAL** | QueryCanceled y TransactionTimeout del plazo se normalizan; AdminShutdown 57P01 y UndefinedTable 42P01 se preservan. Pero un transaction_timeout de sesión de 50 ms, ajeno al plazo local de 2 s, se atribuye a ese deadline. |
| 6. Regresiones | **PARCIAL** | M-02, COPY, M-06, G1 y N-02 conservan las comprobaciones mínimas ejecutadas. Cero intentos externos inesperados. Suite vacía: 97 PASS; sintética: 95 PASS y dos fallos de temporización, detallados abajo. |

## Versión, aislamiento y método

HEAD y la referencia solicitada coincidían; árbol limpio al empezar. Se creó una copia congelada con git archive en:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-f6fe-60016e47c7df4cda8630685cb9ff54cf`

PostgreSQL **17.11 real**, contenedor `civia_f6fe_pg`, red `civia_f6fe_pgnet` y volumen `civia_f6fe_pgdata`, todos exclusivos. Puerto publicado solo en `127.0.0.1:55497`. Bases nuevas `test_f6fe_independent`, `test_f6fe_blank`, `test_f6fe_synthetic`, `test_f6fe_no004` y las creadas por las suites en ese mismo clúster. El proxy de fallo de transporte escuchó temporalmente solo en `127.0.0.1:55498` y reenviaba exclusivamente al PostgreSQL propio.

CPython 3.13.18, psycopg 3.2.6 y dependencias del backend reutilizadas. Sin .env, claves reales o datos privados. Administrador CSPRNG efímero sin imprimirlo. Payloads y archivos sintéticos. Proveedores sustituidos o HTTP MockTransport y bloqueo externo. SQL, restricciones, triggers, commits, pérdidas de conexión y lecturas independientes PostgreSQL son reales.

Los instrumentos y scripts están fuera de producción. Las pausas/eventos controlan intercalados, no sustituyen el resultado SQL. Para cada resultado definitivo se espera el fin del worker o la desaparición comprobada de su backend. No se deduce persistencia a partir de una excepción ni de un sleep de asentamiento.

## 1. Registro opcional: el SAVEPOINT rompe la atomicidad exigida

**Referencias:** `backend/app/db.py:121-175`, `:178-204`, `:680-704`; migración 004.

### Subcontrol positivo

Una herramienta sintética usa el executor y get_conn reales para incrementar una fila y ejecutar commit. Sin fallos, la fila cambia una vez y operation_records queda COMMITTED. La actualización del marcador dentro de la transacción funciona en ese recorrido.

### Fallo SQL del marcador

Se creó únicamente en la BD desechable un trigger sobre operation_records que rechaza la transición a COMMITTED para un tipo sintético de operación. No se simulan los resultados del commit ni se modifica el helper.

Resultado:

```text
intención durable:                  PENDING
UPDATE del negocio:                 realizado dentro de la transacción
UPDATE del marcador COMMITTED:      falla con excepción PostgreSQL
ROLLBACK TO SAVEPOINT op_rec_sp:     revierte solo el marcador
COMMIT del negocio:                 éxito
retorno de execute_tool:            éxito
registro al terminar:               PENDING
reconcile_operation:                ABORTED
fila de negocio desde otra conexión: incremento persistido = 1
```

El SAVEPOINT no vuelve atómico lo que permite ignorar: conserva la escritura de negocio y descarta la evidencia que debía acompañarla. El intento posterior de mark_operation_committed, en conexión separada, también falla y su excepción se absorbe.

### Migración 004 ausente

En otra base propia se aplicaron solo las migraciones 001–003. La intención devuelve un diccionario PENDING aunque su INSERT falla por tabla inexistente. El helper captura el fallo del marcador y la herramienta termina con éxito: negocio incrementado una vez y **operation_records inexistente**.

Esto no afirma que el arranque limpio normal omita 004; normalmente run_migrations la crea. Demuestra que el camino real de escritura degrada silenciosamente cuando falta o no puede usar su registro, condición expresamente prohibida en esta aceptación.

**Corrección mínima:** exigir intención efectivamente persistida antes de ejecutar; no capturar como éxito el fallo del marcador ni un UPDATE que afecta cero filas. Un error de trazabilidad debe abortar la transacción de negocio. Verificar la disponibilidad de la migración en la preparación real; no usar compatibilidad silenciosa con tablas ausentes.

## 2. Reconciliación: certezas falsas y transiciones no seguras

**Referencia:** `backend/app/db.py:279-344`.

### ABORTED antes de terminar el worker, seguido de COMMITTED

La herramienta registra su intención y permanece esperando un evento antes de abrir su conexión de negocio; su deadline es 3 s y no ha expirado. Se consulta su operation_id mediante **GET real de la API**:

1. La operación está durablemente PENDING, todavía sin backend_pid.
2. GET llama a reconcile_operation, que interpreta ausencia de PID como aborto: **HTTP 200 / ABORTED**.
3. Se libera el worker, aún dentro de plazo.
4. Este incrementa negocio y checked_commit cambia el registro a COMMITTED.

**Observado:** ABORTED comunicado → COMMITTED durable; worker exitoso; incremento=1. No intervienen errores SQL ni clocks desfasados. El mismo diseño que ya declaraba aborto permite después confirmar.

### COMMITTED por una propuesta de otra operación

Se crea una propuesta real de aprobación para un reporte. Luego se registra otra operación PENDING de tipo proponer_actualizacion_critica, apuntando al mismo reporte pero con otra decisión; esa segunda operación **no se ejecuta**.

Al reconciliarla, el sistema encuentra la propuesta anterior por report_id y la marca **COMMITTED**. No comprueba que la propuesta lleve el operation_id de la operación evaluada ni que coincida su payload.

### Consultas concurrentes y UNKNOWN

Seis GET concurrentes de una intención sin backend no repiten la escritura de negocio (contador=0), pero uno guarda ABORTED sin evidencia suficiente mientras otros devuelven la instantánea PENDING. La persistencia de un aborto falso, no la mera diferencia de instantáneas concurrentes, es el defecto de integridad.

Una operación marcada explícitamente UNKNOWN permanece UNKNOWN al consultarla: ese subcontrol pasa. Sin embargo, los caminos automáticos de desconexión probados dejan PENDING y el reconciliador usa por defecto ABORTED. La función mark_operation_unknown existe, pero su mera existencia no hace conservadora esa resolución.

### Recuperación y fallos reales de conexión: resultados separados

| Escenario ejecutado | Observación |
|---|---|
| Commit posterior al timeout, recorrido normal en vuelo | OperationPendingError con ID; commit real posterior; negocio +1; marcador COMMITTED. **Correcto bajo el nuevo contrato.** |
| Aborto real durante commit | Negocio sin cambios; registro ABORTED después de terminar el worker. En esta reproducción la evidencia SQL concuerda. |
| Conexión cerrada antes del commit | OperationalError preservado; negocio sin cambios; PENDING → ABORTED por reconciliación. El resultado coincide aquí, aunque el criterio general de PID es inseguro. |
| Pérdida del backend durante COMMIT | pg_stat_activity confirmó **active / COMMIT / PgSleep**. Se terminó solo ese backend desechable: AdminShutdown preservado, negocio=0, registro PENDING → ABORTED. |
| Pérdida de ACK de COMMIT | Proxy TCP propio reenvía COMMIT a PostgreSQL y elimina su respuesta real. Cliente recibe OperationalError; negocio=1 y marcador COMMITTED; reconciliación conserva COMMITTED. **Correcto con marcador atómico presente.** |
| Desaparición/reinicio del proceso escritor | Se termina el proceso Python propio mientras su backend está active/COMMIT/PgSleep y el registro visible es PENDING. Backend desaparece; negocio=1. Una API cargada en otro proceso responde 200/COMMITTED. **Recuperación durable positiva en ese recorrido.** |
| Nuevo proceso con intención PENDING sin PID | reconcile_operation devuelve ABORTED, sin evidencia adicional del resultado. La ausencia de memoria/PID sigue sustituyendo una prueba de aborto. |

La prueba de reinicio usa procesos Python separados y el código real de la API; no reinicia servicios habituales ni afirma haber desplegado un nuevo Uvicorn completo.

**Corrección mínima:** resolver solo con evidencia vinculada inequívocamente al operation_id. No usar «PID ausente» o «existe alguna propuesta de ese reporte» como prueba de aborto/commit. Mientras falte evidencia, conservar UNKNOWN/PENDING. Usar transiciones condicionadas y evitar que un aborto comunicado se pueda sobrescribir por una ejecución aún activa. La reconciliación requiere primero que el marcador obligatorio del apartado 1 sea una invariancia real.

## 3. Endpoint sin autorización y reintentos no seguros

### Lectura pública de una operación privada

**Referencias:** `backend/app/main.py:606-626`, `backend/app/schemas.py:134-146`; migración 004 sin propietario/ámbito de acceso.

Se ejecutó una operación con un resultado interno sintético y una clave de idempotencia propia. Un TestClient sin credenciales consultó su UUID:

- **HTTP 200**.
- result_payload contiene la nota privada sintética.
- idempotency_key se entrega completa.
- No hay dependencia de autorización ni comprobación de propietario.

El UUID se usa como único conocimiento necesario, no como una capacidad autenticada. proposed_payload no se devuelve directamente en este endpoint; **no se afirma que ese campo concreto se filtrara por GET**. Sí se demostró exposición de result_payload y la clave reutilizable.

### Payload diferente con la misma clave

**Referencias:** `agent.py:720-742`; `db.py:135-175`.

Una segunda llamada con la misma clave pero otro objetivo/payload recibió el resultado cacheado de la primera, sin conflicto ni autorización vinculada al solicitante. El objetivo solicitado no se escribió; tampoco se rechazó el uso incoherente de la clave. La tabla no almacena dueño ni fingerprint para validar esa relación.

### Dos llamadas concurrentes con la misma clave

Se sincronizan dos consultas iniciales para que ambas observen ausencia de registro. Se conserva la BD real y su UNIQUE:

```text
escrituras de negocio:                   2
operation_id distintos retornados:       2
registros durables para la misma clave:  1
IDs retornados existentes en la tabla:   [true, false]
```

El UNIQUE protege la fila, pero su conflicto se absorbe; además execute_tool ignora el registro devuelto por register_operation_intent. Continúa con el UUID nuevo y ejecuta de nuevo.

Se repitió con la herramienta real de propuestas, controlando el intercalado de sus SELECT «no hay propuesta pendiente». Resultado: **dos filas PENDING y dos approval_id**, para la misma clave y reporte. Ambas siguen requiriendo aprobación humana; el estado operativo del reporte permanece CONFIRMED. No se afirma una escritura administrativa directa, sino duplicación de propuestas.

### COMMITTED sin result_payload: reintento secuencial duplicado

Un commit tardío legítimo devuelve PENDING y termina COMMITTED. El chequeo de capacidad del worker impide alcanzar el guardado posterior de result_payload, por lo que ese campo queda vacío.

Al reintentar la **misma clave y el mismo payload**:

- El executor no retorna el registro COMMITTED porque condiciona el replay a result_payload no vacío (`agent.py:726`).
- Vuelve a ejecutar: **dos escrituras de negocio**.
- El ID de operación cambia.
- El nuevo ID retornado no existe en operation_records.

Este defecto no necesita concurrencia: ocurre precisamente en el recorrido PENDING→COMMITTED que el nuevo diseño pretende recuperar.

**Corrección mínima:** vincular autorización, clave y fingerprint a una identidad/ámbito de solicitante; reclamar la operación atómicamente y adoptar siempre el ID durable obtenido de la BD. Una sola ejecución debe poseer la reserva de trabajo. Rechazar payload distinto; un COMMITTED sin resultado completo debe recuperarse/reconstruirse o devolverse como resultado ya confirmado, **nunca reejecutarse por falta de cache**. Guardar atómicamente los identificadores suficientes para recuperar el resultado. Proteger GET mediante propietario/capacidad o autorización administrativa y no devolver la clave ni resultados privados indiscriminadamente.

## 4. OPERATION_PENDING: propagación parcial y ventana del registro en vuelo

### Camino positivo

Se observó OperationPendingError con ID durable y resolución posterior COMMITTED. En la API, un turno simulado que solicita una herramienta en vuelo produjo **HTTP 200 / OPERATION_PENDING / operation_id**, consultable. main y run_civia_agent colocan su manejador específico antes de TimeoutError.

### La subclase se pierde en el executor

**Referencia:** `agent.py:787-806`. FuturesTimeoutError es el mismo tipo base TimeoutError que hereda OperationPendingError.

Se registra una operación interna PENDING. Una herramienta llama al executor para repetir esa clave; este produce realmente OperationPendingError. Al salir a través del Future del worker exterior, su executor la captura como expiración ordinaria, porque no tiene un except OperationPendingError previo.

Resultado independiente:

```text
excepción al llamador: TimeoutError
operation_id preservado: false
operación interna: PENDING
POST /api/agent/query: HTTP 200, guardrail TIMEOUT, operation_id=null
```

La prueba usa el executor real y un proveedor de turno simulado. No se limita a inyectar una respuesta HTTP final. El orden correcto de manejadores en main no puede recuperar una identidad que ya se perdió antes.

### Supervisor vence antes de registrar el commit en vuelo

Se intercaló una barrera antes de register_in_flight_commit, después de las comprobaciones pre-commit; el supervisor toma su rama «no hay commit en vuelo». Solo entonces se libera la barrera. Se mantiene posible un commit tardío mediante clock controlado, límite de sentencia aislado y cancelaciones Python retrasadas; no se exige abortarlo bajo este contrato.

Resultado:

- A **0,2860 s**, el supervisor inicia mark_operation_aborted sin certeza de resultado; se libera la barrera.
- COMMIT nativo empieza a **0,2871 s** y confirma a **0,4713 s**.
- La actualización ABORTED espera el bloqueo de fila y no sobrescribe el marcador COMMITTED.
- El caller termina a **0,4728 s** con **TimeoutError ordinario, sin operation_id**.
- Negocio persistido y registro durable **COMMITTED**.

No se denuncia el commit tardío: se denuncia que la decisión de respuesta dependió de una instantánea incompleta de un diccionario de memoria. La ausencia de ese registro no prueba que un trabajador activo no vaya a confirmar.

**Corrección mínima:** preservar OperationPendingError antes del manejador de FuturesTimeoutError y distinguir la excepción del worker de la expiración de espera. No inferir ABORTED por ausencia de `_IN_FLIGHT_COMMITS`: un worker no finalizado debe seguir PENDING/UNKNOWN con ID durable hasta resolver su resultado. Coordinar el registro de fase y la decisión del supervisor; el diccionario puede ser una optimización, no la fuente de verdad.

## 5. Clasificación de excepciones

Pruebas reales, en conexiones propias:

| Caso | Observado |
|---|---|
| QueryCanceled por statement_timeout derivado del deadline | SQLSTATE **57014** → TimeoutError |
| TransactionTimeout del plazo, tres repeticiones | SQLSTATE **25P04** → TimeoutError |
| Terminación administrativa ajena con plazo de 2 s | **AdminShutdown 57P01** preservado a ≈0,039 s |
| Tabla inexistente | **UndefinedTable 42P01** preservado |
| ACK de commit perdido por proxy TCP | **OperationalError** preservado; registro real COMMITTED |

Esto corrige la sobreclasificación de AdminShutdown de la auditoría previa.

Permanece una limitación directamente comprobada de procedencia: conexiones propias con política de sesión transaction_timeout=50 ms y plazo de herramienta **2 s** producen 25P04 y se presentan como TimeoutError del plazo local a **0,135 s**. `is_deadline_cancellation` acepta cualquier 25P04 sin verificar que ese timer sea el del supervisor. El aborto SQL fue real; lo que no se acreditó fue su atribución al deadline local.

**Corrección mínima:** conservar la causa y procedencia de los límites de servidor, sin deducir «deadline propio» únicamente del SQLSTATE. Las decisiones de resultado durable tampoco deben depender solo de esa clasificación.

## 6. Suite y regresiones

Suite ordinaria completa congelada, `-m "not live"`, contador independiente y bloqueo de transportes externos:

| Modo | Resultado | Tiempo | Intentos externos inesperados Google/Groq |
|---|---|---:|---:|
| Claves vacías | **97 passed, 1 skipped, 1 deselected** | 16,58 s | **0** |
| Claves sintéticas | **95 passed, 2 failed, 1 skipped, 1 deselected** | 18,46 s | **0** |

En ambos se contó separadamente un control positivo intencional del centinela. La prueba live se excluyó explícitamente. E2E frontend se omite en pytest host por falta de resolución del servicio local frontend; no se afirma haberlo ejecutado. Un warning de AnyIO sin efecto sobre los datos.

Fallos del pase sintético:

- `test_g2_1_a02_legitimate_commits_within_deadline`: el worker llega al chequeo de capacidad después del plazo y retorna TimeoutError; el log muestra que su BD de prueba no tiene operation_records. No se cambiaron sus aserciones ni se usó este stack como prueba suficiente de persistencia incorrecta.
- `test_g2_1_6_in_flight_commit_returns_operation_pending_on_supervisor_timeout`: el servidor aborta y el worker termina antes de que el supervisor observe su fase en vuelo; recibe TimeoutError donde la prueba exige OperationPendingError. Un aborto ya demostrado puede ser un resultado veraz; esa aserción fallida por sí sola no prueba una escritura indebida.

No se atribuye la diferencia causalmente a las claves: hay variación de planificación. Se informan ambas ejecuciones, no solo la que pasó.

Regresiones mínimas independientes/existentes:

- **M-02:** dos clasificaciones concurrentes: 1400 exactos, reserva final 0; la primera no consume la reserva ajena. Idempotencia de TokenReservation preservada.
- **M-03 COPY:** IN/OUT y revocación funcionan; datos autorizados persistidos=2. Cursores encadenados y publicación de archivo conservan sus comprobaciones.
- **M-06:** configuración y tests existentes sin regresión; sin despliegues históricos adicionales.
- **G1:** sus 14 pruebas pasan en ambos modos; los endpoints administrativos existentes conservan sus controles. La nueva lectura de operaciones y la duplicación de propuestas son los defectos nuevos descritos, no una reapertura genérica de G1.
- **N-02:** adaptadores reales con MockTransport y trazas PostgreSQL conservan Gemini→Groq tras 429 y terciario solo después de fallo Groq; modelos y cantidad de trazas coinciden.
- **Hermeticidad:** cero intentos inesperados en ambos modos; ningún proveedor real contactado.

### Casos históricos interpretados con el NUEVO contrato

61–64 y 81–84 fueron ejecutados sobre PostgreSQL real con las pausas previas; no se exige que todo commit potencialmente válido aborte. Se conservaron los estados SQL y la clasificación observada, sin reinterpretar PENDING como un fallo por sí solo.

Los casos 102 y 109 retornaron **OperationPendingError con ID**, terminaron con negocio CHANGED y registro COMMITTED. El caso 104 retornó PENDING y terminó ORIGINAL/ABORTED. Los casos 151–152 retornaron PENDING y terminaron CHANGED/COMMITTED. Esos resultados concuerdan con el nuevo contrato en los recorridos normales instrumentados.

Los scripts históricos se adaptaron únicamente para dejar propagar sus excepciones y registrar el ID/estado durable; no se mantuvo una expectativa obsoleta de rollback inmediato. Una primera instrumentación confundía el clock_timestamp de updated_at del marcador con una configuración de timeout; se restringió el observador a SELECT CASE y se repitió ese reproductor, sin editar el código auditado.

## Cambios mínimos que bloquean la aceptación

1. **Hacer obligatorio el registro y su marcador:** fallar cerrado si no pueden persistirse; no confirmar negocio tras un rollback parcial del marcador. Un COMMITTED debe disponer de evidencia y de identificadores recuperables sin requerir reejecución.
2. **Reconciliar por identidad de operación y evidencia transaccional:** ausencia de PID y estado de otro recurso no bastan. Incertidumbre debe permanecer UNKNOWN/PENDING; impedir falsos ABORTED seguidos de COMMITTED.
3. **Autorizar lectura y replay:** dueño/capacidad/ámbito administrativo, fingerprint de payload y clave ligada al solicitante. No publicar claves o resultados privados.
4. **Una reclamación durable por clave:** ID estable, conflicto validado y un solo ejecutor. COMMITTED sin cache no autoriza repetir la escritura; la propuesta debe quedar vinculada inequívocamente a su operación.
5. **Preservar PENDING en toda la cadena:** orden de excepciones correcto y decisión conservadora cuando el worker no haya terminado, incluidas ventanas anteriores al registro en memoria.
6. **Precisar procedencia de cancelaciones:** preservar 57P01/42P01 y distinguir un timer de sesión ajeno del deadline local.

No se recomienda volver a timeouts relativos ni a prometer rollback inmediato. Los bloqueos son de atomicidad del nuevo ledger, evidencia de reconciliación, autorización y propiedad/idempotencia del trabajo. **G2.1.6 NO APROBADO; no corresponde cerrar G2.1 bajo este contrato todavía.**

## Evidencia conservada

En la raíz temporal indicada:

- `operation_integrity.py` / `operation_integrity_results.json`: SAVEPOINT, ausencia 004, falsa reconciliación, acceso anónimo, conflicto de payload, idempotencia/propuestas concurrentes y propagación por API.
- `state_transition_checks.py` / `state_transition_results.json`: ABORTED comunicado por GET antes de terminar COMMITTED.
- `recovery_scenarios.py` / `recovery_results.json`: abortos, desconexión, primer recorrido API PENDING y consultas concurrentes.
- `pending_boundaries.py` / `pending_boundary_results.json`: commit tardío con PENDING correcto y ventana de registro. Se conserva también el pase inicial con cancelación más temprana, que abortó en lugar de confirmar.
- `late_replay_and_foreign_timeout.py` / `late_replay_foreign_results.json`: replay de COMMITTED sin cache y timer ajeno.
- `ack_loss_proxy.py` / `ack_loss_result.json`: proxy TCP local que elimina el ACK real de COMMIT, sin simular su resultado.
- `active_commit_and_query_cancel.py` / `active_commit_query_results.json`: backend observado durante COMMIT/PgSleep y QueryCanceled del plazo.
- `api_restart_check.py` / `api_restart_result.json`: escritor terminado y API consultada en proceso nuevo.
- `clock_contract_checks.py`, `prearmed_contract_checks.py` y sus JSON: casos históricos bajo el contrato nuevo.
- `run_suite.py`, `network_guard.py`, logs y JSON de ambos modos; `functional_results.json`, `copy_reservation_results.json`, `n02_results.json`, `semantics_normalization_results.json`.
- `head.zip` / `src`: copia congelada del commit.

Los scripts importan src y src/backend del archivo congelado, con URL del puerto 55497 y base correspondiente, archivos propios y claves vacías o marcadores sintéticos. Los que crean tablas/triggers requieren base nueva para repetir. Las barreras solo controlan planificación: el motor, la persistencia y las verificaciones no se sustituyen.

## Cierre y huellas

Se detuvo y eliminó únicamente el contenedor `civia_f6fe_pg`, su red y su volumen exclusivos. El proxy TCP terminó y el proceso escritor de la prueba de reinicio fue finalizado y recogido. No se tocaron servicios habituales. Se conservan scripts, logs y JSON en la raíz temporal. HEAD permanece en el SHA auditado, rama fix/auditoria-final; el único archivo nuevo del repositorio original es este informe.

SHA256 de evidencias principales:

| Archivo | Huella |
|---|---|
| head.zip | `F1A0732B5ED5B7422A2C75A807B89A4BDE0C2720C9196012DEE8727E035C5DF0` |
| operation_integrity_results.json | `2DA7EEEF9F51BCB97949D761A8A3B361154FBBA397D1B4F1F472ED03C6FDC8E9` |
| state_transition_results.json | `B666C606AD804ED5FCB694CEB24763778ED7703D02CD492104C9A0B6EBB01F21` |
| pending_boundary_results.json | `1DABF25D6E2D437303E03CF3B8A0D14C6BA4FE04E63911D777E868719502E425` |
| late_replay_foreign_results.json | `2556E3F3772E6FD869B352AC1F33EB79997DF6E0B9329147D709EAFBF5FC79A2` |
| ack_loss_result.json | `7DF4CCCC0FAD3E7FBE65F3544AEB8BCA2BA90FF86403B43073A615BF99C7253F` |
| api_restart_result.json | `D14082653B5F6F271C1648E8B7C94C80F71E02D0C39736AC9E8B6FA77CFC805C` |
| network_blank.json | `501CB2994A70F33C4ECFD26E43D446384AD4FA391D8944DEEEDD06239FFD3E3E` |
| network_synthetic.json | `86B63160E0D3F4627FCE0DBD5FF5E2D3F89AB697F6F51D53918A07B174F1348A` |
