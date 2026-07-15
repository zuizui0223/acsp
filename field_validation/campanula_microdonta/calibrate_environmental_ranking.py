#!/usr/bin/env python3
"""Learn candidate ranking from field outcomes with transfer-aware diagnostics.

The primary v2 learner combines selected-site utility with within-island pairwise
ranking concordance. A separate ecology-only diagnostic excludes direct GBIF
proximity and target-record-density features. Field coordinates remain outcomes;
they never become candidate prediction inputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from acsp.field_calibration import calibrate_field_ranker
from acsp.transfer_ranker import (
    GBIF_BIAS_FEATURES,
    TransferObjective,
    calibrate_transfer_ranker,
)
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
    parser.add_argument("--selected-utility-weight", type=float, default=0.5)
    parser.add_argument("--pairwise-concordance-weight", type=float, default=0.5)
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


def _write_calibration(result: dict[str, object], results: Path, prefix: str) -> None:
    result["annotated_candidates"].to_csv(
        results / f"{prefix}_candidate_pool.csv", index=False
    )
    result["configuration_search"].to_csv(
        results / f"{prefix}_configuration_search.csv", index=False
    )
    result["outer_selections"].to_csv(
        results / f"{prefix}_leave_one_island_out.csv", index=False
    )
    result["outer_configurations"].to_csv(
        results / f"{prefix}_fold_rules.csv", index=False
    )
    result["final_selections"].to_csv(
        results / f"{prefix}_development_top5.csv", index=False
    )


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    pool = pd.read_csv(results / "distance_excluded_candidate_pool.csv")
    clusters = pd.read_csv(results / "independent_detection_clusters.csv")
    iterations = int(args.random_iterations)
    seed = int(args.seed)

    legacy = calibrate_field_ranker(pool, clusters)
    legacy["annotated_candidates"].to_csv(
        results / "field_calibrated_candidate_pool.csv", index=False
    )
    legacy["configuration_search"].to_csv(
        results / "field_calibration_configuration_search.csv", index=False
    )
    legacy["outer_selections"].to_csv(
        results / "field_calibration_leave_one_island_out.csv", index=False
    )
    legacy["outer_configurations"].to_csv(
        results / "field_calibration_fold_rules.csv", index=False
    )
    legacy["final_selections"].to_csv(
        results / "field_informed_development_top5.csv", index=False
    )
    legacy_outer_benchmark = _benchmark_and_write(
        legacy["annotated_candidates"],
        legacy["outer_selections"],
        clusters,
        results=results,
        stem="field_calibration_leave_one_island_out_same_pool_random",
        iterations=iterations,
        seed=seed,
    )
    legacy_development_benchmark = _benchmark_and_write(
        legacy["annotated_candidates"],
        legacy["final_selections"],
        clusters,
        results=results,
        stem="field_informed_same_pool_random",
        iterations=iterations,
        seed=seed,
    )

    objective = TransferObjective(
        selected_utility_weight=float(args.selected_utility_weight),
        pairwise_concordance_weight=float(args.pairwise_concordance_weight),
    )
    transfer = calibrate_transfer_ranker(pool, clusters, objective=objective)
    ecology_only = calibrate_transfer_ranker(
        pool,
        clusters,
        objective=objective,
        excluded_features=sorted(GBIF_BIAS_FEATURES),
    )
    _write_calibration(transfer, results, "transfer_ranker")
    _write_calibration(ecology_only, results, "ecology_only_transfer_ranker")

    transfer_outer_benchmark = _benchmark_and_write(
        transfer["annotated_candidates"],
        transfer["outer_selections"],
        clusters,
        results=results,
        stem="transfer_ranker_leave_one_island_out_same_pool_random",
        iterations=iterations,
        seed=seed,
    )
    ecology_outer_benchmark = _benchmark_and_write(
        ecology_only["annotated_candidates"],
        ecology_only["outer_selections"],
        clusters,
        results=results,
        stem="ecology_only_transfer_ranker_leave_one_island_out_same_pool_random",
        iterations=iterations,
        seed=seed,
    )

    summary = {
        "status": "field-informed algorithm development",
        "prediction_inputs": (
            "Candidate attributes only. Field coordinates are outcomes and are never "
            "candidate inputs. The ecology-only diagnostic also excludes direct GBIF "
            "proximity and target-record-density features."
        ),
        "legacy_top_only": {
            "leave_one_island_out_metrics": legacy["outer_cv_metrics"],
            "leave_one_island_out_random_benchmark": legacy_outer_benchmark.to_dict(
                orient="records"
            ),
            "all_data_development_metrics": legacy["development_metrics"],
            "all_data_development_random_benchmark": legacy_development_benchmark.to_dict(
                orient="records"
            ),
            "final_configuration": legacy["final_configuration"].as_dict(),
        },
        "transfer_ranker_v2": {
            "objective": {
                "selected_utility_weight": transfer["objective"].selected_utility_weight,
                "pairwise_concordance_weight": transfer["objective"].pairwise_concordance_weight,
                "complexity_penalty": transfer["objective"].complexity_penalty,
            },
            "leave_one_island_out_metrics": transfer["outer_cv_metrics"],
            "leave_one_island_out_random_benchmark": transfer_outer_benchmark.to_dict(
                orient="records"
            ),
            "all_data_development_metrics": transfer["development_metrics"],
            "final_configuration": transfer["final_configuration"].as_dict(),
        },
        "ecology_only_transfer_diagnostic": {
            "excluded_features": ecology_only["excluded_features"],
            "leave_one_island_out_metrics": ecology_only["outer_cv_metrics"],
            "leave_one_island_out_random_benchmark": ecology_outer_benchmark.to_dict(
                orient="records"
            ),
            "all_data_development_metrics": ecology_only["development_metrics"],
            "final_configuration": ecology_only["final_configuration"].as_dict(),
        },
        "next_data_priority": [
            "vegetation-patch composition and edge structure",
            "substrate or geology class and heterogeneity",
            "moisture and drainage proxies",
            "disturbance and road-cut or cliff exposure",
            "independent non-GBIF presence records reserved for external evaluation",
        ],
        "random_iterations": iterations,
        "seed": seed,
        "interpretation": (
            "Leave-one-island-out results are primary. The ecology-only diagnostic tests "
            "whether apparent gains survive removal of direct GBIF sampling-bias features. "
            "Independent occurrence sources should be held out for external evaluation, not "
            "silently merged into both training and testing."
        ),
    }
    (results / "field_calibration_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
