"""
Suite de integración determinista para el Orquestador Autónomo de CIVIA.
Verifica los 12 escenarios adversariales exigidos por la auditoría independiente de Codex:
1. Codex emite PASS y termina con código no cero: debe rechazarse.
2. Codex emite PASS sin evidencias o con tests_executed=0: debe rechazarse.
3. Codex devuelve PASS global con un FAIL individual: debe rechazarse.
4. Codex audita SHA diferente al commit freeze del desarrollador: debe rechazarse.
5. Falla creación del worktree: debe abortarse (cero fallback al repo principal).
6. Existe un archivo local no relacionado: no debe incluirse en commits (staging selectivo).
7. Falla sincronización de pruebas Docker: no deben ejecutarse pruebas sobre código anterior.
8. Simulación informa PASS: no debe modificar aprobaciones reales en state.json.
9. Estado JSON corrupto: debe detenerse con backup sin perder historial ni reiniciar silenciosamente.
10. Una CLI queda bloqueada: debe finalizar dentro de límites seguros con terminación del árbol de procesos.
11. Un proceso intenta realizar una acción prohibida: debe ser bloqueado por permisos efectivos.
12. Un fallo de pytest debe entregarse al siguiente turno de desarrollo como diagnóstico exacto.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import pytest

from orchestrator.config import OrchestratorConfig
from orchestrator.controller import OrchestratorController
from orchestrator.git_ops import (
    create_audit_worktree,
    create_checkpoint_commit,
    get_current_head,
    remove_audit_worktree,
)
from orchestrator.preflight import PreflightChecker
from orchestrator.runner import ProcessResult, run_subprocess_safe
from orchestrator.security import (
    QuotaExceededError,
    SecurityViolationError,
    StateCorruptionError,
    TestSyncError,
    WorktreeCreationError,
    get_sanitized_agent_env,
    validate_database_command,
    validate_git_command,
)
from orchestrator.simulation import SimulationDriver
from orchestrator.state import OrchestratorState


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
    # Evitar llamadas reales a APIs de red durante el preflight en pruebas unitarias
    from orchestrator.preflight import PreflightChecker
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
    assert "código de error 1" in ctrl.state.history[0]["summary"] or "exit code" in ctrl.state.history[0]["summary"].lower()


# -----------------------------------------------------------------------------
# 2. Codex emite PASS sin evidencias o con tests_executed=0: debe rechazarse
# -----------------------------------------------------------------------------
def test_2_codex_pass_without_evidence_rejected(tmp_path: Path):
    SimulationDriver.reset("AUDITOR_PASS_EMPTY_EVIDENCE")
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"
    assert "evidencias vacía" in ctrl.state.history[0]["summary"].lower() or "tests_executed" in ctrl.state.history[0]["summary"].lower()


# -----------------------------------------------------------------------------
# 3. Codex devuelve PASS global con un FAIL individual: debe rechazarse
# -----------------------------------------------------------------------------
def test_3_codex_pass_with_individual_fail_rejected(tmp_path: Path):
    SimulationDriver.reset("AUDITOR_PASS_WITH_INDIVIDUAL_FAIL")
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"
    assert "incoherencia" in ctrl.state.history[0]["summary"].lower()


# -----------------------------------------------------------------------------
# 4. Codex audita SHA diferente al commit freeze del desarrollador: debe rechazarse
# -----------------------------------------------------------------------------
def test_4_codex_audit_sha_mismatch_rejected(tmp_path: Path):
    SimulationDriver.reset("AUDITOR_SHA_MISMATCH")
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"
    assert "discrepancia de sha" in ctrl.state.history[0]["summary"].lower()


# -----------------------------------------------------------------------------
# 5. Falla creación del worktree: debe abortarse (cero fallback al repo principal)
# -----------------------------------------------------------------------------
def test_5_worktree_creation_failure_aborts(tmp_path: Path, monkeypatch):
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=False, finding="M-03")

    def mock_fail_worktree(sha, temp_dir=None):
        raise WorktreeCreationError("Simulated disk full or lock error")

    monkeypatch.setattr("orchestrator.controller.create_checkpoint_commit", lambda msg: "5b36fb55f87dc49e3256f9814cddb47e3cb3b800")
    monkeypatch.setattr("orchestrator.controller.create_audit_worktree", mock_fail_worktree)
    # Evitar llamadas reales a agy/codex en esta prueba de aborto
    ctrl.dev_runner.execute_turn = lambda f, i: ProcessResult(0, "mock dev", "", 0.1)

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "WORKTREE_CREATION_FAILED"
    assert ctrl.state.status == "WORKTREE_CREATION_FAILED"
    # Jamás se ejecutó auditoría en repo principal
    assert len(ctrl.state.history) == 0 or ctrl.state.history[-1]["auditor_status"] is None


# -----------------------------------------------------------------------------
# 6. Existe un archivo local no relacionado: no debe incluirse en commits (staging selectivo)
# -----------------------------------------------------------------------------
def test_6_unrelated_local_file_not_staged(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # Inicializar git repo en tmp_path
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@civia.local"], cwd=str(repo_dir), check=True)

    # Crear commit inicial
    (repo_dir / "backend").mkdir()
    (repo_dir / "backend" / "app").mkdir()
    init_file = repo_dir / "backend" / "app" / "main.py"
    init_file.write_text("# initial main\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo_dir), check=True)

    # Modificar archivo permitido y crear archivo no relacionado
    init_file.write_text("# modified main\n", encoding="utf-8")
    unrelated_file = repo_dir / "scratch_unrelated.txt"
    unrelated_file.write_text("temporary scratch data", encoding="utf-8")

    # Ejecutar checkpoint commit selectivo
    new_sha = create_checkpoint_commit("checkpoint test", repo_path=repo_dir)

    # Verificar que el commit SOLO contiene backend/app/main.py
    proc = subprocess.run(
        ["git", "diff", "HEAD~1", "--name-only"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    committed_files = proc.stdout.strip().splitlines()
    assert "backend/app/main.py" in committed_files
    assert "scratch_unrelated.txt" not in committed_files

    # El archivo no relacionado sigue existiendo como untracked
    status_proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "scratch_unrelated.txt" in status_proc.stdout


# -----------------------------------------------------------------------------
# 7. Falla sincronización de pruebas Docker: no deben ejecutarse pruebas sobre código anterior
# -----------------------------------------------------------------------------
def test_7_docker_test_sync_mismatch_aborts(tmp_path: Path):
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=False, finding="M-03")

    def mock_fail_sync_tests(*args, **kwargs):
        raise TestSyncError("SHA mismatch: container has stale code 5b36fb55 != current HEAD")

    ctrl.test_runner.run_tests = mock_fail_sync_tests
    ctrl.dev_runner.execute_turn = lambda f, i: ProcessResult(0, "mock dev", "", 0.1)

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "TEST_SYNC_ERROR"
    assert ctrl.state.status == "TEST_SYNC_ERROR"


# -----------------------------------------------------------------------------
# 8. Simulación informa PASS: no debe modificar aprobaciones reales en state.json
# -----------------------------------------------------------------------------
def test_8_simulation_pass_does_not_modify_real_state(tmp_path: Path):
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

    # Ejecutar simulación PASS_PASS usando archivo de estado de simulación
    config = OrchestratorConfig(simulation_mode=True)
    sim_state = OrchestratorState.load(sim_state_file, simulation_mode=True)
    ctrl = OrchestratorController(config=config, state=sim_state, single_finding_target="M-03")
    ctrl.test_runner.run_tests = lambda *args, **kwargs: ProcessResult(0, "SIM PASSED", "", 0.1)

    SimulationDriver.reset("PASS_PASS")
    res = ctrl.run(max_cycles_override=1)
    assert res["status"] == "COMPLETED"

    # Verificar que el estado REAL en disco está intacto y NO fue modificado
    loaded_real = OrchestratorState.load(real_state_file, simulation_mode=False)
    assert "M-03" in loaded_real.open_findings
    assert "M-03" not in loaded_real.closed_findings
    assert loaded_real.status == "READY"
    assert len(loaded_real.history) == 0


# -----------------------------------------------------------------------------
# 9. Estado JSON corrupto: debe detenerse con backup sin perder historial
# -----------------------------------------------------------------------------
def test_9_corrupt_json_state_halts_without_loss(tmp_path: Path):
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
# 10. Una CLI queda bloqueada: debe finalizar dentro de límites seguros
# -----------------------------------------------------------------------------
def test_10_stuck_cli_killed_within_safe_timeout():
    # Lanzar subproceso que duerme 30 segundos pero con timeout de 0.5s
    cmd = ["python", "-c", "import time; time.sleep(30)"]
    t0 = time.monotonic()
    result = run_subprocess_safe(cmd, timeout=0.5)
    elapsed = time.monotonic() - t0

    assert result.returncode == 124
    assert "TIMEOUT" in result.stderr
    assert elapsed < 5.0, f"El subproceso tardó {elapsed}s; debió terminarse en ~0.5s"


# -----------------------------------------------------------------------------
# 11. Un proceso intenta realizar una acción prohibida: debe ser bloqueado por permisos efectivos
# -----------------------------------------------------------------------------
def test_11_prohibited_action_blocked_by_effective_permissions():
    # 1. Prohibir git push
    with pytest.raises(SecurityViolationError, match="No se permite git push"):
        validate_git_command(["git", "push", "origin", "fix/auditoria-final"])

    # 2. Prohibir git merge hacia main
    with pytest.raises(SecurityViolationError, match="No se permite merge hacia main"):
        validate_git_command(["git", "merge", "main"])

    # 3. Prohibir drop de base de datos normal
    with pytest.raises(SecurityViolationError, match="Intento de ejecutar SQL destructivo"):
        validate_database_command("DROP DATABASE civia;", "civia")

    # 4. Verificar que el entorno de los agentes excluye credenciales sensibles
    sanitized_env = get_sanitized_agent_env()
    assert "ADMIN_TOKEN" not in sanitized_env
    assert "POSTGRES_PASSWORD" not in sanitized_env
    assert "DATABASE_URL" not in sanitized_env


# -----------------------------------------------------------------------------
# 12. Un fallo de pytest debe entregarse al siguiente turno de desarrollo
# -----------------------------------------------------------------------------
def test_12_pytest_failure_delivered_to_next_dev_turn(tmp_path: Path):
    ctrl = _get_isolated_controller(tmp_path, simulation_mode=True, finding="M-03")

    failure_diagnostic = "FAILED tests/test_agent.py::test_timeout - TimeoutError: deadline exceeded 0.10s"

    # En turno 1: simular fallo de test
    ctrl.test_runner.run_tests = lambda *args, **kwargs: ProcessResult(1, "", failure_diagnostic, 0.2)

    # Inyectar desarrollador que capture el prompt
    captured_prompts = []

    def mock_dev_turn(finding_id, prompt):
        captured_prompts.append(prompt)
        return ProcessResult(0, "mock fix", "", 0.1)

    ctrl.dev_runner.execute_turn = mock_dev_turn

    # Ejecutar 2 ciclos
    ctrl.run(max_cycles_override=2)

    # Turno 1 falló pruebas
    assert ctrl.state.iteration >= 2
    # El prompt para el turno 2 debe contener el diagnóstico exacto del fallo
    assert len(captured_prompts) >= 2
    turn_2_prompt = captured_prompts[1]
    assert "DIAGNÓSTICO DEL FALLO DE PRUEBAS AUTOMATIZADAS PREVIAS" in turn_2_prompt
    assert "FAILED tests/test_agent.py::test_timeout" in turn_2_prompt
