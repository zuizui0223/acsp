"""Frozen local ecological-graph support for prospective Cirsium discovery.

This module builds outcome-blind continuity primitives on a declared regular
candidate grid. It uses only ecological/public-layer columns. Roads, trails,
permissions, access and field outcomes are explicitly excluded and belong to G_F.

The graph is a Moore-neighbourhood (8-neighbour) grid with no outcome-tuned
threshold. Continuity is represented by local means or robust local similarity,
not by fitting a cutoff to successful field locations.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from acsp.structural_selector import _forbidden_outcome_columns


@dataclass(frozen=True)
class StructuralGraphAudit:
    feature_family: str
    row_count: int
    neighbourhood_radius_cells: int
    graph_type: str = "REGULAR_GRID_MOORE_8_NEIGHBOUR"
    field_outcomes_used: bool = False
    human_access_used: bool = False
    fitted_thresholds: bool = False


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise ValueError(f"missing required graph column: {column}")
    values = pd.to_numeric(frame[column], errors="coerce")
    if not np.isfinite(values.to_numpy(float)).all():
        raise ValueError(f"graph column must be complete and finite: {column}")
    return values.astype(float)


def _unit(frame: pd.DataFrame, column: str) -> pd.Series:
    values = _numeric(frame, column)
    if ((values < 0) | (values > 1)).any():
        raise ValueError(f"graph support column outside [0,1]: {column}")
    return values


def _validate(frame: pd.DataFrame, radius: int) -> None:
    if frame is None or frame.empty:
        raise ValueError("candidate frame must contain at least one row")
    if int(radius) < 1:
        raise ValueError("neighbourhood radius must be >=1 cell")
    forbidden = _forbidden_outcome_columns(frame.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in ecological graph construction: {forbidden}")
    for column in ("grid_row", "grid_col"):
        _numeric(frame, column)
    pairs = list(zip(frame["grid_row"].astype(int), frame["grid_col"].astype(int)))
    if len(set(pairs)) != len(pairs):
        raise ValueError("grid_row/grid_col pairs must be unique")


def _neighbour_indices(frame: pd.DataFrame, radius: int) -> list[list[int]]:
    rows = frame["grid_row"].astype(int).to_numpy()
    cols = frame["grid_col"].astype(int).to_numpy()
    lookup = {(int(r), int(c)): i for i, (r, c) in enumerate(zip(rows, cols))}
    result: list[list[int]] = []
    r = int(radius)
    for rr, cc in zip(rows, cols):
        indices: list[int] = []
        for dr in range(-r, r + 1):
            for dc in range(-r, r + 1):
                if dr == 0 and dc == 0:
                    continue
                idx = lookup.get((int(rr + dr), int(cc + dc)))
                if idx is not None:
                    indices.append(idx)
        result.append(indices)
    return result


def grid_local_mean(frame: pd.DataFrame, value: pd.Series, *, radius: int = 1) -> pd.Series:
    """Mean support over self plus existing Moore neighbours."""
    _validate(frame, radius)
    values = pd.to_numeric(value, errors="coerce").to_numpy(float)
    if len(values) != len(frame) or not np.isfinite(values).all():
        raise ValueError("local-mean values must align with frame and be finite")
    neighbours = _neighbour_indices(frame, radius)
    out = np.empty(len(frame), dtype=float)
    for i, adjacent in enumerate(neighbours):
        indices = [i, *adjacent]
        out[i] = float(np.mean(values[indices]))
    return pd.Series(out, index=frame.index)


def grid_local_similarity(
    frame: pd.DataFrame,
    feature_columns: tuple[str, ...],
    *,
    radius: int = 1,
) -> pd.Series:
    """Robust local terrain similarity with fixed exp(-distance) mapping."""
    _validate(frame, radius)
    if not feature_columns:
        raise ValueError("feature_columns cannot be empty")
    values = np.column_stack([_numeric(frame, column).to_numpy(float) for column in feature_columns])
    median = np.median(values, axis=0)
    q25 = np.quantile(values, 0.25, axis=0)
    q75 = np.quantile(values, 0.75, axis=0)
    scale = np.where((q75 - q25) > 1e-9, q75 - q25, 1.0)
    z = (values - median) / scale
    neighbours = _neighbour_indices(frame, radius)
    out = np.ones(len(frame), dtype=float)
    for i, adjacent in enumerate(neighbours):
        if not adjacent:
            out[i] = 1.0
            continue
        distances = np.sqrt(np.sum((z[adjacent] - z[i]) ** 2, axis=1))
        out[i] = float(np.exp(-np.mean(distances)))
    return pd.Series(np.clip(out, 0.0, 1.0), index=frame.index)


def _rank01(values: pd.Series, *, high: bool) -> pd.Series:
    ranked = values.rank(method="average", pct=True).astype(float)
    if not high:
        ranked = 1.0 - ranked + 1.0 / max(len(ranked), 1)
    return ranked.clip(0.0, 1.0)


def build_structural_graph_primitives(
    frame: pd.DataFrame,
    *,
    feature_family: str,
    target_component_id: str | None = None,
    radius: int = 1,
) -> tuple[pd.DataFrame, StructuralGraphAudit]:
    """Add the graph-support raw columns required by ``structural_raw_adapters``."""
    _validate(frame, radius)
    family = str(feature_family).strip()
    out = frame.copy()

    if family == "WETLAND_MOISTURE_STRUCTURE":
        slope = _numeric(out, "slope100")
        tpi = _numeric(out, "tpi300")
        moisture = np.minimum(_rank01(tpi, high=False), _rank01(slope, high=False))
        out["terrain_continuity_score_raw"] = grid_local_mean(out, moisture, radius=radius)

    elif family == "ALPINE_TOPOGRAPHIC_STRUCTURE":
        for column in ("elev", "slope100", "tpi300", "rough300"):
            _numeric(out, column)
        out["landform_continuity_score_raw"] = grid_local_similarity(
            out, ("elev", "slope100", "tpi300", "rough300"), radius=radius
        )
        tpi_rank = _rank01(_numeric(out, "tpi300"), high=True)
        ridge_valley = (2.0 * (tpi_rank - 0.5).abs()).clip(0.0, 1.0)
        out["ridge_valley_continuity_score_raw"] = grid_local_mean(out, ridge_valley, radius=radius)

    elif family == "OPEN_GRASSLAND_STRUCTURE":
        grass = _unit(out, "wc_grass_frac_250m")
        out["fragment_continuity_score_raw"] = grid_local_mean(out, grass, radius=radius)
        out["terrain_context_score_raw"] = grid_local_similarity(
            out, ("slope100", "tpi300", "rough300"), radius=radius
        )

    elif family == "COASTAL_ISLAND_STRUCTURE":
        coast = _numeric(out, "coast_distance_m")
        if (coast < 0).any():
            raise ValueError("coast_distance_m must be non-negative")
        grass = _unit(out, "wc_grass_frac_250m")
        bare = _unit(out, "wc_bare_frac_250m")
        shore = pd.Series(np.exp(-coast.to_numpy(float) / 1000.0), index=out.index)
        shore_landform = np.minimum(shore, np.maximum(grass, bare))
        out["shore_landform_continuity_score_raw"] = grid_local_mean(out, shore_landform, radius=radius)
        if target_component_id is None or "ecological_component_id" not in out.columns:
            raise ValueError("coastal graph requires frozen target_component_id and ecological_component_id")
        out["island_component_score_raw"] = (
            out["ecological_component_id"].astype(str).eq(str(target_component_id)).astype(float)
        )

    elif family == "FOREST_EDGE_STRUCTURE":
        # Forest-edge location itself is computed in the raw adapter from WorldCover;
        # graph support here only represents local terrain continuity.
        out["terrain_component_score_raw"] = grid_local_similarity(
            out, ("slope100", "tpi300", "rough300"), radius=radius
        )

    elif family == "GENERAL_SPATIAL_BASELINE_ONLY":
        raise ValueError("GENERAL_SPATIAL_BASELINE_ONLY has no ecological graph primitives")
    else:
        raise ValueError(f"unknown structural feature family: {family}")

    return out, StructuralGraphAudit(
        feature_family=family,
        row_count=int(len(out)),
        neighbourhood_radius_cells=int(radius),
    )
