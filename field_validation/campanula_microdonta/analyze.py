#!/usr/bin/env python3
"""Run the frozen-candidate versus field-detection ACSP case study."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from acsp.field_validation import (
    cluster_field_detections,
    detection_recovery_table,
    recovery_summary,
    stratified_random_recovery_benchmark,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-pool", required=True, help="Frozen pre-survey ACSP candidate CSV")
    parser.add_argument(
        "--locations",
        default=str(Path(__file__).with_name("locations_2026.csv")),
        help="Positive field GPS CSV",
    )
    parser.add_argument("--output-dir", default="field_validation/campanula_microdonta/results")
    parser.add_argument("--cluster-radius-m", type=float, default=500.0)
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument("--selected-column", default="is_recommended")
    parser.add_argument("--candidate-id-column", default="site_id")
    parser.add_argument("--area-column", default="survey_area_id")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidates = pd.read_csv(args.candidate_pool)
    locations = pd.read_csv(args.locations)
    if args.selected_column not in candidates.columns:
        raise SystemExit(
            f"Frozen candidate pool must contain {args.selected_column!r}; "
            "do not reconstruct recommendations after inspecting field outcomes."
        )

    selected_mask = candidates[args.selected_column].astype(str).str.lower().isin(
        {"1", "true", "yes", "y", "recommended"}
    )
    selected = candidates[selected_mask].copy()
    if selected.empty:
        raise SystemExit("No frozen recommended candidates were marked in the candidate pool.")

    field_rows, clusters = cluster_field_detections(
        locations,
        cluster_radius_m=args.cluster_radius_m,
        area_col="island",
    )
    recovery = detection_recovery_table(
        selected,
        clusters,
        candidate_id_col=args.candidate_id_column,
        area_col=args.area_column,
    )
    summary = recovery_summary(recovery)
    benchmark, random_draws = stratified_random_recovery_benchmark(
        candidates,
        selected[args.candidate_id_column],
        clusters,
        iterations=args.iterations,
        seed=args.seed,
        candidate_id_col=args.candidate_id_column,
        area_col=args.area_column,
    )

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    field_rows.to_csv(output / "field_rows_with_clusters.csv", index=False)
    clusters.to_csv(output / "independent_detection_clusters.csv", index=False)
    recovery.to_csv(output / "detection_to_nearest_candidate.csv", index=False)
    summary.to_csv(output / "acsp_recovery_summary.csv", index=False)
    benchmark.to_csv(output / "same_pool_random_benchmark.csv", index=False)
    random_draws.to_csv(output / "same_pool_random_draws.csv", index=False)
    print(benchmark.to_string(index=False))


if __name__ == "__main__":
    main()
