from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

import research.attach_cirsium_fresh_sentinel_v2_worldcover_points as mod


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "candidate_cell_id": ["a", "b", "c"],
        "latitude": [35.75, 35.25, 35.75],
        "longitude": [139.25, 139.25, 139.75],
        "regional_tile_id": ["x1_y1"] * 3,
        "tile_west": [139.0] * 3,
        "tile_south": [35.0] * 3,
        "tile_east": [140.0] * 3,
        "tile_north": [36.0] * 3,
        "outer_frame_identity": ["JP_PUBLIC_COUNTRY_BROAD_FRAME_V1"] * 3,
        "field_outcomes_used": [False] * 3,
        "private_exact_site_geometry_used": [False] * 3,
        "occurrence_selected_tile": [False] * 3,
    })


def _write_raster(path: Path) -> None:
    array = np.asarray([[30, 90], [80, 10]], dtype=np.uint8)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(139.0, 36.0, 0.5, 0.5),
        nodata=0,
    ) as dst:
        dst.write(array, 1)


def test_point_class_attachment_preserves_candidate_identity_and_order(tmp_path: Path) -> None:
    raster = tmp_path / "wc.tif"
    _write_raster(raster)
    frame = _frame()
    attached, summary = mod.attach_worldcover_point_classes(frame, crop_path=raster)
    assert attached["candidate_cell_id"].tolist() == frame["candidate_cell_id"].tolist()
    assert len(attached) == len(frame)
    assert summary["candidate_rows_dropped"] == 0
    assert summary["candidate_selection_added"] is False
    assert summary["candidate_ranking_added"] is False
    assert summary["neighborhood_fraction_used"] is False
    assert set(attached["worldcover_point_status"]) == {mod.COMPLETE}
    assert set(attached["worldcover_class_code"].astype(int)) == {10, 30, 90}


def test_unknown_or_nodata_class_is_indeterminate_not_dropped(tmp_path: Path) -> None:
    raster = tmp_path / "wc.tif"
    _write_raster(raster)
    frame = _frame()
    frame.loc[0, ["longitude", "latitude"]] = [140.5, 35.5]
    attached, summary = mod.attach_worldcover_point_classes(frame, crop_path=raster)
    assert len(attached) == len(frame)
    assert attached["candidate_cell_id"].tolist() == frame["candidate_cell_id"].tolist()
    assert mod.POINT_MISSING in set(attached["worldcover_point_status"])
    assert summary["candidate_rows_dropped"] == 0


def test_provider_failure_preserves_all_candidates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        mod,
        "build_worldcover_2021_map_crop",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider down")),
    )
    frame = _frame()
    attached, summary = mod.attach_worldcover_tile_with_provider(
        frame,
        crop_path=tmp_path / "crop.tif",
    )
    assert len(attached) == len(frame)
    assert attached["candidate_cell_id"].tolist() == frame["candidate_cell_id"].tolist()
    assert set(attached["worldcover_point_status"]) == {mod.PROVIDER_FAILURE}
    assert summary["candidate_rows_dropped"] == 0
    assert summary["provider_failure_is_biological_negative"] is False
    assert summary["field_outcomes_used"] is False
