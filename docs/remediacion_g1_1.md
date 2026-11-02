# Remediación G1.1 — Cierre Definitivo de Siete Hallazgos Residuales

- **Proyecto:** CIVIA — Momento Evaluativo 2 (Ingeniería de Aplicaciones con IA)
- **Equipo:** Stefania Córdoba y Sebastian Espinosa
- **Rama:** `fix/auditoria-final`
- **Informe auditado de referencia:** `docs/auditoria_codex_g1.md` (sobre commit `48460b6`)
- **Base de datos de verificación:** PostgreSQL 17 real (`postgres:17-alpine`) con bases desechables aisladas por corrida (`civia_test_<run_id>`, `civia_eval_<run_id>`)

---

## 1. `C-01` — Credenciales administrativas

- **Hallazgo original (`docs/auditoria_codex_g1.md`):**
  La validación `is_strong_admin_token` en `48460b6` solo exigía `len(cleaned) >= 24`, `len(set(cleaned)) >= 8` y ausencia en una lista corta de valores débiles. Esto aceptaba el contraejemplo predecible `"0123456789" * 3` (`30` caracteres y `10` dígitos distintos), permitiendo iniciar el servidor y consultar `/api/admin/observability` (`HTTP 200`).
- **Corrección aplicada:**
  1. En `backend/app/config.py`, se reforzó `is_strong_admin_token()` con validaciones deterministas que rechazan:
     - Cadenas con `< 24` caracteres, `< 10` caracteres únicos o espacios internos.
     - Cadenas de una sola clase de caracteres (solo dígitos o solo letras) o con menos de 2 clases entre minúsculas, mayúsculas, dígitos y símbolos.
     - Secuencias ascendentes, descendentes o de filas de teclado de longitud `>= 5` (`_has_sequential_run`, ej. `01234`, `98765`, `abcde`, `qwerty`).
     - Patrones periódicos globales (`s == (s[:p] * ...)[:n]`) y subcadenas repetidas de longitud `>= 3` tres o más veces o bloques adyacentes repetidos de longitud `>= 4` (`_has_repeated_pattern`, rechazando `"0123456789" * 3`, `"Ab1!" * 8`, etc.).
     - Palabras y subcadenas débiles o de demostración conocidas.
  2. Se añadió `generate_admin_token(32)` basado en `secrets.token_urlsafe(32)` (CSPRNG del sistema operativo) y se actualizaron `scripts/run.ps1`, `run.sh`, `.env.example` y `README.md` para generar credenciales con CSPRNG sin imprimirlas en consola ni versionarlas en Git, aclarando explícitamente que la impredecibilidad real proviene del CSPRNG y no de la mera longitud o diversidad de caracteres.
- **Prueba adversarial ejecutada:**
  `tests/test_audit_g1_security.py::test_g1_1_c01_rejects_sequential_and_repeated_tokens`:
  Evalúa `"0123456789" * 3`, `"9876543210" * 3`, `"abcdefghij" * 3`, `"qwertyuiop" * 3`, `"Ab1!" * 8`, `"11112222333344445555666677778888"` y `"abcdefghijklmnopqrstuvwxyz123456"`; comprueba que `TestClient(app)` lanza `RuntimeError` en el `lifespan` al iniciar con `"0123456789" * 3` y que `/api/admin/observability` responde `401`.
- **Resultado:**
  `PASSED` (`RuntimeError` en arranque con `"0123456789" * 3`, `401 UNAUTHORIZED` en endpoints administrativos y `200 OK` únicamente con token CSPRNG válido).
- **Limitaciones pendientes:**
  Ninguna dentro del alcance del servicio; la custodia del archivo `.env` local depende de los permisos del sistema operativo del host donde se despliegue.

---

## 2. `A-01` — Recuperación indebida de credenciales de edición

- **Hallazgo original (`docs/auditoria_codex_g1.md`):**
  En `48460b6`, cuando un cliente enviaba `POST /api/reports` sin cabecera `Idempotency-Key`, `main.py` construía una clave implícita `op:<req_fingerprint>` a partir de campos públicos (`title`, `description`, `lat`, `lon`, `photo_sha256`). Además, `derive_citizen_edit_token()` derivaba el token de edición con HMAC sobre `settings.DATABASE_URL` y `report_id`. Un segundo cliente anónimo podía descargar los campos públicos (`GET /api/reports/{id}`) y la fotografía pública (`GET /api/reports/{id}/photo`), reenviar el `POST /api/reports` y recibir de vuelta el `citizen_edit_token` del reporte original para sobrescribir su clasificación (`PATCH /api/reports/{id}/confirm` -> `200`).
- **Corrección aplicada:**
  1. Se eliminó por completo `derive_citizen_edit_token()` de `backend/app/repository.py`.
  2. Cada reporte genera una capacidad de edición aleatoria independiente mediante CSPRNG: `generate_citizen_edit_token()` (`secrets.token_urlsafe(32)`), almacenando únicamente su hash SHA-256 en `reports.edit_token_hash`.
  3. Se eliminó el respaldo idempotente implícito por contenido público (`op:<req_fingerprint>`) en `backend/app/main.py`. La idempotencia solo opera cuando el cliente envía una cabecera explícita `Idempotency-Key` (`8..128` caracteres).
  4. Para que solo el propietario de la `Idempotency-Key` pueda recuperar `citizen_edit_token` en un reintento legítimo sin almacenar ni la clave ni el token en texto plano en PostgreSQL:
     - `reports.idempotency_key` e `idempotency_records.idempotency_key` almacenan `SHA-256("civia-idem-v2:" + raw_idem_key)`.
     - `idempotency_records.citizen_edit_token` almacena el token cifrado con un flujo derivado mediante `hashlib.pbkdf2_hmac("sha256", raw_idem_key, report_id.bytes, 10_000)`.
  5. En `frontend/src/api.ts`, `submitCitizenReport` genera una `Idempotency-Key` aleatoria (`crypto.randomUUID()`) por operación.
- **Prueba adversarial ejecutada:**
  `tests/test_audit_g1_security.py::test_g1_1_a01_public_replay_cannot_recover_citizen_edit_token`:
  Dos clientes independientes (`c1`, `c2`); `c1` crea un reporte con PNG sin metadatos; `c2` descarga los datos de `GET /api/reports/{id}` y los bytes de `GET /api/reports/{id}/photo`, reconstruye el `POST /api/reports` y luego intenta confirmar el reporte de `c1`.
- **Resultado:**
  `PASSED` (`c2` obtiene un reporte distinto con su propio ID, no recupera el `citizen_edit_token` de `c1`, recibe `403 CONFIRMATION_UNAUTHORIZED` al intentar confirmar el reporte de `c1`, y el reporte original permanece sin confirmar).
- **Limitaciones pendientes:**
  Ninguna; la confirmación ciudadana queda vinculada exclusivamente al poseedor del token aleatorio emitido al crear el reporte (o de su `Idempotency-Key` secreta en caso de reintento de red).

---

## 3. `M-07` — Aislamiento de pruebas sin daño colateral

- **Hallazgo original (`docs/auditoria_codex_g1.md`):**
  1. `restore_db_snapshot()` ejecutaba `DELETE FROM pending_approvals WHERE NOT (id = ANY(snap))` y `DELETE FROM reports WHERE is_synthetic = FALSE AND NOT (id = ANY(snap))`, eliminando cualquier reporte o aprobación insertada concurrentemente después de tomar el snapshot inicial, y restauraba incondicionalmente `CIV-2026-DEMO0001`, sobrescribiendo cambios concurrentes (`IN_REVIEW` -> `RESOLVED`).
  2. `conftest.py` solo comprobaba `get_database_name(settings.DATABASE_URL) == "civia"` y silenciaba fallos con `except Exception: pass`, permitiendo ejecutar pruebas sobre una base no desechable con otro nombre (ej. `civia_prod_probe`).
- **Corrección aplicada:**
  1. En `backend/tests/conftest.py`, se eliminaron por completo `snapshot_db_state()` y `restore_db_snapshot()`.
  2. Se implementó aislamiento *fail-closed* para cualquier `DATABASE_URL` cuyo nombre no sea explícitamente desechable (`not is_disposable_test_or_eval_db(settings.DATABASE_URL)`), creando automáticamente una base efímera única por corrida (`civia_test_<uuid8>`) y un directorio temporal único (`civia_test_uploads_<uuid8>`), sin bloques `except Exception: pass`, y verificando `assert_disposable_test_db(settings.DATABASE_URL)` antes de correr migraciones.
  3. Mediante los hooks `set_report_created_hook` y `set_approval_created_hook`, la limpieza `cleanup_tracked_test_records()` elimina única y exclusivamente los UUIDs generados por la propia prueba (`DELETE ... WHERE id = ANY(tracked_ids)`).
  4. En `backend/tests/test_ai_and_agent.py::test_four_agent_guardrails_enforced`, se dejó de modificar `CIV-2026-DEMO0001` y se utiliza un reporte desechable propio creado dentro de la prueba.
- **Prueba adversarial ejecutada:**
  - `tests/test_audit_g1_security.py::test_g1_1_m07_concurrent_records_and_demo0001_survive_cleanup`
  - `tests/test_audit_g1_security.py::test_m07_and_n03_seed_force_reset_rejects_non_test_db`
- **Resultado:**
  `PASSED` (`civia_prod_probe` es rechazada por `assert_disposable_test_db`, y tanto el reporte centinela concurrente como la aprobación centinela concurrente y el cambio concurrente de `DEMO0001` a `IN_REVIEW` sobreviven intactos tras `cleanup_tracked_test_records()`).
- **Limitaciones pendientes:**
  Ninguna.

---

## 4. `N-03` — Limpieza segura en `eval/evaluar.py`

- **Hallazgo original (`docs/auditoria_codex_g1.md`):**
  `eval/evaluar.py` tomaba una lista `pre_existing_pa_ids` al inicio de `run_evaluation()` y al final ejecutaba `DELETE FROM pending_approvals WHERE NOT (id = ANY(pre_existing_pa_ids))`, eliminando cualquier solicitud de aprobación creada concurrentemente durante la ventana de evaluación.
- **Corrección aplicada:**
  1. En `eval/evaluar.py`, se eliminó `pre_existing_pa_ids` y el `DELETE ... WHERE NOT (id = ANY(...))`.
  2. El evaluador registra en `created_eval_pa_ids` únicamente los `approval_id` devueltos por sus propias invocaciones a `run_civia_agent()` (ej. `Q13`) y al finalizar ejecuta exclusivamente `DELETE FROM pending_approvals WHERE id = ANY(created_eval_pa_ids)`.
  3. Además, si `DATABASE_URL` no corresponde a una base desechable (`not is_disposable_test_or_eval_db`), crea una base efímera `civia_eval_<uuid8>` en modo *fail-closed* (`assert_disposable_test_db`), usa un directorio temporal `civia_eval_uploads_<uuid8>` y restaura `settings.UPLOAD_DIR` al terminar.
- **Prueba adversarial ejecutada:**
  `tests/test_audit_g1_security.py::test_g1_1_n03_evaluator_cleanup_preserves_concurrent_approvals`:
  Inserta durante la ejecución de `Q13` tanto la aprobación propia del evaluador como una aprobación concurrente ajena y verifica el estado de `pending_approvals` tras completar `run_evaluation()`.
- **Resultado:**
  `PASSED` (la aprobación propia de `Q13` es eliminada y la aprobación concurrente ajena permanece intacta en `pending_approvals`).
- **Limitaciones pendientes:**
  Ninguna.

---

## 5. `A-06` — Huella completa para conflictos de `Idempotency-Key`

- **Hallazgo original (`docs/auditoria_codex_g1.md`):**
  La huella `req_fingerprint` en `main.py` solo concatenaba `title`, `description`, `lat`, `lon`, `raw_photo_sha` y `raw_audio_sha`, omitiendo `comuna`, `neighborhood`, `address_hint` y `auto_analyze`. Reutilizar la misma `Idempotency-Key` cambiando `comuna="Comuna 99"` y `address_hint="Otra referencia"` devolvía `201` con el primer reporte en lugar de `409 IDEMPOTENCY_KEY_CONFLICT`.
- **Corrección aplicada:**
  En `backend/app/main.py`, `req_fingerprint` se calcula como el SHA-256 de un objeto JSON canónico (`json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`) que incluye todos los parámetros de la operación: `title`, `description`, `latitude`, `longitude`, `comuna`, `neighborhood`, `address_hint`, `auto_analyze`, `photo_sha256` y `audio_sha256`.
- **Prueba adversarial ejecutada:**
  `tests/test_audit_g1_security.py::test_g1_1_a06_canonical_fingerprint_detects_optional_field_and_audio_mutations`:
  Envía una solicitud inicial con `Idempotency-Key` sin `comuna` ni `address_hint` y repite con la misma `Idempotency-Key` variando (1) `comuna` + `address_hint`, (2) `neighborhood`, y (3) `auto_analyze`.
- **Resultado:**
  `PASSED` (todas las mutaciones devuelven `409 IDEMPOTENCY_KEY_CONFLICT` y el reporte original conserva `comuna = None` y `address_hint = None`).
- **Limitaciones pendientes:**
  Ninguna.

---

## 6. `A-07` — Aprobaciones obsoletas sin `expected_version`

- **Hallazgo original (`docs/auditoria_codex_g1.md`):**
  En `decide_pending_approval()`, la condición `expected_version is not None` omitía la verificación de versión cuando una fila heredada en `pending_approvals` carecía de `expected_version`. Si el reporte sufría una transición `CONFIRMED -> RESOLVED -> CONFIRMED` (ciclo ABA donde el estado vuelve a `CONFIRMED` pero `version` avanza), la propuesta heredada se aprobaba (`APPROVED`, `stale_conflict=False`) y sobrescribía el reporte a `IN_REVIEW`.
- **Corrección aplicada:**
  1. En `backend/app/agent.py` (`decide_pending_approval`), se exige obligatoriamente que `expected_status` sea un string no vacío y `expected_version` sea un entero válido `>= 1` (`isinstance(expected_version, int) and not isinstance(expected_version, bool) and expected_version >= 1`). Si falta cualquiera de los dos o no coincide con el `status` y `version` actuales de `reports` bajo `SELECT ... FOR UPDATE`, la solicitud se marca `REJECTED` con `stale_conflict = True` (`409 STALE_APPROVAL`).
  2. La sentencia `UPDATE reports` dentro de `decide_pending_approval` exige además en SQL `WHERE id = %s AND status = %s AND COALESCE(version, 1) = %s`.
  3. Se añadió la migración `backend/migrations/003_invalidate_legacy_approvals.sql` que marca como `REJECTED` cualquier fila `PENDING` heredada que no tenga `expected_version` numérico o `previous_status`, sin inventar versiones retroactivas.
- **Prueba adversarial ejecutada:**
  `tests/test_audit_g1_security.py::test_g1_1_a07_legacy_approval_without_expected_version_rejected_after_aba_cycle`:
  Inserta una propuesta `PENDING` sin `expected_version`, ejecuta el ciclo ABA `CONFIRMED -> RESOLVED -> CONFIRMED` sobre el reporte y llama a `decide_pending_approval(..., approve=True)`.
- **Resultado:**
  `PASSED` (la propuesta heredada es rechazada con `status = 'REJECTED'` y `stale_conflict = True`, y el reporte permanece en `CONFIRMED`).
- **Limitaciones pendientes:**
  Ninguna.

---

## 7. `B-03` — Escritura parcial e interrumpida de archivos

- **Hallazgo original (`docs/auditoria_codex_g1.md`):**
  En `48460b6`, `written_files.append(...)` en `main.py` se ejecutaba después de que `validate_and_store_photo()` retornaba. Cuando `Path.write_bytes` escribía 16 bytes parciales y lanzaba `OSError("synthetic partial write failure")`, la excepción se propagaba antes de registrar la ruta en `written_files`, dejando el archivo parcial de 16 bytes huérfano en `UPLOAD_DIR`.
- **Corrección aplicada:**
  En `backend/app/security.py`, se implementó `_atomic_write_bytes(target_dir, final_name, data)` utilizado tanto en `validate_and_store_photo` como en `validate_and_store_audio`:
  - Escribe primero en un archivo temporal `.tmp_<uuid>_<final_name>` dentro de `target_dir`.
  - Verifica que el archivo exista y su tamaño coincida exactamente con `len(data)`.
  - Promueve atómicamente el archivo mediante `os.replace(staging_path, final_path)`.
  - En un bloque `except BaseException:`, elimina inmediatamente tanto `staging_path` como `final_path` (`unlink(missing_ok=True)`) antes de relanzar la excepción.
- **Prueba adversarial ejecutada:**
  `tests/test_audit_g1_security.py::test_g1_1_b03_partial_file_write_oserror_leaves_zero_orphan_files`:
  Reemplaza `Path.write_bytes` con una función que abre el archivo en `UPLOAD_DIR`, escribe `data[:16]`, hace `flush()` y lanza `OSError("synthetic partial write failure")` durante `POST /api/reports`.
- **Resultado:**
  `PASSED` (`POST /api/reports` devuelve `500`, quedan `0` archivos temporales o parciales nuevos en `UPLOAD_DIR` y `0` filas nuevas en `reports`).
- **Limitaciones pendientes:**
  Ninguna.
