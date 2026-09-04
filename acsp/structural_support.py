"""Frozen structural-support composition for prospective Cirsium local discovery.

Raw ecological layers are transformed upstream into interpretable unit-interval
components. This module freezes how those components are combined. It uses a
conjunctive minimum rather than fitted or outcome-tuned weights, so one favorable
component cannot compensate for failure of another required structural component.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from acsp.structural_selector import _forbidden_outcome_columns

FAMILY_COMPONENTS: dict[str, tuple[str, ...]] = {
    "WETLAND_MOISTURE_STRUCTURE": (
        "wetland_water_adjacent_score",
        "topographic_moisture_score",
        "terrain_continuity_score",
    ),
    "ALPINE_TOPOGRAPHIC_STRUCTURE": (
        "relative_relief_score",
        "landform_continuity_score",
        "ridge_valley_continuity_score",
    ),
    "OPEN_GRASSLAND_STRUCTURE": (
        "open_land_score",
        "fragment_continuity_score",
        "terrain_context_score",
    ),
    "COASTAL_ISLAND_STRUCTURE": (
        "shore_position_score",
        "shore_landform_continuity_score",
        "island_component_score",
    ),
    "FOREST_EDGE_STRUCTURE": (
        "forest_edge_score",
        "canopy_opening_transition_score",
        "terrain_component_score",
    ),
}
BASELINE_FAMILY = "GENERAL_SPATIAL_BASELINE_ONLY"


@dataclass(frozen=True)
class StructuralSupportAudit:
    feature_family: str
    component_columns: tuple[str, ...]
    composition_rule: str
    row_count: int
    field_outcomes_used: bool = False
    fitted_feature_weights: bool = False
    post_outcome_component_switch_allowed: bool = False


def compose_structural_support(
    frame: pd.DataFrame,
    *,
    feature_family: str,
) -> tuple[pd.Series, StructuralSupportAudit]:
    """Return frozen conjunctive support for one declared structural family."""
    family = str(feature_family).strip()
    if family == BASELINE_FAMILY:
        raise ValueError("GENERAL_SPATIAL_BASELINE_ONLY has no structural support composition")
    if family not in FAMILY_COMPONENTS:
        raise ValueError(f"unknown structural feature family: {family}")

    forbidden = _forbidden_outcome_columns(frame.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in structural support: {forbidden}")

    components = FAMILY_COMPONENTS[family]
    missing = [column for column in components if column not in frame.columns]
    if missing:
        raise ValueError(f"missing frozen structural components for {family}: {missing}")

    matrix = frame.loc[:, list(components)].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    if not np.isfinite(matrix).all():
        raise ValueError("structural components must be complete and finite")
    if ((matrix < 0.0) | (matrix > 1.0)).any():
        raise ValueError("structural components must lie in [0, 1]")

    support = pd.Series(np.min(matrix, axis=1), index=frame.index, name="structural_support")
    audit = StructuralSupportAudit(
        feature_family=family,
        component_columns=components,
        composition_rule="ROW_MIN_CONJUNCTIVE_SUPPORT",
        row_count=int(len(frame)),
    )
    return support, audit
