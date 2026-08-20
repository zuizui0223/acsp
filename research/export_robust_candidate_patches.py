#!/usr/bin/env python3
"""Audit/development exporter for taxon-agnostic robust support tiers.

This script intentionally exposes multiple thresholds for method development and
audit. It is not the validated production product. Use ``acsp-patches`` or
``acsp.validated_robust.validated_robust_candidate_patches`` for the frozen
2.5% candidate-patch rule confirmed on the untouched cross-taxon cohort.

Inputs contain only a candidate universe, training occurrence prototypes, and the
environmental feature columns shared by both tables. No field outcomes are read.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from acsp.robust_patches import leave_one_out_consensus_support, support_cells_to_patches

DEFAULT_TIERS = (0.025, 0.05, 0.10, 0.20)


def _csv_floats(value: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not values or any(item <= 0 or item >= 1 for item in values):
        raise argparse.ArgumentTypeError("tiers must be comma-separated fractions strictly between 0 and 1")
    return tuple(sorted(set(values)))


def _csv_columns(value: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in value.split(",") if item.strip())
    if not values:
        raise argparse.ArgumentTypeError("feature columns must not be empty")
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--prototypes", type=Path, required=True)
    parser.add_argument("--feature-columns", type=_csv_columns, required=True)
    parser.add_argument("--tiers", type=_csv_floats, default=DEFAULT_TIERS)
    parser.add_argument("--merge-distance-m", type=float, default=1000.0)
    parser.add_argument("--latitude-column", default="latitude")
    parser.add_argument("--longitude-column", default="longitude")
    parser.add_argument("--area-column", default="survey_area_id")
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    universe = pd.read_csv(args.universe)
    prototypes = pd.read_csv(args.prototypes).reset_index(drop=True)
    consensus, uncertainty, audit = leave_one_out_consensus_support(
        universe,
        prototypes,
        feature_columns=args.feature_columns,
        support_world_dtype="float32",
    )

    args.out.mkdir(parents=True, exist_ok=True)
    surface = universe.copy()
    surface["consensus_support_rank"] = consensus
    surface["consensus_support_uncertainty"] = uncertainty
    surface.to_csv(args.out / "robust_support_surface.csv", index=False)

    tier_rows: list[dict[str, object]] = []
    for threshold in args.tiers:
        cells, patches = support_cells_to_patches(
            universe,
            consensus,
            threshold=float(threshold),
            merge_distance_m=float(args.merge_distance_m),
            latitude_col=args.latitude_column,
            longitude_col=args.longitude_column,
            area_col=args.area_column,
            ecological_status="robust_support_patch_descriptive_tier",
        )
        token = f"q{int(round(float(threshold) * 1000)):03d}"
        cells["support_tier"] = float(threshold)
        patches["support_tier"] = float(threshold)
        cells.to_csv(args.out / f"candidate_cells_{token}.csv", index=False)
        patches.to_csv(args.out / f"candidate_patches_{token}.csv", index=False)
        tier_rows.append(
            {
                "support_fraction": float(threshold),
                "selected_cells": int(len(cells)),
                "patch_count": int(len(patches)),
                "cell_fraction": float(len(cells) / len(universe)) if len(universe) else 0.0,
                "patch_file": f"candidate_patches_{token}.csv",
                "cell_file": f"candidate_cells_{token}.csv",
            }
        )

    manifest = {
        "status": "research_audit_only",
        "validated_product": "acsp-patches",
        "scientific_object": "occurrence-conditioned leave-one-prototype-out robust environmental support",
        "field_outcomes_read": False,
        "threshold_selection_claim": "none",
        "tier_role": "nested descriptive research outputs; production uses the separately validated frozen 2.5% rule",
        "feature_columns": list(args.feature_columns),
        "support_audit": audit.as_dict(),
        "merge_distance_m": float(args.merge_distance_m),
        "latitude_column": args.latitude_column,
        "longitude_column": args.longitude_column,
        "area_column": args.area_column,
        "universe_rows": int(len(universe)),
        "prototype_rows_input": int(len(prototypes)),
        "prototype_rows_complete": int(audit.prototype_count),
        "prototype_rows_excluded_incomplete": int(len(prototypes) - audit.prototype_count),
        "tiers": tier_rows,
    }
    (args.out / "robust_candidate_patch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
