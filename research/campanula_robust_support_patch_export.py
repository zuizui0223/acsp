#!/usr/bin/env python3
"""Reproduce the frozen Campanula robust support envelope and export candidate patches.

Campanula is now a regression fixture for the taxon-agnostic robust-support core.
The species-specific adapter only samples the frozen NDVI feature stack and
retains the archived patch aggregation needed for exact freeze reproduction.
The robust environmental geometry and leave-one-prototype-out consensus are
computed by :mod:`acsp.robust_patches`.

The output stops at bounded same-island candidate patches. No route, movement
mode, field-day, site-count, or monetary-budget optimization is performed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.robust_patches import leave_one_out_consensus_support
import campanula_patch_policy as base
from campanula_worldcover_discovery import evaluate

FROZEN_SUPPORT_THRESHOLD = 0.09945575892925262
FROZEN_THRESHOLD_TOLERANCE = 1e-12
EXPECTED_CANONICAL_CELLS = 2367
EXPECTED_RECOVERY = 19
PRIMARY_RADIUS_KM = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def consensus_support(
    universe: pd.DataFrame,
    prototypes: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """Return the archived float32 LOO consensus through the generic core."""
    consensus, uncertainty, audit = leave_one_out_consensus_support(
        universe,
        prototypes,
        feature_columns=base.FULL_NDVI,
        support_world_dtype="float32",
        min_kernel_scale=0.25,
        chunk_size=3000,
    )
    # Keep the legacy return shape while the exporter remains a freeze fixture.
    kernel_scales = [audit.kernel_scale_min, audit.kernel_scale_max]
    return consensus, uncertainty, kernel_scales


def annotate_zones(
    zones: pd.DataFrame,
    consensus_rank: np.ndarray,
    uncertainty: np.ndarray,
) -> pd.DataFrame:
    annotated = zones.copy().reset_index(drop=True)
    best_rank: list[float] = []
    median_rank: list[float] = []
    mean_uncertainty: list[float] = []
    max_uncertainty: list[float] = []
    for _, zone in annotated.iterrows():
        members = base.patch.member_indices(zone)
        rank_values = consensus_rank[members]
        uncertainty_values = uncertainty[members]
        best_rank.append(float(np.min(rank_values)))
        median_rank.append(float(np.median(rank_values)))
        mean_uncertainty.append(float(np.mean(uncertainty_values)))
        max_uncertainty.append(float(np.max(uncertainty_values)))
    annotated["consensus_support_rank_best"] = best_rank
    annotated["consensus_support_rank_median"] = median_rank
    annotated["consensus_support_uncertainty_mean"] = mean_uncertainty
    annotated["consensus_support_uncertainty_max"] = max_uncertainty
    annotated["ecological_support_threshold"] = FROZEN_SUPPORT_THRESHOLD
    annotated["ecological_status"] = "frozen_robust_support_patch"
    # Carry the archived patch-aggregation scale in the artifact itself. The
    # downstream selector reads this provenance instead of maintaining a second
    # hidden 1 km operational constant. This metadata does not alter patch
    # identity; it only makes the already-frozen aggregation scale explicit.
    annotated["patch_merge_distance_m"] = float(base.MERGE_DISTANCE_M)
    annotated["site_id"] = annotated["zone_id"].astype(str)
    return annotated


def main() -> None:
    args = parse_args()
    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes).reset_index(drop=True)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    if len(prototypes) < 5:
        raise RuntimeError("too few prototypes for frozen LOO consensus reconstruction")

    # Ecological generator stage: field outcomes are not read here.
    consensus_rank, uncertainty, kernel_scales = consensus_support(universe, prototypes)
    frozen_cutoff = FROZEN_SUPPORT_THRESHOLD + FROZEN_THRESHOLD_TOLERANCE
    selected_mask = consensus_rank <= frozen_cutoff
    selected_indices = np.flatnonzero(selected_mask)
    selected_cells = universe.iloc[selected_indices].copy()

    # Keep the archived complete-link implementation for exact Campanula patch
    # identity. The generic package API has its own bounded patch converter.
    _, zones = base.make_zones(universe, consensus_rank, frozen_cutoff)
    zones = annotate_zones(zones, consensus_rank, uncertainty)

    island_cells = (
        selected_cells["island"].astype(str).value_counts().sort_index().astype(int).to_dict()
    )
    island_patches = (
        zones["survey_area_id"].astype(str).value_counts().sort_index().astype(int).to_dict()
    )

    # Development verification stage: field outcomes become visible only now.
    detections = pd.read_csv(args.detections)
    field_result = evaluate(selected_cells, detections, PRIMARY_RADIUS_KM)

    report = {
        "status": "frozen_robust_support_patch_export",
        "species": "Campanula microdonta",
        "scientific_role": "regression fixture for taxon-agnostic robust candidate-patch generation",
        "generic_core": "acsp.robust_patches.leave_one_out_consensus_support",
        "field_coordinates_used_to_build_consensus_support": False,
        "field_coordinates_used_to_choose_threshold": False,
        "field_coordinates_used_to_define_patches": False,
        "prototype_count": int(len(prototypes)),
        "leave_one_out_worlds": int(len(prototypes)),
        "feature_columns": list(base.FULL_NDVI),
        "support_threshold": FROZEN_SUPPORT_THRESHOLD,
        "threshold_tolerance": FROZEN_THRESHOLD_TOLERANCE,
        "support_world_dtype": "float32",
        "threshold_source": "research/campanula_development_freeze_v1.json",
        "selected_cells": int(len(selected_indices)),
        "expected_frozen_cells": EXPECTED_CANONICAL_CELLS,
        "selected_cell_fraction": float(len(selected_indices) / len(universe)),
        "patch_count": int(len(zones)),
        "merge_distance_m": float(base.MERGE_DISTANCE_M),
        "patch_artifact_merge_distance_column": "patch_merge_distance_m",
        "island_cell_counts": {str(k): int(v) for k, v in island_cells.items()},
        "island_patch_counts": {str(k): int(v) for k, v in island_patches.items()},
        "support_uncertainty_mean": float(np.mean(uncertainty[selected_mask])),
        "support_uncertainty_q95": float(np.quantile(uncertainty[selected_mask], 0.95)),
        "kernel_scale_min": float(np.min(kernel_scales)),
        "kernel_scale_max": float(np.max(kernel_scales)),
        "field_development_verification": field_result,
        "candidate_output_contract": {
            "all_exported_patches_remain_ecologically_eligible": True,
            "patch_count_is_not_a_user_budget": True,
            "output_stops_at_candidate_patches": True,
            "route_or_effort_optimization": False,
            "patch_merge_scale_is_carried_in_artifact": True,
        },
    }

    report["freeze_reproduction"] = {
        "cell_count_matches": bool(len(selected_indices) == EXPECTED_CANONICAL_CELLS),
        "field_recovery_matches": bool(field_result["recovered"] == EXPECTED_RECOVERY),
        "pass": bool(
            len(selected_indices) == EXPECTED_CANONICAL_CELLS
            and field_result["recovered"] == EXPECTED_RECOVERY
        ),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    zones.to_csv(args.out / "robust_support_patches.csv", index=False)
    selected_cells.to_csv(args.out / "robust_support_cells.csv", index=False)
    pd.DataFrame(
        {
            "universe_index": np.arange(len(universe), dtype=int),
            "consensus_support_rank": consensus_rank,
            "consensus_support_uncertainty": uncertainty,
            "selected_by_frozen_threshold": selected_mask,
        }
    ).to_csv(args.out / "consensus_support_audit.csv", index=False)
    (args.out / "robust_support_patch_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    if not report["freeze_reproduction"]["pass"]:
        raise RuntimeError(
            "generic robust-support core no longer reproduces the archived Campanula freeze"
        )


if __name__ == "__main__":
    main()
