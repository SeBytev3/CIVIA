# CIVIA — Auditoría independiente G2.1.7

Fecha: 2026-11-03, America/Bogota. Commit exacto: `492b0415bd1642d077ce7ce48ea2e2cb1c5b26c6`, rama `fix/auditoria-final`.

## Dictamen

**NO APROBADO. No cerrar G2.1 bajo el contrato transaccional actual.** La eliminación del SAVEPOINT permisivo y el reclamo atómico corrigen contraejemplos importantes de G2.1.6. Se verificaron sobre PostgreSQL 17 real el rollback ante fallo del marcador, la deduplicación concurrente, la identidad durable de PENDING y la recuperación de commits cuyo ACK se pierde. Persisten defectos reproducidos de registro obligatorio, estados terminales, autorización/entrega del token y procedencia de cancelaciones.

Las suites ordinarias pasan en los dos modos de claves, pero no cubren todos estos defectos. No se exige rollback instantáneo de un commit en vuelo ni terminación forzosa de hilos. Un retorno PENDING seguido de COMMITTED es válido cuando conserva la identidad y coincide con PostgreSQL.

## Antecedente de infraestructura y comprobaciones locales

En el primer intento, `docker compose ps` falló dos veces con el canal `dockerDesktopLinuxEngine` inexistente (código 1). Se documentó bloqueo, sin ejecutar pruebas ni emitir aceptación. Ese antecedente no es un fallo funcional de CIVIA.

En la reanudación solicitada se ejecutaron de nuevo:

| Comprobación | Resultado observado |
|---|---|
| `Get-Location` | `C:\Users\Jhoesp\Desarrollo\CIVIA` |
| `git rev-parse --short HEAD` | `492b041` |
| `git branch --show-current` | `fix/auditoria-final` |
| `git status --short` | Solo `M docs/estado.md` y el informe nuevo del intento anterior |
| `docker context show` | `desktop-linux` |
| `docker compose ps` | Código 0; `civia-api-1`, `civia-db-1` y `civia-frontend-1` saludables |

El árbol estuvo limpio antes del primer informe. En la reanudación se distinguieron explícitamente los dos cambios documentales. La copia auditada procede de `git archive 492b041`, no del árbol con esos cambios.

Se leyeron el informe G2.1.6, el diseño G2.1.7, la sección 16 de remediación, el bloque G2.1.7 de estado, las migraciones 004/005 y `backend/app/db.py`. Se recuperó el alcance original mediante `read_thread` de la conversación referenciada.

## Aislamiento y método

Evidencia conservada fuera del repositorio:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-492b041-04bcac63ba274f3093fa56dac5d17406`

- `head.zip` y `src`: archivo congelado y extracción del commit exacto.
- Contenedor PostgreSQL exclusivo: `civia_audit_492b041_pg`, PostgreSQL **17.11** real (`postgres:17-alpine`).
- Runner exclusivo: `civia_audit_492b041_runner`, CPython **3.13.18**, psycopg **3.2.6**. Se reutilizó la imagen local `civia-api` solo como runtime; código, migraciones y tests se importaron de `/audit/src`, la copia congelada montada.
- Red exclusiva **interna** `civia_audit_492b041_net`, sin puertos publicados ni conexión a la red habitual. Los nombres habituales de servicios no se conectaron al runner.
- Bases nuevas: `test_audit`, `test_no004`, `test_suite_blank`, `test_suite_verified`, `test_suite_synthetic` y las creadas por las suites en ese mismo clúster exclusivo.
- Sin cargar `.env`, claves privadas, imágenes privadas ni datos habituales. Payloads y datos sintéticos identificados. Token administrativo efímero generado en memoria, sin imprimirlo. Claves de proveedor vacías o marcadores `SYNTHETIC_*`.
- SQL, triggers, restricciones, commits y verificaciones desde conexiones independientes son reales. Barreras/eventos controlan intercalados; no sustituyen persistencia. El proxy elimina una respuesta real de COMMIT. Un fallo de observación se inyecta únicamente al consultar `pg_stat_activity`, conservando SQL real en el resto del recorrido.

Imágenes del runner y PostgreSQL, respectivamente: `sha256:843e6979568902ee08ba2106fe4a8459042f95108eba22f10dde3365aeeab0d3` y `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b`.

## Matriz de aceptación

| Área | Resultado | Evidencia independiente |
|---|---|---|
| 1. Atomicidad | **PARCIAL** | PASS en executor: marcador rechazado por trigger, ausencia 004, rowcount=0 y control positivo. FAIL de cobertura: REST de actualización de estado confirma sin ledger, incluso con tabla ausente. |
| 2. Reconciliación | **FAIL** | Worker real sin PID conserva PENDING y termina COMMITTED; propuesta ajena sin PID no confirma la operación; ACK perdido y reinicio recuperan COMMITTED. Persisten transición terminal indebida, falso aborto ante fallo de observación y UNKNOWN que ignora evidencia propia. |
| 3. Autorización | **FAIL** | Token propio/admin acceden al resultado; ajeno/inválido/anónimo no reciben resultado ni clave de idempotencia, pero sí tipo, recurso y fechas. Token no se entrega en el recorrido executor/API y el token devuelto por un reclamo repetido no coincide con su hash durable. |
| 4. Idempotencia | **PARCIAL** | Una escritura y un ID ante dos llamadas simultáneas; conflicto de payload; replay COMMITTED sin cache; replay PENDING sin segundo worker; replay desde proceso nuevo; una propuesta real concurrente. ABORTED/UNKNOWN aún entran al worker sin adquirir reclamo, aunque el commit SQL probado falla cerrado. |
| 5. Propagación PENDING | **PASS en recorridos ejecutados** | Excepción anidada e ID hasta API; supervisor antes de registro en vuelo conserva ID; resultado tardío con negocio COMMITTED; aborto real acaba ABORTED; consulta lenta de lectura retorna TIMEOUT sin operación. La autorización de consulta sigue fallando en el área 3. |
| 6. Excepciones | **FAIL** | 57P01 y 42P01 reales preservados; timer ajeno temprano de 50 ms conserva TransactionTimeout. El margen de 50 ms atribuye falsamente 57014 y 25P04 externos a un deadline todavía futuro. |
| 7. Regresiones | **PARCIAL** | Dos pases: 104 PASS, 1 SKIP, 1 live excluida; incluyen las siete G2.1.7 y mínimos M-02, M-03 COPY, M-06, G1, N-02. E2E frontend omitido por aislamiento; no se declara 105 PASS. |

## 1. Atomicidad corregida en el executor; rutas fuera del registro

Instrumentos: `independent.py`, `boundaries.py` y sus JSON.

Resultados desde conexiones independientes:

```text
Control positivo:           negocio=1; marcador=COMMITTED
Trigger rechaza marcador:   RaiseException; negocio=0; marcador=PENDING
Marcador rowcount=0:        RuntimeError; negocio=0; marcador=ABORTED preexistente
Tabla operation_records ausente: UndefinedTable; negocio=0
```

El caso rowcount=0 registra primero una intención y la deja ABORTED antes de intentar la escritura bajo ese contexto. `checked_commit` impide confirmar la escritura. El caso sin 004 usa otra base exclusiva sin esa tabla. Ya no se reproduce el negocio confirmado tras un SAVEPOINT del marcador.

**FAIL de cobertura**, referencias `backend/app/main.py:511`, `:534`, `backend/app/repository.py:517` y `backend/app/db.py:805`:

1. PATCH real mediante TestClient a `/api/reports/{id}/status`, con administrador efímero válido y `human_approved=true`.
2. Respuesta 200 y estado persistido IN_REVIEW; incremento en `operation_records` = **0**.
3. Se renombra temporalmente `operation_records` dentro del clúster exclusivo. El mismo endpoint devuelve 200 y persiste RESOLVED.
4. Se restaura inmediatamente el nombre de la tabla.

La autorización humana funciona; el fallo es que la ruta mutante no establece operación obligatoria y `checked_commit` omite el marcador cuando no existe contexto. No se afirma que todas las escrituras del CRUD deban convertirse en operaciones asíncronas: esta ruta crítica requiere cobertura explícita o una excepción contractual documentada. Bajo el requisito solicitado de registro obligatorio sin rutas inadvertidas, no pasa.

**Cambio mínimo:** establecer intención/contexto en la entrada crítica y confirmar su marcador en la misma transacción; alternativamente delimitar formalmente el contrato y conservar una auditoría durable equivalente para la decisión humana. No introducir registro opcional que permita confirmar silenciosamente si falta la tabla.

## 2. Reconciliación, terminales y recuperación

PASS ejecutados:

- Worker real retenido antes de abrir conexión: GET/helper observa PENDING y `backend_pid=null`; al liberarlo confirma negocio=1 y COMMITTED.
- Propuesta real de otra operación sobre el mismo reporte: la operación nueva sin PID conserva PENDING, no toma la propuesta ajena como prueba de commit.
- Diez reconciliaciones concurrentes conservan PENDING en una intención sin evidencia.
- UNKNOWN sin evidencia conserva UNKNOWN.
- Proxy TCP en el runner: envía COMMIT real a PostgreSQL, descarta su respuesta y cierra el transporte. `ack_dropped=true`, executor recibe OperationalError, negocio=1, marcador=COMMITTED, reconciliación=COMMITTED.
- Escritor en proceso separado observado `active / COMMIT / PgSleep`; se termina exclusivamente ese proceso. Se espera desaparición de su backend. Negocio=1; una API importada en proceso nuevo responde 200/COMMITTED. No se deduce commit de la excepción del cliente.

**FAIL A — inmutabilidad**, `backend/app/db.py:259-290`:

```text
register_operation_intent → mark_operation_aborted → status ABORTED
mark_operation_committed(op, resultado sintético) → status COMMITTED
```

El helper real ejecuta `WHERE operation_id = %s` sin condición de estado. No requiere evidencia de negocio y sobrescribe un terminal. Está llamado por el worker en `backend/app/agent.py:829`; no es solo SQL arbitrario del instrumento. La prueba no afirma que una ruta REST permita seleccionar libremente esta transición: demuestra que la garantía terminal no se impone en el helper usado por la aplicación.

**Cambio mínimo:** transiciones condicionales y rowcount obligatorio, terminales inmutables; separar anexar resultado de cambiar estado para que una finalización tardía no reescriba ABORTED.

**FAIL B — incertidumbre tratada como aborto**, `backend/app/db.py:424-457`:

Se registra PENDING con PID sintético. Solo la observación `pg_stat_activity` lanza OperationalError sintético; el resto del SQL es real. `reconcile_operation` captura el error, asume `is_pid_alive=false` y persiste **ABORTED**. No existe prueba de rollback. La inexistencia del PID usado no se presenta como evidencia independiente: el objetivo es demostrar que el error de observación se consume y decide un terminal.

**Cambio mínimo:** error o ausencia de observación no son prueba positiva de aborto; conservar UNKNOWN/PENDING hasta comprobar desenlace. No confundir backend ausente con rollback completo de esta operación.

**FAIL C — UNKNOWN con evidencia exacta no se resuelve**, `backend/app/db.py:403-417`:

Una propuesta real está vinculada por `pending_approvals.operation_id`. Como preparación de recuperación, se coloca su marcador en UNKNOWN mediante SQL del instrumento y se llama al helper. Este encuentra evidencia, pero el UPDATE acepta solo PENDING, afecta cero filas y retorna UNKNOWN. Este montaje se identifica como estado de recuperación preparado, no como prueba de que el flujo normal produjo UNKNOWN tras un commit.

**Cambio mínimo:** permitir UNKNOWN→COMMITTED con evidencia propia y proteger la actualización contra estados terminales concurrentes; releer el estado durable si no se actualizó ninguna fila.

## 3. Autorización, privacidad y token de consulta

`independent_results.json`, cinco peticiones reales al mismo endpoint:

| Credencial | HTTP | Resultado privado sintético | Metadatos de operación |
|---|---|---|---|
| Token propio | 200 | Visible | Visibles |
| Token otra operación | 200 | Oculto | Visibles |
| Administrador válido | 200 | Visible | Visibles |
| Token inválido | 200 | Oculto | Visibles |
| Anónimo | 200 | Oculto | Visibles |

`idempotency_key` no aparece. Sí aparecen `operation_type=ADMIN_PRIVATE`, `target_id=SYNTHETIC_PRIVATE_TARGET`, estado y ambas fechas para terceros. Eso confirma el comportamiento del diseño, pero no proporciona una política por nivel de privacidad para operaciones administrativas. Referencia: `backend/app/main.py:609-649`.

**Entrega rota del token:** la búsqueda de `query_token` en `backend/app` encuentra su generación en db y su validación en main, sin entrega desde executor. El reclamo devuelve el token en memoria, pero `execute_tool_with_timeout` lo descarta; resultado de herramienta, esquema HTTP y respuesta PENDING no lo entregan. El ciudadano recibe un ID sin capacidad de recuperar el resultado protegido. En el replay de un reclamo, además, se genera otro token y se retorna junto al hash previo: comprobación SHA-256 real devuelve **false**. No se imprimen ni guardan esos tokens.

**Cambio mínimo:** autorizar antes de reconciliar/divulgar; definir acceso por propietario o administrador para metadatos privados; entregar una capacidad recuperable en el canal autorizado y diseñar su replay/rotación sin devolver tokens que no correspondan al hash durable. No hacer público el resultado para compensar la falta de entrega.

## 4. Idempotencia y reclamo exclusivo

PASS reales: dos hilos con la misma clave/payload producen **una escritura**, **un ID** y **un registro COMMITTED**. La rama `xmax` distinguió al ganador en esta ejecución real. Otro payload genera IdempotencyConflictError sin escribir. COMMITTED sin cache retorna confirmación con ID estable y no reejecuta; un proceso nuevo reproduce esa recuperación. PENDING vuelve a dar OperationPendingError con el mismo ID y cero llamadas al segundo worker. Tres reclamos directos con distintas combinaciones solicitante/tipo generan tres IDs exclusivos. Esto prueba el índice compuesto, no una identidad autenticada distinta por ciudadano en el executor, que sigue usando el solicitante predeterminado.

Dos propuestas reales con claves diferentes se sincronizaron para que ambas lecturas vieran ausencia inicial; el índice parcial dejó **una propuesta**, ambos retornos señalaron el mismo approval_id y el reporte conservó CONFIRMED con aprobación humana pendiente.

**PARCIAL:** ante reclamo existente ABORTED o UNKNOWN, `backend/app/agent.py:776-814` no maneja esos estados ni sale; continúa creando worker con otro op_id no adquirido. Los casos `replay_ABORTED` y `replay_UNKNOWN` llegan a RuntimeError del marcador, negocio=0 y conservan el registro original. No se presenta como duplicación SQL persistida: el fail-closed impide ese commit. Sí contradice que ningún no ganador ejecute el worker.

**Cambio mínimo:** manejo exhaustivo de todos los estados antes de crear worker; solo `claim_acquired=true` habilita efectos. Conservar ID original y respuesta veraz para incertidumbre/aborto, sin fabricar un nuevo ejecutor.

## 5. Propagación PENDING

- OperationPendingError lanzado dentro de herramienta anidada conserva clase e ID.
- `/api/agent/query` devuelve `guardrail_triggered=OPERATION_PENDING`, `operation_id` exacto y estado PENDING.
- Supervisor vence mientras worker espera antes de abrir conexión o registrar commit: retorna PENDING con ID, no TIMEOUT anónimo; worker revocado no escribe.
- Commit ya confirmado con resultado retenido 0,4 s frente a supervisor 0,25 s: PENDING con ID; al terminar worker, negocio=1 y COMMITTED.
- UPDATE seguido de pg_sleep bajo deadline real: PENDING con ID; tras desaparecer backend, reconciliación ABORTED y negocio=0.
- Lectura lenta `consultar_reportes`: TimeoutError y sin ID transaccional, como corresponde.

El worker revocado antes de abrir conexión puede dejar PENDING sin PID tras terminar; se informa como limitación de resolución, sin inventar confirmación o aborto. El PASS de propagación no certifica autorización de polling, fallida en el área 3.

## 6. Procedencia de excepciones

PASS: TransactionTimeout externo de 50 ms con deadline a 2 s no se atribuye al plazo local. Controles de 25P04/57014 con plazo futuro/expirado se clasifican según el código actual. AdminShutdown **57P01 real** obtenido terminando únicamente un backend exclusivo y UndefinedTable **42P01 real** se preservan incluso con plazo expirado.

**FAIL reproducido del margen de 50 ms**, `backend/app/db.py:100-146`:

```text
SET LOCAL statement_timeout='20ms'; deadline local = monotonic()+0.060
SELECT pg_sleep(0.2)
57014 externo; restante local=0.03734 / 0.03931 / 0.03917 s
is_deadline_cancellation(...)=True en los tres intentos

SET transaction_timeout='20ms'; mismo deadline local
25P04 externo; restante local=0.03775 s; clasificación local=True
```

El origen externo se conoce porque el instrumento configura el timer de sesión, sin capability revocada ni deadline vencido. El margen temporal atribuye causalidad que no está demostrada.

**Cambio mínimo:** no usar cercanía al deadline como evidencia suficiente de procedencia. Registrar qué límite/cancelación se armó para esta operación y preservar el error original cuando solo existe coincidencia temporal.

## 7. Suites y comprobaciones

Comando de suite desde `/audit/src/backend`:

```text
PYTHONPATH=/audit/src:/audit/src/backend
DATABASE_URL=postgresql://postgres:<credencial-sintética-del-clúster-exclusivo>@civia_audit_492b041_pg:5432/<base-exclusiva>
pytest -m "not live" -q
```

| Pase | Resultado | Tiempo pytest | Salida |
|---|---|---|---|
| Claves vacías, entorno corregido | **104 passed, 1 skipped, 1 deselected** | 21,46 s | 0 |
| Claves sintéticas | **104 passed, 1 skipped, 1 deselected** | 18,12 s | 0 |

Un warning de deprecación de AnyIO en ambos. El test E2E frontend se omite porque la red interna no resuelve ni accede al frontend habitual; no se levantó otro frontend. Las siete pruebas G2.1.7 están incluidas; también M-02, COPY IN/OUT, M-06, G1 y N-02. La guardia hermética de la suite no reportó llamadas externas inesperadas; la red interna y la ausencia de claves reales agregan aislamiento.

La primera pasada del auditor configuró solo `/audit/src/backend` en PYTHONPATH: **103 passed, 1 failed, 1 skipped, 1 deselected**, 16,49 s; el fallo fue `ModuleNotFoundError: eval` en G1. Se corrigió únicamente PYTHONPATH agregando la raíz congelada y se repitió en otra base nueva. No se modificaron código ni aserciones para obtener PASS. No hubo fallos de temporización en los dos pases válidos.

`python -m compileall -q app tests /audit/src/eval` terminó con código 0. Es una comprobación de compilación, no lint. No se localizó configuración/comando de lint Python del proyecto; no se declara lint de producto aprobado. `git diff --check` se utiliza para validar los cambios documentales.

## Evidencia reproducible conservada

En la raíz temporal indicada:

- `independent.py` / `independent_results.json`: atomicidad, replay, concurrencia, estados, autorización y PENDING HTTP.
- `followup.py` / `followup_results.json`: observación fallida, terminales, token repetido, carrera de propuestas y workers reales.
- `boundaries.py` / `boundary_results.json`: ventanas de supervisor, aborto SQL, margen 57014, replay entre procesos y REST sin ledger.
- `error_provenance.py` / `error_provenance_results.json`: 25P04 ajeno cercano al plazo, 57P01 y 42P01 reales.
- `ack_loss_proxy.py` / `ack_loss_result.json`: respuesta COMMIT perdida por proxy TCP local al runner.
- `api_restart_check.py`, `restart_writer.py` y `api_restart_result.json`: proceso escritor terminado durante COMMIT y lectura por proceso nuevo.
- `suite_blank.log` (primer entorno incorrecto), `suite_verified.log`, `suite_synthetic.log` y respectivos `.exit`.

El primer instrumento intentó reemplazar `Cursor.execute`, atributo de solo lectura; registró AttributeError y no produjo evidencia del caso de observación. `followup.py` lo repitió con wrappers compatibles y conservó SQL real. Se mantienen ambos registros. Los scripts ACK/reinicio se adaptaron desde G2.1.6 únicamente en host/puerto, fila de prueba y plataforma; no se sustituyó el motor.

Para repetir, recrear clúster/red/runner exclusivos como en la sesión, montar esta raíz en `/audit`, asignar DATABASE_URL solo al clúster exclusivo y aplicar migraciones/seed sintético. Ejecutar en orden `independent.py`, `followup.py`, `boundaries.py`, `error_provenance.py`, `ack_loss_proxy.py /audit` y `api_restart_check.py /audit`. Empezar desde bases nuevas: los instrumentos crean tablas/triggers y no son idempotentes. Suites usan bases propias nuevas y PYTHONPATH con ambas raíces. La contraseña de auditoría del clúster eliminado fue `audit_synthetic_only`, exclusivamente sintética. No copiar credenciales ni `.env` habituales.

Huellas SHA-256:

| Evidencia | SHA-256 |
|---|---|
| head.zip | `9E4D1ED0800153727541B80E13B1B167C9BD07F1EB235C4726AED20D4609EC5B` |
| independent_results.json | `B93C4CA8F412B560DFE8943B2313B89AF7E242A24605261B2247F91F954DC1F9` |
| followup_results.json | `478172B5F15FC9DAFCFF7A2941379A8245E6BBBEA525A97072EDE9A03B4D8D9E` |
| boundary_results.json | `FCA2398DE53CAF7311DB61805A85B3B60302489F865D765CFBB05491EA739132` |
| ack_loss_result.json | `583CDC6E63C332708E839B0CCDD0610035A785E74DF3A2E415681F4CADC150B4` |
| api_restart_result.json | `51A69C3F61FCA8936C4A9AF2C41AF42BD1471C2F99680C491CC782735023DDBB` |
| suite_verified.log | `59143C6E31CC5A4F3147AE6CF2C3D3DDD4CDDBCB8B711C46470F7782461416F6` |
| suite_synthetic.log | `C2F8717F1AB93DB2700F7FCD5DE8F1D698D708E8831077DB5B1B22AB35F612F3` |

La copia Git usa LF y el checkout Windows CRLF; sus hashes de bytes difieren por finales de línea. SHA-256 congelados: db.py `374350b8e843ab624de4cd618f35c6c6c4412d3cf5af0ebc5d75e0797581f4bf`, 004 `e698d99e5230a694e967b6405969876b74b0c842f6157de4124c5fa7da3245e4`, 005 `64851b084a21473ee3bc825937d4b6ecab5052448c3143f931e4ef60254ba306`. No se cambiaron los fuentes congelados auditados para remediar defectos.

## Recomendación

Si se mantiene el contrato completo, corregir únicamente los defectos reproducidos y volver a ejecutar estos instrumentos. No iniciar otra auditoría general ni cambiar modelos o arquitectura por este informe.

Para preparar la entrega académica funcional, **recomiendo desactivar temporalmente las escrituras asíncronas del agente** mientras se resuelven identidad, autorización y evidencia terminal. Mantener el alta/consulta de reportes ciudadanos, el análisis sin efectos críticos y la aprobación humana explícita mediante una ruta transaccional acotada con auditoría durable. Esa simplificación no convierte este commit en aprobado y requiere un cambio posterior autorizado; no se implementó aquí.

## Cierre

La limpieza se limita al runner y PostgreSQL exclusivos, sus volúmenes exclusivos y la red interna exclusiva. Se conservan scripts, fuentes congelados, logs y JSON en la raíz temporal. El estado final de limpieza y de los servicios habituales se verificó al cerrar esta sesión y se anotó en `docs/estado.md`.

Sin ejecutar ni modificar Autopilot. Sin código de producción modificado, commits, push, merge ni cambio de rama. Únicos cambios del checkout: este informe y `docs/estado.md`.
