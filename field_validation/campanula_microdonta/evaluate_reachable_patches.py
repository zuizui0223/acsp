#!/usr/bin/env python3
"""Evaluate route-constrained persistent survey patches on field detections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.field_calibration import recovery_metrics
from acsp.reachable_patches import PatchSettings, discover_persistent_patches


RADII_KM = (0.5, 1.0, 2.0, 5.0, 10.0)
EARTH_RADIUS_KM = 6371.0088


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    parser.add_argument("--random-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    return parser.parse_args()


def _haversine_matrix_km(
    first_latitude: np.ndarray,
    first_longitude: np.ndarray,
    second_latitude: np.ndarray,
    second_longitude: np.ndarray,
) -> np.ndarray:
    """Return all pairwise great-circle distances without Python row loops."""
    first_lat = np.radians(np.asarray(first_latitude, dtype=float))[:, None]
    first_lon = np.radians(np.asarray(first_longitude, dtype=float))[:, None]
    second_lat = np.radians(np.asarray(second_latitude, dtype=float))[None, :]
    second_lon = np.radians(np.asarray(second_longitude, dtype=float))[None, :]
    delta_lat = second_lat - first_lat
    delta_lon = second_lon - first_lon
    haversine = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(first_lat) * np.cos(second_lat) * np.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(haversine, 0.0, 1.0)))


def _random_same_budget(
    pool: pd.DataFrame,
    selected: pd.DataFrame,
    clusters: pd.DataFrame,
    *,
    iterations: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Vectorized same-area random benchmark.

    Candidate-to-detection distances are computed once. All random sets are then
    sampled and evaluated in NumPy arrays, avoiding 10,000 repeated DataFrame and
    haversine loops while preserving the same island-specific station budget.
    """
    iterations = max(1, int(iterations))
    rng = np.random.default_rng(seed)
    observed = recovery_metrics(selected, clusters)

    working_pool = pool.reset_index(drop=True).copy()
    pool_area = working_pool["survey_area_id"].astype(str).str.lower().to_numpy()
    cluster_area = clusters["island"].astype(str).str.lower().to_numpy()
    selected_counts = (
        selected["survey_area_id"].astype(str).str.lower().value_counts().to_dict()
    )
    distances = _haversine_matrix_km(
        working_pool["latitude"].to_numpy(float),
        working_pool["longitude"].to_numpy(float),
        clusters["latitude"].to_numpy(float),
        clusters["longitude"].to_numpy(float),
    )
    nearest = np.full((iterations, len(clusters)), np.inf, dtype=float)

    for area, requested_n in selected_counts.items():
        candidate_rows = np.flatnonzero(pool_area == area)
        cluster_columns = np.flatnonzero(cluster_area == area)
        if len(candidate_rows) == 0 or len(cluster_columns) == 0:
            continue
        sample_n = min(int(requested_n), len(candidate_rows))
        if sample_n == len(candidate_rows):
            sampled_rows = np.broadcast_to(candidate_rows, (iterations, len(candidate_rows)))
        else:
            random_keys = rng.random((iterations, len(candidate_rows)))
            local_indices = np.argpartition(random_keys, sample_n - 1, axis=1)[:, :sample_n]
            sampled_rows = candidate_rows[local_indices]
        area_nearest = distances[sampled_rows][:, :, cluster_columns].min(axis=1)
        nearest[:, cluster_columns] = area_nearest

    draw_data: dict[str, object] = {
        "iteration": np.arange(iterations, dtype=int),
        "n_detection_clusters": np.full(iterations, len(clusters), dtype=int),
    }
    for radius in RADII_KM:
        recovered = (nearest <= radius).sum(axis=1)
        draw_data[f"recall_{radius:g}km"] = recovered / max(1, len(clusters))
        draw_data[f"n_recovered_{radius:g}km"] = recovered
    draw_data["median_nearest_candidate_km"] = np.median(nearest, axis=1)
    draw_data["mean_nearest_candidate_km"] = np.mean(nearest, axis=1)
    draws = pd.DataFrame(draw_data)

    benchmarks = []
    for radius in RADII_KM:
        column = f"recall_{radius:g}km"
        observed_value = float(observed[column])
        random_values = draws[column].to_numpy(float)
        random_mean = float(random_values.mean())
        benchmarks.append(
            {
                "radius_km": radius,
                "observed_recall": observed_value,
                "random_mean_recall": random_mean,
                "lift_over_random": float(observed_value - random_mean),
                "one_sided_p": float(
                    (1 + np.count_nonzero(random_values >= observed_value))
                    / (len(random_values) + 1)
                ),
            }
        )
    return pd.DataFrame(benchmarks), draws


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    pool = pd.read_csv(results / "distance_excluded_candidate_pool.csv")
    clusters = pd.read_csv(results / "independent_detection_clusters.csv")
    settings = PatchSettings(
        connection_radius_km=2.0,
        environmental_epsilon=3.0,
        support_quantile=0.5,
        persistence_threshold=0.30,
        maximum_patch_diameter_km=3.0,
        maximum_stations=3,
    )
    stations, patches = discover_persistent_patches(pool, settings=settings)
    stations.to_csv(results / "persistent_reachable_patch_stations.csv", index=False)
    patches.to_csv(results / "persistent_reachable_patches.csv", index=False)
    metrics = recovery_metrics(stations, clusters)
    benchmark, draws = _random_same_budget(
        pool,
        stations,
        clusters,
        iterations=int(args.random_iterations),
        seed=int(args.seed),
    )
    benchmark.to_csv(results / "persistent_reachable_patch_random_benchmark.csv", index=False)
    draws.to_csv(results / "persistent_reachable_patch_random_draws.csv", index=False)
    summary = {
        "status": "initial route-constrained persistent-patch experiment",
        "settings": settings.__dict__,
        "metrics": metrics,
        "random_benchmark": benchmark.to_dict(orient="records"),
        "total_stations": int(len(stations)),
        "total_internal_route_km": float(
            pd.to_numeric(patches["patch_internal_route_km"], errors="coerce").sum()
        ),
        "random_evaluation": (
            "Vectorized exact same-island station-count benchmark with one precomputed "
            "candidate-to-detection distance matrix. Internal route length is not yet exactly matched."
        ),
        "interpretation": (
            "This first experiment fixes station count and patch diameter. The random control preserves "
            "station count by island but does not yet exactly match internal route length; route-matched "
            "sampling is the next diagnostic if apparent improvement remains."
        ),
    }
    (results / "persistent_reachable_patch_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
