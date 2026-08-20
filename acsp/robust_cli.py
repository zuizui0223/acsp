"""CLI for the validated ACSP robust candidate-patch product."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from .validated_robust import (
    VALIDATED_ROBUST_BOOTSTRAP_CI,
    VALIDATED_ROBUST_CONFIRMATION_FOLDS,
    VALIDATED_ROBUST_CONFIRMATION_PAIRS,
    VALIDATED_ROBUST_MEAN_LIFT_OVER_RANDOM,
    VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
    VALIDATED_ROBUST_PRIMARY_RADIUS_KM,
    VALIDATED_ROBUST_SIGN_FLIP_P,
    VALIDATED_ROBUST_STATUS,
    VALIDATED_ROBUST_SUPPORT_FRACTION,
    validated_robust_candidate_patches,
)


def _csv_columns(value: str) -> tuple[str, ...]:
    columns = tuple(item.strip() for item in value.split(",") if item.strip())
    if not columns:
        raise argparse.ArgumentTypeError("feature columns must not be empty")
    return columns


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acsp-patches",
        description=(
            "Export the validated ACSP robust candidate-patch set. "
            "The 2.5% support fraction and 1 km patch aggregation are fixed by untouched confirmation."
        ),
    )
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--prototypes", type=Path, required=True)
    parser.add_argument("--feature-columns", type=_csv_columns, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, default=Path("acsp-patches-summary.json"))
    parser.add_argument("--latitude-column", default="latitude")
    parser.add_argument("--longitude-column", default="longitude")
    parser.add_argument("--area-column", default="survey_area_id")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if not args.universe.is_file():
        raise FileNotFoundError(f"Candidate-universe CSV was not found: {args.universe}")
    if not args.prototypes.is_file():
        raise FileNotFoundError(f"Prototype CSV was not found: {args.prototypes}")

    universe = pd.read_csv(args.universe)
    prototypes = pd.read_csv(args.prototypes)
    patches, audit = validated_robust_candidate_patches(
        universe,
        prototypes,
        feature_columns=args.feature_columns,
        latitude_col=args.latitude_column,
        longitude_col=args.longitude_column,
        area_col=args.area_column,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    patches.to_csv(args.output, index=False)
    summary = {
        "status": VALIDATED_ROBUST_STATUS,
        "scientific_object": "occurrence-conditioned robust environmental candidate patches",
        "output_unit": "candidate_patch",
        "field_outcomes_used_for_generation": False,
        "occupancy_probability_claim": False,
        "exact_site_claim": False,
        "routing_or_budget_optimization": False,
        "universe_csv": str(args.universe),
        "prototype_csv": str(args.prototypes),
        "output_csv": str(args.output),
        "universe_rows": int(len(universe)),
        "prototype_rows_input": int(len(prototypes)),
        "candidate_patch_count": int(len(patches)),
        "feature_columns": list(args.feature_columns),
        "support_audit": audit.as_dict(),
        "validated_support_fraction": VALIDATED_ROBUST_SUPPORT_FRACTION,
        "validated_patch_merge_distance_m": VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
        "validation_primary_radius_km": VALIDATED_ROBUST_PRIMARY_RADIUS_KM,
        "validation_confirmation_pairs": VALIDATED_ROBUST_CONFIRMATION_PAIRS,
        "validation_confirmation_folds": VALIDATED_ROBUST_CONFIRMATION_FOLDS,
        "validation_mean_lift_over_random": VALIDATED_ROBUST_MEAN_LIFT_OVER_RANDOM,
        "validation_bootstrap_95_ci": list(VALIDATED_ROBUST_BOOTSTRAP_CI),
        "validation_one_sided_sign_flip_p": VALIDATED_ROBUST_SIGN_FLIP_P,
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
