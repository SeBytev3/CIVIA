"""
Manejador de simulación para pruebas deterministas del orquestador autónomo.
Permite reproducir todos los escenarios adversariales exigidos por la auditoría de Codex
sin consumir tokens de APIs externas ni tocar el estado persistente real del proyecto.
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
    injected_sha: str | None = None
    custom_exit_code: int = 0

    @classmethod
    def reset(cls, scenario: str = "PASS_PASS") -> None:
        cls.current_scenario = scenario
        cls.turn_counter = 0
        cls.injected_diff = "diff --git a/backend/app/main.py b/backend/app/main.py\n+ # simulated fix"
        cls.injected_sha = None
        cls.custom_exit_code = 0

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
            cls.injected_diff = ""
            return ProcessResult(
                returncode=0,
                stdout="Simulated developer: No changes needed.",
                stderr="",
                elapsed_seconds=1.0,
            )

        # Developer produce código con éxito y simula reporte de tokens
        mock_tokens = {"input_tokens": 1200, "output_tokens": 150, "total_tokens": 1350}
        return ProcessResult(
            returncode=0,
            stdout=f"Simulated developer: Implemented fix for {finding_id} successfully.",
            stderr="",
            elapsed_seconds=1.2,
            tokens_used=mock_tokens,
        )

    @classmethod
    def run_auditor_turn(
        cls,
        finding_id: str,
        instructions: str,
        commit_sha: str | None = None,
    ) -> tuple[dict[str, Any], ProcessResult]:
        valid_40_sha = "5b36fb55f87dc49e3256f9814cddb47e3cb3b800"
        active_sha = cls.injected_sha or commit_sha or valid_40_sha

        if cls.current_scenario == "CLI_UNAUTHENTICATED_AUDITOR":
            dummy = ProcessResult(
                returncode=1,
                stdout="",
                stderr="Codex auth error: missing authentication token.",
                elapsed_seconds=0.5,
            )
            return {
                "status": "FAIL",
                "commit_sha": active_sha,
                "findings": [],
                "evidence": [],
                "summary": "Unauthenticated.",
                "tests_executed": 0,
            }, dummy

        if cls.current_scenario == "AUDITOR_QUOTA_EXCEEDED":
            raise QuotaExceededError("Rate limit reached for OpenAI model in Codex.")

        if cls.current_scenario == "AUDITOR_PASS_NON_ZERO_EXIT":
            # Escenario 1: Codex emite PASS pero el proceso termina con exit code != 0
            pass_report = {
                "status": "PASS",
                "commit_sha": active_sha,
                "findings": [{"id": finding_id, "status": "PASS", "summary": "Fix ok"}],
                "evidence": ["Evidencia de ejecución de prueba test_remediation_worker_timeout."],
                "summary": "PASS emitido pero exit code 1",
                "tests_executed": 3,
            }
            proc = ProcessResult(returncode=1, stdout=json.dumps(pass_report), stderr="Crash on exit", elapsed_seconds=1.0)
            return pass_report, proc

        if cls.current_scenario == "AUDITOR_PASS_EMPTY_EVIDENCE":
            # Escenario 2: Codex emite PASS sin evidencias o con evidencias genéricas fabricadas
            pass_report = {
                "status": "PASS",
                "commit_sha": active_sha,
                "findings": [{"id": finding_id, "status": "PASS", "summary": "Fix ok"}],
                "evidence": ["Contraejemplos ejecutados con resultado limpio."],  # Frase genérica prohibida
                "summary": "PASS con evidencia genérica vacía.",
                "tests_executed": 1,
            }
            proc = ProcessResult(returncode=0, stdout=json.dumps(pass_report), stderr="", elapsed_seconds=1.0)
            return pass_report, proc

        if cls.current_scenario == "AUDITOR_PASS_BOOLEAN_TESTS":
            # Escenario: Codex emite PASS pero con tests_executed=True (trampa de tipo booleano)
            pass_report = {
                "status": "PASS",
                "commit_sha": active_sha,
                "findings": [{"id": finding_id, "status": "PASS", "summary": "Fix ok"}],
                "evidence": ["Ejecución de prueba test_adversarial_timeout_rollback en base desechable."],
                "summary": "PASS con tests_executed booleano.",
                "tests_executed": True,  # Trampa booleana
            }
            proc = ProcessResult(returncode=0, stdout=json.dumps(pass_report), stderr="", elapsed_seconds=1.0)
            return pass_report, proc

        if cls.current_scenario == "AUDITOR_PASS_WITH_INDIVIDUAL_FAIL":
            # Escenario 3: Codex emite status global PASS pero contiene un hallazgo individual en FAIL
            incoherent_report = {
                "status": "PASS",
                "commit_sha": active_sha,
                "findings": [
                    {"id": finding_id, "status": "FAIL", "summary": "Worker timeout still fails.", "blocking_issue": "Timeout"}
                ],
                "evidence": ["Contraejemplo de prueba test_worker falló con timeout."],
                "summary": "Incoherencia global PASS con individual FAIL.",
                "tests_executed": 2,
            }
            proc = ProcessResult(returncode=0, stdout=json.dumps(incoherent_report), stderr="", elapsed_seconds=1.0)
            return incoherent_report, proc

        if cls.current_scenario == "AUDITOR_SHA_MISMATCH":
            # Escenario 4: Codex audita un SHA diferente de 40 caracteres
            mismatch_report = {
                "status": "PASS",
                "commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",  # SHA diferente de 40 caracteres
                "findings": [{"id": finding_id, "status": "PASS", "summary": "Aprobado en commit equivocado"}],
                "evidence": ["Prueba test_sha_mismatch ejecutada en checkout anterior."],
                "summary": "Aprobado en SHA viejo.",
                "tests_executed": 3,
            }
            proc = ProcessResult(returncode=0, stdout=json.dumps(mismatch_report), stderr="", elapsed_seconds=1.0)
            return mismatch_report, proc

        if cls.current_scenario == "AUDITOR_INVALID_JSON":
            proc = ProcessResult(
                returncode=0,
                stdout="Este texto no es un objeto JSON y no contiene llaves validas.",
                stderr="",
                elapsed_seconds=1.0,
            )
            report = {
                "status": "FAIL",
                "commit_sha": active_sha,
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
            }
            return report, proc

        if cls.current_scenario in ("PASS_FAIL", "ALWAYS_FAIL"):
            if cls.current_scenario == "ALWAYS_FAIL" or cls.turn_counter <= 1:
                fail_report = {
                    "status": "FAIL",
                    "commit_sha": active_sha,
                    "findings": [
                        {
                            "id": finding_id,
                            "status": "FAIL",
                            "summary": f"Contraejemplo reproducido en {finding_id}.",
                            "evidence": "Fallo observado con trigger tardío.",
                            "blocking_issue": "El worker no fue cancelado a tiempo.",
                        }
                    ],
                    "evidence": ["Evidencia de fallo adversarial con trigger de 0.18s."],
                    "summary": f"Auditoría rechazada para {finding_id}.",
                    "tests_executed": 2,
                }
                proc = ProcessResult(returncode=0, stdout=json.dumps(fail_report), stderr="", elapsed_seconds=1.5)
                return fail_report, proc

        # Escenario por defecto: PASS_PASS genuino
        pass_report = {
            "status": "PASS",
            "commit_sha": active_sha,
            "findings": [
                {
                    "id": finding_id,
                    "status": "PASS",
                    "summary": f"Hallazgo {finding_id} remediado satisfactoriamente.",
                    "evidence": "Prueba adversarial de trigger diferido ejecutada con rollback confirmado en 0.25s.",
                    "blocking_issue": None,
                }
            ],
            "evidence": [
                "Prueba test_adversarial_deferred_trigger ejecutada contra civia_test_db con rollback confirmado.",
                "Consulta de verificación confirmó cero escrituras posteriores a la señal de cancelación.",
            ],
            "summary": f"Dictamen PASS verificado para {finding_id}.",
            "tests_executed": 3,
        }
        mock_tokens = {"input_tokens": 2500, "output_tokens": 300, "total_tokens": 2800}
        proc = ProcessResult(
            returncode=0,
            stdout=json.dumps(pass_report),
            stderr="",
            elapsed_seconds=1.1,
            tokens_used=mock_tokens,
        )
        return pass_report, proc
