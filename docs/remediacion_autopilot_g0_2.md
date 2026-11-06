# CIVIA — Informe de Remediación Obligatoria G0.2: Rediseño de Fronteras de Seguridad de Autopilot

**Fecha:** 2 de Noviembre de 2026  
**Rama:** `fix/auditoria-final`  
**Commit base auditado:** `8c01151`  
**Estado:** REDISEÑO COMPLETADO (Detenido para auditoría independiente de Codex; NO declarado APTO)

---

## 1. Diagnóstico y Enfoque Arquitectónico

La segunda auditoría independiente de Codex sobre `8c01151` concluyó **NO APTO**, exponiendo que validadores superficiales en Python no sustituyen fronteras de aislamiento reales a nivel de sistema operativo y Git:

1. **Invocación del desarrollador en `REPO_ROOT`:** Antigravity operaba directamente sobre la raíz del repositorio, con riesgo de contaminar el árbol de trabajo y saltarse los límites de staging.
2. **Uso de `--dangerously-skip-permissions`:** Auto-aprobaba herramientas sin restricción ni verificación de capacidades reales de sandbox en Windows.
3. **Persistencia de recursos habituales (`civia-api-1` / BD `civia`):** `TestRunner` sincronizaba y ejecutaba pruebas contra el contenedor persistente de desarrollo.
4. **Fuga en commits de checkpoint:** Si un archivo ajeno había sido agregado al índice Git previo al ciclo (`git add`), era incluido en el commit de checkpoint.
5. **Eliminación indiscriminada de directorios:** `remove_audit_worktree` borraba rutas sin comprobar si la propiedad del directorio pertenecía al orquestador.
6. **Trampa de tipos en validación de auditoría:** En Python, `isinstance(True, int) == True`, lo que permitía que dictámenes con `tests_executed: true` o evidencias vacías/genéricas superaran la validación y cerraran hallazgos indebidamente.
7. **Adquisición débil de bloqueos:** `file_lock` cedía el control (`yield`) aun cuando no se había adquirido exclusión tras el timeout.

Para resolver esto, se rediseñaron integralmente las fronteras de seguridad en 4 entregas técnicas.

---

## 2. Remediaciones Implementadas por Entrega

### Entrega 1 — Aislamiento Obligatorio

- **Checkout Independiente para Antigravity (`create_dev_worktree`):**
  - Antigravity ya **NUNCA** opera en `REPO_ROOT`.
  - Se crea un checkout efímero desacoplado en `civia_dev_worktrees/dev_<uuid>` registrado bajo la propiedad del orquestador.
  - Si se intenta ejecutar `DeveloperRunner` en `REPO_ROOT`, se lanza de inmediato `SecurityViolationError`.
- **Checkout Independiente para Codex (`create_audit_worktree`):**
  - Opera exclusivamente en un worktree temporal desacoplado y congelado en el SHA exacto de 40 caracteres (`civia_audit_worktrees/audit_<uuid>`).
- **Prohibición de `civia-api-1` y Base de Datos Habitual:**
  - `validate_no_habitual_resources`: Intercepta y bloquea cualquier intento de referenciar los contenedores `civia-api-1`, `civia-db-1`, `civia-frontend-1` o la base de datos `civia`.
  - `verify_disposable_db_url`: Valida estrictamente que la URL de base de datos comience con `postgresql://` o `postgres://` y contenga el prefijo desechable obligatorio `civia_test_`.
- **Staging mediante Índice Git Aislado (`create_checkpoint_commit`):**
  - Cada commit de checkpoint crea un archivo de índice temporal exclusivo (`GIT_INDEX_FILE = tempfile`).
  - Se ejecuta `git read-tree HEAD` hacia dicho índice y se agregan **únicamente** los archivos modificados que cumplen `is_path_allowed_for_commit`.
  - Archivos previamente staged en el índice habitual de Git quedan **físicamente excluidos**.
- **Limpieza Limitada a Directorios Registrados (`_EPHEMERAL_REGISTRY`):**
  - Se implementó un registro estricto en memoria de directorios efímeros creados (`register_ephemeral_path`, `unregister_ephemeral_path`, `is_ephemeral_path_registered`).
  - `safe_cleanup_worktree` y `safe_cleanup_ephemeral_path` verifican que la ruta esté en el registro antes de cualquier borrado.
  - Si se intenta eliminar un directorio ajeno o protegido (`REPO_ROOT`), se lanza `SecurityViolationError` y el directorio permanece intacto.

### Entrega 2 — Permisos Efectivos y Sandbox

- **Eliminación Total de `--dangerously-skip-permissions`:**
  - Eliminado de todos los ejecutores, configuraciones y comandos del orquestador.
- **Configuración de Permisos Mínimos en AGY 1.4.12:**
  - Se utilizan los parámetros `--sandbox` y `--settings` con un payload JSON que restringe `permissions.allow` estrictamente a operaciones de lectura y edición dentro del `dev_worktree` temporal (`read_file`, `write_file`, `edit_file`).
  - No se otorga permiso para `run_command(*)`.
- **Parada Segura `UNSAFE_AGENT_SANDBOX`:**
  - `check_agent_sandbox_integrity`: Evalúa si el host Windows provee aislamiento estricto a nivel de SO (ej. contenedor carcelario Docker/AppContainer).
  - Al ejecutar sobre Windows host sin jaula de contenedor activa, el orquestador se detiene de forma segura con estado:
    ```json
    {
      "status": "UNSAFE_AGENT_SANDBOX",
      "error": "El entorno de ejecución en Windows host no cuenta con aislamiento de procesos a nivel de sistema operativo... Se activa parada segura."
    }
    ```
  - **No se presume aislamiento:** Se reconoce con honestidad técnica que un proceso CLI en Windows comparte privilegios del usuario si no está enjaulado en contenedor.

### Entrega 3 — Estado y Auditoría Verificables

- **Comparación Exacta de SHA de 40 Caracteres:**
  - Se exige expresión regular `^[0-9a-fA-F]{40}$`.
  - Se rechazan comparaciones por prefijo (7 u 8 caracteres) o strings de longitud inválida.
- **Rechazo Estricto de Booleanos en `tests_executed`:**
  - Se comprueba `type(tests_executed) is int and not isinstance(tests_executed, bool) and tests_executed >= 1`.
  - La trampa de Python `isinstance(True, int) == True` queda completamente neutralizada.
- **Rechazo de Evidencias Vacías o Genéricas:**
  - Lista negra de frases prefabricadas: `"contraejemplos ejecutados con resultado limpio"`, `"dictamen pass para"`, `"sin problemas"`, `"pruebas aprobadas"`, etc.
  - Toda evidencia debe ser una cadena >= 15 caracteres con referencias verificables.
- **Comprobación Obligatoria Multifactor:**
  - Un hallazgo solo puede cerrarse si se cumplen concurrentemente todas las comprobaciones:
    1. Preflight saludable.
    2. Ejecución limpia del desarrollador en `dev_worktree`.
    3. Pruebas deterministas superadas en base desechable.
    4. Checkpoint commit generado con SHA válido de 40 caracteres.
    5. Worktree de auditoría aislado y congelado.
    6. Proceso del auditor con código de salida 0.
    7. SHA auditado coincidente con el checkpoint.
    8. Evidencias técnicas sustantivas y `tests_executed >= 1` (entero).
    9. Modo real (la simulación NUNCA cierra hallazgos reales).
- **Separación Irreversible entre SIMULATED y REAL:**
  - Un estado con `is_simulation == True` rechaza cualquier intento de guardar en `state.json` o rutas sin prefijo `simulation_`, lanzando `SecurityViolationError`.
  - El modo real no puede cargar archivos de estado de simulación.
- **Bloqueo Exclusivo Estricto (`file_lock`):**
  - Si el bloqueo no se adquiere dentro del timeout, se lanza `LockAcquisitionError`.
  - **Jamás** se ejecuta `yield` sin exclusión mutua garantizada.

---

## 3. Matriz de Pruebas Adversariales Independientes

Archivo: [`orchestrator/tests/test_orchestrator_scenarios.py`](orchestrator/tests/test_orchestrator_scenarios.py)

| # | Escenario Adversarial (Contraejemplos Codex) | Mecanismo de Defensa Validado | Resultado |
|---|---|---|:---:|
| 1 | `test_1_codex_pass_with_non_zero_exit_code_rejected` | Proceso auditor termina con exit code 1; dictamen PASS rechazado a FAIL. | **PASS** |
| 2 | `test_2_fabricated_pass_with_generic_evidence_rejected` | PASS con evidencia genérica vacía ("contraejemplos ejecutados con resultado limpio") es rechazado; M-03 no se cierra. | **PASS** |
| 3 | `test_3_fabricated_pass_with_boolean_tests_executed_rejected` | PASS con `tests_executed: true` (trampa booleana de Python) es rechazado; M-03 no se cierra. | **PASS** |
| 4 | `test_4_codex_pass_with_individual_fail_rejected` | PASS global con FAIL individual es rechazado por inconsistencia. | **PASS** |
| 5 | `test_5_exact_40_char_sha_comparison_enforced` | Desviación de SHA o prefijo truncado lanza `AuditReportValidationError`. | **PASS** |
| 6 | `test_6_worktree_creation_failure_aborts` | Falla creación de worktree; aborta con `WORKTREE_CREATION_FAILED` sin tocar repo principal. | **PASS** |
| 7 | `test_7_pre_existing_staged_file_excluded_by_isolated_index` | Archivo ajeno pre-staged en el índice Git del host es excluido del commit mediante índice temporal aislado. | **PASS** |
| 8 | `test_8_habitual_container_and_db_strictly_prohibited` | Intento de usar `civia-api-1` o base `civia` bloqueado con `SecurityViolationError`. | **PASS** |
| 9 | `test_9_unregistered_directory_cannot_be_deleted` | Intento de borrar directorio ajeno no registrado bloqueado con `SecurityViolationError`. | **PASS** |
| 10 | `test_10_permission_escape_and_unsafe_sandbox_halt` | Acceso a rutas externas o `.env` bloqueado por `validate_tool_call_target`; parada segura `UNSAFE_AGENT_SANDBOX` en host sin container jail. | **PASS** |
| 11 | `test_11_simulation_pass_does_not_modify_real_state` | Ejecución simulada deja `state.json` intacto; intento de sobreescritura cruzada bloqueado. | **PASS** |
| 12 | `test_12_file_lock_strict_acquisition_error` | Concurrencia sobre el lock lanza `LockAcquisitionError` sin ceder ejecución. | **PASS** |
| 13 | `test_13_corrupt_json_state_halts_without_loss` | JSON corrupto respaldado en `state.corrupt.<ts>.json` y detención inmediata. | **PASS** |
| 14 | `test_14_stuck_cli_killed_within_safe_timeout` | Proceso colgado terminado forzosamente con `kill_process_tree` en ~0.5s. | **PASS** |
| 15 | `test_15_pytest_failure_delivered_to_next_dev_turn` | Fallo de pytest inyectado íntegramente como contexto al siguiente turno. | **PASS** |

**Ejecución de la suite:**
```powershell
python -m pytest orchestrator/tests/test_orchestrator_scenarios.py -v
# 15 passed in 2.41s
```

---

## 4. Estado de Reglas de Contención

- **Rama:** `fix/auditoria-final`
- **Sin Push / Sin Merge:** No se ha realizado push ni merge a `main`.
- **Sin Ejecución Real:** El Autopilot real permanece **congelado y detenido**.
- **Alcance Estricto:** No se ha modificado el código de los bloques G2.1, G2.2 ni G3.
- **Dictamen:** **NO SE DECLARA AUTOPILOT APTO**. Se somete el rediseño a la evaluación y reauditoría independiente de Codex.
