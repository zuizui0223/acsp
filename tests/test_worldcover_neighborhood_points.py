from __future__ import annotations

import numpy as np
import pandas as pd
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.errors import RasterioIOError

from acsp.discovery.providers.worldcover_neighborhood_points import (
    FEATURE_COLUMNS,
    attach_worldcover_neighbourhood_fractions,
    attach_worldcover_neighbourhood_fractions_blocked,
    audit_worldcover_neighbourhood_availability_blocked,
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


def test_blocked_sampler_is_exactly_equivalent_to_sparse_semantics() -> None:
    rng = np.random.default_rng(123)
    codes = np.asarray([10, 20, 30, 40, 50, 60, 80, 90, 95, 100, 0], dtype=np.int16)
    array = rng.choice(codes, size=(120, 120), replace=True)
    candidates = pd.DataFrame(
        {
            "candidate_cell_id": ["a", "b", "c", "d", "edge"],
            "latitude": [27.9900, 27.9850, 27.9800, 27.9750, 27.9999],
            "longitude": [126.0100, 126.0150, 126.0200, 126.0250, 126.0001],
            "grid_row": [10, 15, 20, 25, 0],
            "grid_col": [10, 15, 20, 25, 0],
        }
    )
    opener = lambda _: FakeSource(array)
    sparse, sparse_audit = attach_worldcover_neighbourhood_fractions(
        candidates,
        radius_m=250.0,
        dataset_opener=opener,
    )
    blocked, blocked_audit = attach_worldcover_neighbourhood_fractions_blocked(
        candidates,
        radius_m=250.0,
        block_pixels=8,
        dataset_opener=opener,
    )
    assert blocked["candidate_cell_id"].tolist() == sparse["candidate_cell_id"].tolist()
    assert np.allclose(
        blocked[list(FEATURE_COLUMNS)].to_numpy(float),
        sparse[list(FEATURE_COLUMNS)].to_numpy(float),
        rtol=0.0,
        atol=1e-12,
    )
    assert blocked_audit.candidate_rows_input == sparse_audit.candidate_rows_input
    assert blocked_audit.complete_neighbourhood_rows == sparse_audit.complete_neighbourhood_rows
    assert blocked_audit.tile_boundary_rows_removed == sparse_audit.tile_boundary_rows_removed
    assert blocked_audit.invalid_or_nodata_rows_removed == sparse_audit.invalid_or_nodata_rows_removed
    assert blocked_audit.source_tile_ids == sparse_audit.source_tile_ids
    assert blocked_audit.source_urls == sparse_audit.source_urls
    assert blocked_audit.feature_digest_sha256 == sparse_audit.feature_digest_sha256


def test_availability_audit_preserves_denominator_and_indeterminate_rows() -> None:
    array = np.full((30, 30), 10, dtype=np.int16)
    candidates = pd.DataFrame(
        {
            "candidate_cell_id": ["center", "tile-edge"],
            "latitude": [27.9900, 27.9999],
            "longitude": [126.0100, 126.0001],
            "grid_row": [10, 0],
            "grid_col": [10, 0],
        }
    )
    audited, audit = audit_worldcover_neighbourhood_availability_blocked(
        candidates,
        radius_m=250.0,
        block_pixels=8,
        dataset_opener=lambda _: FakeSource(array),
    )
    assert audited["candidate_cell_id"].tolist() == ["center", "tile-edge"]
    assert audited["worldcover_source_state"].tolist() == [
        "SOURCE_COMPLETE",
        "INDETERMINATE_NEIGHBOURHOOD_UNAVAILABLE",
    ]
    assert float(audited.loc[0, "wc_tree_frac_250m"]) == 1.0
    assert audited.loc[1, list(FEATURE_COLUMNS)].isna().all()
    assert audit.candidate_rows_input == 2
    assert audit.source_complete_rows == 1
    assert audit.neighbourhood_unavailable_rows == 1
    assert audit.provider_failure_rows == 0
    assert audit.biological_absence_inferred_from_source_failure is False


def test_availability_audit_retains_provider_failure_as_indeterminate() -> None:
    candidates = pd.DataFrame(
        {
            "candidate_cell_id": ["a", "b"],
            "latitude": [27.9900, 27.9850],
            "longitude": [126.0100, 126.0150],
            "grid_row": [10, 15],
            "grid_col": [10, 15],
        }
    )

    def unavailable(_url: str):
        raise RasterioIOError("HTTP 404")

    audited, audit = audit_worldcover_neighbourhood_availability_blocked(
        candidates,
        radius_m=250.0,
        dataset_opener=unavailable,
    )
    assert audited["worldcover_source_state"].eq("INDETERMINATE_PROVIDER_FAILURE").all()
    assert audited[list(FEATURE_COLUMNS)].isna().all().all()
    assert audit.source_complete_rows == 0
    assert audit.provider_failure_rows == 2
    assert audit.provider_failure_tile_ids == ("N27E126",)
    assert audit.biological_absence_inferred_from_source_failure is False
