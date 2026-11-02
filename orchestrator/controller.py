"""
Controlador principal de la máquina de estados del orquestador autónomo CIVIA.
Coordina el ciclo: Contexto -> Desarrollador (agy) -> Pruebas -> Checkpoint -> Auditor (Codex) -> Evaluación.
Asegura aislamiento estricto, auditorías imposibles de falsificar, diagnóstico de fallos
y separación absoluta de simulaciones.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

from orchestrator.auditor_parser import (
    AuditReportValidationError,
    validate_audit_report,
)
from orchestrator.config import OrchestratorConfig, REPO_ROOT
from orchestrator.git_ops import (
    create_audit_worktree,
    create_checkpoint_commit,
    get_current_branch,
    get_current_head,
    get_diff_since,
    get_uncommitted_changes,
    remove_audit_worktree,
)
from orchestrator.preflight import PreflightChecker
from orchestrator.runner import AuditorRunner, DeveloperRunner, ProcessResult, TestRunner
from orchestrator.security import (
    MaxIterationsError,
    QuotaExceededError,
    SecurityViolationError,
    StalledAgentError,
    TestSyncError,
    WorktreeCreationError,
    detect_zero_diff,
    redact_secrets,
)
from orchestrator.state import OrchestratorState


REPORTS_DIR = REPO_ROOT / "orchestrator" / "reports"


class OrchestratorController:
    """Motor de orquestación autónomo para CIVIA."""

    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        state: OrchestratorState | None = None,
        single_finding_target: str | None = None,
        reports_dir: Path | None = None,
    ) -> None:
        self.config = config or OrchestratorConfig.load()
        self.state = state or OrchestratorState.load(simulation_mode=self.config.simulation_mode)
        self.single_finding_target = single_finding_target
        self.reports_dir = reports_dir or REPORTS_DIR
        self.dev_runner = DeveloperRunner(self.config)
        self.auditor_runner = AuditorRunner(self.config)
        self.test_runner = TestRunner(self.config)
        self.last_test_failure: str | None = None

    def run(self, max_cycles_override: int | None = None) -> dict[str, Any]:
        """Ejecuta el ciclo autónomo de desarrollo y auditoría."""
        mode_label = "SIMULACIÓN" if self.config.simulation_mode else "REAL"
        print(f"\n[CIVIA-AUTOPILOT] Iniciando orquestador autónomo en modo [{mode_label}]...")
        max_cycles = max_cycles_override or self.config.max_cycles_per_finding
        max_infra_retries = self.config.max_infrastructure_retries

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

        # Si se especificó un hallazgo objetivo exclusivo, enfocar la lista en él
        if self.single_finding_target:
            target = self.single_finding_target.strip()
            self.state.current_finding = target
            if target not in self.state.open_findings:
                self.state.open_findings.insert(0, target)

        infra_retry_count = 0

        # 2. Bucle principal sobre los hallazgos abiertos
        while self.state.open_findings:
            finding = self.state.current_finding
            print(f"\n" + "=" * 60)
            print(f"[CIVIA-AUTOPILOT] Bloque: {self.state.active_block} | Hallazgo activo: {finding}")
            print(f"[CIVIA-AUTOPILOT] Iteración de corrección: {self.state.iteration + 1} de {max_cycles}")
            print("=" * 60)

            # Verificar límite de ciclos de corrección
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

            # A. Preparar instrucciones para el Agente Desarrollador (inyectando fallo de test si existe)
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
                self.state.record_iteration(
                    finding=finding,
                    commit_sha_developer=self.state.current_commit,
                    commit_sha_audited=self.state.current_commit,
                    developer_status="FAIL",
                    tests_passed=False,
                    auditor_status=None,
                    findings_reported=[],
                    summary=msg,
                    audit_exit_code=dev_result.returncode,
                    tokens_used=dev_result.tokens_used,
                )
                self.state.save()
                continue

            # C. Detección de estancamiento (diff nulo y sin cambios no confirmados)
            if self.config.simulation_mode:
                from orchestrator.simulation import SimulationDriver
                diff = SimulationDriver.injected_diff
            else:
                diff = get_diff_since(self.config.base_commit)
                uncommitted = get_uncommitted_changes()
                if not uncommitted and detect_zero_diff(diff) and self.state.iteration > 1:
                    msg = f"Detección de estancamiento: el agente no introdujo ningún diff ni cambios en iteración {self.state.iteration}."
                    print(f"[CIVIA-AUTOPILOT] [STALL] {msg}")
                    self.state.status = "STALLED"
                    self.state.save()
                    self._generate_reports(msg)
                    return {"status": "STALLED", "finding": finding}

            # D. Ejecutar pruebas automatizadas deterministas
            print("[CIVIA-AUTOPILOT] Ejecutando pruebas deterministas sobre recurso de prueba...")
            try:
                if self.config.simulation_mode and getattr(self, "_simulate_test_failure", False):
                    test_result = ProcessResult(1, "", "FAILED tests/test_audit.py::test_remediation", 1.0)
                else:
                    test_result = self.test_runner.run_tests(expected_commit_sha=self.state.current_commit)
            except TestSyncError as sync_exc:
                msg = f"Error crítico de sincronización de pruebas: {sync_exc}"
                print(f"[CIVIA-AUTOPILOT] [ERROR] {msg}")
                self.state.status = "TEST_SYNC_ERROR"
                self.state.save()
                self._generate_reports(msg)
                return {"status": "TEST_SYNC_ERROR", "error": str(sync_exc)}

            if not test_result.success:
                print("[CIVIA-AUTOPILOT] [TEST FAIL] Las pruebas fallaron. Entregando diagnóstico al desarrollador para siguiente turno...")
                # Capturar diagnóstico de fallo para inyectarlo en el siguiente turno
                self.last_test_failure = test_result.combined_output[:1200]
                self.state.record_iteration(
                    finding=finding,
                    commit_sha_developer=self.state.current_commit,
                    commit_sha_audited=self.state.current_commit,
                    developer_status="PASS",
                    tests_passed=False,
                    auditor_status=None,
                    findings_reported=[],
                    summary=f"Pruebas fallidas en iteración {self.state.iteration}.",
                    tokens_used=dev_result.tokens_used,
                )
                self.state.save()
                continue

            # Pruebas superadas: limpiar último diagnóstico de fallo
            self.last_test_failure = None
            print("[CIVIA-AUTOPILOT] [TEST PASS] Pruebas automatizadas aprobadas.")

            # E. Checkpoint commit selectivo
            commit_msg = f"fix({self.state.active_block.lower()}): remediate {finding} (autopilot cycle {self.state.iteration})"
            if not self.config.simulation_mode:
                new_sha = create_checkpoint_commit(commit_msg)
                self.state.current_commit = new_sha
            else:
                new_sha = self.state.current_commit

            print(f"[CIVIA-AUTOPILOT] Checkpoint commit generado: {new_sha[:8]}")

            # F. Creación de Git worktree congelado para auditoría (ABORTAR ante fallo, CERO fallback a repo principal)
            worktree_dir = None
            if not self.config.simulation_mode:
                try:
                    worktree_dir = create_audit_worktree(new_sha)
                    print(f"[CIVIA-AUTOPILOT] Worktree de auditoría aislado congelado en: {worktree_dir}")
                except Exception as w_exc:
                    msg = f"Fallo crítico al crear worktree de auditoría para commit {new_sha}: {w_exc}. Abortando sin fallback al repositorio principal."
                    print(f"[CIVIA-AUTOPILOT] [ABORT] {msg}")
                    self.state.status = "WORKTREE_CREATION_FAILED"
                    self.state.save()
                    self._generate_reports(msg)
                    return {"status": "WORKTREE_CREATION_FAILED", "error": msg}

            # G. Invocación de Codex CLI (Auditor) en el worktree congelado
            print(f"[CIVIA-AUTOPILOT] Invocando auditor independiente para {finding} en commit {new_sha[:8]}...")
            try:
                audit_instructions = self._build_auditor_prompt(finding)
                audit_report, audit_proc = self.auditor_runner.execute_audit(
                    worktree_path=worktree_dir or REPO_ROOT,
                    finding_id=finding,
                    audit_instructions=audit_instructions,
                    expected_commit_sha=new_sha,
                )
            except QuotaExceededError as q_err:
                msg = f"Cuota de Codex excedida: {q_err}"
                print(f"[CIVIA-AUTOPILOT] [PAUSA] {msg}")
                self.state.status = "HALTED_QUOTA"
                self.state.save()
                self._generate_reports(msg)
                if worktree_dir:
                    remove_audit_worktree(worktree_dir)
                return {"status": "HALTED_QUOTA", "error": str(q_err)}
            finally:
                if worktree_dir:
                    remove_audit_worktree(worktree_dir)

            # H. Validación rigurosa del dictamen del Auditor
            # Comprobar código de salida: si exit code != 0, jamás aceptar PASS
            if audit_proc.returncode != 0 and audit_report.get("status") == "PASS":
                print(f"[CIVIA-AUTOPILOT] [RECHAZO] Codex reportó exit code {audit_proc.returncode} != 0. Rechazando PASS.")
                audit_report["status"] = "FAIL"
                audit_report["summary"] = f"Rechazado: proceso de auditoría terminó con código de error {audit_proc.returncode}."

            audit_status = audit_report.get("status", "FAIL")

            # Validación de integridad de dictamen PASS
            if audit_status == "PASS":
                try:
                    validate_audit_report(
                        audit_report,
                        expected_commit_sha=new_sha,
                        expected_finding_id=finding,
                    )
                except AuditReportValidationError as val_err:
                    print(f"[CIVIA-AUTOPILOT] [RECHAZO] Dictamen PASS inválido según contrato de auditoría: {val_err}")
                    audit_status = "FAIL"
                    audit_report["status"] = "FAIL"
                    audit_report["summary"] = f"Falsificación o inconsistencia rechazada: {val_err}"

            self.state.last_audit_report = audit_report
            print(f"[CIVIA-AUTOPILOT] Dictamen efectivo de auditoría: [{audit_status}]")

            # Combinar tokens reportados
            combined_tokens = dev_result.tokens_used.copy()
            for k, v in audit_proc.tokens_used.items():
                combined_tokens[f"auditor_{k}"] = v

            self.state.record_iteration(
                finding=finding,
                commit_sha_developer=new_sha,
                commit_sha_audited=audit_report.get("commit_sha", new_sha),
                developer_status="PASS",
                tests_passed=True,
                auditor_status=audit_status,
                findings_reported=audit_report.get("findings", []),
                summary=audit_report.get("summary", ""),
                audit_exit_code=audit_proc.returncode,
                tokens_used=combined_tokens,
            )
            self.state.save()

            if audit_status == "PASS":
                print(f"[CIVIA-AUTOPILOT] [ÉXITO] Hallazgo '{finding}' verificado y APROBADO por auditoría.")
                self.state.mark_finding_closed(finding)
                self.state.save()
                if self.single_finding_target:
                    print(f"[CIVIA-AUTOPILOT] Finalizando ejecución tras completar el hallazgo objetivo '{finding}'.")
                    break
            else:
                print(f"[CIVIA-AUTOPILOT] [REINTENTO] Auditoría dictaminó {audit_status}. Reintentando corrección...")

        # Fin del ciclo
        if not self.state.open_findings or (self.single_finding_target and self.single_finding_target in self.state.closed_findings):
            print("\n[CIVIA-AUTOPILOT] ¡Ejecución de hallazgos finalizada satisfactoriamente!")
            self.state.status = "COMPLETED"
            self.state.save()
            self._generate_reports("Ejecución completada satisfactoriamente.")
            return {"status": "COMPLETED", "closed_findings": self.state.closed_findings}

        self._generate_reports("Ejecución finalizada con hallazgos pendientes.")
        return {"status": self.state.status, "open_findings": self.state.open_findings}

    def _build_developer_prompt(self, finding: str) -> str:
        prompt = (
            f"Remediar el hallazgo: {finding} en CIVIA.\n"
            f"Consulte orchestrator/PROJECT_SPEC.md y orchestrator/ACCEPTANCE.md.\n"
        )
        if self.last_test_failure:
            prompt += f"\nDIAGNÓSTICO DEL FALLO DE PRUEBAS AUTOMATIZADAS PREVIAS:\n{self.last_test_failure}\n"

        if self.state.last_audit_report:
            prompt += f"\nÚltimo reporte de auditoría:\n{json.dumps(self.state.last_audit_report, indent=2)}\n"
        return prompt

    def _build_auditor_prompt(self, finding: str) -> str:
        return (
            f"Auditar de forma adversarial el hallazgo {finding} según orchestrator/ACCEPTANCE.md.\n"
            "Verifique contraejemplos técnicos en PostgreSQL 17 desechable y emita el dictamen en formato JSON estructurado.\n"
            "Debe incluir 'commit_sha' exacto, lista no vacía de 'evidence' reproducible y 'tests_executed' >= 1."
        )

    def _generate_reports(self, summary_msg: str) -> None:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        prefix = "simulation_" if self.config.simulation_mode else "execution_"

        # Markdown report
        md_path = self.reports_dir / f"{prefix}report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            mode_tag = "SIMULACIÓN" if self.config.simulation_mode else "PRODUCCIÓN / REAL"
            f.write(f"# CIVIA — Reporte de Ejecución del Orquestador Autónomo ({mode_tag})\n\n")
            f.write(f"- **Fecha:** {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"- **Modo:** `{mode_tag}`\n")
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
            f.write("| Iteración | Hallazgo | Commit Dev | Commit Aud | Dev | Tests | Auditor | Exit | Resumen |\n")
            f.write("|---|---|---|---|---|---|---|---|---|\n")
            for item in self.state.history:
                dev_sha = (item.get("commit_sha_developer") or item.get("commit_sha") or "")[:7]
                aud_sha = (item.get("commit_sha_audited") or item.get("commit_sha") or "")[:7]
                f.write(
                    f"| {item.get('iteration')} | {item.get('finding')} | {dev_sha} | {aud_sha} "
                    f"| {item.get('developer_status')} | {item.get('tests_passed')} | {item.get('auditor_status')} "
                    f"| {item.get('audit_exit_code', 0)} | {item.get('summary', '')[:40]} |\n"
                )

        # JSON report
        json_path = self.reports_dir / f"{prefix}report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            report_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "SIMULATION" if self.config.simulation_mode else "REAL",
                "status": self.state.status,
                "active_block": self.state.active_block,
                "current_commit": self.state.current_commit,
                "summary": summary_msg,
                "closed_findings": self.state.closed_findings,
                "open_findings": self.state.open_findings,
                "history": self.state.history,
            }
            json.dump(report_data, f, indent=2, ensure_ascii=False)
