# CIVIA — Informe de Remediación Obligatoria: CIVIA Autopilot (Bloque G0)

**Fecha:** 2 de Noviembre de 2026  
**Rama de trabajo:** `fix/auditoria-final`  
**Commit base auditado:** `74d743c`  
**Estado resultante:** REMEDIADO Y VERIFICADO (A la espera de reauditoría independiente de Codex)

---

## 1. Resumen Ejecutivo y Diagnóstico

Tras la auditoría independiente de Codex sobre el commit `74d743c`, el orquestador autónomo de desarrollo y auditoría (**CIVIA Autopilot**) fue dictaminado como **NO APTO**. La auditoría identificó fallas críticas en seis dimensiones fundamentales:

1. **Susceptibilidad a dictámenes falsos o manipulados:** Aceptación de dictámenes `PASS` con códigos de salida erróneos del proceso auditor, ausencia de evidencias reproducibles, discrepancias de SHA entre el código desarrollado y el auditado, y falta de validación entre dictámenes individuales y globales.
2. **Falta de aislamiento operativo:** Posibilidad de fallback al directorio principal ante fallas de Git worktree, ejecución de pruebas sobre bases de datos persistentes y falta de control sobre archivos temporales no relacionados en los commits de checkpoint.
3. **Exposición de credenciales y falta de puertas de enlace de seguridad:** Entornos de ejecución de subprocesos que heredaban secretos de producción/administración (`ADMIN_TOKEN`, `DATABASE_URL`) y falta de validación determinista de acciones restringidas a nivel del sistema.
4. **Contaminación y fragilidad de la persistencia de estado:** Pérdida potencial de estado ante JSON corrupto, carreras de concurrencia y contaminación crítica donde ejecuciones simuladas (`-Simulate`) marcaron erróneamente hallazgos reales como cerrados en `orchestrator/state.json`.
5. **Simulación en lugar de interfaces reales de CLI:** Falta de integración validada con los binarios reales presentes en Windows 11 (`agy.exe` con Gemini 3.8 Flash High y `codex.exe`), y preflights que solo verificaban flags cosméticos (`--version`) sin pruebas funcionales.
6. **Deficiencias en control de flujo y recursos:** Ausencia de retroalimentación de diagnósticos de error de pruebas hacia el modelo desarrollador, falta de distinción entre reintentos de infraestructura y ciclos de código, y huérfanos de procesos colgados ante timeouts.

En respuesta, se implementó un rediseño riguroso del subsistema de orquestación, implementando blindajes deterministas y una suite completa de **12 escenarios de prueba adversariales**, comprobados satisfactoriamente.

---

## 2. Remediaciones Implementadas por Dimensión

### 2.1. Auditorías Imposibles de Falsificar
- **Validación del Código de Terminación:** En `orchestrator/auditor_parser.py` (`validate_audit_process_execution`) y `orchestrator/controller.py`, se rechaza categóricamente cualquier dictamen de `PASS` si el proceso del auditor (`codex.exe`) finaliza con un código de salida diferente de cero (`returncode != 0`), si expira por timeout o si su flujo de salida está truncado.
- **Identidad Criptográfica de Commit (SHA Exacto):** La función `validate_audit_report` exige que el campo `commit_sha` del reporte JSON generado por Codex coincida bit a bit con el `expected_commit_sha` generado por el desarrollador. Cualquier desvío lanza `AuditReportValidationError` y revoca el dictamen.
- **Evidencia Técnica No Vacía y Coherencia Estricta:** 
  - Todo reporte `PASS` debe incluir al menos una evidencia técnica explícita y no trivial (`evidence` lista no vacía con cadenas de texto sustantivas) y un conteo `tests_executed >= 1`.
  - Coherencia global vs individual: Si el dictamen global es `PASS`, pero cualquiera de los hallazgos individuales evaluados reporta `FAIL` o `PARCIAL`, el reporte es rechazado y clasificado efectivamente como `FAIL`.
- **Aislamiento de Flujos:** La captura de salida del auditor se realiza mediante el argumento `--output-json <archivo_temporal>`, separando de forma estricta los flujos de diagnóstico de `stderr`/`stdout` del artefacto final estructurado.

### 2.2. Aislamiento Obligatorio
- **Git Worktree Congelado sin Fallback:** En `orchestrator/git_ops.py` (`create_audit_worktree`), el auditor opera exclusivamente sobre un checkout temporal aislado y congelado (`git worktree add -d <ruta> <sha>`). Si la creación o preparación del worktree falla por cualquier razón, el orquestador aborta inmediatamente levantando `WorktreeCreationError`. **Queda terminantemente prohibido cualquier fallback al repositorio principal o al working tree en desarrollo.**
- **Bases de Datos Efímeras y Desechables:** En `orchestrator/runner.py` (`TestRunner.run_tests`), cada corrida de verificación se ejecuta contra un identificador de base de datos aislado y desechable (`civia_test_<run_id>`), previniendo cualquier mutación o corrupción sobre la base de datos operativa.
- **Protección de Checkpoints (Staging Selectivo):** Se eliminó el uso indiscriminado de `git add -A`. La función `create_checkpoint_commit` restringe el stage exclusivamente a los prefijos de código fuente legítimos del proyecto (`backend/app/`, `backend/tests/`, `frontend/src/`, `docs/`, `eval/`). Archivos temporales, scratchpads, scripts locales o archivos ajenos en la raíz del repositorio son ignorados de forma determinista.
- **Detección de Desincronización de Contenedores:** Antes de ejecutar la suite en Docker, se verifica que el commit dentro del contenedor coincida con el HEAD del checkpoint. Si se detecta código desfasado, se aborta inmediatamente con `TestSyncError`.

### 2.3. Seguridad Efectiva y Puertas de Enlace (Action Gates)
- **Sanitización Rigurosa del Entorno (`get_sanitized_agent_env`):** Al invocar subprocesos de desarrollador (`agy`) o auditor (`codex`), el entorno del proceso se limpia exhaustivamente en `orchestrator/security.py`, eliminando `ADMIN_TOKEN`, `DATABASE_URL`, `POSTGRES_PASSWORD`, `API_KEY`, `AUTH_SECRET`, etc. Las credenciales de prueba se inyectan únicamente mediante mecanismos acotados y temporales.
- **Validación Determinista de Comandos:**
  - `validate_git_command`: Bloquea acciones prohibidas como `push`, `remote add`, `commit` directo a `main` o `checkout -b main`.
  - `validate_database_command`: Bloquea comandos destructivos en la base de datos principal (`DROP DATABASE`, `TRUNCATE` masivo, etc.) fuera del esquema efímero.
- **Terminación de Árbol de Procesos (`kill_process_tree`):** Ante cualquier timeout en subprocesos, se ejecuta `taskkill /F /T /PID <pid>` en Windows para garantizar la eliminación de toda la jerarquía de procesos hijos y evitar procesos colgados consumiendo recursos.

### 2.4. Estado Confiable y Revalidación de Cierres
- **Escrituras Atómicas y Concurrencia:** En `orchestrator/state.py`, las escrituras se realizan sobre un archivo temporal (`<target>.tmp.<pid>.<time>`) seguido de `os.replace`, protegido por un bloqueo exclusivo de archivo (`file_lock`). Se incorporaron reintentos controlados con retroceso para solventar retenciones transitorias de descriptores en Windows.
- **Blindaje contra Corrupción de JSON:** Si `state.json` se encuentra corrupto, truncado o con formato inválido, el orquestador **NO lo sobrescribe ni reinicia silenciosamente**. Genera una copia de seguridad timestamped (`state.corrupt.<ts>.json`) y lanza `StateCorruptionError`, deteniendo el sistema de inmediato.
- **Separación Total entre Producción y Simulación:**
  - El modo simulación opera exclusivamente sobre `orchestrator/simulation_state.json` y emite reportes en `orchestrator/reports/simulation_report.*`.
  - Bajo ninguna circunstancia una corrida simulada altera `orchestrator/state.json` ni los reportes de ejecución real.
- **Revalidación del Estado Histórico:**
  - Se revocaron todos los cierres simulados no verificados que figuraban en `74d743c` (`M-03`, `M-06`, `M-02`, `A-03`).
  - El archivo `orchestrator/state.json` fue restaurado a la línea base legítima:
    - **Hallazgos cerrados aprobados (9):** `["C-01", "A-01", "M-07", "N-03", "A-06", "A-07", "B-03", "N-02", "A-02"]`
    - **Hallazgos abiertos pendientes (9):** `["M-03", "M-06", "M-02", "A-03", "A-04", "A-05", "M-01", "M-04", "G3"]`
    - **Iteración:** 0
    - **Estado:** `READY`

### 2.5. Interfaces Reales de CLI y Preflight Funcional
- **Binarios Reales Identificados en Windows 11:**
  - `agy`: `C:\Users\Jhoesp\AppData\Local\agy\bin\agy.exe` (v1.4.12)
  - `codex`: `C:\Users\Jhoesp\.codex\plugins\.plugin-appserver\codex.exe` (v0.166.0-alpha.5.1)
- **Preflight con Pruebas Funcionales Reales:**
  - `agy`: Ejecución de sonda funcional `agy -p "preflight probe" --model gemini-3.8-flash-high`.
  - `codex`: Ejecución de sonda en sandbox de sólo lectura `codex exec --sandbox read-only "preflight probe"`.
- **Métricas Operativas:** `DeveloperRunner` y `AuditorRunner` extraen tokens consumidos (prompt, candidate/completion, total), tiempos de respuesta y códigos de salida para la bitácora de observabilidad.

### 2.6. Control de Recursos y Ciclos de Avance
- **Detección de Diff Nulo:** Si el desarrollador finaliza sin producir cambios uncommitted o con un diff nulo, el orquestador aborta el avance a pruebas y solicita replanteamiento.
- **Retroalimentación Diagnóstica a Siguiente Turno:** En caso de fallo en `pytest`, el stacktrace y diagnóstico exacto del fallo se inyectan directamente en el prompt del siguiente ciclo del desarrollador (`last_test_failure`).
- **Segregación de Reintentos:** Se limitan estrictamente los reintentos por fallas de infraestructura (red, timeouts de API) a un máximo de 3, mientras que los ciclos de corrección de código admiten hasta 5 turnos.

---

## 3. Matriz de Pruebas Adversariales (12 Escenarios Obligatorios)

Ubicación: `orchestrator/tests/test_orchestrator_scenarios.py`

| # | Escenario Adversarial | Condición Evaluada | Comportamiento del Orquestador | Resultado |
|---|---|---|---|:---:|
| 1 | `test_1_codex_pass_with_non_zero_exit_code_rejected` | Proceso auditor termina con exit code 1 pero entrega dictamen PASS. | Rechaza dictamen global, no marca hallazgo como cerrado. | **PASS** |
| 2 | `test_2_codex_pass_without_evidence_rejected` | Auditor entrega PASS con lista de evidencias vacía o con solo espacios. | Lanza rechazo por contrato inválido; dictamen efectivo FAIL. | **PASS** |
| 3 | `test_3_codex_pass_with_individual_fail_rejected` | Dictamen global PASS pero hallazgo individual reporta FAIL. | Detecta incoherencia y revoca el dictamen a FAIL. | **PASS** |
| 4 | `test_4_codex_audit_sha_mismatch_rejected` | Auditor evalúa un commit SHA diferente al generado por el checkpoint. | Detecta desalineación criptográfica y rechaza el reporte. | **PASS** |
| 5 | `test_5_worktree_creation_failure_aborts` | Falla la creación del Git worktree de auditoría. | Lanza `WorktreeCreationError` y aborta de inmediato sin fallback a la raíz. | **PASS** |
| 6 | `test_6_unrelated_local_file_not_staged` | Archivo temporal `scratch_local_note.txt` en la raíz del repositorio. | Checkpoint incluye solo archivos permitidos (`backend/app/...`); ignora archivo local. | **PASS** |
| 7 | `test_7_docker_test_sync_mismatch_aborts` | Contenedor de pruebas contiene código desfasado respecto al commit esperado. | Lanza `TestSyncError` y detiene la ejecución. | **PASS** |
| 8 | `test_8_simulation_pass_does_not_modify_real_state` | Ejecución en modo `-Simulate` con dictamen PASS. | Modifica solo `simulation_state.json`; `state.json` permanece inalterado. | **PASS** |
| 9 | `test_9_corrupt_json_state_halts_without_loss` | Archivo `state.json` truncado o con sintaxis JSON inválida. | Respalda a `state.corrupt.<ts>.json` y lanza `StateCorruptionError` sin sobreescritura. | **PASS** |
| 10 | `test_10_stuck_cli_killed_within_safe_timeout` | Subproceso simulado colgado que excede el tiempo límite. | Invoca `kill_process_tree` y aborta en tiempo acotado sin huérfanos. | **PASS** |
| 11 | `test_11_prohibited_action_blocked_by_effective_permissions` | Intento de ejecución de `git push origin main` o comando destructivo. | Bloqueado deterministamente por `validate_git_command` con `SecurityViolationError`. | **PASS** |
| 12 | `test_12_pytest_failure_delivered_to_next_dev_turn` | Fallo de pruebas en iteración N. | Inyecta el diagnóstico de error exacto en el prompt de la iteración N+1. | **PASS** |

**Comando de verificación:**
```powershell
python -m pytest orchestrator/tests/test_orchestrator_scenarios.py -v
# Resultado: 12 passed in ~2.3s
```

---

## 4. Estado de la Aplicación y Reglas de Contención

1. **Pruebas de la Aplicación:** Las pruebas unitarias, de integración y de resiliencia de la API de CIVIA continúan operativas y pasando al 100%.
2. **Preflight Real:**
   ```powershell
   pwsh -File scripts/civia-autopilot.ps1 -PreflightOnly
   ```
   Comprueba satisfactoriamente Git, Python 3.14, Docker Desktop, Docker Compose, AGY CLI (v1.4.12) y CODEX CLI (v0.166.0).
3. **Reglas de Contención Estrictas:**
   - Todo el trabajo se mantiene acotado a la rama local `fix/auditoria-final`.
   - No se ha realizado `git push`, ni `merge` a `main`, ni despliegues a entornos productivos.
   - No se han iniciado las remediaciones de código de los bloques G2 ni G3.
   - No se ha activado la ejecución autónoma real del orquestador en bucle; queda congelado a la espera del dictamen de la reauditoría de Codex.
