"""
Punto de entrada de línea de comandos para el orquestador autónomo CIVIA.
"""

from __future__ import annotations

import argparse
import sys

from orchestrator.config import OrchestratorConfig
from orchestrator.controller import OrchestratorController
from orchestrator.preflight import PreflightChecker
from orchestrator.state import OrchestratorState


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CIVIA Autopilot: Orquestador autónomo de desarrollo y auditoría."
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Ejecuta en modo simulación determinista sin consumir APIs reales ni requerir CLIs externos.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Ejecuta únicamente el diagnóstico de preflight y finaliza.",
    )
    parser.add_argument(
        "--block",
        type=str,
        default=None,
        help="Especifica el bloque objetivo (ej. G2.1, G2.2, G3).",
    )
    parser.add_argument(
        "--finding",
        type=str,
        default=None,
        help="Especifica el hallazgo específico a remediar (ej. M-03, M-06).",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Número máximo de ciclos antes de detenerse (por defecto 5).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reinicia la memoria de estado (state.json) a los valores iniciales.",
    )

    args = parser.parse_args()

    config = OrchestratorConfig.load()
    if args.simulate:
        config.simulation_mode = True

    if args.preflight_only:
        checker = PreflightChecker(config)
        ok = checker.check_all()
        checker.print_diagnostics_report()
        return 0 if ok else 1

    state = OrchestratorState() if args.reset else OrchestratorState.load()

    if args.block:
        state.active_block = args.block
    if args.finding:
        state.current_finding = args.finding

    controller = OrchestratorController(config=config, state=state)
    result = controller.run(max_cycles_override=args.max_cycles)

    status = result.get("status")
    if status == "COMPLETED":
        return 0
    elif status in ("PREFLIGHT_FAILED", "HALTED_QUOTA", "MAX_CYCLES_REACHED", "STALLED"):
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
