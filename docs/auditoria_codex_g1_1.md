# CIVIA — reauditoría independiente de G1.1

Fecha: 2026-11-01, America/Bogota. Referencia: `docs/auditoria_codex_g1.md`.

**HEAD auditado:** `74ecc025e01bd5ccff36cb28d8a1c182a9c6ea82`, rama `fix/auditoria-final`.
**Base de comparación:** `48460b65317d995242a9d87320616401ed7f45a4`.

## Dictamen limitado a G1.1

**6 hallazgos PASS y 1 FAIL. C-01 permanece abierto por corrección parcial.** Los siete contraejemplos concretos del informe anterior fueron bloqueados en esta ejecución, pero una variación de credencial administrativa previsible sigue permitiendo arranque y privilegios. No se considera resuelto ese control por rechazar únicamente el patrón numérico antes demostrado.

Este dictamen no evalúa otros bloques, disponibilidad real de modelos, métricas, PWA, publicación ni seguridad integral de CIVIA. No se modificaron fuentes de producción, ramas, commits ni resultados versionados. Solo se añade este informe.

## Versión, comparación y aislamiento

`git status --short` inicial: limpio. HEAD y rama corresponden a los anteriores. `git diff 48460b6 HEAD` mostró 20 archivos modificados, 1728 inserciones y 506 eliminaciones; se inspeccionaron las modificaciones relevantes, sin confiar en las conclusiones de remediacion_g1_1.md.

Se congeló HEAD con `git archive HEAD` y se ejecutó su copia bajo:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-g11-f9688e654f4d4863a30d43051f27bba1`.

Clúster **PostgreSQL 17.6 real**, nuevo, escuchando solo en `127.0.0.1:55477`. Bases nuevas: `test_g11_independent`, `test_g11_suite`, `test_g11_sentinels`, `eval_g11_independent`, `test_g11_migration` y `civia_prod_probe`; pytest creó además una base aislada de nombre aleatorio. `civia_prod_probe` también pertenece a este clúster desechable: su nombre sirve para comprobar el tratamiento de una configuración no identificada como test, sin conectarse a producción.

PGDATA, uploads, directorios temporales y TEMP/TMP quedaron dentro de esa raíz. No se usaron la BD ni el volumen habitual. No se copió `.env`. Se reutilizaron los binarios PostgreSQL y el entorno CPython 3.13.18 de la auditoría anterior, con dependencias directas de backend/requirements.txt, que no cambió entre los dos commits. El código importado provino exclusivamente del nuevo archivo de HEAD.

Claves de proveedores vacías. Se inyectaron modelos sintéticos y excepciones controladas para los fallos; SQL, restricciones, bloqueos, commits, archivos y migraciones fueron reales. Docker no está disponible: se probó almacenamiento desechable en directorios, **no se afirma haber probado volúmenes Docker**.

## Matriz de cierre

Todas las filas corresponden exactamente a `74ecc025e01bd5ccff36cb28d8a1c182a9c6ea82`.

| Hallazgo | Resultado | Contraejemplo anterior y evidencia independiente actual | Pendiente |
|---|---|---|---|
| C-01 | **FAIL — parcial** | El patrón numérico repetido ahora rechaza arranque y devuelve admin 401. Pero una credencial demo construida con nombre público del proyecto, rol, año y palabra Demo permite arranque y admin **200**. | No cerrar robustez: sigue aceptando una credencial previsible de demostración. |
| A-01 | **PASS** | Replay anónimo con datos y foto públicos: 201 pero **otro UUID**, otra capacidad; PATCH al original **403**, categoría intacta. Status anónimo 401, confirm sin token/incorrecto/ajeno 403; después de gestión admin, token del autor 409. | Ninguno de los contraejemplos solicitados sigue explotable en los casos ejecutados. |
| M-07 | **PASS** | Pytest real con escritor externo en otro proceso: sobreviven reporte y aprobación concurrentes; conserva IN_REVIEW y versión 2. La BD fuente y sus centinelas no cambian; pytest se redirige a BD aleatoria. Modo estricto rechaza la fuente con exit 4. | No se certifican todos los fallos de infraestructura posibles; sí el recorrido de protección y los centinelas requeridos. |
| N-03 | **PASS** | Evaluador real con escritor externo: conserva aprobación preexistente, reporte/aprobación concurrentes y estado administrativo; elimina solo la propuesta propia identificada por UUID. | Ninguno para el borrado por snapshot/texto que motivó el hallazgo. |
| A-06 | **PASS** | Misma clave, secuencial/concurrente: 201/201, un UUID y una fila. Cambiar descripción o comuna/dirección: 409. Fallo de trazas tras commit: 201/201, mismo UUID y una fila nueva. | Sin clave ya no hay deduplicación por contenido; es el cambio necesario para no recuperar credenciales desde datos públicos, no un fallo del contrato con clave probado. |
| A-07 | **PASS** | Propuesta nueva obsoleta rechazada; heredada sin versión después del ciclo CONFIRMED→RESOLVED→CONFIRMED también REJECTED y no modifica CONFIRMED. Migración 003 invalida una pendiente realmente creada antes de aplicarla. Carrera de decisiones consistente. | Ninguno para los casos nuevos/heredados ejecutados. |
| B-03 | **PASS** | Escritura parcial real de 16 bytes más OSError: HTTP 500 esperado, **cero huérfanos**, incluidos staging. Fallo SQL y audio inválido: cero archivos nuevos; replay: cero adicionales. Escritura corta sin excepción y error de rename, en foto/audio: cero restos. | No se simularon pérdida eléctrica o imposibilidad permanente de borrar; PASS limitado a los fallos reproducidos. |

## 1. C-01 — permanece abierto

### Pruebas ejecutadas

| Credencial sintética | Arranque completo | Acceso administrativo con cabecera coincidente |
|---|---|---|
| Ausente/vacía | Rechazado | 401 |
| Valor demo anterior | Rechazado | 401 |
| Un carácter | Rechazado | 401 |
| Un carácter repetido 30 veces | Rechazado | 401 |
| Diez dígitos ordenados repetidos tres veces, contraejemplo anterior | Rechazado | 401 |
| Patrón contextual público de demostración, descrito abajo | **Permitido** | **200** |

Para el último caso se ensambló exclusivamente información pública: nombre del proyecto con capitalización inicial + separador + etiqueta de rol administrativo + separador + año 2026 + separador + etiqueta Demo y puntuación final. No tiene componente aleatorio. Se instaló solo temporalmente en settings mediante patch; el lifespan completo y el endpoint real de observabilidad lo aceptaron. PostgreSQL estuvo disponible durante la prueba. Los valores de los secretos aleatorios de auditoría no se imprimieron ni se incluyeron en el informe.

Reproductor mínimo, únicamente en la copia desechable configurada para auditoría:

```python
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app

pattern = '_'.join(('Civia', 'AdminToken', '2026', 'Demo')) + '!'
with patch.object(settings, 'ADMIN_TOKEN', pattern):
    with TestClient(app) as client:
        result = client.get('/api/admin/observability', headers={
            'X-Admin-Token': pattern
        })
        assert result.status_code == 200  # Resultado observado; control inseguro.
```

Es una entrada sintética conocida y previsible, no una credencial extraída de una instalación. Su aceptación no permite por sí sola que un atacante cambie la configuración de un servidor ajeno; demuestra que el backend todavía deja arrancar con privilegios una instalación configurada con un secreto débil, precisamente la condición exigida para C-01.

**Comparación:** config.py añadió detección de secuencias, repeticiones, clases de caracteres y generación CSPRNG. Esto cierra el contraejemplo numérico. No obstante, las comprobaciones de `backend/app/config.py:139-178` y la lista de subcadenas de `:76-89` aceptan el patrón contextual. `generate_admin_token` existe, pero la configuración externa puede evitarlo proporcionando ese valor aceptado. El generador no prueba que todos los valores suministrados hayan sido generados con él.

**Corrección mínima pendiente:** hacer de la generación segura por instalación el camino exigido y verificable, evitar credenciales demo/contextuales y añadir este negativo. Ningún conjunto finito de reglas de cadenas demuestra entropía criptográfica; tampoco debe describirse un PASS de esas reglas como garantía universal de impredecibilidad. Hasta resolver el caso ejecutado, C-01 sigue FAIL.

## 2. A-01 — replay público y autorización

Se reutilizó el mismo PNG RGB sintético sin metadatos que hacía explotable 48460b6. Primer cliente creó reporte sin Idempotency-Key. Un segundo cliente, sin token, cookies ni conocimiento de la capacidad original, descargó el GET público y photo_url y reconstruyó título, descripción y coordenadas. El segundo POST devolvió 201, pero su UUID ya no fue el del reporte original y su capacidad no coincidió con la del autor. Usando esa capacidad contra el UUID original, confirm devolvió **403**; final_category permaneció null.

También se repitieron: PATCH status anónimo con human_approved=true **401**; confirm sin capacidad **403**; capacidad incorrecta **403**; capacidad válida de otro reporte **403**. Después de cambiar status a RESOLVED mediante la ruta administrativa autorizada, la capacidad válida del autor recibió **409** y se conservó RESOLVED.

**Comparación:** `main.py:206-234` eliminó la clave implícita derivada de contenido público. `repository.py:86-89` genera capacidad aleatoria y deja de derivarla de DATABASE_URL. El replay con clave explícita recupera la capacidad vinculada a esa clave, en vez de permitir recuperación por mera reproducción de campos públicos. Las lecturas públicas continúan sin entregar el token.

Se considera cerrado el contraejemplo de A-01. No se certifica aquí el diseño criptográfico completo de almacenamiento de capacidades frente a un compromiso de BD, que no era el ataque solicitado.

## 3. M-07 — prueba real y datos de otro proceso

No bastó con llamar al nuevo helper de limpieza desde una prueba fabricada. Se ejecutó una prueba unitaria existente:

`python -m pytest backend/tests/test_ai_and_agent.py::test_secret_sanitization_never_leaks_keys -p g11_external_plugin -q --tb=short`

La configuración de entrada apuntaba a `civia_prod_probe`, base ficticia del clúster de auditoría. Conftest la sustituyó por una nueva `civia_test_<id>`. Antes de la ejecución se habían dejado centinelas y un estado RESOLVED en la fuente: permanecieron intactos.

Un hook pytest_runtest_call arrancó **otro proceso Python**, con conexiones PostgreSQL propias, después de los fixtures. Ese proceso creó un reporte no sintético, su aprobación pendiente y cambió DEMO0001 a IN_REVIEW, incrementando versión. No importó tests.conftest y no registró sus IDs como propios del test. Esto evita atribuir artificialmente datos externos a los hooks de seguimiento del proceso de pruebas.

Resultado: pytest exit **0**; reporte y aprobación externos sobreviven; DEMO0001 conserva **IN_REVIEW, versión 2**. El teardown ya no restaura el estado/versiones previos ni usa DELETE por complemento de snapshot. En una ejecución adicional con `CIVIA_STRICT_REJECT_NON_TEST_DB=1`, la misma fuente no desechable se rechazó con exit **4**, antes de ejecutar la prueba.

**Comparación:** `backend/tests/conftest.py:28-37` exige aislamiento/guardia; `:60-86` limpia IDs registrados propios. El control pasó los contraejemplos de borrado y sobrescritura concurrente del informe G1.

## 4. N-03 — limpieza del evaluador

Se ejecutó `run_evaluation(mode='all', pause_sec=0)` sobre `eval_g11_independent`, conservando el código real del evaluador y su DELETE. Como en la auditoría anterior, su lista se limitó a Q13, suficiente para recorrer creación y limpieza de aprobaciones. Un wrapper lanzó un escritor externo en otro proceso antes de la consulta, y forzó TOTAL para responder por SQL sin APIs. No se sustituyeron persistencia, lectura de trazas ni limpieza.

Resultados verificados por SQL al terminar:

- Aprobación preexistente cuyo motivo contiene atendido: **presente**.
- Reporte y aprobación concurrentes ajenos: **presentes**.
- Cambio administrativo externo a IN_REVIEW: **conservado**.
- Aprobación propia retornada por el agente al evaluador: **eliminada**.

**Comparación:** `eval/evaluar.py:363,382-398,487-493` mantiene IDs propios y borra únicamente esos UUID. Ya no deduce propiedad a partir de una instantánea ni del texto del motivo.

La consulta obtuvo 0/1 en su scoring de contenido, pero ese marcador no es resultado de esta prueba de seguridad: se validó la retención/limpieza de datos, no Q13 ni métricas de inferencia. No se declara haber ejecutado una evaluación live de 15 consultas.

## 5. A-06 — idempotencia, conflictos y trazas

### Persistencia real

| Escenario | HTTP | SQL/resultado |
|---|---|---|
| Misma clave y solicitud, secuencial | 201 / 201 | Mismo UUID; una fila |
| Misma clave y solicitud, dos hilos/clientes con barrera | 201 / 201 | Un UUID; una fila |
| Misma clave, descripción distinta | 409 | No se crea otra fila |
| Misma clave, comuna y dirección distintas, contraejemplo G1 | **409** | Se conserva la fila original, sin aceptar silenciosamente los nuevos datos |
| Excepción de record_ai_trace después del commit, dos reintentos | 201 / 201 | Mismo UUID; una sola fila nueva |

Solo se simularon el resultado de modelo y el fallo de traza. Las altas/commits y el conteo fueron reales. Se repitió la carrera mediante dos conexiones de solicitudes independientes, sin mock del repositorio.

**Comparación:** `main.py:206-223` usa JSON canónico con campos opcionales, auto_analyze y hashes de archivos, frente a la concatenación incompleta de 48460b6. Conserva la protección transaccional de clave y el aislamiento de fallos de observabilidad. El contraejemplo de comuna/dirección y los dos criterios principales de duplicación/trazas pasan.

La ausencia de clave explícita ahora permite dos altas separadas con contenido igual. No se presenta como fallo de idempotencia con clave: es un contrato distinto que impide convertir contenido público en recuperación de la capacidad del reporte original.

## 6. A-07 — propuestas obsoletas nuevas y heredadas

Se repitió la secuencia exacta del informe G1: crear propuesta, retirar únicamente expected_version para reproducir payload persistido anterior a G1, cambiar CONFIRMED→RESOLVED→CONFIRMED y aprobar. Ahora retorna **REJECTED**, stale_conflict=true y el reporte conserva **CONFIRMED**.

La propuesta nueva creada antes de un cambio a RESOLVED también fue REJECTED y conservó RESOLVED. Dos decisiones concurrentes sobre otra propuesta retornaron una decisión consistente; en esta carrera ambos retornaron REJECTED.

Se hizo además una prueba de actualización real de esquema:

1. Base nueva `test_g11_migration`, aplicando únicamente 001 y 002 desde una carpeta temporal de migraciones.
2. Insertar pendiente heredada sin expected_version y conservar estado del reporte.
3. Aplicar las migraciones del HEAD completo, incluida 003.
4. Consultar: pendiente **REJECTED**, estado del reporte **sin cambios**.

**Comparación:** `agent.py:1059-1080` exige versión entera positiva y estado válido antes de aprobar; el UPDATE también compara estado/versión. `003_invalidate_legacy_approvals.sql` invalida pendientes anteriores incompletas, sin inventar versión retrospectiva. Se considera cerrado el bypass heredado probado.

## 7. B-03 — archivos parciales y limpieza

Se repitió la excepción de inserción con **trigger PostgreSQL real** que rechaza el título sintético seleccionado: HTTP 500 esperado y cero archivos nuevos. Foto válida con audio inválido: 415 y cero archivos nuevos. Replay idempotente: cero adicionales.

Para el fallo parcial se instrumentó el punto real de escritura, ahora la ruta de staging: se escribieron 16 bytes reales y se lanzó OSError. No se dejó la condición antigua ligada solo al nombre final, pues eso habría omitido la inyección y producido un falso PASS. Resultado: **HTTP 500 esperado y cero archivos nuevos**, comprobando también archivos `.tmp_...`.

Se añadieron negativos acotados al mismo control:

- Escritura corta que retorna sin excepción: se detectó el tamaño incorrecto, cero restos.
- Fallo de os.replace/rename: cero restos.
- Ambos casos sobre helper de foto y de audio: cero restos en los cuatro recorridos.

**Comparación:** `security.py:104-132` escribe en staging, verifica tamaño, promueve mediante replace y limpia ante excepción. Foto y audio usan ese helper (`:196,275`). Estos controles corrigen los archivos huérfanos ante los fallos ejecutados; no se hizo una prueba de pérdida eléctrica, permisos irrecuperables o corrupción de disco.

## Suite del proyecto y comprobaciones independientes

La suite modificada por Antigravity se ejecutó sin editarla en `test_g11_suite`:

`python -m pytest backend/tests/test_audit_g1_security.py -q --tb=short`

Resultado: **13 passed**, 6,48 s, un warning de deprecación AnyIO. No es la única evidencia del informe: los reproductores independientes reutilizaron los ataques de G1 y comprobaron BD/archivos directamente; el caso contextual de C-01 no está cubierto por esos 13 tests aprobados.

Evidencia temporal independiente:

- `probe_g11.py`, adaptado del reproductor anterior solo para nuevas rutas, hash de clave y punto de escritura staging; `observations.json` recoge sus resultados.
- `probe_sentinels_g11.py`, `external_writer.py` y `g11_external_plugin.py`; `sentinel_observations.json` y salidas pytest.
- `extra_g11.py`; `extra_observations.json` para C-01 contextual, migración y fallos de tamaño/rename.

Los scripts no imprimen tokens aleatorios ni claves API. No se ejecutaron lint/build frontend o suites ajenas a G1.1 porque no aportan evidencia para los siete controles solicitados. Los resultados de esta revisión se documentan aquí sin modificar docs/estado.md ni marcar otras fases como terminadas.

## Pendiente y criterio de aceptación

Cerrar C-01 requiere demostrar que la instalación no puede arrancar con el patrón contextual previsible ejecutado, manteniendo la aceptación de secretos generados de forma segura. Después, repetir ese negativo y comprobar el arranque/admin con un secreto CSPRNG nuevo, sin imprimirlo. No se recomienda aceptar G1.1 íntegramente mientras este control siga parcial.

Los seis PASS son cierre de los contraejemplos y condiciones enumerados, no una certificación de ausencia de cualquier vulnerabilidad futura. Se preserva el alcance exclusivo G1.1.

## Cierre y huellas de evidencia

Se detuvo correctamente el servidor PostgreSQL temporal al finalizar, sin borrar evidencia ni tocar otros servidores o volúmenes. HEAD original permaneció en 74ecc025e01bd5ccff36cb28d8a1c182a9c6ea82; git status solo muestra este informe nuevo. La matriz contiene siete hallazgos y se comprobó la sintaxis del reproductor incluido y ausencia de espacios finales.

SHA256:

- head.zip: `262D618DF430B808F376379372770BFDE683413F0281C33EB9459A51A314BFE4`.
- observations.json: `43694D4ED44910E1E9B545F1EEB13B11EAC58946E617C42CBE65AF27206D76B8`.
- sentinel_observations.json: `64B800762EAF066DC596A40CA1120695C26E2F6832C5216A6259FB6DDA2BDFFB`.
- extra_observations.json: `2D2CC735ABC11A502FC95BB7ED3131D195449B2A3CFCC935DF573F39088DA68A`.
