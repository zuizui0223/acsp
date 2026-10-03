from __future__ import annotations

import pandas as pd

import research.audit_cirsium_fresh_sentinel_v2_local_refinement_geometry as mod


def _frames(n: int = 100, *, duplicate_top: bool = False):
    ids = [f"c{i:03d}" for i in range(n)]
    order = pd.DataFrame({
        "candidate_cell_id": ids,
        "source_state": [mod.READY] * n,
        "coarse_evidence_rank": list(range(1, n + 1)),
    })
    lat = [35.0 + i * 0.02 for i in range(n)]
    lon = [139.0] * n
    if duplicate_top:
        lat[1] = lat[0]
        lon[1] = lon[0]
    terrain = pd.DataFrame({
        "candidate_cell_id": ids,
        "latitude": lat,
        "longitude": lon,
        "regional_tile_id": ["t1"] * n,
    })
    return order, terrain


def test_center_selection_uses_exact_2p5pct_prefix() -> None:
    order, terrain = _frames(100)
    result = mod.audit_unit_geometry(order, terrain, "CIR02")
    assert result["source_ready_candidate_count"] == 100
    assert result["selected_coarse_center_count"] == 3
    assert result["center_fraction"] == 0.025
    assert result["unique_unioned_fine_cell_count"] > 0
    assert result["grid_rows_written"] is False
    assert result["ecological_sources_attached"] is False
    assert result["field_outcomes_used"] is False


def test_duplicate_top_centers_create_union_overlap() -> None:
    order, terrain = _frames(100, duplicate_top=True)
    result = mod.audit_unit_geometry(order, terrain, "CIR06")
    assert result["selected_coarse_center_count"] == 3
    assert result["overlap_memberships_removed"] > 0
    assert result["overlap_fraction_of_raw_memberships"] > 0.0
    assert result["unique_unioned_fine_cell_count"] < result["raw_seed_to_cell_membership_count"]


def test_geometry_hash_is_deterministic() -> None:
    order, terrain = _frames(100)
    a = mod.audit_unit_geometry(order, terrain, "CIR12")
    b = mod.audit_unit_geometry(order, terrain, "CIR12")
    assert a["sorted_packed_global_grid_id_sha256"] == b["sorted_packed_global_grid_id_sha256"]
    assert a["unique_unioned_fine_cell_count"] == b["unique_unioned_fine_cell_count"]
