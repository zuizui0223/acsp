from __future__ import annotations

import pytest

from validate_cirsium_fresh_range_sector_bundle_v1 import EXPECTED_UNITS, validate_bundle


def _feature(unit: str, x: float) -> dict:
    return {
        "type": "Feature",
        "properties": {"cohort_unit_id": unit},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[x, 0.0], [x + 0.5, 0.0], [x + 0.5, 0.5], [x, 0.5], [x, 0.0]]],
        },
    }


def test_bundle_requires_exact_frozen_four_unit_set() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [_feature(unit, float(i)) for i, unit in enumerate(EXPECTED_UNITS)],
    }
    by_unit = validate_bundle(payload)
    assert tuple(by_unit) == EXPECTED_UNITS


def test_bundle_rejects_duplicate_or_missing_unit() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            _feature("CIR02", 0.0),
            _feature("CIR06", 1.0),
            _feature("CIR12", 2.0),
            _feature("CIR12", 3.0),
        ],
    }
    with pytest.raises(ValueError):
        validate_bundle(payload)


def test_bundle_rejects_point_geometry() -> None:
    features = [_feature(unit, float(i)) for i, unit in enumerate(EXPECTED_UNITS)]
    features[0]["geometry"] = {"type": "Point", "coordinates": [0.0, 0.0]}
    with pytest.raises(ValueError):
        validate_bundle({"type": "FeatureCollection", "features": features})


def test_bundle_rejects_swapped_japan_lat_lon_order() -> None:
    features = [_feature(unit, 130.0 + i) for i, unit in enumerate(EXPECTED_UNITS)]
    features[0]["geometry"] = {
        "type": "Polygon",
        "coordinates": [[[35.0, 139.0], [35.1, 139.0], [35.1, 139.1], [35.0, 139.1], [35.0, 139.0]]],
    }
    with pytest.raises(ValueError, match="latitude is outside"):
        validate_bundle({"type": "FeatureCollection", "features": features})


def test_bundle_rejects_projected_meter_coordinates() -> None:
    features = [_feature(unit, float(i)) for i, unit in enumerate(EXPECTED_UNITS)]
    features[0]["geometry"] = {
        "type": "Polygon",
        "coordinates": [[[500000.0, 3900000.0], [500100.0, 3900000.0], [500100.0, 3900100.0], [500000.0, 3900100.0], [500000.0, 3900000.0]]],
    }
    with pytest.raises(ValueError, match="longitude is outside"):
        validate_bundle({"type": "FeatureCollection", "features": features})


def test_bundle_rejects_nonfinite_coordinates() -> None:
    features = [_feature(unit, float(i)) for i, unit in enumerate(EXPECTED_UNITS)]
    features[0]["geometry"]["coordinates"][0][1][0] = float("nan")
    with pytest.raises(ValueError, match="coordinates must be finite"):
        validate_bundle({"type": "FeatureCollection", "features": features})


def test_bundle_accepts_valid_japan_multipolygon_lon_lat() -> None:
    features = [_feature(unit, 130.0 + i) for i, unit in enumerate(EXPECTED_UNITS)]
    features[0]["geometry"] = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[139.0, 35.0], [139.1, 35.0], [139.1, 35.1], [139.0, 35.1], [139.0, 35.0]]]
        ],
    }
    by_unit = validate_bundle({"type": "FeatureCollection", "features": features})
    assert set(by_unit) == set(EXPECTED_UNITS)
