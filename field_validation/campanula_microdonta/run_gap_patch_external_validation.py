#!/usr/bin/env python3
"""Evaluate gap-separated and barrier-supported patches against 2026 field detections.

This script consumes the already frozen temporal-validation outputs. Historical
GBIF records and candidate support are therefore fixed before the 2026 field
clusters are inspected. Travel sensitivity is expressed only through geometry:
each island uses its rectangle centre as the origin and multiples of the island
diagonal as the maximum closed-route distance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.gap_connectivity import CorridorBarrierConfig, annotate_gap_patch_barriers
from acsp.gap_patches import GapPatchConfig, discover_gap_patches, summarize_gap_patches
from acsp.gap_validation import cluster_patch_recovery_table, select_gap_patches_within_travel_distance
from acsp.field_validation import haversine_distance_m


ISLAND_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "oshima": (139.30, 34.64, 139.47, 34.82),
    "toshima": (139.24, 34.49, 139.31, 34.55),
    "niijima": (139.20, 34.33, 139.31, 34.44),
    "shikinejima": (139.18, 34.30, 139.24, 34.35),
    "kozushima": (139.09, 34.17, 139.18, 34.26),
}
TRAVEL_FACTORS = (0.5, 1.0, 2.0)
RECOVERY_RADII_KM = (1.0, 2.0, 5.0, 10.0)
SUPPORT_COL = "component_local_habitat_score"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    return parser.parse_args()


def island_geometry(island: str) -> tuple[float, float, float]:
    west, south, east, north = ISLAND_BOUNDS[island]
    latitude = (south + north) / 2.0
    longitude = (west + east) / 2.0
    diagonal = float(
        haversine_distance_m(south, west, np.array([north]), np.array([east]))[0]
    )
    return latitude, longitude, diagonal


def ensure_cluster_id(clusters: pd.DataFrame) -> pd.DataFrame:
    out = clusters.copy().reset_index(drop=True)
    if "cluster_id" not in out.columns:
        candidate = next((c for c in out.columns if c.endswith("cluster_id")), None)
        if candidate is not None:
            out["cluster_id"] = out[candidate]
        else:
            out["cluster_id"] = np.arange(1, len(out) + 1)
    return out


def recover_by_island(selected: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for island, held in clusters.groupby("island", sort=True):
        members = selected[selected["survey_area_id"].astype(str).str.lower().eq(str(island).lower())]
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
    pool = pd.read_csv(results / "distance_excluded_candidate_pool.csv")
    known = pd.read_csv(results / "gbif_training_occurrences_through_2025.csv")
    clusters = ensure_cluster_id(pd.read_csv(results / "independent_detection_clusters.csv"))

    if SUPPORT_COL not in pool.columns:
        raise RuntimeError(f"Frozen candidate pool lacks {SUPPORT_COL!r}.")
    if "survey_area_id" not in pool.columns:
        raise RuntimeError("Frozen candidate pool lacks survey_area_id.")

    patch_config = GapPatchConfig(
        support_thresholds=(0.45, 0.55, 0.65),
        link_distance_m=1_000.0,
        anchor_radius_m=750.0,
        satellite_max_distance_m=12_000.0,
        min_patch_members=2,
        min_overlap_fraction=0.5,
    )
    patch_members = discover_gap_patches(
        pool,
        known,
        support_col=SUPPORT_COL,
        candidate_id_col="site_id",
        config=patch_config,
    )
    if patch_members.empty:
        raise RuntimeError("No persistent gap patches were discovered from the frozen pool.")

    barrier_config = CorridorBarrierConfig(
        sample_spacing_m=250.0,
        interpolation_radius_m=750.0,
        low_support_threshold=0.35,
        min_barrier_length_m=750.0,
    )
    annotated = annotate_gap_patch_barriers(
        pool,
        patch_members,
        known,
        support_col=SUPPORT_COL,
        config=barrier_config,
    )
    annotated.to_csv(results / "gap_patch_members_with_barriers.csv", index=False)
    summarize_gap_patches(annotated).to_csv(results / "gap_patch_summary.csv", index=False)

    all_recovery = recover_by_island(annotated, clusters)
    all_recovery.to_csv(results / "gap_patch_all_field_cluster_recovery.csv", index=False)

    sensitivity_rows: list[dict[str, object]] = []
    selected_parts: list[pd.DataFrame] = []
    for factor in TRAVEL_FACTORS:
        factor_parts: list[pd.DataFrame] = []
        for island in sorted(ISLAND_BOUNDS):
            members = annotated[
                annotated["survey_area_id"].astype(str).str.lower().eq(island)
            ].copy()
            if members.empty:
                continue
            origin_lat, origin_lon, diagonal_m = island_geometry(island)
            max_distance_m = factor * diagonal_m
            selected = select_gap_patches_within_travel_distance(
                members,
                origin_lat,
                origin_lon,
                max_distance_m,
            )
            if not selected.empty:
                selected["travel_factor"] = factor
                selected["travel_origin_latitude"] = origin_lat
                selected["travel_origin_longitude"] = origin_lon
                selected["island_diagonal_m"] = diagonal_m
                selected["survey_area_id"] = island
                factor_parts.append(selected)
        selected_factor = pd.concat(factor_parts, ignore_index=True) if factor_parts else annotated.iloc[0:0]
        if not selected_factor.empty:
            selected_parts.append(selected_factor)
        recovery = recover_by_island(selected_factor, clusters)
        row: dict[str, object] = {
            "travel_factor": factor,
            "selected_patch_count": int(selected_factor["gap_patch_id"].nunique()) if not selected_factor.empty else 0,
            "selected_member_count": int(len(selected_factor)),
            "held_out_cluster_count": int(len(recovery)),
        }
        for radius in RECOVERY_RADII_KM:
            column = f"recovered_within_{radius:g}km"
            row[f"cluster_recall_{radius:g}km"] = float(recovery[column].mean()) if column in recovery else 0.0
        if not recovery.empty:
            row["median_nearest_patch_distance_m"] = float(recovery["nearest_patch_distance_m"].median())
        else:
            row["median_nearest_patch_distance_m"] = None
        sensitivity_rows.append(row)

    selected_all = pd.concat(selected_parts, ignore_index=True) if selected_parts else pd.DataFrame()
    selected_all.to_csv(results / "travel_constrained_gap_patch_members.csv", index=False)
    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity.to_csv(results / "gap_patch_travel_sensitivity.csv", index=False)

    patch_level = annotated.drop_duplicates("gap_patch_id")
    ecological_counts = {
        str(key): int(value)
        for key, value in patch_level["gap_patch_ecological_class"].value_counts().items()
    }
    summary = {
        "design": "post-frozen gap-patch analysis of the temporal external validation",
        "field_data_used_in_candidate_or_parameter_construction": False,
        "support_column": SUPPORT_COL,
        "patch_count": int(patch_level["gap_patch_id"].nunique()),
        "patch_member_count": int(len(annotated)),
        "ecological_patch_classes": ecological_counts,
        "barrier_separated_patch_count": int(
            patch_level["gap_patch_ecological_class"].eq("barrier_separated_patch").sum()
        ),
        "travel_constraint": "closed centroid route from island rectangle centre",
        "travel_factors_of_island_diagonal": list(TRAVEL_FACTORS),
        "scientific_guardrail": (
            "Corridor support is candidate-derived evidence along a transect, not proof of demographic "
            "or dispersal isolation. Positive field detections do not estimate occupancy or detectability."
        ),
    }
    (results / "gap_patch_external_validation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
