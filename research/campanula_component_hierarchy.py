#!/usr/bin/env python3
"""Development-only disconnected-component hierarchy for Campanula NDVI support.

The experiment treats each island as a disconnected land component, not as a
field-outcome label. Candidate scores are frozen from pre-2026 occurrence
prototypes and public NDVI before the 2026 detections are read.

Sparse components shrink toward global occurrence support; components without
training records can transfer from the geographically nearest component that has
pre-2026 occurrence prototypes. The same logic can later be generalized to
other disconnected survey components.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from campanula_fast_random import fast_matched_random_success
from campanula_ndvi_transition_discovery import ndvi_surfaces, sample_surfaces
from campanula_worldcover_discovery import (
    evaluate,
    haversine_km,
    minimum_count_for_complete_recovery,
    robust_fit,
    transform,
)

FULL_STATE = [
    "ndvi_p50",
    "ndvi_amp",
    "ndvi_mean100",
    "ndvi_mean250",
    "ndvi_amp_mean100",
]


def _rank(values):
    return pd.Series(values).rank(method="average", pct=True).to_numpy(float)


def add_ndvi(universe, prototypes, path):
    all_lon = pd.concat([universe["lon"], prototypes["lon"]], ignore_index=True)
    all_lat = pd.concat([universe["lat"], prototypes["lat"]], ignore_index=True)
    with rasterio.open(path) as src:
        tr, crs, surfaces = ndvi_surfaces(src, all_lon, all_lat)
        ug = sample_surfaces(tr, crs, surfaces, universe["lon"], universe["lat"])
        pg = sample_surfaces(tr, crs, surfaces, prototypes["lon"], prototypes["lat"])
    return (
        pd.concat([universe.reset_index(drop=True), ug], axis=1),
        pd.concat([prototypes.reset_index(drop=True), pg], axis=1),
    )


def component_centers(universe):
    return universe.groupby("island")[["lat", "lon"]].mean().to_dict("index")


def nearest_source_components(universe, prototypes):
    centers = component_centers(universe)
    sources = sorted(set(prototypes["island"].dropna().astype(str)))
    mapping = {}
    for target, center in centers.items():
        if target in sources:
            mapping[target] = target
            continue
        distances = []
        for source in sources:
            source_center = centers[source]
            d = float(
                haversine_km(
                    center["lat"],
                    center["lon"],
                    np.asarray([source_center["lat"]]),
                    np.asarray([source_center["lon"]]),
                )[0]
            )
            distances.append((d, source))
        mapping[target] = min(distances)[1]
    return mapping


def build_score_families(universe, prototypes):
    proto_ok = prototypes[FULL_STATE].notna().all(axis=1)
    grid_ok = universe[FULL_STATE].notna().all(axis=1)
    median, scale = robust_fit(prototypes.loc[proto_ok, FULL_STATE].to_numpy(float))
    proto_z = transform(prototypes.loc[proto_ok, FULL_STATE].to_numpy(float), median, scale)
    grid_z = transform(universe.loc[grid_ok, FULL_STATE].to_numpy(float), median, scale)
    proto_meta = prototypes.loc[proto_ok, ["island"]].reset_index(drop=True)
    grid_indices = np.flatnonzero(grid_ok.to_numpy())

    all_distances = np.sqrt(
        np.square(grid_z[:, None, :] - proto_z[None, :, :]).sum(axis=2)
    )
    global_nearest_valid = all_distances.min(axis=1)
    global_score = np.full(len(universe), np.inf)
    global_score[grid_indices] = global_nearest_valid

    source_mapping = nearest_source_components(universe, prototypes.loc[proto_ok])
    prototype_counts = proto_meta["island"].value_counts().to_dict()

    local_nearest = np.full(len(universe), np.inf)
    local_persistent = np.full(len(universe), np.inf)
    transfer_nearest = np.full(len(universe), np.inf)
    local_available = np.zeros(len(universe), dtype=int)

    valid_islands = universe.loc[grid_ok, "island"].astype(str).to_numpy()
    for island in sorted(set(valid_islands)):
        candidate_local = np.flatnonzero(valid_islands == island)
        universe_indices = grid_indices[candidate_local]
        local_proto = np.flatnonzero(proto_meta["island"].astype(str).to_numpy() == island)
        n_local = len(local_proto)
        local_available[universe_indices] = n_local
        if n_local:
            d = all_distances[candidate_local][:, local_proto]
            local_nearest[universe_indices] = d.min(axis=1)
            if n_local >= 2:
                local_persistent[universe_indices] = np.partition(d, 1, axis=1)[:, 1]
            else:
                local_persistent[universe_indices] = d[:, 0]
        source = source_mapping[island]
        source_proto = np.flatnonzero(proto_meta["island"].astype(str).to_numpy() == source)
        transfer_nearest[universe_indices] = all_distances[candidate_local][:, source_proto].min(axis=1)

    # If a component has no local occurrence, local support is undefined and the
    # hierarchical scores fall back to global or nearest-component transfer.
    no_local = local_available == 0
    local_or_global = local_nearest.copy()
    local_or_global[no_local] = global_score[no_local]
    persistent_or_global = local_persistent.copy()
    persistent_or_global[no_local] = global_score[no_local]
    local_or_transfer = local_nearest.copy()
    local_or_transfer[no_local] = transfer_nearest[no_local]
    persistent_or_transfer = local_persistent.copy()
    persistent_or_transfer[no_local] = transfer_nearest[no_local]

    families = {
        "global_nearest": global_score,
        "component_nearest_global_fallback": local_or_global,
        "component_persistent_global_fallback": persistent_or_global,
        "component_nearest_transfer_fallback": local_or_transfer,
        "component_persistent_transfer_fallback": persistent_or_transfer,
    }

    # Empirical-Bayes-style shrinkage strength is determined only by the number
    # of pre-2026 prototypes in the component. No field outcomes enter alpha.
    for kappa in (0.5, 1.0, 2.0, 4.0, 8.0):
        n = local_available.astype(float)
        alpha = n / (n + kappa)
        local = local_nearest.copy()
        local[no_local] = global_score[no_local]
        persistent = local_persistent.copy()
        persistent[no_local] = global_score[no_local]
        families[f"shrink_nearest_kappa_{kappa:g}"] = (
            alpha * local + (1.0 - alpha) * global_score
        )
        families[f"shrink_persistent_kappa_{kappa:g}"] = (
            alpha * persistent + (1.0 - alpha) * global_score
        )

    # Rank-fusion versions test whether scale rather than ecological support is
    # the issue. All component ranks are computed before field outcomes are read.
    global_rank = _rank(global_score)
    for label in (
        "component_nearest_global_fallback",
        "component_persistent_global_fallback",
        "component_nearest_transfer_fallback",
    ):
        component_rank = _rank(families[label])
        families[f"rank_and_{label}"] = np.maximum(global_rank, component_rank)
        families[f"rank_mean_{label}"] = 0.5 * (global_rank + component_rank)

    metadata = {
        "prototype_counts": {str(k): int(v) for k, v in prototype_counts.items()},
        "nearest_source_component": source_mapping,
    }
    return families, metadata


def frontier_for_radius(universe, detections, score_families, radius_km):
    rows = []
    orders = {}
    for name, values in score_families.items():
        order = np.argsort(values, kind="mergesort")
        count, witness = minimum_count_for_complete_recovery(
            universe, detections, order, radius_km
        )
        if count is None:
            continue
        chosen = universe.iloc[order[:count]]
        result = evaluate(chosen, detections, radius_km)
        rows.append(
            {
                "method": name,
                "radius_km": float(radius_km),
                "candidate_count": int(count),
                "grid_fraction": float(count / len(universe)),
                "detection_witness_ranks": [int(x) for x in witness],
                **result,
            }
        )
        orders[name] = order
    rows.sort(key=lambda row: (row["candidate_count"], row["max_nearest_km"]))
    return rows, orders


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--random-iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = add_ndvi(universe, prototypes, args.ndvi)

    # Generator stage ends here: every hierarchy score is frozen before 2026 data.
    score_families, hierarchy_metadata = build_score_families(universe, prototypes)

    detections = pd.read_csv(args.detections)
    frontiers = {}
    orders_by_radius = {}
    for radius in (1.0, 0.5):
        rows, orders = frontier_for_radius(universe, detections, score_families, radius)
        frontiers[str(radius)] = rows
        orders_by_radius[str(radius)] = orders

    one_km = frontiers["1.0"]
    if not one_km:
        raise RuntimeError("No hierarchy configuration reached 19/19 at 1 km")

    # Audit every 1-km method that beats the previous 867-cell frontier. Fast
    # coverage precomputation makes 5,000 matched draws cheap enough to retain all.
    audited = []
    for i, row in enumerate(one_km):
        if row["candidate_count"] >= 867:
            continue
        order = orders_by_radius["1.0"][row["method"]]
        chosen = universe.iloc[order[: row["candidate_count"]]]
        copy = dict(row)
        copy["matched_random"] = fast_matched_random_success(
            universe,
            detections,
            chosen,
            1.0,
            args.random_iterations,
            args.seed + i * 1009,
        )
        copy["joint_improvement_vs_ndvi_state"] = bool(
            copy["candidate_count"] < 867
            and copy["matched_random"]["complete_recovery_probability"] < 0.2975
        )
        audited.append(copy)

    promoted = [row for row in audited if row["joint_improvement_vs_ndvi_state"]]
    best_promoted = None
    if promoted:
        best_promoted = min(
            promoted,
            key=lambda row: (
                row["candidate_count"],
                row["matched_random"]["complete_recovery_probability"],
            ),
        )

    best_one_km = one_km[0]
    best_half_km = frontiers["0.5"][0] if frontiers["0.5"] else None
    export_row = best_promoted or best_one_km
    export_order = orders_by_radius["1.0"][export_row["method"]]
    export_candidates = universe.iloc[export_order[: export_row["candidate_count"]]].copy()

    args.out.mkdir(parents=True, exist_ok=True)
    export_candidates.to_csv(args.out / "best_component_hierarchy_candidates.csv", index=False)
    pd.DataFrame(one_km).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "component_hierarchy_frontier_1km.csv", index=False
    )
    pd.DataFrame(frontiers["0.5"]).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "component_hierarchy_frontier_500m.csv", index=False
    )
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "hierarchy": hierarchy_metadata,
        "prior_joint_frontier": {
            "candidate_count": 867,
            "grid_fraction": 867 / len(universe),
            "matched_random_complete_probability": 0.2975,
        },
        "frontier_1km": one_km,
        "frontier_500m": frontiers["0.5"],
        "random_audited_below_prior_count": audited,
        "best_promoted": best_promoted,
        "best_count_only_1km": best_one_km,
        "best_count_only_500m": best_half_km,
    }
    (args.out / "component_hierarchy_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
