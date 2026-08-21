"""Downstream movement-constrained selection for validated candidate patches.

This module is deliberately outside the validated ACSP candidate-generation
core. It consumes an already generated candidate-patch table and chooses a
connected operational subset without changing patch membership, scientific
support, or validation claims.

The only user-facing tuning quantity is a maximum geometric transition distance.
Site count, coverage target, survey days, and monetary budget are outputs or are
absent. Straight-line connectivity is a geometric operational constraint, not a
road, trail, ferry, access, safety, or field-efficiency claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from .coverage import EARTH_RADIUS_KM, _coverage_adjacency

DEFAULT_OPERATIONAL_COVERAGE_FLOOR_KM = 1.0
_AUTO_STOP_EPS = 1e-12


@dataclass(frozen=True)
class OperationalSelectionAudit:
    candidate_count: int
    selected_count: int
    movement_component_count: int
    max_transition_km: float
    coverage_scale_km: float
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
) -> float:
    """Derive an internal geometric redundancy scale from patch footprints."""
    if radius_col not in candidates.columns:
        return float(DEFAULT_OPERATIONAL_COVERAGE_FLOOR_KM)
    radii_m = pd.to_numeric(candidates[radius_col], errors="coerce").to_numpy(float)
    radii_m = radii_m[np.isfinite(radii_m) & (radii_m >= 0.0)]
    if radii_m.size == 0:
        return float(DEFAULT_OPERATIONAL_COVERAGE_FLOOR_KM)
    median_radius_km = float(np.median(radii_m)) / 1000.0
    return float(max(DEFAULT_OPERATIONAL_COVERAGE_FLOOR_KM, median_radius_km))


def _movement_adjacency(
    candidates: pd.DataFrame,
    *,
    max_transition_km: float,
    latitude_col: str,
    longitude_col: str,
    group_col: str | None,
) -> list[np.ndarray]:
    """Return same-group geometric movement neighbours for each candidate."""
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
    """Return deterministic connected components in input-row order."""
    n = len(neighbours)
    seen = np.zeros(n, dtype=bool)
    components: list[np.ndarray] = []
    for start in range(n):
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
    """Choose a conservative automatic prefix from a cumulative coverage curve.

    The knee is the largest positive deviation above the straight line from
    (0, 0) to (n, 1). If there is no positive curvature, every visit contributes
    proportionally and the conservative choice is to retain the full prefix.
    """
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


def _connected_greedy_prefix(
    coverage,
    component: np.ndarray,
    movement_neighbours: list[np.ndarray],
) -> tuple[list[int], list[int], list[float], list[int | None]]:
    """Build a deterministic coverage-greedy prefix whose selected set stays connected."""
    component_set = set(int(x) for x in component)
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

        best = None
        best_gain = -1
        for row in eligible:
            start, stop = coverage.indptr[row], coverage.indptr[row + 1]
            cols = coverage.indices[start:stop]
            gain = int((~covered[cols]).sum())
            if gain > best_gain:
                best = row
                best_gain = gain
        assert best is not None

        parent: int | None = None
        if selected:
            possible_parents = [
                chosen for chosen in selected if best in set(int(x) for x in movement_neighbours[chosen])
            ]
            if possible_parents:
                parent = int(possible_parents[0])

        start, stop = coverage.indptr[best], coverage.indptr[best + 1]
        cols = coverage.indices[start:stop]
        newly = cols[~covered[cols]]
        covered[newly] = True
        selected.append(int(best))
        remaining.remove(int(best))
        marginal.append(int(len(newly)))
        cumulative.append(float(covered[list(component_set)].mean()))
        parents.append(parent)

        if bool(covered[list(component_set)].all()):
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

    ``max_transition_km`` is the only user tuning quantity. Candidate count and
    a target coverage fraction are not inputs. Each movement-connected component
    is treated as a separate operational segment; the selected prefix within a
    component is stopped automatically at the geometric coverage knee.

    Connectivity is straight-line geometry constrained by ``group_col``. It is
    not a road, trail, ferry, legal-access, safety, or travel-time model.
    """
    if float(max_transition_km) <= 0.0:
        raise ValueError("max_transition_km must be positive")

    work = candidates.reset_index(drop=False).rename(columns={"index": "_input_index"}).copy()
    n = len(work)
    coverage_scale_km = _derive_coverage_scale_km(work, radius_col=radius_col)
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
        audit = OperationalSelectionAudit(
            candidate_count=0,
            selected_count=0,
            movement_component_count=0,
            max_transition_km=float(max_transition_km),
            coverage_scale_km=coverage_scale_km,
            final_coverage_fraction=0.0,
            movement_group_column=group_col,
        )
        return empty, audit

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
        parent_input = [
            pd.NA if parent is None else int(work.iloc[parent]["_input_index"])
            for parent in parents[:keep]
        ]
        segment["movement_parent_input_index"] = pd.array(parent_input, dtype="Int64")
        rows.append(segment)

        for row in chosen:
            start, stop = coverage.indptr[row], coverage.indptr[row + 1]
            globally_covered[coverage.indices[start:stop]] = True

    if rows:
        out = pd.concat(rows, ignore_index=True)
    else:
        out = work.iloc[0:0].copy()
    out["operational_selector_status"] = "downstream_geometry_not_validated_efficiency"
    out["max_transition_km"] = float(max_transition_km)
    out["operational_coverage_scale_km"] = float(coverage_scale_km)

    audit = OperationalSelectionAudit(
        candidate_count=n,
        selected_count=int(len(out)),
        movement_component_count=int(len(components)),
        max_transition_km=float(max_transition_km),
        coverage_scale_km=float(coverage_scale_km),
        final_coverage_fraction=float(globally_covered.mean()),
        movement_group_column=group_col,
    )
    return out, audit
