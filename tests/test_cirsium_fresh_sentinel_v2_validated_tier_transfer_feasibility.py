from __future__ import annotations

import pandas as pd

import research.test_cirsium_fresh_sentinel_v2_validated_tier_transfer_feasibility as mod


def test_transfer_uses_exact_validated_fraction_and_merge_distance() -> None:
    n = 200
    outer = pd.DataFrame({
        "candidate_cell_id": [f"c{i}" for i in range(n)],
        "latitude": [35.0 + i * 0.01 for i in range(n)],
        "longitude": [139.0] * n,
        "regional_tile_id": ["t1"] * n,
    })
    order = pd.DataFrame({
        "candidate_cell_id": [f"c{i}" for i in range(n)],
        "source_state": [mod.READY] * n,
        "coarse_evidence_rank": list(range(1, n + 1)),
    })
    patches, summary = mod.transfer_unit(order, outer, "CIR02")
    assert summary["retained_point_count"] == 5
    assert summary["support_fraction"] == 0.025
    assert summary["patch_merge_distance_m"] == 1000.0
    assert summary["field_outcome_used"] is False
    assert summary["recovery_used"] is False
    assert summary["source_indeterminate_included"] is False
    assert len(patches) == summary["patch_count"]


def test_source_indeterminate_candidates_are_not_promoted_into_transfer_tier() -> None:
    n = 200
    outer = pd.DataFrame({
        "candidate_cell_id": [f"c{i}" for i in range(n)],
        "latitude": [35.0 + i * 0.001 for i in range(n)],
        "longitude": [139.0] * n,
        "regional_tile_id": ["t1"] * n,
    })
    states = [mod.READY] * 100 + ["SOURCE_INDETERMINATE_RETAIN"] * 100
    ranks = list(range(1, 101)) + [pd.NA] * 100
    order = pd.DataFrame({
        "candidate_cell_id": [f"c{i}" for i in range(n)],
        "source_state": states,
        "coarse_evidence_rank": pd.array(ranks, dtype="Int64"),
    })
    _, summary = mod.transfer_unit(order, outer, "CIR12")
    assert summary["source_ready_candidate_count"] == 100
    assert summary["retained_point_count"] == 3
    assert summary["source_indeterminate_included"] is False
    assert summary["transfer_already_validated"] is False
