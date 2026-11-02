"""
Manejador de simulación para pruebas deterministas del orquestador autónomo.
Permite reproducir los 11 escenarios requeridos sin consumir tokens de APIs externas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.runner import ProcessResult
from orchestrator.security import QuotaExceededError, StalledAgentError


class SimulationDriver:
    """Configura y reproduce escenarios simulados de Antigravity y Codex."""

    current_scenario: str = "PASS_PASS"
    turn_counter: int = 0
    injected_diff: str = "diff --git a/backend/app/main.py b/backend/app/main.py\n+ # simulated fix"
    auditor_json_override: dict[str, Any] | str | None = None

    @classmethod
    def reset(cls, scenario: str = "PASS_PASS") -> None:
        cls.current_scenario = scenario
        cls.turn_counter = 0
        cls.injected_diff = "diff --git a/backend/app/main.py b/backend/app/main.py\n+ # simulated fix"
        cls.auditor_json_override = None

    @classmethod
    def run_developer_turn(cls, finding_id: str, instructions: str) -> ProcessResult:
        cls.turn_counter += 1

        if cls.current_scenario == "CLI_UNAUTHENTICATED_DEV":
            return ProcessResult(
                returncode=1,
                stdout="",
                stderr="Error: No API key provided or invalid credentials for Gemini.",
                elapsed_seconds=0.5,
            )

        if cls.current_scenario == "DEV_QUOTA_EXCEEDED":
            raise QuotaExceededError("ResourceExhausted: 429 Resource has been exhausted (e.g. check quota).")

        if cls.current_scenario == "STALLED_NO_PROGRESS":
            # Developer devuelve éxito pero sin diff
            cls.injected_diff = ""
            return ProcessResult(
                returncode=0,
                stdout="Simulated developer: No changes needed.",
                stderr="",
                elapsed_seconds=1.0,
            )

        return ProcessResult(
            returncode=0,
            stdout=f"Simulated developer: Implemented fix for {finding_id} successfully.",
            stderr="",
            elapsed_seconds=1.2,
        )

    @classmethod
    def run_auditor_turn(
        cls, finding_id: str, instructions: str
    ) -> tuple[dict[str, Any], ProcessResult]:
        if cls.current_scenario == "CLI_UNAUTHENTICATED_AUDITOR":
            dummy = ProcessResult(
                returncode=1,
                stdout="",
                stderr="Codex auth error: missing authentication token.",
                elapsed_seconds=0.5,
            )
            return {"status": "FAIL", "findings": [], "evidence": [], "summary": "Unauthenticated."}, dummy

        if cls.current_scenario == "AUDITOR_QUOTA_EXCEEDED":
            raise QuotaExceededError("Rate limit reached for OpenAI model in Codex.")

        if cls.current_scenario == "AUDITOR_INVALID_JSON":
            proc = ProcessResult(
                returncode=0,
                stdout="Este texto no es un objeto JSON y no contiene llaves validas.",
                stderr="",
                elapsed_seconds=1.0,
            )
            report = {
                "status": "FAIL",
                "findings": [
                    {
                        "id": finding_id,
                        "status": "FAIL",
                        "summary": "Fallo de parsing de JSON de auditoría.",
                        "evidence": proc.stdout,
                        "blocking_issue": "Codex no emitió un JSON válido.",
                    }
                ],
                "evidence": [proc.stdout],
                "summary": "JSON inválido emitido por el auditor.",
                "tests_executed": 0,
                "clean_tree": True,
            }
            return report, proc

        if cls.current_scenario in ("PASS_FAIL", "ALWAYS_FAIL"):
            # Si el escenario es ALWAYS_FAIL, o si es PASS_FAIL y turno <= 1: reporta FAIL
            if cls.current_scenario == "ALWAYS_FAIL" or cls.turn_counter <= 1:
                fail_report = {
                    "status": "FAIL",
                    "findings": [
                        {
                            "id": finding_id,
                            "status": "FAIL",
                            "summary": f"Contraejemplo reproducido en {finding_id}.",
                            "evidence": "Fallo observado con trigger tardío.",
                            "blocking_issue": "El worker no fue cancelado a tiempo.",
                        }
                    ],
                    "evidence": ["Evidencia de fallo adversarial."],
                    "summary": f"Auditoría rechazada para {finding_id}.",
                    "tests_executed": 2,
                    "clean_tree": True,
                }
                proc = ProcessResult(returncode=0, stdout=json.dumps(fail_report), stderr="", elapsed_seconds=1.5)
                return fail_report, proc

        # Escenario por defecto: PASS_PASS
        pass_report = {
            "status": "PASS",
            "findings": [
                {
                    "id": finding_id,
                    "status": "PASS",
                    "summary": f"Hallazgo {finding_id} remediado satisfactoriamente.",
                    "evidence": "Contraejemplos ejecutados con resultado limpio.",
                    "blocking_issue": None,
                }
            ],
            "evidence": ["Pruebas adversariales aprobadas sin escrituras posteriores."],
            "summary": f"Dictamen PASS para {finding_id}.",
            "tests_executed": 3,
            "clean_tree": True,
        }
        proc = ProcessResult(returncode=0, stdout=json.dumps(pass_report), stderr="", elapsed_seconds=1.1)
        return pass_report, proc
