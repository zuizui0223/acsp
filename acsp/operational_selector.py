"""Downstream movement-constrained selection for validated candidate patches.

This module consumes an already generated candidate-patch table. It never
changes validated patch membership or the validated scientific claim.

The only user tuning quantity is a maximum geometric transition distance. Site
count, target coverage, survey days, and monetary budget are not inputs.
Straight-line connectivity is an operational geometry constraint, not a road,
trail, ferry, access, safety, travel-time, or field-efficiency claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from .coverage import EARTH_RADIUS_KM, _coverage_adjacency

_AUTO_STOP_EPS = 1e-12


@dataclass(frozen=True)
class OperationalSelectionAudit:
    candidate_count: int
    selected_count: int
    movement_component_count: int
    max_transition_km: float
    coverage_scale_km: float
    coverage_scale_source: str
    final_coverage_fraction: float
    movement_group_column: Optional[str]
    auto_stop_method: str = "maximum_normalized_knee_deviation"
    user_site_count_required: bool = False
    user_coverage_target_required: bool = False
    route_feasibility_claim: bool = False
    field_efficiency_claim: bool = False
    validated_candidate_membership_changed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "movement_component_count": self.movement_component_count,
            "max_transition_km": self.max_transition_km,
            "coverage_scale_km": self.coverage_scale_km,
            "coverage_scale_source": self.coverage_scale_source,
            "final_coverage_fraction": self.final_coverage_fraction,
            "movement_group_column": self.movement_group_column,
            "auto_stop_method": self.auto_stop_method,
            "user_site_count_required": self.user_site_count_required,
            "user_coverage_target_required": self.user_coverage_target_required,
            "route_feasibility_claim": self.route_feasibility_claim,
            "field_efficiency_claim": self.field_efficiency_claim,
            "validated_candidate_membership_changed": self.validated_candidate_membership_changed,
        }


def _derive_coverage_scale_km(
    candidates: pd.DataFrame,
    *,
    radius_col: str,
    merge_distance_col: str = "patch_merge_distance_m",
) -> tuple[float, str]:
    """Derive redundancy scale entirely from candidate-patch artifact metadata.

    Validated ACSP candidate patches carry the frozen aggregation scale in
    ``patch_merge_distance_m``. That artifact field is authoritative for the
    downstream redundancy scale; no separate operational 1 km constant exists.

    Legacy/pre-validated tables without merge metadata fall back to the median
    positive finite candidate-patch radius. This fallback is deliberately
    conservative and explicitly audited. A non-empty table with no usable
    artifact-derived scale fails instead of inventing a numeric default.
    """
    if candidates.empty:
        return 0.0, "empty_candidate_set_not_applicable"

    if merge_distance_col in candidates.columns:
        merge_m = pd.to_numeric(candidates[merge_distance_col], errors="coerce").to_numpy(float)
        if merge_m.size != len(candidates) or not np.isfinite(merge_m).all() or (merge_m <= 0.0).any():
            raise ValueError(
                f"{merge_distance_col} must contain one finite positive value for every candidate patch"
            )
        first = float(merge_m[0])
        tolerance = max(1e-9, abs(first) * 1e-9)
        if not np.all(np.abs(merge_m - first) <= tolerance):
            unique = sorted({float(value) for value in merge_m.tolist()})
            raise ValueError(
                f"{merge_distance_col} must be internally consistent; found {unique}"
            )
        return first / 1000.0, "candidate_patch_artifact.patch_merge_distance_m"

    if radius_col in candidates.columns:
        radii_m = pd.to_numeric(candidates[radius_col], errors="coerce").to_numpy(float)
        radii_m = radii_m[np.isfinite(radii_m) & (radii_m > 0.0)]
        if radii_m.size:
            return (
                float(np.median(radii_m) / 1000.0),
                "legacy_candidate_patch_artifact.median_positive_radius",
            )

    raise ValueError(
        "cannot derive operational coverage scale: non-empty candidate patches need "
        "finite positive patch_merge_distance_m metadata or positive candidate_patch_radius_m"
    )


def _movement_adjacency(
    candidates: pd.DataFrame,
    *,
    max_transition_km: float,
    latitude_col: str,
    longitude_col: str,
    group_col: str | None,
) -> list[np.ndarray]:
    """Return same-group geometric movement neighbours for each row."""
    if float(max_transition_km) <= 0.0:
        raise ValueError("max_transition_km must be positive")
    if latitude_col not in candidates.columns or longitude_col not in candidates.columns:
        raise ValueError("candidate table lacks latitude/longitude columns")
    if group_col is not None and group_col not in candidates.columns:
        raise ValueError(f"candidate table lacks movement group column {group_col!r}")

    n = len(candidates)
    neighbours: list[np.ndarray] = [np.empty(0, dtype=np.int64) for _ in range(n)]
    if group_col is None:
        groups = [np.arange(n, dtype=np.int64)]
    else:
        groups = [
            np.asarray(index, dtype=np.int64)
            for index in candidates.groupby(group_col, sort=False).indices.values()
        ]

    angular_radius = float(max_transition_km) / EARTH_RADIUS_KM
    for idx in groups:
        if len(idx) == 0:
            continue
        coords = np.radians(candidates.iloc[idx][[latitude_col, longitude_col]].to_numpy(float))
        if not np.isfinite(coords).all():
            raise ValueError("candidate coordinates must be finite")
        tree = BallTree(coords, metric="haversine")
        local = tree.query_radius(coords, r=angular_radius, return_distance=False)
        for row, local_neighbours in zip(idx, local):
            mapped = idx[np.asarray(local_neighbours, dtype=np.int64)]
            neighbours[int(row)] = mapped[mapped != int(row)]
    return neighbours


def _connected_components(neighbours: list[np.ndarray]) -> list[np.ndarray]:
    """Return deterministic connected components in original row order."""
    seen = np.zeros(len(neighbours), dtype=bool)
    components: list[np.ndarray] = []
    for start in range(len(neighbours)):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        rows: list[int] = []
        while stack:
            current = stack.pop()
            rows.append(current)
            for nxt in reversed(neighbours[current].tolist()):
                nxt = int(nxt)
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
        components.append(np.asarray(sorted(rows), dtype=np.int64))
    return components


def _knee_prefix_length(cumulative_fraction: list[float]) -> int:
    """Choose the coverage knee, retaining all rows if the curve is linear."""
    n = len(cumulative_fraction)
    if n <= 1:
        return n
    y = np.asarray(cumulative_fraction, dtype=float)
    x = np.arange(1, n + 1, dtype=float) / float(n)
    deviation = y - x
    maximum = float(np.nanmax(deviation))
    if not np.isfinite(maximum) or maximum <= _AUTO_STOP_EPS:
        return n
    return int(np.flatnonzero(np.isclose(deviation, maximum, rtol=0.0, atol=_AUTO_STOP_EPS))[0] + 1)


def _component_coverage_columns(coverage, row: int, component_mask: np.ndarray) -> np.ndarray:
    start, stop = coverage.indptr[row], coverage.indptr[row + 1]
    cols = coverage.indices[start:stop]
    return cols[component_mask[cols]]


def _connected_greedy_prefix(
    coverage,
    component: np.ndarray,
    movement_neighbours: list[np.ndarray],
) -> tuple[list[int], list[int], list[float], list[int | None]]:
    """Build a coverage-greedy prefix whose selected subgraph stays connected."""
    component_set = set(int(x) for x in component)
    component_mask = np.zeros(coverage.shape[1], dtype=bool)
    component_mask[component] = True
    covered = np.zeros(coverage.shape[1], dtype=bool)
    selected: list[int] = []
    marginal: list[int] = []
    cumulative: list[float] = []
    parents: list[int | None] = []
    remaining = set(component_set)

    while remaining:
        if not selected:
            eligible = sorted(remaining)
        else:
            frontier: set[int] = set()
            for chosen in selected:
                frontier.update(int(x) for x in movement_neighbours[chosen] if int(x) in remaining)
            eligible = sorted(frontier)
            if not eligible:
                break

        best = eligible[0]
        best_gain = -1
        for row in eligible:
            cols = _component_coverage_columns(coverage, row, component_mask)
            gain = int((~covered[cols]).sum())
            if gain > best_gain:
                best, best_gain = row, gain

        parent: int | None = None
        if selected:
            possible = [chosen for chosen in selected if best in movement_neighbours[chosen]]
            if possible:
                parent = int(possible[0])

        cols = _component_coverage_columns(coverage, best, component_mask)
        newly = cols[~covered[cols]]
        covered[newly] = True
        selected.append(int(best))
        remaining.remove(int(best))
        marginal.append(int(len(newly)))
        cumulative.append(float(covered[component].mean()))
        parents.append(parent)
        if bool(covered[component].all()):
            break

    return selected, marginal, cumulative, parents


def select_movement_constrained_patches(
    candidates: pd.DataFrame,
    *,
    max_transition_km: float,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    group_col: str | None = "survey_area_id",
    radius_col: str = "candidate_patch_radius_m",
) -> tuple[pd.DataFrame, OperationalSelectionAudit]:
    """Select an automatically sized connected operational subset of patches.

    ``max_transition_km`` is the only user tuning quantity. Each movement-
    connected component is a separate operational segment. A deterministic
    connected greedy coverage prefix is generated and stopped at its internal
    coverage knee. A linear curve has no defensible knee, so all rows are kept.
    Redundancy scale is derived from candidate-patch artifact metadata and is not
    an independent operational threshold.
    """
    if float(max_transition_km) <= 0.0:
        raise ValueError("max_transition_km must be positive")

    work = candidates.reset_index(drop=False).rename(columns={"index": "_input_index"}).copy()
    n = len(work)
    coverage_scale_km, coverage_scale_source = _derive_coverage_scale_km(
        work,
        radius_col=radius_col,
    )
    if n == 0:
        empty = work.copy()
        for column, dtype in (
            ("operational_segment", "int64"),
            ("operational_selection_step", "int64"),
            ("marginal_covered_patches", "int64"),
            ("segment_coverage_fraction", "float64"),
            ("movement_parent_input_index", "Int64"),
        ):
            empty[column] = pd.Series(dtype=dtype)
        empty["operational_coverage_scale_source"] = pd.Series(dtype="string")
        return empty, OperationalSelectionAudit(
            0,
            0,
            0,
            float(max_transition_km),
            coverage_scale_km,
            coverage_scale_source,
            0.0,
            group_col,
        )

    coverage = _coverage_adjacency(
        work,
        radius_km=coverage_scale_km,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
        group_col=group_col,
    )
    movement = _movement_adjacency(
        work,
        max_transition_km=float(max_transition_km),
        latitude_col=latitude_col,
        longitude_col=longitude_col,
        group_col=group_col,
    )
    components = _connected_components(movement)

    rows: list[pd.DataFrame] = []
    globally_covered = np.zeros(n, dtype=bool)
    for segment_id, component in enumerate(components, start=1):
        component_mask = np.zeros(n, dtype=bool)
        component_mask[component] = True
        prefix, marginal, cumulative, parents = _connected_greedy_prefix(
            coverage, component, movement
        )
        keep = _knee_prefix_length(cumulative)
        chosen = prefix[:keep]
        if not chosen:
            continue
        segment = work.iloc[chosen].copy().reset_index(drop=True)
        segment["operational_segment"] = int(segment_id)
        segment["operational_selection_step"] = np.arange(1, len(segment) + 1, dtype=int)
        segment["marginal_covered_patches"] = marginal[:keep]
        segment["segment_coverage_fraction"] = cumulative[:keep]
        segment["movement_parent_input_index"] = pd.array(
            [pd.NA if p is None else int(work.iloc[p]["_input_index"]) for p in parents[:keep]],
            dtype="Int64",
        )
        rows.append(segment)
        for row in chosen:
            globally_covered[_component_coverage_columns(coverage, row, component_mask)] = True

    out = pd.concat(rows, ignore_index=True) if rows else work.iloc[0:0].copy()
    out["operational_selector_status"] = "downstream_geometry_not_validated_efficiency"
    out["max_transition_km"] = float(max_transition_km)
    out["operational_coverage_scale_km"] = float(coverage_scale_km)
    out["operational_coverage_scale_source"] = str(coverage_scale_source)
    audit = OperationalSelectionAudit(
        candidate_count=n,
        selected_count=int(len(out)),
        movement_component_count=int(len(components)),
        max_transition_km=float(max_transition_km),
        coverage_scale_km=float(coverage_scale_km),
        coverage_scale_source=str(coverage_scale_source),
        final_coverage_fraction=float(globally_covered.mean()),
        movement_group_column=group_col,
    )
    return out, audit
