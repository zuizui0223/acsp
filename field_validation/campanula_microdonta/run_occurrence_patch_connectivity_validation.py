#!/usr/bin/env python3
"""Validate candidate patches that are near, but disconnected from occurrence patches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp import (
    OccurrencePatchConnectivityConfig,
    annotate_occurrence_patch_connectivity,
    build_occurrence_patches,
    cluster_patch_recovery_table,
)

RECOVERY_RADII_KM = (1.0, 2.0, 5.0, 10.0)
CONNECTIVITY_CLASSES = (
    "occurrence_patch_extension",
    "near_disconnected_occurrence_patch",
    "remote_candidate_patch",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    parser.add_argument("--occurrence-link-distance-m", type=float, default=500.0)
    parser.add_argument("--candidate-occurrence-link-distance-m", type=float, default=750.0)
    parser.add_argument("--near-disconnected-max-distance-m", type=float, default=5000.0)
    return parser.parse_args()


def ensure_cluster_id(clusters: pd.DataFrame) -> pd.DataFrame:
    out = clusters.copy().reset_index(drop=True)
    if "cluster_id" not in out.columns:
        candidate = next((c for c in out.columns if c.endswith("cluster_id")), None)
        out["cluster_id"] = out[candidate] if candidate is not None else np.arange(1, len(out) + 1)
    return out


def recover_by_island(selected: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for island, held in clusters.groupby("island", sort=True):
        members = selected[
            selected["survey_area_id"].astype(str).str.lower().eq(str(island).lower())
        ]
        if members.empty:
            empty = held[["cluster_id", "island"]].copy()
            empty["nearest_patch_id"] = None
            empty["nearest_patch_class"] = None
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
    candidate_members = pd.read_csv(results / "gap_patch_members_with_barriers.csv")
    known = pd.read_csv(results / "gbif_training_occurrences_through_2025.csv")
    clusters = ensure_cluster_id(pd.read_csv(results / "independent_detection_clusters.csv"))

    config = OccurrencePatchConnectivityConfig(
        occurrence_link_distance_m=args.occurrence_link_distance_m,
        candidate_occurrence_link_distance_m=args.candidate_occurrence_link_distance_m,
        near_disconnected_max_distance_m=args.near_disconnected_max_distance_m,
    )
    occurrence_members = build_occurrence_patches(
        known,
        link_distance_m=config.occurrence_link_distance_m,
    )
    annotated = annotate_occurrence_patch_connectivity(
        candidate_members,
        known,
        config=config,
    )

    occurrence_members.to_csv(results / "known_occurrence_patch_members.csv", index=False)
    annotated.to_csv(results / "candidate_patch_occurrence_connectivity.csv", index=False)

    patch_level = annotated.drop_duplicates("gap_patch_id").copy()
    class_rows: list[dict[str, object]] = []
    recovery_rows: list[pd.DataFrame] = []
    for connectivity_class in CONNECTIVITY_CLASSES:
        selected = annotated[
            annotated["occurrence_patch_connectivity_class"].eq(connectivity_class)
        ].copy()
        recovery = recover_by_island(selected, clusters)
        recovery["occurrence_patch_connectivity_class"] = connectivity_class
        recovery_rows.append(recovery)
        row: dict[str, object] = {
            "occurrence_patch_connectivity_class": connectivity_class,
            "patch_count": int(selected["gap_patch_id"].nunique()) if not selected.empty else 0,
            "member_count": int(len(selected)),
            "held_out_cluster_count": int(len(recovery)),
        }
        for radius in RECOVERY_RADII_KM:
            column = f"recovered_within_{radius:g}km"
            row[f"cluster_recall_{radius:g}km"] = (
                float(recovery[column].mean()) if column in recovery and len(recovery) else 0.0
            )
        finite = recovery["nearest_patch_distance_m"].replace([np.inf, -np.inf], np.nan).dropna()
        row["median_nearest_patch_distance_m"] = float(finite.median()) if len(finite) else None
        class_rows.append(row)

    pd.concat(recovery_rows, ignore_index=True).to_csv(
        results / "occurrence_patch_connectivity_cluster_recovery.csv", index=False
    )
    class_summary = pd.DataFrame(class_rows)
    class_summary.to_csv(results / "occurrence_patch_connectivity_summary.csv", index=False)

    summary = {
        "design": "known occurrences clustered first; candidate patches classified by edge-to-edge distance",
        "field_data_used_in_candidate_or_parameter_construction": False,
        "occurrence_patch_count": int(occurrence_members["occurrence_patch_id"].nunique()),
        "candidate_patch_count": int(patch_level["gap_patch_id"].nunique()),
        "candidate_patch_class_counts": {
            str(key): int(value)
            for key, value in patch_level[
                "occurrence_patch_connectivity_class"
            ].value_counts().items()
        },
        "occurrence_link_distance_m": config.occurrence_link_distance_m,
        "candidate_occurrence_link_distance_m": config.candidate_occurrence_link_distance_m,
        "near_disconnected_max_distance_m": config.near_disconnected_max_distance_m,
        "primary_target": "near_disconnected_occurrence_patch",
        "scientific_guardrail": (
            "Disconnected means separate under the declared distance graph, not demonstrated demographic, "
            "habitat, or dispersal isolation."
        ),
    }
    (results / "occurrence_patch_connectivity_validation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
