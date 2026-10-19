from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import research.build_cirsium_fresh_sentinel_v2_fine_structural_order as mod


def _gsi(unit: str, *, one_indeterminate: bool = False) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "cohort_unit_id": [unit] * 4,
            "candidate_cell_id": [f"{unit}-{x}" for x in "abcd"],
            "grid_row": [0, 0, 1, 1],
            "grid_col": [0, 1, 0, 1],
            "latitude": [35.0, 35.0, 35.001, 35.001],
            "longitude": [139.0, 139.001, 139.0, 139.001],
            "gsi_source_state": ["SOURCE_COMPLETE"] * 4,
            "elev": [100.0, 120.0, 150.0, 180.0],
            "slope100": [2.0, 3.0, 4.0, 5.0],
            "tpi300": [-2.0, -1.0, 1.0, 2.0],
            "rough300": [0.5, 0.7, 1.0, 1.2],
        }
    )
    if one_indeterminate:
        frame.loc[3, "gsi_source_state"] = "INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE"
        frame.loc[3, list(mod.TERRAIN_COLUMNS)] = np.nan
    return frame


def _wc(unit: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_cell_id": [f"{unit}-{x}" for x in "abcd"],
            "worldcover_source_state": ["SOURCE_COMPLETE"] * 4,
            "wc_tree_frac_250m": [0.1, 0.2, 0.1, 0.2],
            "wc_grass_frac_250m": [0.7, 0.6, 0.8, 0.7],
            "wc_bare_frac_250m": [0.0, 0.0, 0.0, 0.0],
            "wc_water_frac_250m": [0.1, 0.1, 0.0, 0.0],
            "wc_wetland_frac_250m": [0.1, 0.1, 0.1, 0.1],
            "wc_edge_mix_250m": [0.4, 0.5, 0.3, 0.4],
        }
    )


def test_alpine_full_order_is_complete_and_has_no_stopping_rule() -> None:
    ordered, summary = mod.build_fine_structural_order(_gsi("CIR06"), unit_id="CIR06")
    assert len(ordered) == 4
    assert ordered["structural_rank"].tolist() == [1, 2, 3, 4]
    assert ordered["structural_support"].between(0.0, 1.0).all()
    assert summary["feature_family"] == "ALPINE_TOPOGRAPHIC_STRUCTURE"
    assert summary["source_complete_rows"] == 4
    assert summary["source_indeterminate_rows"] == 0
    assert summary["top_k_applied"] is False
    assert summary["support_threshold_applied"] is False
    assert summary["patch_count_applied"] is False
    assert summary["survey_budget_applied"] is False


def test_source_indeterminate_cells_remain_unranked() -> None:
    ordered, summary = mod.build_fine_structural_order(
        _gsi("CIR02", one_indeterminate=True),
        unit_id="CIR02",
        worldcover_frame=_wc("CIR02"),
    )
    assert len(ordered) == 3
    assert "CIR02-d" not in set(ordered["candidate_cell_id"])
    assert summary["candidate_rows"] == 4
    assert summary["source_complete_rows"] == 3
    assert summary["source_indeterminate_rows"] == 1
    assert summary["source_indeterminate_ranked"] is False
    assert summary["source_indeterminate_recoded_as_absence"] is False
    assert summary["source_indeterminate_recoded_as_zero_support"] is False


def test_worldcover_required_for_declared_units() -> None:
    with pytest.raises(ValueError, match="requires frozen WorldCover"):
        mod.build_fine_structural_order(_gsi("CIR12"), unit_id="CIR12")


def test_cir06_rejects_undeclared_worldcover_dependency() -> None:
    with pytest.raises(ValueError, match="must not gain an undeclared WorldCover dependency"):
        mod.build_fine_structural_order(
            _gsi("CIR06"),
            unit_id="CIR06",
            worldcover_frame=_wc("CIR06"),
        )


def test_open_grassland_full_order_uses_frozen_chain() -> None:
    ordered, summary = mod.build_fine_structural_order(
        _gsi("CIR12"),
        unit_id="CIR12",
        worldcover_frame=_wc("CIR12"),
    )
    assert summary["feature_family"] == "OPEN_GRASSLAND_STRUCTURE"
    assert summary["graph_audit"]["graph_type"] == "REGULAR_GRID_MOORE_8_NEIGHBOUR"
    assert summary["graph_audit"]["neighbourhood_radius_cells"] == 1
    assert summary["support_audit"]["composition_rule"] == "ROW_MIN_CONJUNCTIVE_SUPPORT"
    assert ordered["structural_rank"].tolist() == [1, 2, 3, 4]
