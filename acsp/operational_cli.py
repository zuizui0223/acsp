"""CLI for downstream movement-constrained selection of ACSP candidate patches."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from .operational_selector import select_movement_constrained_patches
from .reachability import select_reachability_constrained_patches


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acsp-operate",
        description=(
            "Select an automatically sized operational subset from an existing "
            "ACSP candidate-patch CSV. Supply exactly one hard movement constraint: "
            "a geometric transition threshold or an explicit allowed-edge graph. "
            "Neither mode is a validated road/ferry routing or field-efficiency claim."
        ),
    )
    parser.add_argument("--patches", type=Path, required=True)
    movement = parser.add_mutually_exclusive_group(required=True)
    movement.add_argument(
        "--max-transition-km",
        type=float,
        help="Geometric proxy: same-area patches within this distance are connected.",
    )
    movement.add_argument(
        "--reachability-edges",
        type=Path,
        help=(
            "CSV of explicitly allowed undirected transitions with columns "
            "from_patch_id,to_patch_id. Graph mode does not infer movement from distance."
        ),
    )
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

    if args.reachability_edges is not None:
        if not args.reachability_edges.is_file():
            raise FileNotFoundError(
                f"Reachability-edge CSV was not found: {args.reachability_edges}"
            )
        edges = pd.read_csv(args.reachability_edges)
        selected, audit = select_reachability_constrained_patches(patches, edges)
        movement_mode = "explicit_reachability_graph"
        straight_line_assumption = False
        movement_input: dict[str, object] = {
            "reachability_edges_csv": str(args.reachability_edges),
            "reachability_edge_count": int(audit.reachability_edge_count),
        }
        status = "downstream_operational_reachability"
    else:
        selected, audit = select_movement_constrained_patches(
            patches,
            max_transition_km=float(args.max_transition_km),
        )
        movement_mode = "geometric_transition_proxy"
        straight_line_assumption = True
        movement_input = {"max_transition_km": float(args.max_transition_km)}
        status = "downstream_operational_geometry"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(args.output, index=False)
    summary: dict[str, object] = {
        "status": status,
        "input_csv": str(args.patches),
        "output_csv": str(args.output),
        "candidate_patch_count": int(len(patches)),
        "automatic_selected_count": int(len(selected)),
        "movement_constraint_only": True,
        "movement_constraint_mode": movement_mode,
        "straight_line_movement_assumption": straight_line_assumption,
        **movement_input,
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
