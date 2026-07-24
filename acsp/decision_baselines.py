"""Deterministic same-pool comparators for finite survey decisions.

These selectors operate on an already generated candidate pool. They do not fit
an SDM and they do not use held-out outcomes. Their purpose is to separate the
value of local evidence, geographic coverage, environmental coverage, and their
combination under an identical candidate budget.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class DecisionBaselineConfig:
    """Configuration shared by deterministic candidate-set baselines."""

    k: int = 5
    id_col: str = "site_id"
    latitude_col: str = "latitude"
    longitude_col: str = "longitude"
    score_col: str = "component_local_habitat_score"
    environmental_cols: tuple[str, ...] = ()
    dual_environment_weight: float = 0.5
    random_draws: int = 200
    random_state: int = 42

    def validate(self) -> None:
        if self.k < 1:
            raise ValueError("k must be at least one")
        if not 0.0 <= float(self.dual_environment_weight) <= 1.0:
            raise ValueError("dual_environment_weight must lie in [0, 1]")
        if self.random_draws < 1:
            raise ValueError("random_draws must be at least one")


def _work(candidates: pd.DataFrame, config: DecisionBaselineConfig) -> pd.DataFrame:
    config.validate()
    if candidates is None:
        raise ValueError("candidates must be a DataFrame")
    required = {config.latitude_col, config.longitude_col}
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError(f"candidates is missing: {', '.join(sorted(missing))}")
    out = candidates.copy().reset_index(drop=True)
    out[config.latitude_col] = pd.to_numeric(out[config.latitude_col], errors="coerce")
    out[config.longitude_col] = pd.to_numeric(out[config.longitude_col], errors="coerce")
    out = out.dropna(subset=[config.latitude_col, config.longitude_col]).reset_index(drop=True)
    if config.id_col not in out.columns:
        out[config.id_col] = [f"candidate-{index + 1:06d}" for index in range(len(out))]
    out["_stable_id"] = out[config.id_col].astype(str)
    return out


def _haversine_matrix(frame: pd.DataFrame, config: DecisionBaselineConfig) -> np.ndarray:
    lat = np.radians(frame[config.latitude_col].to_numpy(float))
    lon = np.radians(frame[config.longitude_col].to_numpy(float))
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _robust_environment_matrix(frame: pd.DataFrame, columns: Sequence[str]) -> np.ndarray:
    if not columns:
        raise ValueError("environmental_cols are required for environmental baselines")
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"candidates is missing environmental columns: {', '.join(sorted(missing))}")
    values = frame[list(columns)].apply(pd.to_numeric, errors="coerce")
    medians = values.median(axis=0, skipna=True)
    values = values.fillna(medians)
    if values.isna().any().any():
        raise ValueError("environmental columns contain no finite values")
    q25 = values.quantile(0.25)
    q75 = values.quantile(0.75)
    scale = (q75 - q25).replace(0.0, np.nan)
    keep = scale.notna() & np.isfinite(scale)
    if not bool(keep.any()):
        return np.zeros((len(frame), len(frame)), dtype=float)
    standardized = (values.loc[:, keep] - medians.loc[keep]) / scale.loc[keep]
    array = standardized.to_numpy(float)
    delta = array[:, None, :] - array[None, :, :]
    return np.sqrt(np.sum(delta * delta, axis=2))


def _unit_distance(matrix: np.ndarray) -> np.ndarray:
    finite = matrix[np.isfinite(matrix)]
    maximum = float(finite.max()) if finite.size else 0.0
    if maximum <= 0.0:
        return np.zeros_like(matrix, dtype=float)
    return np.clip(matrix / maximum, 0.0, 1.0)


def _maximin_indices(matrix: np.ndarray, frame: pd.DataFrame, k: int) -> list[int]:
    n = len(frame)
    if n == 0:
        return []
    target = min(int(k), n)
    mean_distance = matrix.mean(axis=1)
    first = min(
        range(n),
        key=lambda index: (-float(mean_distance[index]), frame.at[index, "_stable_id"], index),
    )
    selected = [first]
    while len(selected) < target:
        remaining = [index for index in range(n) if index not in selected]
        nearest = {index: float(np.min(matrix[index, selected])) for index in remaining}
        chosen = min(
            remaining,
            key=lambda index: (-nearest[index], frame.at[index, "_stable_id"], index),
        )
        selected.append(chosen)
    return selected


def _finalize(frame: pd.DataFrame, indices: Sequence[int], method: str) -> pd.DataFrame:
    out = frame.iloc[list(indices)].drop(columns=["_stable_id"], errors="ignore").copy().reset_index(drop=True)
    out["decision_method"] = method
    out["decision_rank"] = range(1, len(out) + 1)
    return out


def select_score_top_k(candidates: pd.DataFrame, config: DecisionBaselineConfig | None = None) -> pd.DataFrame:
    """Select the highest local-evidence candidates with deterministic ties."""
    cfg = config or DecisionBaselineConfig()
    frame = _work(candidates, cfg)
    if cfg.score_col not in frame.columns:
        raise ValueError(f"candidates is missing score column: {cfg.score_col}")
    frame["_score"] = pd.to_numeric(frame[cfg.score_col], errors="coerce").fillna(-math.inf)
    ordered = frame.sort_values(["_score", "_stable_id"], ascending=[False, True], kind="mergesort")
    result = ordered.head(min(cfg.k, len(ordered))).drop(columns=["_score"]).reset_index(drop=True)
    return _finalize(result, range(len(result)), "local_evidence_top_k")


def select_geographic_farthest(candidates: pd.DataFrame, config: DecisionBaselineConfig | None = None) -> pd.DataFrame:
    """Select a deterministic geographic maximin set from the same pool."""
    cfg = config or DecisionBaselineConfig()
    frame = _work(candidates, cfg)
    return _finalize(frame, _maximin_indices(_haversine_matrix(frame, cfg), frame, cfg.k), "geographic_maximin")


def select_environmental_farthest(candidates: pd.DataFrame, config: DecisionBaselineConfig | None = None) -> pd.DataFrame:
    """Select a deterministic environmental maximin set after robust scaling."""
    cfg = config or DecisionBaselineConfig()
    frame = _work(candidates, cfg)
    matrix = _robust_environment_matrix(frame, cfg.environmental_cols)
    return _finalize(frame, _maximin_indices(matrix, frame, cfg.k), "environmental_maximin")


def select_dual_space_farthest(candidates: pd.DataFrame, config: DecisionBaselineConfig | None = None) -> pd.DataFrame:
    """Select a maximin set in a declared geographic-environmental distance mixture."""
    cfg = config or DecisionBaselineConfig()
    frame = _work(candidates, cfg)
    geographic = _unit_distance(_haversine_matrix(frame, cfg))
    environmental = _unit_distance(_robust_environment_matrix(frame, cfg.environmental_cols))
    weight = float(cfg.dual_environment_weight)
    matrix = (1.0 - weight) * geographic + weight * environmental
    return _finalize(frame, _maximin_indices(matrix, frame, cfg.k), "dual_space_maximin")


def random_same_pool_sets(candidates: pd.DataFrame, config: DecisionBaselineConfig | None = None) -> list[pd.DataFrame]:
    """Draw reproducible random sets from the identical candidate pool."""
    cfg = config or DecisionBaselineConfig()
    frame = _work(candidates, cfg)
    rng = np.random.default_rng(int(cfg.random_state))
    size = min(cfg.k, len(frame))
    draws: list[pd.DataFrame] = []
    for draw in range(1, cfg.random_draws + 1):
        indices = rng.choice(len(frame), size=size, replace=False) if size else np.array([], dtype=int)
        selected = _finalize(frame, indices.tolist(), "random_same_pool")
        selected["random_draw"] = draw
        draws.append(selected)
    return draws


def recovered_fraction(selected: pd.DataFrame, *, covered_col: str = "covered_heldout_ids", all_col: str = "all_heldout_ids") -> float:
    """Calculate set-level held-out recovery from auditable candidate coverage IDs."""
    if selected is None or selected.empty:
        return 0.0
    if covered_col not in selected.columns or all_col not in selected.columns:
        raise ValueError(f"selected candidates require {covered_col} and {all_col}")
    all_ids: set[str] = set()
    recovered: set[str] = set()
    for value in selected[all_col].dropna().astype(str):
        all_ids.update(item for item in value.split(";") if item)
    for value in selected[covered_col].dropna().astype(str):
        recovered.update(item for item in value.split(";") if item)
    return len(recovered & all_ids) / len(all_ids) if all_ids else 0.0


def compare_decision_baselines(
    candidates: pd.DataFrame,
    config: DecisionBaselineConfig | None = None,
    *,
    covered_col: str = "covered_heldout_ids",
    all_col: str = "all_heldout_ids",
) -> pd.DataFrame:
    """Compare standard same-pool selectors using precomputed held-out coverage.

    Held-out IDs are used only after each selector has returned its set. They are
    never inputs to the selection functions.
    """
    cfg = config or DecisionBaselineConfig()
    selectors = [select_score_top_k, select_geographic_farthest]
    if cfg.environmental_cols:
        selectors.extend([select_environmental_farthest, select_dual_space_farthest])
    rows: list[dict[str, object]] = []
    for selector in selectors:
        selected = selector(candidates, cfg)
        rows.append({
            "decision_method": str(selected["decision_method"].iloc[0]) if not selected.empty else selector.__name__,
            "selected_count": int(len(selected)),
            "heldout_recall": recovered_fraction(selected, covered_col=covered_col, all_col=all_col),
            "selected_ids": ";".join(selected[cfg.id_col].astype(str)),
        })
    random_recalls = [
        recovered_fraction(draw, covered_col=covered_col, all_col=all_col)
        for draw in random_same_pool_sets(candidates, cfg)
    ]
    rows.append({
        "decision_method": "random_same_pool_mean",
        "selected_count": min(cfg.k, len(candidates)),
        "heldout_recall": float(np.mean(random_recalls)) if random_recalls else 0.0,
        "selected_ids": "",
    })
    return pd.DataFrame(rows)
