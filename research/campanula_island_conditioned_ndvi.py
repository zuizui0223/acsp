#!/usr/bin/env python3
"""Development-only island-conditioned NDVI prototype search for Campanula.

All candidate scores are constructed from pre-2026 GBIF-derived prototypes plus
public NDVI. The 2026 field clusters are opened only after every score vector is
frozen and are used only to compare development frontiers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from campanula_ndvi_transition_discovery import ndvi_surfaces, sample_surfaces
from campanula_worldcover_discovery import (
    evaluate,
    matched_random_success,
    minimum_count_for_complete_recovery,
    nearest_environment,
    robust_fit,
    transform,
)

NDVI_STATE = [
    "ndvi_p50",
    "ndvi_amp",
    "ndvi_mean100",
    "ndvi_mean250",
    "ndvi_amp_mean100",
]


def prototype_distance(grid: pd.DataFrame, proto: pd.DataFrame) -> np.ndarray:
    usable_p = proto[NDVI_STATE].notna().all(axis=1)
    usable_g = grid[NDVI_STATE].notna().all(axis=1)
    out = np.full(len(grid), np.inf)
    if int(usable_p.sum()) < 3 or int(usable_g.sum()) < 1:
        return out
    med, scale = robust_fit(proto.loc[usable_p, NDVI_STATE].to_numpy(float))
    pz = transform(proto.loc[usable_p, NDVI_STATE].to_numpy(float), med, scale)
    gz = transform(grid.loc[usable_g, NDVI_STATE].to_numpy(float), med, scale)
    out[usable_g.to_numpy()] = nearest_environment(gz, pz)
    return out


def within_group_percentile(values: np.ndarray) -> np.ndarray:
    s = pd.Series(values).replace([np.inf, -np.inf], np.nan)
    finite = s.notna()
    out = np.ones(len(values), dtype=float)
    if finite.any():
        out[finite.to_numpy()] = s[finite].rank(method="average", pct=True).to_numpy(float)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--radius-km", type=float, default=1.0)
    parser.add_argument("--random-iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    lon = pd.concat([universe["lon"], prototypes["lon"]], ignore_index=True)
    lat = pd.concat([universe["lat"], prototypes["lat"]], ignore_index=True)

    # Generator stage: field outcomes are not visible here.
    with rasterio.open(args.ndvi) as src:
        tr, crs, surfaces = ndvi_surfaces(src, lon, lat)
        u_ndvi = sample_surfaces(tr, crs, surfaces, universe["lon"], universe["lat"])
        p_ndvi = sample_surfaces(tr, crs, surfaces, prototypes["lon"], prototypes["lat"])
    universe = pd.concat([universe.reset_index(drop=True), u_ndvi], axis=1)
    prototypes = pd.concat([prototypes.reset_index(drop=True), p_ndvi], axis=1)

    pooled_distance = prototype_distance(universe, prototypes)
    universe["pooled_ndvi_distance"] = pooled_distance
    global_score = within_group_percentile(pooled_distance)

    # Convert pooled and local distances to within-island percentiles so island
    # area does not determine candidate allocation by itself.
    pooled_island_score = np.ones(len(universe), dtype=float)
    local_island_score = np.ones(len(universe), dtype=float)
    prototype_counts: dict[str, int] = {}
    for island, idx in universe.groupby("island").groups.items():
        idx = np.asarray(list(idx), dtype=int)
        pooled_island_score[idx] = within_group_percentile(pooled_distance[idx])
        p = prototypes[prototypes["island"].eq(island)]
        prototype_counts[str(island)] = int(len(p))
        local_distance = prototype_distance(universe.loc[idx].reset_index(drop=True), p)
        if np.isfinite(local_distance).sum() >= 1:
            local_island_score[idx] = within_group_percentile(local_distance)
        else:
            local_island_score[idx] = pooled_island_score[idx]

    score_specs: dict[str, np.ndarray] = {
        "pooled_global_rank": global_score,
        "pooled_within_island_rank": pooled_island_score,
        "local_if_available": local_island_score,
    }
    for k in (1.0, 2.0, 4.0, 8.0, 16.0):
        score = pooled_island_score.copy()
        for island, idx in universe.groupby("island").groups.items():
            idx = np.asarray(list(idx), dtype=int)
            n = prototype_counts.get(str(island), 0)
            if n >= 3:
                lam = n / (n + k)
                score[idx] = lam * local_island_score[idx] + (1.0 - lam) * pooled_island_score[idx]
        score_specs[f"partial_pool_k{k:g}"] = score

    # Development evaluation stage starts only here.
    detections = pd.read_csv(args.detections)
    experiments = []
    candidates = {}
    for name, score in score_specs.items():
        order = np.argsort(score, kind="mergesort")
        count, witness = minimum_count_for_complete_recovery(
            universe, detections, order, args.radius_km
        )
        if count is None:
            continue
        chosen = universe.iloc[order[:count]].copy()
        result = evaluate(chosen, detections, args.radius_km)
        experiments.append({
            "score": name,
            "candidate_count": int(count),
            "grid_fraction": float(count / len(universe)),
            "detection_witness_ranks": [int(x) for x in witness],
            **result,
        })
        candidates[name] = chosen

    if not experiments:
        raise RuntimeError("No island-conditioned score recovered all development clusters")
    experiments.sort(key=lambda x: (x["candidate_count"], x["max_nearest_km"]))
    best = dict(experiments[0])
    chosen = candidates[best["score"]]
    best["matched_random"] = matched_random_success(
        universe,
        detections,
        chosen,
        args.radius_km,
        args.random_iterations,
        args.seed,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    chosen.to_csv(args.out / "best_island_conditioned_candidates.csv", index=False)
    universe.to_csv(args.out / "island_conditioned_scored_universe.csv", index=False)
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "feature_set": NDVI_STATE,
        "prototype_counts": prototype_counts,
        "experiments": experiments,
        "best": best,
    }
    (args.out / "island_conditioned_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
