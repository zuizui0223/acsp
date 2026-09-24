from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import box

from acsp.global_inputs import CountryLandGeometry
import research.build_cirsium_fresh_sentinel_public_broad_frame_v2 as mod


def _geometry(code: str = "JP") -> CountryLandGeometry:
    return CountryLandGeometry(
        country_code=code,
        land_geometry_wkt=box(139.0, 35.0, 141.0, 37.0).wkt,
        source_id="synthetic-country-geometry",
        source_version="synthetic-v1",
    )


def test_shared_outer_frame_is_geometry_only_and_outcome_blind() -> None:
    frame, summary = mod.build_fresh_sentinel_v2_outer_frame(
        _geometry(),
        points_per_tile=4,
    )
    assert len(frame) > 0
    assert frame["candidate_cell_id"].is_unique
    assert set(frame["field_outcomes_used"]) == {False}
    assert set(frame["private_exact_site_geometry_used"]) == {False}
    assert set(frame["occurrence_selected_tile"]) == {False}
    assert summary["cohort_unit_ids"] == ["CIR02", "CIR06", "CIR12", "CIR13"]
    assert summary["shared_outer_frame_across_units"] is True
    assert summary["historical_occurrence_tile_selection"] is False
    assert summary["private_exact_site_geometry_used"] is False
    assert summary["p02_result_used"] is False
    assert summary["prospective_field_outcomes_opened"] is False
    assert summary["points_per_tile"] == 4
    assert summary["candidate_count"] == len(frame)


def test_outer_frame_rejects_non_japan_geometry() -> None:
    with pytest.raises(ValueError, match="Japan country geometry"):
        mod.build_fresh_sentinel_v2_outer_frame(
            _geometry("US"),
            points_per_tile=4,
        )


def test_outer_frame_candidate_ids_are_deterministic() -> None:
    first, _ = mod.build_fresh_sentinel_v2_outer_frame(_geometry(), points_per_tile=5)
    second, _ = mod.build_fresh_sentinel_v2_outer_frame(_geometry(), points_per_tile=5)
    assert first["candidate_cell_id"].tolist() == second["candidate_cell_id"].tolist()
    assert first[["latitude", "longitude"]].equals(second[["latitude", "longitude"]])


def test_run_refuses_coordinate_outputs_inside_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "ROOT", tmp_path.resolve())
    inside = tmp_path / "frame.csv"
    with pytest.raises(ValueError, match="outside the public repository"):
        mod.run(inside, tmp_path / "summary.json")
