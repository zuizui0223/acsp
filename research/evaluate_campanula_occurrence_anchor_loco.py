"""Evaluate an occurrence-only local-discovery baseline with whole-cluster holdout.

Scientific role: Campanula development diagnosis only. This evaluator reads the
pre-2026 occurrence cache and frozen island bounds, but never reads the inspected
2026 field detections. It asks how often a historical occurrence cluster would
fall inside an annular search around the retained same-island clusters when the
whole focal cluster is removed.

The output is a baseline curve, not a promoted survey algorithm. Search-area
figures are unclipped sums of circular annuli; they are diagnostic upper bounds,
not land area, reachable area, route length, time, or budget.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OCCURRENCES = (
    REPO_ROOT
    / "field_validation"
    / "campanula_microdonta"
    / "development_data"
    / "gbif_training_occurrences_through_2025.csv"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "field_validation"
    / "campanula_microdonta"
    / "development_data"
    / "manifest.json"
)
DEFAULT_OUT_DIR = REPO_ROOT / "validation" / "campanula_occurrence_anchor_loco_v1"
EARTH_RADIUS_M = 6_371_008.8
PRIMARY_CLUSTER_POLICY = "single_link"
SENSITIVITY_CLUSTER_POLICY = "complete_link"
SUPPORTED_CLUSTER_POLICIES = (PRIMARY_CLUSTER_POLICY, SENSITIVITY_CLUSTER_POLICY)


def haversine_m(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance in metres."""
    phi_a = math.radians(float(latitude_a))
    phi_b = math.radians(float(latitude_b))
    delta_phi = math.radians(float(latitude_b) - float(latitude_a))
    delta_lambda = math.radians(float(longitude_b) - float(longitude_a))
    value = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_a)
        * math.cos(phi_b)
        * math.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(max(0.0, min(1.0, value))))


def assign_island(
    latitude: float,
    longitude: float,
    island_bounds: Mapping[str, Sequence[float]],
) -> str | None:
    """Assign one point to a non-overlapping frozen island rectangle."""
    matches: list[str] = []
    for island, bounds in island_bounds.items():
        if len(bounds) != 4:
            raise ValueError(
                f"island_bounds[{island!r}] must contain "
                "[min_lon, min_lat, max_lon, max_lat]"
            )
        min_lon, min_lat, max_lon, max_lat = map(float, bounds)
        if min_lat <= float(latitude) <= max_lat and min_lon <= float(longitude) <= max_lon:
            matches.append(str(island))
    if len(matches) > 1:
        raise ValueError(f"point falls in overlapping island bounds: {matches}")
    return matches[0] if matches else None


def prepare_island_occurrences(
    occurrences: pd.DataFrame,
    island_bounds: Mapping[str, Sequence[float]],
) -> pd.DataFrame:
    """Clean historical coordinates and retain only the frozen five-island frame."""
    required = {"_latitude", "_longitude"}
    missing = sorted(required.difference(occurrences.columns))
    if missing:
        raise ValueError(f"occurrence table is missing columns: {missing}")

    work = occurrences.copy().reset_index(drop=True)
    work["latitude"] = pd.to_numeric(work["_latitude"], errors="coerce")
    work["longitude"] = pd.to_numeric(work["_longitude"], errors="coerce")
    work = work.dropna(subset=["latitude", "longitude"]).copy()
    valid = work["latitude"].between(-90, 90) & work["longitude"].between(-180, 180)
    work = work.loc[valid].copy()
    work["island"] = [
        assign_island(lat, lon, island_bounds)
        for lat, lon in zip(work["latitude"], work["longitude"])
    ]
    work = work.dropna(subset=["island"]).copy()
    if "_row_id" in work.columns:
        stable_id = pd.to_numeric(work["_row_id"], errors="coerce")
    else:
        stable_id = pd.Series(np.arange(len(work)), index=work.index, dtype=float)
    work["source_occurrence_id"] = stable_id
    work["_stable_text"] = work.index.astype(str)
    work = work.sort_values(
        ["island", "source_occurrence_id", "_stable_text", "latitude", "longitude"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    work["source_occurrence_id"] = [
        str(int(value)) if pd.notna(value) and float(value).is_integer() else str(value)
        for value in work["source_occurrence_id"]
    ]
    return work.loc[:, ["source_occurrence_id", "island", "latitude", "longitude"]]


def _distance_matrix_m(group: pd.DataFrame) -> np.ndarray:
    n = len(group)
    matrix = np.zeros((n, n), dtype=float)
    rows = group.loc[:, ["latitude", "longitude"]].to_numpy(float)
    for i in range(n):
        for j in range(i + 1, n):
            distance = haversine_m(rows[i, 0], rows[i, 1], rows[j, 0], rows[j, 1])
            matrix[i, j] = distance
            matrix[j, i] = distance
    return matrix


def _single_link_members(distance_matrix: np.ndarray, threshold_m: float) -> list[list[int]]:
    """Return connected components under a pairwise distance threshold."""
    n = len(distance_matrix)
    unvisited = set(range(n))
    clusters: list[list[int]] = []
    while unvisited:
        seed = min(unvisited)
        unvisited.remove(seed)
        stack = [seed]
        members: list[int] = []
        while stack:
            current = stack.pop()
            members.append(current)
            neighbours = [
                candidate
                for candidate in sorted(unvisited)
                if distance_matrix[current, candidate] <= threshold_m
            ]
            for candidate in neighbours:
                unvisited.remove(candidate)
                stack.append(candidate)
        clusters.append(sorted(members))
    return clusters


def _complete_link_members(distance_matrix: np.ndarray, threshold_m: float) -> list[list[int]]:
    """Return deterministic agglomerative complete-link clusters."""
    clusters: list[tuple[int, ...]] = [(index,) for index in range(len(distance_matrix))]
    while True:
        candidates: list[tuple[float, tuple[int, ...], tuple[int, ...], int, int]] = []
        for left in range(len(clusters)):
            for right in range(left + 1, len(clusters)):
                left_members = clusters[left]
                right_members = clusters[right]
                linkage = max(
                    float(distance_matrix[i, j])
                    for i in left_members
                    for j in right_members
                )
                if linkage <= threshold_m:
                    candidates.append(
                        (linkage, left_members, right_members, left, right)
                    )
        if not candidates:
            break
        _, _, _, left, right = min(candidates)
        merged = tuple(sorted(clusters[left] + clusters[right]))
        clusters = [
            cluster
            for index, cluster in enumerate(clusters)
            if index not in {left, right}
        ]
        clusters.append(merged)
        clusters.sort()
    return [list(cluster) for cluster in clusters]


def _medoid_index(distance_matrix: np.ndarray, members: Sequence[int]) -> int:
    ordered = list(sorted(int(member) for member in members))
    sums = [float(distance_matrix[index, ordered].sum()) for index in ordered]
    return ordered[int(np.argmin(sums))]


def cluster_occurrence_points(
    points: pd.DataFrame,
    *,
    cluster_radius_m: float = 500.0,
    policy: str = PRIMARY_CLUSTER_POLICY,
) -> pd.DataFrame:
    """Cluster historical rows within islands and return bounded audit fields."""
    if float(cluster_radius_m) <= 0:
        raise ValueError("cluster_radius_m must be positive")
    if policy not in SUPPORTED_CLUSTER_POLICIES:
        raise ValueError(
            f"policy must be one of {SUPPORTED_CLUSTER_POLICIES}, got {policy!r}"
        )
    required = {"source_occurrence_id", "island", "latitude", "longitude"}
    missing = sorted(required.difference(points.columns))
    if missing:
        raise ValueError(f"points are missing columns: {missing}")

    rows: list[dict[str, object]] = []
    next_cluster = 1
    for island, source_group in points.groupby("island", sort=True):
        group = source_group.sort_values(
            ["source_occurrence_id", "latitude", "longitude"], kind="mergesort"
        ).reset_index(drop=True)
        distance_matrix = _distance_matrix_m(group)
        if policy == PRIMARY_CLUSTER_POLICY:
            member_sets = _single_link_members(distance_matrix, float(cluster_radius_m))
        else:
            member_sets = _complete_link_members(distance_matrix, float(cluster_radius_m))

        for members in member_sets:
            medoid = _medoid_index(distance_matrix, members)
            diameter = max(
                (float(distance_matrix[i, j]) for i in members for j in members),
                default=0.0,
            )
            source_ids = group.iloc[members]["source_occurrence_id"].astype(str).tolist()
            rows.append(
                {
                    "historical_cluster_id": next_cluster,
                    "cluster_policy": policy,
                    "island": str(island),
                    "latitude": float(group.iloc[medoid]["latitude"]),
                    "longitude": float(group.iloc[medoid]["longitude"]),
                    "n_source_rows": int(len(members)),
                    "source_occurrence_ids": ";".join(source_ids),
                    "cluster_radius_m": float(cluster_radius_m),
                    "cluster_diameter_m": float(diameter),
                    "single_link_chain_warning": bool(
                        policy == PRIMARY_CLUSTER_POLICY
                        and float(diameter) > float(cluster_radius_m) + 1e-9
                    ),
                }
            )
            next_cluster += 1
    return pd.DataFrame(rows).sort_values(
        ["cluster_policy", "island", "historical_cluster_id"], kind="mergesort"
    ).reset_index(drop=True)


def leave_one_cluster_out_distances(
    clusters: pd.DataFrame,
    *,
    exclusion_radius_km: float = 0.5,
    outer_radii_km: Sequence[float] = (1.0, 2.0, 5.0),
) -> pd.DataFrame:
    """Hide each whole cluster and measure distance to retained same-island anchors."""
    if float(exclusion_radius_km) < 0:
        raise ValueError("exclusion_radius_km must be non-negative")
    radii = tuple(sorted({float(radius) for radius in outer_radii_km}))
    if not radii or any(radius <= exclusion_radius_km for radius in radii):
        raise ValueError("every outer radius must exceed exclusion_radius_km")
    required = {
        "historical_cluster_id",
        "cluster_policy",
        "island",
        "latitude",
        "longitude",
    }
    missing = sorted(required.difference(clusters.columns))
    if missing:
        raise ValueError(f"clusters are missing columns: {missing}")

    rows: list[dict[str, object]] = []
    for hidden in clusters.to_dict(orient="records"):
        same_island = clusters.loc[
            clusters["island"].astype(str).eq(str(hidden["island"]))
            & clusters["cluster_policy"].astype(str).eq(str(hidden["cluster_policy"]))
            & ~clusters["historical_cluster_id"].eq(hidden["historical_cluster_id"])
        ].copy()
        nearest_distance_km: float | None = None
        nearest_cluster_id: int | None = None
        if not same_island.empty:
            distances = [
                (
                    haversine_m(
                        float(hidden["latitude"]),
                        float(hidden["longitude"]),
                        float(anchor["latitude"]),
                        float(anchor["longitude"]),
                    )
                    / 1000.0,
                    int(anchor["historical_cluster_id"]),
                )
                for anchor in same_island.to_dict(orient="records")
            ]
            nearest_distance_km, nearest_cluster_id = min(distances)

        anchor_absent = nearest_distance_km is None
        inside_exclusion = bool(
            nearest_distance_km is not None
            and nearest_distance_km <= float(exclusion_radius_km) + 1e-12
        )
        row: dict[str, object] = {
            "cluster_policy": hidden["cluster_policy"],
            "hidden_cluster_id": hidden["historical_cluster_id"],
            "island": hidden["island"],
            "hidden_latitude": hidden["latitude"],
            "hidden_longitude": hidden["longitude"],
            "retained_same_island_anchor_count": int(len(same_island)),
            "nearest_retained_cluster_id": nearest_cluster_id,
            "nearest_retained_anchor_km": nearest_distance_km,
            "anchor_absent": anchor_absent,
            "inside_known_point_exclusion": inside_exclusion,
            "anchor_conditioned_evaluable": bool(not anchor_absent and not inside_exclusion),
            "known_point_exclusion_km": float(exclusion_radius_km),
        }
        for radius in radii:
            row[f"recovered_annulus_{radius:g}km"] = bool(
                nearest_distance_km is not None
                and nearest_distance_km > float(exclusion_radius_km)
                and nearest_distance_km <= radius
            )
            # This is deliberately not called field effort: overlap, coastlines,
            # land masks, and reachability are not represented in this baseline.
            row[f"unclipped_sum_annulus_area_{radius:g}km2"] = float(
                len(same_island)
                * math.pi
                * (radius**2 - float(exclusion_radius_km) ** 2)
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["cluster_policy", "island", "hidden_cluster_id"], kind="mergesort"
    ).reset_index(drop=True)


def annular_baseline_curve(
    folds: pd.DataFrame,
    *,
    outer_radii_km: Sequence[float] = (1.0, 2.0, 5.0),
) -> pd.DataFrame:
    """Aggregate annular recovery separately for each clustering policy."""
    radii = tuple(sorted({float(radius) for radius in outer_radii_km}))
    rows: list[dict[str, object]] = []
    for policy, group in folds.groupby("cluster_policy", sort=True):
        evaluable = group["anchor_conditioned_evaluable"].astype(bool)
        for radius in radii:
            recovered = group[f"recovered_annulus_{radius:g}km"].astype(bool)
            area = pd.to_numeric(
                group[f"unclipped_sum_annulus_area_{radius:g}km2"], errors="coerce"
            )
            rows.append(
                {
                    "cluster_policy": str(policy),
                    "outer_radius_km": radius,
                    "known_point_exclusion_km": float(
                        group["known_point_exclusion_km"].iloc[0]
                    ),
                    "declared_folds": int(len(group)),
                    "anchor_conditioned_evaluable_folds": int(evaluable.sum()),
                    "anchor_absent_folds": int(group["anchor_absent"].astype(bool).sum()),
                    "inside_exclusion_folds": int(
                        group["inside_known_point_exclusion"].astype(bool).sum()
                    ),
                    "recovered_folds": int(recovered.sum()),
                    "anchor_conditioned_recall": (
                        float(recovered.loc[evaluable].mean()) if evaluable.any() else None
                    ),
                    "intention_to_evaluate_recall": float(recovered.mean()),
                    "median_unclipped_sum_annulus_area_km2": float(area.median()),
                    "interpretation": (
                        "Occurrence-only annular baseline; area is an unclipped sum "
                        "around retained anchors, not reachable field effort."
                    ),
                }
            )
    return pd.DataFrame(rows)


def evaluate_occurrence_anchor_loco(
    occurrences: pd.DataFrame,
    island_bounds: Mapping[str, Sequence[float]],
    *,
    cluster_radius_m: float = 500.0,
    exclusion_radius_km: float = 0.5,
    outer_radii_km: Sequence[float] = (1.0, 2.0, 5.0),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Return occurrence clusters, whole-cluster folds, curve, and summary."""
    points = prepare_island_occurrences(occurrences, island_bounds)
    cluster_frames = [
        cluster_occurrence_points(
            points,
            cluster_radius_m=cluster_radius_m,
            policy=policy,
        )
        for policy in SUPPORTED_CLUSTER_POLICIES
    ]
    clusters = pd.concat(cluster_frames, ignore_index=True)
    folds = leave_one_cluster_out_distances(
        clusters,
        exclusion_radius_km=exclusion_radius_km,
        outer_radii_km=outer_radii_km,
    )
    curve = annular_baseline_curve(folds, outer_radii_km=outer_radii_km)

    policy_summaries: dict[str, object] = {}
    for policy, group in clusters.groupby("cluster_policy", sort=True):
        policy_folds = folds.loc[folds["cluster_policy"].eq(policy)]
        distances = pd.to_numeric(
            policy_folds["nearest_retained_anchor_km"], errors="coerce"
        ).dropna()
        policy_curve = curve.loc[curve["cluster_policy"].eq(policy)]
        policy_summaries[str(policy)] = {
            "clusters": int(len(group)),
            "islands_with_clusters": int(group["island"].nunique()),
            "single_link_chain_warning_clusters": int(
                group["single_link_chain_warning"].astype(bool).sum()
            ),
            "anchor_absent_folds": int(policy_folds["anchor_absent"].astype(bool).sum()),
            "inside_exclusion_folds": int(
                policy_folds["inside_known_point_exclusion"].astype(bool).sum()
            ),
            "median_nearest_retained_anchor_km": (
                None if distances.empty else float(distances.median())
            ),
            "maximum_nearest_retained_anchor_km": (
                None if distances.empty else float(distances.max())
            ),
            "annular_curve": policy_curve.to_dict(orient="records"),
        }

    summary: dict[str, object] = {
        "schema_version": "campanula-occurrence-anchor-loco-v1",
        "scientific_role": "development_internal_baseline_only",
        "independent_validation": False,
        "reads_2026_field_outcomes": False,
        "historical_rows_inside_five_islands": int(len(points)),
        "cluster_radius_m": float(cluster_radius_m),
        "known_point_exclusion_km": float(exclusion_radius_km),
        "outer_radii_km": [float(value) for value in sorted(set(outer_radii_km))],
        "primary_cluster_policy": PRIMARY_CLUSTER_POLICY,
        "sensitivity_cluster_policy": SENSITIVITY_CLUSTER_POLICY,
        "policy_summaries": policy_summaries,
        "decision_rule": (
            "Do not add habitat or learned scores until their whole-cluster, "
            "matched-effort result can beat the annular nearest-known baseline."
        ),
        "interpretation_boundary": (
            "Historical occurrence-cluster reconstruction is development evidence; "
            "it does not estimate discovery probability, detection probability, "
            "reachable search area, field days, or external generalization."
        ),
    }
    return clusters, folds, curve, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--cluster-radius-m", type=float, default=500.0)
    parser.add_argument("--known-point-exclusion-km", type=float, default=0.5)
    parser.add_argument(
        "--outer-radii-km", type=float, nargs="+", default=[1.0, 2.0, 5.0]
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    island_bounds = manifest.get("island_bounds")
    if not isinstance(island_bounds, dict):
        raise ValueError("manifest must contain an island_bounds object")

    clusters, folds, curve, summary = evaluate_occurrence_anchor_loco(
        pd.read_csv(args.occurrences),
        island_bounds,
        cluster_radius_m=args.cluster_radius_m,
        exclusion_radius_km=args.known_point_exclusion_km,
        outer_radii_km=args.outer_radii_km,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "historical_occurrence_clusters.csv": clusters,
        "leave_one_cluster_out_folds.csv": folds,
        "annular_baseline_curve.csv": curve,
    }
    for filename, frame in outputs.items():
        path = args.out_dir / filename
        frame.to_csv(path, index=False)
        print(f"wrote {path}")
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()
