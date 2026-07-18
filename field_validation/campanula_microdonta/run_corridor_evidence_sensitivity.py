#!/usr/bin/env python3
"""Assess whether ecological-gap labels are stable to technical corridor settings."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from acsp.gap_connectivity import CorridorBarrierConfig, annotate_gap_patch_barriers

SUPPORT_COL = "component_local_habitat_score"
INTERPOLATION_RADII_M = (500.0, 750.0, 1000.0, 1500.0)
COVERAGE_THRESHOLDS = (0.60, 0.75, 0.90)
LOW_SUPPORT_THRESHOLDS = (0.25, 0.35, 0.45)
MIN_BARRIER_LENGTHS_M = (500.0, 750.0, 1000.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    pool = pd.read_csv(results / "distance_excluded_candidate_pool.csv")
    known = pd.read_csv(results / "gbif_training_occurrences_through_2025.csv")
    patch_members = pd.read_csv(results / "gap_patch_members_with_barriers.csv")
    base_columns = [
        column for column in patch_members.columns
        if not column.startswith("corridor_") and column != "gap_patch_ecological_class"
    ]
    patch_members = patch_members[base_columns].copy()

    rows: list[dict[str, object]] = []
    labels: list[pd.DataFrame] = []
    setting_id = 0
    for interpolation_radius_m in INTERPOLATION_RADII_M:
        for min_coverage_fraction in COVERAGE_THRESHOLDS:
            for low_support_threshold in LOW_SUPPORT_THRESHOLDS:
                for min_barrier_length_m in MIN_BARRIER_LENGTHS_M:
                    setting_id += 1
                    config = CorridorBarrierConfig(
                        sample_spacing_m=250.0,
                        interpolation_radius_m=interpolation_radius_m,
                        low_support_threshold=low_support_threshold,
                        min_barrier_length_m=min_barrier_length_m,
                        min_coverage_fraction=min_coverage_fraction,
                    )
                    annotated = annotate_gap_patch_barriers(
                        pool,
                        patch_members,
                        known,
                        support_col=SUPPORT_COL,
                        config=config,
                    )
                    patch_level = annotated.drop_duplicates("gap_patch_id").copy()
                    counts = patch_level["gap_patch_ecological_class"].value_counts()
                    rows.append({
                        "setting_id": setting_id,
                        "interpolation_radius_m": interpolation_radius_m,
                        "min_coverage_fraction": min_coverage_fraction,
                        "low_support_threshold": low_support_threshold,
                        "min_barrier_length_m": min_barrier_length_m,
                        "barrier_patch_count": int(counts.get("barrier_separated_patch", 0)),
                        "insufficient_evidence_patch_count": int(counts.get("insufficient_corridor_evidence", 0)),
                        "distance_without_barrier_patch_count": int(counts.get("distance_separated_without_barrier", 0)),
                        "anchor_extension_patch_count": int(counts.get("continuous_anchor_extension", 0)),
                    })
                    labels.append(patch_level[[
                        "gap_patch_id",
                        "gap_patch_class",
                        "gap_patch_ecological_class",
                        "corridor_evidence_class",
                        "corridor_coverage_fraction",
                        "corridor_longest_low_support_m",
                        "corridor_longest_support_gap_m",
                    ]].assign(setting_id=setting_id))

    settings = pd.DataFrame(rows)
    label_table = pd.concat(labels, ignore_index=True)
    settings.to_csv(results / "corridor_evidence_sensitivity.csv", index=False)
    label_table.to_csv(results / "corridor_patch_labels_by_setting.csv", index=False)

    stability = (
        label_table.groupby("gap_patch_id", sort=True)
        .agg(
            settings=("setting_id", "nunique"),
            barrier_frequency=("gap_patch_ecological_class", lambda s: float(s.eq("barrier_separated_patch").mean())),
            insufficient_frequency=("gap_patch_ecological_class", lambda s: float(s.eq("insufficient_corridor_evidence").mean())),
            distinct_labels=("gap_patch_ecological_class", "nunique"),
        )
        .reset_index()
    )
    stability["stable_barrier"] = stability["barrier_frequency"].eq(1.0)
    stability["ever_barrier"] = stability["barrier_frequency"].gt(0.0)
    stability.to_csv(results / "corridor_patch_label_stability.csv", index=False)

    print(settings[["barrier_patch_count", "insufficient_evidence_patch_count"]].describe().to_string())
    print(stability.to_string(index=False))


if __name__ == "__main__":
    main()
