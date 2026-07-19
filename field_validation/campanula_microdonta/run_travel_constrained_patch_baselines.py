#!/usr/bin/env python3
"""Compare patch priorities under identical island travel-distance limits."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.gap_validation import select_gap_patches_within_travel_distance
from run_gap_patch_external_validation import (
    ISLAND_BOUNDS,
    RECOVERY_RADII_KM,
    TRAVEL_FACTORS,
    ensure_cluster_id,
    island_geometry,
    recover_by_island,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    parser.add_argument("--random-draws", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260718)
    return parser.parse_args()


def select_all_islands(
    members: pd.DataFrame,
    factor: float,
    *,
    priority_col: str,
    higher_priority_is_better: bool,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for island in sorted(ISLAND_BOUNDS):
        island_members = members[
            members["survey_area_id"].astype(str).str.lower().eq(island)
        ].copy()
        if island_members.empty:
            continue
        origin_lat, origin_lon, diagonal_m = island_geometry(island)
        selected = select_gap_patches_within_travel_distance(
            island_members,
            origin_lat,
            origin_lon,
            factor * diagonal_m,
            priority_col=priority_col,
            higher_priority_is_better=higher_priority_is_better,
        )
        if not selected.empty:
            selected["survey_area_id"] = island
            parts.append(selected)
    return pd.concat(parts, ignore_index=True) if parts else members.iloc[0:0].copy()


def summarize_selection(
    method: str,
    draw: int,
    factor: float,
    selected: pd.DataFrame,
    clusters: pd.DataFrame,
) -> dict[str, object]:
    recovery = recover_by_island(selected, clusters)
    row: dict[str, object] = {
        "method": method,
        "draw": int(draw),
        "travel_factor": float(factor),
        "selected_patch_count": int(selected["gap_patch_id"].nunique()) if not selected.empty else 0,
        "held_out_cluster_count": int(len(recovery)),
        "median_nearest_patch_distance_m": (
            float(recovery["nearest_patch_distance_m"].median()) if not recovery.empty else np.nan
        ),
    }
    for radius in RECOVERY_RADII_KM:
        column = f"recovered_within_{radius:g}km"
        row[f"cluster_recall_{radius:g}km"] = (
            float(recovery[column].mean()) if column in recovery else 0.0
        )
    return row


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    members = pd.read_csv(results / "gap_patch_members_with_barriers.csv")
    clusters = ensure_cluster_id(pd.read_csv(results / "independent_detection_clusters.csv"))

    methods = (
        ("gap_patch_score", "gap_patch_score", True),
        ("support_only", "gap_patch_support_mean", True),
        ("nearest_known", "gap_patch_nearest_known_m", False),
        ("farthest_known", "gap_patch_nearest_known_m", True),
    )
    rows: list[dict[str, object]] = []
    for factor in TRAVEL_FACTORS:
        for method, priority_col, higher in methods:
            selected = select_all_islands(
                members,
                factor,
                priority_col=priority_col,
                higher_priority_is_better=higher,
            )
            rows.append(summarize_selection(method, 0, factor, selected, clusters))

    patch_ids = sorted(members["gap_patch_id"].astype(str).unique())
    rng = np.random.default_rng(int(args.seed))
    for draw in range(1, max(1, int(args.random_draws)) + 1):
        random_values = dict(zip(patch_ids, rng.random(len(patch_ids))))
        random_members = members.copy()
        random_members["random_priority"] = random_members["gap_patch_id"].astype(str).map(random_values)
        for factor in TRAVEL_FACTORS:
            selected = select_all_islands(
                random_members,
                factor,
                priority_col="random_priority",
                higher_priority_is_better=True,
            )
            rows.append(summarize_selection("random", draw, factor, selected, clusters))

    raw = pd.DataFrame(rows)
    raw.to_csv(results / "travel_constrained_patch_baseline_draws.csv", index=False)
    deterministic = raw[raw["method"].ne("random")].copy()
    random_summary = (
        raw[raw["method"].eq("random")]
        .groupby("travel_factor", as_index=False)
        .agg(
            random_recall_1km_mean=("cluster_recall_1km", "mean"),
            random_recall_1km_q025=("cluster_recall_1km", lambda x: float(np.quantile(x, 0.025))),
            random_recall_1km_q975=("cluster_recall_1km", lambda x: float(np.quantile(x, 0.975))),
            random_recall_2km_mean=("cluster_recall_2km", "mean"),
            random_recall_2km_q025=("cluster_recall_2km", lambda x: float(np.quantile(x, 0.025))),
            random_recall_2km_q975=("cluster_recall_2km", lambda x: float(np.quantile(x, 0.975))),
        )
    )
    deterministic.merge(random_summary, on="travel_factor", how="left").to_csv(
        results / "travel_constrained_patch_baseline_comparison.csv", index=False
    )


if __name__ == "__main__":
    main()
