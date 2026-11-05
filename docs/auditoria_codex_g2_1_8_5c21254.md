# CIVIA — Auditoría independiente de cierre G2.1.8 F1–F8

Fecha: 2026-11-04, America/Bogota. Commit exacto: `5c212542185dacf1223c3f96ef5a22c1ce8316c8`. Base: `187dea00e770191621f7fa4c481a41f2acbc1ab4`. Rama: `fix/auditoria-final`.

## Dictamen

**NO APROBADO. No cerrar G2.1.8 F1–F8.** F3, F5 y F7 pasan los controles ejecutados. F1, F2, F4 y F8 conservan fallos reproducidos; F6 está parcialmente corregido, pero aún permite reconciliación durable a un GET sin credencial en operaciones clasificadas como públicas.

La mejora del backend de recuperación es real: un cliente que conserva clave y capacidad originales recupera su ID, estado y resultado después de perder íntegramente la respuesta y reiniciar la API, sin duplicar negocio. La PWA auditada no conserva esas credenciales: al reintentar genera otras y ejecuta otro efecto. Esta diferencia impide aceptar F4 aunque sus pruebas unitarias estén verdes.

Las suites BLANK y SYNTHETIC dieron **122 PASS cada una**, incluido el proxy aislado. Las ocho pruebas nuevas dieron **8 PASS** por separado. Se inspeccionaron sus aserciones y los instrumentos anteriores: esos PASS no cubren las variantes adversariales que fallaron.

## Preparación y aislamiento

Se verificaron mediante comandos el HEAD exacto, la rama esperada y el árbol inicialmente limpio. `docker compose ps` mostró saludables los tres servicios habituales. Se leyeron AGENTS.md, el informe de `187dea0`, las ocho pruebas nuevas y el diff completo de los commits, conservado en `full.diff`.

El diff contiene 13 archivos, 1060 inserciones y 124 eliminaciones: cinco fuentes backend, tres frontend, prueba nueva, ajustes a dos expectativas históricas en una prueba existente y documentación. Las expectativas históricas que inferían ABORTED por PID ausente se sustituyeron por PENDING/UNKNOWN; esto concuerda con F6 y no se cuenta como evidencia independiente suficiente.

Raíz de evidencia preservada fuera del checkout:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-5c21254-248661f4d8804b998306933c4baa364b`

- `head.zip` generado con `git archive 5c21254`, extracción `src`, sin usar el árbol mutable como fuente auditada.
- PostgreSQL **17.11 real**, CPython **3.13.18**, psycopg **3.2.6**. Runner y API reutilizan exclusivamente el runtime de imagen local; imports desde `/audit/src` y `/audit/src/backend` congelados.
- Contenedores exclusivos `civia_audit_5c21254_pg`, `_runner`, `_api` y `_frontend`; bases nuevas `test_audit`, `test_api`, `test_suite_blank`, `test_suite_synthetic` y bases exclusivas creadas por instrumentos/suites.
- Red exclusiva interna `civia_audit_5c21254_net` para PostgreSQL, runner y API. Para acceso del navegador se añadió otra red exclusiva `civia_audit_5c21254_browser_net`, conectada solo al frontend, y puerto `127.0.0.1:55981`. No se usaron redes, volúmenes, bases ni servicios habituales.
- Frontend construido desde `src/frontend`, imagen `sha256:996f72b94a11fb1bab0039050da4b2f045a69a3e8edb1ee706ec6532a9ef3c95`. API/runner runtime `sha256:843e6979568902ee08ba2106fe4a8459042f95108eba22f10dde3365aeeab0d3`; PostgreSQL `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b`.
- Sin `.env`, datos reales o claves privadas. Claves IA vacías o marcadores sintéticos; adaptadores de turnos sustituidos y guardia hermética. Cero llamadas externas inesperadas reportadas por las suites. No se contactaron proveedores IA.
- PWA ejecutada con Edge headless, perfil de prueba separado, Playwright instalado fuera del repositorio y solicitudes externas al origen de auditoría bloqueadas. Service worker bloqueado en este escenario controlado: se prueba el bundle real con conectividad determinista, no un modo offline. Las herramientas de interfaz integradas fallaron al inicializar sus assets; se conserva el instrumento de navegador usado como alternativa.

## Matriz de aceptación

| Hallazgo | Estado | Resultado esperado / observado |
|---|---|---|
| F1 Replay legítimo y secretos | **FAIL** | Replay propietario ya funciona sin NameError y no reejecuta. Filtros solo superficiales: secretos anidados quedan en payload/fingerprint, resultados, trazas y respuesta; argumentos legítimos anidados se conservaron |
| F2 Privacidad en replay | **FAIL** | Resultado general, target y error ya se ocultan al no propietario. Pero se copia `approval_id` desde el resultado privado en COMMITTED y PENDING→COMMITTED, sin autorización |
| F3 Separación de privilegios | **PASS** | Token propio/admin acceden; X-Edit-Token ciudadano, token ajeno, inválido y anónimo no acceden a operación administrativa privada sobre el mismo reporte |
| F4 Recuperación real | **FAIL** | HTTP backend con credenciales originales recupera tras pérdida de respuesta, reinicio y concurrencia. PWA genera nuevas credenciales al reintentar, duplica el efecto sintético y pierde seguimiento al recargar |
| F5 UNKNOWN | **PASS** | Helper genérico rechaza UNKNOWN sin evidencia; ausencia conserva UNKNOWN; evidencia exacta propia resuelve por GET autorizado bajo concurrencia; terminales protegidos |
| F6 Reconciliación/autorización | **PARCIAL** | PID ausente y observación fallida conservan incertidumbre; GET privado anónimo no muta; ACK perdido se recupera. GET público anónimo aún cambia UNKNOWN→COMMITTED con evidencia propia |
| F7 Auditoría REST | **PASS** | Acción, estados, versiones y nota durables; rollback conjunto, concurrencia serializada y ningún registro de éxito para inexistente. Identidad `admin` compartida documentada, no exigida como identidad individual |
| F8 Procedencia causal | **FAIL** | Cache de primera observación corrige el caso básico. Con capability activa la misma excepción externa cambia de false a true al expirar; un cancel fallido marca procedencia propia; primera inspección tardía sigue deduciendo causa del tiempo |

## F1 — Corrección superficial de secretos

**Ubicaciones:** `backend/app/db.py:46-60`, `:180-198`; `backend/app/agent.py:775-793`, `:878`, `:1465`, `:1690-1702`. **Evidencia:** `closure.py`, `closure_results.json`; control original `adversarial.py`.

El caso original del propietario pasa: import hmac presente, token reconocido, resultado recuperado sin segundo worker y token de primer nivel ausente de proposed_payload. La ampliación solicitada a valores anidados falla:

```text
payload.data.operation_token = capacidad sintética
payload.list[0].admin_token = capacidad sintética
secret_in_proposed = true
secret_affects_fingerprint = true al cambiar solo la capacidad anidada
legitimate_preserved = true (description/quantity intactos)
```

Se ejecutó además una herramienta sintética que retorna argumentos para verificar las fronteras de persistencia: el resultado durable conserva la credencial (`secret_in_result=true`). Un turno controlado devuelve argumentos con una capacidad anidada; estos se registran en `ai_traces.tool_calls` antes del filtro público, reaparecen en la respuesta y en la conversación de la siguiente llamada al adaptador. Los cuatro indicadores del caso son true. No se enviaron esos datos a un proveedor real: se capturó el límite del adaptador simulado.

Se distingue esto del transporte nuevo correcto: la capacidad del cliente pasada **fuera de banda** no apareció en los mensajes del adaptador (`out_of_band_client_cap_in_provider=false`); también fue false en las ocho observaciones del control HTTP. No se afirma una filtración de esa cabecera en el flujo normal solo por existir el caso anidado.

**Impacto:** la garantía de separar credenciales del negocio no se sostiene para objetos/listas ni para las otras fronteras persistidas. Un secreto anidado también afecta el fingerprint e interfiere con replay equivalente. **Clasificación:** defecto previo parcialmente remediado; filtros nuevos incompletos.

**Corrección mínima verificable:** sanitizador recursivo común para dict/list, usado antes de fingerprint, persistencia, trazas, historial y respuesta; credenciales fuera de resultados de negocio. Conservar campos normales y probar estructuras anidadas sin modificar los argumentos legítimos que necesita una herramienta. No limitar la corrección a importar hmac o a quitar claves de primer nivel.

## F2 — Campo privado aún divulgado por replay

**Ubicaciones:** `backend/app/agent.py:812-813`, `:831-832`. **Evidencia:** matriz de doce combinaciones en `closure_results.json` y carrera en `targeted_tail_results.json`.

Se probaron COMMITTED, ABORTED, PENDING y UNKNOWN con propietario, capacidad ajena y anónimo. Ningún replay ejecutó worker. Resultado privado general, target y error interno están ocultos a terceros; PENDING/UNKNOWN solo devuelven capacidad al propietario. Esas correcciones pasan.

En cambio, un resultado de operación `ADMIN_REPLAY_MATRIX` contiene `approval_id=SYNTHETIC_PRIVATE_APPROVAL`. Al repetir sin capacidad o con capacidad ajena:

```text
COMMITTED: approval_exposed=true, result_exposed=false
PENDING que confirma durante el sondeo: approval_exposed=true
```

El código copia ese campo del resultado sin comprobar `is_owner`. No se exige ocultar el ID durable de operación que sirve para recuperación; se distingue del ID de aprobación extraído de un resultado privado. Tampoco se demostró que ese ID permita aprobar cambios sin el control administrativo existente.

**Impacto:** divulgación parcial de un resultado privado, pese al filtro general. **Clasificación:** problema nuevo de la corrección, añadido para conservar un campo en la respuesta resumida.

**Corrección mínima:** no copiar ningún campo de `result_payload` para un replay sin autorización, incluidos approval_id y el recorrido de sondeo. Mantener una confirmación mínima estable sin datos del resultado privado.

## F3 — Separación administrativa verificada

**Evidencia:** casos `private_auth` de `adversarial.log`/JSON y pruebas permanentes. Misma operación administrativa privada y mismo report_id: token propio y administrador reciben 200 con resultado; editor ciudadano, token ajeno, inválido y anónimo reciben 404 sin resultado ni metadatos privados.

La comprobación de `is_admin_or_private` antes de aceptar X-Edit-Token corrige el bypass de `187dea0`. PASS limitado al esquema de identidad/tipo/capacidad existente; no se inventa autenticación individual donde solo existe una credencial administrativa compartida.

## F4 — Backend recuperable, PWA no recuperable

**Ubicación:** `frontend/src/App.tsx:474-493`, especialmente generación local `:483-488`; estado de operación en memoria y botón de consulta `:1424`. **Evidencia:** `pwa.cjs`, `pwa_results.json`, `proxy_events.jsonl`, `http_business_snapshot.json`, capturas `pwa_lost_response.png` y `pwa_poll.png`; control `http_recovery.py`.

Se usa la PWA real compilada, Nginx real y FastAPI real. El adaptador IA es sintético y solicita una herramienta de auditoría que incrementa una fila PostgreSQL y confirma un marcador real antes de retener el resultado hasta que vence el supervisor. Es un efecto sintético observable, no una afirmación de duplicación de datos ciudadanos reales.

Un proxy de transporte entre Nginx y FastAPI lee íntegramente la respuesta upstream y la descarta cerrando la conexión. El navegador recibe 502 de Nginx, no el cuerpo exitoso, ID ni token de FastAPI. El instrumento no lee el cuerpo perdido para recuperar esos valores.

Secuencia observada en el navegador:

1. La PWA genera clave y capacidad antes del POST y el servidor confirma el primer efecto.
2. Primera respuesta descartada: HTTP 502, ningún ID de operación visible, localStorage y sessionStorage vacíos.
3. Se vuelve a pulsar «Consultar al Agente» con la misma consulta: **same_key=false y same_capability=false**.
4. El servidor ejecuta otro efecto bajo otra operación. Los hashes capturados de las dos peticiones corresponden a **dos IDs COMMITTED distintos**; la base pasó de 0 a 2 efectos por esas dos peticiones.
5. El botón nuevo permite consultar correctamente la segunda operación y muestra COMMITTED y el resultado autorizado.
6. Tras recargar la página: `operation_ui_restored=false`; ambos almacenes siguen vacíos.

La clave/capacidad originales solo existen como variables locales del intento. No hay reintento del mismo intento ni restauración tras recarga.

**Control positivo del backend:** otro cliente conserva clave/capacidad antes de la petición. Se descarta también toda su primera respuesta sin conocer el ID, se reinicia únicamente la API de auditoría y se lanzan dos reintentos concurrentes con las credenciales originales. Ambos recuperan el **mismo ID no vacío**, estado COMMITTED; GET propietario recupera resultado y no se duplica el efecto. El contador total final es 3: dos efectos de la PWA y uno de este control. Capacidad ajena no recupera resultado. Logs capturados después de las peticiones no contienen la capacidad comprobada ni el token ajeno.

**Impacto:** una interrupción de transporte o recarga puede dejar al usuario sin la primera operación y hacer que su «reintento» sea otra ejecución. La prueba permanente F4 sustituye `run_civia_agent` por un retorno prearmado y no verifica esta secuencia.

**Clasificación:** limitación previa de recuperación que persiste en la implementación nueva de PWA; transporte backend efectivamente corregido.

**Corrección mínima:** conservar un objeto de intento —clave, capacidad, consulta y estado— antes del envío; reusar exactamente ese objeto al reintentar y restaurarlo tras recarga. Crear credenciales nuevas solo para una nueva operación deliberada. Separar almacenamiento de capacidades de prompts/datos públicos y comprobar el mismo escenario de pérdida de respuesta con un único efecto final.

## F5 — UNKNOWN y terminales verificados

**Evidencia:** `closure_results.json`, `migration_unknown.log` y controles originales. Sin evidencia, helper genérico rechaza UNKNOWN y la reconciliación lo conserva. Se prepara evidencia durable ligada al mismo operation_id sin convertir un terminal a UNKNOWN: ocho GET autorizados concurrentes retornan COMMITTED. El GET ya considera UNKNOWN.

La evidencia de otra operación no confirma la examinada. Seis transiciones SQL desde COMMITTED/ABORTED a otros estados siguen bloqueadas por el trigger 006; cambios de metadatos y replays legítimos no se bloquean. El intento histórico de fabricar UNKNOWN a partir de COMMITTED se rechaza correctamente y no se interpreta como fallo del producto.

## F6 — Conservación de incertidumbre y límite pendiente de autorización

**Ubicación residual:** `backend/app/main.py:670-673` permite reconciliar consultas «autorizadas o públicas». **Evidencia:** `closure_results.json`, `targeted_tail_results.json`, `public_reconcile_results.json`, ACK/reinicio originales.

PASS comprobados: PID inexistente no produce aborto; UNKNOWN sin evidencia permanece UNKNOWN; ocultar temporalmente la tabla de evidencia únicamente en la base exclusiva produce fallo de observación y conserva PENDING durable. GET privado anónimo devuelve 404 y conserva PENDING sin mutación.

Queda esta excepción al requisito «un GET no autorizado no puede producir mutaciones durables»: una operación ciudadana clasificada como pública está UNKNOWN y tiene evidencia durable propia. GET **sin cabeceras** responde 200 y cambia el registro de UNKNOWN a COMMITTED. No expone el resultado privado. La transición coincide con la evidencia y no se afirma que haya corrupción de negocio; el incumplimiento es permitir el efecto de reconciliación sin autorización.

**Impacto:** un tercero puede provocar una transición durable aunque no posea capacidad. **Clasificación:** comportamiento preexistente conservado explícitamente para consultas públicas, no una nueva falsa inferencia de aborto.

**Corrección mínima:** si se mantiene el contrato solicitado, devolver a consultas públicas el estado ya almacenado sin reconciliar; reservar transiciones a consultas autorizadas o a reconciliación interna. No exigir ocultar todo metadato público para corregir esto.

La pérdida real de ACK conserva negocio=1, COMMITTED durable y recuperación correcta; terminar el escritor durante COMMIT/PgSleep y leer desde proceso nuevo también conserva 200/COMMITTED. No se exige rollback inmediato ni terminar hilos en vuelo.

## F7 — Auditoría REST verificada

**Evidencia:** `adversarial_results.json`, `boundaries.log`, prueba nueva F7. El registro contiene acción, estado anterior/nuevo, versiones previa/final y nota. Dos PATCH concurrentes producen la cadena correcta CONFIRMED/v1→IN_REVIEW/v2→RESOLVED/v3, con un registro por confirmación, bajo FOR UPDATE.

Rechazo real del INSERT conserva estado y versión previos; ledger ausente produce 500 y rollback conjunto; reporte inexistente responde 404 sin falso registro. Anónimo/token inválido reciben 401 y falta de aprobación explícita 400. La identidad registrada es `admin`, consistente con una credencial compartida: la imposibilidad de identificar a una persona concreta se documenta y **no bloquea F7**.

## F8 — Cache temporal insuficiente y marca anterior a cancelación fallida

**Ubicaciones:** `backend/app/db.py:127-155`, `:748`, `:1074-1077`. **Evidencia:** `closure_results.json`, `adversarial.log`, `error_provenance.log`.

El contraejemplo básico anterior está corregido cuando no existe capability activa y la primera clasificación ocurre antes del deadline: el mismo 57014/25P04 externo permanece false tras retener la excepción. También se preservan 57P01 y 42P01 reales.

Las variantes requeridas para atribuir causalidad todavía fallan:

```text
Timer externo 20ms; capability con plazo futuro:
57014: primera clasificación=false; expira capability; segunda=true
25P04: primera clasificación=false; expira capability; segunda=true
En ambos: own_cancellation_marked=false

cancel() falla con error de transporte inyectado:
cancel_success_count=0
Luego statement_timeout externo real 20ms:
own_marker_on_exception=true; classified_local=true; deadline aún futuro

57014 externo recibido antes del plazo, primera inspección retenida hasta después:
classified_local=true; own_marker=false
```

En el segundo caso solo se sustituye el envío de cancelación por un fallo controlado; la conexión, SET de timer y pg_sleep son reales. El código marca la conexión **antes** de llamar a `cancel()`. Por eso la marca que luego se copia a la excepción no acredita una cancelación propia efectiva.

**Impacto:** siguen normalizándose errores ajenos como timeout de CIVIA; la clasificación de una misma excepción no es estable si cambia el estado de la capability. **Clasificación:** remediación parcial del defecto previo; la marca previa al envío fallido es un problema de la nueva corrección.

**Corrección mínima:** registrar hechos del intento/resultado de cancelación y vincularlos a la operación; no convertir revocación, expiración o primera observación tardía en prueba de causa. No marcar una cancelación efectiva antes de que el envío se complete. Añadir variantes con capability activa y fallo de transporte, además del caso sin capability que hoy pasa.

## Regresiones, exclusiones y validez de los instrumentos

| Ejecución | Resultado |
|---|---|
| Suite completa BLANK, `pytest -m "not live" -q -rs` | **122 passed, 1 deselected**, 20,18 s |
| Suite completa SYNTHETIC, mismo comando | **122 passed, 1 deselected**, 23,75 s |
| `test_audit_g2_1_8_remediation.py` por separado | **8 passed**, 2,02 s |
| Identificación separada live opcional + frontend E2E | **1 passed, 1 skipped**, 0,37 s |
| `python -m compileall -q app tests` | Código 0 |

Una advertencia de deprecación AnyIO. Las suites incluyen G1, G2, A-02, M-02, M-03 COPY, M-06, N-02 y E2E frontend/proxy. El navegador añade la prueba funcional real de seguimiento, separada del E2E de assets/proxy. No se modificaron tests del producto para obtener estos resultados.

**Las dos pruebas susceptibles de omisión quedan identificadas:**

1. `tests/test_ai_and_agent.py::test_optional_live_provider_multimodal_connectivity`, decorada con live/skipif en líneas 457–462. Se excluyó en ambas suites para cumplir la prohibición de proveedores externos. Ejecutada aisladamente con claves vacías, se omite con razón explícita «Prueba opcional con proveedor real separada de la suite ordinaria».
2. `tests/test_e2e_frontend_proxy.py::test_frontend_pwa_and_nginx_reverse_proxy_e2e`, línea 15 omite si frontend no está accesible. **No se omitió aquí:** el frontend aislado existe y la prueba pasa.

No se reproducen las «121 passed, 2 skipped» de la documentación de AG. Aquí el segundo caso se ejecuta, por eso son 122 PASS y una live excluida, sin skips en las suites filtradas. No se inventa una segunda exclusión ni se cuentan omitidas como aprobadas.

Se conservaron **byte por byte** los seis instrumentos originales y `adversarial.py` de la auditoría anterior; hashes comparados antes de cerrar. No cambiaron sus expectativas de seguridad. `independent.py` y `adversarial.py` capturan errores internos y pueden terminar en 0 aunque una preparación quede bloqueada por un rechazo correcto de UNKNOWN/terminal. `followup.py` termina en 1 al rechazar ABORTED→COMMITTED, ahora correctamente. Su cola se ejecutó con `followup_remaining.py` ya existente. Nuevos instrumentos complementan los casos que dejaron de ejecutarse, sin cambiar fuentes/tests de producto.

El caso de upgrade del instrumento histórico conserva su error de parametrización de texto SQL con `%`; no se usa como defecto del producto. Los instrumentos complementarios de upgrade lo resuelven sin alterar el original. No se repitió la investigación histórica G2.1.1–G2.1.8; se reutilizaron los contraejemplos solicitados y las regresiones de suite.

Para el navegador hubo dos ajustes de infraestructura documentados: las herramientas UI integradas no pudieron inicializar assets, y Docker no expuso el puerto de un contenedor conectado solo a red interna. Se usó navegador headless con perfil separado y una segunda red exclusiva solo para frontend. No se alteraron las redes habituales ni se relajaron las expectativas de recuperación.

No se encontró comando/configuración lint Python del proyecto; compileall no equivale a lint. El diff del commit ya contiene espacios finales en la prueba nueva, observación de formato no bloqueante que no se corrigió. `git diff --check` del trabajo documental se verifica al cerrar.

## Evidencia y reproducción

En la raíz aislada: snapshot, diff, scripts originales y complementarios, logs/JSON, capturas del navegador y logs de build. `closure.py` produce F1/F2/F5/F6/F8; `targeted_tail.py` cubre observación fallida y el sondeo que confirma; `public_reconcile_and_snapshot.py` comprueba F6 público y relaciona hashes de peticiones con operaciones/contador. `serve.py` contiene el adaptador sintético y proxy de pérdida de respuesta; no es código del producto.

Repetir desde bases nuevas: crear red/PG exclusivos, esperar readiness, montar esta raíz como `/audit`, configurar PYTHONPATH con las dos raíces congeladas y DATABASE_URL solo al clúster propio. Contraseña del clúster eliminado: `audit_synthetic_only`, exclusivamente sintética. Nunca cargar `.env` habitual. Aplicar migraciones y seed sintético antes de instrumentos. Estos crean tablas/triggers y no son idempotentes.

Orden usado: instrumentos originales `independent`, `followup`, `followup_remaining`, `boundaries`, `error_provenance`, `adversarial`, ACK/reinicio, complementos UNKNOWN/upgrade; suites en bases propias; `closure.py`; PWA con `pwa.cjs`; control `http_recovery.py`; sondeos finales. La API aislada usa `test_api`, el runner `test_audit`, las suites bases distintas.

`pwa.cjs` lanza Edge headless, interactúa con los controles reales y no modifica el frontend; solo conserva hashes de capacidades/claves. `http_recovery.py` espera archivos de coordinación para reiniciar la API propia y capturar logs mientras mantiene credenciales en memoria. `serve.py` descarta solo la respuesta señalada por `drop_next_response`; guarda hechos de transporte y hashes, nunca el cuerpo perdido ni credenciales. No hay datos reales ni dumps privados. No se afirma hermeticidad de otros recorridos de logs no ejecutados.

| Evidencia | SHA-256 |
|---|---|
| head.zip | `36E90E64F49FF99004E503737C89ED7C03ACFE936FF606D26454F10C2323E60C` |
| closure_results.json | `729A6A1EC8207DF72710D713F2E7385F8535434D61965CBB6E817C925AE30D1C` |
| pwa_results.json | `CFED7012B28082BD4A33C01F233B1F92A2002D7990514DAB2D4CFB9DFF0C611C` |
| http_recovery_results.json | `D3D750A66BC49C8E3C069549BC5C1ECC778AE8D97DD5DEAA46B58FA570114DD2` |
| suite_blank.log | `4A2911542EABE1BC557DC210361262113B797A78A082FDBF0E8463885E2CDDF8` |
| suite_synthetic.log | `7D1DA136161CF3BC23E9A0003CF56007769E13E031336E644955E8A979125AE5` |

## Cierre

No se corrigió producto ni se cambiaron pruebas existentes. Sin Autopilot, commits, push, merge ni cambio de rama. Únicos cambios del checkout: este informe y anotación de `docs/estado.md`.

Se retiran exclusivamente recursos creados por el auditor, comprobando sus IDs; se conservan instrumentos, logs, resultados y capturas en la raíz indicada. La disponibilidad final de los tres servicios habituales y la limpieza exclusiva se registran en `docs/estado.md`. La auditoría se detiene al entregar este dictamen.
