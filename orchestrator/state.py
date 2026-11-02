"""
Gestión de memoria de estado persistente del orquestador (orchestrator/state.json).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = REPO_ROOT / "orchestrator" / "state.json"


@dataclass
class IterationLog:
    iteration: int
    timestamp: str
    finding: str
    commit_sha: str
    developer_status: str
    tests_passed: bool
    auditor_status: str | None
    findings_reported: list[dict[str, Any]]
    summary: str


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

    @classmethod
    def load(cls, state_path: Path | None = None) -> OrchestratorState:
        target_path = state_path or DEFAULT_STATE_PATH
        if not target_path.exists():
            return cls()

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()

    def save(self, state_path: Path | None = None) -> None:
        target_path = state_path or DEFAULT_STATE_PATH
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_run_timestamp = datetime.now(timezone.utc).isoformat()
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    def record_iteration(
        self,
        finding: str,
        commit_sha: str,
        developer_status: str,
        tests_passed: bool,
        auditor_status: str | None,
        findings_reported: list[dict[str, Any]],
        summary: str,
    ) -> None:
        log_entry = IterationLog(
            iteration=self.iteration,
            timestamp=datetime.now(timezone.utc).isoformat(),
            finding=finding,
            commit_sha=commit_sha,
            developer_status=developer_status,
            tests_passed=tests_passed,
            auditor_status=auditor_status,
            findings_reported=findings_reported,
            summary=summary,
        )
        self.history.append(asdict(log_entry))

    def mark_finding_closed(self, finding: str) -> None:
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
