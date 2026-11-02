"""
Ejecutores de procesos para Agente Desarrollador, Agente Auditor y Suite de Pruebas.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
from typing import Any

from orchestrator.auditor_parser import parse_and_validate_audit_report
from orchestrator.config import OrchestratorConfig
from orchestrator.preflight import resolve_binary_path, WELL_KNOWN_AGY_PATHS, WELL_KNOWN_CODEX_PATHS
from orchestrator.security import (
    QuotaExceededError,
    StalledAgentError,
    redact_secrets,
    validate_git_command,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


class ProcessResult:
    def __init__(self, returncode: int, stdout: str, stderr: str, elapsed_seconds: float) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.elapsed_seconds = elapsed_seconds

    @property
    def success(self) -> bool:
        return self.returncode == 0

    @property
    def combined_output(self) -> str:
        return (self.stdout + "\n" + self.stderr).strip()


def run_subprocess_safe(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: float = 300,
    input_text: str | None = None,
) -> ProcessResult:
    """Ejecuta un subproceso con timeout estricto y sanitización de salida."""
    target_cwd = cwd or REPO_ROOT
    t0 = time.monotonic()

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(target_cwd),
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        elapsed = time.monotonic() - t0
        return ProcessResult(
            returncode=proc.returncode,
            stdout=redact_secrets(proc.stdout),
            stderr=redact_secrets(proc.stderr),
            elapsed_seconds=elapsed,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - t0
        out = redact_secrets(exc.stdout or "") if hasattr(exc, "stdout") else ""
        err = redact_secrets(exc.stderr or "") if hasattr(exc, "stderr") else ""
        return ProcessResult(
            returncode=124,
            stdout=out,
            stderr=f"TIMEOUT: El proceso superó el límite de {timeout}s.\n{err}".strip(),
            elapsed_seconds=elapsed,
        )
    except Exception as exc:
        elapsed = time.monotonic() - t0
        return ProcessResult(
            returncode=1,
            stdout="",
            stderr=f"Error inesperado ejecutando subproceso: {exc}",
            elapsed_seconds=elapsed,
        )


class DeveloperRunner:
    """Invoca a Antigravity CLI (`agy`) para implementar correcciones."""

    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config

    def execute_turn(
        self,
        finding_id: str,
        instructions: str,
        context_files: list[Path] | None = None,
    ) -> ProcessResult:
        if self.config.simulation_mode:
            from orchestrator.simulation import SimulationDriver
            return SimulationDriver.run_developer_turn(finding_id, instructions)

        binary = resolve_binary_path(self.config.agy_binary, WELL_KNOWN_AGY_PATHS)
        if not binary:
            return ProcessResult(
                returncode=1,
                stdout="",
                stderr=f"CLI de Antigravity ('{self.config.agy_binary}') no encontrado.",
                elapsed_seconds=0.0,
            )

        prompt = (
            f"# Tarea de remediación autónoma CIVIA: {finding_id}\n\n"
            f"{instructions}\n\n"
            "Reglas: Trabajar sobre una tarea, aplicar cambios con pruebas y verificar en base desechable."
        )

        cmd = [
            binary,
            "--model",
            self.config.developer_model,
            prompt,
        ]

        result = run_subprocess_safe(cmd, timeout=self.config.agent_timeout_seconds)

        # Detección de cuota
        if "quota exceeded" in result.combined_output.lower() or "429" in result.combined_output:
            raise QuotaExceededError("Antigravity CLI excedió la cuota de la API.")

        return result


class AuditorRunner:
    """Invoca a Codex CLI (`codex exec`) para auditar en un worktree aislado de solo lectura."""

    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config

    def execute_audit(
        self,
        worktree_path: Path,
        finding_id: str,
        audit_instructions: str,
        output_json_path: Path | None = None,
    ) -> tuple[dict[str, Any], ProcessResult]:
        if self.config.simulation_mode:
            from orchestrator.simulation import SimulationDriver
            report, proc_res = SimulationDriver.run_auditor_turn(finding_id, audit_instructions)
            return report, proc_res

        binary = resolve_binary_path(self.config.codex_binary, WELL_KNOWN_CODEX_PATHS)
        if not binary:
            dummy_proc = ProcessResult(
                returncode=1,
                stdout="",
                stderr=f"CLI de Codex ('{self.config.codex_binary}') no encontrado.",
                elapsed_seconds=0.0,
            )
            return {"status": "FAIL", "findings": [], "evidence": [], "summary": "Codex no disponible."}, dummy_proc

        prompt = (
            f"Audita el hallazgo {finding_id} en el repositorio congelado.\n"
            f"{audit_instructions}\n"
            "Emite estrictamente un informe JSON según las instrucciones de orchestrator/AUDITOR.md."
        )

        cmd = [
            binary,
            "exec",
            "--sandbox",
            "read-only",
            "-C",
            str(worktree_path),
            prompt,
        ]

        proc_result = run_subprocess_safe(cmd, timeout=self.config.agent_timeout_seconds)

        # Detección de cuota
        if "rate limit" in proc_result.combined_output.lower() or "quota" in proc_result.combined_output.lower():
            raise QuotaExceededError("Codex CLI reportó límite de cuota o tasa alcanzada.")

        # Intentar parsear el informe
        try:
            report = parse_and_validate_audit_report(proc_result.combined_output)
            return report, proc_result
        except Exception as exc:
            # Si falló la extracción de JSON, empaquetar como FAIL estructurado
            raw_summary = proc_result.combined_output[:300] or "Sin respuesta estructurada."
            fallback_report = {
                "status": "FAIL",
                "findings": [
                    {
                        "id": finding_id,
                        "status": "FAIL",
                        "summary": f"Error parseando JSON de auditoría: {exc}",
                        "evidence": raw_summary,
                        "blocking_issue": "Codex no devolvió un JSON estructurado válido.",
                    }
                ],
                "evidence": [raw_summary],
                "summary": f"Fallo de validación de informe: {exc}",
                "tests_executed": 0,
                "clean_tree": True,
            }
            return fallback_report, proc_result


class TestRunner:
    """Ejecuta las pruebas deterministas del backend de CIVIA."""

    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config

    def run_tests(self, target_pattern: str | None = None) -> ProcessResult:
        """
        Ejecuta pytest dentro del contenedor docker civia-api-1
        o mediante el entorno de python local si Docker no está activo.
        """
        if self.config.simulation_mode:
            return ProcessResult(0, "SIMULATED: All tests passed successfully.", "", 0.05)
        # Sincronizar archivos modificados con el contenedor si Docker está activo
        try:
            subprocess.run(
                ["docker", "cp", "backend/tests", "civia-api-1:/app/"],
                cwd=str(REPO_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ["docker", "cp", "backend/app", "civia-api-1:/app/"],
                cwd=str(REPO_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass

        cmd = ["docker", "exec", "civia-api-1", "pytest", "-v"]
        if target_pattern:
            cmd.extend(["-k", target_pattern])

        result = run_subprocess_safe(cmd, timeout=self.config.test_timeout_seconds)
        if result.returncode == 0:
            return result

        # Si Docker no está corriendo o falló la conexión al contenedor, probar pytest local
        if "no such container" in result.stderr.lower() or "docker" in result.stderr.lower():
            local_cmd = ["python", "-m", "pytest", "backend/tests", "-v"]
            if target_pattern:
                local_cmd.extend(["-k", target_pattern])
            return run_subprocess_safe(local_cmd, timeout=self.config.test_timeout_seconds)

        return result
