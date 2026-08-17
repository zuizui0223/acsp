"""Deterministic set-level survey coverage primitives.

This module is intentionally ecology-free. It selects a finite set of survey
stops that maximizes newly covered candidate points under a declared search
radius. Ecological evidence belongs upstream (for example regional ACSP
screening); route/time constraints belong downstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.neighbors import BallTree

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class CoverageSelectionAudit:
    candidate_count: int
    selected_count: int
    radius_km: float
    final_coverage_fraction: float
    group_column: Optional[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "radius_km": self.radius_km,
            "final_coverage_fraction": self.final_coverage_fraction,
            "group_column": self.group_column,
        }


def _coverage_adjacency(
    candidates: pd.DataFrame,
    *,
    radius_km: float,
    latitude_col: str,
    longitude_col: str,
    group_col: str | None,
) -> csr_matrix:
    if radius_km <= 0:
        raise ValueError("radius_km must be positive")
    if latitude_col not in candidates.columns or longitude_col not in candidates.columns:
        raise ValueError("candidate table lacks latitude/longitude columns")
    if group_col is not None and group_col not in candidates.columns:
        raise ValueError(f"candidate table lacks group column {group_col!r}")

    n = len(candidates)
    rows_all: list[np.ndarray] = []
    cols_all: list[np.ndarray] = []
    if group_col is None:
        groups = [(None, np.arange(n, dtype=np.int64))]
    else:
        groups = [
            (key, np.asarray(index, dtype=np.int64))
            for key, index in candidates.groupby(group_col, sort=False).indices.items()
        ]

    angular_radius = float(radius_km) / EARTH_RADIUS_KM
    for _group, idx in groups:
        if len(idx) == 0:
            continue
        coords = np.radians(
            candidates.iloc[idx][[latitude_col, longitude_col]].to_numpy(float)
        )
        if not np.isfinite(coords).all():
            raise ValueError("candidate coordinates must be finite")
        tree = BallTree(coords, metric="haversine")
        neighbourhoods = tree.query_radius(coords, r=angular_radius, return_distance=False)
        lengths = np.fromiter((len(x) for x in neighbourhoods), dtype=np.int64, count=len(idx))
        if int(lengths.sum()) == 0:
            continue
        rows = np.repeat(idx, lengths)
        local_cols = np.concatenate([np.asarray(x, dtype=np.int64) for x in neighbourhoods])
        cols = idx[local_cols]
        rows_all.append(rows)
        cols_all.append(cols)

    if rows_all:
        rows = np.concatenate(rows_all)
        cols = np.concatenate(cols_all)
        data = np.ones(len(rows), dtype=np.int8)
        matrix = csr_matrix((data, (rows, cols)), shape=(n, n), dtype=np.int8)
    else:
        matrix = csr_matrix((n, n), dtype=np.int8)
    matrix.sort_indices()
    return matrix


def select_maximum_coverage_sites(
    candidates: pd.DataFrame,
    *,
    radius_km: float,
    max_sites: int,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    group_col: str | None = None,
) -> tuple[pd.DataFrame, CoverageSelectionAudit]:
    """Greedily select stops that maximize newly covered candidate points.

    The objective is set-level geographic coverage, not biological suitability.
    Exact ties are resolved by the original row order, making the selector
    deterministic for a fixed input table. If ``group_col`` is supplied,
    coverage never crosses group boundaries (for example between islands or
    disconnected survey areas).
    """
    if int(max_sites) < 0:
        raise ValueError("max_sites must be non-negative")
    work = candidates.reset_index(drop=False).rename(columns={"index": "_input_index"}).copy()
    n = len(work)
    if n == 0 or int(max_sites) == 0:
        empty = work.iloc[0:0].copy()
        empty["coverage_rank"] = pd.Series(dtype="int64")
        empty["marginal_covered_candidates"] = pd.Series(dtype="int64")
        empty["cumulative_coverage_fraction"] = pd.Series(dtype="float64")
        return empty, CoverageSelectionAudit(n, 0, float(radius_km), 0.0, group_col)

    adjacency = _coverage_adjacency(
        work,
        radius_km=float(radius_km),
        latitude_col=latitude_col,
        longitude_col=longitude_col,
        group_col=group_col,
    )
    selected_mask = np.zeros(n, dtype=bool)
    covered = np.zeros(n, dtype=bool)
    gains = np.diff(adjacency.indptr).astype(np.int32, copy=True)
    selected: list[int] = []
    marginal: list[int] = []
    cumulative: list[float] = []

    for _ in range(min(int(max_sites), n)):
        scores = gains.copy()
        scores[selected_mask] = -1
        best_gain = int(scores.max())
        best = int(np.flatnonzero(scores == best_gain)[0])
        selected.append(best)
        selected_mask[best] = True

        start = adjacency.indptr[best]
        stop = adjacency.indptr[best + 1]
        neighbours = adjacency.indices[start:stop]
        newly_covered = neighbours[~covered[neighbours]]
        marginal.append(int(len(newly_covered)))
        if len(newly_covered):
            covered[newly_covered] = True
            decrement = np.asarray(adjacency[newly_covered].sum(axis=0)).ravel().astype(np.int32, copy=False)
            gains -= decrement
        cumulative.append(float(covered.mean()))

    out = work.iloc[selected].copy().reset_index(drop=True)
    out["coverage_rank"] = np.arange(1, len(out) + 1, dtype=int)
    out["marginal_covered_candidates"] = marginal
    out["cumulative_coverage_fraction"] = cumulative
    audit = CoverageSelectionAudit(
        candidate_count=n,
        selected_count=len(out),
        radius_km=float(radius_km),
        final_coverage_fraction=float(cumulative[-1]) if cumulative else 0.0,
        group_column=group_col,
    )
    return out, audit
