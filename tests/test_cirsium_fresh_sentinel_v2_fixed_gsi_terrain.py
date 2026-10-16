from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import research.attach_cirsium_fresh_sentinel_v2_fixed_gsi_terrain as mod


def _fine_grid(unit: str = "CIR06") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cohort_unit_id": [unit] * 4,
            "candidate_cell_id": [f"{unit}-{x}" for x in "abcd"],
            "grid_row": [0, 1, 2, 401],
            "grid_col": [0, 1, 2, 401],
            "latitude": [35.0, 35.001, 35.002, 35.4],
            "longitude": [139.0, 139.001, 139.002, 139.4],
        }
    )


def test_fixed_gsi_attachment_preserves_denominator_and_source_states(tmp_path: Path) -> None:
    calls = []

    def dem_builder(bounds, references, max_tiles):
        calls.append((bounds, references, max_tiles))
        return "/tmp/fake-dem.tif", "GSI; DEM5A"

    def sampler(component, _path):
        out = component.iloc[:-1].copy()
        out["elev"] = np.arange(len(out), dtype=float)
        out["slope100"] = 1.0
        out["tpi300"] = 2.0
        out["rough300"] = 3.0
        return out

    audited, summary = mod.attach_fixed_gsi_terrain(
        _fine_grid(),
        unit_id="CIR06",
        cache_dir=tmp_path / "cache",
        dem_builder=dem_builder,
        terrain_sampler=sampler,
    )
    assert len(audited) == 4
    assert audited["candidate_cell_id"].tolist() == ["CIR06-a", "CIR06-b", "CIR06-c", "CIR06-d"]
    assert summary["candidate_denominator_preserved"] is True
    assert summary["source_complete_rows"] == 2
    assert summary["terrain_vector_unavailable_rows"] == 2
    assert summary["provider_unavailable_rows"] == 0
    assert summary["chunk_grid_cells"] == 400
    assert summary["chunk_phase_offset_cells"] == [0, 0]
    assert summary["physical_chunk_width_m"] == 40000
    assert summary["source_indeterminate_recoded_as_absence"] is False
    assert summary["source_indeterminate_recoded_as_zero_support"] is False
    assert summary["structural_graph_computed"] is False
    assert summary["field_outcomes_opened"] is False
    assert len(calls) == 2
    assert all(call[2] == 900 for call in calls)


def test_provider_unavailable_is_retained_as_indeterminate(tmp_path: Path) -> None:
    def dem_builder(bounds, references, max_tiles):
        return None, ""

    audited, summary = mod.attach_fixed_gsi_terrain(
        _fine_grid(),
        unit_id="CIR06",
        cache_dir=tmp_path / "cache",
        dem_builder=dem_builder,
        terrain_sampler=lambda frame, path: frame,
    )
    assert len(audited) == 4
    assert audited["gsi_source_state"].eq("INDETERMINATE_GSI_PROVIDER_UNAVAILABLE").all()
    assert audited[list(mod.TERRAIN_COLUMNS)].isna().all().all()
    assert summary["provider_unavailable_rows"] == 4
    assert summary["source_complete_rows"] == 0


def test_zero_complete_terrain_is_retained_as_vector_unavailable(tmp_path: Path) -> None:
    def dem_builder(bounds, references, max_tiles):
        return "/tmp/fake-dem.tif", "GSI; DEM5A"

    def sampler(frame, path):
        raise ValueError("no annular candidate cell has complete terrain support in the GSI DEM snapshot")

    audited, summary = mod.attach_fixed_gsi_terrain(
        _fine_grid(),
        unit_id="CIR06",
        cache_dir=tmp_path / "cache",
        dem_builder=dem_builder,
        terrain_sampler=sampler,
    )
    assert audited["gsi_source_state"].eq("INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE").all()
    assert summary["terrain_vector_unavailable_rows"] == 4
    assert summary["source_complete_rows"] == 0


def test_reference_rule_is_stable_grid_order() -> None:
    frame = _fine_grid().iloc[[2, 0, 3, 1]].reset_index(drop=True)
    refs = mod._references(frame, 8)
    expected = tuple(
        (float(r.latitude), float(r.longitude))
        for r in frame.sort_values(["grid_row", "grid_col"], kind="mergesort").itertuples(index=False)
    )
    assert refs == expected
