"""CLI for downstream movement-constrained selection of ACSP candidate patches."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from .operational_selector import select_movement_constrained_patches


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acsp-operate",
        description=(
            "Select an automatically sized operational subset from an existing "
            "ACSP candidate-patch CSV. The only survey-design input is maximum "
            "geometric transition distance. This is not road/ferry routing or "
            "a validated field-efficiency claim."
        ),
    )
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--max-transition-km", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("acsp-operate-summary.json"),
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if not args.patches.is_file():
        raise FileNotFoundError(f"Candidate-patch CSV was not found: {args.patches}")
    patches = pd.read_csv(args.patches)
    selected, audit = select_movement_constrained_patches(
        patches,
        max_transition_km=float(args.max_transition_km),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(args.output, index=False)
    summary: dict[str, object] = {
        "status": "downstream_operational_geometry",
        "input_csv": str(args.patches),
        "output_csv": str(args.output),
        "candidate_patch_count": int(len(patches)),
        "automatic_selected_count": int(len(selected)),
        "movement_constraint_only": True,
        "user_site_count_required": False,
        "user_coverage_target_required": False,
        "survey_days_input": False,
        "monetary_budget_input": False,
        "route_feasibility_claim": False,
        "field_efficiency_claim": False,
        "validated_candidate_generation_changed": False,
        "audit": audit.as_dict(),
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
