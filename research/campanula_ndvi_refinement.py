#!/usr/bin/env python3
"""Refine the Campanula NDVI discovery frontier without changing the data boundary.

All candidate score families are constructed from pre-2026 GBIF-derived
prototypes, the frozen full-island microterrain universe, and the public ESA
WorldCover NDVI composite. The inspected 2026 field clusters are read only after
all score vectors have been frozen. They are development loss, never generator
inputs.

This experiment asks whether the current 3.805% complete-recovery frontier can
be compressed by (1) NDVI-state ablation, (2) support from more than one
occurrence prototype, or (3) occurrence-derived environmental modes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from sklearn.cluster import KMeans

from campanula_ndvi_transition_discovery import ndvi_surfaces, sample_surfaces
from campanula_worldcover_discovery import (
    evaluate,
    matched_random_success,
    minimum_count_for_complete_recovery,
    robust_fit,
    transform,
)

FEATURE_SETS = {
    "p50_only": ["ndvi_p50"],
    "p50_amplitude": ["ndvi_p50", "ndvi_amp"],
    "local_means": ["ndvi_mean100", "ndvi_mean250"],
    "compact_state": ["ndvi_p50", "ndvi_amp", "ndvi_mean100"],
    "full_state": [
        "ndvi_p50",
        "ndvi_amp",
        "ndvi_mean100",
        "ndvi_mean250",
        "ndvi_amp_mean100",
    ],
}


def _rank(values: np.ndarray) -> np.ndarray:
    return pd.Series(values).rank(method="average", pct=True).to_numpy(float)


def standardized_matrices(universe: pd.DataFrame, prototypes: pd.DataFrame, columns):
    columns = list(columns)
    proto_ok = prototypes[columns].notna().all(axis=1)
    grid_ok = universe[columns].notna().all(axis=1)
    if proto_ok.sum() < 3 or grid_ok.sum() < 1:
        return None
    median, scale = robust_fit(prototypes.loc[proto_ok, columns].to_numpy(float))
    proto_z = transform(prototypes.loc[proto_ok, columns].to_numpy(float), median, scale)
    grid_z = transform(universe.loc[grid_ok, columns].to_numpy(float), median, scale)
    return proto_ok, grid_ok, proto_z, grid_z


def individual_support_scores(universe, prototypes, columns):
    """Nearest and leave-one-prototype-out persistent support scores."""
    matrices = standardized_matrices(universe, prototypes, columns)
    if matrices is None:
        return {}
    _, grid_ok, proto_z, grid_z = matrices
    # 22k x ~18 is small enough to calculate exactly and makes the persistence
    # definition auditable. With a fixed transform, the second-nearest distance
    # is the worst nearest distance after deleting the closest single prototype.
    d = np.sqrt(np.square(grid_z[:, None, :] - proto_z[None, :, :]).sum(axis=2))
    ordered = np.partition(d, kth=min(1, d.shape[1] - 1), axis=1)
    nearest = ordered[:, 0]
    second = ordered[:, min(1, d.shape[1] - 1)]
    mean_two = 0.5 * (nearest + second)
    outputs = {}
    for name, values in {
        "nearest_occurrence": nearest,
        "persistent_second": second,
        "persistent_mean_two": mean_two,
    }.items():
        full = np.full(len(universe), np.inf)
        full[grid_ok.to_numpy()] = values
        outputs[name] = full
    return outputs


def mode_support_scores(universe, prototypes, columns, seed):
    """Distance to deterministic occurrence-derived environmental modes."""
    matrices = standardized_matrices(universe, prototypes, columns)
    if matrices is None:
        return {}
    _, grid_ok, proto_z, grid_z = matrices
    outputs = {}
    max_k = min(6, len(proto_z) - 1)
    for k in range(2, max_k + 1):
        model = KMeans(n_clusters=k, random_state=seed, n_init=50)
        model.fit(proto_z)
        centers = model.cluster_centers_
        d2 = np.square(grid_z[:, None, :] - centers[None, :, :]).sum(axis=2)
        centroid_distance = np.sqrt(d2.min(axis=1))
        full = np.full(len(universe), np.inf)
        full[grid_ok.to_numpy()] = centroid_distance
        outputs[f"kmeans_centroid_k{k}"] = full

        # A medoid version keeps every environmental mode anchored to an actual
        # pre-2026 occurrence rather than an interpolated centroid.
        medoids = []
        for center in centers:
            medoids.append(proto_z[np.argmin(np.square(proto_z - center).sum(axis=1))])
        medoids = np.asarray(medoids)
        md2 = np.square(grid_z[:, None, :] - medoids[None, :, :]).sum(axis=2)
        medoid_distance = np.sqrt(md2.min(axis=1))
        full_medoid = np.full(len(universe), np.inf)
        full_medoid[grid_ok.to_numpy()] = medoid_distance
        outputs[f"kmeans_medoid_k{k}"] = full_medoid
    return outputs


def build_ndvi_tables(universe, prototypes, ndvi_path):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--radius-km", type=float, default=1.0)
    parser.add_argument("--random-iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = build_ndvi_tables(universe, prototypes, args.ndvi)

    # Generator stage. Every score below is frozen before field outcomes are read.
    score_families = {}
    for feature_name, columns in FEATURE_SETS.items():
        for method, distance in individual_support_scores(universe, prototypes, columns).items():
            score_families[(feature_name, method)] = _rank(distance)
        if feature_name in {"compact_state", "full_state"}:
            for method, distance in mode_support_scores(
                universe, prototypes, columns, args.seed
            ).items():
                score_families[(feature_name, method)] = _rank(distance)

    # Outcome-free terrain combinations are also preconstructed. The previous
    # NDVI experiment selected zero terrain weight, so only small conservative
    # additions are tested here rather than another dense weight search.
    terrain_rank = _rank(universe["env_nn"].to_numpy(float))
    expanded_scores = dict(score_families)
    for key, ndvi_rank in list(score_families.items()):
        if key[0] not in {"compact_state", "full_state"}:
            continue
        for terrain_weight in (0.10, 0.20, 0.30):
            expanded_scores[(key[0], f"{key[1]}+terrain_{terrain_weight:.2f}")] = (
                terrain_weight * terrain_rank + (1.0 - terrain_weight) * ndvi_rank
            )
        expanded_scores[(key[0], f"{key[1]}+terrain_and_max")] = np.maximum(
            terrain_rank, ndvi_rank
        )
    score_families = expanded_scores

    # Development scoring stage: field clusters become visible only here.
    detections = pd.read_csv(args.detections)
    experiments = []
    orders = {}
    for key, score in score_families.items():
        order = np.argsort(score, kind="mergesort")
        count, witness = minimum_count_for_complete_recovery(
            universe, detections, order, args.radius_km
        )
        if count is None:
            continue
        chosen = universe.iloc[order[:count]].copy()
        result = evaluate(chosen, detections, args.radius_km)
        if result["recovered"] != len(detections):
            raise RuntimeError(f"frontier audit failed for {key}")
        row = {
            "feature_set": key[0],
            "method": key[1],
            "candidate_count": int(count),
            "grid_fraction": float(count / len(universe)),
            "detection_witness_ranks": [int(value) for value in witness],
            **result,
        }
        experiments.append(row)
        orders[key] = order

    if not experiments:
        raise RuntimeError("No refinement score family achieved complete recovery")
    experiments.sort(key=lambda row: (row["candidate_count"], row["max_nearest_km"]))

    # Random auditing is expensive and not needed for clearly inferior fronts.
    # Audit every configuration that beats the prior 867-cell frontier, plus the
    # best configuration so a failed compression attempt still has a control.
    audit_rows = [row for row in experiments if row["candidate_count"] < 867]
    if not audit_rows:
        audit_rows = [experiments[0]]
    for i, row in enumerate(audit_rows):
        key = (row["feature_set"], row["method"])
        chosen = universe.iloc[orders[key][: row["candidate_count"]]].copy()
        row["matched_random"] = matched_random_success(
            universe,
            detections,
            chosen,
            args.radius_km,
            args.random_iterations,
            args.seed + i * 1009,
        )

    best = min(
        audit_rows,
        key=lambda row: (
            row["candidate_count"],
            row["matched_random"]["complete_recovery_probability"],
            row["max_nearest_km"],
        ),
    )
    best_key = (best["feature_set"], best["method"])
    best_candidates = universe.iloc[orders[best_key][: best["candidate_count"]]].copy()

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(experiments).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "ndvi_refinement_frontier.csv", index=False
    )
    best_candidates.to_csv(args.out / "best_ndvi_refinement_candidates.csv", index=False)
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "prior_frontier": {
            "candidate_count": 867,
            "grid_fraction": 867 / len(universe),
            "matched_random_complete_probability": 0.2975,
        },
        "feature_sets": FEATURE_SETS,
        "n_score_families": int(len(score_families)),
        "experiments": experiments,
        "random_audited": audit_rows,
        "best": best,
        "compression_vs_prior_cells": int(867 - best["candidate_count"]),
        "compression_vs_prior_fraction": float((867 - best["candidate_count"]) / len(universe)),
    }
    (args.out / "ndvi_refinement_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
