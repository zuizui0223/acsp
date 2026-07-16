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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    parser.add_argument("--random-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    return parser.parse_args()


def _random_same_budget(
    pool: pd.DataFrame,
    selected: pd.DataFrame,
    clusters: pd.DataFrame,
    *,
    iterations: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    observed = recovery_metrics(selected, clusters)
    rows = []
    for iteration in range(iterations):
        parts = []
        for area, selected_group in selected.groupby("survey_area_id"):
            candidates = pool[pool["survey_area_id"].eq(area)]
            sample_n = min(len(candidates), len(selected_group))
            chosen = rng.choice(candidates.index.to_numpy(), size=sample_n, replace=False)
            parts.append(candidates.loc[chosen])
        random_selected = pd.concat(parts, ignore_index=True)
        metrics = recovery_metrics(random_selected, clusters)
        rows.append({"iteration": iteration, **metrics})
    draws = pd.DataFrame(rows)
    benchmarks = []
    for radius in (0.5, 1.0, 2.0, 5.0, 10.0):
        column = f"recall_{radius:g}km"
        observed_value = float(observed[column])
        random_values = pd.to_numeric(draws[column], errors="coerce")
        benchmarks.append(
            {
                "radius_km": radius,
                "observed_recall": observed_value,
                "random_mean_recall": float(random_values.mean()),
                "lift_over_random": float(observed_value - random_values.mean()),
                "one_sided_p": float((1 + np.sum(random_values >= observed_value)) / (len(random_values) + 1)),
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
        "total_internal_route_km": float(pd.to_numeric(patches["patch_internal_route_km"], errors="coerce").sum()),
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
