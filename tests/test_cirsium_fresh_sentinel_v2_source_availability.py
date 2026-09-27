from __future__ import annotations

import pandas as pd
import pytest

import research.compose_cirsium_fresh_sentinel_v2_source_availability as mod


def _frames():
    ids = ["a", "b", "c", "d"]
    common = {
        "candidate_cell_id": ids,
        "regional_tile_id": ["t1", "t1", "t2", "t2"],
        "latitude": [35.0, 35.1, 36.0, 36.1],
        "longitude": [139.0, 139.1, 140.0, 140.1],
    }
    terrain = pd.DataFrame({
        **common,
        "coarse_terrain_status": ["COMPLETE", "COMPLETE", "INDETERMINATE_TERRAIN_MISSING", "INDETERMINATE_TERRAIN_MISSING"],
    })
    wc = pd.DataFrame({
        **common,
        "worldcover_point_status": ["COMPLETE", "INDETERMINATE_PROVIDER_FAILURE", "COMPLETE", "INDETERMINATE_WORLDCOVER_MISSING"],
    })
    return terrain, wc


def test_source_composition_retains_indeterminate_candidates(monkeypatch) -> None:
    terrain, wc = _frames()
    monkeypatch.setattr(mod, "EXPECTED_CANDIDATES", 4)
    monkeypatch.setattr(
        mod,
        "_contract",
        lambda: {
            "expected_source_coverage_from_frozen_inputs": {
                "terrain_complete_candidates": 2,
                "worldcover_complete_candidates": 2,
                "both_terrain_and_worldcover_complete_candidates": 1,
                "terrain_incomplete_worldcover_complete": 1,
                "terrain_complete_worldcover_incomplete": 1,
                "both_incomplete": 1,
                "CIR06_source_ready_candidates": 2,
                "CIR06_source_indeterminate_retain_candidates": 2,
                "CIR02_CIR12_CIR13_source_ready_candidates_each": 1,
                "CIR02_CIR12_CIR13_source_indeterminate_retain_candidates_each": 3,
            }
        },
    )
    ledger, summary = mod.compose_source_availability(terrain, wc)
    assert ledger["candidate_cell_id"].tolist() == ["a", "b", "c", "d"]
    assert len(ledger) == 4
    assert ledger["CIR06_source_state"].tolist() == [
        mod.READY, mod.READY, mod.INDETERMINATE, mod.INDETERMINATE
    ]
    assert ledger["CIR02_source_state"].tolist() == [
        mod.READY, mod.INDETERMINATE, mod.INDETERMINATE, mod.INDETERMINATE
    ]
    assert ledger["CIR12_source_state"].tolist() == ledger["CIR02_source_state"].tolist()
    assert ledger["CIR13_source_state"].tolist() == ledger["CIR02_source_state"].tolist()
    assert summary["candidate_rows_dropped"] == 0
    assert summary["source_indeterminate_candidates_retained"] is True
    assert summary["source_indeterminate_may_be_recoded_as_unsuitable"] is False
    assert summary["source_indeterminate_may_be_dropped"] is False
    assert summary["source_indeterminate_may_receive_worst_ecological_score"] is False
    assert summary["ecological_score_computed"] is False
    assert summary["candidate_selection_added"] is False


def test_composition_rejects_candidate_order_drift(monkeypatch) -> None:
    terrain, wc = _frames()
    monkeypatch.setattr(mod, "EXPECTED_CANDIDATES", 4)
    monkeypatch.setattr(mod, "_contract", lambda: {"expected_source_coverage_from_frozen_inputs": {}})
    wc = wc.iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="identity/order"):
        mod.compose_source_availability(terrain, wc)


def test_composition_rejects_coordinate_drift(monkeypatch) -> None:
    terrain, wc = _frames()
    monkeypatch.setattr(mod, "EXPECTED_CANDIDATES", 4)
    monkeypatch.setattr(mod, "_contract", lambda: {"expected_source_coverage_from_frozen_inputs": {}})
    wc.loc[0, "longitude"] += 0.01
    with pytest.raises(ValueError, match="longitude differ"):
        mod.compose_source_availability(terrain, wc)
