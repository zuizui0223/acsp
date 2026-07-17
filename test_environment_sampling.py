import numpy as np
import pandas as pd

from acsp.environment_sampling import sample_environment_at_points


def test_samples_nearest_complete_cell_with_distance_audit():
    points = pd.DataFrame({"latitude": [35.0, 35.01], "longitude": [139.0, 139.01]})
    reference = pd.DataFrame(
        {
            "latitude": [35.0001, 35.0101, 36.0],
            "longitude": [139.0001, 139.0101, 140.0],
            "elevation": [10.0, 20.0, 999.0],
            "slope": [1.0, 2.0, 9.0],
        }
    )
    result = sample_environment_at_points(
        points, reference, ["elevation", "slope"], maximum_distance_km=0.1
    )
    assert result.values.tolist() == [[10.0, 1.0], [20.0, 2.0]]
    assert np.all(result.distances_km < 0.1)
    assert result.matched_reference_indices.tolist() == [0, 1]


def test_does_not_impute_beyond_distance_bound():
    points = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
    reference = pd.DataFrame(
        {"latitude": [36.0], "longitude": [140.0], "elevation": [10.0], "slope": [1.0]}
    )
    result = sample_environment_at_points(
        points, reference, ["elevation", "slope"], maximum_distance_km=1.0
    )
    assert result.values.shape == (0, 2)
    assert result.distances_km.size == 0


def test_removes_reference_rows_with_missing_features():
    points = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
    reference = pd.DataFrame(
        {
            "latitude": [35.0, 35.0002],
            "longitude": [139.0, 139.0002],
            "elevation": [np.nan, 12.0],
            "slope": [1.0, 2.0],
        }
    )
    result = sample_environment_at_points(
        points, reference, ["elevation", "slope"], maximum_distance_km=0.1
    )
    assert result.values.tolist() == [[12.0, 2.0]]
    assert result.matched_reference_indices.tolist() == [1]
