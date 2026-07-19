"""Validation and travel-constrained selection for gap-separated patches."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .gap_patches import haversine_distance_m, patch_recovery_table, summarize_gap_patches


def _point_distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    return float(haversine_distance_m(a_lat, a_lon, np.array([b_lat]), np.array([b_lon]))[0])


def _route_distance_m(points: list[tuple[float, float]], origin: tuple[float, float]) -> float:
    """Return closed-route distance through ordered points using great-circle legs."""
    if not points:
        return 0.0
    route = [origin, *points, origin]
    return float(sum(_point_distance_m(*route[index], *route[index + 1]) for index in range(len(route) - 1)))


def _best_insertion(
    route: list[tuple[float, float]],
    point: tuple[float, float],
    origin: tuple[float, float],
) -> tuple[float, int]:
    """Return minimum closed-route distance and insertion position for one point."""
    best_distance = float("inf")
    best_position = 0
    for position in range(len(route) + 1):
        candidate = [*route[:position], point, *route[position:]]
        distance = _route_distance_m(candidate, origin)
        if distance < best_distance:
            best_distance = distance
            best_position = position
    return best_distance, best_position


def select_gap_patches_within_travel_distance(
    patch_members: pd.DataFrame,
    origin_latitude: float,
    origin_longitude: float,
    max_travel_distance_m: float,
    *,
    allowed_classes: Iterable[str] | None = None,
    priority_col: str = "gap_patch_score",
    higher_priority_is_better: bool = True,
) -> pd.DataFrame:
    """Select whole patches whose centroid route fits a maximum travel distance.

    Patches are added greedily by priority per marginal route metre. Supplying an
    explicit ``priority_col`` allows support-only, nearest-anchor, random-order,
    or other baselines to be evaluated under exactly the same travel constraint.
    Patch count and member count are not treated as budgets.
    """
    if patch_members is None or patch_members.empty or max_travel_distance_m <= 0:
        return pd.DataFrame()
    work = patch_members.copy()
    if allowed_classes is not None:
        allowed = {str(value) for value in allowed_classes}
        work = work[work["gap_patch_class"].astype(str).isin(allowed)].copy()
    if work.empty:
        return work

    summary = summarize_gap_patches(work)
    if priority_col not in summary.columns:
        if priority_col not in work.columns:
            raise ValueError(f"priority column {priority_col!r} was not found")
        patch_priority = work.groupby("gap_patch_id", sort=True)[priority_col].mean()
        summary[priority_col] = summary["gap_patch_id"].map(patch_priority)
    priority = pd.to_numeric(summary[priority_col], errors="coerce")
    if priority.notna().sum() < 1:
        raise ValueError(f"priority column {priority_col!r} has no usable values")
    priority = priority.fillna(priority.min())
    if not higher_priority_is_better:
        priority = -priority
    summary["_selection_priority"] = priority

    origin = (float(origin_latitude), float(origin_longitude))
    route: list[tuple[float, float]] = []
    selected: list[str] = []
    route_distances: dict[str, float] = {}
    remaining = set(summary["gap_patch_id"].astype(str))

    while remaining:
        current_distance = _route_distance_m(route, origin)
        best: tuple[float, float, str, int] | None = None
        for patch_id in sorted(remaining):
            row = summary.loc[summary["gap_patch_id"].astype(str).eq(patch_id)].iloc[0]
            point = (
                float(row["gap_patch_centroid_latitude"]),
                float(row["gap_patch_centroid_longitude"]),
            )
            new_distance, position = _best_insertion(route, point, origin)
            marginal = max(new_distance - current_distance, 1.0)
            if new_distance > float(max_travel_distance_m):
                continue
            value = float(row["_selection_priority"])
            efficiency = value / marginal
            key = (efficiency, value, patch_id, position)
            if best is None or key[:2] > best[:2] or (key[:2] == best[:2] and patch_id < best[2]):
                best = key
        if best is None:
            break
        _, _, patch_id, position = best
        row = summary.loc[summary["gap_patch_id"].astype(str).eq(patch_id)].iloc[0]
        route.insert(position, (
            float(row["gap_patch_centroid_latitude"]),
            float(row["gap_patch_centroid_longitude"]),
        ))
        selected.append(patch_id)
        route_distances[patch_id] = _route_distance_m(route, origin)
        remaining.remove(patch_id)

    out = work[work["gap_patch_id"].astype(str).isin(selected)].copy()
    rank = {patch_id: index + 1 for index, patch_id in enumerate(selected)}
    out["gap_patch_selection_rank"] = out["gap_patch_id"].astype(str).map(rank).astype(int)
    out["gap_patch_route_distance_m"] = out["gap_patch_id"].astype(str).map(route_distances)
    out["gap_patch_max_travel_distance_m"] = float(max_travel_distance_m)
    out["gap_patch_selection_priority_col"] = priority_col
    return out.sort_values(["gap_patch_selection_rank", "gap_patch_id"]).reset_index(drop=True)


def cluster_patch_recovery_table(
    selected_members: pd.DataFrame,
    held_out_occurrences: pd.DataFrame,
    *,
    cluster_col: str = "cluster_id",
    radii_km: Iterable[float] = (1.0, 2.0, 5.0, 10.0),
) -> pd.DataFrame:
    """Return one recovery row per held-out population cluster."""
    if held_out_occurrences is None or held_out_occurrences.empty:
        return pd.DataFrame()
    held = held_out_occurrences.copy().reset_index(drop=True)
    if cluster_col not in held.columns:
        held[cluster_col] = np.arange(len(held), dtype=int)
    point_table = patch_recovery_table(selected_members, held, radii_km=radii_km)
    if point_table.empty:
        return point_table
    point_table[cluster_col] = held[cluster_col].to_numpy()
    recovered_cols = [column for column in point_table.columns if column.startswith("recovered_within_")]
    rows: list[dict[str, object]] = []
    for cluster_id, group in point_table.groupby(cluster_col, sort=True):
        nearest_row = group.loc[group["nearest_patch_distance_m"].idxmin()]
        row: dict[str, object] = {
            cluster_col: cluster_id,
            "nearest_patch_id": nearest_row["nearest_patch_id"],
            "nearest_patch_class": nearest_row["nearest_patch_class"],
            "nearest_patch_distance_m": float(nearest_row["nearest_patch_distance_m"]),
            "held_out_point_count": int(len(group)),
        }
        for column in recovered_cols:
            row[column] = bool(group[column].any())
        rows.append(row)
    return pd.DataFrame(rows)
