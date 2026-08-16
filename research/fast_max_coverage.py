#!/usr/bin/env python3
"""Exact sparse implementation of the current greedy max-coverage selector.

This is a computational optimization only. For a fixed grid, eligibility mask,
radius and budget it implements the same objective and tie break as
`develop_izu_strong_coverage_sweep.greedy_coverage_order`: maximize the number
of newly covered public-grid cells at every step; break exact ties by the
smallest global dataframe index.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix


@dataclass
class SparseCoverageIndex:
    adjacency: csr_matrix

    @classmethod
    def from_geometry(cls, grid: pd.DataFrame, geometry: dict[str, dict], radius_km: float):
        n = len(grid)
        row_parts: list[np.ndarray] = []
        col_parts: list[np.ndarray] = []
        for island in sorted(geometry):
            geo = geometry[island]
            idx = np.asarray(geo["idx"], dtype=np.int64)
            neighborhoods = geo["tree"].query_ball_tree(geo["tree"], r=float(radius_km))
            lengths = np.fromiter((len(x) for x in neighborhoods), dtype=np.int64, count=len(idx))
            if lengths.sum() == 0:
                continue
            rows = np.repeat(idx, lengths)
            local_cols = np.concatenate(
                [np.asarray(x, dtype=np.int64) for x in neighborhoods if len(x)]
            )
            cols = idx[local_cols]
            row_parts.append(rows)
            col_parts.append(cols)
        if row_parts:
            rows = np.concatenate(row_parts)
            cols = np.concatenate(col_parts)
            data = np.ones(len(rows), dtype=np.int8)
            matrix = csr_matrix((data, (rows, cols)), shape=(n, n), dtype=np.int8)
        else:
            matrix = csr_matrix((n, n), dtype=np.int8)
        matrix.sort_indices()
        return cls(matrix)

    def select(self, grid: pd.DataFrame, eligible: np.ndarray, *, max_budget: int) -> pd.DataFrame:
        eligible = np.asarray(eligible, dtype=bool)
        if eligible.shape != (len(grid),):
            raise ValueError("eligible mask length does not match grid")

        selected_mask = np.zeros(len(grid), dtype=bool)
        covered = np.zeros(len(grid), dtype=bool)
        selected: list[int] = []
        limit = min(int(max_budget), int(eligible.sum()))

        # At step zero every candidate's gain is simply its neighbourhood size.
        # Later steps update only for cells that have just become covered. This
        # is algebraically identical to recomputing A @ (~covered) every step,
        # but avoids scanning the whole sparse graph repeatedly.
        gains = np.diff(self.adjacency.indptr).astype(np.int32, copy=True)

        for _ in range(limit):
            valid = eligible & ~selected_mask
            if not valid.any():
                break
            scores = gains.copy()
            scores[~valid] = -1
            best_gain = int(scores.max())
            # np.flatnonzero is index ordered, preserving the reference global
            # dataframe-index tie break exactly.
            best = int(np.flatnonzero(scores == best_gain)[0])
            selected.append(best)
            selected_mask[best] = True

            start = self.adjacency.indptr[best]
            stop = self.adjacency.indptr[best + 1]
            neighbours = self.adjacency.indices[start:stop]
            newly_covered = neighbours[~covered[neighbours]]
            if len(newly_covered):
                covered[newly_covered] = True
                # The neighbourhood graph is symmetric. For each newly covered
                # cell, subtract one from every candidate whose footprint
                # contains that cell. Sparse row summation counts those losses.
                decrement = np.asarray(
                    self.adjacency[newly_covered].sum(axis=0)
                ).ravel().astype(np.int32, copy=False)
                gains -= decrement

        return grid.iloc[selected].copy().reset_index(drop=True)


_CACHE: dict[tuple[int, int, float], SparseCoverageIndex] = {}


def greedy_coverage_order_fast(
    grid: pd.DataFrame,
    geometry: dict[str, dict],
    eligible: np.ndarray,
    *,
    max_budget: int,
    radius_km: float,
) -> pd.DataFrame:
    """API-compatible exact replacement for the reference greedy selector."""
    key = (id(grid), len(grid), float(radius_km))
    index = _CACHE.get(key)
    if index is None:
        index = SparseCoverageIndex.from_geometry(grid, geometry, float(radius_km))
        _CACHE.clear()
        _CACHE[key] = index
    return index.select(grid, eligible, max_budget=max_budget)
