from __future__ import annotations

import pandas as pd

import research.build_cirsium_fresh_sentinel_v2_coarse_evidence_orders as mod


def _inputs():
    ids = ["a", "b", "c", "d", "e", "f"]
    terrain = pd.DataFrame({
        "candidate_cell_id": ids,
        "regional_tile_id": ["t1", "t1", "t2", "t2", "t3", "t3"],
        "elevation": [100, 600, 300, 500, 900, 200],
        "slope": [8, 2, 4, 1, 3, 7],
        "tpi": [5, -3, 1, -5, 0, 4],
    })
    worldcover = pd.DataFrame({
        "candidate_cell_id": ids,
        "regional_tile_id": terrain["regional_tile_id"],
        "worldcover_class_code": [90, 30, 30, 10, 30, 10],
    })
    ledger = pd.DataFrame({
        "candidate_cell_id": ids,
        "regional_tile_id": terrain["regional_tile_id"],
        "CIR02_source_state": [mod.READY, mod.READY, mod.READY, mod.READY, mod.INDETERMINATE, mod.INDETERMINATE],
        "CIR06_source_state": [mod.READY, mod.READY, mod.READY, mod.READY, mod.READY, mod.INDETERMINATE],
        "CIR12_source_state": [mod.READY, mod.READY, mod.READY, mod.READY, mod.INDETERMINATE, mod.INDETERMINATE],
        "CIR13_source_state": [mod.READY, mod.READY, mod.READY, mod.READY, mod.INDETERMINATE, mod.INDETERMINATE],
    })
    return terrain, worldcover, ledger


def _contracts():
    return (
        {
            "status": "FROZEN_BEFORE_COARSE_EVIDENCE_ORDER_EXECUTION",
            "candidate_count": 6,
            "expected_direct_signal_counts_on_frozen_source_ready_denominator": {
                "CIR02_wetland_class_90": 1,
                "CIR12_grass_class_30": 2,
                "CIR13_grass_class_30": 2,
            },
        },
        {"status": "FROZEN_BEFORE_SOURCE_AVAILABILITY_COMPOSITION"},
    )


def test_full_coarse_orders_rank_only_source_ready_candidates(monkeypatch) -> None:
    terrain, worldcover, ledger = _inputs()
    monkeypatch.setattr(mod, "EXPECTED_CANDIDATES", 6)
    monkeypatch.setattr(mod, "_contracts", _contracts)
    monkeypatch.setattr(mod, "compose_source_availability", lambda t, w: (ledger.copy(), {}))

    orders, summary = mod.build_coarse_evidence_orders(terrain, worldcover)

    for unit in mod.UNITS:
        out = orders[unit]
        assert out["candidate_cell_id"].tolist() == ["a", "b", "c", "d", "e", "f"]
        indeterminate = out["source_state"].eq(mod.INDETERMINATE)
        assert out.loc[indeterminate, "coarse_evidence_rank"].isna().all()
        assert out.loc[indeterminate, "ecological_rank_defined"].eq(False).all()

    cir02 = orders["CIR02"].set_index("candidate_cell_id")
    assert cir02.loc["a", "direct_wetland_signal"] == 1
    assert cir02.loc["a", "coarse_evidence_rank"] == 1

    cir06 = orders["CIR06"].set_index("candidate_cell_id")
    assert cir06.loc["e", "coarse_evidence_rank"] == 1

    for unit in ("CIR12", "CIR13"):
        out = orders[unit]
        ready_ranked = out.loc[out["source_state"].eq(mod.READY)].sort_values("coarse_evidence_rank")
        assert ready_ranked.head(2)["direct_grass_signal"].eq(1).all()

    assert summary["CIR02_direct_wetland_signal_count"] == 1
    assert summary["CIR12_direct_grass_signal_count"] == 2
    assert summary["CIR13_direct_grass_signal_count"] == 2
    assert summary["source_indeterminate_candidates_receive_ecological_rank"] is False
    assert summary["source_indeterminate_candidates_ranked_below_source_ready"] is False
    assert summary["candidate_selection_added"] is False
    assert summary["top_k_or_threshold_applied"] is False
    assert summary["coarse_order_is_final_100m_structural_order"] is False


def test_low_direct_signal_is_not_dropped_or_called_unsuitable(monkeypatch) -> None:
    terrain, worldcover, ledger = _inputs()
    monkeypatch.setattr(mod, "EXPECTED_CANDIDATES", 6)
    monkeypatch.setattr(mod, "_contracts", _contracts)
    monkeypatch.setattr(mod, "compose_source_availability", lambda t, w: (ledger.copy(), {}))
    orders, _ = mod.build_coarse_evidence_orders(terrain, worldcover)
    cir12 = orders["CIR12"].set_index("candidate_cell_id")
    assert cir12.loc["d", "direct_grass_signal"] == 0
    assert pd.notna(cir12.loc["d", "coarse_evidence_rank"])
    assert cir12.loc["d", "source_state"] == mod.READY
