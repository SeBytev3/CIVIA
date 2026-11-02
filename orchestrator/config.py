"""
Configuración central del orquestador autónomo de CIVIA.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "orchestrator" / "config.json"


@dataclass
class OrchestratorConfig:
    agy_binary: str = "agy"
    codex_binary: str = "codex"
    developer_model: str = "gemini-3.8-flash-high"
    auditor_model: str = "o3"
    git_branch: str = "fix/auditoria-final"
    base_commit: str = "5b36fb55f87dc49e3256f9814cddb47e3cb3b800"
    max_cycles_per_finding: int = 5
    max_infrastructure_retries: int = 3
    agent_timeout_seconds: int = 300
    test_timeout_seconds: int = 180
    simulation_mode: bool = False
    disposable_db_prefix: str = "civia_test_"
    require_human_approval_for_destructive: bool = True
    auto_push: bool = False
    auto_merge_main: bool = False

    @classmethod
    def load(cls, config_path: Path | None = None) -> OrchestratorConfig:
        target_path = config_path or DEFAULT_CONFIG_PATH
        if not target_path.exists():
            return cls()

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()

    def save(self, config_path: Path | None = None) -> None:
        target_path = config_path or DEFAULT_CONFIG_PATH
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
