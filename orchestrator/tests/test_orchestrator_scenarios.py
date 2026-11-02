"""
Suite de integración y pruebas adversariales para el Orquestador Autónomo de CIVIA.
Verifica las fronteras de seguridad y reproduce rigurosamente los contraejemplos de Codex:

1. PASS fabricado que cierra M-03 (evidencia vacía, frase genérica o booleanos como tests_executed).
2. Escape de permisos mediante comandos directos y parada segura UNSAFE_AGENT_SANDBOX.
3. Prohibición estricta del contenedor habitual civia-api-1 y base de datos habitual civia.
4. Inclusión de archivos previamente staged excluida mediante índice Git aislado.
5. Contaminación del estado real durante simulación estrictamente prevenida.
6. Directorio ajeno no registrado protegido contra eliminación accidental.
7. Comparación exacta de SHA de 40 caracteres (rechazo de discrepancias y prefijos).
8. Bloqueo de concurrencia estricto (LockAcquisitionError ante fallo de adquisición).
9. Imposibilidad de cerrar un hallazgo cuando falta una comprobación obligatoria.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import pytest

from orchestrator.auditor_parser import (
    AuditReportValidationError,
    validate_audit_report,
)
from orchestrator.config import OrchestratorConfig
from orchestrator.controller import OrchestratorController
from orchestrator.git_ops import (
    create_audit_worktree,
    create_checkpoint_commit,
    create_dev_worktree,
    get_current_head,
    remove_audit_worktree,
    remove_dev_worktree,
    safe_cleanup_worktree,
)
from orchestrator.preflight import PreflightChecker
from orchestrator.runner import ProcessResult, TestRunner, run_subprocess_safe
from orchestrator.security import (
    LockAcquisitionError,
    QuotaExceededError,
    SecurityViolationError,
    StateCorruptionError,
    TestSyncError,
    WorktreeCreationError,
    check_agent_sandbox_integrity,
    get_sanitized_agent_env,
    is_ephemeral_path_registered,
    register_ephemeral_path,
    safe_cleanup_ephemeral_path,
    unregister_ephemeral_path,
    validate_database_command,
    validate_git_command,
    validate_no_habitual_resources,
    validate_tool_call_target,
    verify_disposable_db_url,
)
from orchestrator.simulation import SimulationDriver
from orchestrator.state import OrchestratorState, file_lock


@pytest.fixture(autouse=True)
def reset_simulation():
    """Reinicia el driver de simulación antes de cada prueba."""
    SimulationDriver.reset()


def _get_isolated_controller(
    tmp_path: Path,
    simulation_mode: bool = True,
    finding: str = "M-03",
) -> OrchestratorController:
    """Construye un controlador aislado en directorio temporal para no tocar el repositorio real."""
    state_file = tmp_path / ("simulation_state.json" if simulation_mode else "state.json")
    config = OrchestratorConfig(
        simulation_mode=simulation_mode,
        max_cycles_per_finding=3,
        agent_timeout_seconds=5,
        test_timeout_seconds=5,
    )
    state = OrchestratorState(
        active_block="G2.1",
        current_finding=finding,
        iteration=0,
        status="READY",
        open_findings=[finding],
        closed_findings=["A-02"],
        is_simulation=simulation_mode,
    )
    state.save(state_file)

    ctrl = OrchestratorController(
        config=config,
        state=state,
        single_finding_target=finding,
        reports_dir=tmp_path / "reports",
    )
    # Evitar llamadas reales a docker en tests unitarios rápidos
    ctrl.test_runner.run_tests = lambda target_pattern=None, expected_commit_sha=None, disposable_db_url=None: ProcessResult(
        0, "ALL PASSED", "", 0.1
    )
    # Preflight exitoso en pruebas unitarias
    PreflightChecker.check_all = lambda self: True
    return ctrl


# -----------------------------------------------------------------------------
# 1. Codex emite PASS y termina con código no cero: debe rechazarse
# -----------------------------------------------------------------------------
def test_1_codex_pass_with_non_zero_exit_code_rejected(tmp_path: Path):
    SimulationDriver.reset("AUDITOR_PASS_NON_ZERO_EXIT")
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert "M-03" not in ctrl.state.closed_findings
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"


# -----------------------------------------------------------------------------
# 2. Contraejemplo Codex: PASS fabricado con evidencia vacía o genérica no cierra M-03
# -----------------------------------------------------------------------------
def test_2_fabricated_pass_with_generic_evidence_rejected(tmp_path: Path):
    SimulationDriver.reset("AUDITOR_PASS_EMPTY_EVIDENCE")
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    res = ctrl.run(max_cycles_override=1)

    # El dictamen es rechazado, M-03 NUNCA se cierra
    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert "M-03" not in ctrl.state.closed_findings
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"
    assert "rechazo de pass" in ctrl.state.history[0]["summary"].lower()


# -----------------------------------------------------------------------------
# 3. Contraejemplo Codex: PASS fabricado con booleanos como tests_executed (trampa bool)
# -----------------------------------------------------------------------------
def test_3_fabricated_pass_with_boolean_tests_executed_rejected(tmp_path: Path):
    SimulationDriver.reset("AUDITOR_PASS_BOOLEAN_TESTS")
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    res = ctrl.run(max_cycles_override=1)

    # tests_executed: true es rechazado categóricamente
    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert "M-03" not in ctrl.state.closed_findings
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"
    assert "entero estrictamente numérico" in ctrl.state.history[0]["summary"].lower()


# -----------------------------------------------------------------------------
# 4. Codex devuelve PASS global con un FAIL individual: debe rechazarse
# -----------------------------------------------------------------------------
def test_4_codex_pass_with_individual_fail_rejected(tmp_path: Path):
    SimulationDriver.reset("AUDITOR_PASS_WITH_INDIVIDUAL_FAIL")
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"
    assert "incoherencia" in ctrl.state.history[0]["summary"].lower()


# -----------------------------------------------------------------------------
# 5. Comparación exacta de SHA de 40 caracteres (rechazo de prefijos y no-hexadecimales)
# -----------------------------------------------------------------------------
def test_5_exact_40_char_sha_comparison_enforced(tmp_path: Path):
    SimulationDriver.reset("AUDITOR_SHA_MISMATCH")
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"
    assert "discrepancia exacta de sha" in ctrl.state.history[0]["summary"].lower()

    # Validación directa de la función de parseo
    with pytest.raises(AuditReportValidationError, match="SHA hexadecimal válido de 40 caracteres"):
        validate_audit_report(
            {"status": "PASS", "commit_sha": "5b36fb5", "findings": [], "evidence": ["test"], "tests_executed": 1},
            expected_commit_sha="5b36fb55f87dc49e3256f9814cddb47e3cb3b800",
        )


# -----------------------------------------------------------------------------
# 6. Falla creación del worktree: debe abortarse (cero fallback al repo principal)
# -----------------------------------------------------------------------------
def test_6_worktree_creation_failure_aborts(tmp_path: Path, monkeypatch):
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=False, finding="M-03")

    def mock_fail_worktree(sha, temp_dir=None):
        raise WorktreeCreationError("Simulated disk full or lock error")

    dev_dir = tmp_path / "mock_dev_worktree"
    dev_dir.mkdir()

    monkeypatch.setattr("orchestrator.controller.check_agent_sandbox_integrity", lambda: (True, "OK"))
    monkeypatch.setattr("orchestrator.controller.create_checkpoint_commit", lambda msg, repo_path=None: "5b36fb55f87dc49e3256f9814cddb47e3cb3b800")
    monkeypatch.setattr("orchestrator.controller.create_dev_worktree", lambda sha: dev_dir)
    monkeypatch.setattr("orchestrator.controller.remove_dev_worktree", lambda path: None)
    monkeypatch.setattr("orchestrator.controller.get_diff_since", lambda base, repo_path=None: "diff mock")
    monkeypatch.setattr("orchestrator.controller.get_uncommitted_changes", lambda repo_path=None: ["backend/app/main.py"])
    monkeypatch.setattr("orchestrator.controller.create_audit_worktree", mock_fail_worktree)
    ctrl.dev_runner.execute_turn = lambda f, i, dev_worktree=None: ProcessResult(0, "mock dev", "", 0.1)

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "WORKTREE_CREATION_FAILED"
    assert ctrl.state.status == "WORKTREE_CREATION_FAILED"
    # Jamás se ejecutó auditoría en repo principal
    assert len(ctrl.state.history) == 0 or ctrl.state.history[-1]["auditor_status"] is None


# -----------------------------------------------------------------------------
# 7. Contraejemplo Codex: Inclusión de archivos staged ajenos excluida mediante índice aislado
# -----------------------------------------------------------------------------
def test_7_pre_existing_staged_file_excluded_by_isolated_index(tmp_path: Path):
    repo_dir = tmp_path / "synthetic_repo"
    repo_dir.mkdir()

    # Inicializar git repo de prueba
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "tester@civia.local"], cwd=str(repo_dir), check=True)

    # Commit inicial
    app_dir = repo_dir / "backend" / "app"
    app_dir.mkdir(parents=True)
    main_file = app_dir / "main.py"
    main_file.write_text("# initial content\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "init commit"], cwd=str(repo_dir), check=True)

    # 1. Simular un archivo ajeno que fue pre-staged por un usuario antes del checkpoint
    unrelated_file = repo_dir / "unrelated_secret_note.txt"
    unrelated_file.write_text("sensible private info", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated_secret_note.txt"], cwd=str(repo_dir), check=True)

    # 2. El desarrollador modifica legítimamente el archivo de la aplicación
    main_file.write_text("# modified content by developer\n", encoding="utf-8")

    # 3. Crear commit de checkpoint usando create_checkpoint_commit con índice aislado
    new_sha = create_checkpoint_commit("fix(g2.1): update main.py", repo_path=repo_dir)

    # 4. Verificar qué archivos entraron en el commit generado
    diff_proc = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    committed_files = diff_proc.stdout.strip().splitlines()

    # El commit contiene únicamente el archivo legítimo permitido
    assert "backend/app/main.py" in committed_files
    # El archivo pre-staged ajeno NO fue incluido en el commit
    assert "unrelated_secret_note.txt" not in committed_files


# -----------------------------------------------------------------------------
# 8. Contraejemplo Codex: Prohibición estricta de contenedor habitual civia-api-1 y BD civia
# -----------------------------------------------------------------------------
def test_8_habitual_container_and_db_strictly_prohibited():
    runner = TestRunner(OrchestratorConfig(simulation_mode=False))

    # Intento de usar el contenedor habitual civia-api-1
    with pytest.raises(SecurityViolationError, match="No se permite utilizar el contenedor habitual 'civia-api-1'"):
        runner.run_tests(target_container="civia-api-1")

    # Intento de usar la base de datos habitual civia
    with pytest.raises(SecurityViolationError, match="No se permite utilizar la base de datos habitual 'civia'"):
        runner.run_tests(disposable_db_url="postgresql://civia:local_dev_change_me@localhost:5432/civia")

    # URL sin prefijo desechable
    with pytest.raises(SecurityViolationError, match="no cumple el patrón desechable obligatorio"):
        verify_disposable_db_url("postgresql://postgres:postgres@localhost:5432/production_data")

    # URL válida con prefijo desechable se acepta
    verify_disposable_db_url("postgresql://postgres:postgres@localhost:5432/civia_test_abc123")


# -----------------------------------------------------------------------------
# 9. Contraejemplo Codex: Directorio ajeno no registrado protegido contra eliminación
# -----------------------------------------------------------------------------
def test_9_unregistered_directory_cannot_be_deleted(tmp_path: Path):
    foreign_dir = tmp_path / "unregistered_external_folder"
    foreign_dir.mkdir()
    sensitive_file = foreign_dir / "critical_data.txt"
    sensitive_file.write_text("cannot be deleted", encoding="utf-8")

    # Intento de eliminar un directorio no registrado por el orquestador
    with pytest.raises(SecurityViolationError, match="Intento de eliminar directorio no registrado"):
        safe_cleanup_worktree(foreign_dir)

    with pytest.raises(SecurityViolationError, match="Intento de eliminar directorio no registrado"):
        safe_cleanup_ephemeral_path(foreign_dir)

    # El directorio y su archivo permanecen intactos
    assert foreign_dir.exists()
    assert sensitive_file.exists()


# -----------------------------------------------------------------------------
# 10. Contraejemplo Codex: Escape de permisos mediante comandos directos y parada segura
# -----------------------------------------------------------------------------
def test_10_permission_escape_and_unsafe_sandbox_halt(tmp_path: Path):
    allowed_checkout = tmp_path / "isolated_checkout"
    allowed_checkout.mkdir()

    # 1. Intento de acceder a archivo externo fuera del checkout permitido
    with pytest.raises(SecurityViolationError, match="Escape de permisos detectado"):
        validate_tool_call_target("write_file", "C:/Windows/System32/evil.dll", allowed_checkout)

    # 2. Intento de acceder a archivo de secretos (.env)
    with pytest.raises(SecurityViolationError, match="Intento de acceso a archivo restringido"):
        validate_tool_call_target("read_file", str(allowed_checkout / ".env"), allowed_checkout)

    # 3. Comprobación de integridad de sandbox en entorno Windows sin container jail
    is_safe, msg = check_agent_sandbox_integrity()
    if os.name == "nt" and os.environ.get("CIVIA_SANDBOX_CONTAINER_ACTIVE") != "true":
        assert not is_safe
        assert "UNSAFE_AGENT_SANDBOX" in msg or "no cuenta con aislamiento" in msg


# -----------------------------------------------------------------------------
# 11. Contraejemplo Codex: Separación irreversible entre estado SIMULATED y REAL
# -----------------------------------------------------------------------------
def test_11_simulation_pass_does_not_modify_real_state(tmp_path: Path):
    real_state_file = tmp_path / "state.json"
    sim_state_file = tmp_path / "simulation_state.json"

    # Estado real inicial con M-03 abierto
    real_state = OrchestratorState(
        active_block="G2.1",
        current_finding="M-03",
        iteration=0,
        status="READY",
        open_findings=["M-03"],
        closed_findings=["A-02"],
        is_simulation=False,
    )
    real_state.save(real_state_file)

    # Ejecutar simulación PASS_PASS
    config = OrchestratorConfig(simulation_mode=True)
    sim_state = OrchestratorState.load(sim_state_file, simulation_mode=True)
    ctrl = OrchestratorController(config=config, state=sim_state, single_finding_target="M-03", reports_dir=tmp_path / "reports")
    ctrl.test_runner.run_tests = lambda *args, **kwargs: ProcessResult(0, "SIM PASSED", "", 0.1)

    SimulationDriver.reset("PASS_PASS")
    res = ctrl.run(max_cycles_override=1)
    assert res["status"] == "COMPLETED"

    # Verificar que el estado REAL en disco está 100% intacto y NO fue modificado
    loaded_real = OrchestratorState.load(real_state_file, simulation_mode=False)
    assert "M-03" in loaded_real.open_findings
    assert "M-03" not in loaded_real.closed_findings
    assert loaded_real.status == "READY"
    assert len(loaded_real.history) == 0

    # Intento de guardar estado de simulación sobre el archivo de producción bloqueado
    sim_state.is_simulation = True
    with pytest.raises(SecurityViolationError, match="Contaminación de estado bloqueada"):
        sim_state.save(real_state_file)


# -----------------------------------------------------------------------------
# 12. Bloqueo de concurrencia: LockAcquisitionError estricto sin adquisición
# -----------------------------------------------------------------------------
def test_12_file_lock_strict_acquisition_error(tmp_path: Path):
    lock_file = tmp_path / "concurrency.lock"

    # Adquirir el primer lock
    with file_lock(lock_file, timeout=1.0):
        # Intentar adquirir un segundo lock sobre el mismo archivo con timeout breve
        with pytest.raises(LockAcquisitionError, match="No se pudo adquirir el bloqueo exclusivo"):
            with file_lock(lock_file, timeout=0.2):
                pass


# -----------------------------------------------------------------------------
# 13. Estado JSON corrupto: debe detenerse con backup sin perder historial
# -----------------------------------------------------------------------------
def test_13_corrupt_json_state_halts_without_loss(tmp_path: Path):
    corrupt_file = tmp_path / "state.json"
    corrupt_content = '{"active_block": "G2.1", "status": "IN_PROGRESS", "history": [{"id": 1}], INVALID_JSON...'
    corrupt_file.write_text(corrupt_content, encoding="utf-8")

    # Intentar cargar debe fallar con StateCorruptionError
    with pytest.raises(StateCorruptionError, match="JSON corrupto o inválido"):
        OrchestratorState.load(corrupt_file)

    # Verificar que se creó un archivo de respaldo con el contenido corrupto
    backups = list(tmp_path.glob("state.corrupt.*.json"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == corrupt_content


# -----------------------------------------------------------------------------
# 14. Una CLI queda bloqueada: debe finalizar dentro de límites seguros
# -----------------------------------------------------------------------------
def test_14_stuck_cli_killed_within_safe_timeout():
    cmd = ["python", "-c", "import time; time.sleep(30)"]
    t0 = time.monotonic()
    result = run_subprocess_safe(cmd, timeout=0.5)
    elapsed = time.monotonic() - t0

    assert result.returncode == 124
    assert "TIMEOUT" in result.stderr
    assert elapsed < 5.0, f"El subproceso tardó {elapsed}s; debió terminarse en ~0.5s"


# -----------------------------------------------------------------------------
# 15. Un fallo de pytest debe entregarse al siguiente turno de desarrollo
# -----------------------------------------------------------------------------
def test_15_pytest_failure_delivered_to_next_dev_turn(tmp_path: Path):
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    failure_diagnostic = "FAILED tests/test_agent.py::test_timeout - TimeoutError: deadline exceeded 0.10s"

    ctrl.test_runner.run_tests = lambda *args, **kwargs: ProcessResult(1, "", failure_diagnostic, 0.2)

    captured_prompts = []

    def mock_dev_turn(finding_id, prompt, dev_worktree=None):
        captured_prompts.append(prompt)
        return ProcessResult(0, "mock fix", "", 0.1)

    ctrl.dev_runner.execute_turn = mock_dev_turn

    ctrl.run(max_cycles_override=2)

    assert ctrl.state.iteration >= 2
    assert len(captured_prompts) >= 2
    turn_2_prompt = captured_prompts[1]
    assert "DIAGNÓSTICO DEL FALLO DE PRUEBAS AUTOMATIZADAS PREVIAS" in turn_2_prompt
    assert "FAILED tests/test_agent.py::test_timeout" in turn_2_prompt
