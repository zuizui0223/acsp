import numpy as np

from acsp.relations import (
    infer_occurrence_relation_graph,
    relation_membership,
    select_relation_cover,
)


def test_graph_uses_mutual_local_relations():
    occurrences = np.array([[0.0, 0.0], [0.1, 0.0], [3.0, 3.0], [3.1, 3.0]])
    graph = infer_occurrence_relation_graph(occurrences, n_neighbors=1)
    assert {tuple(edge) for edge in graph.edges.tolist()} == {(0, 1), (2, 3)}


def test_relation_membership_is_invariant_to_feature_units():
    occurrences = np.array([[0.0, 0.0], [1.0, 0.0], [4.0, 4.0], [5.0, 4.0]])
    candidates = np.array([[0.5, 0.0], [4.5, 4.0], [10.0, 10.0]])
    graph_a = infer_occurrence_relation_graph(occurrences, n_neighbors=1)
    membership_a = relation_membership(graph_a, candidates)

    multiplier = np.array([1000.0, 0.01])
    graph_b = infer_occurrence_relation_graph(occurrences * multiplier, n_neighbors=1)
    membership_b = relation_membership(graph_b, candidates * multiplier)
    np.testing.assert_allclose(membership_a, membership_b)


def test_relation_cover_prefers_distinct_occurrence_relations():
    membership = np.array(
        [
            [1.00, 0.00],
            [0.95, 0.00],
            [0.00, 0.90],
        ]
    )
    selected = select_relation_cover(membership, n_select=2)
    assert selected.tolist() == [0, 2]


def test_relation_cover_is_deterministic_on_ties():
    membership = np.ones((3, 2))
    selected = select_relation_cover(membership, n_select=2)
    assert selected.tolist() == [0, 1]


def test_arbitrary_feature_dimension():
    rng = np.random.default_rng(42)
    occurrences = rng.normal(size=(20, 11))
    candidates = rng.normal(size=(30, 11))
    graph = infer_occurrence_relation_graph(occurrences, n_neighbors=3)
    membership = relation_membership(graph, candidates)
    selected = select_relation_cover(membership, n_select=5)
    assert membership.shape == (30, graph.edges.shape[0])
    assert selected.shape == (5,)
