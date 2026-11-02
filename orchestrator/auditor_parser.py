"""
Parser y validador del informe estructurado emitido por el Auditor (Codex).
Asegura que los informes sean imposibles de falsificar, con evidencia reproducible,
coherencia entre hallazgos individuales y globales, validación de SHA y verificación de código de salida.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


class AuditReportValidationError(Exception):
    """Excepción cuando el informe del auditor no cumple el contrato exigido."""
    pass


VALID_STATUSES = {"PASS", "FAIL", "PARCIAL"}


def extract_json_from_text(raw_text: str) -> dict[str, Any] | None:
    """Extrae un objeto JSON válido desde texto plano o bloques de código markdown."""
    if not raw_text:
        return None

    trimmed = raw_text.strip()

    # 1. Intentar parseo directo
    try:
        data = json.loads(trimmed)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Intentar extraer bloques ```json ... ```
    code_block_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", trimmed)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Intentar extraer el primer bloque {...} balanceado
    start_idx = trimmed.find("{")
    end_idx = trimmed.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        candidate = trimmed[start_idx : end_idx + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def validate_audit_report(
    data: dict[str, Any],
    expected_commit_sha: str | None = None,
    expected_finding_id: str | None = None,
) -> dict[str, Any]:
    """
    Valida rigurosamente que el informe del auditor sea genuino e imposible de falsificar:
    - Status global debe ser PASS, FAIL o PARCIAL.
    - El SHA auditado debe coincidir exactamente con el commit freeze del desarrollador.
    - Si el status es PASS:
      - Todas las sub-evaluaciones individuales deben ser PASS (cero incoherencias).
      - La lista de evidencias debe ser no vacía con descripciones sustantivas.
      - tests_executed debe ser un entero >= 1.
      - El hallazgo esperado debe estar presente en findings.
    """
    if not isinstance(data, dict):
        raise AuditReportValidationError("El informe del auditor debe ser un objeto JSON (dict).")

    raw_status = data.get("status")
    if not raw_status or not isinstance(raw_status, str):
        raise AuditReportValidationError("El campo 'status' es obligatorio y debe ser una cadena.")

    status_upper = raw_status.upper().strip()
    if status_upper not in VALID_STATUSES:
        raise AuditReportValidationError(
            f"El estado global '{raw_status}' no es válido. Debe ser uno de: {VALID_STATUSES}"
        )
    data["status"] = status_upper

    # Validar coherencia de SHA si se exige verificación
    reported_sha = data.get("commit_sha")
    if expected_commit_sha:
        if not reported_sha or not isinstance(reported_sha, str):
            raise AuditReportValidationError(
                f"El informe no incluye 'commit_sha' pero se esperaba verificación del commit '{expected_commit_sha}'."
            )
        # Comparar por prefijo de al menos 7 caracteres o coincidencia exacta
        norm_expected = expected_commit_sha.lower().strip()
        norm_reported = reported_sha.lower().strip()
        if not (norm_expected.startswith(norm_reported) or norm_reported.startswith(norm_expected)):
            raise AuditReportValidationError(
                f"Discrepancia de SHA: el auditor evaluó '{reported_sha}' pero el desarrollador generó '{expected_commit_sha}'."
            )

    findings = data.get("findings")
    if not isinstance(findings, list):
        raise AuditReportValidationError("El campo 'findings' es obligatorio y debe ser una lista.")

    found_target = False
    for idx, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise AuditReportValidationError(f"El hallazgo en índice {idx} debe ser un objeto.")
        f_id = finding.get("id")
        f_status = finding.get("status")
        if not f_id or not isinstance(f_id, str):
            raise AuditReportValidationError(f"El hallazgo en índice {idx} no tiene un 'id' válido.")
        if not f_status or not isinstance(f_status, str) or f_status.upper().strip() not in VALID_STATUSES:
            raise AuditReportValidationError(
                f"El hallazgo '{f_id}' tiene un status inválido: '{f_status}'. Debe ser PASS/FAIL/PARCIAL."
            )
        norm_status = f_status.upper().strip()
        finding["status"] = norm_status

        if expected_finding_id and f_id.strip() == expected_finding_id.strip():
            found_target = True

        # Incoherencia individual vs global
        if status_upper == "PASS" and norm_status != "PASS":
            raise AuditReportValidationError(
                f"Incoherencia en auditoría: status global es PASS pero el hallazgo individual '{f_id}' es {norm_status}."
            )

    if expected_finding_id and not found_target:
        raise AuditReportValidationError(
            f"El informe de auditoría no incluye evaluación para el hallazgo activo esperado '{expected_finding_id}'."
        )

    summary = data.get("summary")
    if not summary or not isinstance(summary, str) or not summary.strip():
        raise AuditReportValidationError("El campo 'summary' es obligatorio y debe ser una cadena no vacía.")

    evidence = data.get("evidence")
    if evidence is None:
        raise AuditReportValidationError("El campo 'evidence' es obligatorio.")

    if not isinstance(evidence, list):
        raise AuditReportValidationError("El campo 'evidence' debe ser una lista de evidencias reproducibles.")

    # Si el dictamen es PASS, exigir evidencias obligatorias no vacías y pruebas ejecutadas
    if status_upper == "PASS":
        if len(evidence) == 0:
            raise AuditReportValidationError("Rechazo de PASS: lista de evidencias vacía.")

        has_substantive_evidence = any(
            isinstance(e, str) and len(e.strip()) >= 10 for e in evidence
        )
        if not has_substantive_evidence:
            raise AuditReportValidationError(
                "Rechazo de PASS: las evidencias no contienen descripciones técnicas reproducibles sustantivas."
            )

        tests_executed = data.get("tests_executed")
        if tests_executed is None or not isinstance(tests_executed, int) or tests_executed < 1:
            raise AuditReportValidationError(
                f"Rechazo de PASS: tests_executed debe ser un entero >= 1 (reportado: {tests_executed})."
            )

    return data


def validate_audit_process_execution(audit_report: dict[str, Any], proc_returncode: int) -> None:
    """Valida que el subproceso del auditor haya terminado con código de salida 0."""
    if proc_returncode != 0:
        raise AuditReportValidationError(
            f"El proceso de auditoría finalizó anormalmente con código de salida {proc_returncode}."
        )


def parse_and_validate_audit_report(
    raw_text: str,
    expected_commit_sha: str | None = None,
    expected_finding_id: str | None = None,
    proc_returncode: int = 0,
) -> dict[str, Any]:
    """
    Parsea y valida integralmente el informe de auditoría.
    Lanza AuditReportValidationError si el código de salida no es cero, el JSON es inválido,
    el SHA no coincide, falta evidencia o hay incoherencias lógicas.
    """
    validate_audit_process_execution({}, proc_returncode)

    data = extract_json_from_text(raw_text)
    if data is None:
        raise AuditReportValidationError("No se pudo extraer un objeto JSON válido del mensaje del auditor.")

    return validate_audit_report(
        data,
        expected_commit_sha=expected_commit_sha,
        expected_finding_id=expected_finding_id,
    )
