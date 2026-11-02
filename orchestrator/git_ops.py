"""
Operaciones de control de versiones Git y aislamiento de auditoría mediante worktrees.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from orchestrator.security import redact_secrets, validate_git_command


REPO_ROOT = Path(__file__).resolve().parent.parent


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


def get_diff_since(base_sha: str, repo_path: Path | None = None) -> str:
    """Retorna el diff de cambios introducidos respecto a un commit base."""
    return _run_git(["diff", f"{base_sha}..HEAD"], cwd=repo_path)


def create_checkpoint_commit(message: str, repo_path: Path | None = None) -> str:
    """
    Crea un commit de checkpoint en la rama activa si existen cambios modificados o nuevos.
    Retorna el nuevo SHA de HEAD.
    """
    _run_git(["add", "-A"], cwd=repo_path)
    # Verificar si hay algo staged
    staged = _run_git(["diff", "--cached", "--name-only"], cwd=repo_path)
    if staged:
        _run_git(["commit", "-m", message], cwd=repo_path)
    return get_current_head(repo_path)


def create_audit_worktree(commit_sha: str, temp_dir: Path | None = None) -> Path:
    """
    Crea un worktree aislado de Git desacoplado en una carpeta temporal
    congelando el commit_sha exacto para la inspección de Codex.
    """
    if temp_dir is None:
        worktree_base = Path(tempfile.gettempdir()) / "civia_audit_worktrees"
        worktree_base.mkdir(parents=True, exist_ok=True)
        worktree_dir = Path(tempfile.mkdtemp(prefix="audit_", dir=worktree_base))
    else:
        worktree_dir = temp_dir
        worktree_dir.mkdir(parents=True, exist_ok=True)

    # Añadir worktree detached
    _run_git(["worktree", "add", "--detach", str(worktree_dir), commit_sha])
    return worktree_dir


def remove_audit_worktree(worktree_dir: Path) -> None:
    """Elimina el worktree temporal y limpia el registro de Git."""
    if not worktree_dir.exists():
        return

    try:
        _run_git(["worktree", "remove", "--force", str(worktree_dir)])
    except Exception:
        # Forzar prune y eliminación manual de directorio si git worktree remove falla
        try:
            _run_git(["worktree", "prune"])
        except Exception:
            pass

    if worktree_dir.exists():
        try:
            shutil.rmtree(worktree_dir, ignore_errors=True)
        except Exception:
            pass
