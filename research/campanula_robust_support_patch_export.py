#!/usr/bin/env python3
"""Reproduce the frozen Campanula robust support envelope and export survey patches.

This is the active bridge between the ecological and operational ACSP layers.
The ecological object is the already-frozen leave-one-prototype-out consensus
support envelope.  It is not compressed to a field-tuned finite Top-k set.
Instead, every cell passing the frozen 1-km support threshold is aggregated into
bounded same-island survey patches.  Those patches are then suitable inputs for
the separate reachability-first operational planner, where explicit movement
edges determine which patches can actually be visited and survey effort is an
output.

The frozen threshold and expected canonical cell count come from
``campanula_development_freeze_v1.json``.  2026 field detections are opened only
after the consensus surface, thresholded cells, and patch universe are frozen,
solely to verify that the archived ecological object still reproduces its
recorded Campanula development recovery.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_patch_policy as base
from campanula_worldcover_discovery import evaluate

FROZEN_SUPPORT_THRESHOLD = 0.09945575892925262
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
    """Return median LOO support rank and its cross-world standard deviation."""
    ranks: list[np.ndarray] = []
    kernel_scales: list[float] = []
    for removed in range(len(prototypes)):
        subset = prototypes.loc[prototypes.index != removed].reset_index(drop=True)
        _, support_rank, _, kernel_scale = base.environmental_geometry(universe, subset)
        ranks.append(np.asarray(support_rank, dtype=float))
        kernel_scales.append(float(kernel_scale))
    if not ranks:
        raise RuntimeError("no leave-one-prototype-out support worlds were generated")
    stack = np.vstack(ranks)
    return np.median(stack, axis=0), np.std(stack, axis=0), kernel_scales


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
    # Operational planners consume a unique site_id plus coordinates.  Keep the
    # zone identifier as the operational node identifier without changing the
    # ecological score or inventing movement links.
    annotated["site_id"] = annotated["zone_id"].astype(str)
    return annotated


def selected_cells_from_zones(universe: pd.DataFrame, zones: pd.DataFrame) -> pd.DataFrame:
    indices: set[int] = set()
    for _, zone in zones.iterrows():
        indices.update(base.patch.member_indices(zone))
    return universe.loc[sorted(indices)].copy()


def main() -> None:
    args = parse_args()
    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes).reset_index(drop=True)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    if len(prototypes) < 5:
        raise RuntimeError("too few prototypes for frozen LOO consensus reconstruction")

    # Ecological generator stage: field outcomes are not read here.
    consensus_rank, uncertainty, kernel_scales = consensus_support(universe, prototypes)
    selected_mask = consensus_rank <= FROZEN_SUPPORT_THRESHOLD
    selected_indices = np.flatnonzero(selected_mask)
    selected_cells = universe.iloc[selected_indices].copy()
    _, zones = base.make_zones(universe, consensus_rank, FROZEN_SUPPORT_THRESHOLD)
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
        "scientific_role": "reproduce frozen ecological support object and expose operational patch universe",
        "field_coordinates_used_to_build_consensus_support": False,
        "field_coordinates_used_to_choose_threshold": False,
        "field_coordinates_used_to_define_patches": False,
        "prototype_count": int(len(prototypes)),
        "leave_one_out_worlds": int(len(kernel_scales)),
        "support_threshold": FROZEN_SUPPORT_THRESHOLD,
        "threshold_source": "research/campanula_development_freeze_v1.json",
        "selected_cells": int(len(selected_indices)),
        "expected_frozen_cells": EXPECTED_CANONICAL_CELLS,
        "selected_cell_fraction": float(len(selected_indices) / len(universe)),
        "patch_count": int(len(zones)),
        "merge_distance_m": float(base.MERGE_DISTANCE_M),
        "island_cell_counts": {str(k): int(v) for k, v in island_cells.items()},
        "island_patch_counts": {str(k): int(v) for k, v in island_patches.items()},
        "support_uncertainty_mean": float(np.mean(uncertainty[selected_mask])),
        "support_uncertainty_q95": float(np.quantile(uncertainty[selected_mask], 0.95)),
        "kernel_scale_min": float(np.min(kernel_scales)),
        "kernel_scale_max": float(np.max(kernel_scales)),
        "field_development_verification": field_result,
        "operational_contract": {
            "all_exported_patches_remain_ecologically_eligible": True,
            "patch_count_is_not_a_user_budget": True,
            "next_layer": "explicit movement graph -> directed round-trip reachability -> set-level coverage -> automatic effort knee",
            "straight_line_movement_fallback": False,
        },
    }

    # Hard reproducibility checks against the archived freeze.  A mismatch is a
    # scientific drift, not something to tune around.
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
        raise RuntimeError("frozen robust support envelope no longer reproduces its archived cell-count/recovery contract")


if __name__ == "__main__":
    main()
