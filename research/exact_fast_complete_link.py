#!/usr/bin/env python3
"""Research-only exact acceleration of the frozen complete-link patch aggregation.

This changes only candidate lookup. A patch can accept a point under the frozen
complete-link rule only if the point is within the merge threshold of the
patch's first member. First members are indexed on the unit sphere in a 3-D
chord-distance grid, so patches that cannot possibly be compatible are skipped.
Every potentially compatible patch is still evaluated with the original exact
haversine/max-distance rule and the original `(maximum, patch_index)` tie break.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd

from acsp.robust_patches import EARTH_RADIUS_M, _haversine_m, _safe_area_token


def _unit_vector(latitude: float, longitude: float) -> tuple[float, float, float]:
    lat = math.radians(float(latitude))
    lon = math.radians(float(longitude))
    c = math.cos(lat)
    return c * math.cos(lon), c * math.sin(lon), math.sin(lat)


def _grid_key(vector: tuple[float, float, float], cell: float) -> tuple[int, int, int]:
    return tuple(int(math.floor((float(v) + 1.0) / cell)) for v in vector)


def exact_fast_complete_link_support_patches(
    selected: pd.DataFrame,
    *,
    merge_distance_m: float,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    area_col: str = "survey_area_id",
) -> pd.DataFrame:
    """Return exactly the frozen complete-link patch table with faster lookup."""
    if selected.empty:
        return pd.DataFrame()
    threshold = float(merge_distance_m)
    if threshold <= 0:
        raise ValueError("merge_distance_m must be positive")

    work = selected.copy().reset_index(drop=True)
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if work.empty:
        return pd.DataFrame()

    # Great-circle distance <= threshold implies 3-D unit-sphere chord distance
    # <= this value. Therefore each Cartesian coordinate differs by at most one
    # cell when cell width equals the threshold chord. Search the 27 neighbors.
    angular = threshold / float(EARTH_RADIUS_M)
    chord = 2.0 * math.sin(angular / 2.0)
    if not chord > 0.0:
        raise ValueError("merge_distance_m produces a non-positive chord")

    patch_members: list[tuple[object, int, list[int]]] = []
    for area, group in work.groupby(area_col, sort=True, dropna=False):
        ordered = group.assign(
            _stable_numeric=pd.to_numeric(group["site_id"], errors="coerce"),
            _stable_id=group["site_id"].astype(str),
        ).sort_values(
            ["_stable_numeric", "_stable_id", latitude_col, longitude_col],
            kind="mergesort",
            na_position="last",
        )
        area_patches: list[list[int]] = []
        first_member_grid: dict[tuple[int, int, int], list[int]] = defaultdict(list)

        for index in ordered.index:
            vector = _unit_vector(work.at[index, latitude_col], work.at[index, longitude_col])
            key = _grid_key(vector, chord)
            candidate_patch_indices: set[int] = set()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        candidate_patch_indices.update(
                            first_member_grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ())
                        )

            compatible: list[tuple[float, int]] = []
            for patch_index in sorted(candidate_patch_indices):
                member_indices = area_patches[patch_index]
                members = work.loc[member_indices]
                distances = _haversine_m(
                    work.at[index, latitude_col],
                    work.at[index, longitude_col],
                    members[latitude_col].to_numpy(float),
                    members[longitude_col].to_numpy(float),
                )
                maximum = float(distances.max()) if len(distances) else 0.0
                if maximum <= threshold:
                    compatible.append((maximum, patch_index))

            if compatible:
                patch_index = min(compatible)[1]
                area_patches[patch_index].append(index)
            else:
                patch_index = len(area_patches)
                area_patches.append([index])
                first_member_grid[key].append(patch_index)

        for patch_number, indices in enumerate(area_patches, start=1):
            patch_members.append((area, patch_number, indices))

    rows: list[dict[str, object]] = []
    for area, patch_number, indices in patch_members:
        members = work.loc[indices].copy()
        representative = members.assign(
            _support_rank=pd.to_numeric(members["ecological_support_rank"], errors="coerce"),
            _stable_id=members["site_id"].astype(str),
        ).sort_values(
            ["_support_rank", "_stable_id", latitude_col, longitude_col],
            kind="mergesort",
            na_position="last",
        ).iloc[0]
        distances = _haversine_m(
            representative[latitude_col],
            representative[longitude_col],
            members[latitude_col].to_numpy(float),
            members[longitude_col].to_numpy(float),
        )
        zone_id = f"{_safe_area_token(area)}-Z{patch_number:03d}"
        rows.append(
            {
                "zone_id": zone_id,
                area_col: area,
                "zone_member_count": int(len(members)),
                "zone_radius_m": round(float(distances.max()) if len(distances) else 0.0, 1),
                "zone_merge_threshold_m": round(threshold, 1),
                "representative_site_id": str(representative["site_id"]),
                "latitude": float(representative[latitude_col]),
                "longitude": float(representative[longitude_col]),
                "zone_member_site_ids": ";".join(members["site_id"].astype(str).tolist()),
            }
        )
    zones = pd.DataFrame(rows)
    if zones.empty:
        return zones
    zones["_neutral_area_sort"] = zones[area_col].astype(str)
    return zones.sort_values(
        ["_neutral_area_sort", "zone_id"],
        kind="mergesort",
    ).drop(columns="_neutral_area_sort").reset_index(drop=True)


def exact_fast_support_cells_to_patches(
    universe: pd.DataFrame,
    support_rank: np.ndarray,
    *,
    threshold: float,
    threshold_tolerance: float = 0.0,
    merge_distance_m: float = 1000.0,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    area_col: str = "survey_area_id",
    ecological_status: str = "robust_support_patch",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mirror frozen support_cells_to_patches, changing lookup implementation only."""
    ranks = np.asarray(support_rank, dtype=float)
    if len(ranks) != len(universe):
        raise ValueError("support_rank length must match universe rows")
    required = {latitude_col, longitude_col, area_col}
    missing = required - set(universe.columns)
    if missing:
        raise ValueError("candidate universe lacks required columns: " + ", ".join(sorted(missing)))
    cutoff = float(threshold) + float(threshold_tolerance)
    keep = np.isfinite(ranks) & (ranks <= cutoff)
    selected = universe.loc[keep].copy()
    selected["universe_index"] = np.flatnonzero(keep)
    selected["site_id"] = selected["universe_index"].astype(str)
    selected["priority_score"] = 1.0 - ranks[keep]
    selected["candidate_type"] = "robust ecological support cell"
    selected["ecological_support_rank"] = ranks[keep]
    if selected.empty:
        return selected.reset_index(drop=True), pd.DataFrame()

    zones = exact_fast_complete_link_support_patches(
        selected,
        merge_distance_m=float(merge_distance_m),
        area_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )
    zones = zones.copy()
    zones["ecological_support_threshold"] = float(threshold)
    zones["ecological_status"] = str(ecological_status)
    zones["site_id"] = zones["zone_id"].astype(str)
    return selected.reset_index(drop=True), zones.reset_index(drop=True)


__all__ = ["exact_fast_complete_link_support_patches", "exact_fast_support_cells_to_patches"]
