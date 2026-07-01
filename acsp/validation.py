"""Spatially honest retrospective validation for ACSP candidate builders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from .planning import EARTH_RADIUS_M, integrated_candidate_scores


def _nearest_distances_km(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    if len(source) == 0 or len(target) == 0:
        return np.full(len(target), np.inf, dtype=float)
    lat1 = np.radians(target[:, 0])[:, None]
    lon1 = np.radians(target[:, 1])[:, None]
    lat2 = np.radians(source[:, 0])[None, :]
    lon2 = np.radians(source[:, 1])[None, :]
    a = np.sin((lat2 - lat1) / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    distances = 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return distances.min(axis=1) / 1000.0


def spatial_block_recovery_validation(
    occurrences: pd.DataFrame,
    candidate_builder: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    block_degrees: float = 0.25,
    repeats: int = 10,
    holdout_fraction: float = 0.20,
    top_k: int = 10,
    hit_radius_km: float = 5.0,
    random_draws: int = 100,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Test whether distance-excluded candidate evidence recovers held-out occurrences.

    `candidate_builder` receives training occurrences only. It must rebuild local
    environment profiles and optional SDM support without consulting held-out
    coordinates. Known-location candidates and direct occurrence/distance-derived
    score components are removed before ranking. Random controls draw from the
    same candidate pool, controlling for its geographic and access envelope.
    """
    required = {latitude_col, longitude_col}
    missing = required.difference(occurrences.columns)
    if missing:
        raise ValueError(f"Occurrence table is missing: {', '.join(sorted(missing))}")
    work = occurrences.copy()
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if len(work) < 4:
        raise ValueError("At least four occurrence records are required for spatial recovery validation.")
    block = max(1e-6, float(block_degrees))
    work["_validation_block"] = (
        np.floor(pd.to_numeric(work[latitude_col], errors="coerce") / block).astype(int).astype(str)
        + ":"
        + np.floor(pd.to_numeric(work[longitude_col], errors="coerce") / block).astype(int).astype(str)
    )
    blocks = work["_validation_block"].drop_duplicates().to_numpy()
    if len(blocks) < 2:
        raise ValueError("Occurrences occupy fewer than two spatial blocks; reduce block_degrees or use leave-one-cluster-out validation.")
    rng = np.random.default_rng(int(random_state))
    rows: list[dict[str, Any]] = []
    n_holdout_blocks = min(len(blocks) - 1, max(1, int(round(len(blocks) * float(holdout_fraction)))))
    for repeat in range(1, max(1, int(repeats)) + 1):
        held_blocks = set(rng.choice(blocks, size=n_holdout_blocks, replace=False).tolist())
        heldout = work[work["_validation_block"].isin(held_blocks)].copy()
        training = work[~work["_validation_block"].isin(held_blocks)].drop(columns="_validation_block").copy()
        candidates = candidate_builder(training)
        if candidates is None or candidates.empty:
            rows.append({"repeat": repeat, "status": "no_candidates", "training_records": len(training), "heldout_records": len(heldout)})
            continue
        candidates = candidates.dropna(subset=["latitude", "longitude"]).copy().reset_index(drop=True)
        candidate_type = candidates.get("candidate_type", pd.Series("", index=candidates.index)).astype(str)
        candidates = candidates[
            ~candidate_type.str.contains("occurrence-supported|known-location|known anchor", case=False, na=False)
        ].reset_index(drop=True)
        scored = integrated_candidate_scores(candidates, exclude_occurrence_derived=True)
        scored = scored.sort_values("integrated_support_score", ascending=False, kind="mergesort").reset_index(drop=True)
        selected = scored.head(min(max(1, int(top_k)), len(scored)))
        if selected.empty:
            rows.append({"repeat": repeat, "status": "no_distance_free_candidates", "training_records": len(training), "heldout_records": len(heldout)})
            continue
        held_coords = heldout[[latitude_col, longitude_col]].to_numpy(dtype=float)
        selected_coords = selected[["latitude", "longitude"]].to_numpy(dtype=float)
        nearest = _nearest_distances_km(selected_coords, held_coords)
        model_recall = float(np.mean(nearest <= float(hit_radius_km)))
        random_recalls = []
        random_medians = []
        random_k = len(selected)
        pool_coords = scored[["latitude", "longitude"]].to_numpy(dtype=float)
        for _ in range(max(1, int(random_draws))):
            indices = rng.choice(len(pool_coords), size=random_k, replace=False)
            random_nearest = _nearest_distances_km(pool_coords[indices], held_coords)
            random_recalls.append(float(np.mean(random_nearest <= float(hit_radius_km))))
            random_medians.append(float(np.median(random_nearest)))
        random_recall = float(np.mean(random_recalls))
        rows.append({
            "repeat": repeat,
            "status": "ok",
            "heldout_blocks": ";".join(sorted(held_blocks)),
            "training_records": int(len(training)),
            "heldout_records": int(len(heldout)),
            "candidate_pool": int(len(scored)),
            "top_k": int(len(selected)),
            "hit_radius_km": float(hit_radius_km),
            "distance_excluded_recall": round(model_recall, 6),
            "random_same_pool_recall": round(random_recall, 6),
            "recall_lift_over_random": round(model_recall - random_recall, 6),
            "median_nearest_candidate_km": round(float(np.median(nearest)), 6),
            "random_median_nearest_km": round(float(np.mean(random_medians)), 6),
        })
    folds = pd.DataFrame(rows)
    valid = folds[folds.get("status", pd.Series(dtype=str)).eq("ok")]
    summary = {
        "validation_design": "repeated random spatial-block holdout; candidate builder receives training records only",
        "distance_excluded_components": "observed support, known-location candidates, survey-gap, environmental novelty, and distance-to-known evidence",
        "valid_repeats": int(len(valid)),
        "mean_distance_excluded_recall": None if valid.empty else round(float(valid["distance_excluded_recall"].mean()), 6),
        "mean_random_same_pool_recall": None if valid.empty else round(float(valid["random_same_pool_recall"].mean()), 6),
        "mean_recall_lift_over_random": None if valid.empty else round(float(valid["recall_lift_over_random"].mean()), 6),
        "random_state": int(random_state),
    }
    return folds, summary
