from __future__ import annotations

import pandas as pd

import research.materialize_cirsium_fresh_sentinel_v2_fine_frames as mod


def _seeds(unit: str) -> pd.DataFrame:
    rows = []
    for lane, lon in [
        ("SOURCE_READY_COARSE_ORDER_COVER", 139.0),
        ("SOURCE_INDETERMINATE_GEOMETRY_ONLY_COVER", 140.0),
    ]:
        rows.append({
            "cohort_unit_id": unit,
            "seed_lane": lane,
            "seed_order": 1,
            "candidate_cell_id": f"{unit}-{lane}",
            "latitude": 35.0,
            "longitude": lon,
            "fine_expansion_radius_km": 5.0,
        })
    return pd.DataFrame(rows)


def test_fine_frame_uses_one_shared_integer_grid_and_separate_lanes() -> None:
    frame, summary = mod.materialize_unit_fine_frame(_seeds("CIR02"), "CIR02")
    assert summary["projection_identity"] == "JAPAN_CENTERED_AEQD_V1"
    assert summary["grid_spacing_m"] == 100.0
    assert summary["seed_radius_m"] == 5000.0
    assert summary["lanes_kept_separate"] is True
    assert set(frame["fine_frame_lane"]) == set(mod.LANES)
    assert not frame["fine_cell_id"].duplicated().any()
    for lane in mod.LANES:
        part = frame.loc[frame["fine_frame_lane"].eq(lane)]
        assert not part[["grid_row", "grid_col"]].duplicated().any()
        assert len(part) > 7000


def test_overlapping_seeds_union_duplicate_cells_within_lane() -> None:
    seeds = _seeds("CIR06")
    extra = seeds.iloc[[0]].copy()
    extra["seed_order"] = 2
    extra["candidate_cell_id"] = "CIR06-ready-duplicate"
    seeds = pd.concat([seeds, extra], ignore_index=True)
    _, summary = mod.materialize_unit_fine_frame(seeds, "CIR06")
    ready = summary["lane_results"]["SOURCE_READY_COARSE_ORDER_COVER"]
    assert ready["seed_count"] == 2
    assert ready["overlap_memberships_removed"] > 0
    assert ready["grid_pair_unique"] is True


def test_fine_frame_adds_no_ecological_or_field_claims() -> None:
    _, summary = mod.materialize_unit_fine_frame(_seeds("CIR12"), "CIR12")
    assert summary["ecological_sources_attached"] is False
    assert summary["structural_graph_computed"] is False
    assert summary["candidate_ranking_added"] is False
    assert summary["access_or_roads_used"] is False
    assert summary["budget_used"] is False
    assert summary["field_outcomes_used"] is False
