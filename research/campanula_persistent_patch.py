#!/usr/bin/env python3
"""Development-only persistent survey-patch compression for Campanula.

The environmental support surface is built from pre-2026 GBIF prototypes and
the pinned ESA annual NDVI composite. Candidate cells are converted to bounded
complete-link zones with the existing ACSP zone aggregator. The inspected 2026
field clusters are read only after every support threshold / merge-distance
patch universe has been constructed.

The experiment asks a different question from per-cell ranking: how many
continuous survey patches, and how much total patch area, are required to retain
complete field-cluster recovery?
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from acsp.planning import aggregate_candidates_to_zones
from campanula_ndvi_transition_discovery import distance_rank, ndvi_surfaces, sample_surfaces
from campanula_worldcover_discovery import evaluate

FULL_NDVI = [
    "ndvi_p50",
    "ndvi_amp",
    "ndvi_mean100",
    "ndvi_mean250",
    "ndvi_amp_mean100",
]
SUPPORT_FRACTIONS = (0.02, 0.03, 0.0381, 0.05, 0.075, 0.10, 0.15, 0.20)
MERGE_DISTANCES_M = (200.0, 300.0, 500.0, 750.0, 1000.0)


def attach_ndvi(universe, prototypes, ndvi_path):
    all_lon = pd.concat([universe["lon"], prototypes["lon"]], ignore_index=True)
    all_lat = pd.concat([universe["lat"], prototypes["lat"]], ignore_index=True)
    with rasterio.open(ndvi_path) as src:
        transform_, crs, surfaces = ndvi_surfaces(src, all_lon, all_lat)
        grid = sample_surfaces(transform_, crs, surfaces, universe["lon"], universe["lat"])
        proto = sample_surfaces(transform_, crs, surfaces, prototypes["lon"], prototypes["lat"])
    return (
        pd.concat([universe.reset_index(drop=True), grid], axis=1),
        pd.concat([prototypes.reset_index(drop=True), proto], axis=1),
    )


def make_patch_universe(universe, support_rank, fraction, merge_distance_m):
    keep = support_rank <= float(fraction)
    cells = universe.loc[keep].copy().reset_index(drop=False).rename(
        columns={"index": "universe_index", "lat": "latitude", "lon": "longitude"}
    )
    if cells.empty:
        return cells, pd.DataFrame()
    cells["site_id"] = cells["universe_index"].astype(str)
    cells["survey_area_id"] = cells["island"].astype(str)
    cells["priority_score"] = 1.0 - support_rank[keep]
    cells["candidate_type"] = "NDVI-support patch cell"
    cells["access_score"] = 0.5
    cells["evidence_agreement_score"] = 0.0
    zones = aggregate_candidates_to_zones(
        cells,
        merge_distance_m=float(merge_distance_m),
        area_col="survey_area_id",
        latitude_col="latitude",
        longitude_col="longitude",
        id_col="site_id",
        score_col="priority_score",
    )
    return cells, zones


def member_indices(row):
    text = str(row.get("zone_member_site_ids", ""))
    return [int(value) for value in text.split(";") if value != ""]


def prefix_patch_frontier(universe, zones, detections, radius_km):
    if zones.empty:
        return None
    order = zones.sort_values(["zone_score", "zone_id"], ascending=[False, True], kind="mergesort")
    selected_indices = set()
    for n_patches, (_, zone) in enumerate(order.iterrows(), start=1):
        selected_indices.update(member_indices(zone))
        chosen = universe.loc[sorted(selected_indices)]
        result = evaluate(chosen, detections, radius_km)
        if result["recovered"] == len(detections):
            selected_zones = order.iloc[:n_patches].copy()
            island_patch_counts = selected_zones["survey_area_id"].astype(str).value_counts().to_dict()
            return {
                "n_patches": int(n_patches),
                "n_cells": int(len(selected_indices)),
                "grid_fraction": float(len(selected_indices) / len(universe)),
                "estimated_cell_area_km2": float(len(selected_indices) * 0.01),
                "island_patch_counts": {str(k): int(v) for k, v in island_patch_counts.items()},
                "selected_zone_ids": selected_zones["zone_id"].astype(str).tolist(),
                **result,
            }
    return None


def random_patch_audit(universe, zones, detections, observed, radius_km, iterations, seed):
    """Random patch sets matched on island-specific patch counts.

    Patch area is reported for every draw. This is a first operational control;
    a future route-budget benchmark can additionally match travel time.
    """
    rng = np.random.default_rng(seed)
    groups = {str(area): frame.copy() for area, frame in zones.groupby("survey_area_id")}
    recoveries = []
    cell_counts = []
    complete = 0
    for _ in range(int(iterations)):
        selected_indices = set()
        feasible = True
        for island, count in observed["island_patch_counts"].items():
            frame = groups.get(str(island))
            if frame is None or len(frame) < int(count):
                feasible = False
                break
            draw = rng.choice(frame.index.to_numpy(), size=int(count), replace=False)
            for idx in draw:
                selected_indices.update(member_indices(frame.loc[idx]))
        if not feasible or not selected_indices:
            continue
        result = evaluate(universe.loc[sorted(selected_indices)], detections, radius_km)
        recoveries.append(result["recovered"])
        cell_counts.append(len(selected_indices))
        complete += int(result["recovered"] == len(detections))
    n = len(recoveries)
    return {
        "iterations_requested": int(iterations),
        "iterations_evaluated": int(n),
        "complete_recovery_probability": float(complete / n) if n else None,
        "mean_recovered": float(np.mean(recoveries)) if n else None,
        "mean_cells": float(np.mean(cell_counts)) if n else None,
        "q05_cells": float(np.quantile(cell_counts, 0.05)) if n else None,
        "q95_cells": float(np.quantile(cell_counts, 0.95)) if n else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--random-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = attach_ndvi(universe, prototypes, args.ndvi)
    distance, support_rank = distance_rank(universe, prototypes, FULL_NDVI)
    universe["ndvi_state_nn"] = distance
    universe["ndvi_state_rank"] = support_rank

    # Generator stage: all patch universes are frozen before field outcomes open.
    patch_universes = {}
    for fraction in SUPPORT_FRACTIONS:
        for merge_distance in MERGE_DISTANCES_M:
            cells, zones = make_patch_universe(universe, support_rank, fraction, merge_distance)
            patch_universes[(fraction, merge_distance)] = (cells, zones)

    detections = pd.read_csv(args.detections)
    experiments = []
    zone_exports = {}
    for (fraction, merge_distance), (_, zones) in patch_universes.items():
        for radius in (1.0, 0.5):
            frontier = prefix_patch_frontier(universe, zones, detections, radius)
            if frontier is None:
                continue
            row = {
                "support_fraction": float(fraction),
                "merge_distance_m": float(merge_distance),
                "radius_km": float(radius),
                "total_patch_universe": int(len(zones)),
                **frontier,
            }
            experiments.append(row)
            zone_exports[(fraction, merge_distance)] = zones

    one_km = [row for row in experiments if row["radius_km"] == 1.0]
    if not one_km:
        raise RuntimeError("No patch configuration recovered all 19 clusters at 1 km")
    # Operational objective is lexicographic: fewer field patches first, then
    # smaller total searched grid area, then lower merge diameter.
    one_km.sort(key=lambda row: (row["n_patches"], row["n_cells"], row["merge_distance_m"]))
    audit_pool = one_km[: min(10, len(one_km))]
    for i, row in enumerate(audit_pool):
        zones = zone_exports[(row["support_fraction"], row["merge_distance_m"])]
        row["matched_random_patches"] = random_patch_audit(
            universe, zones, detections, row, 1.0, args.random_iterations, args.seed + i * 1009
        )

    # Prefer fewer patches, then lower matched-random success, then less area.
    best = min(
        audit_pool,
        key=lambda row: (
            row["n_patches"],
            row["matched_random_patches"]["complete_recovery_probability"]
            if row["matched_random_patches"]["complete_recovery_probability"] is not None else 1.0,
            row["n_cells"],
        ),
    )
    best_zones = zone_exports[(best["support_fraction"], best["merge_distance_m"])]
    selected_zone_ids = set(best["selected_zone_ids"])
    best_zone_rows = best_zones[best_zones["zone_id"].astype(str).isin(selected_zone_ids)].copy()

    half_km = [row for row in experiments if row["radius_km"] == 0.5]
    half_km.sort(key=lambda row: (row["n_patches"], row["n_cells"], row["merge_distance_m"]))

    args.out.mkdir(parents=True, exist_ok=True)
    best_zone_rows.to_csv(args.out / "best_persistent_patches.csv", index=False)
    pd.DataFrame(experiments).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "persistent_patch_frontier.csv", index=False
    )
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "support_source": "pre-2026 GBIF occurrence-conditioned ESA 2021 NDVI state",
        "zone_algorithm": "existing ACSP deterministic complete-link aggregation",
        "support_fractions": list(SUPPORT_FRACTIONS),
        "merge_distances_m": list(MERGE_DISTANCES_M),
        "experiments": experiments,
        "best_1km": best,
        "best_count_only_500m": half_km[0] if half_km else None,
    }
    (args.out / "persistent_patch_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
