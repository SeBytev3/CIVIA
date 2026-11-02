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
    SecurityViolationError,
    WorktreeCreationError,
    is_ephemeral_path_registered,
    redact_secrets,
    register_ephemeral_path,
    safe_cleanup_ephemeral_path,
    unregister_ephemeral_path,
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


def _run_git(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
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
            env=env,
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
    Crea un commit de checkpoint selectivo mediante un índice Git aislado.
    Garantiza que ningún archivo previamente staged en el índice habitual
    o fuera de los prefijos permitidos pueda ser incluido en el commit de checkpoint.
    """
    target_cwd = repo_path or REPO_ROOT
    if target_files is not None:
        files_to_stage = [f for f in target_files if is_path_allowed_for_commit(f)]
    else:
        uncommitted = get_uncommitted_changes(target_cwd)
        files_to_stage = [f for f in uncommitted if is_path_allowed_for_commit(f)]

    if not files_to_stage:
        return get_current_head(target_cwd)

    # Crear archivo de índice Git temporal y aislado
    isolated_index_fd, isolated_index_path_str = tempfile.mkstemp(prefix="git_idx_")
    os.close(isolated_index_fd)
    isolated_index_path = Path(isolated_index_path_str)

    try:
        git_env = os.environ.copy()
        git_env["GIT_INDEX_FILE"] = str(isolated_index_path)

        # Inicializar el índice aislado desde el HEAD del repo_path
        _run_git(["read-tree", "HEAD"], cwd=target_cwd, env=git_env)

        # Stagear ÚNICAMENTE los archivos autorizados en el índice aislado
        for f in files_to_stage:
            _run_git(["add", f], cwd=target_cwd, env=git_env)

        # Verificar que ningún archivo no autorizado esté en el staging
        staged = _run_git(["diff", "--cached", "--name-only"], cwd=target_cwd, env=git_env)
        staged_files = [line.strip().replace("\\", "/") for line in staged.splitlines() if line.strip()]

        for sf in staged_files:
            if not is_path_allowed_for_commit(sf):
                raise SecurityViolationError(
                    f"Intento de incluir archivo no autorizado en el commit de checkpoint: '{sf}'."
                )

        if staged_files:
            _run_git(["commit", "-m", message], cwd=target_cwd, env=git_env)

        return get_current_head(target_cwd)
    finally:
        if isolated_index_path.exists():
            try:
                isolated_index_path.unlink()
            except Exception:
                pass


def create_dev_worktree(commit_sha: str, temp_dir: Path | None = None) -> Path:
    """
    Crea un worktree aislado e independiente para el Agente Desarrollador (Antigravity).
    Garantiza que el desarrollador nunca trabaje sobre REPO_ROOT.
    Registra la propiedad del directorio en el orquestador.
    """
    if temp_dir is None:
        worktree_base = Path(tempfile.gettempdir()) / "civia_dev_worktrees"
        worktree_base.mkdir(parents=True, exist_ok=True)
        worktree_dir = Path(tempfile.mkdtemp(prefix="dev_", dir=worktree_base))
    else:
        worktree_dir = temp_dir
        worktree_dir.mkdir(parents=True, exist_ok=True)

    # Registrar la propiedad del directorio efímero antes de la creación
    register_ephemeral_path(worktree_dir)

    try:
        _run_git(["worktree", "add", "--detach", str(worktree_dir), commit_sha])
    except Exception as exc:
        safe_cleanup_ephemeral_path(worktree_dir)
        raise WorktreeCreationError(
            f"Fallo crítico al crear el worktree de desarrollo para el commit {commit_sha}: {exc}. "
            "Operación abortada por seguridad: no se permite desarrollar directamente en REPO_ROOT."
        ) from exc

    return worktree_dir


def create_audit_worktree(commit_sha: str, temp_dir: Path | None = None) -> Path:
    """
    Crea un worktree aislado de Git desacoplado en una carpeta temporal
    congelando el commit_sha exacto para la inspección de Codex.
    Si falla la creación, aborta de forma tajante (NUNCA fallback al repo principal).
    Registra la propiedad del directorio en el orquestador.
    """
    if temp_dir is None:
        worktree_base = Path(tempfile.gettempdir()) / "civia_audit_worktrees"
        worktree_base.mkdir(parents=True, exist_ok=True)
        worktree_dir = Path(tempfile.mkdtemp(prefix="audit_", dir=worktree_base))
    else:
        worktree_dir = temp_dir
        worktree_dir.mkdir(parents=True, exist_ok=True)

    # Registrar la propiedad del directorio efímero antes de la creación
    register_ephemeral_path(worktree_dir)

    try:
        _run_git(["worktree", "add", "--detach", str(worktree_dir), commit_sha])
    except Exception as exc:
        safe_cleanup_ephemeral_path(worktree_dir)
        raise WorktreeCreationError(
            f"Fallo crítico al crear el worktree de auditoría para el commit {commit_sha}: {exc}. "
            "Operación abortada por seguridad: no se permite auditar sobre el repositorio principal."
        ) from exc

    return worktree_dir


def safe_cleanup_worktree(worktree_dir: Path) -> None:
    """
    Elimina un worktree efímero de forma segura comprobando que esté registrado.
    Limpia el registro de git worktrees y borra el directorio del sistema.
    """
    if not is_ephemeral_path_registered(worktree_dir):
        raise SecurityViolationError(
            f"Intento de eliminar directorio no registrado por el orquestador: '{worktree_dir}'."
        )

    try:
        _run_git(["worktree", "remove", "--force", str(worktree_dir)])
    except Exception:
        try:
            _run_git(["worktree", "prune"])
        except Exception:
            pass

    safe_cleanup_ephemeral_path(worktree_dir)


def remove_dev_worktree(worktree_dir: Path) -> None:
    """Elimina el worktree temporal del desarrollador."""
    safe_cleanup_worktree(worktree_dir)


def remove_audit_worktree(worktree_dir: Path) -> None:
    """Elimina el worktree temporal del auditor."""
    safe_cleanup_worktree(worktree_dir)
