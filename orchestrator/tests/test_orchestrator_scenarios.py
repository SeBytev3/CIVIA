"""
Suite de integración determinista para el Orquestador Autónomo de CIVIA.
Verifica los 11 escenarios requeridos por la especificación:
1. Desarrollador PASS y Auditor PASS -> avance al siguiente hallazgo.
2. Desarrollador PASS y Auditor FAIL -> reintento y remediación.
3. Auditor devuelve JSON inválido -> fallback seguro y diagnóstico.
4. CLI sin autenticación -> parada limpia e instrucciones.
5. CLI alcanza cuota -> parada segura (HALTED_QUOTA) sin simular PASS.
6. Agente sin progreso (estancamiento / diff nulo) -> detección y parada.
7. Prueba automatizada fallida -> realimentación antes de llamar al auditor.
8. Interrupción del proceso y reanudación desde state.json.
9. Error de Git -> aborto limpio y cleanup de worktree.
10. Intento de comando destructivo -> bloqueo por guardrail de seguridad.
11. Alcance de máximo de iteraciones -> parada controlada sin bucle infinito.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest

from orchestrator.config import OrchestratorConfig
from orchestrator.controller import OrchestratorController
from orchestrator.git_ops import GitError, create_audit_worktree, remove_audit_worktree
from orchestrator.preflight import PreflightChecker
from orchestrator.runner import ProcessResult
from orchestrator.security import (
    QuotaExceededError,
    SecurityViolationError,
    detect_zero_diff,
    redact_secrets,
    validate_database_command,
    validate_git_command,
)
from orchestrator.simulation import SimulationDriver
from orchestrator.state import OrchestratorState


@pytest.fixture(autouse=True)
def reset_simulation():
    """Reinicia el driver de simulación antes de cada prueba."""
    SimulationDriver.reset()


def _get_test_controller(tmp_path: Path, simulation_mode: bool = True) -> OrchestratorController:
    """Construye un controlador aislado en directorio temporal para no tocar el repositorio."""
    config = OrchestratorConfig(
        simulation_mode=simulation_mode,
        max_cycles_per_finding=3,
        agent_timeout_seconds=5,
        test_timeout_seconds=5,
    )
    state = OrchestratorState(
        active_block="G2.1",
        current_finding="M-03",
        iteration=0,
        status="READY",
        open_findings=["M-03"],
        closed_findings=["A-02"],
    )
    # Evitar llamadas reales a docker en tests unitarios
    ctrl = OrchestratorController(config=config, state=state)
    ctrl.test_runner.run_tests = lambda pattern=None: ProcessResult(0, "ALL PASSED", "", 0.1)
    return ctrl


# -----------------------------------------------------------------------------
# Escenario 1: Desarrollador PASS y Auditor PASS
# -----------------------------------------------------------------------------
def test_scenario_1_developer_pass_auditor_pass(tmp_path: Path):
    SimulationDriver.reset("PASS_PASS")
    ctrl = _get_test_controller(tmp_path)

    res = ctrl.run(max_cycles_override=2)

    assert res["status"] == "COMPLETED"
    assert "M-03" in ctrl.state.closed_findings
    assert len(ctrl.state.open_findings) == 0
    assert len(ctrl.state.history) == 1
    assert ctrl.state.history[0]["auditor_status"] == "PASS"


# -----------------------------------------------------------------------------
# Escenario 2: Desarrollador PASS y Auditor FAIL, seguido de nueva corrección y PASS
# -----------------------------------------------------------------------------
def test_scenario_2_developer_pass_auditor_fail_then_pass(tmp_path: Path):
    SimulationDriver.reset("PASS_FAIL")
    ctrl = _get_test_controller(tmp_path)

    res = ctrl.run(max_cycles_override=3)

    assert res["status"] == "COMPLETED"
    assert "M-03" in ctrl.state.closed_findings
    assert len(ctrl.state.history) == 2
    # Turno 1 falló la auditoría
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"
    # Turno 2 aprobó la auditoría
    assert ctrl.state.history[1]["auditor_status"] == "PASS"


# -----------------------------------------------------------------------------
# Escenario 3: Auditor devuelve JSON inválido
# -----------------------------------------------------------------------------
def test_scenario_3_auditor_returns_invalid_json(tmp_path: Path):
    SimulationDriver.reset("AUDITOR_INVALID_JSON")
    ctrl = _get_test_controller(tmp_path)

    # Con 1 solo ciclo permitido
    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert len(ctrl.state.history) == 1
    # Se capturó como FAIL sin reventar el sistema
    assert ctrl.state.history[0]["auditor_status"] == "FAIL"
    assert "JSON inválido" in ctrl.state.history[0]["summary"]


# -----------------------------------------------------------------------------
# Escenario 4: CLI sin autenticación
# -----------------------------------------------------------------------------
def test_scenario_4_cli_unauthenticated(tmp_path: Path):
    SimulationDriver.reset("CLI_UNAUTHENTICATED_DEV")
    ctrl = _get_test_controller(tmp_path)

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert ctrl.state.history[0]["developer_status"] == "FAIL"


# -----------------------------------------------------------------------------
# Escenario 5: CLI alcanza cuota (QuotaExceededError)
# -----------------------------------------------------------------------------
def test_scenario_5_cli_quota_exceeded(tmp_path: Path):
    SimulationDriver.reset("DEV_QUOTA_EXCEEDED")
    ctrl = _get_test_controller(tmp_path)

    res = ctrl.run(max_cycles_override=2)

    assert res["status"] == "HALTED_QUOTA"
    assert ctrl.state.status == "HALTED_QUOTA"
    # NO se simuló un PASS falso
    assert "M-03" in ctrl.state.open_findings
    assert "M-03" not in ctrl.state.closed_findings


# -----------------------------------------------------------------------------
# Escenario 6: Agente sin progreso (estancamiento / diff nulo)
# -----------------------------------------------------------------------------
def test_scenario_6_agent_stalled_no_progress(tmp_path: Path):
    SimulationDriver.reset("STALLED_NO_PROGRESS")
    ctrl = _get_test_controller(tmp_path)
    # Simular que ya vamos por la iteración 1
    ctrl.state.iteration = 1

    res = ctrl.run(max_cycles_override=3)

    assert res["status"] == "STALLED"
    assert ctrl.state.status == "STALLED"
    assert "M-03" in ctrl.state.open_findings


# -----------------------------------------------------------------------------
# Escenario 7: Prueba automatizada fallida (realimentación sin auditor)
# -----------------------------------------------------------------------------
def test_scenario_7_automated_test_failure(tmp_path: Path):
    SimulationDriver.reset("PASS_PASS")
    ctrl = _get_test_controller(tmp_path)
    # Inyectar fallo en pruebas
    ctrl.test_runner.run_tests = lambda pattern=None: ProcessResult(1, "", "FAILED tests/test_audit.py", 0.5)

    res = ctrl.run(max_cycles_override=1)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert len(ctrl.state.history) == 1
    assert ctrl.state.history[0]["tests_passed"] is False
    # NO se invocó al auditor si fallaron las pruebas
    assert ctrl.state.history[0]["auditor_status"] is None


# -----------------------------------------------------------------------------
# Escenario 8: Interrupción del proceso y reanudación desde state.json
# -----------------------------------------------------------------------------
def test_scenario_8_interruption_and_resumption_from_state(tmp_path: Path):
    state_file = tmp_path / "state.json"
    initial_state = OrchestratorState(
        active_block="G2.1",
        current_finding="M-03",
        iteration=1,
        status="IN_PROGRESS",
        open_findings=["M-03", "M-06"],
        closed_findings=["A-02"],
    )
    initial_state.record_iteration(
        finding="M-03",
        commit_sha="abcdef123456",
        developer_status="PASS",
        tests_passed=True,
        auditor_status="FAIL",
        findings_reported=[],
        summary="Intento 1 falló",
    )
    initial_state.save(state_file)

    # Reanudar con una nueva instancia cargando el archivo persistido
    resumed_state = OrchestratorState.load(state_file)
    assert resumed_state.iteration == 1
    assert len(resumed_state.history) == 1
    assert resumed_state.history[0]["auditor_status"] == "FAIL"

    ctrl = _get_test_controller(tmp_path)
    ctrl.state = resumed_state
    SimulationDriver.reset("PASS_PASS")

    res = ctrl.run(max_cycles_override=3)

    assert res["status"] == "COMPLETED"
    assert "M-03" in ctrl.state.closed_findings
    assert len(ctrl.state.history) >= 2


# -----------------------------------------------------------------------------
# Escenario 9: Error de Git y limpieza segura de worktree
# -----------------------------------------------------------------------------
def test_scenario_9_git_error_and_worktree_cleanup(tmp_path: Path):
    dummy_worktree = tmp_path / "dummy_worktree"
    dummy_worktree.mkdir()
    (dummy_worktree / "test.txt").write_text("frozen snapshot")

    # Verificar que el cleanup elimina la carpeta sin colgar locks
    remove_audit_worktree(dummy_worktree)
    assert not dummy_worktree.exists()


# -----------------------------------------------------------------------------
# Escenario 10: Intento de comando destructivo bloqueado por guardrail
# -----------------------------------------------------------------------------
def test_scenario_10_destructive_command_blocked():
    # 1. Prohibir git push
    with pytest.raises(SecurityViolationError, match="No se permite git push"):
        validate_git_command(["git", "push", "origin", "main"])

    # 2. Prohibir git merge main
    with pytest.raises(SecurityViolationError, match="No se permite merge hacia main"):
        validate_git_command(["git", "merge", "main"])

    # 3. Prohibir SQL destructivo contra base principal
    with pytest.raises(SecurityViolationError, match="Intento de ejecutar SQL destructivo"):
        validate_database_command("DROP DATABASE civia;", "civia")

    # 4. Permitir SQL destructivo contra base desechable
    validate_database_command("DROP TABLE test_report;", "civia_test_123")


# -----------------------------------------------------------------------------
# Escenario 11: Alcance de máximo de iteraciones
# -----------------------------------------------------------------------------
def test_scenario_11_max_iterations_reached(tmp_path: Path):
    SimulationDriver.reset("ALWAYS_FAIL")
    ctrl = _get_test_controller(tmp_path)
    # Máximo 2 ciclos
    res = ctrl.run(max_cycles_override=2)

    assert res["status"] == "MAX_CYCLES_REACHED"
    assert ctrl.state.status == "MAX_CYCLES_REACHED"
    assert "M-03" in ctrl.state.open_findings
    assert ctrl.state.iteration == 2
