"""Outcome-blind raw-layer adapters for prospective Cirsium structural support.

The adapters deliberately stop short of learning habitat preferences from field
outcomes. They transform public-layer primitives into interpretable unit-interval
components whose semantics were frozen before Cirsium field outcomes.

Continuity/component scores that require an explicit ecological graph are *not*
reconstructed from convenient rasters here. They must be supplied by a separately
pinned graph builder and are only validated/passed through by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from acsp.structural_selector import _forbidden_outcome_columns
from acsp.structural_support import BASELINE_FAMILY


WORLD_COVER_REQUIRED = (
    "wc_tree_frac_250m",
    "wc_grass_frac_250m",
    "wc_bare_frac_250m",
    "wc_water_frac_250m",
    "wc_wetland_frac_250m",
    "wc_edge_mix_250m",
)
TERRAIN_REQUIRED = (
    "elev",
    "slope100",
    "tpi300",
)


@dataclass(frozen=True)
class RawAdapterAudit:
    feature_family: str
    row_count: int
    formulas_fitted_to_field_outcome: bool = False
    field_outcomes_used: bool = False
    graph_components_inferred_from_convenience_rasters: bool = False
    frame_relative_ranks_used: tuple[str, ...] = ()
    pass_through_graph_components: tuple[str, ...] = ()


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise ValueError(f"missing required raw structural column: {column}")
    values = pd.to_numeric(frame[column], errors="coerce")
    if not np.isfinite(values.to_numpy(float)).all():
        raise ValueError(f"raw structural column must be complete and finite: {column}")
    return values.astype(float)


def _unit_interval(frame: pd.DataFrame, column: str) -> pd.Series:
    values = _numeric(frame, column)
    if ((values < 0.0) | (values > 1.0)).any():
        raise ValueError(f"unit-interval structural column outside [0,1]: {column}")
    return values


def _rank01(values: pd.Series, *, high_is_support: bool) -> pd.Series:
    """Deterministic within-frame percentile rank, with no tuned cut point."""
    ranked = values.rank(method="average", pct=True).astype(float)
    if not high_is_support:
        ranked = 1.0 - ranked + (1.0 / max(len(ranked), 1))
    return ranked.clip(0.0, 1.0)


def _coast_support(distance_m: pd.Series, scale_m: float = 1000.0) -> pd.Series:
    """Frozen monotone coast-proximity transform; no field-fitted distance threshold."""
    if scale_m <= 0:
        raise ValueError("scale_m must be positive")
    values = pd.to_numeric(distance_m, errors="coerce").astype(float)
    if not np.isfinite(values.to_numpy()).all() or (values < 0).any():
        raise ValueError("coast distance must be complete, finite and non-negative")
    return pd.Series(np.exp(-values.to_numpy() / float(scale_m)), index=values.index)


def _validate_input(frame: pd.DataFrame) -> None:
    forbidden = _forbidden_outcome_columns(frame.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in raw structural adapters: {forbidden}")
    if frame is None or len(frame) == 0:
        raise ValueError("candidate frame must contain at least one row")


def adapt_structural_components(
    frame: pd.DataFrame,
    *,
    feature_family: str,
) -> tuple[pd.DataFrame, RawAdapterAudit]:
    """Return the frozen component columns required by ``structural_support``.

    Raw fields are intentionally explicit. Public-layer fractions are used as
    fractions, terrain-derived monotone quantities use outcome-blind within-frame
    ranks, and ecological graph continuity is supplied as precomputed [0,1]
    support rather than inferred here from roads, access or arbitrary raster stacks.
    """
    _validate_input(frame)
    family = str(feature_family).strip()
    if family == BASELINE_FAMILY:
        raise ValueError("GENERAL_SPATIAL_BASELINE_ONLY has no structural raw adapter")

    out = frame.copy()
    rank_fields: list[str] = []
    graph_fields: list[str] = []

    if family == "WETLAND_MOISTURE_STRUCTURE":
        water = _unit_interval(out, "wc_water_frac_250m")
        wetland = _unit_interval(out, "wc_wetland_frac_250m")
        slope = _numeric(out, "slope100")
        tpi = _numeric(out, "tpi300")
        terrain = _unit_interval(out, "terrain_continuity_score_raw")

        out["wetland_water_adjacent_score"] = (water + wetland).clip(0.0, 1.0)
        valley = _rank01(tpi, high_is_support=False)
        low_slope = _rank01(slope, high_is_support=False)
        out["topographic_moisture_score"] = np.minimum(valley, low_slope)
        out["terrain_continuity_score"] = terrain
        rank_fields.extend(["tpi300:low", "slope100:low"])
        graph_fields.append("terrain_continuity_score_raw")

    elif family == "ALPINE_TOPOGRAPHIC_STRUCTURE":
        elev = _numeric(out, "elev")
        landform = _unit_interval(out, "landform_continuity_score_raw")
        ridge_valley = _unit_interval(out, "ridge_valley_continuity_score_raw")

        out["relative_relief_score"] = _rank01(elev, high_is_support=True)
        out["landform_continuity_score"] = landform
        out["ridge_valley_continuity_score"] = ridge_valley
        rank_fields.append("elev:high")
        graph_fields.extend(["landform_continuity_score_raw", "ridge_valley_continuity_score_raw"])

    elif family == "OPEN_GRASSLAND_STRUCTURE":
        grass = _unit_interval(out, "wc_grass_frac_250m")
        fragment = _unit_interval(out, "fragment_continuity_score_raw")
        terrain_context = _unit_interval(out, "terrain_context_score_raw")

        out["open_land_score"] = grass
        out["fragment_continuity_score"] = fragment
        out["terrain_context_score"] = terrain_context
        graph_fields.extend(["fragment_continuity_score_raw", "terrain_context_score_raw"])

    elif family == "COASTAL_ISLAND_STRUCTURE":
        coast = _numeric(out, "coast_distance_m")
        shore_landform = _unit_interval(out, "shore_landform_continuity_score_raw")
        island_component = _unit_interval(out, "island_component_score_raw")

        out["shore_position_score"] = _coast_support(coast, scale_m=1000.0)
        out["shore_landform_continuity_score"] = shore_landform
        out["island_component_score"] = island_component
        graph_fields.extend(["shore_landform_continuity_score_raw", "island_component_score_raw"])

    elif family == "FOREST_EDGE_STRUCTURE":
        tree = _unit_interval(out, "wc_tree_frac_250m")
        edge_mix = _unit_interval(out, "wc_edge_mix_250m")
        terrain = _unit_interval(out, "terrain_component_score_raw")

        # Symmetric edge support: zero for all-tree/all-open, maximum at 50:50.
        out["forest_edge_score"] = (4.0 * tree * (1.0 - tree)).clip(0.0, 1.0)
        out["canopy_opening_transition_score"] = edge_mix
        out["terrain_component_score"] = terrain
        graph_fields.append("terrain_component_score_raw")

    else:
        raise ValueError(f"unknown structural feature family: {family}")

    audit = RawAdapterAudit(
        feature_family=family,
        row_count=int(len(out)),
        frame_relative_ranks_used=tuple(rank_fields),
        pass_through_graph_components=tuple(graph_fields),
    )
    return out, audit
