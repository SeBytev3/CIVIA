# CIVIA — Auditoría de aceptación con puerta temprana F1/F8

Fecha: 2026-11-05, America/Bogota. Commit exacto: `cf48e710a4d321455864d2b59a4257cdca9938aa`. Rama: `fix/auditoria-final`. Referencia: `docs/auditoria_codex_g2_1_8_c345ba2.md`.

## Dictamen

**G2.1.8 APROBADA para el commit exacto auditado.** La puerta temprana F1/F8 pasa con la distinción explícita entre procedencia SQL y vencimiento del presupuesto local que se desarrolla abajo. Se continuó a la fase de cierre y no se reprodujeron regresiones bloqueantes relacionadas en F2–F7, A-02 o M-03.

La aprobación corresponde a los contratos solicitados y al snapshot identificado; no ejecuta despliegue, commit, push o merge. No se modificó producto ni pruebas existentes.

## Preparación, skills y aislamiento

Comandos ejecutados desde `C:\Users\Jhoesp\Desarrollo\CIVIA`: HEAD exacto solicitado, rama esperada y `git status --short` inicialmente sin salida. Se leyeron AGENTS.md, el informe anterior y el diff completo c345ba2→cf48e71. Son 8 archivos: agent/db, configuración y fixtures de tests, pruebas de frontera, ajuste de replay autorizado y documentos. El diff queda en `diff.patch`.

Snapshot `head.zip` generado por `git archive cf48e71`, extracción `src`. Verificación al cerrar: **113 miembros del ZIP, cero archivos fuente modificados**.

Raíz aislada conservada:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-cf48e71-e052c8633d5f4de383d66e78e35b5c1c`

PostgreSQL **17.11 real**, Python **3.13.18**, psycopg **3.2.6**. Recursos exclusivos `civia_audit_cf48e71_pg`, `_runner`, `_api`, y, tras superar la puerta, `_frontend`. Bases nuevas `test_audit`, `test_api`, `test_suite_blank`, `test_suite_synthetic` y las bases propias creadas por instrumentos y tests.

Red interna exclusiva `civia_audit_cf48e71_net`. Para Playwright, solo el frontend se conectó además a `civia_audit_cf48e71_browser_net`, exclusiva, con puerto `127.0.0.1:55985`. Ninguna base, volumen o red habitual se usó para pruebas. Los tres servicios habituales se comprobaron por metadatos y permanecieron saludables.

API/runner reutilizan la imagen local solo como runtime, con imports desde `/audit/src` y `/audit/src/backend`. Frontend construido desde el snapshot. Sin `.env`, datos reales ni claves IA privadas. Turnos sintéticos para PWA; adaptadores reales con httpx.MockTransport para F1. Ningún mensaje se envió a proveedores externos. No se cambiaron IDs de modelos de producción ni se realizaron preflights remotos.

### Correspondencia con skills

Se descubrieron y seleccionaron skills pertinentes, sin aplicar todas las alternativas ni iniciar desarrollo:

| Tarea | Skill leída/aplicada | Instrucción aplicada | Evidencia aportada |
|---|---|---|---|
| Puerta F8 | `systematic-debugging`, `C:\Users\Jhoesp\.codex\plugins\cache\openai-curated-remote\superpowers\7.0.1\skills\systematic-debugging\SKILL.md` | Reproducir, comparar con casos que funcionan y seguir causa/objeto entre capas antes de sugerir cambios | Negativos repetidos, positivo SQL real y separación excepción original/envoltura/supervisor |
| Puerta F1 | `backend-security-coder`, `C:\Users\Jhoesp\.codex\skills\backend-security-coder\SKILL.md` | Validar fronteras externas, saneamiento y exclusión de secretos en mensajes/resultados | Adaptadores Gemini/Groq reales interceptados, inspección de JSON, firma, args, contexto y trazas |
| Criterio de aceptación | `code-review-and-quality`, `C:\Users\Jhoesp\.codex\skills\code-review-and-quality\SKILL.md` | Revisar corrección y error paths, comprobar qué prueban las aserciones, no bloquear por preferencias o perfección ajena al contrato | No se exige clasificar una causa SQL ambigua como local ni eliminar toda envoltura TimeoutError cuando el plazo sí venció |
| Recuperación PWA | `playwright-skill`, `C:\Users\Jhoesp\.codex\skills\playwright-skill\SKILL.md` | Scripts temporales, URL parametrizada, navegador separado, esperas por estado y capturas | Edge visible y perfil de prueba, PWA real, pérdida de respuesta, recargas y polling. Detección por HEAD solo del puerto propio, evitando el escaneo de puertos habituales prohibidos |
| Reintento y estado cliente | `frontend-api-integration-patterns`, `C:\Users\Jhoesp\.codex\skills\frontend-api-integration-patterns\SKILL.md` | Comprobar deduplicación y consistencia de reintentos asíncronos | Misma clave/capacidad e ID tras pérdida y recarga; contador PostgreSQL único |

No se aplicó una fase GREEN ni refactor. La autorización para el laboratorio y su alcance provienen de la solicitud expresa; no se contactaron objetivos externos.

## Matriz final

| Contrato | Resultado | Verificación |
|---|---|---|
| F1 Capacidad y serialización | **PASS** | Primera y segunda petición Gemini/Groq sin capacidad; raw/signature/args de negocio preservados; contexto interno autoriza; replay legítimo ejecuta una vez; sin secretos en trazas/payloads/historial público |
| F2 Privacidad | **PASS** | Replays propietario/tercero/anónimo en cuatro estados; sin resultado, approval_id, target o errores privados para no propietario; incluye PENDING que confirma |
| F3 Privilegios | **PASS** | Credencial de edición ciudadana no accede a operación administrativa; propio/admin sí |
| F4 Recuperación PWA | **PASS** | Respuesta perdida íntegramente, recarga, mismas credenciales, mismo ID y un efecto; polling autorizado, restauración y limpieza explícita |
| F5 UNKNOWN/terminales | **PASS** | Sin evidencia no confirma; evidencia exacta propia resuelve bajo concurrencia; terminales protegidos |
| F6 Reconciliación autorizada | **PASS** | GET público/anónimo sin mutación durable; autorizado reconcilia; incertidumbre conservada; ACK perdido/reinicio recuperables |
| F7 Auditoría REST | **PASS** | Acción, estados, versiones y nota atómicos; rollback, concurrencia y autorización; inexistente sin éxito falso |
| F8 Causa SQL y supervisor | **PASS** | Negativos reales 57014/25P04 repetidos sin marca local falsa; causa SQL estable en manejo tardío; deadline local real conserva guardrail y rollback; transacciones no resueltas conservan ID/PENDING |

## Fase 1 — F1: fronteras Gemini y Groq

Se conservó `gemini_boundary.py` sin cambiar sus expectativas independientes. Resultado: primera y segunda petición sin capacidad; ni tools públicos ni proposed_payload durable la contienen.

`gate_f1.py` amplía el control a ambos adaptadores reales. Solo se reemplaza el transporte de httpx por MockTransport. Cada proveedor realiza cuatro peticiones: dos para ejecutar y dos para replay con las mismas credenciales. El modelo simulado recibe inicialmente solo argumentos inocuos de negocio; no conoce la capacidad.

| Control | Gemini | Groq |
|---|---|---|
| Capacidad en cualquier mensaje serializado | false | false |
| Argumentos de negocio preservados | true | true |
| thoughtSignature de Gemini preservada | true | No aplica al protocolo Groq |
| Contexto interno contiene capacidad correcta | true | true |
| Ejecuciones de worker después de replay | 1 | 1 |
| Mismo operation_id recuperado | true | true |
| Polling propietario con resultado | 200 / presente | 200 / presente |
| Capacidad en registro durable o trazas inspeccionadas | false | false |

`closure.py` conserva los controles recursivos: secreto anidado ausente de proposed_payload, resultado, trazas y respuesta; modificar solo credencial no cambia fingerprint; datos legítimos description/quantity intactos.

**Referencias compartidas:** `reference_probe.py` usa el parser/serializador real de Gemini. Los args y sus objetos anidados no son el objeto de `raw_gemini_part.functionCall.args`. Se mutan deliberadamente los args del consumidor: el raw de negocio queda intacto, thoughtSignature no cambia y la capacidad añadida al objeto mutado no reaparece en el JSON siguiente. Todos los indicadores resultan true. El diff elimina la inyección de credencial en tool_args, mantiene esa capacidad en el contexto interno y copia las estructuras antes de usarlas.

No se confunden las claves sintéticas de autenticación del proveedor de prueba con la capacidad ciudadana: la prueba busca esta última y ningún request salió del MockTransport.

## Fase 1 — F8 negativos repetidos

Se conservaron `causal_races.py`, `causal_commit.py` y `closure.py` byte por byte. El instrumento original de races extrae el SQLSTATE desde `__cause__`; ahora una excepción SQL preservada sale directamente, sin envoltura, por lo que ese campo antiguo aparece null. No se interpreta como pérdida de SQLSTATE: `gate_f8.py` inspecciona explícitamente ambos objetos y confirma el SQLSTATE del objeto que realmente se lanzó.

### A. Cancelación externa observada durante COMMIT

Trigger diferido con pg_sleep(0,4), deadline CIVIA de 2 s. Una conexión de control espera el mismo PID en `active / COMMIT / PgSleep` y ejecuta pg_cancel_backend. Dos repeticiones:

```text
Excepción lanzada: QueryCanceled
SQLSTATE: 57014
Tiempo local restante al retornar: 1,969 / 1,968 s aproximadamente
Marca local falsa: false
Clasificación original/exterior: false / false
Negocio: 0; registro durable: ABORTED
```

### B. transaction_timeout externo de sesión

Conexión con `options=-c transaction_timeout=60ms`, deadline CIVIA de 2 s y el mismo commit diferido. Dos repeticiones:

```text
Excepción lanzada: TransactionTimeout
SQLSTATE: 25P04
Tiempo local restante: 1,918 / 1,920 s aproximadamente
Marca local falsa: false
Clasificación original/exterior: false / false
Negocio: 0; registro durable: ABORTED
```

El rollback se verifica desde otra conexión, no se deduce solo del tipo de excepción. El código ya no añade `_civia_confirmed_local_deadline` por estar dentro de checked_commit ni por haber configurado un límite.

Los negativos de closure también pasan: timers externos, primera inspección tardía, misma excepción tras expirar capability, solicitud cancel fallida y cancel enviado sin evidencia causal siguen false. 57P01 y 42P01 reales preservan tipo y clasificación de infraestructura. No se restauró la expectativa errónea «deadline pasado implica causa local».

## Verificación especial del positivo y del manejo tardío

### 1. ¿Qué objeto recibió classified_local=False?

**La excepción SQL original**, en `TimeoutError.__cause__`. No el TimeoutError exterior. `positive_object_results.json` lo mide explícitamente:

```text
outer_type=TimeoutError
outer_classified_local=true
sql_cause=TransactionTimeout; sqlstate=25P04
sql_cause_classified_local=false
false_local_marker=false
deadline_effectively_expired=true
business=0; status=ABORTED
```

Conservar false en la excepción SQL es una clasificación conservadora de procedencia. No significa que el supervisor haya perdido la capacidad de aplicar su presupuesto. No se exige una marca causal artificial para aprobar el positivo.

### 2. ¿El timeout local fue real y conserva guardrail?

Sí. En el control de commit solo se configuran los límites de CIVIA: deadline 0,20 s, sin timer externo, statement_timeout deshabilitado para aislar el caso y trigger diferido de 0,4 s. Se obtiene 25P04 real como causa de TimeoutError, negocio=0 y ABORTED; el tiempo observado supera efectivamente el deadline.

Además, `supervisor_http.py` usa la API real con turno simulado y lectura que tarda 0,20 s frente a límite de herramienta de 0,05 s: HTTP 200, **guardrail TIMEOUT**, sin operation_id transaccional y plazo efectivo vencido. No es una excepción preconstruida para hacer pasar el clasificador.

### 3. ¿Puede aparecer un TimeoutError si una cancelación externa se maneja después del plazo?

**Sí, como envoltura exterior de vencimiento local**, no como modificación de la causa SQL. Se provocó la cancelación externa durante COMMIT cuando aún quedaban unos 0,132/0,131 s de deadline; se retuvo el rollback/manejo 0,20 s para cruzar el límite. Dos repeticiones:

```text
Excepción exterior: TimeoutError; clasificación exterior=true
__cause__: QueryCanceled, SQLSTATE 57014
Clasificación de esa causa SQL: false
Marca local en la causa SQL: false
Negocio=0; estado durable=ABORTED
```

Este comportamiento se declara expresamente, no se oculta bajo un PASS genérico. El código de `backend/app/db.py:989-990` puede envolver después de comprobar que su presupuesto ya venció; el origen externo permanece en `__cause__`. **No se usa el reloj como prueba de que PostgreSQL fue cancelado por CIVIA.** El reloj fundamenta el hecho distinto de que el presupuesto local también se agotó.

### 4. ¿Se conserva la separación entre supervisor y causa PostgreSQL?

Sí en los objetos y recorridos observados: exterior TimeoutError local frente a causa SQL 57014/25P04 no local, sin marca falsa ni reclasificación de esa misma causa. Por eso el caso anterior no se cuenta como el defecto de c345ba2, donde la excepción SQL misma recibía confirmación causal local aun con más de 1,9 s disponibles.

Aceptar esta separación no requiere prohibir toda envoltura TimeoutError cuando el presupuesto efectivamente venció. El texto de la envoltura puede interpretarse mal si se omite su causa: el informe conserva ambos objetos para evitar esa confusión. No se impone una nueva arquitectura de tipos o metadatos como condición adicional de cierre.

### 5. ¿Hay rollback, revocación y prohibición de efectos tardíos?

Sí. Positivo local de commit: negocio=0 y ABORTED. Control antes de abrir conexión/registrar commit en vuelo: retorna PENDING con ID, worker revocado falla con TimeoutError y negocio=0; no ejecuta la escritura tardía. Las pruebas A-02 y M-03 también pasan.

`late_supervisor.py` añade el recorrido completo de la cancelación externa con manejo tardío: el supervisor retorna **OperationPendingError con el mismo ID** mientras el worker aún no termina; después el worker finaliza, la causa SQL sigue 57014/false, la capability ya no es válida, negocio=0 y el estado final es ABORTED. Se conserva así el hecho local de timeout y el origen externo del fallo SQL.

### 6. ¿Se conserva la incertidumbre de un COMMIT?

Sí en los recorridos ejecutados. ACK real descartado: cliente recibe OperationalError, pero la lectura independiente encuentra negocio=1 y COMMITTED; reconciliación conserva COMMITTED. El marcador no se convierte falsamente a ABORTED. Reiniciar proceso durante COMMIT/PgSleep permite recuperar 200/COMMITTED desde proceso nuevo.

Cuando el supervisor vence antes de conocer el final del worker, retorna PENDING con ID. Una cancelación de sentencia comprobada sin resolución durable del registro puede conservar PENDING con negocio=0; no se fuerza un terminal solo por desaparecer un PID. No se afirma que todo aborto vaya a resolverse sincrónicamente ni se simula éxito.

**Decisión de la puerta:** F1 y F8 pasan con esta lectura separada y explícita de los objetos. Se continuó a fase 2. No hubo un bloqueo reproducido al que se le ignorara la orden de detenerse.

## Fase 2 — Regresiones de cierre

F2: matriz de COMMITTED/ABORTED/PENDING/UNKNOWN con propietario, tercero y anónimo; sin segundo worker indebido. Approval_id, resultado privado, destino y error no se divulgan en replay no autorizado, tampoco si PENDING pasa a COMMITTED durante el sondeo.

F3: token propio/admin reciben 200 con resultado administrativo; token ajeno, inválido, anónimo y credencial de edición del reporte reciben 404 para la operación privada sobre el mismo destino.

F5: helper rechaza UNKNOWN sin evidencia; ausencia conserva UNKNOWN; ocho consultas autorizadas concurrentes con evidencia propia resuelven COMMITTED. Estados terminales protegidos por trigger; metadatos/replays legítimos no se bloquean.

F6: GET público anónimo conserva UNKNOWN aun con evidencia propia; privado anónimo no altera PENDING. Autorizado sí reconcilia. Fallo de observación y PID inexistente no prueban aborto. Recuperación ACK/reinicio descrita arriba.

F7: dos PATCH concurrentes tienen dos registros y cadena de versiones correcta, con acción, estados anterior/nuevo y nota. Fallo de INSERT/ledger ausente revierte reporte y marcador; inexistente no crea éxito falso. Autorización y aprobación humana se mantienen. Identidad `admin` compartida es limitación conocida y no bloqueante.

### PWA y E2E funcional

Se construyó el frontend congelado y se ejecutó Playwright sobre Nginx/FastAPI/PostgreSQL exclusivos, con adaptador IA sintético y tabla de negocio propia. Un proxy recibe y descarta íntegramente la primera respuesta FastAPI después del efecto durable; el navegador solo ve 502 de Nginx y no lee ID/token de la respuesta perdida.

Resultados:

- Intento/clave/capacidad guardados antes de la respuesta; cliente aún sin ID.
- Recarga previa restaura consulta; reintento usa **misma Idempotency-Key y misma capacidad**.
- Una operación COMMITTED para esa clave y **un efecto de negocio total**.
- Polling propietario muestra COMMITTED y resultado; recarga posterior conserva ID.
- Capacidad ausente de DOM, URL y logs API/frontend capturados después de las peticiones.
- «Nueva consulta / Limpiar sesión» elimina `civia_pwa_agent_attempt`.

LocalStorage sigue siendo almacenamiento bearer del origen/perfil, reutilizado para la misma consulta. La auditoría no afirma cifrado ni inmunidad ante un script malicioso del mismo origen; no se inventan requisitos nuevos para impedir este cierre. Service worker bloqueado en la prueba para hacer determinista el transporte; modo offline no forma parte del contrato ensayado.

## Suites y exclusiones

| Ejecución | Resultado |
|---|---|
| BLANK: `pytest -m "not live" -q -rs` | **135 passed, 1 deselected**, 19,88 s |
| SYNTHETIC: mismo comando | **135 passed, 1 deselected**, 22,91 s |
| Live opcional + E2E, claves vacías, para identificar exclusión | **1 passed, 1 skipped**, 0,41 s |
| `python -m compileall -q app tests` | Código 0 |

Una advertencia AnyIO por suite. Incluyen pruebas nuevas F1/F8, F1–F8 previas, G1, G2, A-02, M-02, M-03 COPY, M-06, N-02 y E2E frontend/proxy. No se alteraron pruebas para conseguir PASS.

La deselected es `tests/test_ai_and_agent.py::test_optional_live_provider_multimodal_connectivity`, excluida para no llamar proveedores reales. La condición de skip por frontend inaccesible está en `tests/test_e2e_frontend_proxy.py:15`; aquí frontend existe y pasa, por lo que no hay skips en las suites filtradas. En el sondeo separado con claves vacías, la live se omite con motivo explícito y E2E pasa. No se cuentan omitidas como aprobaciones.

El ajuste de la prueba histórica de replay ahora proporciona capacidad propietaria explícita en ambas llamadas: conserva la expectativa de una sola aprobación y añade la autorización necesaria; no se interpreta como permiso para divulgar resultado a un tercero. `allow_mock_transport` evita sustituir el adaptador real solo en tests marcados; la guardia HTTP sigue rechazando transporte no interceptado para proveedores. Las suites no reportan llamadas externas inesperadas.

No se encontró comando/configuración lint Python. Compileall no equivale a lint; los cambios documentales se comprueban con git diff --check.

## Instrumentos y trazabilidad

`gemini_boundary.py`, `causal_races.py`, `causal_commit.py` y `closure.py` se conservaron byte por byte frente a la auditoría anterior, con comparación de hashes. Se inspeccionaron resultados, no solo exit codes.

`gate_f1.py`, `reference_probe.py` y `gate_f8.py` son complementos que distinguen las estructuras y el objeto SQL exterior/cause; no modifican las expectativas de seguridad originales. `positive_and_snapshot.py` verifica explícitamente los dos objetos del positivo, el contador PWA y snapshot. `late_supervisor.py` y `supervisor_http.py` prueban guardrails reales, no marcas prearmadas.

Los instrumentos heredados que capturan excepciones pueden salir en 0 tras preparaciones ahora correctamente rechazadas por UNKNOWN/terminal. followup se detiene al rechazarse ABORTED→COMMITTED y su cola se ejecuta aparte; eso no es una regresión ni «todo PASS por exit 0». Un auxiliar de snapshot ejecutado antes de existir eventos PWA termina con FileNotFound después de guardar su comprobación F6; se conserva y no se atribuye al producto. El snapshot/contador final válido se verifica después de la PWA con `positive_and_snapshot.py`.

No se hizo investigación nueva de funcionalidades ajenas. La fase de regresión valida controles previamente aprobados y no los redefine.

## Reproducción y evidencia conservada

En la raíz aislada: `head.zip`, `src`, `diff.patch`, scripts, JSON, logs de build/API/frontend/suites, `pwa_lost_response.png` y `pwa_authorized_poll.png`.

Para repetir: PostgreSQL 17 exclusivo, alias pg, bases nuevas test_, raíz montada `/audit`, PYTHONPATH `/audit/src:/audit/src/backend`, URL solo del clúster desechable; nunca cargar `.env` habitual. Credencial del clúster eliminado: `audit_synthetic_only`, exclusivamente sintética. Aplicar migraciones/seed antes de los instrumentos. Estos crean tablas/triggers y no son idempotentes.

Orden de puerta: gemini_boundary, causal_commit (crea tabla/trigger), causal_races, gate_f1, gate_f8 y closure. Repetir negativos A/B con verificación de la excepción exterior y su causa. Si se reproduce un bloqueo contractual, no lanzar suites. Para la fase 2 usar bases independientes BLANK/SYNTHETIC, frontend compilado y puerto exclusivo de navegador.

El script Playwright se ejecuta mediante `playwright-skill/run.js`, con CIVIA_AUDIT_URL apuntando al puerto propio. La coordinación de captura de logs usa archivos pwa_logs_requested/ready; no se guardan capacidades en claro, solo hashes/indicadores. Los turnos de la PWA son sintéticos, pero SQL, API, almacenamiento de navegador y transporte son reales. La fase F1 usa adaptadores reales y MockTransport, sin red externa.

| Evidencia | SHA-256 |
|---|---|
| head.zip | `9D8C1820FDF4DE636C800BA681A130AB28E67E8C63C1128054BA84C75BD5FB51` |
| gate_f1_results.json | `9CA551907F3276B86966BF187E73F817A483BDA25681139ED5CF355B4EC58AD6` |
| gate_f8_results.json | `630E868D169FB1A59CDB8EE2BA3D4BBBF15B395EC9BA077CCB16405757434E29` |
| positive_object_results.json | `43C2A1D36117336CC693C72C7C1B075E19D7BAA00BF66FCC90904E9E4E46A2EC` |
| pwa_final_results.json | `BBCA1A23626F5EA2274B24F56F702EB0066F2F0C5EBA2A5A7B2798CD63E6B002` |
| suite_blank.log | `98CD077392AF11937B8EF261A284CBC19E413BD5308CBED5491CF5E6BC37B87F` |
| suite_synthetic.log | `B47D7734E87E21EF29C5940ED425807C7BF3C5C7CC49E39B4279191BB3393D7C` |

## Cierre

No hay corrección bloqueante adicional que proponer dentro de los contratos comprobados. Se recomienda cerrar G2.1.8 para este commit exacto, conservando esta evidencia y la separación documentada entre timeout local y causa SQL.

Únicos cambios del checkout: este informe y anotación de docs/estado.md. Sin código/tests modificados, Autopilot, commits, push, merge o cambio de rama. La limpieza elimina solo recursos del auditor, previa comprobación de identidad; los tres servicios habituales se verifican saludables al cerrar. Evidencia aislada preservada. Se detiene el trabajo al entregar el dictamen.
