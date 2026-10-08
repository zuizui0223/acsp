from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.audit_cirsium_fresh_sentinel_v2_selected_mosaic_sequence import (
    SelectedMosaicSequence,
)
from research.attach_cirsium_fresh_sentinel_v2_fixed_gsi_terrain import attach_fixed_gsi_terrain


def test_selected_source_order_and_source_bytes_change_commitment(tmp_path: Path) -> None:
    cache=tmp_path/"cache"
    cache.mkdir()
    a,b=cache/"mosaicA.tif",cache/"mosaicB.tif"
    a.write_bytes(b"A")
    b.write_bytes(b"B")
    one=SelectedMosaicSequence(unit_id="CIR06",cache_dir=cache)
    one(0,a)
    one(1,b)
    one(2,None)
    summary=one.summary(chunk_count=3)
    assert summary["selected_dem_chunks"]==2
    assert summary["unavailable_dem_chunks"]==1
    assert summary["chunk_count"]==3
    assert len(summary["selected_mosaic_content_sequence_sha256"])==64
    assert summary["private_source_paths_or_tile_coordinates_exported"] is False
    assert "mosaicA" not in json.dumps(summary)
    assert "mosaicB" not in json.dumps(summary)

    again=SelectedMosaicSequence(unit_id="CIR06",cache_dir=cache)
    again(0,a)
    again(1,b)
    again(2,None)
    assert again.summary(chunk_count=3)==summary
    swapped=SelectedMosaicSequence(unit_id="CIR06",cache_dir=cache)
    swapped(0,b)
    swapped(1,a)
    swapped(2,None)
    assert swapped.summary(chunk_count=3)["selected_mosaic_content_sequence_sha256"] != summary["selected_mosaic_content_sequence_sha256"]
    b.write_bytes(b"B modified")
    changed=SelectedMosaicSequence(unit_id="CIR06",cache_dir=cache)
    changed(0,a)
    changed(1,b)
    changed(2,None)
    assert changed.summary(chunk_count=3)["selected_mosaic_content_sequence_sha256"] != summary["selected_mosaic_content_sequence_sha256"]


def test_missing_sources_preserved_as_explicit_input_states(tmp_path: Path) -> None:
    observer=SelectedMosaicSequence(unit_id="CIR02",cache_dir=tmp_path)
    observer(0,None)
    result=observer.summary(chunk_count=1)
    assert result["selected_dem_chunks"]==0
    assert result["unavailable_dem_chunks"]==1
    assert result["cross_run_numeric_reproduction_proven"] is False


def test_fail_closed_for_missing_or_outside_cache_and_chunk_gaps(tmp_path: Path) -> None:
    cache=tmp_path/"cache"
    cache.mkdir()
    observer=SelectedMosaicSequence(unit_id="CIR06",cache_dir=cache)
    with pytest.raises(ValueError,match="original order"):
        observer(1,None)
    with pytest.raises(ValueError,match="selected DEM content missing"):
        observer(0,cache/"missing.tif")
    path=tmp_path/"outside.tif"
    path.write_bytes(b"bytes")
    with pytest.raises(ValueError,match="private read-only GSI cache"):
        observer(0,path)
    with pytest.raises(ValueError,match="incomplete"):
        observer.summary(chunk_count=1)


def test_opt_in_selected_source_probe_preserves_primary_output(tmp_path: Path) -> None:
    cache=tmp_path/"cache"
    cache.mkdir()
    mosaic=cache/"immutable.tif"
    mosaic.write_bytes(b"frozen-mosaic-source")
    frame=pd.DataFrame({
        "candidate_cell_id":["CIR06_r0_c0","CIR06_r1_c1","CIR06_r401_c401"],
        "cohort_unit_id":["CIR06"]*3,
        "grid_row":[0,1,401],
        "grid_col":[0,1,401],
        "latitude":[35.,35.001,35.4],
        "longitude":[139.,139.001,139.4],
    })
    def builder(bounds,references,max_tiles):
        return str(mosaic),"GSI DEM5A"
    def sampler(data,path):
        out=data.copy()
        out["elev"]=10.0
        out["slope100"]=20.0
        out["tpi300"]=30.0
        out["rough300"]=40.0
        return out
    base,baseline=attach_fixed_gsi_terrain(
        frame,unit_id="CIR06",cache_dir=cache,
        dem_builder=builder,terrain_sampler=sampler,
    )
    observer=SelectedMosaicSequence(unit_id="CIR06",cache_dir=cache)
    audited,summary=attach_fixed_gsi_terrain(
        frame,unit_id="CIR06",cache_dir=cache,
        dem_builder=builder,terrain_sampler=sampler,
        selected_mosaic_observer=observer,
    )
    pd.testing.assert_frame_equal(base,audited)
    assert baseline==summary
    observed=observer.summary(chunk_count=int(summary["chunk_count"]))
    assert observed["selected_dem_chunks"]==2
    assert observed["production_gsi_selection_changed"] is False
