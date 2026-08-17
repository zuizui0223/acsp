#!/usr/bin/env python3
"""Local prototype-agreement support scales for ACSP development.

The current support score uses distance to the single nearest training
prototype. This module generalizes that representation to the mean distance to
k nearest prototypes while keeping the public-grid support area fixed to the
existing k=1 q mask. Thus k changes required local environmental agreement, not
survey footprint.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from campanula_ndvi_microclimate_hybrid import fit_distance_rank
from campanula_worldcover_discovery import robust_fit, transform


@dataclass
class LocalScaleFamily:
    k1_rank: np.ndarray
    distance_by_k: dict[int, np.ndarray]
    n_grid: int

    @classmethod
    def build(
        cls,
        grid_features: pd.DataFrame,
        train_features: pd.DataFrame,
        columns: list[str],
        neighbour_counts: list[int],
    ) -> "LocalScaleFamily":
        ks = sorted(set(int(k) for k in neighbour_counts))
        if not ks or ks[0] < 1:
            raise ValueError("neighbour_counts must contain positive integers")

        good_p = train_features[columns].notna().all(axis=1).to_numpy()
        good_g = grid_features[columns].notna().all(axis=1).to_numpy()
        if int(good_p.sum()) < max(ks):
            raise ValueError("not enough complete training prototypes for requested k")

        # k=1 rank is delegated to the historical implementation so the control
        # support mask is exactly identical to the current representation.
        _, k1_rank = fit_distance_rank(grid_features, train_features, columns)

        p = train_features.loc[good_p, columns].to_numpy(float)
        median, scale = robust_fit(p)
        pz = transform(p, median, scale)
        gz = transform(grid_features.loc[good_g, columns].to_numpy(float), median, scale)
        tree = cKDTree(pz)
        max_k = max(ks)
        queried = tree.query(gz, k=max_k)[0]
        if max_k == 1:
            queried = queried[:, None]

        distance_by_k: dict[int, np.ndarray] = {}
        for k in ks:
            full = np.full(len(grid_features), np.inf, dtype=float)
            full[good_g] = np.mean(queried[:, :k], axis=1)
            distance_by_k[k] = full
        return cls(np.asarray(k1_rank, dtype=float), distance_by_k, len(grid_features))

    def target_count(self, q: float) -> int:
        q = float(q)
        if q >= 1.0:
            return self.n_grid
        return int(np.sum(self.k1_rank <= q + 1e-12))

    def mask(self, k: int, q: float) -> np.ndarray:
        k = int(k)
        q = float(q)
        if k not in self.distance_by_k:
            raise KeyError(k)
        if not 0.0 < q <= 1.0:
            raise ValueError("q must lie in (0,1]")
        if q >= 1.0:
            return np.ones(self.n_grid, dtype=bool)
        target = self.target_count(q)
        if k == 1:
            # Exact historical identity, including any percentile ties.
            return self.k1_rank <= q + 1e-12
        distance = self.distance_by_k[k]
        finite = np.isfinite(distance)
        if int(finite.sum()) < target:
            raise RuntimeError("not enough finite grid cells to match k1 support area")
        indices = np.arange(self.n_grid, dtype=int)
        order = np.lexsort((indices, distance))
        chosen = order[:target]
        mask = np.zeros(self.n_grid, dtype=bool)
        mask[chosen] = True
        return mask

    def detail(self, k: int, q: float) -> dict:
        mask = self.mask(k, q)
        return {
            "prototype_neighbours": int(k),
            "support_quantile": float(q),
            "support_cells": int(mask.sum()),
            "k1_target_cells": int(self.target_count(q)),
        }
