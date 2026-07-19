#!/usr/bin/env python3
"""Test whether near-disconnected occurrence patches are stable to distance rules."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from acsp import (
    OccurrencePatchConnectivityConfig,
    annotate_occurrence_patch_connectivity,
    cluster_patch_recovery_table,
)

OCCURRENCE_LINKS_M = (250.0, 500.0, 750.0, 1000.0)
CANDIDATE_LINKS_M = (500.0, 750.0, 1000.0, 1500.0)
NEAR_MAXIMA_M = (3000.0, 5000.0, 8000.0)
RECOVERY_RADII_KM = (1.0, 2.0, 5.0, 10.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    return parser.parse_args()


def ensure_cluster_id(clusters: pd.DataFrame) -> pd.DataFrame:
    out = clusters.copy().reset_index(drop=True)
    if "cluster_id" not in out.columns:
        candidate = next((c for c in out.columns if c.endswith("cluster_id")), None)
        out["cluster_id"] = out[candidate] if candidate else np.arange(1, len(out) + 1)
    return out


def recover_by_island(selected: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for island, held in clusters.groupby("island", sort=True):
        members = selected[
            selected["survey_area_id"].astype(str).str.lower().eq(str(island).lower())
        ]
        if members.empty:
            empty = held[["cluster_id", "island"]].copy()
            empty["nearest_patch_distance_m"] = np.inf
            for radius in RECOVERY_RADII_KM:
                empty[f"recovered_within_{radius:g}km"] = False
            rows.append(empty)
            continue
        recovery = cluster_patch_recovery_table(
            members,
            held,
            cluster_col="cluster_id",
            radii_km=RECOVERY_RADII_KM,
        )
        recovery["island"] = island
        rows.append(recovery)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    members = pd.read_csv(results / "gap_patch_members_with_barriers.csv")
    known = pd.read_csv(results / "gbif_training_occurrences_through_2025.csv")
    clusters = ensure_cluster_id(pd.read_csv(results / "independent_detection_clusters.csv"))

    setting_rows: list[dict[str, object]] = []
    label_rows: list[pd.DataFrame] = []
    setting_id = 0
    for occurrence_link in OCCURRENCE_LINKS_M:
        for candidate_link in CANDIDATE_LINKS_M:
            for near_max in NEAR_MAXIMA_M:
                if near_max < candidate_link:
                    continue
                setting_id += 1
                cfg = OccurrencePatchConnectivityConfig(
                    occurrence_link_distance_m=occurrence_link,
                    candidate_occurrence_link_distance_m=candidate_link,
                    near_disconnected_max_distance_m=near_max,
                )
                annotated = annotate_occurrence_patch_connectivity(members, known, config=cfg)
                patch_level = annotated.drop_duplicates("gap_patch_id").copy()
                patch_level["setting_id"] = setting_id
                patch_level["occurrence_link_distance_m"] = occurrence_link
                patch_level["candidate_occurrence_link_distance_m"] = candidate_link
                patch_level["near_disconnected_max_distance_m"] = near_max
                label_rows.append(
                    patch_level[[
                        "setting_id",
                        "gap_patch_id",
                        "survey_area_id",
                        "candidate_occurrence_edge_distance_m",
                        "candidate_occurrence_gap_width_m",
                        "occurrence_patch_connectivity_class",
                        "occurrence_link_distance_m",
                        "candidate_occurrence_link_distance_m",
                        "near_disconnected_max_distance_m",
                    ]]
                )

                near = annotated[
                    annotated["occurrence_patch_connectivity_class"].eq(
                        "near_disconnected_occurrence_patch"
                    )
                ]
                recovery = recover_by_island(near, clusters)
                row: dict[str, object] = {
                    "setting_id": setting_id,
                    "occurrence_link_distance_m": occurrence_link,
                    "candidate_occurrence_link_distance_m": candidate_link,
                    "near_disconnected_max_distance_m": near_max,
                    "near_disconnected_patch_count": int(near["gap_patch_id"].nunique()),
                    "near_disconnected_member_count": int(len(near)),
                }
                for radius in RECOVERY_RADII_KM:
                    column = f"recovered_within_{radius:g}km"
                    row[f"near_disconnected_cluster_recall_{radius:g}km"] = (
                        float(recovery[column].mean()) if column in recovery else 0.0
                    )
                setting_rows.append(row)

    settings = pd.DataFrame(setting_rows)
    labels = pd.concat(label_rows, ignore_index=True)
    stability = (
        labels.assign(
            is_near_disconnected=labels["occurrence_patch_connectivity_class"].eq(
                "near_disconnected_occurrence_patch"
            )
        )
        .groupby(["gap_patch_id", "survey_area_id"], as_index=False)
        .agg(
            setting_count=("setting_id", "nunique"),
            near_disconnected_frequency=("is_near_disconnected", "mean"),
            min_edge_distance_m=("candidate_occurrence_edge_distance_m", "min"),
            max_edge_distance_m=("candidate_occurrence_edge_distance_m", "max"),
            class_count=("occurrence_patch_connectivity_class", "nunique"),
        )
    )
    stability["always_near_disconnected"] = stability["near_disconnected_frequency"].eq(1.0)
    stability["ever_near_disconnected"] = stability["near_disconnected_frequency"].gt(0.0)

    settings.to_csv(results / "occurrence_patch_connectivity_sensitivity.csv", index=False)
    labels.to_csv(results / "occurrence_patch_labels_by_setting.csv", index=False)
    stability.to_csv(results / "occurrence_patch_label_stability.csv", index=False)

    print(settings.to_string(index=False))
    print(stability.to_string(index=False))


if __name__ == "__main__":
    main()
