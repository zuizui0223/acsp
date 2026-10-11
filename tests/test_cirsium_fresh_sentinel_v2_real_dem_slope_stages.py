from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
from pyproj import Transformer

from research.audit_cirsium_slope_kernel_synthetic_two_run import synthesize_mosaic
from research.audit_cirsium_fresh_sentinel_v2_real_dem_slope_stages import (
    CIR02RealDEMSlopeStageCollector, STAGES, _contract,
)
from research.attach_cirsium_fresh_sentinel_v2_fixed_gsi_terrain import attach_fixed_gsi_terrain
from research.build_cirsium_private_alpine_local_grid_v1 import _sample_terrain


def _original_synthetic_real_grid(tmp_path: Path):
    path = tmp_path / "gsi_private_cache" / "mosaic.tif"
    synthesize_mosaic(path)
    coords = [(r, c) for r in (75, 90, 105, 120, 135, 150) for c in (40, 58, 76, 130, 148, 166, 184, 206)]
    with rasterio.open(path) as src:
        xs, ys = rasterio.transform.xy(
            src.transform, [r for r, _ in coords], [c for _, c in coords],
            offset="center",
        )
    lon, lat = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(xs, ys)
    frame = pd.DataFrame({
        "cohort_unit_id": ["CIR02"] * len(coords),
        "candidate_cell_id": [f"CIR02_r{i}_c{i}" for i in range(len(coords))],
        "grid_row": [r for r, _ in coords],
        "grid_col": [c for _, c in coords],
        "latitude": lat,
        "longitude": lon,
    })
    original = _sample_terrain(frame, path)
    assert len(original) == len(frame)
    return frame, original, path


def test_sampled_real_DEM_stages_are_exactly_original_production_and_coordinate_free(tmp_path: Path):
    _contract()
    grid, original, path = _original_synthetic_real_grid(tmp_path)
    a = CIR02RealDEMSlopeStageCollector()
    for i in (0, 88, 176):
        a(i, 177, grid, original, path)
    receipt = a.summary(unit_id="CIR02", source_chunk_count=177)
    assert receipt["status"] == "ORIGINAL_REAL_DEM_CIR02_THREE_CHUNK_STAGE_AUDIT_COMPLETE"
    assert receipt["all_predeclared_chunks_eligible"] is True
    assert receipt["source_complete_cells_probed"] == 72
    assert receipt["probed_chunk_count"] == 3
    assert set(receipt["stages_exact_float64_sha256"]) == set(STAGES)
    assert all(len(v) == 64 for v in receipt["stages_exact_float64_sha256"].values())
    assert all(set(r) == {"2", "8"} for r in receipt["stages_decimal_sha256"].values())
    dumped = json.dumps(receipt)
    for forbidden in ("latitude", "longitude", "candidate_cell_id", "mosaic.tif", "CIR02_r"):
        assert forbidden not in dumped
    assert receipt["all_177_chunks_or_actual_historical_CIR02_cause_reproduced"] is False

    b = CIR02RealDEMSlopeStageCollector()
    for i in (0, 88, 176):
        b(i, 177, grid, original, path)
    assert b.summary(unit_id="CIR02", source_chunk_count=177) == receipt


def test_stage_hashes_react_to_changed_selected_DEM_content(tmp_path: Path):
    grid, original, path = _original_synthetic_real_grid(tmp_path)
    initial = CIR02RealDEMSlopeStageCollector()
    initial(0, 177, grid, original, path)
    first = initial.summary(unit_id="CIR02", source_chunk_count=177)
    assert first["status"] == "ORIGINAL_REAL_DEM_STAGE_SAMPLING_INCOMPLETE"
    assert first["stages_exact_float64_sha256"] == {}
    # Finish the first prospective run under its original unchanged TIFF;
    # do NOT mix old sampled vectors with modified DEM bytes across chunks.
    for i in (88, 176):
        initial(i, 177, grid, original, path)
    before = initial.summary(unit_id="CIR02", source_chunk_count=177)

    with rasterio.open(path, "r+") as dst:
        values = dst.read(1)
        values[100:120, 100:160] += 1.75
        dst.write(values, 1)
    second_original = _sample_terrain(grid, path)
    later = CIR02RealDEMSlopeStageCollector()
    for i in (0, 88, 176):
        later(i, 177, grid, second_original, path)
    after = later.summary(unit_id="CIR02", source_chunk_count=177)
    assert before["sampled_mosaics_content_order_sha256"] != after["sampled_mosaics_content_order_sha256"]


def test_unfinished_selected_chunks_fail_closed_and_source_counts_are_frozen(tmp_path: Path):
    grid, original, path = _original_synthetic_real_grid(tmp_path)
    collector = CIR02RealDEMSlopeStageCollector()
    with pytest.raises(ValueError, match="CIR02 real source chunk denominator"):
        collector(0, 3, grid, original, path)
    collector(0, 177, grid, original, path)
    with pytest.raises(ValueError, match="duplicate original selected"):
        collector(0, 177, grid, original, path)
    incomplete = collector.summary(unit_id="CIR02", source_chunk_count=177)
    assert incomplete["all_predeclared_chunks_eligible"] is False
    assert incomplete["stages_decimal_sha256"] == {}
    with pytest.raises(ValueError, match="original fixed chunk policy"):
        collector.summary(unit_id="CIR13", source_chunk_count=177)


def test_opt_in_probe_callback_preserves_primary_GSI_attachment(tmp_path: Path):
    grid, original, path = _original_synthetic_real_grid(tmp_path)
    grid = grid.iloc[[0, 1, -2, -1]].copy()
    grid.loc[grid.index[2:], "grid_row"] = [401, 402]
    calls = []

    def builder(bounds, references, max_tiles):
        return str(path), "GSI DEM5A"

    def sampler(rows: pd.DataFrame, dem: Path) -> pd.DataFrame:
        result = rows.copy()
        for feature in ("elev", "slope100", "tpi300", "rough300"):
            result[feature] = 10.0
        return result

    regular, regular_status = attach_fixed_gsi_terrain(
        grid, unit_id="CIR02", cache_dir=tmp_path / "regular",
        dem_builder=builder, terrain_sampler=sampler,
    )

    def recording_probe(chunk_index, total_chunks, rows, source_sampled, dem_path):
        calls.append((chunk_index, total_chunks, len(rows), len(source_sampled), dem_path))

    probed, probed_status = attach_fixed_gsi_terrain(
        grid, unit_id="CIR02", cache_dir=tmp_path / "diagnostic",
        dem_builder=builder, terrain_sampler=sampler,
        real_slope_stage_probe=recording_probe,
    )
    pd.testing.assert_frame_equal(regular, probed)
    assert regular_status == probed_status
    assert [x[0] for x in calls] == [0, 1]
    assert all(x[-1] == path for x in calls)
