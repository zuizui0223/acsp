#!/usr/bin/env python3
"""Development-only jackknife-consensus Campanula survey policy.

The previous Campanula development policy achieved complete 1-km recovery but
failed prototype-deletion robustness.  This script replaces direct dependence
on any one occurrence prototype with a deterministic jackknife consensus:

* cell support = median environmental support rank across all leave-one-prototype-out worlds;
* patch priority = median normalized rank across the same leave-one-out worlds,
  each using the already fixed spatial-policy coefficients.

No policy coefficient is searched here.  All jackknife support surfaces, patch
universes, and consensus orders are frozen before the inspected 2026 field
clusters are opened.  Field outcomes are then used only to measure the
Campanula development frontier and the explicit data-limited upper bound.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_patch_policy as base
import campanula_patch_policy_spatial as spatial
from campanula_patch_policy_fast import cached_prefix, json_safe_oracle
from campanula_persistent_patch_hash import fast_random_patch_audit
from campanula_spatial_policy_robustness import (
    AREA_COST_WEIGHT,
    GAP_WEIGHT,
    GEO_WEIGHT,
    NEW_COMPONENT_WEIGHT,
    SUPPORT_WEIGHT,
    DEFAULT_SEED,
)
from campanula_worldcover_discovery import evaluate

CELL_FRONTIER_FRACTIONS = (0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.50, 1.00)
PATCH_FRACTIONS = (0.05, 0.075, 0.10, 0.15)


def normalized_rank(order: list[int], n: int) -> np.ndarray:
    rank = np.full(n, 1.0, dtype=float)
    if n <= 1:
        if n == 1:
            rank[0] = 0.0
        return rank
    for position, index in enumerate(order):
        rank[int(index)] = float(position) / float(n - 1)
    return rank


def jackknife_worlds(universe: pd.DataFrame, prototypes: pd.DataFrame) -> list[dict]:
    worlds = []
    for removed in range(len(prototypes)):
        subset = prototypes.loc[prototypes.index != removed].reset_index(drop=True)
        responsibility, support_rank, proto_rows, kernel_scale = base.environmental_geometry(
            universe, subset
        )
        worlds.append(
            {
                "removed": int(removed),
                "responsibility": responsibility,
                "support_rank": support_rank,
                "proto_rows": proto_rows,
                "kernel_scale": float(kernel_scale),
            }
        )
    return worlds


def consensus_order_for_zones(
    universe: pd.DataFrame,
    zones: pd.DataFrame,
    consensus_support_rank: np.ndarray,
    worlds: list[dict],
) -> tuple[list[int], dict]:
    rank_vectors = []
    for world in worlds:
        matrix, support, area_cost, islands = base.patch_responsibilities(
            zones,
            world["responsibility"],
            consensus_support_rank,
        )
        gap, spatial_scale, islands, lat, lon = spatial.patch_spatial_features(
            zones,
            world["proto_rows"],
        )
        order = spatial.greedy_spatial_order(
            matrix,
            support,
            area_cost,
            islands,
            lat,
            lon,
            gap,
            spatial_scale,
            SUPPORT_WEIGHT,
            NEW_COMPONENT_WEIGHT,
            AREA_COST_WEIGHT,
            GEO_WEIGHT,
            GAP_WEIGHT,
        )
        rank_vectors.append(normalized_rank(order, len(zones)))

    stacked = np.vstack(rank_vectors)
    median_rank = np.median(stacked, axis=0)
    mean_rank = np.mean(stacked, axis=0)
    # Stable lexicographic ordering: consensus median, then mean, then zone ID.
    zone_ids = zones["zone_id"].astype(str).to_numpy()
    order = sorted(
        range(len(zones)),
        key=lambda index: (
            float(median_rank[index]),
            float(mean_rank[index]),
            str(zone_ids[index]),
        ),
    )
    diagnostics = {
        "n_jackknife_worlds": int(len(worlds)),
        "mean_patch_rank_sd": float(np.mean(np.std(stacked, axis=0))),
        "median_patch_rank_sd": float(np.median(np.std(stacked, axis=0))),
        "mean_pairwise_rank_correlation": None,
    }
    if len(rank_vectors) > 1:
        correlations = []
        for i in range(len(rank_vectors) - 1):
            for j in range(i + 1, len(rank_vectors)):
                value = np.corrcoef(rank_vectors[i], rank_vectors[j])[0, 1]
                if np.isfinite(value):
                    correlations.append(float(value))
        if correlations:
            diagnostics["mean_pairwise_rank_correlation"] = float(np.mean(correlations))
    return [int(value) for value in order], diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--random-iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    prototypes = prototypes.reset_index(drop=True)
    if len(prototypes) < 5:
        raise RuntimeError("Too few prototypes for jackknife consensus")

    # Generator stage: no 2026 outcomes are visible here.
    worlds = jackknife_worlds(universe, prototypes)
    support_stack = np.vstack([world["support_rank"] for world in worlds])
    consensus_support_rank = np.median(support_stack, axis=0)
    support_uncertainty = np.std(support_stack, axis=0)

    frozen_patch_designs = {}
    for fraction in PATCH_FRACTIONS:
        _, zones = base.make_zones(universe, consensus_support_rank, float(fraction))
        if zones.empty:
            continue
        order, rank_diagnostics = consensus_order_for_zones(
            universe,
            zones,
            consensus_support_rank,
            worlds,
        )
        frozen_patch_designs[float(fraction)] = {
            "zones": zones,
            "order": order,
            "rank_diagnostics": rank_diagnostics,
        }

    # Development scoring starts only here.
    detections = pd.read_csv(args.detections)

    cell_frontier = []
    for fraction in CELL_FRONTIER_FRACTIONS:
        selected = universe.loc[consensus_support_rank <= float(fraction)]
        result = evaluate(selected, detections, 1.0)
        cell_frontier.append(
            {
                "support_fraction": float(fraction),
                "n_cells": int(len(selected)),
                "grid_fraction": float(len(selected) / len(universe)),
                **result,
            }
        )

    patch_results = []
    for fraction, design in frozen_patch_designs.items():
        zones = design["zones"]
        ranked = base.ranked_zones_for_order(zones, design["order"])
        frontier = cached_prefix(universe, ranked, detections, 1.0)
        fixed32_ids = design["order"][: min(32, len(design["order"]))]
        fixed32_zones = zones.iloc[fixed32_ids]
        fixed32_cells: set[int] = set()
        for _, zone in fixed32_zones.iterrows():
            fixed32_cells.update(base.patch.member_indices(zone))
        fixed32_result = evaluate(
            universe.loc[sorted(fixed32_cells)], detections, 1.0
        ) if fixed32_cells else {
            "recovered": 0,
            "total": int(len(detections)),
            "max_nearest_km": float("inf"),
            "nearest_km": [float("inf")] * len(detections),
        }
        row = {
            "support_fraction": float(fraction),
            "total_patch_universe": int(len(zones)),
            "rank_diagnostics": design["rank_diagnostics"],
            "fixed_32": {
                "n_patches": int(len(fixed32_zones)),
                "n_cells": int(len(fixed32_cells)),
                "grid_fraction": float(len(fixed32_cells) / len(universe)),
                "island_patch_counts": {
                    str(key): int(value)
                    for key, value in fixed32_zones["survey_area_id"]
                    .astype(str)
                    .value_counts()
                    .to_dict()
                    .items()
                },
                "selected_zone_ids": fixed32_zones["zone_id"].astype(str).tolist(),
                **fixed32_result,
            },
            "complete_recovery_prefix": frontier,
            "oracle_set_cover": json_safe_oracle(universe, zones, detections, 1.0),
        }
        patch_results.append(row)

    complete_prefixes = [
        row for row in patch_results
        if row["complete_recovery_prefix"] is not None
    ]
    best = None
    if complete_prefixes:
        best = min(
            complete_prefixes,
            key=lambda row: (
                row["complete_recovery_prefix"]["n_patches"],
                row["complete_recovery_prefix"]["n_cells"],
                row["support_fraction"],
            ),
        )
        zones = frozen_patch_designs[best["support_fraction"]]["zones"]
        best["complete_recovery_prefix"]["matched_random_patches"] = fast_random_patch_audit(
            universe,
            zones,
            detections,
            best["complete_recovery_prefix"],
            1.0,
            args.random_iterations,
            args.seed,
        )

    minimum_complete_cell_fraction = None
    for row in cell_frontier:
        if row["recovered"] == row["total"]:
            minimum_complete_cell_fraction = row
            break

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                key: value
                for key, value in row.items()
                if key not in {"nearest_km"}
            }
            for row in cell_frontier
        ]
    ).to_csv(args.out / "jackknife_consensus_cell_frontier.csv", index=False)
    report = {
        "status": "development_only_jackknife_consensus",
        "field_coordinates_used_by_generator": False,
        "policy_weights_were_searched_in_this_experiment": False,
        "prototype_count": int(len(prototypes)),
        "n_jackknife_worlds": int(len(worlds)),
        "support_consensus": "median leave-one-prototype-out environmental support rank",
        "patch_consensus": "median normalized fixed-policy patch rank across leave-one-prototype-out worlds",
        "fixed_policy_weights": {
            "support_weight": SUPPORT_WEIGHT,
            "new_component_weight": NEW_COMPONENT_WEIGHT,
            "area_cost_weight": AREA_COST_WEIGHT,
            "geo_weight": GEO_WEIGHT,
            "gap_weight": GAP_WEIGHT,
            "merge_distance_m": base.MERGE_DISTANCE_M,
        },
        "support_rank_uncertainty": {
            "mean_sd": float(np.mean(support_uncertainty)),
            "median_sd": float(np.median(support_uncertainty)),
            "q95_sd": float(np.quantile(support_uncertainty, 0.95)),
        },
        "cell_frontier": cell_frontier,
        "minimum_complete_cell_fraction": minimum_complete_cell_fraction,
        "patch_results": patch_results,
        "best_complete_patch_policy": best,
        "interpretation": (
            "If complete recovery requires a broad consensus support fraction or "
            "many consensus patches, that is the explicit robustness-limited "
            "upper bound of the current public data and pre-2026 occurrence set."
        ),
    }
    (args.out / "jackknife_consensus_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
