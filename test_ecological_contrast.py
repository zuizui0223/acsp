import numpy as np

from acsp.contrast import (
    automatic_support_size,
    candidate_contrasts,
    contrast_membership,
    empirical_contrast,
    fit_ecological_contrast,
    fit_local_ecological_contrast,
    local_contrasts,
    select_contrast_cover,
)


def test_empirical_contrast_maps_constant_feature_to_zero():
    availability = np.array([[1.0, 5.0], [2.0, 5.0], [3.0, 5.0]])
    values = np.array([[2.0, 5.0]])
    result = empirical_contrast(values, availability)
    np.testing.assert_allclose(result[0], [0.0, 0.0])


def test_operator_is_invariant_to_group_specific_location_shift():
    availability = np.array([
        [0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0],
        [100.0, -50.0], [101.0, -49.0], [102.0, -48.0], [103.0, -47.0],
    ])
    groups = np.array(["a"] * 4 + ["b"] * 4)
    occupied = np.array([[3.0, 0.0], [103.0, -50.0]])
    occupied_groups = np.array(["a", "b"])

    operator = fit_ecological_contrast(occupied, occupied_groups, availability, groups)
    np.testing.assert_allclose(operator.group_contrasts[0], operator.group_contrasts[1])
    assert operator.median_contrast[0] > 0
    assert operator.median_contrast[1] < 0


def test_candidates_are_ranked_within_their_own_availability_group():
    availability = np.array([[0.0], [1.0], [2.0], [100.0], [101.0], [102.0]])
    groups = np.array(["a", "a", "a", "b", "b", "b"])
    candidates = np.array([[2.0], [102.0]])
    contrasts = candidate_contrasts(candidates, np.array(["a", "b"]), availability, groups)
    np.testing.assert_allclose(contrasts[0], contrasts[1])


def test_contrast_cover_selects_distinct_observed_transformations():
    membership = np.array([[1.0, 0.0], [0.95, 0.0], [0.0, 0.9]])
    selected = select_contrast_cover(membership, n_select=2)
    assert selected.tolist() == [0, 2]


def test_shifted_regions_match_same_contrast_operator():
    availability = np.array([
        [0.0], [1.0], [2.0], [3.0],
        [100.0], [101.0], [102.0], [103.0],
    ])
    groups = np.array(["a"] * 4 + ["b"] * 4)
    occupied = np.array([[3.0], [103.0]])
    operator = fit_ecological_contrast(occupied, np.array(["a", "b"]), availability, groups)
    candidates = np.array([[3.0], [100.0], [103.0]])
    candidate_groups = np.array(["a", "b", "b"])
    contrasts = candidate_contrasts(candidates, candidate_groups, availability, groups)
    membership = contrast_membership(operator, contrasts)
    assert membership[0].mean() == membership[2].mean()
    assert membership[0].mean() > membership[1].mean()


def test_local_frames_do_not_require_query_and_support_to_share_a_grid_cell():
    support_coordinates = np.column_stack([np.arange(12, dtype=float), np.zeros(12)])
    support_features = np.arange(12, dtype=float).reshape(-1, 1)
    query_coordinates = np.array([[0.49, 3.7], [10.51, -2.0]])
    query_features = np.array([[2.0], [10.0]])
    contrasts = local_contrasts(
        query_features,
        query_coordinates,
        support_features,
        support_coordinates,
        n_neighbors=4,
    )
    assert contrasts.shape == (2, 1)
    assert np.isfinite(contrasts).all()


def test_local_operator_recovers_repeated_relative_extreme_after_spatial_shift():
    coordinates = np.column_stack([np.arange(16, dtype=float), np.zeros(16)])
    features = np.concatenate([np.arange(8), 100 + np.arange(8)]).reshape(-1, 1)
    occupied_coordinates = np.array([[7.0, 0.2], [15.0, -0.3]])
    occupied_features = np.array([[7.0], [107.0]])
    operator = fit_local_ecological_contrast(
        occupied_features,
        occupied_coordinates,
        np.array(["west", "east"]),
        features,
        coordinates,
        n_neighbors=8,
    )
    assert len(operator.group_labels) == 2
    assert np.all(operator.group_contrasts > 0)


def test_candidate_self_row_is_excluded_from_local_availability():
    features = np.arange(9, dtype=float).reshape(-1, 1)
    coordinates = np.arange(9, dtype=float).reshape(-1, 1)
    contrasts = local_contrasts(
        features,
        coordinates,
        features,
        coordinates,
        n_neighbors=4,
        self_indices=np.arange(9),
    )
    assert contrasts[0, 0] < 0
    assert contrasts[-1, 0] > 0


def test_automatic_support_size_is_deterministic_and_bounded():
    assert automatic_support_size(4) == 4
    assert automatic_support_size(100) == 10
    assert automatic_support_size(5000) < 5000
