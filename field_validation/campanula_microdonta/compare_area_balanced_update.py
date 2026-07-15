#!/usr/bin/env python3
"""Compare the frozen baseline with a general survey-area balanced update.

This script runs after the historical GBIF candidate pool has been constructed.
The updated selection reads only that candidate pool. Independent field clusters
are loaded afterwards for evaluation, so they are never selection inputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.area_selection import select_area_balanced_candidates
from acsp.field_validation import (
    detection_recovery_table,
    recovery_summary,
    stratified_random_recovery_benchmark,
)
from run_temporal_external_validation import (
    DEFAULT_SEED,
    PRIMARY_RADIUS_KM,
    PRIMARY_TOP_K,
    island_constrained_recovery,
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


def _primary(frame: pd.DataFrame) -> dict[str, object]:
    row = frame[np.isclose(frame["radius_km"], PRIMARY_RADIUS_KM)].iloc[0]
    return row.to_dict()


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    pool = pd.read_csv(results / "distance_excluded_candidate_pool.csv")
    baseline = pd.read_csv(results / "frozen_acsp_top5.csv")
    clusters = pd.read_csv(results / "independent_detection_clusters.csv")

    # No field outcome is used here. The update is a generic multi-area set
    # constraint: when k equals the number of declared survey areas, represent
    # each area once before allocating duplicate candidates.
    updated = select_area_balanced_candidates(
        pool,
        min(PRIMARY_TOP_K, len(pool)),
        score_col="component_local_habitat_score",
        area_col="survey_area_id",
        evidence_weight=1.0,
        cover_areas_first=True,
    )
    updated["is_recommended"] = True
    updated["validation_role"] = "post_baseline_general_area_balance_update"
    updated.to_csv(results / "updated_area_balanced_top5.csv", index=False)

    regional_recovery = detection_recovery_table(
        updated,
        clusters,
        candidate_id_col="site_id",
        area_col="survey_area_id",
    )
    regional_summary = recovery_summary(regional_recovery)
    regional_benchmark, regional_draws = stratified_random_recovery_benchmark(
        pool,
        updated["site_id"],
        clusters,
        iterations=int(args.random_iterations),
        seed=int(args.seed),
        candidate_id_col="site_id",
        area_col="survey_area_id",
    )
    regional_recovery.to_csv(results / "updated_regional_detection_recovery.csv", index=False)
    regional_summary.to_csv(results / "updated_regional_recovery_summary.csv", index=False)
    regional_benchmark.to_csv(results / "updated_regional_same_pool_random_benchmark.csv", index=False)
    regional_draws.to_csv(results / "updated_regional_same_pool_random_draws.csv", index=False)

    within_recovery = island_constrained_recovery(updated, clusters)
    within_summary = recovery_summary(within_recovery)
    within_benchmark, within_draws = island_random_benchmark(
        pool,
        updated,
        clusters,
        iterations=int(args.random_iterations),
        seed=int(args.seed),
    )
    within_recovery.to_csv(results / "updated_within_island_detection_recovery.csv", index=False)
    within_summary.to_csv(results / "updated_within_island_recovery_summary.csv", index=False)
    within_benchmark.to_csv(results / "updated_within_island_same_pool_random_benchmark.csv", index=False)
    within_draws.to_csv(results / "updated_within_island_same_pool_random_draws.csv", index=False)

    baseline_regional = pd.read_csv(results / "regional_same_pool_random_benchmark.csv").assign(
        algorithm_version="baseline_global_top5"
    )
    updated_regional = regional_benchmark.assign(
        algorithm_version="updated_area_balanced_top5"
    )
    comparison = pd.concat([baseline_regional, updated_regional], ignore_index=True)
    comparison.to_csv(results / "baseline_vs_area_balanced_comparison.csv", index=False)

    summary = {
        "update_type": "general multi-survey-area set-selection constraint",
        "field_data_used_for_updated_selection": False,
        "baseline_policy": "global Top-5 by local-habitat evidence",
        "updated_policy": (
            "Top-5 by local-habitat evidence with every declared survey area "
            "represented before duplicate allocation"
        ),
        "baseline_island_allocation": {
            str(key): int(value)
            for key, value in baseline["survey_area_id"].value_counts().sort_index().items()
        },
        "updated_island_allocation": {
            str(key): int(value)
            for key, value in updated["survey_area_id"].value_counts().sort_index().items()
        },
        "baseline_regional_primary": _primary(baseline_regional),
        "updated_regional_primary": _primary(updated_regional),
        "updated_within_island_primary": _primary(within_benchmark),
        "interpretation": (
            "The baseline remains the first external evaluation. The area-balanced result is a "
            "post-baseline algorithm update and must be labelled as such; its generality should be "
            "checked on independent multi-area datasets."
        ),
    }
    (results / "algorithm_update_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
