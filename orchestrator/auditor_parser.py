"""
Parser y validador del informe estructurado emitido por el Auditor (Codex).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


class AuditReportValidationError(Exception):
    """Excepción cuando el informe del auditor no cumple el esquema exigido."""
    pass


VALID_STATUSES = {"PASS", "FAIL", "PARCIAL"}


def extract_json_from_text(raw_text: str) -> dict[str, Any] | None:
    """Extrae un objeto JSON válido desde texto plano o bloques de código markdown."""
    if not raw_text:
        return None

    trimmed = raw_text.strip()

    # Intentar parseo directo
    try:
        data = json.loads(trimmed)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Intentar extraer bloques ```json ... ```
    code_block_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", trimmed)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # Intentar extraer el primer bloque {...} balanceado
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


def validate_audit_report(data: dict[str, Any]) -> dict[str, Any]:
    """
    Valida que el informe del auditor contenga todos los campos obligatorios
    y cumpla los invariantes requeridos.
    """
    if not isinstance(data, dict):
        raise AuditReportValidationError("El informe del auditor debe ser un objeto JSON (dict).")

    status = data.get("status")
    if not status or not isinstance(status, str):
        raise AuditReportValidationError("El campo 'status' es obligatorio y debe ser una cadena.")

    status_upper = status.upper().strip()
    if status_upper not in VALID_STATUSES:
        raise AuditReportValidationError(
            f"El estado '{status}' no es válido. Debe ser uno de: {VALID_STATUSES}"
        )
    data["status"] = status_upper

    findings = data.get("findings")
    if not isinstance(findings, list):
        raise AuditReportValidationError("El campo 'findings' es obligatorio y debe ser una lista.")

    for idx, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise AuditReportValidationError(f"El hallazgo en índice {idx} debe ser un objeto.")
        f_id = finding.get("id")
        f_status = finding.get("status")
        if not f_id or not isinstance(f_id, str):
            raise AuditReportValidationError(f"El hallazgo {idx} no tiene un 'id' de cadena válido.")
        if not f_status or f_status.upper().strip() not in VALID_STATUSES:
            raise AuditReportValidationError(
                f"El hallazgo '{f_id}' tiene un status inválido: '{f_status}'. Debe ser PASS/FAIL/PARCIAL."
            )
        finding["status"] = f_status.upper().strip()

    summary = data.get("summary")
    if not summary or not isinstance(summary, str):
        raise AuditReportValidationError("El campo 'summary' es obligatorio y debe ser una cadena no vacía.")

    evidence = data.get("evidence")
    if evidence is None:
        raise AuditReportValidationError("El campo 'evidence' es obligatorio.")

    return data


def parse_and_validate_audit_report(raw_text: str) -> dict[str, Any]:
    """
    Parsea y valida el informe del auditor.
    Lanza AuditReportValidationError si el JSON es inválido o no cumple el esquema.
    """
    data = extract_json_from_text(raw_text)
    if data is None:
        raise AuditReportValidationError("No se pudo extraer un objeto JSON válido del mensaje del auditor.")

    return validate_audit_report(data)
