"""Taxon-agnostic robust ecological-support and candidate-patch utilities.

This module intentionally stops at candidate generation. It does not optimize
routes, field days, budgets, or movement modes. The core object is a robust
occurrence-conditioned support envelope reconstructed from training occurrence
prototypes and environmental features, then aggregated into bounded same-area
survey patches.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Sequence

import numpy as np
import pandas as pd


EARTH_RADIUS_M = 6_371_008.8


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


def _haversine_m(
    latitude: float,
    longitude: float,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
) -> np.ndarray:
    """Vectorised great-circle distances from one point in metres."""
    lat1 = math.radians(float(latitude))
    lon1 = math.radians(float(longitude))
    lat2 = np.radians(np.asarray(latitudes, dtype=float))
    lon2 = np.radians(np.asarray(longitudes, dtype=float))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + math.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _safe_area_token(area: object) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", str(area)).strip("-")
    return token or "1"


def _complete_link_support_patches(
    selected: pd.DataFrame,
    *,
    merge_distance_m: float,
    latitude_col: str,
    longitude_col: str,
    area_col: str,
) -> pd.DataFrame:
    """Aggregate support cells without invoking the historical planner stack.

    Group membership reproduces the earlier deterministic complete-link rule:
    cells are processed in universe-index order and join the compatible patch
    with the smallest resulting maximum pairwise distance. The representative
    point is the member with the strongest ecological support (lowest support
    rank), with site id as deterministic tie-breaker.
    """
    if selected.empty:
        return pd.DataFrame()
    threshold = float(merge_distance_m)
    if threshold <= 0:
        raise ValueError("merge_distance_m must be positive")

    work = selected.copy().reset_index(drop=True)
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if work.empty:
        return pd.DataFrame()

    patch_members: list[tuple[object, int, list[int]]] = []
    for area, group in work.groupby(area_col, sort=True, dropna=False):
        ordered = group.assign(
            _stable_numeric=pd.to_numeric(group["site_id"], errors="coerce"),
            _stable_id=group["site_id"].astype(str),
        ).sort_values(
            ["_stable_numeric", "_stable_id", latitude_col, longitude_col],
            kind="mergesort",
            na_position="last",
        )
        area_patches: list[list[int]] = []
        for index in ordered.index:
            compatible: list[tuple[float, int]] = []
            for patch_index, member_indices in enumerate(area_patches):
                members = work.loc[member_indices]
                distances = _haversine_m(
                    work.at[index, latitude_col],
                    work.at[index, longitude_col],
                    members[latitude_col].to_numpy(float),
                    members[longitude_col].to_numpy(float),
                )
                maximum = float(distances.max()) if len(distances) else 0.0
                if maximum <= threshold:
                    compatible.append((maximum, patch_index))
            if compatible:
                patch_index = min(compatible)[1]
                area_patches[patch_index].append(index)
            else:
                area_patches.append([index])
        for patch_number, indices in enumerate(area_patches, start=1):
            patch_members.append((area, patch_number, indices))

    rows: list[dict[str, object]] = []
    for area, patch_number, indices in patch_members:
        members = work.loc[indices].copy()
        representative = members.assign(
            _support_rank=pd.to_numeric(members["ecological_support_rank"], errors="coerce"),
            _stable_id=members["site_id"].astype(str),
        ).sort_values(
            ["_support_rank", "_stable_id", latitude_col, longitude_col],
            kind="mergesort",
            na_position="last",
        ).iloc[0]
        distances = _haversine_m(
            representative[latitude_col],
            representative[longitude_col],
            members[latitude_col].to_numpy(float),
            members[longitude_col].to_numpy(float),
        )
        zone_id = f"{_safe_area_token(area)}-Z{patch_number:03d}"
        rows.append(
            {
                "zone_id": zone_id,
                area_col: area,
                "zone_member_count": int(len(members)),
                "zone_radius_m": round(float(distances.max()) if len(distances) else 0.0, 1),
                "zone_merge_threshold_m": round(threshold, 1),
                "representative_site_id": str(representative["site_id"]),
                "latitude": float(representative[latitude_col]),
                "longitude": float(representative[longitude_col]),
                "zone_member_site_ids": ";".join(members["site_id"].astype(str).tolist()),
            }
        )
    zones = pd.DataFrame(rows)
    if zones.empty:
        return zones
    zones["_neutral_area_sort"] = zones[area_col].astype(str)
    return zones.sort_values(
        ["_neutral_area_sort", "zone_id"],
        kind="mergesort",
    ).drop(columns="_neutral_area_sort").reset_index(drop=True)


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
    selected["ecological_support_rank"] = ranks[keep]
    if selected.empty:
        return selected.reset_index(drop=True), pd.DataFrame()

    zones = _complete_link_support_patches(
        selected,
        merge_distance_m=float(merge_distance_m),
        area_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )
    zones = zones.copy()
    zones["ecological_support_threshold"] = float(threshold)
    zones["ecological_status"] = str(ecological_status)
    zones["site_id"] = zones["zone_id"].astype(str)
    return selected.reset_index(drop=True), zones.reset_index(drop=True)
