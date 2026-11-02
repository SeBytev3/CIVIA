"""
Módulo de seguridad, guardrails, sanitización de datos y control de procesos del orquestador.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent

# Patrones sensibles comunes a redactar
SECRET_PATTERNS = [
    re.compile(r"(AIzaSy[A-Za-z0-9_-]{33})"),
    re.compile(r"(gsk_[A-Za-z0-9]{32,})"),
    re.compile(r"(bearer\s+)([a-zA-Z0-9_\-\.]{16,})", re.IGNORECASE),
    re.compile(r"(ADMIN_TOKEN=)(.+)", re.IGNORECASE),
    re.compile(r"(POSTGRES_PASSWORD=)(.+)", re.IGNORECASE),
    re.compile(r"(SECRET_KEY=)(.+)", re.IGNORECASE),
    re.compile(r"(['\"]?[a-zA-Z0-9_]*key['\"]?\s*[:=]\s*['\"])([a-zA-Z0-9_\-]{16,})(['\"])", re.IGNORECASE),
    re.compile(r"(['\"]?[a-zA-Z0-9_]*token['\"]?\s*[:=]\s*['\"])([a-zA-Z0-9_\-]{16,})(['\"])", re.IGNORECASE),
]


class SecurityViolationError(Exception):
    """Excepción lanzada cuando una operación viola una política de seguridad."""
    pass


class QuotaExceededError(Exception):
    """Excepción lanzada cuando un proveedor o CLI alcanza su cuota."""
    pass


class StalledAgentError(Exception):
    """Excepción lanzada cuando un agente no realiza cambios o se atasca en bucle."""
    pass


class MaxIterationsError(Exception):
    """Excepción lanzada cuando se alcanza el límite máximo de iteraciones."""
    pass


class WorktreeCreationError(Exception):
    """Excepción lanzada cuando falla la creación del worktree aislado."""
    pass


class TestSyncError(Exception):
    """Excepción lanzada cuando el código del entorno de pruebas no coincide con el commit auditado."""
    __test__ = False


class StateCorruptionError(Exception):
    """Excepción lanzada cuando el archivo de estado contiene JSON corrupto o inválido."""
    pass


def load_env_secret_values(env_path: Path | None = None) -> list[str]:
    """Carga valores reales de .env para redactarlos activamente en logs."""
    target_env = env_path or (REPO_ROOT / ".env")
    secrets = []
    if not target_env.exists():
        return secrets

    try:
        with open(target_env, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    val = val.strip().strip("\"'")
                    if len(val) >= 8 and not val.startswith("local_"):
                        secrets.append(val)
    except Exception:
        pass
    return secrets


_LOADED_SECRETS: list[str] | None = None


def get_known_secrets() -> list[str]:
    global _LOADED_SECRETS
    if _LOADED_SECRETS is None:
        _LOADED_SECRETS = load_env_secret_values()
    return _LOADED_SECRETS


def redact_secrets(text: str) -> str:
    """Sanitiza cualquier texto eliminando API keys, tokens y credenciales."""
    if not text:
        return ""

    sanitized = text
    # Redactar valores conocidos de .env
    for secret in get_known_secrets():
        if secret in sanitized:
            sanitized = sanitized.replace(secret, "[REDACTED_SECRET]")

    # Redactar mediante regex
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub(r"[REDACTED]", sanitized)

    return sanitized


def validate_git_command(command: list[str] | str) -> None:
    """
    Verifica que un comando de Git sea seguro.
    Prohíbe terminantemente:
    - git push
    - merge hacia main o master
    - eliminación de ramas principales
    """
    cmd_str = " ".join(command) if isinstance(command, list) else command
    cmd_lower = cmd_str.lower().strip()

    if "push" in cmd_lower:
        raise SecurityViolationError(
            f"Operación prohibida por seguridad: '{cmd_str}'. No se permite git push automático."
        )

    if "merge" in cmd_lower and ("main" in cmd_lower or "master" in cmd_lower):
        raise SecurityViolationError(
            f"Operación prohibida por seguridad: '{cmd_str}'. No se permite merge hacia main sin aprobación humana."
        )

    if "branch" in cmd_lower and ("-d" in cmd_lower or "-D" in cmd_lower) and ("main" in cmd_lower or "master" in cmd_lower):
        raise SecurityViolationError(
            f"Operación prohibida por seguridad: '{cmd_str}'. No se permite eliminar ramas principales."
        )


def validate_database_command(sql: str, db_name: str, allowed_test_prefix: str = "civia_test_") -> None:
    """
    Verifica que sentencias SQL potencialmente destructivas solo se ejecuten
    contra bases de datos de prueba desechables identificadas.
    """
    sql_upper = sql.upper()
    is_destructive = any(kw in sql_upper for kw in ["DROP DATABASE", "DROP TABLE", "TRUNCATE"])

    if is_destructive:
        if not db_name.startswith(allowed_test_prefix) and not db_name.startswith("test_"):
            raise SecurityViolationError(
                f"Intento de ejecutar SQL destructivo sobre la base no desechable '{db_name}'. "
                f"Solo permitido sobre bases con prefijo '{allowed_test_prefix}' o 'test_'."
            )


def detect_zero_diff(diff_output: str) -> bool:
    """Determina si un ciclo no generó ningún cambio en el código."""
    return not bool(diff_output and diff_output.strip())


def kill_process_tree(pid: int) -> None:
    """Termina de forma forzada un árbol completo de procesos por PID."""
    if pid <= 0:
        return

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass
    else:
        try:
            import signal
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            try:
                os.kill(pid, 9)
            except Exception:
                pass


def get_sanitized_agent_env() -> dict[str, str]:
    """
    Retorna un diccionario de variables de entorno saneado para invocar subagentes.
    Elimina secretos administrativos y credenciales no necesarias para la tarea del agente.
    """
    env = os.environ.copy()
    # Variables de alta sensibilidad a eliminar del entorno hijo del subagente
    forbidden_vars = [
        "ADMIN_TOKEN",
        "POSTGRES_PASSWORD",
        "SECRET_KEY",
        "DATABASE_URL",
    ]
    for var in forbidden_vars:
        env.pop(var, None)

    return env
