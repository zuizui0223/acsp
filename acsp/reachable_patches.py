"""Discover stable, route-constrained survey patches from irregular candidates.

The algorithm does not interpret raster cells as exact field sites. It builds a
candidate graph, repeats patch extraction across support thresholds and connection
radii, retains persistent co-membership, prevents single-link chains with a
complete-link diameter cap, and chooses a small internal survey route.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .field_validation import haversine_distance_m


DEFAULT_ENVIRONMENT_COLUMNS = (
    "analogue_score",
    "elevation",
    "slope",
    "roughness",
    "tpi",
    "distance_to_coast_m",
)


@dataclass(frozen=True)
class PatchSettings:
    connection_radius_km: float = 2.0
    environmental_epsilon: float = 3.0
    support_quantile: float = 0.5
    persistence_threshold: float = 0.30
    maximum_patch_diameter_km: float = 3.0
    maximum_stations: int = 3


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(missing)}")


def _distance_km(a: pd.Series, b: pd.Series) -> float:
    return float(
        haversine_distance_m(
            float(a["latitude"]),
            float(a["longitude"]),
            np.asarray([float(b["latitude"])]),
            np.asarray([float(b["longitude"])]),
        )[0]
        / 1000.0
    )


def add_area_relative_environment(
    candidates: pd.DataFrame,
    *,
    area_col: str = "survey_area_id",
    environment_columns: Sequence[str] = DEFAULT_ENVIRONMENT_COLUMNS,
) -> pd.DataFrame:
    """Add robust within-area environmental coordinates and support ranks."""
    _require_columns(candidates, [area_col, "latitude", "longitude", "site_id"], "candidates")
    out = candidates.copy().reset_index(drop=True)
    available = [column for column in environment_columns if column in out.columns]
    if "analogue_score" not in out.columns:
        raise ValueError("candidates require analogue_score")
    out["patch_support_rank"] = pd.to_numeric(out["analogue_score"], errors="coerce").groupby(
        out[area_col]
    ).rank(method="average", pct=True).fillna(0.5)
    for column in available:
        values = pd.to_numeric(out[column], errors="coerce")
        median = values.groupby(out[area_col]).transform("median")
        deviation = (values - median).abs()
        mad = deviation.groupby(out[area_col]).transform("median") * 1.4826
        out[f"patch_z_{column}"] = ((values - median) / mad.replace(0.0, np.nan)).fillna(0.0).clip(-5.0, 5.0)
    out.attrs["patch_environment_columns"] = available
    return out


def _components(active: np.ndarray, adjacent: list[list[int]]) -> list[list[int]]:
    seen: set[int] = set()
    result: list[list[int]] = []
    for start in range(len(active)):
        if not active[start] or start in seen:
            continue
        stack = [start]
        seen.add(start)
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in adjacent[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        result.append(component)
    return result


def _route_length_and_order(frame: pd.DataFrame, indices: Sequence[int]) -> tuple[float, list[int]]:
    if len(indices) <= 1:
        return 0.0, list(indices)
    matrix = np.zeros((len(indices), len(indices)), dtype=float)
    for first, second in combinations(range(len(indices)), 2):
        distance = _distance_km(frame.iloc[indices[first]], frame.iloc[indices[second]])
        matrix[first, second] = matrix[second, first] = distance
    start = int(np.argmin(matrix.sum(axis=1)))
    order = [start]
    remaining = set(range(len(indices))) - {start}
    while remaining:
        next_index = min(remaining, key=lambda candidate: matrix[order[-1], candidate])
        order.append(next_index)
        remaining.remove(next_index)
    length = sum(matrix[order[position], order[position + 1]] for position in range(len(order) - 1))
    return float(length), [int(indices[position]) for position in order]


def discover_persistent_patches(
    candidates: pd.DataFrame,
    *,
    settings: PatchSettings | None = None,
    area_col: str = "survey_area_id",
    environment_columns: Sequence[str] = DEFAULT_ENVIRONMENT_COLUMNS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return route stations and patch summaries for every survey area."""
    settings = settings or PatchSettings()
    prepared = add_area_relative_environment(
        candidates, area_col=area_col, environment_columns=environment_columns
    )
    environment = [f"patch_z_{column}" for column in prepared.attrs["patch_environment_columns"]]
    station_rows: list[dict[str, object]] = []
    patch_rows: list[dict[str, object]] = []

    for area, original_group in prepared.groupby(area_col, sort=True):
        group = original_group.reset_index(drop=True)
        count = len(group)
        co_membership = np.zeros((count, count), dtype=float)
        active_count = np.zeros(count, dtype=float)
        setting_count = 0
        thresholds = (
            max(0.20, settings.support_quantile - 0.10),
            settings.support_quantile,
            min(0.85, settings.support_quantile + 0.10),
        )
        radii = (
            settings.connection_radius_km * 0.75,
            settings.connection_radius_km,
            settings.connection_radius_km * 1.25,
        )
        for threshold in thresholds:
            active = group["patch_support_rank"].to_numpy(float) >= float(threshold)
            for radius in radii:
                setting_count += 1
                active_count += active.astype(float)
                adjacent: list[list[int]] = [[] for _ in range(count)]
                for first, second in combinations(range(count), 2):
                    if not active[first] or not active[second]:
                        continue
                    geographic = _distance_km(group.iloc[first], group.iloc[second])
                    environmental = float(
                        np.linalg.norm(
                            group.loc[first, environment].to_numpy(float)
                            - group.loc[second, environment].to_numpy(float)
                        )
                    )
                    if geographic <= radius and environmental <= settings.environmental_epsilon:
                        adjacent[first].append(second)
                        adjacent[second].append(first)
                for component in _components(active, adjacent):
                    for first in component:
                        for second in component:
                            co_membership[first, second] += 1.0

        node_persistence = active_count / max(1, setting_count)
        valid = [
            index
            for index, persistence in enumerate(node_persistence)
            if persistence >= settings.persistence_threshold
        ]
        ordered = sorted(
            valid,
            key=lambda index: (
                -float(group.loc[index, "patch_support_rank"]),
                str(group.loc[index, "site_id"]),
            ),
        )
        clusters: list[list[int]] = []
        for index in ordered:
            assigned = False
            for cluster in clusters:
                compatible = all(
                    _distance_km(group.iloc[index], group.iloc[member])
                    <= settings.maximum_patch_diameter_km
                    and co_membership[index, member] / max(1, setting_count)
                    >= settings.persistence_threshold
                    for member in cluster
                )
                if compatible:
                    cluster.append(index)
                    assigned = True
                    break
            if not assigned:
                clusters.append([index])

        summaries: list[tuple[float, list[int], float, float]] = []
        for cluster in clusters:
            selected: list[int] = []
            while len(selected) < min(settings.maximum_stations, len(cluster)):
                best: tuple[float, str, int] | None = None
                for index in cluster:
                    if index in selected:
                        continue
                    value = float(group.loc[index, "patch_support_rank"] * node_persistence[index])
                    if selected:
                        separation = min(
                            _distance_km(group.iloc[index], group.iloc[member])
                            for member in selected
                        )
                        value *= 0.5 + 0.5 * min(
                            1.0, separation / max(settings.maximum_patch_diameter_km, 1e-9)
                        )
                    candidate = (value, str(group.loc[index, "site_id"]), index)
                    if best is None or candidate > best:
                        best = candidate
                if best is None:
                    break
                selected.append(best[2])
            route_km, route_order = _route_length_and_order(group, selected)
            mean_support = float(group.loc[selected, "patch_support_rank"].mean())
            persistence = float(np.mean(node_persistence[selected]))
            score = (
                mean_support
                * persistence
                * np.log1p(len(selected))
                / (1.0 + route_km / max(settings.maximum_patch_diameter_km, 1e-9))
            )
            summaries.append((float(score), route_order, route_km, persistence))

        if not summaries:
            fallback = int(group["patch_support_rank"].idxmax())
            summaries = [(float(group.loc[fallback, "patch_support_rank"]), [fallback], 0.0, 1.0)]
        score, selected_order, route_km, persistence = max(summaries, key=lambda item: item[0])
        patch_id = f"{area}-persistent-1"
        diameter = max(
            [0.0]
            + [
                _distance_km(group.iloc[first], group.iloc[second])
                for first, second in combinations(selected_order, 2)
            ]
        )
        for route_rank, index in enumerate(selected_order, start=1):
            row = group.iloc[index].to_dict()
            row.update(
                {
                    "patch_id": patch_id,
                    "patch_route_rank": route_rank,
                    "patch_score": score,
                    "patch_persistence": persistence,
                    "patch_internal_route_km": route_km,
                    "patch_diameter_km": diameter,
                }
            )
            station_rows.append(row)
        patch_rows.append(
            {
                area_col: area,
                "patch_id": patch_id,
                "patch_score": score,
                "patch_persistence": persistence,
                "patch_station_count": len(selected_order),
                "patch_internal_route_km": route_km,
                "patch_diameter_km": diameter,
                "representative_site_id": group.iloc[selected_order[0]]["site_id"],
                "latitude": float(group.iloc[selected_order]["latitude"].mean()),
                "longitude": float(group.iloc[selected_order]["longitude"].mean()),
            }
        )

    return pd.DataFrame(station_rows), pd.DataFrame(patch_rows)
