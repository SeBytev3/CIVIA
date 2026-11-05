# CIVIA — Auditoría independiente definitiva G2.1.8

Fecha: 2026-11-05, America/Bogota. Commit exacto: `c345ba252e01272ae5c7fce9614d27d63a345f36`. Rama: `fix/auditoria-final`. Comparaciones: `6734fe6→c345ba2` y conjunto de correcciones `5c21254→c345ba2`.

## Dictamen

**G2.1.8 NO APROBADA.** Se reproducen dos bloqueos dentro del alcance solicitado:

1. **F1:** la capacidad del cliente llega al JSON de la segunda petición del adaptador real de Gemini por el historial `raw_gemini_part`, aunque los payloads durables y la respuesta pública estén sanitizados.
2. **F8:** `checked_commit` transforma cancelaciones externas reales 57014/25P04 en TimeoutError y marca procedencia local cuando todavía quedan más de 1,9 segundos del plazo de CIVIA.

F2, F3, F4, F5, F6 y F7 pasan los controles ejecutados. La recuperación PWA antes fallida funciona ahora, incluidas pérdida íntegra de respuesta, recarga y reutilización de credenciales. No se agregan requisitos ajenos a F1–F8 ni se presentan mejoras opcionales como bloqueos.

Las suites completas pasan **132 pruebas por modo**, sin que ello invalide los dos contraejemplos independientes. No se corrigió código durante la auditoría.

## Preparación y aislamiento

Se ejecutaron `git rev-parse HEAD`, `git branch --show-current` y `git status --short`: HEAD exacto solicitado, rama esperada y árbol inicialmente limpio. Se leyeron AGENTS.md, el informe independiente anterior, las pruebas modificadas y los dos diffs completos, conservados en `diff_recent.patch` y `diff_f1_f8.patch`.

El diff reciente modifica agent.py, db.py, pruebas adversariales y estado: 4 archivos, 279 inserciones y 69 eliminaciones. El acumulado desde 5c21254 comprende 10 archivos, incluidas sanitización, observabilidad, autorización de reconciliación y recuperación PWA.

Snapshot creado con `git archive c345ba2` como `head.zip`, extraído en `src`. Verificación final contra todos los miembros del ZIP: **112 archivos, cero miembros modificados**. Los instrumentos y resultados están fuera del snapshot.

Raíz aislada conservada:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-c345ba2-639c45a17657442a8d1bf727e4927e84`

PostgreSQL **17.11 real**, Python **3.13.18**, psycopg **3.2.6**. Contenedores exclusivos `civia_audit_c345ba2_pg`, `_runner`, `_api`, `_frontend`; bases nuevas para instrumentos, API, suites y migraciones. Red interna exclusiva `civia_audit_c345ba2_net`; solo el frontend se conecta además a `civia_audit_c345ba2_browser_net`, exclusiva, para exponer `127.0.0.1:55983` al navegador de prueba. Sin bases, volúmenes o redes habituales.

API y runner usan la imagen local solo como runtime, importando código congelado desde `/audit/src` y `/audit/src/backend`. Frontend construido desde `src/frontend`. Imágenes: runtime `sha256:843e6979568902ee08ba2106fe4a8459042f95108eba22f10dde3365aeeab0d3`, PostgreSQL `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b`, frontend `sha256:6337423794c5eb35aa97e4ee8c5899995c4b0966ab1f4a462bf341f5d91d861b`.

Sin `.env`, credenciales privadas, datos reales ni llamadas a proveedores IA. Suites con claves vacías o marcadores sintéticos. La PWA usa adaptador IA sintético y negocio de auditoría en tabla propia, con API, executor, Nginx y PostgreSQL reales. La prueba F1 usa el adaptador real, pero intercepta todas sus peticiones con HTTP MockTransport; ningún mensaje sale a Internet. Los resultados guardan booleanos/hashes, no capacidades en claro.

## Skills aplicadas y verificaciones aportadas

Se descubrieron los SKILL.md disponibles en el entorno y se seleccionaron cinco, sin cargar todas las alternativas de la solicitud. Autorización y alcance proceden del encargo explícito: repo/commit indicados, recursos desechables propios y ningún servicio habitual.

| Hallazgo/tarea | Skill y archivo leído | Instrucción aplicada | Verificación concreta |
|---|---|---|---|
| F8, causa y productores de marcas | `systematic-debugging`, `C:\Users\Jhoesp\.codex\plugins\cache\openai-curated-remote\superpowers\7.0.1\skills\systematic-debugging\SKILL.md` | Reproducir y rastrear el flujo entre componentes antes de proponer corrección; contrastar patrón que funciona con el que falla | Clasificador aislado estable frente a marcas producidas por checked_commit; controles positivos y cancelación externa observada durante COMMIT |
| F2/F3/F6 | `api-security`, `C:\Users\Jhoesp\.codex\skills\api-security\SKILL.md` | Matriz de autorización y replay de lógica de negocio con identidades/capacidades diferentes, dentro del laboratorio autorizado | Propietario/tercero/anónimo, credencial ciudadana frente a administrativa, GET sin mutaciones no autorizadas; sin enumeración sobre sistemas externos |
| F4 | `frontend-api-integration-patterns`, `C:\Users\Jhoesp\.codex\skills\frontend-api-integration-patterns\SKILL.md` | Comprobar reintentos, deduplicación y consistencia del estado asíncrono | Pérdida de respuesta, recarga antes/después del replay, misma clave/capacidad e ID; contador SQL por intento |
| F4 y E2E | `playwright-skill`, `C:\Users\Jhoesp\.codex\skills\playwright-skill\SKILL.md` | Script temporal, URL parametrizada, navegador visible, selectores/esperas por estado y captura de evidencia; ejecución mediante run.js | Edge con perfil/contexto separado, PWA compilada, screenshots y transporte real. Detección restringida por HEAD al puerto exclusivo: no se ejecutó el escaneo genérico de puertos que incluiría servicios habituales prohibidos |
| F7 y transacciones | `postgres-best-practices`, `C:\Users\Jhoesp\.codex\skills\postgres-best-practices\SKILL.md` y `rules/lock-short-transactions.md` | Examinar alcance de locks/transacciones y evitar atribuir atomicidad solo al retorno de aplicación | Dos mutaciones serializadas con trazas de versiones; rechazo de INSERT/ledger ausente y lectura independiente de rollback. No se añadieron metas de rendimiento |

No se aplicaron fases de implementación/TDD GREEN ni refactor: el encargo prohíbe modificar producto. Las sugerencias se limitan a los fallos reproducidos.

## Matriz de aceptación F1–F8

| Contrato | Dictamen | Evidencia y límite |
|---|---|---|
| F1 Secretos | **FAIL** | Sanitización recursiva durable/trazas/respuesta pasa los casos anteriores. Pero la capacidad externa al prompt se inyecta en args compartidos y reaparece en raw_gemini_part del siguiente JSON al adaptador |
| F2 Privacidad | **PASS** | Propietario recibe resultado; tercero/anónimo no reciben resultado privado, approval_id, target ni error. Incluye COMMITTED y sondeo PENDING→COMMITTED, ABORTED y UNKNOWN; cero segundo worker |
| F3 Privilegios | **PASS** | Credencial ciudadana de edición no autoriza operación administrativa sobre el mismo reporte; propio/admin sí acceden |
| F4 Recuperación PWA | **PASS en recorrido real ejecutado** | Primera respuesta perdida sin conocer ID; capacidad/clave conservadas antes del envío; recarga y replay con las mismas credenciales; una operación por intento; polling y restauración correctos; limpieza explícita elimina credencial local |
| F5 UNKNOWN | **PASS** | Helper genérico rechaza UNKNOWN sin evidencia; ausencia conserva incertidumbre; ocho GET autorizados concurrentes con evidencia propia resuelven COMMITTED; terminales protegidos |
| F6 Reconciliación autorizada | **PASS** | GET público sin token conserva UNKNOWN incluso con evidencia; privado anónimo 404 sin mutación; autorizado reconcilia. PID ausente/observación fallida conservan incertidumbre. ACK perdido y proceso reiniciado recuperan COMMITTED |
| F7 Auditoría REST | **PASS** | Acción, estados anterior/nuevo, versiones y notas; concurrencia serializada, autorización y rollback conjunto; inexistente sin éxito falso. Admin compartido es limitación documentada, no bloqueo |
| F8 Causalidad | **FAIL** | Clasificador sin marca pasa negativos y es estable. checked_commit marca como «confirmadas locales» excepciones externas 57014/25P04 solo por ocurrir en sus fases protegidas. Positivos locales reales también funcionan |

## Bloqueo F1 — La capacidad se reenvía por raw_gemini_part

**Ubicaciones:** `backend/app/agent.py:849` inyecta capacidad en tool_args; `:1138` conserva args y raw_gemini_part sobre la misma estructura; `:1655-1662` retiene el raw sin sanitizar; `:1069-1070` lo usa directamente al construir la siguiente petición Gemini.

**Esperado:** una capacidad entregada por cabecera/parámetro independiente del prompt no debe aparecer en contents/functionCall ni enviarse al proveedor.

**Reproducción (`gemini_boundary.py`):**

1. Generar capacidad sintética fuera de banda y llamar a `run_civia_agent` con `client_token` e Idempotency-Key.
2. Ejecutar `_call_agent_turn_gemini` real con httpx.MockTransport, sin sustituir su serialización.
3. La primera respuesta simulada contiene una functionCall con argumentos de negocio inocuos y thoughtSignature sintético; **no contiene la capacidad**.
4. El executor añade `tool_args['operation_token']` al adquirir el reclamo. Esos args pertenecen también al raw original.
5. La segunda petición serializada usa el raw del historial y contiene la capacidad.

```text
request_number=1: client_capacity_in_outbound_json=false
request_number=2: client_capacity_in_outbound_json=true
client_cap_in_public_tools=false
client_cap_in_durable_proposed=false
```

No se modeló una IA que ya conociera el secreto: el primer mensaje y la primera respuesta no lo contienen. La herramienta recibe un objeto compartido que el código modifica. La fuga se observa en el límite HTTP real del adaptador, antes del transporte simulado. No hubo exposición a un proveedor externo durante la auditoría.

**Impacto:** el proveedor podría recibir la capacidad de consulta, que es un secreto de posesión. Que payload y respuesta estén sanitizados no protege el raw utilizado en el prompt siguiente.

**Clasificación:** defecto de la corrección posterior a 5c21254; la sanitización recursiva corrige los casos previos, pero la inyección del token en argumentos y el bypass del raw abren esta ruta concreta.

**Corrección mínima:** no mutar el objeto de argumentos/raw con capacidades; mantener autenticación fuera de los argumentos de negocio. Sanear también el contenido que efectivamente se serializa, preservando los campos de protocolo necesarios, y proteger este caso con el adaptador/MockTransport real. No basta sanear solo conversation.args o tools_invoked.

## Bloqueo F8 — checked_commit certifica sin evidencia el origen de errores externos

**Ubicaciones:** `backend/app/db.py:899`, `:949`, `:985` asignan `_civia_confirmed_local_deadline=True` en bloques except; `:156` acepta esa marca como evidencia positiva. El caso reproducido de COMMIT pasa por `:985`.

El clasificador nuevo ya no infiere por reloj o capability y conserva su resultado. El problema está en **quién produce la marca**: checked_commit la asigna a la excepción capturada sin demostrar causalidad exclusiva local.

### Contraejemplo 57014 externo durante COMMIT

`causal_races.py` crea tabla de negocio sintética y trigger diferido con pg_sleep(0,4). Plazo CIVIA: 2 s. Usa checked_commit real, negocio y marcador en la misma transacción. Una conexión de control exclusiva espera observar el **mismo backend** en `active / COMMIT / PgSleep` y ejecuta `pg_cancel_backend(pid)`.

**Esperado:** rollback real permitido, pero conservar causa externa/indeterminada; no certificar que venció CIVIA.

**Observado en dos ejecuciones:**

```text
Control observa COMMIT/PgSleep; pg_cancel_backend=true
Error emitido: TimeoutError
Causa PostgreSQL real: QueryCanceled, 57014
_civia_confirmed_local_deadline=true
is_deadline_cancellation=true
Plazo local todavía disponible: 1,970 / 1,968 s aproximadamente
Negocio persistido=0; operation_records=ABORTED
```

El timer local de 2 s no venció; la cancelación externa es conocida y observada. El rollback y ABORTED concuerdan con el motor, pero su atribución al deadline es falsa.

### Contraejemplo 25P04 de sesión ajeno al plazo

Otra conexión comienza con opción de sesión `transaction_timeout=60ms`; su operación tiene plazo CIVIA a 2 s y ejecuta el mismo trigger diferido mediante checked_commit. El código configura sus límites, pero el servidor termina por el límite de sesión corto.

```text
Causa PostgreSQL real: TransactionTimeout, 25P04
Error emitido: TimeoutError
Marca local=true; clasificación local=true
Restante del plazo CIVIA: 1,918 / 1,917 s aproximadamente
Negocio=0; marcador=ABORTED
```

Se conservaron ambas repeticiones. Esto responde específicamente a la carrera entre límite de sesión y límites configurados por CIVIA: **haber configurado un timeout no identifica cuál causó la excepción**.

Los ensayos iniciales con SET LOCAL durante una transacción ya abierta no interrumpieron el commit y terminaron COMMITTED. Se conservan en `causal_commit_results.json`; no se contaron como fallos. Se usaron después controles que realmente provocan la excepción: cancelación externa observada y timer de sesión al conectar. No se simularon las excepciones ni los resultados SQL de estos dos contraejemplos.

**Impacto real:** normalización y diagnóstico causal incorrectos de un fallo externo; no se afirma corrupción o pérdida de negocio, pues los casos medidos hicieron rollback conjunto. El contrato F8 exige conservar incertidumbre y no rotular como probado un origen no demostrado.

**Clasificación:** problema de la corrección del commit c345ba2: el clasificador se vuelve conservador, pero checked_commit fabrica la marca que lo habilita.

**Corrección mínima:** no asignar confirmación local incondicional por estar dentro de una fase de commit ni por haber armado un límite. Separar estado del supervisor de procedencia del error de PostgreSQL; cuando no exista evidencia exclusiva, preservar la causa original/indeterminada y el resultado durable. Proteger los dos escenarios anteriores junto con el positivo local real.

## F8 — Negativos y positivos independientes

Los instrumentos originales, conservados sin modificar expectativas, verifican ahora correctamente:

- 57014/25P04 externos antes del deadline, primera inspección tardía y posterior expiración de capability: false estable.
- cancel solicitado pero fallido: contador 0, sin marca propia efectiva, error externo false.
- cancel enviado mientras no existe sentencia activa y posterior statement_timeout externo real: contador de envíos 1, clasificación false; enviar no demuestra causa.
- AdminShutdown 57P01 real y UndefinedTable 42P01 real: false y tipos preservados.

**Positivo local no circular (`causal_commit.py`):** plazo CIVIA de 0,20 s, sin timer externo y statement_timeout deshabilitado para aislar el límite de transacción; trigger diferido de 0,4 s. El límite armado por el código interrumpe el COMMIT con **25P04 real**, retorna TimeoutError, negocio=0 y ABORTED. Duración observada: 0,217 s aproximadamente. Este control demuestra que el timeout local no quedó desactivado.

**Supervisor real:** consulta de solo lectura que tarda 0,20 s frente a límite de 0,05 s produce TimeoutError. Los recorridos transaccionales de las suites e instrumentos conservan OperationPendingError e identidad durable cuando corresponde.

**Juicio sobre la prueba histórica modificada:** cambiar `past_deadline→True` por false para una QueryCanceled externa construida sin evidencia local **corrige un contrato equivocado**; la antigüedad del plazo no demuestra causa. No recomiendo restaurar esa aserción. La nueva prueba positiva que añade manualmente `_civia_confirmed_local_deadline=True` solo verifica que el clasificador confía en la marca, no que producción la emita correctamente. El positivo SQL independiente anterior aporta la cobertura local real que faltaba; los dos negativos dentro de checked_commit aportan la cobertura adversarial que sigue faltando.

## Controles aprobados F2–F7 y regresiones

F1 parcial: los casos originales de sanitización anidada ahora excluyen credenciales de proposed_payload, fingerprint, resultado, trazas y respuesta; description/quantity legítimos se conservan. F1 falla solo por la frontera raw identificada, no por repetir el defecto superficial ya corregido.

F2: doce combinaciones de COMMITTED/ABORTED/PENDING/UNKNOWN con propietario, tercero y anónimo; sin segundo worker. Propietario obtiene resultado; terceros no obtienen secretos, target, error o approval_id. El sondeo que pasa PENDING→COMMITTED también oculta approval_id no autorizado.

F3: propio/admin 200 y resultado; ajeno/inválido/anónimo/editor del reporte 404 para operación administrativa privada con el mismo report_id.

F5: helper bloquea UNKNOWN sin evidencia; ocho consultas autorizadas concurrentes con evidencia del mismo operation_id resuelven COMMITTED. Trigger 006 mantiene terminales; replays/metadatos legítimos funcionan.

F6: GET público sin credencial conserva UNKNOWN pese a existir evidencia propia; GET privado anónimo no altera PENDING; autorizado sí reconcilia. PID ausente y evidencia temporalmente inaccesible no prueban aborto. Proxy que elimina ACK real termina con negocio=1, marcador COMMITTED y retorno PENDING con ID. Proceso escritor terminado durante COMMIT/PgSleep se recupera desde proceso nuevo como 200/COMMITTED.

F7: las dos escrituras concurrentes producen versiones consecutivas y registros con acción, estados, nota y versiones correctas. INSERT rechazado o ledger ausente revierte todo; inexistente no crea auditoría falsa; autorización/admin y aprobación humana se mantienen. La credencial administrativa compartida limita atribución individual y no se trata como nuevo bloqueo.

## F4 — PWA real y almacenamiento de capacidad

Se ejecutó `playwright-test-final.cjs` mediante `playwright-skill/run.js`, Edge visible, perfil/contexto separado y URL parametrizada del frontend compilado. Solicitudes ajenas al origen de auditoría bloqueadas. Service worker bloqueado para hacer determinista el transporte: no se evalúa modo offline.

El proxy de `serve.py` recibe y descarta íntegramente la respuesta FastAPI después del efecto durable y cierra el transporte; el navegador solo recibe 502 de Nginx. El test no lee el cuerpo perdido para conocer ID o token.

Resultados:

```text
Credenciales persistidas antes de recibir respuesta: true
Cliente no conoce operation_id de la respuesta perdida: true
Recarga antes de reintentar restaura consulta: true
Reintento con misma Idempotency-Key y capacidad: true / true
Una operación COMMITTED asociada al hash de esa clave: true
Polling propietario: COMMITTED y resultado visible
Recarga después de recuperar conserva el mismo ID: true
Capacidad en DOM / URL / logs capturados: false / false / false
«Nueva consulta / Limpiar sesión» elimina almacenamiento: true
```

La primera ejecución del navegador completó recuperación y polling, pero el coordinador de auditoría capturó logs después de su espera de 20 s, causando ENOENT antes de la comprobación final. Se conserva en `pwa_attempt1`. Se amplió únicamente la espera de coordinación a 50 s y se repitió en contexto nuevo; segunda ejecución completa exitosa. Cada ejecución genera un intento independiente y **un efecto por clave**. El contador global 2 corresponde a esos dos ensayos separados, no a duplicación por replay; `pwa_business_verification.json` relaciona la clave del ensayo final con una sola operación.

Alcance del almacenamiento: clave `civia_pwa_agent_attempt` en localStorage del origen, con consulta, capacidad, ID y última respuesta; reutilización condicionada a la misma consulta y eliminación explícita comprobada. El navegador de prueba dispone de crypto.randomUUID. Una capacidad bearer durable en localStorage es accesible a scripts del mismo origen/perfil y requiere proteger ese origen; no equivale a cifrado ni a identidad individual. Es una limitación del mecanismo, **no un requisito nuevo de cifrado/expiración para impedir este cierre**. El control de acceso F1 al proveedor sigue siendo un bloqueo separado.

## Suites, exclusiones e interpretación

| Ejecución | Resultado |
|---|---|
| BLANK, `pytest -m "not live" -q -rs` | **132 passed, 1 deselected**, 19,13 s |
| SYNTHETIC, mismo comando | **132 passed, 1 deselected**, 22,18 s |
| Identificación live opcional + E2E, claves vacías | **1 passed, 1 skipped**, 0,39 s |
| `python -m compileall -q app tests` | Código 0 |

Una advertencia AnyIO por suite. Incluyen adversariales F1–F8, G1, G2, A-02, M-02, M-03 COPY, M-06, N-02 y frontend/proxy. Guardia hermética sin llamadas externas inesperadas. No se modificaron pruebas para conseguir PASS.

**Resultado reportado por AG 131 PASS / 1 skipped / 1 deselected:** la deselected es `tests/test_ai_and_agent.py::test_optional_live_provider_multimodal_connectivity`, marcada live y excluida para no contactar proveedor. La prueba de omisión por falta de frontend es `tests/test_e2e_frontend_proxy.py::test_frontend_pwa_and_nginx_reverse_proxy_e2e`, línea 15. Aquí sí existe frontend aislado y pasa, por lo que se observa **132 PASS sin skips** en las suites filtradas. Al ejecutar ambas aisladamente con claves vacías, live se omite con razón explícita y E2E pasa. No se inventan las condiciones del entorno previo de AG ni se cuentan skips como aprobaciones.

Los seis instrumentos originales y `adversarial.py`/`closure.py` se conservaron byte por byte; hashes comparados. No se alteraron sus expectativas. Algunos capturan errores y salen en 0 tras una preparación rechazada correctamente por terminal/UNKNOWN; followup se detiene al rechazarse ABORTED→COMMITTED. Se inspeccionaron cada resultado y su cola con el instrumento ya existente, sin interpretar exit 0 como todos PASS. El error histórico de parametrización del instrumento de migración se conserva y no se atribuye al producto; sus complementos se ejecutaron. No se repitió la investigación histórica fuera de F1–F8.

No se encontró comando/configuración lint Python; compileall no es lint. Los cambios documentales se verifican con git diff --check. No se cambiaron modelos ni se hicieron preflights remotos de IA, porque no forman parte de esta remediación y están prohibidas las llamadas externas.

## Evidencia y reproducción

En la raíz aislada: snapshot, dos diffs, scripts originales, `closure_results.json`, `targeted_tail_results.json`, resultados de autorización/reconciliación/REST, logs de suites, build, ACK y reinicio. Nuevos instrumentos:

- `gemini_boundary.py`: adaptador real de Gemini y HTTPMockTransport; solo registra indicadores, no el secreto.
- `causal_commit.py`: control local real, supervisor y cancel enviado sin prueba causal; conserva ensayos iniciales no interruptivos.
- `causal_races.py`: cancelación externa observada y timer de sesión externo durante COMMIT, con SQL real y snapshot independiente. Repetición previa en `causal_races_run1.json/.log`.
- `playwright-test-final.cjs`: pérdida completa de respuesta, recargas y credencial local; capturas `pwa_lost_response.png`, `pwa_authorized_poll.png`, resultados `pwa_final_results.json`.
- `snapshot_verification.json`, `pwa_business_verification.json`, logs API/frontend y eventos de proxy con hashes.

Para repetir, montar raíz en `/audit`, usar PYTHONPATH `/audit/src:/audit/src/backend`, crear PostgreSQL exclusivo y bases nuevas con prefijo test_, aplicar migraciones/seed sintético y configurar únicamente URL de ese clúster. Contraseña del clúster eliminado: `audit_synthetic_only`, exclusivamente sintética. No cargar `.env` habitual. Los instrumentos crean tablas/triggers y necesitan bases nuevas. Ejecutar causal_commit antes de causal_races, pues crea su tabla/trigger; ambos preservan controles de lectura desde otra conexión.

El navegador usa el runtime de la skill ya instalado y `run.js` con `await require(ruta_temporal)`. Se verificó por HEAD solo el puerto exclusivo, sin usar el detector genérico que también sondearía servicios habituales prohibidos. Coordinación de logs por archivos pwa_logs_requested/ready; nunca se serializa la capacidad en resultados. El adaptador HTTP real de F1 está totalmente interceptado por MockTransport.

| Evidencia | SHA-256 |
|---|---|
| head.zip | `8FABA1B48685B469C362F00BFC9D412FA8401D74A2BBE8425D016C7C8B7A8431` |
| gemini_boundary_results.json | `6C454CDC973FFC86B630EC5089BF3F370B2C10948A1B60FE7414337EC28EB8FA` |
| causal_races_results.json | `071B703D2F3E1602F9972A8315A8D7733B1CD9E0E4D5565A471B20423D2ABB88` |
| pwa_final_results.json | `E74B45DE30A1B96EE46171B3CCAE02E1667C15E0430320E7AC2E6A8BD3A6A408` |
| suite_blank.log | `785B7F41DA9CD13B4EA504BA0D9892A160EBE38D7EBFAF4BB22CC55891349CAE` |
| suite_synthetic.log | `FD1EC7C190586AC6FD076BBDDF9C1D9FAD9AEA925726D5EC09F902F81114BA3F` |

## Cierre

No se corrigió código ni se cambiaron pruebas existentes. Sin CIVIA Autopilot, commits, push, merge ni cambio de rama. Solo se generan este informe y la anotación de docs/estado.md en el checkout.

La limpieza retira exclusivamente contenedores, volumen, redes e imagen creados por el auditor, previa comprobación de IDs; evidencia aislada conservada. Servicios habituales verificados saludables al cerrar. La auditoría se detiene con este dictamen; no se inicia una fase nueva de desarrollo.
