"""Occurrence-anchored discovery of disconnected survey patches.

This module deliberately does not estimate presence probability.  It groups
candidate locations that already have occurrence-conditioned environmental
support, then identifies components that are separated from known anchors by a
spatial gap.  The output unit is an operational patch rather than a ranked
single cell.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class GapPatchConfig:
    """Configuration for occurrence-anchored gap-patch discovery."""

    support_thresholds: tuple[float, ...] = (0.45, 0.55, 0.65)
    link_distance_m: float = 1_000.0
    anchor_radius_m: float = 750.0
    satellite_max_distance_m: float = 12_000.0
    min_patch_members: int = 2
    min_overlap_fraction: float = 0.5

    def validated_thresholds(self) -> tuple[float, ...]:
        values = sorted({float(value) for value in self.support_thresholds})
        if not values:
            raise ValueError("support_thresholds must not be empty")
        if values[0] < 0.0 or values[-1] > 1.0:
            raise ValueError("support_thresholds must lie in [0, 1]")
        return tuple(values)


def haversine_distance_m(
    lat: float,
    lon: float,
    other_lats: np.ndarray,
    other_lons: np.ndarray,
) -> np.ndarray:
    """Vectorized great-circle distance in metres."""

    lat1 = math.radians(float(lat))
    lon1 = math.radians(float(lon))
    lat2 = np.radians(np.asarray(other_lats, dtype=float))
    lon2 = np.radians(np.asarray(other_lons, dtype=float))
    a = (
        np.sin((lat2 - lat1) / 2.0) ** 2
        + math.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _validate_locations(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    required = {"latitude", "longitude"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {', '.join(sorted(missing))}")
    out = frame.copy().reset_index(drop=True)
    out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
    return out.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)


def _connected_components(latitudes: np.ndarray, longitudes: np.ndarray, radius_m: float) -> list[list[int]]:
    """Return radius-graph components without a heavy graph dependency."""

    count = len(latitudes)
    if count == 0:
        return []
    adjacency: list[list[int]] = [[] for _ in range(count)]
    for index in range(count):
        distances = haversine_distance_m(
            latitudes[index], longitudes[index], latitudes[index + 1 :], longitudes[index + 1 :]
        )
        neighbours = np.flatnonzero(distances <= float(radius_m)) + index + 1
        for neighbour in neighbours.tolist():
            adjacency[index].append(neighbour)
            adjacency[neighbour].append(index)

    components: list[list[int]] = []
    seen: set[int] = set()
    for start in range(count):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        members: list[int] = []
        while stack:
            node = stack.pop()
            members.append(node)
            for neighbour in adjacency[node]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        components.append(sorted(members))
    return components


def _components_by_threshold(
    candidates: pd.DataFrame,
    thresholds: Sequence[float],
    support_col: str,
    link_distance_m: float,
) -> dict[float, list[set[int]]]:
    result: dict[float, list[set[int]]] = {}
    for threshold in thresholds:
        eligible = candidates.index[candidates[support_col].ge(threshold)].to_numpy(dtype=int)
        subset = candidates.loc[eligible]
        components = _connected_components(
            subset["latitude"].to_numpy(float),
            subset["longitude"].to_numpy(float),
            link_distance_m,
        )
        result[threshold] = [{int(eligible[position]) for position in component} for component in components]
    return result


def _patch_persistence(
    members: set[int],
    components_by_threshold: dict[float, list[set[int]]],
    min_overlap_fraction: float,
) -> float:
    represented = 0
    for components in components_by_threshold.values():
        best_overlap = max((len(members & component) / len(members) for component in components), default=0.0)
        represented += int(best_overlap >= min_overlap_fraction)
    return represented / max(1, len(components_by_threshold))


def discover_gap_patches(
    candidates: pd.DataFrame,
    known_occurrences: pd.DataFrame,
    *,
    support_col: str = "integrated_support_score",
    candidate_id_col: str = "site_id",
    config: GapPatchConfig | None = None,
) -> pd.DataFrame:
    """Assign supported candidate points to anchor, satellite, or outpost patches.

    Candidate points are connected only when they are geographically close.  A
    connected component touching a known occurrence is an ``anchor_expansion``.
    A disconnected component within ``satellite_max_distance_m`` is a
    ``gap_separated_satellite``; more distant components are
    ``environmental_analogue_outpost`` patches.

    The same graph is rebuilt across several support thresholds.  Components
    that persist across thresholds receive a higher stability score.  The
    returned table contains one row per retained candidate member so downstream
    mapping and route planning do not lose the patch geometry.
    """

    cfg = config or GapPatchConfig()
    thresholds = cfg.validated_thresholds()
    if cfg.link_distance_m <= 0 or cfg.anchor_radius_m < 0:
        raise ValueError("link_distance_m must be positive and anchor_radius_m non-negative")
    if cfg.min_patch_members < 1:
        raise ValueError("min_patch_members must be at least one")

    work = _validate_locations(candidates, "candidates")
    known = _validate_locations(known_occurrences, "known_occurrences")
    if support_col not in work.columns:
        raise ValueError(f"candidates is missing support column: {support_col}")
    work[support_col] = pd.to_numeric(work[support_col], errors="coerce")
    work = work.dropna(subset=[support_col]).copy().reset_index(drop=True)
    work[support_col] = work[support_col].clip(0.0, 1.0)
    if candidate_id_col not in work.columns:
        work[candidate_id_col] = [f"candidate-{index + 1}" for index in range(len(work))]
    if work.empty:
        return work

    components_by_threshold = _components_by_threshold(work, thresholds, support_col, cfg.link_distance_m)
    base_threshold = thresholds[0]
    base_components = components_by_threshold[base_threshold]
    known_lats = known["latitude"].to_numpy(float)
    known_lons = known["longitude"].to_numpy(float)

    retained: list[pd.DataFrame] = []
    patch_rank_rows: list[tuple[str, float]] = []
    for ordinal, member_set in enumerate(base_components, start=1):
        if len(member_set) < cfg.min_patch_members:
            continue
        member_indices = sorted(member_set)
        patch = work.loc[member_indices].copy()
        if known.empty:
            nearest_known_m = math.inf
        else:
            nearest_known_m = min(
                float(np.min(haversine_distance_m(row.latitude, row.longitude, known_lats, known_lons)))
                for row in patch[["latitude", "longitude"]].itertuples(index=False)
            )

        if nearest_known_m <= cfg.anchor_radius_m:
            patch_class = "anchor_expansion"
        elif nearest_known_m <= cfg.satellite_max_distance_m:
            patch_class = "gap_separated_satellite"
        else:
            patch_class = "environmental_analogue_outpost"

        persistence = _patch_persistence(member_set, components_by_threshold, cfg.min_overlap_fraction)
        support_mean = float(patch[support_col].mean())
        centroid_lat = float(patch["latitude"].mean())
        centroid_lon = float(patch["longitude"].mean())
        radial = haversine_distance_m(
            centroid_lat,
            centroid_lon,
            patch["latitude"].to_numpy(float),
            patch["longitude"].to_numpy(float),
        )
        diameter_proxy_m = 2.0 * float(np.max(radial, initial=0.0))
        compactness = 1.0 / (1.0 + diameter_proxy_m / max(cfg.link_distance_m, 1.0))
        patch_score = support_mean * persistence * compactness
        patch_id = f"gap-patch-{ordinal:03d}"

        patch["gap_patch_id"] = patch_id
        patch["gap_patch_class"] = patch_class
        patch["gap_patch_member_count"] = len(patch)
        patch["gap_patch_support_mean"] = support_mean
        patch["gap_patch_persistence"] = persistence
        patch["gap_patch_nearest_known_m"] = nearest_known_m
        patch["gap_patch_width_m"] = max(0.0, nearest_known_m - cfg.anchor_radius_m)
        patch["gap_patch_centroid_latitude"] = centroid_lat
        patch["gap_patch_centroid_longitude"] = centroid_lon
        patch["gap_patch_diameter_proxy_m"] = diameter_proxy_m
        patch["gap_patch_score"] = patch_score
        retained.append(patch)
        patch_rank_rows.append((patch_id, patch_score))

    if not retained:
        return work.iloc[0:0].assign(
            gap_patch_id=pd.Series(dtype=str),
            gap_patch_class=pd.Series(dtype=str),
            gap_patch_score=pd.Series(dtype=float),
        )

    out = pd.concat(retained, ignore_index=True)
    ranks = {
        patch_id: rank
        for rank, (patch_id, _) in enumerate(
            sorted(patch_rank_rows, key=lambda item: (-item[1], item[0])), start=1
        )
    }
    out["gap_patch_rank"] = out["gap_patch_id"].map(ranks).astype(int)
    return out.sort_values(["gap_patch_rank", "gap_patch_id", candidate_id_col]).reset_index(drop=True)


def summarize_gap_patches(patch_members: pd.DataFrame) -> pd.DataFrame:
    """Collapse member rows to one transparent record per operational patch."""

    if patch_members is None or patch_members.empty:
        return pd.DataFrame()
    required = {
        "gap_patch_id",
        "gap_patch_class",
        "gap_patch_rank",
        "gap_patch_score",
        "gap_patch_support_mean",
        "gap_patch_persistence",
        "gap_patch_nearest_known_m",
        "gap_patch_width_m",
        "gap_patch_member_count",
        "gap_patch_centroid_latitude",
        "gap_patch_centroid_longitude",
    }
    missing = required.difference(patch_members.columns)
    if missing:
        raise ValueError(f"patch_members is missing columns: {', '.join(sorted(missing))}")
    columns = sorted(required, key=lambda value: (value != "gap_patch_id", value))
    return (
        patch_members[columns]
        .drop_duplicates(subset=["gap_patch_id"])
        .sort_values(["gap_patch_rank", "gap_patch_id"])
        .reset_index(drop=True)
    )


def patch_recovery_table(
    patch_members: pd.DataFrame,
    held_out_occurrences: pd.DataFrame,
    *,
    radii_km: Iterable[float] = (1.0, 2.0, 5.0, 10.0),
) -> pd.DataFrame:
    """Measure held-out occurrence recovery against patch members, not centroids."""

    held_out = _validate_locations(held_out_occurrences, "held_out_occurrences")
    if patch_members is None or patch_members.empty or held_out.empty:
        return pd.DataFrame()
    patches = _validate_locations(patch_members, "patch_members")
    patch_lats = patches["latitude"].to_numpy(float)
    patch_lons = patches["longitude"].to_numpy(float)
    radii = tuple(sorted({float(radius) for radius in radii_km if float(radius) >= 0.0}))
    rows: list[dict[str, object]] = []
    for held_index, occurrence in held_out.iterrows():
        distances = haversine_distance_m(occurrence.latitude, occurrence.longitude, patch_lats, patch_lons)
        nearest_position = int(np.argmin(distances))
        nearest_m = float(distances[nearest_position])
        nearest_patch = patches.iloc[nearest_position]
        row: dict[str, object] = {
            "held_out_index": int(held_index),
            "nearest_patch_id": nearest_patch.get("gap_patch_id", ""),
            "nearest_patch_class": nearest_patch.get("gap_patch_class", ""),
            "nearest_patch_distance_m": nearest_m,
        }
        for radius in radii:
            row[f"recovered_within_{radius:g}km"] = nearest_m <= radius * 1_000.0
        rows.append(row)
    return pd.DataFrame(rows)
