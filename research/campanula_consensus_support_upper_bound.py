#!/usr/bin/env python3
"""Exact robustness-limited support envelope for Campanula development.

This is not another policy search.  It quantifies the support fraction required
for complete field-cluster recovery after jackknife consensus is reconstructed
under every outer leave-one-prototype-out dataset.

For a frozen consensus support surface and a declared distance radius, the exact
minimum threshold is:

    max_detection min_reachable_cell support_rank(cell)

Thus the result is an explicit data-limited upper bound, not a tuned classifier
score.  Pair-deletion support surfaces are built from pre-2026 occurrences and
public NDVI before the inspected 2026 field clusters are opened.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_patch_policy as base
from campanula_worldcover_discovery import evaluate, haversine_km

RADII_KM = (1.0, 0.5)


def support_rank_for_subset(
    universe: pd.DataFrame,
    prototypes: pd.DataFrame,
    removed: tuple[int, ...],
) -> np.ndarray:
    keep = ~prototypes.index.isin(removed)
    subset = prototypes.loc[keep].reset_index(drop=True)
    _, support_rank, _, _ = base.environmental_geometry(universe, subset)
    return support_rank.astype("float32", copy=False)


def exact_required_threshold(
    universe: pd.DataFrame,
    support_rank: np.ndarray,
    detections: pd.DataFrame,
    radius_km: float,
) -> dict:
    witnesses = []
    required = 0.0
    for _, point in detections.iterrows():
        island = str(point["island"])
        indices = np.flatnonzero(universe["island"].astype(str).eq(island).to_numpy())
        if not len(indices):
            witnesses.append(
                {
                    "detection_cluster_id": int(point["detection_cluster_id"]),
                    "island": island,
                    "minimum_reachable_support_rank": None,
                }
            )
            return {
                "status": "unreachable_no_island_cells",
                "required_support_threshold": None,
                "witnesses": witnesses,
            }
        d = haversine_km(
            float(point["latitude"]),
            float(point["longitude"]),
            universe.iloc[indices]["lat"].to_numpy(float),
            universe.iloc[indices]["lon"].to_numpy(float),
        )
        reachable = indices[np.asarray(d) <= float(radius_km)]
        if not len(reachable):
            witnesses.append(
                {
                    "detection_cluster_id": int(point["detection_cluster_id"]),
                    "island": island,
                    "minimum_reachable_support_rank": None,
                }
            )
            return {
                "status": "unreachable_no_grid_cell_within_radius",
                "required_support_threshold": None,
                "witnesses": witnesses,
            }
        minimum = float(np.min(support_rank[reachable]))
        required = max(required, minimum)
        witnesses.append(
            {
                "detection_cluster_id": int(point["detection_cluster_id"]),
                "island": island,
                "minimum_reachable_support_rank": minimum,
            }
        )

    selected = np.flatnonzero(support_rank <= required + 1e-12)
    result = evaluate(universe.loc[selected], detections, radius_km)
    if result["recovered"] != len(detections):
        raise RuntimeError("exact support-threshold calculation failed its recovery audit")
    return {
        "status": "complete",
        "required_support_threshold": float(required),
        "n_cells_at_required_threshold": int(len(selected)),
        "grid_fraction_at_required_threshold": float(len(selected) / len(universe)),
        "max_nearest_km": float(result["max_nearest_km"]),
        "witnesses": witnesses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    prototypes = prototypes.reset_index(drop=True)
    n = len(prototypes)
    if n < 6:
        raise RuntimeError("Too few prototypes for nested consensus upper bound")

    # Generator stage only: precompute support ranks for every unique single and
    # pair deletion before field coordinates are opened.
    single = {
        i: support_rank_for_subset(universe, prototypes, (i,))
        for i in range(n)
    }
    pair = {
        tuple(indices): support_rank_for_subset(universe, prototypes, tuple(indices))
        for indices in itertools.combinations(range(n), 2)
    }

    consensus_surfaces = {
        "canonical": np.median(np.vstack([single[i] for i in range(n)]), axis=0)
    }
    for outer in range(n):
        worlds = [
            pair[tuple(sorted((outer, inner)))]
            for inner in range(n)
            if inner != outer
        ]
        consensus_surfaces[f"outer_{outer}"] = np.median(np.vstack(worlds), axis=0)

    # Development scoring starts only here.
    detections = pd.read_csv(args.detections)
    results = {}
    for name, surface in consensus_surfaces.items():
        results[name] = {
            f"{radius:g}km": exact_required_threshold(
                universe, surface, detections, radius
            )
            for radius in RADII_KM
        }

    robust_thresholds = {}
    for radius in RADII_KM:
        key = f"{radius:g}km"
        outer_values = [
            results[f"outer_{outer}"][key]["required_support_threshold"]
            for outer in range(n)
        ]
        finite = [float(value) for value in outer_values if value is not None]
        robust_threshold = max(finite) if len(finite) == n else None
        robust_thresholds[key] = {
            "all_outer_reconstructions_reachable": bool(len(finite) == n),
            "max_required_support_threshold": robust_threshold,
            "mean_required_support_threshold": float(np.mean(finite))
            if finite
            else None,
            "median_required_support_threshold": float(np.median(finite))
            if finite
            else None,
            "q95_required_support_threshold": float(np.quantile(finite, 0.95))
            if finite
            else None,
        }
        if robust_threshold is not None:
            canonical_surface = consensus_surfaces["canonical"]
            selected = np.flatnonzero(canonical_surface <= robust_threshold + 1e-12)
            robust_thresholds[key]["canonical_cells_at_robust_threshold"] = int(
                len(selected)
            )
            robust_thresholds[key]["canonical_grid_fraction_at_robust_threshold"] = float(
                len(selected) / len(universe)
            )
            robust_thresholds[key]["canonical_recovery_at_robust_threshold"] = evaluate(
                universe.loc[selected], detections, radius
            )

    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, by_radius in results.items():
        for radius_key, value in by_radius.items():
            rows.append(
                {
                    "reconstruction": name,
                    "radius": radius_key,
                    "required_support_threshold": value.get(
                        "required_support_threshold"
                    ),
                    "n_cells_at_required_threshold": value.get(
                        "n_cells_at_required_threshold"
                    ),
                    "grid_fraction_at_required_threshold": value.get(
                        "grid_fraction_at_required_threshold"
                    ),
                    "max_nearest_km": value.get("max_nearest_km"),
                    "status": value.get("status"),
                }
            )
    pd.DataFrame(rows).to_csv(
        args.out / "consensus_support_upper_bound.csv", index=False
    )
    report = {
        "status": "development_only_robust_support_upper_bound",
        "field_coordinates_used_by_generator": False,
        "policy_or_feature_weights_searched": False,
        "prototype_count": int(n),
        "consensus_definition": (
            "median support rank across internal leave-one-prototype-out worlds"
        ),
        "radii_km": list(RADII_KM),
        "robust_thresholds": robust_thresholds,
        "reconstructions": results,
        "interpretation": (
            "The maximum outer-LOO required threshold is the fixed support "
            "fraction needed to guarantee complete Campanula development "
            "recovery under any single pre-2026 prototype deletion. It is an "
            "upper-bound diagnostic, not a probability of occurrence."
        ),
    }
    (args.out / "consensus_support_upper_bound_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
