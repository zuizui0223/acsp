from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import research.attach_cirsium_fresh_sentinel_public_terrain_v2 as mod


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_cell_id": ["a", "b", "c"],
            "latitude": [35.0, 36.0, 37.0],
            "longitude": [139.0, 140.0, 141.0],
            "regional_tile_id": ["t1", "t1", "t2"],
            "outer_frame_identity": ["JP_PUBLIC_COUNTRY_BROAD_FRAME_V1"] * 3,
            "field_outcomes_used": [False] * 3,
            "private_exact_site_geometry_used": [False] * 3,
            "occurrence_selected_tile": [False] * 3,
        }
    )


def _extractor(frame, variables, lat_col, lon_col, resolution):
    out = frame.copy()
    assert variables == ["elevation", "slope", "aspect", "roughness", "tpi"]
    assert lat_col == "latitude"
    assert lon_col == "longitude"
    assert resolution == "2.5m"
    out["elevation"] = [100.0, 200.0, np.nan]
    out["slope"] = [1.0, 2.0, 3.0]
    out["aspect"] = [10.0, 20.0, 30.0]
    out["roughness"] = [0.1, 0.2, 0.3]
    out["tpi"] = [-1.0, 0.0, 1.0]
    return out


def test_attachment_retains_all_rows_and_never_ranks() -> None:
    frame = _frame()
    enriched, summary = mod.attach_coarse_terrain(frame, extractor=_extractor)
    assert enriched["candidate_cell_id"].tolist() == ["a", "b", "c"]
    assert len(enriched) == len(frame)
    assert summary["rows_dropped"] == 0
    assert summary["rank_candidates"] is False
    assert summary["select_tiles"] is False
    assert summary["select_candidates"] is False
    assert summary["structural_graph_applied"] is False
    assert summary["coarse_fields_are_100m_structural_fields"] is False
    assert summary["all_feature_complete_count"] == 2
    assert summary["all_feature_complete_fraction"] == pytest.approx(2 / 3)
    assert "coarse_elevation" in enriched
    assert "coarse_slope" in enriched
    assert "slope100" not in enriched
    assert "tpi300" not in enriched
    assert "rough300" not in enriched


def test_attachment_rejects_candidate_reordering() -> None:
    def bad(frame, *args, **kwargs):
        out = _extractor(frame, *args, **kwargs)
        return out.iloc[::-1].reset_index(drop=True)

    with pytest.raises(ValueError, match="changed candidate order or identity"):
        mod.attach_coarse_terrain(_frame(), extractor=bad)


def test_attachment_rejects_outer_frame_with_outcome_flag() -> None:
    frame = _frame()
    frame.loc[0, "field_outcomes_used"] = True
    with pytest.raises(ValueError, match="pre-outcome boundary"):
        mod.attach_coarse_terrain(frame, extractor=_extractor)


def test_attachment_requires_all_frozen_terrain_fields() -> None:
    def missing(frame, variables, lat_col, lon_col, resolution):
        out = _extractor(frame, variables, lat_col, lon_col, resolution)
        return out.drop(columns=["roughness"])

    with pytest.raises(ValueError, match="omitted frozen feature"):
        mod.attach_coarse_terrain(_frame(), extractor=missing)
