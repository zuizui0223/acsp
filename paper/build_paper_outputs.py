#!/usr/bin/env python3
"""Build paper-ready ACSP retrospective and field-validation tables.

The retrospective tables are rebuilt from the frozen independent benchmark
cohorts already committed to the repository. The prospective field comparison
runs only when the exact pre-survey candidate pool is present. A broad route
plan or a candidate pool reconstructed after seeing detections is deliberately
not accepted as a substitute.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from acsp.field_validation import (
    cluster_field_detections,
    detection_recovery_table,
    recovery_summary,
    stratified_random_recovery_benchmark,
)
from audit_random_validation_stability import run as run_stability_audit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCATIONS = ROOT / "field_validation/campanula_microdonta/locations_2026.csv"
DEFAULT_CANDIDATES = ROOT / "field_validation/campanula_microdonta/frozen_candidate_pool.csv"
DEFAULT_OUTPUT = ROOT / "paper/generated"
RADII_KM = (0.5, 1.0, 2.0, 5.0, 10.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locations", type=Path, default=DEFAULT_LOCATIONS)
    parser.add_argument("--candidate-pool", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cluster-radius-m", type=float, default=500.0)
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260715)
    return parser.parse_args()


def _retrospective_table(stability: dict[str, object]) -> pd.DataFrame:
    rows = []
    definitions = (
        ("animals", "animals_independent_mixed_cohort", "Independent mixed confirmation"),
        ("plants", "plants_pooled_independent_cohorts", "Pooled independent plant confirmations"),
    )
    for group, key, cohort in definitions:
        values = stability[key]
        rows.append(
            {
                "taxon_group": group,
                "cohort": cohort,
                "declared_taxon_region_pairs": values["declared_pairs"],
                "acsp_ite_recall_10km": values["mean_ite_default_recall"],
                "same_pool_random_ite_recall_10km": values["mean_ite_random_recall"],
                "lift_over_random": values["mean_lift"],
                "leave_one_pair_out_min_lift": values["leave_one_pair_out_min_lift"],
                "minimum_bootstrap_probability_lift_positive": values[
                    "minimum_bootstrap_probability_positive_across_seeds"
                ],
                "minimum_half_cohort_probability_lift_positive": values[
                    "minimum_half_sample_probability_positive_across_seeds"
                ],
                "maximum_sign_flip_p_across_seeds": values[
                    "maximum_sign_flip_p_across_seeds"
                ],
                "stability_verdict": values["stability_verdict"],
            }
        )
    return pd.DataFrame(rows)


def _seed_sensitivity_table(stability: dict[str, object]) -> pd.DataFrame:
    frames = []
    for group, key in (
        ("animals", "animals_independent_mixed_cohort"),
        ("plants", "plants_pooled_independent_cohorts"),
    ):
        frame = pd.DataFrame(stability[key]["seed_sensitivity"])
        frame.insert(0, "taxon_group", group)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _field_inventory(locations: pd.DataFrame, cluster_radius_m: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    field_rows, clusters = cluster_field_detections(
        locations,
        cluster_radius_m=cluster_radius_m,
        area_col="island",
    )
    raw_counts = field_rows.groupby("island", as_index=False).agg(raw_positive_gps_rows=("field_row_id", "size"))
    cluster_counts = clusters.groupby("island", as_index=False).agg(
        independent_detection_clusters=("detection_cluster_id", "size"),
        source_points_after_clustering=("n_source_points", "sum"),
    )
    inventory = raw_counts.merge(cluster_counts, on="island", how="outer").fillna(0)
    inventory["cluster_radius_m"] = float(cluster_radius_m)
    return field_rows, clusters, inventory


def _selected_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    required = {"site_id", "survey_area_id", "latitude", "longitude", "is_recommended"}
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"Frozen candidate pool is missing: {', '.join(sorted(missing))}")
    selected_mask = candidates["is_recommended"].astype(str).str.strip().str.lower().isin(
        {"1", "true", "yes", "y", "recommended"}
    )
    selected = candidates[selected_mask].copy()
    if selected.empty:
        raise ValueError("Frozen candidate pool contains no rows marked is_recommended.")
    return selected


def build(args: argparse.Namespace) -> dict[str, object]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    stability = run_stability_audit()
    retrospective = _retrospective_table(stability)
    seed_sensitivity = _seed_sensitivity_table(stability)
    retrospective.to_csv(output / "table_1_retrospective_validation.csv", index=False)
    seed_sensitivity.to_csv(output / "table_s1_seed_sensitivity.csv", index=False)
    (output / "retrospective_stability.json").write_text(
        json.dumps(stability, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    locations = pd.read_csv(args.locations)
    field_rows, clusters, inventory = _field_inventory(locations, args.cluster_radius_m)
    field_rows.to_csv(output / "field_rows_with_clusters.csv", index=False)
    clusters.to_csv(output / "independent_detection_clusters.csv", index=False)
    inventory.to_csv(output / "table_2_field_inventory.csv", index=False)

    manifest: dict[str, object] = {
        "retrospective_status": "complete",
        "retrospective_endpoint": stability["endpoint"],
        "retrospective_baseline": stability["baseline"],
        "field_locations": str(args.locations),
        "raw_positive_gps_rows": int(len(field_rows)),
        "independent_detection_clusters": int(len(clusters)),
        "field_cluster_radius_m": float(args.cluster_radius_m),
        "candidate_pool": str(args.candidate_pool),
    }

    if not args.candidate_pool.exists():
        status = pd.DataFrame(
            [
                {
                    "status": "blocked_missing_frozen_candidate_pool",
                    "reason": (
                        "The exact pre-survey ACSP candidate export is required. "
                        "Do not regenerate recommendations after inspecting field detections."
                    ),
                    "expected_path": str(args.candidate_pool),
                }
            ]
        )
        status.to_csv(output / "table_3_prospective_field_comparison_status.csv", index=False)
        manifest["prospective_status"] = "blocked_missing_frozen_candidate_pool"
    else:
        candidates = pd.read_csv(args.candidate_pool)
        selected = _selected_candidates(candidates)
        recovery = detection_recovery_table(
            selected,
            clusters,
            radii_km=RADII_KM,
            candidate_id_col="site_id",
            area_col="survey_area_id",
        )
        summary = recovery_summary(recovery, radii_km=RADII_KM)
        benchmark, random_draws = stratified_random_recovery_benchmark(
            candidates,
            selected["site_id"],
            clusters,
            radii_km=RADII_KM,
            iterations=args.iterations,
            seed=args.seed,
            candidate_id_col="site_id",
            area_col="survey_area_id",
        )
        recovery.to_csv(output / "field_detection_to_nearest_candidate.csv", index=False)
        summary.to_csv(output / "table_3_acsp_field_recovery.csv", index=False)
        benchmark.to_csv(output / "table_4_same_pool_random_field_comparison.csv", index=False)
        random_draws.to_csv(output / "table_s2_same_pool_random_draws.csv", index=False)
        manifest.update(
            {
                "prospective_status": "complete",
                "candidate_pool_rows": int(len(candidates)),
                "recommended_candidate_rows": int(len(selected)),
                "random_iterations": int(args.iterations),
                "random_seed": int(args.seed),
            }
        )

    (output / "paper_output_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def main() -> None:
    args = parse_args()
    print(json.dumps(build(args), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
