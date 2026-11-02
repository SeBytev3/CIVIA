"""
Operaciones de control de versiones Git, staging selectivo y aislamiento mediante worktrees.
Garantiza que fallos al crear worktrees aborten inmediatamente y prohíbe el uso de git add -A indiscriminado.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from orchestrator.security import (
    WorktreeCreationError,
    redact_secrets,
    validate_git_command,
)


REPO_ROOT = Path(__file__).resolve().parent.parent

# Rutas permitidas para staging automático por tarea
ALLOWED_SOURCE_PREFIXES = (
    "backend/app/",
    "backend/tests/",
    "backend/migrations/",
    "frontend/src/",
    "docs/",
    "eval/",
)

FORBIDDEN_FILE_PATTERNS = (
    ".env",
    ".tmp",
    ".log",
    ".lock",
    ".db",
    "scratch/",
    "state.json",
    "simulation_state.json",
)


class GitError(Exception):
    """Excepción para errores de ejecución en operaciones de Git."""
    pass


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    """Ejecuta un comando de Git de forma segura validando contra restricciones."""
    validate_git_command(args)
    target_cwd = cwd or REPO_ROOT

    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(target_cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        raise GitError(f"Error invocando git {args[0] if args else ''}: {exc}") from exc

    if proc.returncode != 0:
        err_msg = redact_secrets(proc.stderr.strip() or proc.stdout.strip())
        raise GitError(f"Git falló con código {proc.returncode}: {err_msg}")

    return proc.stdout.strip()


def get_current_branch(repo_path: Path | None = None) -> str:
    """Retorna el nombre de la rama activa actual."""
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)


def get_current_head(repo_path: Path | None = None) -> str:
    """Retorna el SHA exacto del HEAD actual."""
    return _run_git(["rev-parse", "HEAD"], cwd=repo_path)


def is_working_tree_clean(repo_path: Path | None = None) -> bool:
    """Verifica si el árbol de trabajo está completamente limpio (sin cambios ni untracked)."""
    status = _run_git(["status", "--porcelain"], cwd=repo_path)
    return len(status) == 0


def get_uncommitted_changes(repo_path: Path | None = None) -> list[str]:
    """Retorna la lista de rutas relativas con cambios no confirmados (tracked o untracked)."""
    status_output = _run_git(["status", "--porcelain"], cwd=repo_path)
    changes = []
    for line in status_output.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            path_part = parts[1].strip()
            # En caso de renombramientos ("old -> new"), tomar la nueva ruta
            if " -> " in path_part:
                path_part = path_part.split(" -> ")[1].strip()
            changes.append(path_part.replace("\\", "/"))
    return changes


def has_uncommitted_changes(repo_path: Path | None = None) -> bool:
    """Indica si existen cambios en el árbol de trabajo."""
    return len(get_uncommitted_changes(repo_path)) > 0


def get_diff_since(base_sha: str, repo_path: Path | None = None) -> str:
    """Retorna el diff de cambios introducidos respecto a un commit base."""
    return _run_git(["diff", f"{base_sha}..HEAD"], cwd=repo_path)


def is_path_allowed_for_commit(rel_path: str) -> bool:
    """Comprueba si un archivo pertenece a las rutas del proyecto permitidas para commit."""
    norm_path = rel_path.replace("\\", "/")

    # Excluir patrones prohibidos o temporales
    for pattern in FORBIDDEN_FILE_PATTERNS:
        if pattern in norm_path:
            return False

    # Incluir solo si pertenece a prefijos autorizados
    for prefix in ALLOWED_SOURCE_PREFIXES:
        if norm_path.startswith(prefix):
            return True

    return False


def create_checkpoint_commit(
    message: str,
    target_files: list[str] | None = None,
    repo_path: Path | None = None,
) -> str:
    """
    Crea un commit de checkpoint selectivo.
    Prohíbe terminantemente `git add -A` indiscriminado.
    Solo agrega archivos modificados o nuevos que pertenezcan a las rutas de código permitidas.
    """
    if target_files is not None:
        files_to_stage = [f for f in target_files if is_path_allowed_for_commit(f)]
    else:
        uncommitted = get_uncommitted_changes(repo_path)
        files_to_stage = [f for f in uncommitted if is_path_allowed_for_commit(f)]

    if not files_to_stage:
        # Nada permitido para stagear
        return get_current_head(repo_path)

    # Stagear únicamente los archivos permitidos
    for f in files_to_stage:
        _run_git(["add", f], cwd=repo_path)

    staged = _run_git(["diff", "--cached", "--name-only"], cwd=repo_path)
    if staged:
        _run_git(["commit", "-m", message], cwd=repo_path)

    return get_current_head(repo_path)


def create_audit_worktree(commit_sha: str, temp_dir: Path | None = None) -> Path:
    """
    Crea un worktree aislado de Git desacoplado en una carpeta temporal
    congelando el commit_sha exacto para la inspección de Codex.
    Si falla la creación, aborta de forma tajante (NUNCA fallback al repo principal).
    """
    if temp_dir is None:
        worktree_base = Path(tempfile.gettempdir()) / "civia_audit_worktrees"
        worktree_base.mkdir(parents=True, exist_ok=True)
        worktree_dir = Path(tempfile.mkdtemp(prefix="audit_", dir=worktree_base))
    else:
        worktree_dir = temp_dir
        worktree_dir.mkdir(parents=True, exist_ok=True)

    try:
        _run_git(["worktree", "add", "--detach", str(worktree_dir), commit_sha])
    except Exception as exc:
        # Limpieza si el directorio quedó a medias
        if worktree_dir.exists():
            try:
                shutil.rmtree(worktree_dir, ignore_errors=True)
            except Exception:
                pass
        raise WorktreeCreationError(
            f"Fallo crítico al crear el worktree de auditoría para el commit {commit_sha}: {exc}. "
            "Operación abortada por seguridad: no se permite auditar sobre el repositorio principal."
        ) from exc

    return worktree_dir


def remove_audit_worktree(worktree_dir: Path) -> None:
    """Elimina el worktree temporal y limpia el registro de Git."""
    if not worktree_dir.exists():
        return

    try:
        _run_git(["worktree", "remove", "--force", str(worktree_dir)])
    except Exception:
        try:
            _run_git(["worktree", "prune"])
        except Exception:
            pass

    if worktree_dir.exists():
        try:
            shutil.rmtree(worktree_dir, ignore_errors=True)
        except Exception:
            pass
