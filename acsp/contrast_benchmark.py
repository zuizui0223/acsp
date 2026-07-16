"""Spatially honest benchmarks for local ecological contrast selection.

The benchmark rebuilds candidates from training occurrences only. Environmental
values at training occurrences are provisionally represented by the globally
nearest candidate, while availability is defined by point-centred local support
neighbourhoods rather than coincident raster or grid cells. Held-out occurrences
are used only for final geographic recovery evaluation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

from .contrast import (
    automatic_support_size,
    contrast_membership,
    fit_local_ecological_contrast,
    local_contrasts,
    select_contrast_cover,
)
from .planning import integrated_candidate_scores, select_complementary_candidates

DEFAULT_CONTRAST_FEATURES = (
    "elevation",
    "slope",
    "roughness",
    "tpi",
    "distance_to_coast_m",
)
EARTH_RADIUS_KM = 6371.0088


def _coordinates(frame: pd.DataFrame) -> np.ndarray:
    for latitude, longitude in (("latitude", "longitude"), ("_latitude", "_longitude")):
        if latitude in frame.columns and longitude in frame.columns:
            return frame[[latitude, longitude]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    raise ValueError("table lacks latitude and longitude columns")


def _metric_coordinates(coords: np.ndarray) -> np.ndarray:
    """Return locally metric coordinates in kilometres for neighbourhood search."""
    values = np.asarray(coords, dtype=float)
    mean_latitude = float(np.nanmean(values[:, 0]))
    return np.column_stack(
        [values[:, 0] * 111.0, values[:, 1] * 111.0 * np.cos(np.deg2rad(mean_latitude))]
    )


def _distance_matrix_km(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    first_lat = np.radians(first[:, 0])[:, None]
    first_lon = np.radians(first[:, 1])[:, None]
    second_lat = np.radians(second[:, 0])[None, :]
    second_lon = np.radians(second[:, 1])[None, :]
    delta_lat = second_lat - first_lat
    delta_lon = second_lon - first_lon
    value = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(first_lat) * np.cos(second_lat) * np.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(value, 0.0, 1.0)))


def _block_labels(coords: np.ndarray, block_degrees: float) -> np.ndarray:
    block = max(float(block_degrees), 1e-6)
    return np.asarray(
        [f"{int(np.floor(lat / block))}:{int(np.floor(lon / block))}" for lat, lon in coords],
        dtype=object,
    )


def _finite_features(frame: pd.DataFrame, requested: tuple[str, ...]) -> tuple[pd.DataFrame, list[str]]:
    columns = [column for column in requested if column in frame.columns]
    if not columns:
        raise ValueError("candidate pool has no contrast features")
    result = frame.copy()
    for column in columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=columns + ["latitude", "longitude"]).reset_index(drop=True)
    if len(result) < 2:
        raise ValueError("fewer than two complete candidates remain")
    return result, columns


def _occurrence_proxies(
    training: pd.DataFrame,
    candidates: pd.DataFrame,
    features: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Map occurrences to nearest candidate features without requiring cell overlap."""
    occurrence_coords = _coordinates(training)
    candidate_coords = candidates[["latitude", "longitude"]].to_numpy(float)
    distances = _distance_matrix_km(occurrence_coords, candidate_coords)
    nearest = np.argmin(distances, axis=1)
    features_matrix = candidates.iloc[nearest][features].to_numpy(float)
    return features_matrix, occurrence_coords, distances[np.arange(len(nearest)), nearest]


def _prototype_membership(occupied: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    scaler = RobustScaler(quantile_range=(25.0, 75.0)).fit(occupied)
    occupied_scaled = scaler.transform(occupied)
    candidate_scaled = scaler.transform(candidates)
    delta = candidate_scaled[:, None, :] - occupied_scaled[None, :, :]
    distance2 = np.mean(delta * delta, axis=2)
    return np.exp(-0.5 * distance2)


def _covered_ids(selected: pd.DataFrame, heldout: pd.DataFrame, radius_km: float) -> set[str]:
    distances = _distance_matrix_km(_coordinates(heldout), selected[["latitude", "longitude"]].to_numpy(float))
    identifiers = heldout["_contrast_occurrence_id"].astype(str).to_numpy()
    return set(identifiers[np.any(distances <= float(radius_km), axis=1)])


def spatial_block_contrast_benchmark(
    occurrences: pd.DataFrame,
    candidate_builder: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    block_degrees: float = 0.10,
    availability_block_degrees: float | None = None,
    repeats: int = 5,
    holdout_fraction: float = 0.20,
    top_k: int = 5,
    hit_radius_km: float = 10.0,
    random_draws: int = 200,
    random_state: int = 42,
    feature_columns: tuple[str, ...] = DEFAULT_CONTRAST_FEATURES,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare local contrast, absolute prototypes, current ACSP, and random.

    ``availability_block_degrees`` is retained for API compatibility but no longer
    controls availability. Local support size is selected deterministically from
    candidate-pool size, and no occurrence-candidate grid-cell coincidence is
    required.
    """

    del availability_block_degrees
    work = occurrences.copy().reset_index(drop=True)
    coords = _coordinates(work)
    finite = np.isfinite(coords).all(axis=1)
    work = work.loc[finite].reset_index(drop=True)
    coords = coords[finite]
    if len(work) < 4:
        raise ValueError("at least four occurrences are required")
    work["_contrast_occurrence_id"] = np.arange(len(work), dtype=int)
    work["_contrast_holdout_block"] = _block_labels(coords, block_degrees)
    blocks = work["_contrast_holdout_block"].drop_duplicates().to_numpy()
    if len(blocks) < 2:
        raise ValueError("occurrences occupy fewer than two holdout blocks")

    rng = np.random.default_rng(int(random_state))
    n_holdout = min(len(blocks) - 1, max(1, int(round(len(blocks) * holdout_fraction))))
    candidate_outputs: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []

    for repeat in range(1, max(1, int(repeats)) + 1):
        held_blocks = set(rng.choice(blocks, size=n_holdout, replace=False).tolist())
        heldout = work[work["_contrast_holdout_block"].isin(held_blocks)].copy()
        training_with_blocks = work[~work["_contrast_holdout_block"].isin(held_blocks)].copy()
        training = training_with_blocks.drop(columns=["_contrast_holdout_block", "_contrast_occurrence_id"])
        try:
            raw_candidates = candidate_builder(training.copy())
            if raw_candidates is None or raw_candidates.empty:
                raise ValueError("candidate builder returned no rows")
            candidate_type = raw_candidates.get("candidate_type", pd.Series("", index=raw_candidates.index)).astype(str)
            raw_candidates = raw_candidates[
                ~candidate_type.str.contains("occurrence-supported|known-location|known anchor", case=False, na=False)
            ].reset_index(drop=True)
            scored = integrated_candidate_scores(raw_candidates, exclude_occurrence_derived=True)
            pool, features = _finite_features(scored, feature_columns)
            candidate_matrix = pool[features].to_numpy(float)
            candidate_geo = pool[["latitude", "longitude"]].to_numpy(float)
            candidate_metric = _metric_coordinates(candidate_geo)
            support_size = automatic_support_size(len(pool))

            occupied_matrix, occupied_geo, proxy_distances = _occurrence_proxies(
                training, pool, features
            )
            occupied_groups = training_with_blocks["_contrast_holdout_block"].to_numpy(object)
            if len(np.unique(occupied_groups)) < 2:
                raise ValueError("fewer than two occupied training blocks")
            occupied_metric = _metric_coordinates(occupied_geo)

            operator = fit_local_ecological_contrast(
                occupied_matrix,
                occupied_metric,
                occupied_groups,
                candidate_matrix,
                candidate_metric,
                n_neighbors=support_size,
            )
            transformed = local_contrasts(
                candidate_matrix,
                candidate_metric,
                candidate_matrix,
                candidate_metric,
                n_neighbors=support_size,
                self_indices=np.arange(len(pool)),
            )
            contrast_matrix = contrast_membership(operator, transformed)
            contrast_indices = select_contrast_cover(
                contrast_matrix, n_select=min(int(top_k), len(pool))
            )
            prototype_matrix = _prototype_membership(occupied_matrix, candidate_matrix)
            prototype_indices = select_contrast_cover(
                prototype_matrix, n_select=min(int(top_k), len(pool))
            )
            current = select_complementary_candidates(
                pool,
                min(int(top_k), len(pool)),
                score_col="component_local_habitat_score",
                evidence_weight=1.0,
            )
            methods = {
                "ecological_contrast": pool.iloc[contrast_indices],
                "absolute_prototype": pool.iloc[prototype_indices],
                "current_acsp": current,
            }
            all_ids = set(heldout["_contrast_occurrence_id"].astype(str))
            row: dict[str, Any] = {
                "repeat": repeat,
                "status": "ok",
                "training_records": len(training),
                "heldout_records": len(heldout),
                "candidate_pool": len(pool),
                "feature_columns": ";".join(features),
                "occupied_availability_blocks": len(np.unique(occupied_groups)),
                "target_availability_blocks": len(pool),
                "local_support_neighbors": support_size,
                "median_occurrence_proxy_km": float(np.median(proxy_distances)),
                "availability_design": "point-centred nearest-support neighbourhood",
            }
            for name, selected in methods.items():
                recovered = _covered_ids(selected, heldout, hit_radius_km)
                row[f"{name}_recall"] = len(recovered) / max(1, len(all_ids))
                rank_lookup = {int(index): rank for rank, index in enumerate(selected.index, start=1)}
                pool[f"{name}_selection_rank"] = pd.Series(pool.index.map(rank_lookup), dtype="Int64")
            random_values = []
            for _ in range(max(1, int(random_draws))):
                selected = pool.iloc[rng.choice(len(pool), size=min(int(top_k), len(pool)), replace=False)]
                random_values.append(len(_covered_ids(selected, heldout, hit_radius_km)) / max(1, len(all_ids)))
            row["random_same_pool_recall"] = float(np.mean(random_values))
            row["contrast_lift_over_random"] = row["ecological_contrast_recall"] - row["random_same_pool_recall"]
            row["contrast_lift_over_absolute"] = row["ecological_contrast_recall"] - row["absolute_prototype_recall"]
            pool["repeat"] = repeat
            pool["all_heldout_ids"] = ";".join(sorted(all_ids))
            candidate_outputs.append(pool)
            fold_rows.append(row)
        except Exception as exc:
            fold_rows.append({
                "repeat": repeat,
                "status": "failed",
                "training_records": len(training),
                "heldout_records": len(heldout),
                "reason": str(exc),
            })

    candidates = pd.concat(candidate_outputs, ignore_index=True) if candidate_outputs else pd.DataFrame()
    return candidates, pd.DataFrame(fold_rows)
