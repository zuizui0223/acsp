from __future__ import annotations

import pandas as pd

import research.build_cirsium_fresh_sentinel_v2_coarse_to_fine_seeds as mod


def _outer() -> pd.DataFrame:
    return pd.DataFrame({
        "candidate_cell_id": ["a", "b", "c", "d", "e", "f"],
        "latitude": [35.0, 35.01, 35.10, 36.0, 36.01, 36.10],
        "longitude": [139.0, 139.01, 139.10, 140.0, 140.01, 140.10],
        "regional_tile_id": ["t1", "t1", "t1", "t2", "t2", "t2"],
    })


def _order() -> pd.DataFrame:
    return pd.DataFrame({
        "candidate_cell_id": ["a", "b", "c", "d", "e", "f"],
        "source_state": [
            mod.READY, mod.READY, mod.READY,
            mod.INDETERMINATE, mod.INDETERMINATE, mod.INDETERMINATE,
        ],
        "coarse_evidence_rank": pd.array([1, 2, 3, pd.NA, pd.NA, pd.NA], dtype="Int64"),
    })


def test_ready_lane_respects_coarse_order_and_covers_all() -> None:
    seeds, summary = mod.build_unit_seed_plan(_order(), _outer(), "CIR02", radius_km=5.0)
    ready = seeds.loc[seeds["seed_lane"].eq("SOURCE_READY_COARSE_ORDER_COVER")]
    assert ready["candidate_cell_id"].tolist()[0] == "a"
    assert summary["source_ready_coverage_complete"] is True
    assert summary["top_k_used"] is False
    assert summary["score_threshold_used"] is False
    assert summary["budget_used"] is False


def test_indeterminate_lane_is_separate_geometry_only_cover() -> None:
    seeds, summary = mod.build_unit_seed_plan(_order(), _outer(), "CIR12", radius_km=5.0)
    ind = seeds.loc[seeds["seed_lane"].eq("SOURCE_INDETERMINATE_GEOMETRY_ONLY_COVER")]
    assert len(ind) >= 1
    assert ind["coarse_evidence_rank"].isna().all()
    assert summary["source_indeterminate_coverage_complete"] is True
    assert summary["cross_lane_coverage_used"] is False
    assert summary["source_indeterminate_ecological_rank_used"] is False


def test_no_candidate_is_dropped_from_lane_coverage_semantics() -> None:
    _, summary = mod.build_unit_seed_plan(_order(), _outer(), "CIR06", radius_km=5.0)
    assert summary["source_ready_candidate_count"] == 3
    assert summary["source_indeterminate_candidate_count"] == 3
    assert summary["candidate_rows_dropped"] == 0
    assert summary["source_ready_seed_count"] <= 3
    assert summary["source_indeterminate_seed_count"] <= 3
