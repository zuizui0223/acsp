import numpy as np

from acsp.contrast import (
    candidate_contrasts,
    contrast_membership,
    empirical_contrast,
    fit_ecological_contrast,
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
