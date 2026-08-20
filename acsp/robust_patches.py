"""Taxon-agnostic robust ecological-support and candidate-patch utilities.

This module intentionally stops at candidate generation. It does not optimize
routes, field days, budgets, or movement modes. The core object is a robust
occurrence-conditioned support envelope reconstructed from training occurrence
prototypes and environmental features, then aggregated into bounded same-area
survey patches.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from .planning import aggregate_candidates_to_zones


@dataclass(frozen=True)
class RobustSupportAudit:
    prototype_count: int
    leave_one_out_worlds: int
    feature_columns: tuple[str, ...]
    kernel_scale_min: float
    kernel_scale_max: float
    support_world_dtype: str

    def as_dict(self) -> dict[str, object]:
        return {
            "prototype_count": self.prototype_count,
            "leave_one_out_worlds": self.leave_one_out_worlds,
            "feature_columns": list(self.feature_columns),
            "kernel_scale_min": self.kernel_scale_min,
            "kernel_scale_max": self.kernel_scale_max,
            "support_world_dtype": self.support_world_dtype,
        }


def _feature_matrix(frame: pd.DataFrame, feature_columns: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    columns = tuple(str(column) for column in feature_columns)
    if not columns:
        raise ValueError("feature_columns must contain at least one environmental feature")
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError("missing environmental features: " + ", ".join(sorted(missing)))
    values = frame.loc[:, columns].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    valid = np.isfinite(values).all(axis=1)
    return values, valid


def _complete_prototypes(prototypes: pd.DataFrame, feature_columns: Sequence[str]) -> pd.DataFrame:
    _, valid = _feature_matrix(prototypes, feature_columns)
    complete = prototypes.loc[valid].copy().reset_index(drop=True)
    if len(complete) < 1:
        raise ValueError("no prototypes have complete environmental features")
    return complete


def robust_environment_geometry(
    universe: pd.DataFrame,
    prototypes: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    min_kernel_scale: float = 0.25,
    chunk_size: int = 3000,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame, float]:
    """Return prototype responsibilities and percentile-ranked nearest distance.

    Environmental features are centered by the prototype median and scaled by
    prototype IQR. Candidate support is therefore defined relative to the
    environmental geometry occupied by training occurrences, without fitting a
    presence/absence classifier or calibrated suitability probability.
    """
    if float(min_kernel_scale) <= 0:
        raise ValueError("min_kernel_scale must be positive")
    if int(chunk_size) < 1:
        raise ValueError("chunk_size must be positive")

    universe_values, universe_valid = _feature_matrix(universe, feature_columns)
    prototype_complete = _complete_prototypes(prototypes, feature_columns)
    prototype_values, _ = _feature_matrix(prototype_complete, feature_columns)
    median = np.nanmedian(prototype_values, axis=0)
    q1 = np.nanquantile(prototype_values, 0.25, axis=0)
    q3 = np.nanquantile(prototype_values, 0.75, axis=0)
    scale = np.where((q3 - q1) > 1e-9, q3 - q1, 1.0)
    prototype_z = (prototype_values - median) / scale

    if len(prototype_z) > 1:
        pairwise = np.sqrt(
            np.square(prototype_z[:, None, :] - prototype_z[None, :, :]).sum(axis=2)
        )
        np.fill_diagonal(pairwise, np.inf)
        kernel_scale = float(np.median(np.min(pairwise, axis=1)))
    else:
        kernel_scale = 1.0
    kernel_scale = max(float(kernel_scale), float(min_kernel_scale))

    valid_indices = np.flatnonzero(universe_valid)
    distances = np.full((len(universe), len(prototype_z)), np.inf, dtype=float)
    if len(valid_indices):
        universe_z = (universe_values[valid_indices] - median) / scale
        for start in range(0, len(universe_z), int(chunk_size)):
            block = universe_z[start : start + int(chunk_size)]
            d2 = np.square(block[:, None, :] - prototype_z[None, :, :]).sum(axis=2)
            distances[valid_indices[start : start + len(block)]] = np.sqrt(d2)

    responsibility = np.exp(-0.5 * np.square(distances / kernel_scale))
    responsibility[~np.isfinite(responsibility)] = 0.0
    nearest = np.min(distances, axis=1)
    support_rank = pd.Series(nearest).rank(method="average", pct=True).to_numpy(float)
    return responsibility, support_rank, prototype_complete, kernel_scale


def leave_one_out_consensus_support(
    universe: pd.DataFrame,
    prototypes: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    support_world_dtype: str = "float32",
    min_kernel_scale: float = 0.25,
    chunk_size: int = 3000,
) -> tuple[np.ndarray, np.ndarray, RobustSupportAudit]:
    """Reconstruct a leave-one-prototype-out consensus support rank surface."""
    complete = _complete_prototypes(prototypes, feature_columns)
    if len(complete) < 2:
        raise ValueError("at least two complete prototypes are required for leave-one-out support")
    ranks: list[np.ndarray] = []
    kernel_scales: list[float] = []
    for removed in range(len(complete)):
        subset = complete.drop(index=complete.index[removed]).reset_index(drop=True)
        _, support_rank, _, kernel_scale = robust_environment_geometry(
            universe,
            subset,
            feature_columns=feature_columns,
            min_kernel_scale=min_kernel_scale,
            chunk_size=chunk_size,
        )
        ranks.append(np.asarray(support_rank).astype(support_world_dtype, copy=False))
        kernel_scales.append(float(kernel_scale))
    stack = np.vstack(ranks)
    consensus = np.median(stack, axis=0)
    uncertainty = np.std(stack, axis=0)
    audit = RobustSupportAudit(
        prototype_count=int(len(complete)),
        leave_one_out_worlds=int(len(ranks)),
        feature_columns=tuple(str(column) for column in feature_columns),
        kernel_scale_min=float(np.min(kernel_scales)),
        kernel_scale_max=float(np.max(kernel_scales)),
        support_world_dtype=str(np.dtype(support_world_dtype)),
    )
    return consensus, uncertainty, audit


def support_cells_to_patches(
    universe: pd.DataFrame,
    support_rank: np.ndarray,
    *,
    threshold: float,
    threshold_tolerance: float = 0.0,
    merge_distance_m: float = 1000.0,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    area_col: str = "survey_area_id",
    ecological_status: str = "robust_support_patch",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Threshold support ranks and aggregate selected cells into bounded patches."""
    ranks = np.asarray(support_rank, dtype=float)
    if len(ranks) != len(universe):
        raise ValueError("support_rank length must match universe rows")
    required = {latitude_col, longitude_col, area_col}
    missing = required - set(universe.columns)
    if missing:
        raise ValueError("candidate universe lacks required columns: " + ", ".join(sorted(missing)))
    cutoff = float(threshold) + float(threshold_tolerance)
    keep = np.isfinite(ranks) & (ranks <= cutoff)
    selected = universe.loc[keep].copy()
    selected["universe_index"] = np.flatnonzero(keep)
    selected["site_id"] = selected["universe_index"].astype(str)
    selected["priority_score"] = 1.0 - ranks[keep]
    selected["candidate_type"] = "robust ecological support cell"
    selected["access_score"] = 0.5
    selected["evidence_agreement_score"] = 0.0
    selected["ecological_support_rank"] = ranks[keep]
    if selected.empty:
        return selected.reset_index(drop=True), pd.DataFrame()

    zones = aggregate_candidates_to_zones(
        selected,
        merge_distance_m=float(merge_distance_m),
        area_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
        id_col="site_id",
        score_col="priority_score",
    )
    zones = zones.copy()
    zones["ecological_support_threshold"] = float(threshold)
    zones["ecological_status"] = str(ecological_status)
    zones["site_id"] = zones["zone_id"].astype(str)
    return selected.reset_index(drop=True), zones.reset_index(drop=True)
