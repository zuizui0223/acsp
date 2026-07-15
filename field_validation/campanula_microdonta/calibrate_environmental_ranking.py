#!/usr/bin/env python3
"""Learn a GBIF/environment-only candidate score from field outcomes.

The field detections define the development objective, but candidate scoring uses
only GBIF-derived and environmental columns. Leave-one-island-out selections are
reported separately from the all-data development fit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from acsp.field_calibration import calibrate_field_ranker
from run_temporal_external_validation import (
    DEFAULT_SEED,
    island_random_benchmark,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    parser.add_argument("--random-iterations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def _benchmark_and_write(
    annotated: pd.DataFrame,
    selected: pd.DataFrame,
    clusters: pd.DataFrame,
    *,
    results: Path,
    stem: str,
    iterations: int,
    seed: int,
) -> pd.DataFrame:
    benchmark, draws = island_random_benchmark(
        annotated,
        selected,
        clusters,
        iterations=iterations,
        seed=seed,
    )
    benchmark.to_csv(results / f"{stem}_benchmark.csv", index=False)
    draws.to_csv(results / f"{stem}_draws.csv", index=False)
    return benchmark


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    pool = pd.read_csv(results / "distance_excluded_candidate_pool.csv")
    clusters = pd.read_csv(results / "independent_detection_clusters.csv")

    calibration = calibrate_field_ranker(pool, clusters)
    annotated = calibration["annotated_candidates"]
    search = calibration["configuration_search"]
    outer = calibration["outer_selections"]
    outer_configs = calibration["outer_configurations"]
    final_selected = calibration["final_selections"]

    annotated.to_csv(results / "field_calibrated_candidate_pool.csv", index=False)
    search.to_csv(results / "field_calibration_configuration_search.csv", index=False)
    outer.to_csv(results / "field_calibration_leave_one_island_out.csv", index=False)
    outer_configs.to_csv(results / "field_calibration_fold_rules.csv", index=False)
    final_selected.to_csv(results / "field_informed_development_top5.csv", index=False)

    iterations = int(args.random_iterations)
    seed = int(args.seed)
    outer_benchmark = _benchmark_and_write(
        annotated,
        outer,
        clusters,
        results=results,
        stem="field_calibration_leave_one_island_out_same_pool_random",
        iterations=iterations,
        seed=seed,
    )
    development_benchmark = _benchmark_and_write(
        annotated,
        final_selected,
        clusters,
        results=results,
        stem="field_informed_same_pool_random",
        iterations=iterations,
        seed=seed,
    )

    summary = {
        "status": "field-informed algorithm development",
        "prediction_inputs": (
            "GBIF-derived occurrence context and environmental candidate attributes only; "
            "field coordinates are not candidate inputs"
        ),
        "field_outcome_role": (
            "select environmental/GBIF rank features and weights; leave-one-island-out "
            "predictions estimate geographic transfer without using the held island"
        ),
        "baseline_metrics": calibration["baseline_metrics"],
        "leave_one_island_out_metrics": calibration["outer_cv_metrics"],
        "leave_one_island_out_random_benchmark": outer_benchmark.to_dict(orient="records"),
        "all_data_development_metrics": calibration["development_metrics"],
        "all_data_development_random_benchmark": development_benchmark.to_dict(orient="records"),
        "final_configuration": calibration["final_configuration"].as_dict(),
        "available_feature_specs": calibration["available_feature_specs"],
        "random_iterations": iterations,
        "seed": seed,
        "interpretation": (
            "Leave-one-island-out performance and its same-pool random benchmark are the primary "
            "current transfer estimate. The all-data fit is an optimized development result and "
            "must not be treated as independent confirmation."
        ),
    }
    (results / "field_calibration_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
