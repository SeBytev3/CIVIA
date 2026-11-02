"""
Gestión de memoria de estado persistente del orquestador.
Asegura escrituras atómicas, bloqueo de concurrencia, detección de JSON corrupto
y separación estricta entre ejecuciones reales y simuladas.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Generator

from orchestrator.security import (
    LockAcquisitionError,
    SecurityViolationError,
    StateCorruptionError,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = REPO_ROOT / "orchestrator" / "state.json"
DEFAULT_SIMULATION_STATE_PATH = REPO_ROOT / "orchestrator" / "simulation_state.json"


@dataclass
class IterationLog:
    iteration: int
    timestamp: str
    finding: str
    commit_sha_developer: str
    commit_sha_audited: str
    developer_status: str
    tests_passed: bool
    auditor_status: str | None
    findings_reported: list[dict[str, Any]]
    summary: str
    audit_exit_code: int = 0
    tokens_used: dict[str, int] = field(default_factory=dict)
    mode: str = "REAL"


@contextmanager
def file_lock(lock_file_path: Path, timeout: float = 10.0) -> Generator[None, None, None]:
    """Bloqueo de archivo multiplataforma con espera acotada y adquisición estricta."""
    start_time = time.monotonic()
    acquired = False

    lock_file_path.parent.mkdir(parents=True, exist_ok=True)
    while time.monotonic() - start_time < timeout:
        try:
            # En Windows/Unix, O_CREAT | O_EXCL garantiza atomicidad
            fd = os.open(str(lock_file_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            time.sleep(0.05)
        except Exception:
            time.sleep(0.05)

    if not acquired:
        # Intentar recuperar solo si el lock supera 60s de antigüedad (proceso muerto)
        try:
            mtime = lock_file_path.stat().st_mtime
            if time.time() - mtime > 60.0:
                lock_file_path.unlink(missing_ok=True)
                fd = os.open(str(lock_file_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.close(fd)
                acquired = True
        except Exception:
            pass

    if not acquired:
        raise LockAcquisitionError(
            f"No se pudo adquirir el bloqueo exclusivo en '{lock_file_path}' tras {timeout}s. "
            "Operación abortada para evitar condiciones de carrera o escrituras concurrentes."
        )

    try:
        yield
    finally:
        if acquired:
            try:
                lock_file_path.unlink(missing_ok=True)
            except Exception:
                pass


@dataclass
class OrchestratorState:
    active_block: str = "G2.1"
    current_finding: str = "M-03"
    iteration: int = 0
    status: str = "READY"
    current_commit: str = "5b36fb55f87dc49e3256f9814cddb47e3cb3b800"
    closed_findings: list[str] = field(
        default_factory=lambda: [
            "C-01",
            "A-01",
            "M-07",
            "N-03",
            "A-06",
            "A-07",
            "B-03",
            "N-02",
            "A-02",
        ]
    )
    open_findings: list[str] = field(
        default_factory=lambda: [
            "M-03",
            "M-06",
            "M-02",
            "A-03",
            "A-04",
            "A-05",
            "M-01",
            "M-04",
            "G3",
        ]
    )
    pending_blocks: list[str] = field(
        default_factory=lambda: [
            "G2.1",
            "G2.2",
            "G3",
            "AUDIT_GENERAL",
            "PUBLICATION",
        ]
    )
    history: list[dict[str, Any]] = field(default_factory=list)
    last_audit_report: dict[str, Any] | None = None
    last_run_timestamp: str | None = None
    is_simulation: bool = False

    @classmethod
    def get_default_path(cls, simulation_mode: bool = False) -> Path:
        return DEFAULT_SIMULATION_STATE_PATH if simulation_mode else DEFAULT_STATE_PATH

    @classmethod
    def load(cls, state_path: Path | None = None, simulation_mode: bool = False) -> OrchestratorState:
        target_path = state_path or cls.get_default_path(simulation_mode)

        # Separación irreversible entre SIMULATED y REAL
        if simulation_mode and (target_path == DEFAULT_STATE_PATH or not target_path.name.startswith("simulation_")):
            raise SecurityViolationError("Prohibido cargar el estado de producción en modo simulación.")
        if not simulation_mode and (target_path == DEFAULT_SIMULATION_STATE_PATH or target_path.name.startswith("simulation_")):
            raise SecurityViolationError("Prohibido cargar el estado de simulación en modo producción.")

        if not target_path.exists():
            instance = cls()
            instance.is_simulation = simulation_mode
            instance._state_path = target_path
            return instance

        lock_path = target_path.with_suffix(".lock")
        with file_lock(lock_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if not content.strip():
                    raise json.JSONDecodeError("Archivo de estado vacío.", "", 0)

                data = json.loads(content)
            except Exception as exc:
                # Ante JSON corrupto, NO reiniciar silenciosamente: hacer backup y detenerse
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                backup_path = target_path.with_name(f"{target_path.stem}.corrupt.{ts}{target_path.suffix}")
                try:
                    shutil.copy2(target_path, backup_path)
                except Exception:
                    pass
                raise StateCorruptionError(
                    f"El archivo de estado '{target_path}' contiene JSON corrupto o inválido: {exc}. "
                    f"Se ha creado un respaldo de seguridad en '{backup_path}'. "
                    "El orquestador se detiene para evitar pérdida de datos o reinicio silencioso."
                ) from exc

            # Validar campos esenciales
            if not isinstance(data, dict):
                raise StateCorruptionError(f"El estado en '{target_path}' no es un objeto JSON.")

            if "closed_findings" not in data or not isinstance(data.get("closed_findings"), list):
                raise StateCorruptionError(f"El estado en '{target_path}' no contiene la lista 'closed_findings'.")

            valid_kwargs = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            instance = cls(**valid_kwargs)
            instance.is_simulation = simulation_mode
            instance._state_path = target_path
            return instance

    def save(self, state_path: Path | None = None) -> None:
        target_path = state_path or getattr(self, "_state_path", None) or self.get_default_path(self.is_simulation)

        # Separación irreversible entre estado SIMULATED y REAL
        if self.is_simulation:
            if target_path == DEFAULT_STATE_PATH or not target_path.name.startswith("simulation_"):
                raise SecurityViolationError(
                    f"Contaminación de estado bloqueada: una ejecución en modo simulación intentó guardar "
                    f"en el estado real de producción '{target_path}'."
                )
        else:
            if target_path == DEFAULT_SIMULATION_STATE_PATH or target_path.name.startswith("simulation_"):
                raise SecurityViolationError(
                    f"Contaminación de estado bloqueada: una ejecución real intentó guardar en '{target_path}'."
                )

        if state_path:
            self._state_path = state_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_run_timestamp = datetime.now(timezone.utc).isoformat()

        lock_path = target_path.with_suffix(".lock")
        with file_lock(lock_path):
            # Escritura atómica mediante archivo temporal y reemplazo
            tmp_path = target_path.with_name(f"{target_path.stem}.tmp.{os.getpid()}.{time.time_ns()}")
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(asdict(self), f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())

                # Reintentos breves ante retención transitoria de identificadores en Windows
                replaced = False
                for attempt in range(10):
                    try:
                        os.replace(tmp_path, target_path)
                        replaced = True
                        break
                    except PermissionError:
                        if attempt == 9:
                            raise
                        time.sleep(0.05)
            except Exception as exc:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                raise exc

    def record_iteration(
        self,
        finding: str,
        commit_sha_developer: str,
        commit_sha_audited: str,
        developer_status: str,
        tests_passed: bool,
        auditor_status: str | None,
        findings_reported: list[dict[str, Any]],
        summary: str,
        audit_exit_code: int = 0,
        tokens_used: dict[str, int] | None = None,
    ) -> None:
        log_entry = IterationLog(
            iteration=self.iteration,
            timestamp=datetime.now(timezone.utc).isoformat(),
            finding=finding,
            commit_sha_developer=commit_sha_developer,
            commit_sha_audited=commit_sha_audited,
            developer_status=developer_status,
            tests_passed=tests_passed,
            auditor_status=auditor_status,
            findings_reported=findings_reported,
            summary=summary,
            audit_exit_code=audit_exit_code,
            tokens_used=tokens_used or {},
            mode="SIMULATION" if self.is_simulation else "REAL",
        )
        self.history.append(asdict(log_entry))

    def mark_finding_closed(self, finding: str) -> None:
        if self.is_simulation:
            # En modo simulación jamás se altera la lista real de aprobaciones permanentes
            pass

        if finding in self.open_findings:
            self.open_findings.remove(finding)
        if finding not in self.closed_findings:
            self.closed_findings.append(finding)
        self.iteration = 0
        if self.open_findings:
            self.current_finding = self.open_findings[0]
        else:
            self.current_finding = "NONE"
            self.status = "COMPLETED"
