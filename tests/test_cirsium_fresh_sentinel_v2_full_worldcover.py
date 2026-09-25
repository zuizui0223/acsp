from __future__ import annotations

from pathlib import Path

import pandas as pd

import research.run_cirsium_fresh_sentinel_v2_full_worldcover as mod


def _reference_frame() -> pd.DataFrame:
    rows = []
    for tile_ordinal in range(mod.EXPECTED_TILES):
        tile_id = f"x{tile_ordinal:03d}_y00"
        for point in range(mod.EXPECTED_POINTS_PER_TILE):
            rows.append({
                "candidate_cell_id": f"JP_{tile_id}_p{point:04d}",
                "latitude": 30.0 + tile_ordinal * 0.01 + point * 1e-7,
                "longitude": 130.0 + tile_ordinal * 0.01 + point * 1e-7,
                "regional_tile_id": tile_id,
                "tile_west": 130.0,
                "tile_south": 30.0,
                "tile_east": 132.0,
                "tile_north": 32.0,
                "outer_frame_identity": "JP_PUBLIC_COUNTRY_BROAD_FRAME_V1",
                "field_outcomes_used": False,
                "private_exact_site_geometry_used": False,
                "occurrence_selected_tile": False,
            })
    return pd.DataFrame(rows)


def _fake_attach(frame: pd.DataFrame):
    out = frame.copy()
    out["worldcover_class_code"] = 30.0
    out["worldcover_class_name"] = "Grassland"
    out["worldcover_point_status"] = mod.COMPLETE
    out["worldcover_provider_error_class"] = ""
    return out, {
        "complete_candidate_count": len(out),
        "incomplete_candidate_count": 0,
        "status_counts": {mod.COMPLETE: len(out)},
        "provider_id": "synthetic",
        "provider_release_id": "synthetic",
        "source_tile_ids": ["synthetic"],
        "successful_source_tile_ids": ["N30E129"],
        "failed_source_tile_ids": [],
        "failed_source_tile_error_classes": {},
        "bounds_overfetch_used": False,
        "point_bearing_cog_only": True,
        "candidate_rows_dropped": 0,
    }


def test_tile_partition_is_exact_seven_by_seven() -> None:
    tiles = [f"x{i:03d}_y00" for i in range(mod.EXPECTED_TILES)]
    parts = mod.tile_partition(tiles)
    assert set(parts) == set(range(mod.SHARD_COUNT))
    assert all(len(value) == 7 for value in parts.values())
    flattened = [tile for shard in range(mod.SHARD_COUNT) for tile in parts[shard]]
    assert len(flattened) == 49
    assert set(flattened) == set(tiles)


def test_all_shards_assemble_to_exact_frozen_candidate_order(tmp_path: Path, monkeypatch) -> None:
    reference = _reference_frame()
    monkeypatch.setattr(mod, "frozen_outer_frame", lambda: reference.copy())
    monkeypatch.setattr(mod, "attach_worldcover_point_bearing_cogs", _fake_attach)

    root = tmp_path / "shards"
    for shard_id in range(mod.SHARD_COUNT):
        manifest = mod.run_shard(shard_id, root / f"worldcover-shard-{shard_id}")
        assert manifest["selected_tile_count"] == 7
        assert manifest["candidate_count"] == 7 * mod.EXPECTED_POINTS_PER_TILE
        assert manifest["candidate_rows_dropped"] == 0

    out = tmp_path / "full.csv.gz"
    summary_path = tmp_path / "summary.json"
    summary = mod.assemble_shards(
        root,
        out,
        summary_path,
        reference_frame=reference,
    )
    assembled = pd.read_csv(out)
    assert assembled["candidate_cell_id"].astype(str).tolist() == reference["candidate_cell_id"].astype(str).tolist()
    assert len(assembled) == mod.EXPECTED_CANDIDATES
    assert summary["intersecting_tile_count"] == 49
    assert summary["output_candidate_count"] == 39200
    assert summary["candidate_rows_dropped"] == 0
    assert summary["exact_candidate_id_set_match"] is True
    assert summary["exact_candidate_id_order_match"] is True
    assert summary["provider_failure_tile_count"] == 0
    assert summary["complete_candidate_count"] == 39200
    assert summary["worldcover_class_counts"] == {"30": 39200}
    assert summary["repair_identity"] == mod.REPAIR_IDENTITY
    assert summary["source_gate_complete"] is True
    assert summary["bounds_overfetch_used"] is False
    assert summary["point_bearing_cog_only"] is True
    assert summary["habitat_threshold_added"] is False
    assert summary["neighborhood_fraction_used"] is False
