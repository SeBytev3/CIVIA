# CIVIA — revisión funcional y de calidad de d07a1e5

Fecha: 2026-11-02, America/Bogota.

**Commit exacto:** `d07a1e5dc0a0d06ede8d41422c62928885549dbf`, rama `fix/auditoria-final`. Comparación con `a745a1ca01356253659b8db97b38fcf30ef5a260` y `docs/auditoria_codex_g2_1_1_a745a1c.md`. Se leyó también `docs/remediacion_g2_1.md`.

Alcance ajustado a la última instrucción: calidad, regresiones funcionales, pruebas unitarias/integración existentes y comprobaciones defensivas locales. No se revisó ni ejecutó Autopilot. No hubo pruebas contra proveedores o sistemas externos, cambios de producción, commits, push o merge.

**Resultado general: NO APROBADO para el cierre de G2.1.** Se corrigen varias condiciones anteriores, pero COPY válido falla, la conciliación concurrente duplica cargos y la suite completa aún intenta proveedores con claves sintéticas. La preservación incondicional de A-02 tampoco quedó demostrada.

## Matriz de resultados

| Control | Dictamen | Evidencia ejecutada |
|---|---|---|
| Cursores encadenados y envío SQL tras revocación | **PASS, casos comprobados** | `conn.cursor().execute()` y `conn.execute()` devuelven `_CapabilityCursorProxy`; rechazan otro execute tras revocar. COPY nuevo y stream pendiente también rechazan con TimeoutError. |
| COPY funcional antes del vencimiento | **FAIL** | `with cursor.copy(...) as cp: cp.rows()` produce AttributeError: `_GeneratorContextManager` no tiene rows. El wrapper conserva el gestor de contexto, no el objeto Copy devuelto por su entrada. |
| Publicación atómica y revocación | **PASS, sincronización local comprobada** | Promoción real y revoke se serializan; orden observado replaced → revoked, ambos hilos terminan. Revocación previa impide crear destino. |
| M-03 en conjunto | **FAIL** | La protección encadenada mejora, pero COPY válido está roto; la prueba existente de respuesta menor a 0,16 s falla repetidamente en este entorno. |
| Compose y relación de identidad del proxy | **PARCIAL** | Configuración original fija Nginx=.2, PostgreSQL=.10, API=.11 y confía solo en Nginx. Dos arranques desechables traducidos a 172.29/16 quedan saludables y conservan esas asignaciones; red original 172.28/16 ocupada por instalación habitual, no se alteró. |
| M-02: presupuesto por intento y contabilidad conjunta | **FAIL** | El caso 1000 consumidos impide Groq; 600+800=1400 y tres inválidos=1800. Pero dos clasificaciones autorizadas de 700 registran **2100 en vez de 1400**, por conciliar la reserva de otra ejecución. |
| Hermeticidad de toda la suite | **FAIL** | Con claves vacías: cero intentos Google/Groq observados. Con claves sintéticas: diez intentos de transporte a proveedores desde el test G1 de fallo de traza; todos bloqueados antes de salir. El archivo test_ai_and_agent sí dejó de depender del adaptador externo. |
| G1 funcional | **PASS en las pruebas existentes ejecutadas** | Los 14 tests G1 pasan tras configurar correctamente el import del evaluador. La falta de mocks de red en uno de ellos se informa por separado. |
| A-02 | **PARCIAL** | Dos reproducciones propias con reports y PostgreSQL real conservan ORIGINAL. Sin embargo una ejecución del test existente observó CORRUPTED; otras ejecuciones del mismo test pasaron. No se puede certificar ausencia de escritura tardía en todos los recorridos. |
| N-02 | **PASS, transporte simulado** | Orden de llamadas y trazas PostgreSQL coinciden: 429 Gemini → Groq; Groq 400 → Gemini terciario. No aparece llamada Gemini oculta. |

Todos los resultados corresponden al SHA completo indicado. PASS significa únicamente el comportamiento ejecutado y descrito, no una garantía sobre código arbitrario ni proveedores reales.

## Entorno y aislamiento

El árbol original estaba limpio y HEAD coincidía con el commit solicitado. Se congeló con git archive y se importó la copia, sin cambiar de rama. Raíz de trabajo y evidencia:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-d07-bbd1a7dea51f4c25b4af2fe35d211daa`

Se creó otro clúster **PostgreSQL 17.6 real**, escuchando solo en `127.0.0.1:55489`, con PGDATA nuevo. Bases nuevas: `test_d07_independent`, `test_d07_suite_blank`, `test_d07_suite_synthetic`, más nombres reservados para pruebas G1/evaluación y las bases que crea la suite en ese mismo clúster. Se reutilizaron CPython 3.13.18 y dependencias directas exactas del backend. Uploads, TEMP y TMP quedaron bajo la raíz de auditoría. No se copió .env ni se utilizaron datos privados o claves reales.

Los proveedores se sustituyeron por funciones simuladas o HTTP MockTransport; el runner de pytest bloqueó los transportes externos y registró solo test/hostname, sin claves. Los tokens administrativos de pruebas se generaron mediante CSPRNG sin imprimirlos. Las consultas, triggers, commits y lecturas de verificación PostgreSQL fueron reales.

Docker se ejecutó únicamente con proyecto `civia_d07_audit`, imágenes/contenedores de auditoría y volúmenes propios. La API se construyó desde el commit congelado. Para comprobar cuota sin dependencia IA se reemplazó únicamente el cuerpo del agente por una respuesta sintética. Nginx usó una imagen frontend local existente con el nginx.conf exacto del commit montado; no se afirma haber reconstruido el bundle frontend de este commit.

## 1. Cursores y COPY

### Correcciones anteriores verificadas

En `functional_checks.py`, una capacidad activa se vincula a get_conn. Se retiene el valor devuelto por las APIs públicas habituales, se revoca la capacidad y se intenta continuar:

| Ruta | Tipo protegido | Resultado posterior a revoke |
|---|---|---|
| conn.cursor().execute('SELECT 1') | Sí | TimeoutError |
| conn.execute('SELECT 1') | Sí | TimeoutError |
| cursor.copy iniciado después de revoke | Sí, cursor | TimeoutError |
| stream adquirido antes de revoke, primer next posterior | Sí | TimeoutError |

Se corrige el escape de cursor nativo observado en a745a1c. Las pruebas existentes correspondientes también se ejecutaron.

### Defecto funcional reproducido: COPY autorizado no puede utilizarse

Sin deadline expirado ni capacidad revocada:

```python
with db.get_conn() as conn:
    with conn.cursor().copy('COPY (SELECT 42) TO STDOUT') as cp:
        rows = cp.rows()
```

Resultado: **AttributeError: '_GeneratorContextManager' object has no attribute 'rows'**.

`backend/app/db.py:118-159` recibe el gestor de contexto que devuelve psycopg.Cursor.copy. En `__enter__` llama `self._copy_obj.__enter__()` pero descarta el objeto Copy resultante. Después intenta read/rows/write sobre el gestor original. El defecto se presenta antes de poder evaluar la lectura de filas tras revocación; **no se afirma que se haya logrado eludir el deadline mediante ese iterador**.

El test existente solo comprueba rechazo de COPY después de vencer; no cubre el flujo positivo autorizado. Por eso puede pasar mientras COPY normal falla.

**Corrección mínima:** mantener separados el gestor de contexto y el objeto Copy activo; delegar lectura/escritura en el objeto activo y salida en el gestor. Añadir una prueba positiva PostgreSQL de COPY OUT/IN y cobertura del iterador admitido con revocación. No se modificó el código durante la revisión.

## 2. Archivos: sincronización corregida

Se verificó el helper real `_atomic_write_bytes` y `ExecutionCapability.authorized_replace`. La comprobación y os.replace están bajo el mismo lock.

Prueba de concurrencia local: se intercala una barrera a la entrada del replace, conservando la operación real. Mientras el publicador posee el lock, otro hilo intenta revoke; este espera. Al liberar la barrera, se observa **replaced → revoked**. Ambos hilos terminan dentro del límite de espera de dos segundos. Si revoke ya terminó antes de solicitar almacenamiento, el helper lanza TimeoutError y el archivo no aparece.

Esto corrige la carrera anterior en la que revoke podía terminar y después publicarse el archivo. No se exige terminar por fuerza un hilo arbitrario. El PASS acredita serialización y terminación en este sistema de archivos local; no demuestra que cualquier llamada al sistema de archivos tenga una duración máxima universal. El test existente llamado «race» solo revoca primero y luego intenta publicar; la comprobación adicional sí ejecutó ambos hilos concurrentemente.

## 3. Docker Compose y direcciones configuradas

Por lectura de `docker-compose.yml`, las asignaciones ahora son disjuntas:

| Servicio | Configuración original |
|---|---|
| frontend/Nginx | 172.28.0.2 |
| PostgreSQL | 172.28.0.10 |
| API | 172.28.0.11 |

`TRUSTED_PROXIES` por defecto es únicamente **172.28.0.2**, tanto en Compose como en config.py. No conserva 172.18.0.2 ni rangos Docker completos. Uvicorn conserva `--no-proxy-headers`.

El intento de crear el proyecto exclusivo con la subred original falló: **Pool overlaps with other one on this address space**. Una inspección de solo lectura confirmó que `civia_civia_net`, de la instalación habitual, ya usa 172.28.0.0/16. No se conectaron los contenedores de prueba a ella ni se detuvo/eliminó esa red. **No es evidencia de que el commit vuelva a asignar .2 a la BD**; es una limitación de coexistencia del entorno de prueba.

Para verificar funcionalmente el despliegue sin tocar la instalación, un override externo tradujo exclusivamente subred, IPs y confianza del proxy a **172.29.0.0/16**, conservando sufijos .2/.10/.11; además usó puertos host 58089/58189 y datos sintéticos. Se ejecutaron dos arranques desde red y volúmenes propios vacíos, eliminándolos entre ambos.

En ambos, Docker Network Inspect confirmó:

- frontend: **172.29.0.2/16**.
- db: **172.29.0.10/16**.
- api: **172.29.0.11/16**.
- Los tres servicios terminaron saludables.

Con cuota dos y peticiones sintéticas:

| Recorrido Docker real, cabeceras XFF/X-Real-IP variables | Resultado |
|---|---|
| Cliente .9 → API directo | **200/200/429** |
| Cliente .20 → Nginx → API | **200/200/429** |
| Cliente .21 → Nginx → API | **200/200/429** |

Los clientes legítimos detrás de Nginx conservaron cuotas independientes. No reapareció la confusión BD/proxy en la topología probada. Se mantiene **PARCIAL** porque no se ejecutó un arranque exclusivo con las IP literales originales; no se presenta la traducción como si hubiera usado 172.28.

## 4. Presupuesto y conciliación

### Comportamientos corregidos y conservados

Proveedores simulados, router/clasificador/agent reales y PostgreSQL desechable:

| Escenario | Resultado |
|---|---|
| Saldo 1000; Gemini devuelve JSON inválido con 1000 consumidos | **Una llamada**, 1000 usados, reserva final 0, MAX_TOKENS; Groq no se inicia |
| Gemini inválido 600 + Groq válido 800, saldo 6000 | **1400**, sin duplicación en recorrido secuencial |
| Tres inválidos de 600 | **1800**, sin duplicación secuencial |
| Dos reservas de 700 con saldo 1000 | La prueba existente de exclusión concurrente pasa |
| Dos turnos del agente de 20 más clasificación de 1600 | **1640**, tracker presente en el worker |
| Presupuesto 200 frente a entrada textual estimada 394 más imagen/salida | **Cero llamadas**, MAX_TOKENS |
| Consumo real 1600 superior a reserva/presupuesto 1000 | Registra **1600 una vez**, reserva final 0, siguiente clasificación bloqueada |
| Éxito sin metadatos | **732 estimados**, marcado como desconocido |
| Todos los turnos principales fallan con NETWORK_ERROR | **1290 estimados**, tokens_estimated=true, unknown_consumption=true, degradación SQL |

No se equiparó una estimación con uso real de una cuenta. Si una respuesta declara más uso que el estimado, la contabilidad no debe truncarlo; bloquear llamadas posteriores es distinto de garantizar retrospectivamente un consumo inferior al máximo.

### Defecto reproducido: doble cargo con dos llamadas autorizadas

`functional_checks.py` ejecuta dos clasificaciones mediante ThreadPoolExecutor, compartiendo tracker de **6000**. Ambas están autorizadas y reservan su payload. Se controla únicamente cuándo retorna cada proveedor simulado; cada respuesta declara **600+100=700**.

1. Ambas llamadas están dentro del router con sus reservas activas.
2. Se permite terminar la primera mientras la segunda sigue esperando.
3. Tras terminar la primera, el tracker ya declara **1400**, y la reserva que correspondía a la segunda ha desaparecido.
4. Se permite terminar la segunda.

**Observado: 2 análisis completados, total 2100, esperado 1400; reserva final 0.**

Causa: `backend/app/agent.py:455-469` deduce si su reserva sigue activa mirando el **total global** `tracker.reserved_tokens >= reserved_upfront`. El router ya concilió la reserva de la primera; pero como otra llamada aún tiene una reserva equivalente, el finally la confunde con la propia, vuelve a cargar el meta de 700 y libera reserva ajena.

No es el caso de saldo 1000 que ya bloquea correctamente a la segunda llamada. Es el flujo de **dos llamadas legítimamente autorizadas** que la nueva coordinación debe soportar. Las pruebas de exclusión con saldo insuficiente no detectan el doble cargo.

**Corrección mínima:** identificar la reserva por ejecución/intento, con estado de transferencia y conciliación propios; no deducir propiedad a partir del saldo global. El router y la herramienta deben conciliar cada reserva una sola vez incluso mientras existan otras activas. Añadir una prueba con dos llamadas admitidas y finalización escalonada.

### Errores y reintentos sin metadatos

503 seguido de éxito sin uso declarado: dos llamadas observan saldo disponible 268 durante la reserva de 732; total final **732 estimados**, unknown marcado. El primer error libera su reserva sin sumar una estimación individual; el éxito posterior sí suma su propia estimación. Los flags impiden presentar ese número como consumo exacto, pero **no verifican una estimación acumulada de cada intento desconocido** como afirma la remediación. No se afirma que un HTTP 503 haya consumido necesariamente tokens.

La reserva por intento conocido se corrigió; el doble cargo concurrente demostrado impide aprobar M-02 con independencia de esta limitación. Conviene fijar y probar la semántica de estimación por error sin inventar uso remoto.

## 5. Suite existente y dependencia de servicios

Se ejecutó la suite completa dos veces, en procesos y bases separados, con claves vacías y después con claves sintéticas no válidas. HTTPTransport y conexiones no locales quedaron bloqueados por el runner; las solicitudes locales de TestClient y los transportes simulados se conservaron.

Tras corregir únicamente el PYTHONPATH del runner para incluir la raíz congelada `src` (necesaria para importar eval):

| Modo | Resultado completo | Tiempo |
|---|---|---:|
| Claves vacías | **79 passed, 2 failed, 2 skipped** | 21,34 s |
| Claves sintéticas | **81 passed, 1 failed, 1 skipped** | 29,91 s |

Un primer pase del runner omitía `src` y produjo ModuleNotFoundError al importar eval; ese error era de preparación de auditoría y no se contabiliza como defecto del producto. Los logs iniciales se conservaron. La repetición fue necesaria para corregir esa preparación, no para buscar un resultado verde.

### Fallos observados de la suite

- `test_g2_1_1_m03_retained_connection_late_sql_rejected_by_execution_capability`, línea 726: exige retorno menor a 0,16 s. Midió **0,3031 s** en el pase vacío y **0,3079 s** en el sintético. Repetido aisladamente dio **0,1680 s** y volvió a fallar. Son incumplimientos del objetivo temporal de ese test en este entorno Windows, **no prueba de que se ejecutara SQL vencido en esa repetición**; la aserción de tiempo detiene el test antes de sus verificaciones posteriores.
- `test_g2_1_a02_deferred_constraint_trigger_cancelled_on_timeout`, línea 153: en el pase vacío la conexión independiente observó **CORRUPTED en vez de ORIGINAL**. En el pase sintético y la repetición aislada pasó. No se oculta el resultado intermitente ni se afirma que todas las ejecuciones fallen.
- E2E frontend se omitió porque el pytest host no dispone de la resolución de servicio `frontend`. Las comprobaciones Nginx/Docker independientes sí se ejecutaron, con la traducción de subred informada.
- La prueba opcional live se omite con claves vacías y pasa como no-op con claves sintéticas (`pass`); **no se contó como comprobación de conectividad real**.

### Hermeticidad: mejora parcial, defecto fuera de test_ai_and_agent

La sustitución multimodal de `test_ai_and_agent.py` ahora es incondicional y sus pruebas ejecutadas no llegaron a transporte Google/Groq. Se corrige el comportamiento señalado en a745a1c para ese archivo.

Pero la suite completa con claves sintéticas registró **diez intentos de transporte** hacia Google/Groq desde `test_a06_idempotency_and_post_commit_trace_failure_isolation`, en `test_audit_g1_security.py`. Esa prueba habilita auto_analyze y sustituye la traza, pero no los adaptadores que podrían llamar al proveedor. Los fallos de red bloqueados se absorben y el test puede pasar.

Ningún intento salió al exterior: el guard de auditoría lanza ConnectError en HTTPTransport antes de abrir conexión. El JSON de evidencia contiene únicamente hostname y nombre de test. La resolución local `frontend` se registra aparte y no se cuenta como proveedor externo.

**Corrección mínima:** usar proveedor/transporte simulado también en esa prueba G1, o una fixture hermética común a toda la suite ordinaria. Hacer fallar la suite si intenta llegar a un proveedor, en vez de limitarse a absorber el error en la aplicación.

## 6. Regresiones G1, A-02 y N-02

**G1:** los 14 tests existentes pasan en los recorridos completos con preparación correcta: autorización, tokens, capacidad de edición, idempotencia, aprobación y limpieza/centinelas no muestran regresión funcional en esas pruebas. Que una de esas pruebas no sea hermética es un defecto del aislamiento del test, separado de sus aserciones funcionales. No se repitió toda la batería independiente G1 anterior innecesariamente.

**A-02:** además del fallo intermitente existente ya descrito, se repitió independientemente sobre reports con trigger diferido de 0,18 s, deadline 0,25 y commit iniciado dentro del plazo:

| Método | Entrada a commit | Retorno | Estado leído por otra conexión tras terminar el worker y esperar |
|---|---:|---:|---|
| conn.commit envuelto | 0,1264 s | 0,4645 s | ORIGINAL |
| checked_commit | 0,1199 s | 0,4443 s | ORIGINAL |

Estos PASS usan get_conn del proyecto. El test que falló usa psycopg.connect directo, registro de conexión y checked_commit. Por tanto el PASS de un recorrido no invalida el fallo del otro. No se demostró que d07a1e5 introdujera el problema temporal: **sí se demostró que no permite certificar el requisito en todos los casos probados**.

`checked_commit` depende de un Timer de Python que envía cancelación. No constituye por sí mismo un deadline impuesto por PostgreSQL; si la cancelación se procesa tarde, el commit puede ganar. Esta es una explicación técnicamente sustentada del riesgo, no una cronología interna medida de la ejecución fallida. Para cerrar el control: reproducir y corregir ese recorrido, aplicar límite de servidor/transacción coherente en las conexiones admitidas y verificar finalización del worker antes de concluir la ausencia de escrituras. No basta con aumentar el sleep o retirar la aserción de datos.

**N-02:** adaptadores reales con HTTP MockTransport y trazas SQL reales mantienen Gemini → Groq tras 429 y Gemini terciario solo después de fallar Groq. También pasan JSON inválido primario y turno de agente con 429. Cantidad/modelos de trazas coinciden con llamadas; no se evaluó accesibilidad real de los modelos.

## Evidencia y correcciones mínimas pendientes

La raíz temporal conserva:

- `functional_checks.py`, `functional_results.json`: cursores, COPY, archivos y doble conciliación.
- `core_probe.py`, `core_results.json`, `core.log`: commits PostgreSQL, HTTP, router y tracker integrado.
- `accounting_exact.py`, `exact_results.json`, `retry_probe.py`, `retry_results.json`, `main_unknown.json`.
- `run_suite.py`, `network_guard.py`, `suite_blank_corrected.log`, `suite_synthetic_corrected.log`, `network_blank_corrected.json`, `network_synthetic_corrected.json`, `focused_timing.log`.
- `docker_audit.py`, `docker_up_1.log`: intento original bloqueado por subred ocupada.
- `docker_translated.py`, `docker_translated_up_1.log`, `docker_translated_up_2.log`, `docker_translated_network_1.json`, `docker_translated_network_2.json`, `nginx_results.json`.
- `n02_probe.py`, `n02_results.json` y copia congelada `head.zip`.

Los scripts se ejecutaron con PYTHONPATH apuntando a `src` y `src/backend`, URLs del puerto desechable 55489, uploads/TEMP propios y sin .env. Los que crean triggers requieren una base nueva para repetir desde cero. El primer script funcional se detuvo al encontrar AttributeError en COPY; se cambió únicamente el reproductor para registrar la excepción y continuar con las demás comprobaciones, sin modificar producción ni ocultar el fallo.

Prioridad mínima de corrección:

1. Eliminar la doble conciliación de reservas ajenas y cubrir dos operaciones concurrentes autorizadas.
2. Corregir el contrato del wrapper COPY y probar su flujo válido.
3. Resolver/estabilizar el caso PostgreSQL que observó CORRUPTED y separar esa garantía del umbral de latencia dependiente del entorno.
4. Completar mocks y guard de proveedores en toda la suite, no solo un archivo.

La topología disjunta y la sincronización de archivos muestran mejoras comprobadas; no compensan los defectos anteriores. **No corresponde recomendar aún el cierre de G2.1 ni afirmar que todas las regresiones pasan.**

## Cierre

Se detuvo PostgreSQL portable y se eliminaron únicamente los contenedores, red y volúmenes de `civia_d07_audit`. No se tocó la instalación habitual. HEAD permanece en el commit solicitado; el único archivo nuevo del repositorio original es este informe. Sin cambios de producción ni publicaciones.

Huellas SHA256:

| Evidencia | SHA256 |
|---|---|
| head.zip | `9E542BF4F16EE07537A605807215424279687771993CF436811991525817ED2A` |
| functional_results.json | `381260889CB47BDB6DF3577EA6407E4E383845D805F4F89776F512479E058D61` |
| suite_blank_corrected.log | `14C6C083A8D36D9504E51DD09699E6607E871071D2F3F50B672D86615CC27A80` |
| suite_synthetic_corrected.log | `80DC02F7A5B212B757B0B70E496AE7D71EC4F8521BE92D548EBE323E7490452E` |
| network_synthetic_corrected.json | `07FAA5427A1B3D75E0B26B4436CC9897D9ABED9915DF5C46F8908301FE6375C6` |
| docker_translated_network_1.json | `63C7B47C94D9E38125336AA26A49F91E67FC236CF246DDF95CB8A57DACE9B106` |
| docker_translated_network_2.json | `2A28726450DBF0D3E75941850594282F7B63A4585B2FC9CEC14073B6F6B68F7C` |
