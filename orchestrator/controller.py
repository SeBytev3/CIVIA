"""
Controlador principal de la máquina de estados del orquestador autónomo CIVIA.
Coordina el ciclo: Contexto -> Desarrollador (agy) -> Pruebas -> Checkpoint -> Auditor (Codex) -> Evaluación.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

from orchestrator.config import OrchestratorConfig, REPO_ROOT
from orchestrator.git_ops import (
    create_audit_worktree,
    create_checkpoint_commit,
    get_current_branch,
    get_current_head,
    get_diff_since,
    remove_audit_worktree,
)
from orchestrator.preflight import PreflightChecker
from orchestrator.runner import AuditorRunner, DeveloperRunner, ProcessResult, TestRunner
from orchestrator.security import (
    MaxIterationsError,
    QuotaExceededError,
    SecurityViolationError,
    StalledAgentError,
    detect_zero_diff,
    redact_secrets,
)
from orchestrator.state import OrchestratorState


REPORTS_DIR = REPO_ROOT / "orchestrator" / "reports"


class OrchestratorController:
    """Motor de orquestación autónomo para CIVIA."""

    def __init__(self, config: OrchestratorConfig | None = None, state: OrchestratorState | None = None) -> None:
        self.config = config or OrchestratorConfig.load()
        self.state = state or OrchestratorState.load()
        self.dev_runner = DeveloperRunner(self.config)
        self.auditor_runner = AuditorRunner(self.config)
        self.test_runner = TestRunner(self.config)

    def run(self, max_cycles_override: int | None = None) -> dict[str, Any]:
        """Ejecuta el ciclo autónomo de desarrollo y auditoría."""
        print("\n[CIVIA-AUTOPILOT] Iniciando orquestador autónomo...")
        max_cycles = max_cycles_override or self.config.max_cycles_per_finding

        # 1. Preflight
        preflight = PreflightChecker(self.config)
        if not preflight.check_all():
            preflight.print_diagnostics_report()
            print("[CIVIA-AUTOPILOT] [ALERTA] Preflight no superado. Deteniendo ejecución de forma segura.")
            self.state.status = "PREFLIGHT_FAILED"
            self.state.save()
            self._generate_reports("Preflight fallido. Revise los requisitos del sistema.")
            return {"status": "PREFLIGHT_FAILED", "diagnostics": preflight.diagnostics}

        preflight.print_diagnostics_report()

        # 2. Bucle principal sobre los hallazgos abiertos
        while self.state.open_findings:
            finding = self.state.current_finding
            print(f"\n" + "=" * 60)
            print(f"[CIVIA-AUTOPILOT] Bloque: {self.state.active_block} | Hallazgo activo: {finding}")
            print(f"[CIVIA-AUTOPILOT] Iteración: {self.state.iteration + 1} de {max_cycles}")
            print("=" * 60)

            # Verificar límite de ciclos
            if self.state.iteration >= max_cycles:
                msg = f"Se alcanzó el límite máximo de {max_cycles} ciclos para el hallazgo '{finding}'."
                print(f"[CIVIA-AUTOPILOT] [ERROR] {msg}")
                self.state.status = "MAX_CYCLES_REACHED"
                self.state.save()
                self._generate_reports(msg)
                return {"status": "MAX_CYCLES_REACHED", "finding": finding, "iteration": self.state.iteration}

            self.state.iteration += 1
            self.state.status = "IN_PROGRESS"
            self.state.save()

            # A. Preparar instrucciones para el Agente Desarrollador
            dev_instructions = self._build_developer_prompt(finding)

            # B. Invocación del Agente Desarrollador
            print(f"[CIVIA-AUTOPILOT] Invocando desarrollador para {finding}...")
            try:
                dev_result = self.dev_runner.execute_turn(finding, dev_instructions)
            except QuotaExceededError as q_err:
                msg = f"Cuota excedida durante invocación de desarrollador: {q_err}"
                print(f"[CIVIA-AUTOPILOT] [PAUSA] {msg}")
                self.state.status = "HALTED_QUOTA"
                self.state.save()
                self._generate_reports(msg)
                return {"status": "HALTED_QUOTA", "error": str(q_err)}

            if not dev_result.success:
                msg = f"Desarrollador falló con código {dev_result.returncode}: {dev_result.stderr}"
                print(f"[CIVIA-AUTOPILOT] {msg}")
                # Registrar y reintentar si queda presupuesto
                self.state.record_iteration(
                    finding=finding,
                    commit_sha=self.state.current_commit,
                    developer_status="FAIL",
                    tests_passed=False,
                    auditor_status=None,
                    findings_reported=[],
                    summary=msg,
                )
                self.state.save()
                continue

            # C. Detección de estancamiento (diff nulo)
            if self.config.simulation_mode:
                from orchestrator.simulation import SimulationDriver
                diff = SimulationDriver.injected_diff
            else:
                diff = get_diff_since(self.config.base_commit)

            if detect_zero_diff(diff) and self.state.iteration > 1:
                msg = f"Detección de estancamiento: el agente no introdujo ningún diff en iteración {self.state.iteration}."
                print(f"[CIVIA-AUTOPILOT] [STALL] {msg}")
                self.state.status = "STALLED"
                self.state.save()
                self._generate_reports(msg)
                return {"status": "STALLED", "finding": finding}

            # D. Ejecutar pruebas automatizadas deterministas
            print("[CIVIA-AUTOPILOT] Ejecutando pruebas deterministas...")
            if self.config.simulation_mode and getattr(self, "_simulate_test_failure", False):
                test_result = ProcessResult(1, "", "FAILED tests/test_audit.py::test_remediation", 1.0)
            else:
                test_result = self.test_runner.run_tests()

            if not test_result.success:
                print(f"[CIVIA-AUTOPILOT] [TEST FAIL] Las pruebas automáticas fallaron. Realimentando al desarrollador...")
                self.state.record_iteration(
                    finding=finding,
                    commit_sha=self.state.current_commit,
                    developer_status="PASS",
                    tests_passed=False,
                    auditor_status=None,
                    findings_reported=[],
                    summary=f"Pruebas fallidas en iteración {self.state.iteration}.",
                )
                self.state.save()
                continue

            print("[CIVIA-AUTOPILOT] [TEST PASS] Pruebas automatizadas aprobadas.")

            # E. Checkpoint commit
            commit_msg = f"fix({self.state.active_block.lower()}): remediate {finding} (autopilot cycle {self.state.iteration})"
            if not self.config.simulation_mode:
                new_sha = create_checkpoint_commit(commit_msg)
                self.state.current_commit = new_sha
            else:
                new_sha = self.state.current_commit

            print(f"[CIVIA-AUTOPILOT] Checkpoint commit generado: {new_sha[:8]}")

            # F. Creación de Git worktree congelado para auditoría
            worktree_dir = None
            if not self.config.simulation_mode:
                try:
                    worktree_dir = create_audit_worktree(new_sha)
                    print(f"[CIVIA-AUTOPILOT] Worktree de auditoría aislado en: {worktree_dir}")
                except Exception as w_exc:
                    print(f"[CIVIA-AUTOPILOT] Error creando worktree: {w_exc}")
                    worktree_dir = REPO_ROOT

            # G. Invocación de Codex CLI (Auditor)
            print(f"[CIVIA-AUTOPILOT] Invocando auditor independiente para {finding}...")
            try:
                audit_instructions = self._build_auditor_prompt(finding)
                audit_report, audit_proc = self.auditor_runner.execute_audit(
                    worktree_path=worktree_dir or REPO_ROOT,
                    finding_id=finding,
                    audit_instructions=audit_instructions,
                )
            except QuotaExceededError as q_err:
                msg = f"Cuota de Codex excedida: {q_err}"
                print(f"[CIVIA-AUTOPILOT] [PAUSA] {msg}")
                self.state.status = "HALTED_QUOTA"
                self.state.save()
                self._generate_reports(msg)
                if worktree_dir and worktree_dir != REPO_ROOT:
                    remove_audit_worktree(worktree_dir)
                return {"status": "HALTED_QUOTA", "error": str(q_err)}
            finally:
                if worktree_dir and worktree_dir != REPO_ROOT:
                    remove_audit_worktree(worktree_dir)

            # H. Procesar dictamen del Auditor
            audit_status = audit_report.get("status", "FAIL")
            self.state.last_audit_report = audit_report
            print(f"[CIVIA-AUTOPILOT] Dictamen de auditoría: [{audit_status}]")

            self.state.record_iteration(
                finding=finding,
                commit_sha=new_sha,
                developer_status="PASS",
                tests_passed=True,
                auditor_status=audit_status,
                findings_reported=audit_report.get("findings", []),
                summary=audit_report.get("summary", ""),
            )
            self.state.save()

            if audit_status == "PASS":
                print(f"[CIVIA-AUTOPILOT] [ÉXITO] Hallazgo '{finding}' verificado y APROBADO por auditoría.")
                self.state.mark_finding_closed(finding)
                self.state.save()
            else:
                print(f"[CIVIA-AUTOPILOT] [REINTENTO] Auditoría dictaminó {audit_status}. Reintentando corrección...")

        # Fin del ciclo
        print("\n[CIVIA-AUTOPILOT] ¡Todos los hallazgos abiertos han sido completados con éxito!")
        self.state.status = "COMPLETED"
        self.state.save()
        self._generate_reports("Ejecución completada satisfactoriamente.")
        return {"status": "COMPLETED", "closed_findings": self.state.closed_findings}

    def _build_developer_prompt(self, finding: str) -> str:
        prompt = (
            f"Remediar el hallazgo: {finding} en CIVIA.\n"
            f"Consulte orchestrator/PROJECT_SPEC.md y orchestrator/ACCEPTANCE.md.\n"
        )
        if self.state.last_audit_report:
            prompt += f"\nÚltimo reporte de auditoría:\n{json.dumps(self.state.last_audit_report, indent=2)}\n"
        return prompt

    def _build_auditor_prompt(self, finding: str) -> str:
        return (
            f"Auditar de forma adversarial el hallazgo {finding} según orchestrator/ACCEPTANCE.md.\n"
            "Verifique contraejemplos técnicos y emita el dictamen en formato JSON estructurado."
        )

    def _generate_reports(self, summary_msg: str) -> None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        # Markdown report
        md_path = REPORTS_DIR / "execution_report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# CIVIA — Reporte de Ejecución del Orquestador Autónomo\n\n")
            f.write(f"- **Fecha:** {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"- **Estado final:** `{self.state.status}`\n")
            f.write(f"- **Bloque activo:** `{self.state.active_block}`\n")
            f.write(f"- **Commit actual:** `{self.state.current_commit[:8]}`\n")
            f.write(f"- **Resumen:** {summary_msg}\n\n")
            f.write("## Hallazgos cerrados\n")
            for h in self.state.closed_findings:
                f.write(f"- [x] {h}\n")
            f.write("\n## Hallazgos pendientes\n")
            for h in self.state.open_findings:
                f.write(f"- [ ] {h}\n")
            f.write("\n## Historial de Iteraciones\n")
            f.write("| Iteración | Hallazgo | Commit | Dev | Tests | Auditor | Resumen |\n")
            f.write("|---|---|---|---|---|---|---|\n")
            for item in self.state.history:
                f.write(
                    f"| {item.get('iteration')} | {item.get('finding')} | {item.get('commit_sha')[:7]} "
                    f"| {item.get('developer_status')} | {item.get('tests_passed')} | {item.get('auditor_status')} "
                    f"| {item.get('summary')[:40]} |\n"
                )

        # JSON report
        json_path = REPORTS_DIR / "execution_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            report_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": self.state.status,
                "active_block": self.state.active_block,
                "current_commit": self.state.current_commit,
                "summary": summary_msg,
                "closed_findings": self.state.closed_findings,
                "open_findings": self.state.open_findings,
                "history": self.state.history,
            }
            json.dump(report_data, f, indent=2, ensure_ascii=False)
