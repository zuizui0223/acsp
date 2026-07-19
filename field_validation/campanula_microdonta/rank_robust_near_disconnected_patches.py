#!/usr/bin/env python3
"""Rank near-disconnected occurrence patches without using 2026 detections in the score."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from acsp import cluster_patch_recovery_table

RADII_KM = (1.0, 2.0, 5.0, 10.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    return parser.parse_args()


def main() -> None:
    results = Path(parse_args().results)
    stability = pd.read_csv(results / "occurrence_patch_label_stability.csv")
    members = pd.read_csv(results / "candidate_patch_occurrence_connectivity.csv")
    clusters = pd.read_csv(results / "independent_detection_clusters.csv")

    patch = (
        members.sort_values("gap_patch_id")
        .drop_duplicates("gap_patch_id")
        [[
            "gap_patch_id",
            "survey_area_id",
            "gap_patch_centroid_latitude",
            "gap_patch_centroid_longitude",
            "gap_patch_member_count",
            "gap_patch_support_mean",
            "gap_patch_score",
            "candidate_occurrence_edge_distance_m",
            "candidate_occurrence_gap_width_m",
        ]]
    )
    ranked = patch.merge(stability, on=["gap_patch_id", "survey_area_id"], how="inner")
    ranked = ranked[ranked["ever_near_disconnected"]].copy()
    ranked["robust_near_disconnected_priority_score"] = (
        ranked["near_disconnected_frequency"] * ranked["gap_patch_score"]
    )
    ranked["priority_uses_2026_field_detections"] = False
    ranked = ranked.sort_values(
        [
            "robust_near_disconnected_priority_score",
            "near_disconnected_frequency",
            "gap_patch_score",
            "candidate_occurrence_edge_distance_m",
            "gap_patch_id",
        ],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)
    ranked["robust_near_disconnected_rank"] = ranked.index + 1

    evaluation_rows: list[dict[str, object]] = []
    for row in ranked.itertuples(index=False):
        selected = members[members["gap_patch_id"].eq(row.gap_patch_id)]
        recovery = cluster_patch_recovery_table(
            selected,
            clusters,
            cluster_col="cluster_id",
            radii_km=RADII_KM,
        )
        item: dict[str, object] = {"gap_patch_id": row.gap_patch_id}
        for radius in RADII_KM:
            column = f"recovered_within_{radius:g}km"
            item[f"field_cluster_recall_{radius:g}km"] = float(recovery[column].mean())
        item["field_validation_used_only_for_evaluation"] = True
        evaluation_rows.append(item)

    evaluation = pd.DataFrame(evaluation_rows)
    ranked = ranked.merge(evaluation, on="gap_patch_id", how="left")
    ranked.to_csv(results / "robust_near_disconnected_patch_ranking.csv", index=False)

    summary = {
        "priority_definition": "near_disconnected_frequency * frozen gap_patch_score",
        "field_data_used_in_priority": False,
        "ranked_patch_count": int(len(ranked)),
        "top_patch_id": None if ranked.empty else str(ranked.iloc[0]["gap_patch_id"]),
        "top_patch_island": None if ranked.empty else str(ranked.iloc[0]["survey_area_id"]),
    }
    (results / "robust_near_disconnected_patch_ranking_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
