# CIVIA — aceptación focalizada G2.1.4

Fecha: 2026-11-03, America/Bogota.

**Commit exacto:** `95eecba8a5db1eea1ea862b5433622c56c5d17ec`, rama `fix/auditoria-final`, congelado mediante git archive. Referencias: `docs/auditoria_codex_g2_1_3_4a99705.md`, sección 9 de `docs/remediacion_g2_1.md` y bloque G2.1.4 de `docs/estado.md`.

## Dictamen

**NO APROBADO.** La hermeticidad pendiente quedó corregida en las pruebas ejecutadas. Los cuatro casos anteriores 61–64 también pasan. Sin embargo, **A-02 sigue permitiendo commits confirmados después del deadline de 0,25 s** cuando ambas configuraciones reciben pausas finitas de planificación. Se reprodujo en PostgreSQL 17 real por ambos métodos.

No se realizó una auditoría general, no se revisó ni ejecutó Autopilot y no se cambiaron aserciones o código de producción. No hubo commits, push, merge ni cambio de rama.

## Matriz de aceptación

| Control | Dictamen | Evidencia reproducida |
|---|---|---|
| A-02 | **FAIL** | Casos originales 61–64: ORIGINAL. Variante con 40 ms antes de cada configuración: commits reales a **0,283–0,294 s**, posteriores al TIMEOUT y al deadline **0,25 s**, con trigger diferido **0,18 s**. |
| Hermeticidad | **PASS en ambos modos** | **0 intentos inesperados Google/Groq** con claves vacías y sintéticas. Los turnos principales están sustituidos. Un intento deliberado capturado por el producto produce fallo de pytest **en teardown del fixture del proyecto**. |
| M-02, regresión mínima | **PASS** | Dos clasificaciones simultáneas de 700: **1400** finales, reservas **0**. La primera registra solo 700 mientras la segunda conserva su reserva. |
| M-03 COPY/revocación, regresión mínima | **PASS** | COPY IN/OUT e iteradores funcionales; nuevas lecturas/escrituras revocadas producen TimeoutError. Cursores encadenados y publicación serializada conservan PASS. |
| G1 y N-02, regresión mínima | **PASS en casos ejecutados** | Suite G1 sin fallos; orden y trazas de fallback preservados con transporte simulado. |
| M-06, regresión mínima | **PASS de configuración/tests** | Compose/proxy sin cambios frente a la base y pruebas existentes de confianza/cuota aprobadas. No se repitió despliegue Docker de la aplicación. |

La suite ordinaria completa no quedó verde: en ambos modos una prueba de cancelación recibe QueryCanceled donde espera TimeoutError. Se informa abajo; no se confunde esa cancelación efectiva con el commit tardío demostrado en otro reproductor.

## Aislamiento y versión

HEAD coincidía con el SHA solicitado y el árbol estaba limpio. Código importado exclusivamente desde la copia congelada en:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-95ee-1cb52b92ad0649b8a4138cfe4a495507`

PostgreSQL **17.11 real**, imagen local postgres:17-alpine, contenedor `civia_95ee_pg`, red `civia_95ee_pgnet` y volumen `civia_95ee_pgdata`, todos exclusivos. Puerto solo en `127.0.0.1:55493`; bases nuevas `test_95ee_independent`, `test_95ee_blank`, `test_95ee_synthetic` y bases propias creadas por tests en ese mismo servidor. No se conectó a bases o servicios habituales.

CPython 3.13.18, psycopg 3.2.6 y dependencias del backend reutilizadas. Archivos, uploads y TEMP/TMP desechables bajo la raíz indicada. Sin .env, claves reales ni datos privados. Administradores CSPRNG efímeros sin imprimirlos; proveedores y tokens consumidos, simulados. SQL, triggers, COPY, COMMIT, cancelaciones y verificaciones fueron reales.

## 1. A-02: corrección parcial del intervalo relativo

### Los cuatro casos anteriores pasan

Se repitió el reproductor anterior, con conexiones registradas, pausa **0,13 s** antes del SET LOCAL inicial, cancelación asíncrona retrasada **0,15 s**, trigger diferido **0,18 s** y deadline total **0,25 s**.

| Caso | Método | Retorno del llamador | Worker finalizado | Estado definitivo |
|---|---|---:|---|---|
| 61 | checked_commit | 0,2626 s, TimeoutError | Sí, TimeoutError | **ORIGINAL** |
| 62 | _wrapped_commit | 0,2651 s, TimeoutError | Sí, TimeoutError | **ORIGINAL** |
| 63 | checked_commit | 0,2616 s, TimeoutError | Sí, TimeoutError | **ORIGINAL** |
| 64 | _wrapped_commit | 0,2639 s, TimeoutError | Sí, TimeoutError | **ORIGINAL** |

La nueva reevaluación y set_config acortan correctamente el margen de estos casos. La diferencia de algunos milisegundos de retorno no se considera fallo de integridad.

### El motor sí puede proteger sin Timer de Python

Se ejecutaron repeticiones secuenciales y concurrentes con pausas previas variadas, además de cuatro casos que suprimen únicamente el Timer de Python para aislar el límite PostgreSQL. Se mantuvieron filas ORIGINAL; el log real del servidor contiene **terminating connection due to transaction timeout**. No se simuló la respuesta de la BD.

Una comprobación adicional interpuso **0,13 s después del último set_config y antes de transmitir COMMIT**, sin Timer de Python y con cancelación del llamador retrasada: ambos métodos abortaron y conservaron ORIGINAL. En esos casos la primera configuración ya había instalado un límite suficiente. Se distingue este PASS de la variante que falla a continuación.

### FAIL reproducido: dos remanentes calculados antes de sus respectivas pausas

Archivo: `balanced_config_checks.py`; resultado: `balanced_config_results.json`.

Se usa el mismo deadline de **0,25 s**, el mismo trigger diferido real de **0,18 s** y conexiones registradas. Se introducen pausas locales finitas, sin modificar el SQL ni las decisiones del producto:

1. **40 ms** después de que el helper calcula el primer remanente y antes de enviar SET LOCAL transaction_timeout.
2. Un intervalo de procesamiento **5 ms** después de volver de ese SET, para ejercitar de forma determinista el camino documentado de ajuste.
3. **40 ms** después de calcular el segundo remanente y antes de enviar SELECT set_config.

El cálculo y el envío se instrumentan en el cursor de esa conexión; PostgreSQL ejecuta realmente ambas sentencias y el trigger. Se registra cuándo cada configuración retorna aplicada y cuándo COMMIT retorna éxito.

Se probaron dos modalidades para cada helper:

- **Servidor aislado:** el Timer Python se sustituye por un objeto inerte; la cancelación asíncrona del llamador conserva la pausa previa de 0,15 s. Comprueba si PostgreSQL es una protección efectiva por sí sola.
- **Timer activo con retraso finito:** Timer real programado con **0,15 s de retraso adicional** en su ejecución; no se elimina la cancelación. Simula el retraso de planificación del hilo de cancelación. La cancelación asíncrona del llamador también conserva el retraso de 0,15 s del reproductor anterior.

| Caso | Método / protección | Timeout devuelto | COMMIT confirmado | Primera lectura al retorno | Lectura tras fin del worker |
|---|---|---:|---:|---|---|
| 81 | checked, servidor aislado | 0,2683 s | **0,2875 s** | ORIGINAL | **CHANGED** |
| 82 | wrapped, servidor aislado | 0,2555 s | **0,2942 s** | ORIGINAL | **CHANGED** |
| 83 | checked, Timer retrasado | 0,2565 s | **0,2936 s** | ORIGINAL | **CHANGED** |
| 84 | wrapped, Timer retrasado | 0,2612 s | **0,2832 s** | ORIGINAL | **CHANGED** |

Los cuatro workers terminaron. No hubo excepción en el cuerpo que confirmó el commit; el executor ya había declarado TIMEOUT. Otra conexión psql confirmó después CHANGED en las cuatro filas.

Ejemplo completo del caso 84, dentro del helper wrapped:

```text
0,0097 s  calcula remanente inicial: 240 ms
           pausa de 40 ms antes de enviar
0,0521 s  PostgreSQL termina SET LOCAL transaction_timeout = 240
           procesamiento de 5 ms
0,0574 s  calcula remanente para ajuste: 192 ms
           pausa de 40 ms antes de enviar
0,0991 s  PostgreSQL termina set_config(..., '192', true)
0,0994 s  entra al commit real
0,2500 s  deadline absoluto
0,2612 s  llamador recibe TimeoutError
           otra conexión todavía lee ORIGINAL
0,2832 s  COMMIT retorna éxito al worker
           al terminar el worker, otra conexión lee CHANGED
```

La última comprobación monotónica todavía ve saldo positivo antes del commit. El Timer alineado al plazo original ayuda si se ejecuta puntualmente; el límite del motor, en cambio, recibió nuevamente un **intervalo calculado antes de otra espera**. La segunda lectura local no convierte ese intervalo en un deadline absoluto del servidor.

Precisión de los relojes: los instantes de configuración registrados son el envío instrumentado y el retorno exitoso de execute al cliente; el servidor aplica el GUC dentro de ese intervalo y necesariamente antes del retorno. Son cotas de aplicación, no una afirmación de conocer el ciclo exacto de CPU del backend PostgreSQL. Los COMMIT confirmados se midieron por su retorno real y se corroboraron con lecturas independientes; la incertidumbre del viaje SQL no cambia el hecho de que las escrituras aparecen después del TIMEOUT.

La prueba con Timer retrasado es la evidencia con cancelación aún activa. La modalidad sin Timer solo aísla la protección PostgreSQL; no se presenta como configuración normal de producción. Ambas satisfacen la comprobación solicitada de que la integridad no dependa exclusivamente de la puntualidad del hilo de cancelación.

No se usa una espera fija de asentamiento para decidir el resultado. Se lee desde otra conexión al retorno del llamador y, para el estado definitivo, después del evento de finalización real del trabajador. Así se observa el cambio tardío en vez de ocultarlo.

### Los commits legítimos siguen funcionando

Con el mismo trigger de 0,18 s y límite 0,25, sin pausas artificiales:

| Método | COMMIT confirmado | Resultado |
|---|---:|---|
| checked_commit | **0,2067 s** | Éxito, estado CHANGED |
| _wrapped_commit | **0,1988 s** | Éxito, estado CHANGED |

No se exige impedir transacciones autorizadas ni terminar forzosamente hilos. Se evalúa exclusivamente la garantía declarada de no confirmar después del deadline.

### Cambio mínimo necesario

Referencias: `backend/app/db.py:350-424` y `:469-539`, en especial las dos configuraciones relativas y las comprobaciones de remanente.

**Corregir solamente la instalación del deadline en estos helpers para que el motor reciba un vencimiento anclado al plazo original, no un remanente que puede quedar obsoleto durante el envío.** Evaluar el saldo en el dominio temporal del servidor al aplicar la restricción, o usar un mecanismo equivalente que no amplíe el plazo por las pausas de transporte/planificación; abortar si no puede instalarse el límite requerido. Conservar el Timer como respaldo, no como única protección efectiva. Añadir otra lectura Python seguida de otro set_config relativo reproduce la misma ventana.

Las pruebas de aceptación deben conservar los casos 61–64 y añadir los casos 81–84 y los commits legítimos. No es necesario rediseñar reservas, COPY, proxy ni el centinela, que pasaron sus comprobaciones.

**A-02 FAIL:** hay escrituras tardías confirmadas, no solo una demora de respuesta.

## 2. Hermeticidad: defecto pendiente corregido

### Suite completa ordinaria, dos modos

Se ejecutaron todos los tests backend ordinarios con `-m "not live"`, sin modificar sus aserciones. Se usan bases separadas. El contador independiente envuelve Client.send después de instalarse las fixtures y detecta incluso intentos que el producto absorba; el bloqueo de transportes/socket impide tráfico externo.

| Modo | Resultado pytest | Intentos inesperados Google/Groq | Control positivo esperado | Solicitudes reales a proveedores |
|---|---|---:|---:|---:|
| Claves vacías | **87 passed, 1 failed, 1 skipped, 1 deselected**, 10,95 s | **0** | **1** | **0** |
| Claves sintéticas no válidas | **87 passed, 1 failed, 1 skipped, 1 deselected**, 11,46 s | **0** | **1** | **0** |

El control positivo es `test_hermetic_guard_fails_immediately_on_unexpected_external_http`; su petición deliberada se bloquea en el fixture y se contabiliza por separado, no como un intento accidental. El único destino no local bloqueado por el transporte host fue `frontend`, servicio local de Compose no resuelto aquí; no se cuenta como proveedor externo.

La prueba opcional live está marcada y se excluyó explícitamente: **una deselect**, incluso con claves sintéticas. No se ejecutó por accidente ni se presentó como verificación real de conectividad.

Las fixtures sustituyen los adaptadores multimodales y los de turnos principales. Los tests que necesitan otro comportamiento los sustituyen localmente. No se observaron nuevos intentos inesperados.

### El fixture del proyecto falla en teardown aunque la aplicación capture la excepción

Se creó fuera del código congelado una prueba independiente que carga `tests.conftest`, deja un único nodo de proveedor y llama al router real con clave sintética. El router intenta un envío; el fixture lanza RuntimeError; el producto lo captura y retorna degradación honesta. Las aserciones del cuerpo de la prueba pasan.

Al finalizar, **el fixture original de CIVIA** detecta su intento acumulado y ejecuta pytest.fail en teardown:

```text
1 passed, 1 error
ERROR at teardown:
Centinela de hermeticidad detectó 1 intento HTTP inesperado
pytest exit = 1
transport_attempts = []
```

Este control se ejecutó **sin la aserción de fallo del plugin auditor**, para atribuir el fallo de teardown al proyecto y no al contador independiente. El transporte externo de respaldo siguió bloqueado; no fue alcanzado. No se editó conftest ni el producto.

Referencias: `backend/tests/conftest.py:101-155` (turnos simulados), `:157-185` (lista de intentos y fallo en teardown), fixtures multimodales y marca live de test_ai_and_agent.py.

**Hermeticidad PASS** para los requisitos solicitados.

### Fallo restante de la suite, distinto de hermeticidad

En ambos modos falla la prueba existente `test_g2_1_a02_active_conn_cancellation_on_slow_worker` (`test_audit_g2_1_remediation.py:179`). Durante `SELECT pg_sleep(1.0)`, PostgreSQL aplica statement_timeout y el executor devuelve **psycopg.errors.QueryCanceled**, mientras la prueba espera **TimeoutError**.

Se ejecutó sin cambiar aserciones. La cancelación del servidor fue efectiva; ese fallo por tipo de excepción **no demuestra un commit tardío en esa prueba**. Tampoco permite afirmar que la suite completa haya pasado. La evidencia de escritura tardía es el reproductor separado 81–84.

E2E frontend se omitió porque espera un servicio de Compose desde el pytest host. Los warnings de deprecación AnyIO no afectan los resultados descritos.

## Regresiones mínimas preservadas

- **M-02:** dos clasificaciones reales a través de ThreadPoolExecutor con finalización escalonada: 700 tras la primera, reserva ajena de 732 preservada, total **1400** y reservas **0** al final. Idempotencia de manija comprobada con ocho conciliadores y liberación repetida.
- **M-03:** COPY IN persiste dos filas válidas; COPY OUT devuelve filas y chunks. rows, iterador y write_row rechazan después de revoke; la transacción de escritura revocada no agrega filas. Cursores encadenados protegidos. Publicación atómica y revoke se serializan y terminan en la comprobación local.
- **G1:** sus 14 pruebas existentes pasan en ambos modos.
- **N-02:** adaptadores reales con MockTransport y trazas PostgreSQL conservan primario 429 → Groq, y terciario Gemini únicamente tras fallar Groq; orden, modelos y número de trazas coinciden. No se probó accesibilidad real de proveedores.
- **M-06:** configuración Compose/proxy y tests existentes sin regresión. No se repitieron despliegues históricos fuera del alcance.

## Evidencia y reproducción

La raíz temporal conserva:

| Archivos | Contenido |
|---|---|
| head.zip, src | Commit congelado |
| registered_scheduling.py, registered_scheduling_results.json | Casos anteriores 61–64, ahora ORIGINAL |
| transaction_checks.py, transaction_results.json | Repeticiones secuenciales/concurrentes y servidor aislado |
| final_config_checks.py, final_config_results.json | Pausa de 0,13 s después de la última configuración y otras variantes que abortan |
| balanced_config_checks.py, balanced_config_results.json | Casos 81–84 con escrituras tardías |
| legitimate_checks.py, legitimate_results.json | Commits autorizados dentro de plazo |
| run_suite.py, network_guard.py | Runner y contador/bloqueo independientes |
| suite_blank.log, suite_synthetic.log, network_blank.json, network_synthetic.json | Resultados completos e intentos exactos |
| sentinel_probe_test.py, run_sentinel_probe.py, sentinel_probe.log, sentinel_probe_result.json | Fallo de teardown del fixture original ante una violación capturada |
| functional_checks.py, functional_results.json, copy_and_reservations.py, copy_reservation_results.json | Regresiones de reservas/COPY/archivos |
| n02_probe.py, n02_results.json | Fallback y trazas |
| final_states.txt, postgres_timeout_events.log | Lectura final psql y eventos reales de timeout de servidor |

Los scripts importan `src`/`src/backend` del archivo congelado, con DATABASE_URL al puerto 55493/base desechable y uploads/TEMP propios. Los reproductores que crean tablas/triggers requieren una base nueva para repetir. El trigger es `AFTER UPDATE DEFERRABLE INITIALLY DEFERRED`, ejecuta pg_sleep(0.18) al escribir CHANGED, y las filas comienzan ORIGINAL.

Las pausas se intercalan alrededor de los envíos de configuración y del despacho de cancelación, sin sustituir SQL, COMMIT o verificación. Se registran valores calculados, retorno de cada configuración, retorno de COMMIT, TIMEOUT del llamador y fin del worker. No se usa un sleep fijo para dar por definitivos los datos.

## Conclusión de aceptación

La corrección de hermeticidad puede aceptarse dentro del alcance verificado. El ajuste de A-02 resuelve los cuatro casos anteriores, pero no su garantía transaccional bajo las variantes demostradas. **NO APROBADO: G2.1 no debe cerrarse todavía.** El cambio pendiente se limita al deadline efectivo de commit en los helpers de BD, conservando los componentes que ya pasaron.

## Cierre y huellas

Se detuvo y eliminó únicamente `civia_95ee_pg`, su red y volumen exclusivos. La evidencia de archivos permanece en la raíz temporal; no se tocaron servicios habituales. HEAD conserva el SHA auditado y el único archivo nuevo del repositorio original es este informe. Sin publicaciones ni cambios de producción.

SHA256 de evidencias principales:

| Archivo | Huella |
|---|---|
| head.zip | `7C6FCB286DC5A9C0CA56427B9F1F0B8F2B7BD79B68A99E5FFDDBDE53F876B678` |
| balanced_config_results.json | `F8FE75ECBD4275DB74384F198FF2AD3C29C9F6A0C02486B4261B6EE7E6DAE00C` |
| registered_scheduling_results.json | `D90AE49CF6E2E35DDB0C953B17C7A986C23202E42C1C5FCBCC20650175D6FB29` |
| final_config_results.json | `93FFF259D78CC77559E8A1FBD1202957FDE0A2A58DCD78B07F26C86F4FF72A76` |
| legitimate_results.json | `F69C5B5BE543AA4FDC0EF06E9E6B2FDB8C8E61C567405046108C67A4B88D2D15` |
| network_blank.json / network_synthetic.json | `86B63160E0D3F4627FCE0DBD5FF5E2D3F89AB697F6F51D53918A07B174F1348A` |
| sentinel_probe_result.json | `4CACE54EA5AD00289EE34868A545E25B71E66D6B76D76B037B0FBF02461D9CDA` |
