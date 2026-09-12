"""Declarative, outcome-blind structural recipes for experimental discovery.

The five current structural families share a small set of reusable primitives:
relative rank, local continuity, local multivariate similarity, edge/fragment
signals, connected-component membership, distance decay, and conjunctive minimum.

This module expresses those families as ordered recipes. It initially runs in
parallel with the frozen hard-coded Cirsium pipeline; parity tests must pass before
any caller may substitute the recipe engine in an existing frozen experiment.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from acsp.structural_graph import grid_local_mean, grid_local_similarity
from acsp.structural_selector import _forbidden_outcome_columns


@dataclass(frozen=True)
class RecipeStep:
    output: str
    operation: str
    inputs: tuple[str, ...]
    parameters: tuple[tuple[str, Any], ...] = ()

    @property
    def params(self) -> dict[str, Any]:
        return dict(self.parameters)


@dataclass(frozen=True)
class StructuralRecipe:
    recipe_id: str
    label: str
    required_raw_columns: tuple[str, ...]
    steps: tuple[RecipeStep, ...]
    support_components: tuple[str, ...]
    composition_rule: str = "ROW_MIN_CONJUNCTIVE_SUPPORT"


@dataclass(frozen=True)
class StructuralRecipeAudit:
    recipe_id: str
    row_count: int
    graph_radius_cells: int
    support_components: tuple[str, ...]
    composition_rule: str
    recipe_fingerprint: str
    field_outcomes_used: bool = False
    human_access_used: bool = False
    fitted_feature_weights: bool = False


def _step(output: str, operation: str, *inputs: str, **parameters: Any) -> RecipeStep:
    return RecipeStep(
        output=str(output),
        operation=str(operation),
        inputs=tuple(str(value) for value in inputs),
        parameters=tuple(sorted(parameters.items())),
    )


STRUCTURAL_RECIPES: dict[str, StructuralRecipe] = {
    "WETLAND_MOISTURE_STRUCTURE": StructuralRecipe(
        recipe_id="WETLAND_MOISTURE_STRUCTURE",
        label="Wetland / moisture continuity",
        required_raw_columns=("wc_water_frac_250m", "wc_wetland_frac_250m", "slope100", "tpi300"),
        steps=(
            _step("wetland_water_adjacent_score", "clip_sum", "wc_water_frac_250m", "wc_wetland_frac_250m"),
            _step("_wetland_valley_rank", "rank", "tpi300", high=False),
            _step("_wetland_low_slope_rank", "rank", "slope100", high=False),
            _step("topographic_moisture_score", "minimum", "_wetland_valley_rank", "_wetland_low_slope_rank"),
            _step("terrain_continuity_score", "local_mean", "topographic_moisture_score"),
        ),
        support_components=("wetland_water_adjacent_score", "topographic_moisture_score", "terrain_continuity_score"),
    ),
    "ALPINE_TOPOGRAPHIC_STRUCTURE": StructuralRecipe(
        recipe_id="ALPINE_TOPOGRAPHIC_STRUCTURE",
        label="Alpine topographic continuity",
        required_raw_columns=("elev", "slope100", "tpi300", "rough300"),
        steps=(
            _step("relative_relief_score", "rank", "elev", high=True),
            _step("landform_continuity_score", "local_similarity", "elev", "slope100", "tpi300", "rough300"),
            _step("_alpine_tpi_rank", "rank", "tpi300", high=True),
            _step("_alpine_ridge_valley", "abs_center_scale", "_alpine_tpi_rank", center=0.5, scale=2.0),
            _step("ridge_valley_continuity_score", "local_mean", "_alpine_ridge_valley"),
        ),
        support_components=("relative_relief_score", "landform_continuity_score", "ridge_valley_continuity_score"),
    ),
    "OPEN_GRASSLAND_STRUCTURE": StructuralRecipe(
        recipe_id="OPEN_GRASSLAND_STRUCTURE",
        label="Open grassland / fragment continuity",
        required_raw_columns=("wc_grass_frac_250m", "slope100", "tpi300", "rough300"),
        steps=(
            _step("open_land_score", "identity", "wc_grass_frac_250m"),
            _step("fragment_continuity_score", "local_mean", "wc_grass_frac_250m"),
            _step("terrain_context_score", "local_similarity", "slope100", "tpi300", "rough300"),
        ),
        support_components=("open_land_score", "fragment_continuity_score", "terrain_context_score"),
    ),
    "COASTAL_ISLAND_STRUCTURE": StructuralRecipe(
        recipe_id="COASTAL_ISLAND_STRUCTURE",
        label="Coastal / island structure",
        required_raw_columns=("coast_distance_m", "wc_grass_frac_250m", "wc_bare_frac_250m", "ecological_component_id"),
        steps=(
            _step("shore_position_score", "exp_decay", "coast_distance_m", scale=1000.0),
            _step("_coastal_open_cover", "maximum", "wc_grass_frac_250m", "wc_bare_frac_250m"),
            _step("_coastal_shore_landform", "minimum", "shore_position_score", "_coastal_open_cover"),
            _step("shore_landform_continuity_score", "local_mean", "_coastal_shore_landform"),
            _step("island_component_score", "component_membership", "ecological_component_id"),
        ),
        support_components=("shore_position_score", "shore_landform_continuity_score", "island_component_score"),
    ),
    "FOREST_EDGE_STRUCTURE": StructuralRecipe(
        recipe_id="FOREST_EDGE_STRUCTURE",
        label="Forest-edge structure",
        required_raw_columns=("wc_tree_frac_250m", "wc_edge_mix_250m", "slope100", "tpi300", "rough300"),
        steps=(
            _step("forest_edge_score", "symmetric_edge", "wc_tree_frac_250m"),
            _step("canopy_opening_transition_score", "identity", "wc_edge_mix_250m"),
            _step("terrain_component_score", "local_similarity", "slope100", "tpi300", "rough300"),
        ),
        support_components=("forest_edge_score", "canopy_opening_transition_score", "terrain_component_score"),
    ),
}


def get_structural_recipe(recipe_id: str) -> StructuralRecipe:
    key = str(recipe_id).strip()
    try:
        return STRUCTURAL_RECIPES[key]
    except KeyError as exc:
        raise ValueError(f"unknown structural recipe: {key!r}") from exc


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise ValueError(f"recipe input is missing: {column}")
    values = pd.to_numeric(frame[column], errors="coerce")
    if not np.isfinite(values.to_numpy(float)).all():
        raise ValueError(f"recipe input must be complete and finite: {column}")
    return values.astype(float)


def _unit(frame: pd.DataFrame, column: str) -> pd.Series:
    values = _numeric(frame, column)
    if ((values < 0.0) | (values > 1.0)).any():
        raise ValueError(f"recipe unit-interval input outside [0,1]: {column}")
    return values


def _rank01(values: pd.Series, *, high: bool) -> pd.Series:
    ranked = values.rank(method="average", pct=True).astype(float)
    if not bool(high):
        ranked = 1.0 - ranked + 1.0 / max(len(ranked), 1)
    return ranked.clip(0.0, 1.0)


def _recipe_fingerprint(recipe: StructuralRecipe) -> str:
    payload = asdict(recipe)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_structural_recipe(
    frame: pd.DataFrame,
    *,
    recipe_id: str,
    target_component_id: str | None = None,
    graph_radius_cells: int = 1,
) -> tuple[pd.DataFrame, StructuralRecipeAudit]:
    """Evaluate one declared recipe and add ``structural_support``.

    No operation fits a parameter from outcomes. Temporary step outputs prefixed
    with ``_`` are retained in the returned development frame for auditability.
    """
    if frame is None or frame.empty:
        raise ValueError("recipe frame cannot be empty")
    if int(graph_radius_cells) < 1:
        raise ValueError("graph_radius_cells must be >=1")
    forbidden = _forbidden_outcome_columns(frame.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in structural recipes: {forbidden}")
    recipe = get_structural_recipe(recipe_id)
    missing = sorted(set(recipe.required_raw_columns).difference(frame.columns))
    if missing:
        raise ValueError(f"recipe {recipe.recipe_id} missing raw columns: {missing}")

    work = frame.copy()
    for step in recipe.steps:
        op = step.operation
        inputs = step.inputs
        params = step.params
        if op == "identity":
            work[step.output] = _unit(work, inputs[0])
        elif op == "clip_sum":
            values = sum((_unit(work, column) for column in inputs), start=pd.Series(0.0, index=work.index))
            work[step.output] = values.clip(0.0, 1.0)
        elif op == "rank":
            work[step.output] = _rank01(_numeric(work, inputs[0]), high=bool(params["high"]))
        elif op == "minimum":
            matrix = np.column_stack([_unit(work, column).to_numpy(float) for column in inputs])
            work[step.output] = np.min(matrix, axis=1)
        elif op == "maximum":
            matrix = np.column_stack([_unit(work, column).to_numpy(float) for column in inputs])
            work[step.output] = np.max(matrix, axis=1)
        elif op == "abs_center_scale":
            center = float(params["center"])
            scale = float(params["scale"])
            work[step.output] = (scale * (_unit(work, inputs[0]) - center).abs()).clip(0.0, 1.0)
        elif op == "symmetric_edge":
            values = _unit(work, inputs[0])
            work[step.output] = (4.0 * values * (1.0 - values)).clip(0.0, 1.0)
        elif op == "exp_decay":
            scale = float(params["scale"])
            if scale <= 0:
                raise ValueError("exp_decay scale must be positive")
            distance = _numeric(work, inputs[0])
            if (distance < 0).any():
                raise ValueError("exp_decay distance cannot be negative")
            work[step.output] = np.exp(-distance.to_numpy(float) / scale)
        elif op == "local_mean":
            work[step.output] = grid_local_mean(work, _unit(work, inputs[0]), radius=int(graph_radius_cells))
        elif op == "local_similarity":
            work[step.output] = grid_local_similarity(work, tuple(inputs), radius=int(graph_radius_cells))
        elif op == "component_membership":
            if not str(target_component_id or "").strip():
                raise ValueError("component_membership requires target_component_id")
            work[step.output] = work[inputs[0]].astype(str).eq(str(target_component_id)).astype(float)
        else:
            raise ValueError(f"unknown structural recipe operation: {op}")

    matrix = np.column_stack([_unit(work, column).to_numpy(float) for column in recipe.support_components])
    work["structural_support"] = np.min(matrix, axis=1)
    return work, StructuralRecipeAudit(
        recipe_id=recipe.recipe_id,
        row_count=int(len(work)),
        graph_radius_cells=int(graph_radius_cells),
        support_components=recipe.support_components,
        composition_rule=recipe.composition_rule,
        recipe_fingerprint=_recipe_fingerprint(recipe),
    )


def rank_structural_recipe(
    frame: pd.DataFrame,
    *,
    recipe_id: str,
    target_component_id: str | None = None,
    graph_radius_cells: int = 1,
    candidate_id_column: str = "candidate_cell_id",
) -> tuple[pd.DataFrame, StructuralRecipeAudit]:
    """Evaluate a recipe and return its full deterministic support order."""
    evaluated, audit = evaluate_structural_recipe(
        frame,
        recipe_id=recipe_id,
        target_component_id=target_component_id,
        graph_radius_cells=graph_radius_cells,
    )
    if candidate_id_column not in evaluated.columns:
        raise ValueError(f"candidate frame missing ID column: {candidate_id_column}")
    if evaluated[candidate_id_column].isna().any() or evaluated[candidate_id_column].astype(str).duplicated().any():
        raise ValueError("candidate IDs must be complete and unique")
    ordered = evaluated.sort_values(
        ["structural_support", candidate_id_column],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    ordered["decision_method"] = "STRUCTURAL_RECIPE_SUPPORT"
    ordered["decision_rank"] = range(1, len(ordered) + 1)
    return ordered, audit
