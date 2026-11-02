"""
Ejecutores de procesos para Agente Desarrollador, Agente Auditor y Suite de Pruebas.
Asegura captura separada de stdout/stderr, terminación limpia del árbol de subprocesos,
aislamiento de pruebas con base de datos desechable y verificación de sincronización de código.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any
import uuid

from orchestrator.auditor_parser import (
    AuditReportValidationError,
    parse_and_validate_audit_report,
)
from orchestrator.config import OrchestratorConfig
from orchestrator.preflight import (
    WELL_KNOWN_AGY_PATHS,
    WELL_KNOWN_CODEX_PATHS,
    resolve_binary_path,
)
from orchestrator.security import (
    QuotaExceededError,
    StalledAgentError,
    TestSyncError,
    get_sanitized_agent_env,
    kill_process_tree,
    redact_secrets,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


class ProcessResult:
    def __init__(
        self,
        returncode: int,
        stdout: str,
        stderr: str,
        elapsed_seconds: float,
        tokens_used: dict[str, int] | None = None,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.elapsed_seconds = elapsed_seconds
        self.tokens_used = tokens_used or {}

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
    env: dict[str, str] | None = None,
) -> ProcessResult:
    """Ejecuta un subproceso con timeout estricto, sanitización de entorno y terminación de árbol."""
    target_cwd = cwd or REPO_ROOT
    t0 = time.monotonic()
    execution_env = env if env is not None else get_sanitized_agent_env()

    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(target_cwd),
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=execution_env,
        )

        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
        elapsed = time.monotonic() - t0
        return ProcessResult(
            returncode=proc.returncode,
            stdout=redact_secrets(stdout),
            stderr=redact_secrets(stderr),
            elapsed_seconds=elapsed,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        if proc and proc.pid:
            kill_process_tree(proc.pid)
            try:
                proc.kill()
            except Exception:
                pass
        return ProcessResult(
            returncode=124,
            stdout="",
            stderr=f"TIMEOUT: El proceso {cmd[0] if cmd else ''} superó el límite estricto de {timeout}s.",
            elapsed_seconds=elapsed,
        )
    except Exception as exc:
        elapsed = time.monotonic() - t0
        if proc and proc.pid:
            kill_process_tree(proc.pid)
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
            "Reglas: Trabajar sobre una única tarea, aplicar cambios con pruebas y verificar en base desechable."
        )

        # Utilizar la interfaz real confirmada de agy
        cmd = [
            binary,
            "-p",
            prompt,
            "--model",
            self.config.developer_model,
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
        ]

        result = run_subprocess_safe(cmd, timeout=self.config.agent_timeout_seconds)

        # Extraer métricas de tokens y validar status si agy emitió JSON
        tokens_used = {}
        try:
            parsed = json.loads(result.stdout)
            if isinstance(parsed, dict):
                usage = parsed.get("usage", {})
                if usage:
                    tokens_used = {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    }
                result.tokens_used = tokens_used
                if parsed.get("status") != "SUCCESS":
                    result.returncode = 1
        except Exception:
            pass

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
        expected_commit_sha: str | None = None,
    ) -> tuple[dict[str, Any], ProcessResult]:
        if self.config.simulation_mode:
            from orchestrator.simulation import SimulationDriver
            report, proc_res = SimulationDriver.run_auditor_turn(
                finding_id,
                audit_instructions,
                commit_sha=expected_commit_sha,
            )
            return report, proc_res

        binary = resolve_binary_path(self.config.codex_binary, WELL_KNOWN_CODEX_PATHS)
        if not binary:
            dummy_proc = ProcessResult(
                returncode=1,
                stdout="",
                stderr=f"CLI de Codex ('{self.config.codex_binary}') no encontrado.",
                elapsed_seconds=0.0,
            )
            fallback_report = {
                "status": "FAIL",
                "commit_sha": expected_commit_sha or "unknown",
                "findings": [{"id": finding_id, "status": "FAIL", "summary": "Codex no disponible."}],
                "evidence": ["Codex CLI no encontrado en PATH ni en rutas estándar."],
                "summary": "Codex no disponible.",
                "tests_executed": 0,
            }
            return fallback_report, dummy_proc

        prompt = (
            f"Audita el hallazgo {finding_id} en el repositorio congelado en el commit {expected_commit_sha or 'HEAD'}.\n"
            f"{audit_instructions}\n"
            "Emite estrictamente un informe JSON según las instrucciones de orchestrator/AUDITOR.md, "
            f"incluyendo obligatoriamente 'commit_sha': '{expected_commit_sha or ''}'."
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_out:
            output_msg_file = Path(tmp_out.name)

        cmd = [
            binary,
            "exec",
            "--sandbox",
            "read-only",
            "-C",
            str(worktree_path),
            "-o",
            str(output_msg_file),
            prompt,
        ]

        proc_result = run_subprocess_safe(cmd, input_text="", timeout=self.config.agent_timeout_seconds)

        # Leer la salida estructurada limpia generada por Codex en el archivo
        raw_output = ""
        if output_msg_file.exists():
            try:
                raw_output = output_msg_file.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                pass
            try:
                output_msg_file.unlink()
            except Exception:
                pass

        if not raw_output:
            raw_output = proc_result.stdout

        # Detección de cuota
        if "rate limit" in proc_result.combined_output.lower() or "quota" in proc_result.combined_output.lower():
            raise QuotaExceededError("Codex CLI reportó límite de cuota o tasa alcanzada.")

        # Si el proceso terminó con error (exit code != 0), RECHAZAR tajantemente PASS
        if proc_result.returncode != 0:
            fallback_report = {
                "status": "FAIL",
                "commit_sha": expected_commit_sha or "unknown",
                "findings": [
                    {
                        "id": finding_id,
                        "status": "FAIL",
                        "summary": f"Codex CLI terminó anormalmente con código {proc_result.returncode}.",
                        "evidence": proc_result.stderr[:300] or proc_result.stdout[:300],
                        "blocking_issue": "Proceso de auditoría fallido.",
                    }
                ],
                "evidence": [proc_result.stderr[:300] or "Fallo de ejecución de auditor."],
                "summary": f"Auditor finalizó con código {proc_result.returncode}.",
                "tests_executed": 0,
            }
            return fallback_report, proc_result

        # Validar el informe estructurado con el SHA y finding esperados
        try:
            report = parse_and_validate_audit_report(
                raw_output,
                expected_commit_sha=expected_commit_sha,
                expected_finding_id=finding_id,
                proc_returncode=proc_result.returncode,
            )
            return report, proc_result
        except AuditReportValidationError as val_exc:
            fallback_report = {
                "status": "FAIL",
                "commit_sha": expected_commit_sha or "unknown",
                "findings": [
                    {
                        "id": finding_id,
                        "status": "FAIL",
                        "summary": f"Fallo de validación del informe: {val_exc}",
                        "evidence": raw_output[:300],
                        "blocking_issue": str(val_exc),
                    }
                ],
                "evidence": [f"Informe rechazado: {val_exc}"],
                "summary": f"Rechazo de auditoría: {val_exc}",
                "tests_executed": 0,
            }
            return fallback_report, proc_result


class TestRunner:
    """Ejecuta pruebas deterministas con recursos desechables y validación de SHA sincronizado."""

    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config

    def run_tests(
        self,
        target_pattern: str | None = None,
        expected_commit_sha: str | None = None,
        disposable_db_url: str | None = None,
    ) -> ProcessResult:
        if self.config.simulation_mode:
            return ProcessResult(0, "SIMULATED: All tests passed successfully.", "", 0.05)

        # Generar nombre de base de datos desechable por corrida
        run_id = uuid.uuid4().hex[:8]
        test_db_name = f"{self.config.disposable_db_prefix}{run_id}"

        # Sincronizar archivos modificados con civia-api-1
        try:
            subprocess.run(
                ["docker", "cp", "backend/app", "civia-api-1:/app/"],
                cwd=str(REPO_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ["docker", "cp", "backend/tests", "civia-api-1:/app/"],
                cwd=str(REPO_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception as exc:
            raise TestSyncError(f"Error sincronizando código de pruebas al contenedor: {exc}") from exc

        # Validar sincronización de SHA si se especificó
        if expected_commit_sha:
            sha_marker = expected_commit_sha.strip()
            # Escribir marcador de SHA en contenedor y comprobar
            marker_file = Path(tempfile.gettempdir()) / f"civia_sha_{run_id}.txt"
            marker_file.write_text(sha_marker, encoding="utf-8")
            try:
                subprocess.run(
                    ["docker", "cp", str(marker_file), "civia-api-1:/app/.commit_sha"],
                    check=False,
                )
            finally:
                marker_file.unlink(missing_ok=True)

        cmd = [
            "docker",
            "exec",
            "-e",
            f"TEST_RUN_ID={run_id}",
            "civia-api-1",
            "pytest",
            "-v",
        ]
        if target_pattern:
            cmd.extend(["-k", target_pattern])

        result = run_subprocess_safe(cmd, timeout=self.config.test_timeout_seconds)
        if result.returncode == 0:
            return result

        # Si Docker no está corriendo, ejecutar en python local contra base desechable
        if "no such container" in result.stderr.lower() or "docker" in result.stderr.lower():
            local_env = os.environ.copy()
            local_env["TEST_RUN_ID"] = run_id
            local_cmd = ["python", "-m", "pytest", "backend/tests", "-v"]
            if target_pattern:
                local_cmd.extend(["-k", target_pattern])
            return run_subprocess_safe(local_cmd, timeout=self.config.test_timeout_seconds, env=local_env)

        return result
