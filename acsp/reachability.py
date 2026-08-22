"""Explicit hard-reachability selection for validated ACSP candidate patches.

This module is strictly downstream of validated candidate-patch generation.
Movement is defined only by an externally supplied edge list. No straight-line
proximity, SDM, ranking score, access weight, survey-day count, or monetary
budget is used to infer an allowed transition.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .coverage import _coverage_adjacency
from .operational_selector import (
    _component_coverage_columns,
    _connected_components,
    _connected_greedy_prefix,
    _derive_coverage_scale_km,
    _knee_prefix_length,
)


@dataclass(frozen=True)
class ReachabilitySelectionAudit:
    candidate_count: int
    selected_count: int
    movement_component_count: int
    reachability_edge_count: int
    coverage_scale_km: float
    coverage_scale_source: str
    final_coverage_fraction: float
    coverage_group_column: Optional[str]
    patch_id_column: str
    movement_constraint_mode: str = "explicit_reachability_graph"
    straight_line_movement_assumption: bool = False
    user_site_count_required: bool = False
    user_coverage_target_required: bool = False
    route_feasibility_claim: bool = False
    field_efficiency_claim: bool = False
    reachability_provider_validated: bool = False
    validated_candidate_membership_changed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "movement_component_count": self.movement_component_count,
            "reachability_edge_count": self.reachability_edge_count,
            "coverage_scale_km": self.coverage_scale_km,
            "coverage_scale_source": self.coverage_scale_source,
            "final_coverage_fraction": self.final_coverage_fraction,
            "coverage_group_column": self.coverage_group_column,
            "patch_id_column": self.patch_id_column,
            "movement_constraint_mode": self.movement_constraint_mode,
            "straight_line_movement_assumption": self.straight_line_movement_assumption,
            "user_site_count_required": self.user_site_count_required,
            "user_coverage_target_required": self.user_coverage_target_required,
            "route_feasibility_claim": self.route_feasibility_claim,
            "field_efficiency_claim": self.field_efficiency_claim,
            "reachability_provider_validated": self.reachability_provider_validated,
            "validated_candidate_membership_changed": self.validated_candidate_membership_changed,
        }


def _explicit_reachability_adjacency(
    candidates: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    id_col: str,
    from_col: str,
    to_col: str,
) -> tuple[list[np.ndarray], int]:
    """Build deterministic undirected adjacency from explicitly allowed edges."""
    if id_col not in candidates.columns:
        raise ValueError(f"candidate table lacks patch ID column {id_col!r}")
    if from_col not in edges.columns or to_col not in edges.columns:
        raise ValueError(
            f"reachability edge table must contain {from_col!r} and {to_col!r}"
        )
    if candidates[id_col].isna().any():
        raise ValueError("candidate patch IDs must not be missing")
    candidate_ids = candidates[id_col].astype(str)
    if candidate_ids.duplicated().any():
        duplicate_ids = sorted(candidate_ids[candidate_ids.duplicated(keep=False)].unique())
        raise ValueError(f"candidate patch IDs must be unique; duplicates: {duplicate_ids}")
    if edges[from_col].isna().any() or edges[to_col].isna().any():
        raise ValueError("reachability edge patch IDs must not be missing")

    id_to_row = {patch_id: i for i, patch_id in enumerate(candidate_ids.tolist())}
    from_ids = edges[from_col].astype(str)
    to_ids = edges[to_col].astype(str)
    referenced = set(from_ids) | set(to_ids)
    unknown = sorted(referenced.difference(id_to_row))
    if unknown:
        raise ValueError(f"reachability graph references unknown patch IDs: {unknown}")

    neighbour_sets: list[set[int]] = [set() for _ in range(len(candidates))]
    unique_edges: set[tuple[int, int]] = set()
    for from_id, to_id in zip(from_ids, to_ids):
        left = int(id_to_row[from_id])
        right = int(id_to_row[to_id])
        if left == right:
            continue
        a, b = sorted((left, right))
        unique_edges.add((a, b))
        neighbour_sets[left].add(right)
        neighbour_sets[right].add(left)

    neighbours = [
        np.asarray(sorted(values), dtype=np.int64) for values in neighbour_sets
    ]
    return neighbours, int(len(unique_edges))


def select_reachability_constrained_patches(
    candidates: pd.DataFrame,
    reachability_edges: pd.DataFrame,
    *,
    id_col: str = "candidate_patch_id",
    from_col: str = "from_patch_id",
    to_col: str = "to_patch_id",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    coverage_group_col: str | None = "survey_area_id",
    radius_col: str = "candidate_patch_radius_m",
) -> tuple[pd.DataFrame, ReachabilitySelectionAudit]:
    """Select an automatically sized subset under an explicit movement graph.

    Only edges present in ``reachability_edges`` are traversable. The movement
    graph may cross ``survey_area_id`` when a cross-area edge is explicitly
    supplied, while ecological coverage remains same-area by default.

    The returned ``operational_selection_step`` is the deterministic connected
    set-construction order, not an optimized travel route. The parent column
    records one already-selected adjacent patch that made each addition legal.
    Redundancy scale is read from candidate-patch artifact metadata rather than
    maintained as a separate operational threshold.
    """
    work = candidates.reset_index(drop=False).rename(columns={"index": "_input_index"}).copy()
    movement, edge_count = _explicit_reachability_adjacency(
        work,
        reachability_edges,
        id_col=id_col,
        from_col=from_col,
        to_col=to_col,
    )
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
            ("movement_parent_patch_id", "string"),
        ):
            empty[column] = pd.Series(dtype=dtype)
        empty["movement_constraint_mode"] = pd.Series(dtype="string")
        empty["straight_line_movement_assumption"] = pd.Series(dtype="bool")
        empty["operational_coverage_scale_km"] = pd.Series(dtype="float64")
        empty["operational_coverage_scale_source"] = pd.Series(dtype="string")
        return empty, ReachabilitySelectionAudit(
            candidate_count=0,
            selected_count=0,
            movement_component_count=0,
            reachability_edge_count=edge_count,
            coverage_scale_km=coverage_scale_km,
            coverage_scale_source=coverage_scale_source,
            final_coverage_fraction=0.0,
            coverage_group_column=coverage_group_col,
            patch_id_column=id_col,
        )

    coverage = _coverage_adjacency(
        work,
        radius_km=coverage_scale_km,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
        group_col=coverage_group_col,
    )
    components = _connected_components(movement)

    rows: list[pd.DataFrame] = []
    globally_covered = np.zeros(n, dtype=bool)
    for segment_id, component in enumerate(components, start=1):
        component_mask = np.zeros(n, dtype=bool)
        component_mask[component] = True
        prefix, marginal, cumulative, parents = _connected_greedy_prefix(
            coverage,
            component,
            movement,
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
        segment["movement_parent_patch_id"] = pd.array(
            [pd.NA if p is None else str(work.iloc[p][id_col]) for p in parents[:keep]],
            dtype="string",
        )
        rows.append(segment)

        for row in chosen:
            globally_covered[_component_coverage_columns(coverage, row, component_mask)] = True

    out = pd.concat(rows, ignore_index=True) if rows else work.iloc[0:0].copy()
    out["movement_constraint_mode"] = "explicit_reachability_graph"
    out["straight_line_movement_assumption"] = False
    out["operational_selector_status"] = "downstream_reachability_not_validated_efficiency"
    out["operational_coverage_scale_km"] = float(coverage_scale_km)
    out["operational_coverage_scale_source"] = str(coverage_scale_source)

    audit = ReachabilitySelectionAudit(
        candidate_count=n,
        selected_count=int(len(out)),
        movement_component_count=int(len(components)),
        reachability_edge_count=edge_count,
        coverage_scale_km=float(coverage_scale_km),
        coverage_scale_source=str(coverage_scale_source),
        final_coverage_fraction=float(globally_covered.mean()),
        coverage_group_column=coverage_group_col,
        patch_id_column=id_col,
    )
    return out, audit
