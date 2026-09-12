"""Generic structural-support ordering for experimental N4 discovery."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

import pandas as pd

from acsp.structural_graph import build_structural_graph_primitives
from acsp.structural_raw_adapters import adapt_structural_components
from acsp.structural_selector import _forbidden_outcome_columns
from acsp.structural_support import BASELINE_FAMILY, compose_structural_support


@dataclass(frozen=True)
class StructuralOrderAudit:
    feature_family: str
    candidate_count: int
    support_provenance_id: str
    graph_radius_cells: int
    graph_audit: dict[str, Any]
    adapter_audit: dict[str, Any]
    support_audit: dict[str, Any]
    field_outcomes_used: bool = False
    human_access_used: bool = False
    fitted_feature_weights: bool = False


def _provenance_id(
    *,
    feature_family: str,
    graph_radius_cells: int,
    target_component_id: str | None,
    source_provenance: dict[str, Any],
) -> str:
    payload = {
        "api": "acsp.discovery.structural.v1",
        "feature_family": str(feature_family),
        "graph_radius_cells": int(graph_radius_cells),
        "target_component_id": str(target_component_id or ""),
        "source_provenance": source_provenance,
        "support_composition": "ROW_MIN_CONJUNCTIVE_SUPPORT",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_structural_support_order(
    raw_candidate_frame: pd.DataFrame,
    *,
    feature_family: str,
    source_provenance: dict[str, Any],
    target_component_id: str | None = None,
    graph_radius_cells: int = 1,
    candidate_id_col: str = "candidate_cell_id",
) -> tuple[pd.DataFrame, StructuralOrderAudit]:
    """Return a full deterministic structural-support order on one frozen frame.

    This function is species-neutral. Ecological meaning enters only through a
    separately frozen ``feature_family`` and source provenance. It never reads
    held-out detections, roads, permissions, route cost, or field effort.
    """
    if raw_candidate_frame is None or raw_candidate_frame.empty:
        raise ValueError("raw_candidate_frame must contain at least one row")
    required = {candidate_id_col, "latitude", "longitude", "grid_row", "grid_col"}
    missing = sorted(required.difference(raw_candidate_frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing required columns: {missing}")
    if raw_candidate_frame[candidate_id_col].isna().any() or raw_candidate_frame[candidate_id_col].astype(str).duplicated().any():
        raise ValueError("candidate IDs must be complete and unique")
    forbidden = _forbidden_outcome_columns(raw_candidate_frame.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in structural discovery: {forbidden}")
    if not isinstance(source_provenance, dict) or not source_provenance:
        raise ValueError("source_provenance must be a non-empty mapping")
    if str(feature_family) == BASELINE_FAMILY:
        raise ValueError("GENERAL_SPATIAL_BASELINE_ONLY has no structural support order")

    graph_frame, graph = build_structural_graph_primitives(
        raw_candidate_frame,
        feature_family=str(feature_family),
        target_component_id=target_component_id,
        radius=int(graph_radius_cells),
    )
    adapted, adapter = adapt_structural_components(graph_frame, feature_family=str(feature_family))
    support, composer = compose_structural_support(adapted, feature_family=str(feature_family))
    ordered = adapted.copy()
    ordered["structural_support"] = support
    ordered = ordered.sort_values(
        ["structural_support", candidate_id_col],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    ordered["decision_method"] = "STRUCTURAL_SUPPORT"
    ordered["decision_rank"] = range(1, len(ordered) + 1)

    provenance_id = _provenance_id(
        feature_family=str(feature_family),
        graph_radius_cells=int(graph_radius_cells),
        target_component_id=target_component_id,
        source_provenance=source_provenance,
    )
    audit = StructuralOrderAudit(
        feature_family=str(feature_family),
        candidate_count=int(len(ordered)),
        support_provenance_id=provenance_id,
        graph_radius_cells=int(graph_radius_cells),
        graph_audit=graph.__dict__.copy(),
        adapter_audit=adapter.__dict__.copy(),
        support_audit=composer.__dict__.copy(),
    )
    return ordered, audit
