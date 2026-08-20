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
            "With --taxon alone, ACSP scans the same 12 Japanese regions used in cross-taxon confirmation. "
            "Add --extent for one custom region, or provide precomputed CSV inputs. "
            "The 2.5% support fraction and 1 km patch aggregation are fixed."
        ),
    )
    parser.add_argument("--taxon", help="Scientific species name for the simple discovery path")
    parser.add_argument("--extent", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--area-id", default="survey")
    parser.add_argument("--universe", type=Path)
    parser.add_argument("--prototypes", type=Path)
    parser.add_argument("--feature-columns", type=_csv_columns)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, default=Path("acsp-patches-summary.json"))
    parser.add_argument("--latitude-column", default="latitude")
    parser.add_argument("--longitude-column", default="longitude")
    parser.add_argument("--area-column", default="survey_area_id")
    return parser


def _validated_summary_base() -> dict[str, object]:
    return {
        "status": VALIDATED_ROBUST_STATUS,
        "scientific_object": "occurrence-conditioned robust environmental candidate patches",
        "output_unit": "candidate_patch",
        "field_outcomes_used_for_generation": False,
        "occupancy_probability_claim": False,
        "exact_site_claim": False,
        "routing_or_budget_optimization": False,
        "validated_support_fraction": VALIDATED_ROBUST_SUPPORT_FRACTION,
        "validated_patch_merge_distance_m": VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
        "validation_primary_radius_km": VALIDATED_ROBUST_PRIMARY_RADIUS_KM,
        "validation_confirmation_pairs": VALIDATED_ROBUST_CONFIRMATION_PAIRS,
        "validation_confirmation_folds": VALIDATED_ROBUST_CONFIRMATION_FOLDS,
        "validation_mean_lift_over_random": VALIDATED_ROBUST_MEAN_LIFT_OVER_RANDOM,
        "validation_bootstrap_95_ci": list(VALIDATED_ROBUST_BOOTSTRAP_CI),
        "validation_one_sided_sign_flip_p": VALIDATED_ROBUST_SIGN_FLIP_P,
    }


def _run_taxon_mode(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, object]]:
    if any(value is not None for value in (args.universe, args.prototypes, args.feature_columns)):
        raise ValueError("--taxon mode cannot be combined with --universe, --prototypes, or --feature-columns")

    if args.extent is None:
        from .taxon_patches import discover_validated_candidate_patches_japan

        patches, discovery = discover_validated_candidate_patches_japan(args.taxon)
    else:
        from .taxon_patches import discover_validated_candidate_patches

        patches, discovery = discover_validated_candidate_patches(
            args.taxon,
            tuple(args.extent),
            area_id=args.area_id,
        )
    summary = {
        **_validated_summary_base(),
        **discovery,
        "output_csv": str(args.output),
    }
    return patches, summary


def _run_csv_mode(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, object]]:
    missing = [
        flag
        for flag, value in (
            ("--universe", args.universe),
            ("--prototypes", args.prototypes),
            ("--feature-columns", args.feature_columns),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            "CSV mode requires " + ", ".join(missing) + "; alternatively use --taxon"
        )
    if args.extent is not None:
        raise ValueError("--extent is only used with --taxon mode")
    assert args.universe is not None and args.prototypes is not None and args.feature_columns is not None
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
    summary = {
        **_validated_summary_base(),
        "input_mode": "precomputed_csv",
        "universe_csv": str(args.universe),
        "prototype_csv": str(args.prototypes),
        "output_csv": str(args.output),
        "universe_rows": int(len(universe)),
        "prototype_rows_input": int(len(prototypes)),
        "candidate_patch_count": int(len(patches)),
        "feature_columns": list(args.feature_columns),
        "support_audit": audit.as_dict(),
    }
    return patches, summary


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.taxon:
        patches, summary = _run_taxon_mode(args)
    else:
        patches, summary = _run_csv_mode(args)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    patches.to_csv(args.output, index=False)
    summary = {**summary, "candidate_patch_count": int(len(patches))}
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
