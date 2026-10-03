from __future__ import annotations

import numpy as np
import pandas as pd
from rasterio.crs import CRS
from rasterio.transform import from_origin

from acsp.discovery.providers.worldcover_neighborhood_points import (
    FEATURE_COLUMNS,
    attach_worldcover_neighbourhood_fractions,
)


class FakeSource:
    def __init__(self, array: np.ndarray):
        self.array = np.asarray(array, dtype=np.int16)
        self.height, self.width = self.array.shape
        self.crs = CRS.from_epsg(4326)
        self.transform = from_origin(126.0, 28.0, 0.001, 0.001)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, band: int, *, window, masked: bool = True):
        assert band == 1
        r0 = int(window.row_off)
        c0 = int(window.col_off)
        r1 = r0 + int(window.height)
        c1 = c0 + int(window.width)
        data = self.array[r0:r1, c0:c1]
        return np.ma.array(data, mask=np.zeros_like(data, dtype=bool)) if masked else data


def test_sparse_neighbourhood_fraction_semantics_and_tile_edge_fail_closed() -> None:
    array = np.full((30, 30), 10, dtype=np.int16)
    array[:, 10:] = 30
    candidates = pd.DataFrame(
        {
            "candidate_cell_id": ["center", "tile-edge"],
            "latitude": [27.9900, 27.9999],
            "longitude": [126.0100, 126.0001],
            "grid_row": [10, 0],
            "grid_col": [10, 0],
        }
    )

    retained, audit = attach_worldcover_neighbourhood_fractions(
        candidates,
        radius_m=250.0,
        dataset_opener=lambda _: FakeSource(array),
    )
    assert retained["candidate_cell_id"].tolist() == ["center"]
    assert audit.candidate_rows_input == 2
    assert audit.complete_neighbourhood_rows == 1
    assert audit.tile_boundary_rows_removed == 1
    assert audit.invalid_or_nodata_rows_removed == 0
    assert set(FEATURE_COLUMNS).issubset(retained.columns)
    row = retained.iloc[0]
    assert 0.0 < float(row["wc_tree_frac_250m"]) < 1.0
    assert 0.0 < float(row["wc_grass_frac_250m"]) < 1.0
    assert float(row["wc_bare_frac_250m"]) == 0.0
    assert float(row["wc_water_frac_250m"]) == 0.0
    assert float(row["wc_wetland_frac_250m"]) == 0.0
    assert 0.0 < float(row["wc_edge_mix_250m"]) <= 1.0


def test_all_tree_neighbourhood_has_zero_edge_mix() -> None:
    array = np.full((30, 30), 10, dtype=np.int16)
    candidates = pd.DataFrame(
        {
            "candidate_cell_id": ["tree"],
            "latitude": [27.9900],
            "longitude": [126.0100],
            "grid_row": [10],
            "grid_col": [10],
        }
    )
    retained, _ = attach_worldcover_neighbourhood_fractions(
        candidates,
        dataset_opener=lambda _: FakeSource(array),
    )
    assert float(retained.loc[0, "wc_tree_frac_250m"]) == 1.0
    assert float(retained.loc[0, "wc_edge_mix_250m"]) == 0.0
