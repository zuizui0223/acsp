from __future__ import annotations

import numpy as np
import pandas as pd

import research.attach_cirsium_fresh_sentinel_v2_coarse_terrain as mod


def _frame(n: int = 4) -> pd.DataFrame:
    return pd.DataFrame({
        "candidate_cell_id": [f"c{i}" for i in range(n)],
        "latitude": [35.0 + 0.01 * i for i in range(n)],
        "longitude": [139.0 + 0.01 * i for i in range(n)],
        "regional_tile_id": ["x159_y62"] * n,
        "outer_frame_identity": ["JP_PUBLIC_COUNTRY_BROAD_FRAME_V1"] * n,
        "field_outcomes_used": [False] * n,
        "private_exact_site_geometry_used": [False] * n,
        "occurrence_selected_tile": [False] * n,
    })


def _complete_extractor(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["elevation"] = [100.0 + i for i in range(len(out))]
    out["slope"] = 5.0
    out["aspect"] = 90.0
    out["roughness"] = 2.0
    out["tpi"] = 1.0
    return out


def test_complete_attachment_preserves_every_candidate_and_order() -> None:
    frame = _frame()
    enriched, summary = mod.attach_coarse_terrain_primitives(
        frame,
        extractor=_complete_extractor,
    )
    assert enriched["candidate_cell_id"].tolist() == frame["candidate_cell_id"].tolist()
    assert len(enriched) == len(frame)
    assert set(enriched["coarse_terrain_status"]) == {mod.COMPLETE}
    assert summary["input_candidate_count"] == summary["output_candidate_count"] == len(frame)
    assert summary["candidate_rows_dropped"] == 0
    assert summary["complete_candidate_count"] == len(frame)
    assert summary["candidate_selection_added"] is False
    assert summary["candidate_ranking_added"] is False
    assert summary["field_outcomes_used"] is False


def test_point_missing_terrain_is_indeterminate_not_dropped() -> None:
    def extractor(frame: pd.DataFrame) -> pd.DataFrame:
        out = _complete_extractor(frame)
        out.loc[1, "elevation"] = np.nan
        return out

    frame = _frame()
    enriched, summary = mod.attach_coarse_terrain_primitives(frame, extractor=extractor)
    assert enriched["candidate_cell_id"].tolist() == frame["candidate_cell_id"].tolist()
    assert len(enriched) == len(frame)
    assert enriched.loc[1, "coarse_terrain_status"] == mod.POINT_MISSING
    assert summary["incomplete_candidate_count"] == 1
    assert summary["missing_terrain_is_biological_negative"] is False


def test_provider_failure_preserves_full_outer_frame_as_indeterminate() -> None:
    def extractor(frame: pd.DataFrame) -> pd.DataFrame:
        raise RuntimeError("provider unavailable")

    frame = _frame()
    enriched, summary = mod.attach_coarse_terrain_primitives(frame, extractor=extractor)
    assert enriched["candidate_cell_id"].tolist() == frame["candidate_cell_id"].tolist()
    assert len(enriched) == len(frame)
    assert set(enriched["coarse_terrain_status"]) == {mod.PROVIDER_FAILURE}
    assert summary["candidate_rows_dropped"] == 0
    assert summary["provider_error_class"] == "RuntimeError"
    assert summary["provider_failure_is_biological_negative"] is False
    assert summary["complete_candidate_count"] == 0


def test_extractor_cannot_reorder_or_shrink_candidate_frame() -> None:
    frame = _frame()

    def reorder(frame: pd.DataFrame) -> pd.DataFrame:
        return _complete_extractor(frame).iloc[::-1].reset_index(drop=True)

    enriched, summary = mod.attach_coarse_terrain_primitives(frame, extractor=reorder)
    # Contract violation is represented as provider/computation indeterminate,
    # never accepted as a modified candidate universe.
    assert enriched["candidate_cell_id"].tolist() == frame["candidate_cell_id"].tolist()
    assert set(enriched["coarse_terrain_status"]) == {mod.PROVIDER_FAILURE}
    assert summary["provider_error_class"] == "ValueError"
