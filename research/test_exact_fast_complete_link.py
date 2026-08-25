#!/usr/bin/env python3
"""Outcome-free equivalence tests for research-only exact complete-link acceleration."""
from __future__ import annotations

import numpy as np
import pandas as pd

from acsp.robust_patches import _complete_link_support_patches, support_cells_to_patches
from exact_fast_complete_link import exact_fast_complete_link_support_patches, exact_fast_support_cells_to_patches


def _assert_frame_equal(left: pd.DataFrame, right: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(
        left.reset_index(drop=True),
        right.reset_index(drop=True),
        check_dtype=True,
        check_exact=True,
    )


def _selected(seed: int, isolated: int, clustered: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    lat = list(rng.uniform(-80.0, 80.0, isolated))
    lon = list(rng.uniform(-180.0, 180.0, isolated))
    # Dense ordinary cluster.
    lat.extend((35.0 + rng.normal(0.0, 0.002, clustered)).tolist())
    lon.extend((139.0 + rng.normal(0.0, 0.002, clustered)).tolist())
    # High-latitude cluster.
    lat.extend((75.0 + rng.normal(0.0, 0.0015, clustered)).tolist())
    lon.extend((100.0 + rng.normal(0.0, 0.006, clustered)).tolist())
    # Dateline pair of clusters; haversine periodicity must be retained.
    lat.extend((50.0 + rng.normal(0.0, 0.0015, clustered)).tolist())
    lon.extend((179.999 + rng.normal(0.0, 0.002, clustered)).tolist())
    lat.extend((50.0 + rng.normal(0.0, 0.0015, clustered)).tolist())
    lon.extend((-179.999 + rng.normal(0.0, 0.002, clustered)).tolist())
    n = len(lat)
    return pd.DataFrame({
        "site_id": np.arange(n).astype(str),
        "latitude": lat,
        "longitude": lon,
        "survey_area_id": np.where(np.arange(n) % 7 == 0, "country-B", "country-A"),
        "ecological_support_rank": rng.random(n),
    })


def test_exact_fast_complete_link_matches_frozen() -> None:
    for seed, isolated, clustered in ((1, 10, 5), (2, 100, 10), (3, 500, 20)):
        selected = _selected(seed, isolated, clustered)
        frozen = _complete_link_support_patches(
            selected,
            merge_distance_m=1000.0,
            latitude_col="latitude",
            longitude_col="longitude",
            area_col="survey_area_id",
        )
        fast = exact_fast_complete_link_support_patches(
            selected,
            merge_distance_m=1000.0,
            latitude_col="latitude",
            longitude_col="longitude",
            area_col="survey_area_id",
        )
        _assert_frame_equal(frozen, fast)


def test_exact_fast_support_projection_matches_frozen() -> None:
    rng = np.random.default_rng(20260825)
    n = 1500
    universe = pd.DataFrame({
        "latitude": rng.uniform(-80.0, 80.0, n),
        "longitude": rng.uniform(-180.0, 180.0, n),
        "survey_area_id": np.where(np.arange(n) % 11 == 0, "country-B", "country-A"),
    })
    # Force local clusters and dateline points into the 2.5% tier.
    universe.loc[:19, "latitude"] = 35.0 + rng.normal(0, 0.002, 20)
    universe.loc[:19, "longitude"] = 139.0 + rng.normal(0, 0.002, 20)
    universe.loc[20:29, "latitude"] = 70.0 + rng.normal(0, 0.001, 10)
    universe.loc[20:24, "longitude"] = 179.999 + rng.normal(0, 0.001, 5)
    universe.loc[25:29, "longitude"] = -179.999 + rng.normal(0, 0.001, 5)
    ranks = rng.random(n)
    ranks[:30] = np.linspace(1e-6, 0.02, 30)
    frozen_cells, frozen_zones = support_cells_to_patches(
        universe, ranks, threshold=0.025, merge_distance_m=1000.0
    )
    fast_cells, fast_zones = exact_fast_support_cells_to_patches(
        universe, ranks, threshold=0.025, merge_distance_m=1000.0
    )
    _assert_frame_equal(frozen_cells, fast_cells)
    _assert_frame_equal(frozen_zones, fast_zones)


if __name__ == "__main__":
    test_exact_fast_complete_link_matches_frozen()
    test_exact_fast_support_projection_matches_frozen()
    print("exact complete-link equivalence passed")
