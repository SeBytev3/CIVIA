# CIVIA — auditoría exclusiva del Bloque G1

Referencia: docs/auditoria_codex_final.md. Fecha: 2026-11-01, America/Bogota.

**Versión exacta auditada:** `48460b65317d995242a9d87320616401ed7f45a4`, rama `fix/auditoria-final`. Árbol limpio al comenzar. Se congeló ese HEAD con git archive; las ejecuciones usaron la copia, no fuentes modificadas. No se cambió de rama, no se modificó producción ni se publicó nada.

**Resultado de cierre: G1 no aprobado.** Hay correcciones verificadas, pero ninguno de los siete hallazgos puede cerrarse íntegramente con las condiciones adversariales documentadas abajo. Un FAIL no significa que todas sus pruebas fallen: cada tabla distingue controles aprobados de la condición residual que impide el cierre.

## Entorno y evidencia

- PostgreSQL **17.6 real**, clúster recién inicializado, escucha solo en `127.0.0.1:55475`, rol local de auditoría. No se usó la BD habitual ni SQLite, emulación o mocks de SQL.
- Bases nuevas: `test_g1_independent`, `test_g1_suite`, `eval_g1_independent` y `civia_prod_probe`. Esta última es también desechable y pertenece exclusivamente al clúster nuevo: su nombre permite probar que la protección no debe depender de que la BD habitual se llame exactamente civia.
- Python 3.13.18 y backend/requirements.txt exacto. Claves de IA vacías; respuestas de modelos y fallos de traza/I/O fueron inyectados con datos sintéticos. PostgreSQL, sus restricciones, bloqueos, commits y archivos en disco fueron reales.
- PGDATA, uploads y TEMP/TMP se aislaron bajo `C:\Users\Jhoesp\AppData\Local\Temp\civia-g1-0ac7349344684c709eb4043f9adfe20e`. No se copiaron .env ni datos privados. Docker no está disponible: se emplearon directorios/almacenamiento desechables, **no se afirma haber probado volúmenes Docker**.
- La suite G1 existente, sin cambiarla, obtuvo **6 passed**, un warning de deprecación, 7,04 s: `python -m pytest backend/tests/test_audit_g1_security.py -q --tb=short`. Estos seis casos no cubren los contraejemplos independientes siguientes.
- Reproductores: `probe_g1.py` y `probe_sentinels.py`; evidencia estructurada: `observations.json` y `sentinel_observations.json`, en el directorio temporal indicado. No contienen los tokens aleatorios de la instalación. Se conservaron las fuentes archivadas y resultados para inspección; la disponibilidad futura del directorio temporal no está garantizada.

No se revisaron G2, métricas de inferencia, publicación, PWA u otros hallazgos fuera de los siete solicitados.

## C-01 — FAIL: el token demo se rechaza, pero una secuencia débil permite privilegios

Versión: `48460b65317d995242a9d87320616401ed7f45a4`.

| Prueba | Resultado | Evidencia ejecutada | Bloqueo pendiente |
|---|---|---|---|
| ADMIN_TOKEN ausente, demo anterior o un carácter | PASS | Lifespan completo rechaza arranque; petición admin con la misma credencial débil devuelve 401. | Ninguno para esos valores concretos. |
| Un único carácter repetido 30 veces | PASS | Arranque rechazado y admin 401. | Ninguno para ese patrón. |
| Secuencia de diez dígitos ordenados, repetida tres veces | **FAIL** | Arranque permitido y GET admin/observability **200** contra PostgreSQL real. La credencial se identifica por patrón, no se imprime ningún secreto de instalación. | Longitud y ocho caracteres distintos no acreditan robustez; admite credenciales previsibles. |

Ubicación: `backend/app/config.py:76-89`, validación de startup en main.py. El valor demo público ya no es fallback válido: esa corrección está comprobada. Falta bloquear patrones conocidos/repetidos/secuenciales y exigir generación criptográficamente aleatoria por instalación, sin vía de configuración débil aceptada silenciosamente. No existe una prueba finita que garantice la entropía de cualquier cadena elegida por humanos; sí debe rechazarse este contraejemplo evidente.

## A-01 — FAIL: el reenvío público recupera la credencial de edición ajena

Versión: `48460b65317d995242a9d87320616401ed7f45a4`.

| Prueba | Resultado | Evidencia ejecutada | Bloqueo pendiente |
|---|---|---|---|
| PATCH status anónimo con human_approved=true | PASS | **401**; no cambió el estado. | El UUID por sí solo ya no basta para esta ruta. |
| Confirm sin credencial, credencial incorrecta o token de otro reporte | PASS | **403 / 403 / 403**. GET público no entrega citizen_edit_token. | Ninguno en acceso directo. |
| Decisión admin seguida de confirmación con token legítimo del autor | PASS | Cambio admin **200**; confirmación posterior del autor **409**, conserva RESOLVED. | Bloqueo posterior a gestión comprobado. |
| Segundo cliente anónimo reconstruye el POST a partir del GET y foto públicos | **FAIL** | PNG sintético permitido; foto descargada de photo_url pública. Reenvío sin Idempotency-Key: **201**, mismo UUID y credencial de edición reemitida. PATCH confirm del atacante: **200**, categoría final QUEMA persistida. | El respaldo idempotente por contenido público se convierte en recuperación de una capacidad secreta. |

Reproducción: crear un reporte PNG RGB sin metadatos, leer título/descripción/coordenadas y foto mediante endpoints públicos, reenviar esos datos desde otro TestClient sin cookies, token ni clave de operación, tomar la credencial del POST y confirmar el UUID original. Se ejecutó toda la secuencia, sin conocer la credencial del autor. No se afirma que todos los formatos/imágenes produzcan el mismo fingerprint; basta un formato admitido explotable.

Ubicación: `main.py:201-213,258-263`; `repository.py:134-158`. El replay devuelve `_citizen_edit_token`; la huella sin clave depende de contenido público. Además, `repository.py:79-82` deriva la credencial desde DATABASE_URL, que no debe reutilizarse como secreto de autorización.

Corrección mínima: capacidad aleatoria por reporte y recuperación vinculada a una credencial de operación impredecible del cliente/identidad autenticada; no reemitir capacidades a quien solo reproduce campos públicos. Preservar idempotencia sin convertirla en prueba de propiedad.

## M-07 — FAIL: la suite preserva centinelas anteriores, pero borra operaciones concurrentes

Versión: `48460b65317d995242a9d87320616401ed7f45a4`.

| Prueba | Resultado | Evidencia ejecutada | Bloqueo pendiente |
|---|---|---|---|
| Centinela no sintético y aprobación creados antes del snapshot | PASS | Ambos sobreviven a una prueba unitaria existente y su teardown. | Corrección del borrado incondicional anterior comprobada. |
| Centinelas insertados después del snapshot, durante una prueba real | **FAIL** | Hook pytest_runtest_call insertó reporte y aprobación ajenos al test. La prueba original terminó exit 0, pero el teardown borró **ambos**. | Snapshot de IDs no demuestra propiedad de las filas nuevas. |
| Cambio administrativo concurrente de DEMO0001 | **FAIL** | Durante la prueba se cambió a IN_REVIEW. Teardown lo devolvió a RESOLVED, el valor anterior al snapshot. | Sobrescribe decisión posterior y restaura una versión anterior. |
| BD configurada con nombre distinto de civia y sin sufijo desechable | **FAIL** | La prueba siguió usando `civia_prod_probe`; no la rechazó ni la aisló. Todo ocurrió en el clúster nuevo, no en producción real. | Conftest solo redirige el nombre literal civia; snapshot/restore no exige la guardia desechable. |

Ejecutado: `pytest backend/tests/test_ai_and_agent.py::test_secret_sanitization_never_leaks_keys -p g1_concurrent_plugin -q --tb=short`. El plugin solo inserta centinelas y simula una operación externa después de los fixtures; no modifica la prueba ni la limpieza del proyecto. El centinela se creó con otra conexión/transacción: representa datos concurrentes ajenos, no datos propios que el fixture debería limpiar.

Ubicación: `backend/tests/conftest.py:19-25,54-81`. DELETE WHERE NOT(id=ANY(snapshot)) elimina todo lo nuevo, no solo lo creado por el test. La restauración de estado/versión también pisa cambios legítimos. El except/pass ante fallo de aislamiento es otro recorrido abierto por lectura; no se provocó una conexión a la BD habitual para probarlo.

Corrección mínima: exigir entorno desechable antes de migrar/escribir, fallar cerrado si no puede aislar, nombre/almacenamiento único por ejecución, y eliminar solo IDs/run_id propios. Preferir transacciones revertidas o descartar una BD realmente exclusiva; no restaurar versiones de reportes compartidos.

## N-03 — FAIL: evaluación borra una aprobación concurrente ajena

Versión: `48460b65317d995242a9d87320616401ed7f45a4`.

| Prueba | Resultado | Evidencia ejecutada | Bloqueo pendiente |
|---|---|---|---|
| Aprobación preexistente cuyo motivo contiene atendido | PASS | Se conserva al finalizar la evaluación. Ya no la borra por coincidencia textual. | La corrección del predicado textual está verificada. |
| Aprobación ajena creada después del snapshot inicial | **FAIL** | En `eval_g1_independent`, se ejecutó una consulta de propuesta G1 con respaldo SQL local. Se insertó otra aprobación ajena antes de ejecutarla. Al terminar, la ajena fue eliminada. | Se sigue limpiando por complemento de una instantánea, sin IDs propios de la ejecución. |

Se ejecutó el evaluador real en modo all limitando su lista a Q13, que basta para recorrer propuesta/limpieza. Solo se envolvió la invocación del agente para insertar el centinela concurrente y forzar TOTAL sin API; PostgreSQL, snapshot y DELETE fueron reales. El scoring de esa consulta no forma parte del dictamen G1.

Ubicación: `eval/evaluar.py:350-351,459-466`. Incluso una BD llamada civia_eval es compartida entre ejecuciones si siempre se reutiliza ese nombre: otro evaluador/operador puede crear filas después del snapshot.

Corrección mínima: capturar y limpiar únicamente los IDs producidos por esa ejecución; base/esquema/almacenamiento único por run con guardia obligatoria. No usar DELETE de todo lo ausente en la instantánea.

## A-06 — FAIL de cierre: duplicados y trazas corregidos, fingerprint incompleto

Versión: `48460b65317d995242a9d87320616401ed7f45a4`.

| Prueba | Resultado | Evidencia ejecutada | Bloqueo pendiente |
|---|---|---|---|
| Dos POST idénticos con misma Idempotency-Key | PASS | **201/201**, mismo UUID; consulta SQL: **una fila**. | Duplicación secuencial corregida. |
| Dos POST concurrentes con misma clave | PASS | Barrera de dos hilos/clientes, conexiones reales: **201/201**, un UUID y **una fila**. | Duplicación concurrente no reproducida. |
| Misma clave, descripción diferente | PASS | **409**. | Comparación del contenido cubierto por la huella funciona. |
| record_ai_trace lanza después del commit | PASS | Dos reintentos **201/201**, mismo UUID y una fila nueva. Adaptador de modelo sintético; alta y almacenamiento reales. | No se reprodujo 500 por trazas. |
| Misma clave, comuna y dirección diferentes | **FAIL** | Se cambia comuna a Comuna 99 y dirección a otra referencia: **201**, devuelve el reporte anterior con comuna null, sin conflicto. | La huella omite campos persistidos; no vincula la clave a la solicitud completa. |

Ubicación: `main.py:205-208`, huella de título/descripción/coordenadas/foto/audio. No incluye comuna, neighborhood, address_hint ni auto_analyze. El test se ejecutó cambiando comuna y address_hint. Este último FAIL **no significa que se hayan creado duplicados ni que sigan fallando las trazas**: esos criterios críticos aprobaron. Impide cerrar íntegramente el contrato de idempotencia, porque un payload diferente aceptado silenciosamente se trata como la misma operación. La reemisión de credenciales en ese mecanismo es además el bypass de A-01.

Corrección mínima: huella canónica de todos los parámetros que definen la operación, evitando concatenaciones ambiguas y truncamiento silencioso de claves; 409 para cualquier reutilización con solicitud distinta. Mantener UNIQUE y bloqueo transaccional, cuya protección sí se comprobó.

## A-07 — FAIL: propuestas nuevas protegidas; pendientes heredadas sin versión siguen abiertas

Versión: `48460b65317d995242a9d87320616401ed7f45a4`.

| Prueba | Resultado | Evidencia ejecutada | Bloqueo pendiente |
|---|---|---|---|
| Propuesta G1, luego estado posterior RESOLVED | PASS | Decisión **REJECTED**, stale_conflict=true, reporte conserva RESOLVED. | Comprobación estado/versión de propuestas nuevas verificada. |
| Dos decisiones concurrentes sobre una propuesta | PASS | Dos conexiones/hilos: ambos retornan REJECTED en esa carrera, una sola decisión consistente. | No se reprodujo doble decisión. |
| Pendiente heredada con previous_status pero sin expected_version | **FAIL** | Se conservó el formato previo a G1 retirando solo expected_version de una propuesta en BD. Después: CONFIRMED→RESOLVED→CONFIRMED. Aprobar pendiente antigua: **APPROVED**, stale_conflict=false, reporte termina **IN_REVIEW**. | Si el estado vuelve a coincidir, no se detectan las decisiones intermedias porque la versión es opcional. |

La migración 002 no invalida ni completa de forma verificable las propuestas existentes. El formato probado corresponde al payload anterior a G1; no se inyectó una versión futura para eludir el control de una propuesta nueva.

Ubicación: `agent.py:1047-1061`: solo compara versión cuando expected_version no es None. Corrección mínima: rechazar/inutilizar pendientes heredadas sin versión y exigir siempre estado+versión; no inventar retrospectivamente que una propuesta vieja corresponde a la versión actual. Conservar bloqueo del reporte y decisión en la misma transacción.

## B-03 — FAIL: limpieza ante BD/audio corregida, pero escritura parcial deja huérfano

Versión: `48460b65317d995242a9d87320616401ed7f45a4`.

| Prueba | Resultado | Evidencia ejecutada | Bloqueo pendiente |
|---|---|---|---|
| Error de inserción PostgreSQL después de guardar foto | PASS | Trigger real rechaza INSERT según título sintético: **500** esperado y **cero archivos nuevos**. | Limpieza por fallo de BD comprobada, sin mock de create_report. |
| Foto válida, audio inválido | PASS | **415**, cero archivos nuevos. | Corrección comprobada. |
| Replay idempotente | PASS | Cero archivos adicionales al finalizar. | Elimina duplicados temporales del replay. |
| Escritura de foto interrumpida después de crear bytes | **FAIL** | Se escribieron 16 bytes reales y se inyectó OSError en Path.write_bytes. Petición **500**, permanece **un archivo huérfano** sin fila persistida. | La ruta solo se añade a written_files después de que el validador termine; si su escritura falla, no está registrada para limpieza. |

Ubicación: `main.py:218-219,254-257`; `security.py:167-170`. No se llenó el disco del usuario: se reprodujo la semántica de fallo parcial mediante escritura real seguida de error controlado, exclusivamente en almacenamiento desechable.

Corrección mínima: reservar/conocer la ruta antes de escribir, limpieza dentro del helper ante cualquier excepción y staging atómico con rename solo al terminar. Añadir negativa de I/O parcial, no solo excepción del repositorio. Los códigos de seguimiento ahora usan hash del UUID y año actual; no se repitió aquí una prueba exhaustiva de colisiones, ya que el archivo huérfano basta para impedir cerrar B-03.

## Bloqueos G1, ordenados

1. Impedir recuperar credenciales ajenas mediante replay público; mantener capacidad de edición vinculada a una operación secreta/identidad.
2. Rechazar tokens administrativos previsibles y exigir generación segura por instalación.
3. Sustituir limpiezas por complemento de snapshot y restauración de versiones por aislamiento real y propiedad por run_id/IDs; fallar cerrado para cualquier nombre de BD no desechable.
4. Rechazar propuestas heredadas sin versión; comprobar siempre la versión del reporte al decidir.
5. Completar fingerprint y pruebas de conflicto para campos omitidos; conservar la idempotencia transaccional y el aislamiento de trazas ya verificados.
6. Limpiar archivos parciales en el punto de escritura.

La aprobación de seis tests del proyecto no resuelve los contraejemplos reproducidos. Este dictamen se limita a G1 y no sustituye una nueva auditoría de los demás bloques.

## Cierre

Se detuvo el servidor PostgreSQL temporal al terminar; no se borraron los archivos de evidencia. El repositorio original conserva HEAD 48460b65317d995242a9d87320616401ed7f45a4 y solo tiene este informe nuevo. No se ejecutó push ni se modificó código de producción.

SHA256 de evidencia: head.zip `FD7F7D6161FABC91961C3A74E033EC8DB9B6892B024B3D190ABD437EE741DC2C`; observations.json `8F75C71334026B50221533EE1BC0E9C3F68DE2D71091653A8879326B2F4CD9B0`; sentinel_observations.json `A30B06729C037C6C960E1C938BD4B59B8A8AF18ADE6E70D7B75A2655DC0F955D`.
