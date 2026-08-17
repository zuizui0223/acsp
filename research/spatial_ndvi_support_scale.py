#!/usr/bin/env python3
"""Spatial aggregation views of the existing NDVI state signal.

This module does not add a new ecological covariate family.  It compares the
same annual NDVI state at raw, ~100 m, ~250 m and the current multiscale view.
For every q<1, alternative views are forced to the exact candidate-grid support
cardinality of the current multiscale nearest-prototype q mask.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from campanula_ndvi_microclimate_hybrid import NDVI_STATE, fit_distance_rank
from campanula_ndvi_transition_discovery import (
    crop_stack,
    decode_ndvi,
    local_mean,
    ndvi_surfaces,
)


VIEW_COLUMNS = {
    "point": ["ndvi_p50", "ndvi_amp"],
    "local100": ["ndvi_mean100", "ndvi_amp_mean100"],
    "local250": ["ndvi_mean250", "ndvi_amp_mean250"],
    "current_multiscale": list(NDVI_STATE),
}
VIEW_TIE_PRIORITY = {
    "current_multiscale": 3,
    "point": 2,
    "local100": 1,
    "local250": 0,
}


def ndvi_surfaces_with_scale_views(src, lon, lat):
    """Return existing NDVI surfaces plus the symmetric 250 m amplitude mean."""
    transform, crs, surfaces = ndvi_surfaces(src, lon, lat)
    raw, extra_transform = crop_stack(src, lon, lat)
    if raw.shape[0] < 3:
        raise RuntimeError(f"NDVI composite needs 3 bands; found {raw.shape[0]}")
    # The same crop arguments are used by ndvi_surfaces(), so transforms should
    # be identical.  Fail rather than silently sampling mismatched rasters.
    if extra_transform != transform:
        raise RuntimeError("NDVI scale-view crop transform differs from base surfaces")
    p90, _, p10 = (decode_ndvi(raw[i]) for i in range(3))
    amplitude = p90 - p10
    pixel_m = abs(float(transform.a)) * 111_320.0 * math.cos(math.radians(34.5))
    size250 = max(3, int(round(500 / pixel_m)) | 1)
    amp_valid = np.isfinite(amplitude)
    surfaces = dict(surfaces)
    surfaces["ndvi_amp_mean250"] = local_mean(amplitude, amp_valid, size250)
    return transform, crs, surfaces


@dataclass
class SpatialScaleFamily:
    baseline_rank: np.ndarray
    distance_by_view: dict[str, np.ndarray]
    n_grid: int

    @classmethod
    def build(
        cls,
        grid_features: pd.DataFrame,
        train_features: pd.DataFrame,
        views: dict[str, list[str]] | None = None,
    ) -> "SpatialScaleFamily":
        views = VIEW_COLUMNS if views is None else views
        if "current_multiscale" not in views:
            raise ValueError("current_multiscale view is required as support-area control")
        _, baseline_rank = fit_distance_rank(
            grid_features, train_features, views["current_multiscale"]
        )
        distances: dict[str, np.ndarray] = {}
        for name, columns in views.items():
            distance, _ = fit_distance_rank(grid_features, train_features, columns)
            distances[str(name)] = np.asarray(distance, dtype=float)
        return cls(
            baseline_rank=np.asarray(baseline_rank, dtype=float),
            distance_by_view=distances,
            n_grid=len(grid_features),
        )

    def target_count(self, q: float) -> int:
        q = float(q)
        if q >= 1.0:
            return self.n_grid
        if not 0.0 < q < 1.0:
            raise ValueError("q must lie in (0,1]")
        return int(np.sum(self.baseline_rank <= q + 1e-12))

    def mask(self, view: str, q: float) -> np.ndarray:
        view = str(view)
        q = float(q)
        if view not in self.distance_by_view:
            raise KeyError(view)
        if not 0.0 < q <= 1.0:
            raise ValueError("q must lie in (0,1]")
        if q >= 1.0:
            return np.ones(self.n_grid, dtype=bool)

        target = self.target_count(q)
        if view == "current_multiscale":
            # Exact identity with the historical representation, including its
            # empirical percentile tie behavior.
            return self.baseline_rank <= q + 1e-12
        if target == 0:
            return np.zeros(self.n_grid, dtype=bool)

        distance = self.distance_by_view[view]
        finite = np.isfinite(distance)
        if int(finite.sum()) < target:
            raise RuntimeError(
                f"{view} has only {int(finite.sum())} finite cells for target {target}"
            )
        indices = np.arange(self.n_grid, dtype=int)
        order = np.lexsort((indices, distance))
        chosen = order[:target]
        if not np.isfinite(distance[chosen]).all():
            raise RuntimeError(f"{view} support selection reached non-finite cells")
        mask = np.zeros(self.n_grid, dtype=bool)
        mask[chosen] = True
        return mask

    def detail(self, view: str, q: float) -> dict:
        mask = self.mask(view, q)
        return {
            "scale_view": str(view),
            "support_quantile": float(q),
            "support_cells": int(mask.sum()),
            "baseline_target_cells": int(self.target_count(q)),
            "feature_count": int(len(VIEW_COLUMNS[str(view)])),
        }
