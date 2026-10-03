from __future__ import annotations

import pandas as pd

import research.smoke_cirsium_fresh_sentinel_v2_cir06_fine_terrain as mod


def test_retrieval_margin_is_derived_from_existing_terrain_surface() -> None:
    assert mod.derived_retrieval_margin_m() == 175.0


def test_rank1_core_grid_is_exact_frozen_size() -> None:
    grid = mod.build_core_grid(
        36.395756807601344,
        137.59768511286327,
    )
    assert len(grid) == 7860
    assert not grid[["grid_row", "grid_col"]].duplicated().any()
    assert grid["candidate_cell_id"].is_unique


def test_retrieval_bounds_include_center_and_margin() -> None:
    lat = 36.395756807601344
    lon = 137.59768511286327
    west, south, east, north = mod.padded_retrieval_bounds(lat, lon)
    assert west < lon < east
    assert south < lat < north
    assert mod.derived_retrieval_margin_m() > 150.0
