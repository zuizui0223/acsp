from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import research.attach_cirsium_fresh_sentinel_v2_fixed_gsi_terrain as gsi
from research.audit_cirsium_fresh_sentinel_v2_same_mosaic_numerical_replay import (
    FEATURES,
    SameMosaicReplayCollector,
    _selected_chunks,
    _run_probe,
)


def _frame(unit: str = "CIR06") -> pd.DataFrame:
    n = 48
    return pd.DataFrame(
        {
            "candidate_cell_id": [f"{unit}_r{i}_c{i}" for i in range(n)],
            "cohort_unit_id": [unit] * n,
            "grid_row": [i if i < 24 else 400 + i for i in range(n)],
            "grid_col": [i if i < 24 else 400 + i for i in range(n)],
            "latitude": [35.0 + i / 1000 for i in range(n)],
            "longitude": [139.0 + i / 1000 for i in range(n)],
        }
    )


def _sampler(frame: pd.DataFrame, mosaic: Path) -> pd.DataFrame:
    out = frame.copy()
    for j, feature in enumerate(FEATURES):
        out[feature] = out["grid_row"].to_numpy(float) * 0.25 + j / 100.0
    return out


def test_frozen_chunk_indices_cover_edges_and_middle_without_tuning() -> None:
    assert _selected_chunks(1) == (0,)
    assert _selected_chunks(2) == (0, 1)
    assert _selected_chunks(3) == (0, 1, 2)
    assert _selected_chunks(177) == (0, 88, 176)


def test_same_mosaic_exact_replay_and_coordinate_free_summary(tmp_path: Path) -> None:
    original = _frame()
    mosaic = tmp_path / "input-mosaic.tif"
    mosaic.write_bytes(b"immutable DEM bytes for test")
    values = _sampler(original, mosaic)
    record = _run_probe(values, original, mosaic, _sampler)
    assert record["sampled_source_complete_cells"] == 24
    assert record["original_vs_replay_1"]["all_exact"] is True
    assert record["replay_1_vs_replay_2"]["all_exact"] is True
    assert all(n == 0 for n in record["original_vs_replay_1"]["exact_mismatch_by_feature"].values())
    collector = SameMosaicReplayCollector()
    collector(0, 3, original, values, mosaic, _sampler)
    collector(1, 3, original, values, mosaic, _sampler)
    collector(2, 3, original, values, mosaic, _sampler)
    result = collector.summary("CIR06", 3)
    assert result["probed_chunk_count"] == 3
    assert result["source_complete_cells_probed"] == 72
    assert result["comparison"]["original_vs_replay_1"]["all_exact"] is True
    assert result["comparison"]["replay_1_vs_replay_2"]["all_exact"] is True
    assert result["source_integrity_and_full_order_reproduction_claim"] is False
    assert result["field_outcomes_opened"] is False
    encoded = json.dumps(result)
    for prohibited in ("latitude", "longitude", "candidate_cell_id", "input-mosaic", "CIR06_r"):
        assert prohibited not in encoded


def test_original_vs_replay_mismatch_detected_without_source_change(tmp_path: Path) -> None:
    mosaic = tmp_path / "input-mosaic.tif"
    mosaic.write_bytes(b"controlled DEM bytes")
    frame = _frame()
    original = _sampler(frame, mosaic)
    calls = 0

    def drift_sampler(values: pd.DataFrame, path: Path) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        out = _sampler(values, path)
        if calls == 1:
            out.loc[out.index[0], "elev"] += 0.000001
        return out

    row = _run_probe(original, frame, mosaic, drift_sampler)
    assert row["mosaic_sha256_stable_across_replays"] is True
    assert row["original_vs_replay_1"]["exact_mismatch_by_feature"]["elev"] == 1
    assert row["replay_1_vs_replay_2"]["exact_mismatch_by_feature"]["elev"] == 1
    assert row["original_vs_replay_1"]["near_mismatch_by_feature"]["elev"] == 1
    assert row["original_vs_replay_1"]["max_abs_difference_by_feature"]["elev"] > 0


def test_mosaic_mutation_is_rejected_before_public_receipt(tmp_path: Path) -> None:
    mosaic = tmp_path / "input-mosaic.tif"
    mosaic.write_bytes(b"before")
    frame = _frame()
    original = _sampler(frame, mosaic)

    def mutate_sampler(rows: pd.DataFrame, path: Path) -> pd.DataFrame:
        path.write_bytes(b"after")
        return _sampler(rows, path)

    with pytest.raises(ValueError, match="changed DEM source bytes"):
        _run_probe(original, frame, mosaic, mutate_sampler)


def test_missing_complete_replay_rows_rejected(tmp_path: Path) -> None:
    mosaic = tmp_path / "input-mosaic.tif"
    mosaic.write_bytes(b"same source")
    frame = _frame()
    original = _sampler(frame, mosaic)

    def drop_sampler(rows: pd.DataFrame, path: Path) -> pd.DataFrame:
        return _sampler(rows.iloc[1:], path)

    with pytest.raises(ValueError, match="changed the source-complete ID set"):
        _run_probe(original, frame, mosaic, drop_sampler)


def test_probe_is_opt_in_and_cannot_change_fixed_source_output(tmp_path: Path) -> None:
    mosaic = tmp_path / "immutable-mosaic.tif"
    mosaic.write_bytes(b"same exact DEM")
    frame = _frame()
    def builder(bounds, references, max_tiles):
        return str(mosaic), "GSI DEM5A"

    ordinary, ordinary_summary = gsi.attach_fixed_gsi_terrain(
        frame, unit_id="CIR06", cache_dir=tmp_path / "ordinary",
        dem_builder=builder, terrain_sampler=_sampler,
    )
    collector = SameMosaicReplayCollector()
    probed, probed_summary = gsi.attach_fixed_gsi_terrain(
        frame, unit_id="CIR06", cache_dir=tmp_path / "diagnostic",
        dem_builder=builder, terrain_sampler=_sampler,
        numerical_probe=collector,
    )
    pd.testing.assert_frame_equal(ordinary, probed)
    assert ordinary_summary == probed_summary
    outcome = collector.summary("CIR06", ordinary_summary["chunk_count"])
    assert outcome["probed_chunk_count"] == 2
    assert outcome["source_complete_cells_probed"] == 48


def test_empty_and_denominator_cases_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        _selected_chunks(0)
    collector = SameMosaicReplayCollector()
    with pytest.raises(ValueError, match="unknown numerical replay"):
        collector.summary("UNDECLARED", 3)
