"""
Módulo de preflight: verificación de herramientas, autenticación, modelos y entorno.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from orchestrator.config import OrchestratorConfig
from orchestrator.git_ops import get_current_branch, get_current_head, is_working_tree_clean
from orchestrator.security import redact_secrets


WELL_KNOWN_CODEX_PATHS = [
    Path.home() / ".codex" / "plugins" / ".plugin-appserver" / "codex.exe",
    Path.home() / ".codex" / "bin" / "codex.exe",
]

WELL_KNOWN_AGY_PATHS = [
    Path.home() / "AppData" / "Roaming" / "Antigravity" / "bin" / "agy.cmd",
    Path.home() / ".gemini" / "antigravity" / "bin" / "agy.cmd",
    Path.home() / ".gemini" / "bin" / "agy.cmd",
]


def resolve_binary_path(binary_name: str, well_known_list: list[Path] | None = None) -> str | None:
    """Busca un ejecutable en el PATH del sistema o en ubicaciones estándar conocidas."""
    found = shutil.which(binary_name)
    if found:
        return found

    if well_known_list:
        for p in well_known_list:
            if p.exists():
                return str(p)

    return None


def run_simple_command(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    """Ejecuta un comando con timeout acotado y retorna código de salida y stdout sanitizado."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        output = proc.stdout.strip() or proc.stderr.strip()
        return proc.returncode, redact_secrets(output)
    except Exception as exc:
        return 1, str(exc)


class PreflightChecker:
    """Verificador integral del entorno para el orquestador."""

    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        self.config = config or OrchestratorConfig.load()
        self.diagnostics: list[dict[str, Any]] = []

    def check_all(self) -> bool:
        """Ejecuta todas las comprobaciones y retorna True si todo es apto para ejecución autónoma."""
        self.diagnostics = []
        all_passed = True

        # 1. Git
        git_ok = self._check_git()
        all_passed = all_passed and git_ok

        # 2. Python
        python_ok = self._check_python()
        all_passed = all_passed and python_ok

        # 3. Docker y Docker Compose
        docker_ok = self._check_docker()
        compose_ok = self._check_docker_compose()
        all_passed = all_passed and docker_ok and compose_ok

        # 4. Agente Desarrollador (Antigravity / agy)
        agy_ok = self._check_agy()
        all_passed = all_passed and (agy_ok or self.config.simulation_mode)

        # 5. Agente Auditor (Codex / codex exec)
        codex_ok = self._check_codex()
        all_passed = all_passed and (codex_ok or self.config.simulation_mode)

        # 6. Repositorio y Rama
        repo_ok = self._check_repo_state()
        all_passed = all_passed and repo_ok

        return all_passed

    def _check_git(self) -> bool:
        code, out = run_simple_command(["git", "--version"])
        if code == 0 and "git version" in out.lower():
            self.diagnostics.append({"tool": "git", "status": "OK", "version": out})
            return True
        self.diagnostics.append(
            {
                "tool": "git",
                "status": "FAIL",
                "error": "Git no está instalado o no se encuentra en el PATH.",
                "solution": "Instale Git para Windows desde https://git-scm.com/download/win",
            }
        )
        return False

    def _check_python(self) -> bool:
        code, out = run_simple_command(["python", "--version"])
        if code == 0 and "python" in out.lower():
            self.diagnostics.append({"tool": "python", "status": "OK", "version": out})
            return True
        self.diagnostics.append(
            {
                "tool": "python",
                "status": "FAIL",
                "error": "Python no está disponible en el comando 'python'.",
                "solution": "Instale Python 3.13 o 3.14 y agréguelo al PATH del sistema.",
            }
        )
        return False

    def _check_docker(self) -> bool:
        code, out = run_simple_command(["docker", "--version"])
        if code == 0:
            # Comprobar si el demonio responde
            daemon_code, daemon_out = run_simple_command(["docker", "info"], timeout=5)
            if daemon_code == 0:
                self.diagnostics.append({"tool": "docker", "status": "OK", "version": out})
                return True
            else:
                self.diagnostics.append(
                    {
                        "tool": "docker",
                        "status": "FAIL",
                        "error": "Docker CLI está instalado, pero Docker Desktop / el demonio no está en ejecución.",
                        "solution": "Inicie Docker Desktop en Windows y espere a que el motor esté listo.",
                    }
                )
                return False

        self.diagnostics.append(
            {
                "tool": "docker",
                "status": "FAIL",
                "error": "Docker no está disponible en PATH.",
                "solution": "Instale Docker Desktop para Windows desde https://www.docker.com/products/docker-desktop/",
            }
        )
        return False

    def _check_docker_compose(self) -> bool:
        code, out = run_simple_command(["docker", "compose", "version"])
        if code == 0 and "version" in out.lower():
            self.diagnostics.append({"tool": "docker compose", "status": "OK", "version": out})
            return True
        self.diagnostics.append(
            {
                "tool": "docker compose",
                "status": "FAIL",
                "error": "Docker Compose v2 no responde mediante 'docker compose version'.",
                "solution": "Habilite Compose V2 en la configuración de Docker Desktop.",
            }
        )
        return False

    def _check_agy(self) -> bool:
        if self.config.simulation_mode:
            self.diagnostics.append(
                {
                    "tool": "agy",
                    "status": "SIMULATED",
                    "path": "simulated_developer_agent",
                    "version": "simulated",
                    "model": self.config.developer_model,
                }
            )
            return True

        agy_path = resolve_binary_path(self.config.agy_binary, WELL_KNOWN_AGY_PATHS)
        if agy_path:
            # Comprobar versión o ayuda sin interactividad
            code, out = run_simple_command([agy_path, "--version"])
            if code == 0:
                self.diagnostics.append(
                    {
                        "tool": "agy",
                        "status": "OK",
                        "path": agy_path,
                        "version": out,
                        "model": self.config.developer_model,
                    }
                )
                return True
            # Intentar con --help
            code_h, out_h = run_simple_command([agy_path, "--help"])
            if code_h == 0:
                self.diagnostics.append(
                    {
                        "tool": "agy",
                        "status": "OK",
                        "path": agy_path,
                        "version": "disponible",
                        "model": self.config.developer_model,
                    }
                )
                return True

        self.diagnostics.append(
            {
                "tool": "agy",
                "status": "FAIL",
                "error": f"No se encontró el ejecutable '{self.config.agy_binary}' en PATH ni en rutas conocidas.",
                "solution": (
                    "Para instalar Antigravity CLI (`agy`), consulte la documentación en "
                    "https://antigravity.google/docs/cli o configure la ruta exacta en `orchestrator/config.json`. "
                    "Si desea verificar el orquestador sin la CLI, ejecute en modo simulación: "
                    "`pwsh -File scripts/civia-autopilot.ps1 -Simulate`."
                ),
            }
        )
        return False

    def _check_codex(self) -> bool:
        if self.config.simulation_mode:
            self.diagnostics.append(
                {
                    "tool": "codex",
                    "status": "SIMULATED",
                    "path": "simulated_auditor_agent",
                    "version": "simulated",
                }
            )
            return True

        codex_path = resolve_binary_path(self.config.codex_binary, WELL_KNOWN_CODEX_PATHS)
        if codex_path:
            code, out = run_simple_command([codex_path, "--version"])
            if code == 0 and "codex" in out.lower():
                self.diagnostics.append(
                    {
                        "tool": "codex",
                        "status": "OK",
                        "path": codex_path,
                        "version": out,
                    }
                )
                return True

        self.diagnostics.append(
            {
                "tool": "codex",
                "status": "FAIL",
                "error": f"No se encontró el ejecutable '{self.config.codex_binary}' en PATH ni en rutas estándar.",
                "solution": (
                    "Para instalar Codex CLI, consulte la documentación oficial o agregue el binario "
                    f"a su PATH o configure 'codex_binary' en `orchestrator/config.json`. "
                    "Ruta detectada en el perfil: `~/.codex/plugins/.plugin-appserver/codex.exe`. "
                    "Para probar el flujo sin Codex real, use el modo simulación: "
                    "`pwsh -File scripts/civia-autopilot.ps1 -Simulate`."
                ),
            }
        )
        return False

    def _check_repo_state(self) -> bool:
        try:
            branch = get_current_branch()
            head = get_current_head()
            clean = is_working_tree_clean()

            self.diagnostics.append(
                {
                    "tool": "repository",
                    "status": "OK",
                    "branch": branch,
                    "head": head[:8],
                    "clean_tree": clean,
                }
            )
            return True
        except Exception as exc:
            self.diagnostics.append(
                {
                    "tool": "repository",
                    "status": "FAIL",
                    "error": f"Error leyendo el estado de Git: {exc}",
                    "solution": "Asegúrese de estar en la raíz de un repositorio Git válido.",
                }
            )
            return False

    def print_diagnostics_report(self) -> None:
        """Imprime un informe claro en consola con el resultado del preflight."""
        print("\n" + "=" * 70)
        print(" CIVIA AUTOPILOT — REPORTE DE PREFLIGHT")
        print("=" * 70)

        for diag in self.diagnostics:
            tool = diag.get("tool", "").upper()
            status = diag.get("status", "")
            if status == "OK":
                detail = diag.get("version") or diag.get("branch") or diag.get("path") or ""
                print(f" [PASS] {tool:<15}: OK ({detail})")
            elif status == "SIMULATED":
                print(f" [SIM]  {tool:<15}: MODO SIMULACIÓN")
            else:
                err = diag.get("error", "Error desconocido")
                sol = diag.get("solution", "")
                print(f" [FAIL] {tool:<15}: {err}")
                if sol:
                    print(f"        -> Acción recomendada: {sol}")

        print("=" * 70 + "\n")
