# CIVIA — Auditoría independiente G2.1.8

Fecha de auditoría: 2026-11-04, America/Bogota. Commit exacto: `187dea00e770191621f7fa4c481a41f2acbc1ab4`. Rama: `fix/auditoria-final`.

## Dictamen

**NO APROBADO.** Las mejoras de G2.1.8 se verifican parcialmente: el PATCH crítico confirma reporte y registro juntos, el trigger impide cambios de estado terminal, las lecturas privadas rechazan credenciales inválidas y los replays ABORTED/UNKNOWN ya no ejecutan workers. Sin embargo, persisten confirmaciones UNKNOWN sin evidencia, reconciliación que deduce aborto de un PID ausente, divulgación por replay y pérdida de capacidad tras perder la primera respuesta. Aparecen además regresiones en el replay con token propio y en la autorización mediante credencial de edición del reporte.

Las suites completas pasan **114 pruebas en cada modo**, incluido E2E básico del proxy. Esto no demuestra los contratos ausentes en sus aserciones. No se recomienda cerrar G2.1 ni iniciar automáticamente otra fase de desarrollo.

## Preflight, alcance y aislamiento

Comprobaciones ejecutadas directamente en `C:\Users\Jhoesp\Desarrollo\CIVIA`:

| Comprobación | Observado |
|---|---|
| `git rev-parse HEAD` | `187dea00e770191621f7fa4c481a41f2acbc1ab4` |
| `git branch --show-current` | `fix/auditoria-final` |
| `git status --short` inicial | Sin salida, árbol limpio |
| `git diff 492b041 187dea0` | 10 archivos; 838 inserciones, 23 eliminaciones; diff completo conservado como `full.diff` |
| `docker compose ps` | API, PostgreSQL y frontend habituales saludables |
| Migración 006 y fuentes/pruebas | Lectura de migración, diff y código efectivo de db, agent, main, repository, schemas y las nueve pruebas nuevas |

El diff incluye las cinco fuentes, la migración 006, `test_audit_g2_1_8_adversarial.py` y tres documentos. Se contrastaron las afirmaciones de remediación con los resultados; no se aceptaron sus recuentos como evidencia independiente.

Raíz aislada de evidencia:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-187dea0-a8a1bf0a03e240289e8175ad44f7113d`

Se generó `head.zip` con `git archive 187dea0` y se extrajo en `src`. PostgreSQL **17.11 real**, Python **3.13.18**, psycopg **3.2.6**. Red interna exclusiva `civia_audit_187dea0_net`, sin puertos publicados ni conexión a redes habituales. Recursos exclusivos:

- `civia_audit_187dea0_pg`, alias `pg`, imagen PostgreSQL `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b`.
- Runner y API dedicados, imagen local usada únicamente como runtime `sha256:843e6979568902ee08ba2106fe4a8459042f95108eba22f10dde3365aeeab0d3`; imports desde `/audit/src` y `/audit/src/backend`, nunca desde el código incluido en la imagen.
- API aislada en base `test_api`, alias `api`; proveedor sustituido por adaptador sintético en `serve.py`. Ejecuta el executor y API reales; la herramienta sintética escribe en tabla propia para observar commit/timeout. No se presenta como evaluación de proveedor IA ni de calidad multimodal.
- Frontend aislado, alias `frontend`. Se construyó desde `src/frontend`; imagen `sha256:35c84286d29d116a2f42d69648075ec1bbd255912b20dec9d8cdb2dd0717ab71`.

Bases nuevas exclusivas para instrumentos, API, suites, ausencia 004 y migraciones. Sin cargar `.env`, datos reales, imágenes privadas ni credenciales de proveedores. Las suites usan claves vacías o marcadores sintéticos, guardia hermética y red interna; no reportan llamadas externas inesperadas. La construcción del frontend descargó dependencias npm; no contactó proveedores IA.

## Matriz contractual

| Control | Resultado | Evidencia principal |
|---|---|---|
| Atomicidad REST | **PASS** | PATCH exitoso agrega ledger; rechazo de INSERT y tabla ausente revierten reporte/version; inexistente no agrega registro; concurrencia serializa dos updates y dos registros |
| Trazabilidad REST de cambios | **PARCIAL** | Guarda tipo, destino, estado y solicitante genérico `admin`; no registra estado anterior/nuevo, nota, versión ni identidad administrativa diferenciada |
| Terminales SQL y helpers ABORTED | **PASS** | Seis cambios SQL terminales rechazados; metadatos legítimos permitidos; helper rechaza ABORTED→COMMITTED; replays sin cambio de estado funcionan |
| UNKNOWN→COMMITTED solo con evidencia | **FAIL** | `mark_operation_committed` confirma UNKNOWN sin evidencia propia; trigger 006 no lo impide |
| Reconciliación | **PARCIAL / FAIL contractual** | Observación fallida conserva PENDING; evidencia propia resuelve UNKNOWN en helper; PID ausente sigue produciendo ABORTED; GET no reconcilia UNKNOWN; GET anónimo privado modifica estado antes de responder 404 |
| Autorización de GET privado | **PARCIAL** | Propio/admin 200; ajeno/inválido/anónimo 404. Credencial de edición del reporte accede también a operación administrativa privada |
| Privacidad de replay | **FAIL** | Replay público revela resultado que GET oculta; replay privado revela target; replay privado ABORTED revela detalle de error |
| Posesión y recuperación de tokens | **FAIL** | Token propio en replay provoca NameError; PENDING HTTP entrega token, pero no hay capacidad cliente funcional ni recuperación genérica al perder primera respuesta |
| No workers en replay terminal | **PASS** | ABORTED retorna ABORTED y UNKNOWN retorna excepción UNKNOWN; cero llamadas a worker |
| Timeouts | **PARCIAL** | 57014/25P04 externos antes del deadline ya no se atribuyen localmente; el mismo error se atribuye al deadline si se procesa después. 57P01/42P01 reales preservados |
| Migraciones 001–006, 005→006 y reaplicación | **PASS** | Base limpia, upgrade con historial de cinco migraciones y fila COMMITTED preexistente, solo 006 nueva, reaplicación vacía y un trigger |
| Suites G1/G2/M-02/COPY/M-06/N-02 | **PASS en alcance hermético** | 114 PASS por modo, una live excluida, sin tests omitidos |
| E2E frontend/proxy | **PASS** | Suite con frontend aislado y repetición específica contra imagen recién construida: 1 PASS |
| Seguimiento funcional | **PARCIAL / FAIL recuperación** | POST→PENDING→GET autorizado real por Nginx funciona; pérdida de primera respuesta no recupera capacidad. UI no conserva token ni hace polling |

## Hallazgos reproducidos

### F1 — El replay con prueba de posesión falla por NameError (regresión G2.1.8)

**Archivo:** `backend/app/db.py:222`, imports `:1`. **Instrumento:** `adversarial.py`, caso `owner_token_replay`.

Se genera capacidad sintética de 32 bytes antes del primer reclamo, se pasa como `client_token`, se registra el payload con `operation_token`, se confirma y se repite exactamente la herramienta/clave/payload/capacidad. Esperado: reconocer propietario y recuperar el resultado sin reejecutar. Observado: **NameError** al ejecutar `hmac.compare_digest`; db.py no importa hmac. No se alteró el import para continuar. La suite nueva no prueba ese recorrido de propietario.

La comprobación también encuentra la capacidad en claro en `proposed_payload`, porque el executor persiste `tool_args` completo (`backend/app/agent.py:777`). Esto no prueba filtración en logs, pero invalida describir el almacenamiento como exclusivamente un hash de capacidad.

**Impacto:** la ruta nueva de recuperación con capacidad preexistente falla incluso a nivel executor; credenciales quedan en payload durable. **Mínimo:** corregir el import y excluir credenciales del payload persistido/fingerprint; transportar autenticación separada de argumentos de negocio. Agregar prueba de replay real del propietario sin modificar esta auditoría.

### F2 — Replays eluden la política de privacidad (preexistencia y regresión diferenciadas)

**Archivos:** `backend/app/agent.py:787-818`, `:825-833`. **Instrumentos:** `adversarial.py`, `final_probes.py`, `http_tracking.py`.

Con clave y payload conocidos, sin token:

- Operación ordinaria COMMITTED (`requester_id=citizen`): replay devuelve `result_payload` sintético privado. GET con capacidad inválida devuelve el mismo resultado oculto. Esta divergencia **ya existía en G2.1.7** y continúa mediante `not is_private_op`.
- Operación `ADMIN_PRIVATE_REPLAY`: el filtro nuevo oculta el payload, pero la respuesta resumida revela `target_id=SYNTHETIC_PRIVATE_TARGET`. **Corrección incompleta del defecto previo.**
- Operación `ADMIN_ABORT_PRIVATE` ABORTED: el replay no ejecuta worker, pero devuelve target y `mensaje` igual al error privado almacenado. Esta rama de retorno es **nueva en G2.1.8**.

La prueba HTTP por proxy confirma `private_result_in_tools=true` en un replay sin la capacidad de propietario, mientras GET con capacidad inválida mantiene `result_payload=null`. El payload privado HTTP se prepara explícitamente en la base sintética para comprobar el control de acceso; no se afirma haber extraído datos reales.

**Impacto:** conocer clave/payload basta para acceder a datos cuya consulta exige credencial. **Mínimo:** aplicar la misma autorización antes de todos los retornos y sondeos del replay, independientemente del nombre de herramienta, conservando ID sin divulgar target, resultado ni error privado.

### F3 — Una credencial de edición del reporte autoriza datos administrativos (regresión G2.1.8)

**Archivo:** `backend/app/main.py:642-655`. **Instrumento:** `adversarial.py`, casos `private_auth`.

Se prepara reporte sintético con edit_token hash y una operación `ADMIN_PRIVATE_EDIT_BYPASS`, `requester_id=admin`, ligada a ese reporte. Propietario de operación y administrador reciben 200; token ajeno, inválido y anónimo reciben 404, como corresponde. Pero **X-Edit-Token del reporte devuelve 200 con resultado administrativo privado**.

**Esperado:** la capacidad ciudadana de edición no equivale a autorización administrativa. **Impacto:** ampliación indebida del ámbito de la credencial. **Mínimo:** autorizar por tipo y alcance antes de aceptar la capacidad del recurso; restringir esa alternativa a operaciones ciudadanas expresamente compatibles.

### F4 — Pérdida de primera respuesta deja recuperación incompleta (defecto previo no resuelto)

**Archivos:** `backend/app/schemas.py:102-109`, `backend/app/main.py:544`, `backend/app/agent.py:770`, frontend `src/api.ts:127`, `src/types.ts:68`, `src/App.tsx:1331`. **Instrumentos:** `serve.py`, `http_tracking.py` y `log_probe.py`.

Se prueba desde HTTP real hacia frontend Nginx→API aislada, con proveedor sintético y executor real. El cliente genera previamente una capacidad y envía `operation_token`/`idempotency_key` en JSON y `X-Operation-Token`/`Idempotency-Key` en cabeceras.

```text
Primer POST: 200, OPERATION_PENDING, ID presente, token servidor presente
Capacidad propuesta por cliente respetada: false
GET con token recibido: 200, COMMITTED; resultado consultable
GET con capacidad prepropuesta: 200, resultado oculto
Descartar token de primera respuesta y repetir POST: token_recovered=false
```

El modelo HTTP no incluye esos campos de capacidad/clave; las cabeceras no se propagan al executor. Que el executor acepte argumentos internos `operation_token` no crea un contrato cliente funcional. El replay puede devolver confirmación/resultado de herramienta sin reconstruir el token ni conservar siempre `operation_id` en el nivel superior de la respuesta agéntica; se registran también los casos de MAX_ITERATIONS producidos por el adaptador que solicita repetidamente la misma herramienta.

Un administrador o, en ciertos destinos UUID, una credencial de edición ya existente pueden consultar por otra vía. Esto **no demuestra recuperación genérica del propietario** de una operación sin recurso o identificada por tracking code, ni justifica el bypass de F3.

El frontend congelado muestra respuesta y guardrail, pero no declara `operation_id`, `operation_status` ni `query_token` en su tipo y no contiene cliente de `/api/operations`. El E2E básico del proxy no es E2E de seguimiento desde la UI.

**Impacto:** perder la primera respuesta deja al ciudadano sin la capacidad nueva; reintentar no resuelve la propiedad de forma segura. **Mínimo:** contrato HTTP explícito para capacidad cliente fuerte conservada antes del envío, o identidad autenticada recuperable; mantenerla fuera del prompt y persistirla en el cliente. Implementar seguimiento UI y probar pérdida de respuesta sin acceso al token descartado. No solucionar recuperabilidad divulgando resultados por replay.

### F5 — UNKNOWN puede confirmarse sin evidencia; GET no usa su reconciliación (preexistentes)

**Archivos:** `backend/app/db.py:291`, `backend/app/main.py:625`. **Instrumentos:** `adversarial.py`, `migration_and_unknown.py`.

Esperado: UNKNOWN→COMMITTED solo por evidencia propia. Observado: intención sin negocio ni aprobación, `mark_operation_unknown`, luego `mark_operation_committed` produce **COMMITTED**; conteo de evidencia por operation_id = **0**. El WHERE `status != 'ABORTED'` admite UNKNOWN y el trigger protege solo estados terminales previos.

En otro caso preparado correctamente desde UNKNOWN con una aprobación ligada al mismo ID, diez reconciliaciones concurrentes retornan COMMITTED. Este recorrido del helper **está corregido**. Sin embargo, GET autorizado devuelve **UNKNOWN**; llamar al helper después devuelve **COMMITTED**, porque main solo reconcilia PENDING.

**Impacto:** falsas confirmaciones por helper y polling ciudadano que no resuelve incertidumbre aunque exista evidencia. **Mínimo:** separar anexar resultado de confirmar; negar UNKNOWN en el helper genérico y reservar transición al reconciliador con prueba. Reconciliar también UNKNOWN desde la ruta autorizada y releer estados concurrentes.

### F6 — PID ausente aún se convierte en aborto; autorización ocurre después de mutar (preexistentes)

**Archivos:** `backend/app/db.py:454-496`, `backend/app/main.py:625-655`. **Instrumentos:** `adversarial.py`, `unauthorized_reconcile.json`.

El fallo de observación inyectado ya conserva PENDING: **PASS de remediación**. Sin embargo, una intención sin prueba positiva de rollback con PID inexistente `999999` se marca **ABORTED** tras consulta exitosa vacía. La preparación sintética no se presenta como aborto demostrado ni como evidencia de una escritura real perdida: demuestra exactamente la regla que el contrato prohíbe usar por sí sola.

Además, GET anónimo a una operación privada PENDING responde **404**, pero su estado durable ya cambió a **ABORTED**. La ruta reconcilia antes de autorizar.

**Impacto:** se comunica certeza a partir de ausencia y se permite a un no autorizado disparar decisiones de estado privadas. **Mínimo:** comprobar autorización antes de reconciliar y exigir evidencia inequívoca de reversión; en ausencia de ella conservar PENDING/UNKNOWN.

### F7 — El registro REST es atómico pero no describe los cambios (nueva cobertura incompleta)

**Archivo:** `backend/app/repository.py:545-561`. **Instrumento:** `adversarial.py`, caso `rest_concurrent`.

Dos PATCH autorizados concurrentes devuelven 200, aumentan versión exactamente en 2 y crean dos registros COMMITTED. **No se demuestra pérdida de updates ni fallo de atomicidad.** Ambos registros contienen requester `admin`, tipo y destino, pero `proposed_payload=null` y `result_payload=null`: no permiten conocer cambios de estado, nota ni versiones. El campo requester tampoco distingue personas detrás de una credencial administrativa compartida.

**Impacto:** evidencia de que hubo una acción, insuficiente para reconstruir qué cambio se autorizó. **Mínimo:** guardar acción y valores anteriores/nuevos/versiones en el mismo INSERT; registrar el principal real disponible sin inventar una identidad que el mecanismo de autenticación actual no conoce.

### F8 — Expiración temporal sigue tratándose como prueba de causa (preexistente)

**Archivo:** `backend/app/db.py:110-146`. **Instrumentos:** `boundaries.py`, `error_provenance.py`, `adversarial.py`.

Los casos del margen anterior están corregidos: 57014 externo con 39 ms restantes y 25P04 externo con unos 37 ms restantes devuelven `classified_local=false`. 57P01 por terminación real de backend exclusivo y 42P01 por tabla inexistente se preservan.

Se configura explícitamente timer externo de 20 ms y deadline local a 60 ms. Tras recibir 57014/25P04, la clasificación inmediata es false. Se retiene **la misma excepción externa** 70 ms antes de clasificarla: ahora devuelve true por `monotonic >= dl`. El origen no cambió; solo cambió cuándo se manejó la excepción. No se presenta como fallo de timing de una aserción ni como corrupción SQL.

**Impacto:** errores ajenos pueden normalizarse como timeout local bajo pausas de planificación/observación. **Mínimo:** conservar procedencia de la cancelación armada por esta ejecución; expiración o revocación no demuestran por sí mismas qué originó el error de PostgreSQL.

## Controles que sí pasan y migraciones

Atomicidad del executor: positivo negocio=1/COMMITTED; trigger que rechaza marcador deja negocio=0; rowcount=0 deja negocio=0; ausencia 004 impide el worker. Atomicidad REST: ledger agregado=1; ausencia de tabla produce 500 y mantiene IN_REVIEW; trigger que rechaza INSERT mantiene estado y versión previos. Reporte inexistente devuelve 404 sin registro; anónimo/inválido 401; falta de aprobación explícita 400.

El trigger 006 rechaza COMMITTED/ABORTED→PENDING/UNKNOWN/otro terminal en seis intentos SQL reales. Permite actualizar metadatos sin cambiar estado; helpers y ON CONFLICT de replay siguen funcionando. La prueba antigua que intentaba fabricar UNKNOWN cambiando un COMMITTED es ahora rechazada correctamente, no una regresión.

Concurrencia de clave idéntica: una escritura y un ID. Conflicto de payload rechazado. Replay COMMITTED sin cache no reejecuta; PENDING mantiene ID y cero segundo worker. Dos propuestas reales sincronizadas con claves diferentes dejan una sola propuesta PENDING y reporte CONFIRMED, manteniendo aprobación humana. Supervisor antes de registro en vuelo conserva ID; commit tardío termina COMMITTED; aborto SQL comprobado termina ABORTED; lectura lenta conserva TIMEOUT sin operación.

Proxy de ACK: respuesta real de COMMIT descartada, cliente OperationalError, negocio=1 y marcador COMMITTED. Reinicio: proceso escritor terminado mientras PostgreSQL mostraba `COMMIT/PgSleep`; tras desaparecer backend, negocio=1 y API importada en proceso nuevo recupera 200/COMMITTED.

Migraciones:

- Base limpia 001–006 aplicada y reaplicada, un solo trigger.
- Upgrade real con `schema_migrations` registrando 001–005 y fila COMMITTED preexistente: aplicación devuelve solo `006_operation_records_terminal_states.sql`; fila conservada; segunda aplicación devuelve `[]`.
- Actualización legítima de metadatos posterior al upgrade permitida.

## Suites, instrumentos y límites de evidencia

| Ejecución | Resultado observado |
|---|---|
| Suite completa claves vacías | **114 passed, 1 deselected**, 17,47 s |
| Suite completa claves sintéticas | **114 passed, 1 deselected**, 19,75 s |
| E2E repetido con frontend construido desde snapshot | **1 passed**, 0,21 s |
| Compilación `python -m compileall -q app tests` | Código 0 |

Una advertencia AnyIO por suite. La prueba live se excluyó explícitamente con `-m "not live"`. Se incluyen las nueve G2.1.8, siete G2.1.7 y regresiones G1, G2, M-02, COPY IN/OUT, M-06 y N-02. No se modificaron tests para obtener PASS. No se encontró configuración/comando lint Python; compileall no se presenta como lint. Los cambios documentales se verifican con `git diff --check`.

Las dos suites usaron inicialmente un frontend aislado basado en la imagen local previa, con nginx congelado, mientras terminaba el build; el diff de los commits no modifica frontend. Después se reemplazó únicamente ese contenedor aislado por la imagen recién construida y se repitió el E2E específico. `log_probe.py` también usa esa imagen congelada.

Instrumentos antiguos ejecutados y evaluados por contenido:

| Instrumento | Resultado interpretado |
|---|---|
| `independent.py` | Código 0, pero contiene caso de preparación bloqueado por trigger; no es «todos PASS». Atomicidad/replay/privacidad/excepciones inspeccionados individualmente |
| `followup.py` | Código 1 al rechazar correctamente ABORTED→COMMITTED. Observación fallida conservó PENDING. Casos restantes ejecutados en `followup_remaining.py` sin cambiar producción |
| `boundaries.py` | Código 0; ledger REST ahora aumenta 1 y ausencia provoca 500/rollback, a diferencia de G2.1.7 |
| `error_provenance.py` | Código 0; 25P04 externo antes del deadline, 57P01 y 42P01 conservados |
| `ack_loss_proxy.py` | Código 0; ACK realmente descartado y estado durable COMMITTED |
| `api_restart_check.py` | Código 0; recuperación real entre procesos y COMMITTED durable |

Se conservaron los originales de G2.1.7 adaptados únicamente en el nombre del host PostgreSQL. `followup_remaining.py` evita repetir las preparaciones ahora ilegales y corre su cola; las nuevas expectativas están en instrumentos adicionales. El primer intento de setup no esperó readiness de PostgreSQL y otro lanzó suites antes de crear sus bases; esos errores del auditor quedan en `initial_setup_attempt`. Se crearon las bases correctamente y se repitieron instrumentos desde base nueva y suites válidas. No se atribuyen esos errores a CIVIA.

El primer upgrade manual del instrumento pasó texto SQL con porcentajes como consulta parametrizada vacía y falló con ProgrammingError. Se repitió con ejecución SQL sin parámetros y, de forma adicional, upgrade con historial real en `final_probes.py`. El build frontend sin red quedó esperando npm; se interrumpió ese proceso de build exclusivo y se construyó con descarga de dependencias. Ninguno de estos ajustes modifica código o tests del producto.

`log_probe.py` conserva la capacidad solo en memoria, espera captura de logs después de sus peticiones y busca su valor sin serializarlo: `token_exposed_in_captured_logs=false`. Es PASS para logs de API y frontend capturados en ese recorrido; no una garantía sobre toda integración de logging futura. No se conservaron tokens de proveedores ni datos reales. La credencial administrativa efímera del API se guardó solo en archivo de capacidad dentro de la raíz aislada para el proceso, se eliminó al cerrar y no se incorpora al informe.

## Reproducción y evidencia

En la raíz aislada se conservan `head.zip`, `src`, `full.diff`, fuentes de instrumentos, `.log`, `.exit` y JSON de resultados. Archivos adicionales: `adversarial.py`, `serve.py`, `http_tracking.py`, `migration_and_unknown.py`, `final_probes.py`, `log_probe.py`, `unauthorized_reconcile.json`. No hay dumps de datos reales.

Configuración utilizada: red Docker **interna**, alias PostgreSQL `pg`, credencial exclusivamente sintética `audit_synthetic_only`, bases con prefijo `test_`, montaje de raíz en `/audit`, cwd `/audit/src/backend`, `PYTHONPATH=/audit/src:/audit/src/backend`. `serve.py` usa únicamente `test_api`; las suites usan `test_suite_blank` y `test_suite_synthetic` separadas. Esperar `pg_isready`, crear bases y aplicar migraciones/seed sintético antes de los instrumentos. Los scripts crean tablas/triggers: repetir desde bases nuevas y conservar cada intento en otra carpeta.

Comandos principales dentro del runner:

```text
python /audit/independent.py
python /audit/followup.py
python /audit/followup_remaining.py
python /audit/boundaries.py
python /audit/error_provenance.py
python /audit/ack_loss_proxy.py /audit
python /audit/api_restart_check.py /audit
python /audit/adversarial.py
python /audit/migration_and_unknown.py
python /audit/final_probes.py
pytest -m "not live" -q
python /audit/http_tracking.py
```

Para el scan de logs ejecutar `log_probe.py`, esperar `log_scan_requested`, capturar `docker logs` de API/frontend exclusivos en los archivos de la raíz y crear `log_scan_ready`. No imprimir capacidades. El JSON conserva solo resultados booleanos.

| Evidencia | SHA-256 |
|---|---|
| head.zip | `7E3661204564F762B11CCB935B7363155292F004498C88E5142607031C6833D6` |
| adversarial_results.json | `4126B57FE6D3D42C937B8C85380C1F9F528CA9975625D5211D5CB12743DEE210` |
| http_tracking_results.json | `81B31B3222D812F3B65ABE89045B307A2EEBA66D8580E9620C7754A65DACC74C` |
| suite_blank.log | `8236F18653136CED432AB6E99546D69A7F87DC5068F4BE0797AB7A3E3039B817` |
| suite_synthetic.log | `89F81781D4D64EF04A836810CE97BBA0D92DA58B68DADC3137A6D78EA1371137` |

## Cierre

No se corrigieron defectos ni se cambiaron fuentes/tests de producción. Sin Autopilot, commits, push, merge ni cambio de rama. El informe y `docs/estado.md` son los únicos cambios autorizados del checkout. La limpieza retira exclusivamente contenedores/red/volúmenes e imagen frontend creados por el auditor, con identidad comprobada; se conservan fuentes, logs y JSON aislados. El estado final de recursos y servicios habituales se registra en `docs/estado.md`.

La auditoría termina con este informe. Los defectos requieren otro cambio expresamente separado; los PASS de las suites no sustituyen los contratos que fallaron.
