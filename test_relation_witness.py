import numpy as np

from acsp.relation_witness import relation_witness_membership
from acsp.relations import infer_occurrence_relation_graph


def test_relation_witness_rejects_unobserved_midpoint_bridge():
    occurrences = np.array([[0.0, 0.0], [2.0, 0.0], [10.0, 10.0]])
    graph = infer_occurrence_relation_graph(occurrences, n_neighbors=1)
    candidates = np.array([[1.0, 0.0], [0.1, 0.0]])
    membership = relation_witness_membership(graph, candidates)
    edge_index = np.where(np.all(graph.edges == np.array([0, 1]), axis=1))[0][0]
    assert membership[0, edge_index] < 1.0
    assert membership[0, edge_index] > membership[1, edge_index]


def test_relation_witness_requires_support_for_both_endpoints():
    occurrences = np.array([[0.0, 0.0], [1.0, 0.0], [8.0, 8.0], [9.0, 8.0]])
    graph = infer_occurrence_relation_graph(occurrences, n_neighbors=1)
    candidates = np.array([[0.5, 0.0], [0.0, 0.0], [8.5, 8.0]])
    membership = relation_witness_membership(graph, candidates)
    first_edge = np.where(np.all(graph.edges == np.array([0, 1]), axis=1))[0][0]
    assert membership[0, first_edge] > membership[1, first_edge]
    assert membership[0, first_edge] > membership[2, first_edge]


def test_relation_witness_is_feature_unit_invariant():
    occurrences = np.array([[0.0, 0.0], [1.0, 0.0], [4.0, 4.0], [5.0, 4.0]])
    candidates = np.array([[0.5, 0.0], [4.5, 4.0], [10.0, 10.0]])
    graph_a = infer_occurrence_relation_graph(occurrences, n_neighbors=1)
    membership_a = relation_witness_membership(graph_a, candidates)
    multiplier = np.array([1000.0, 0.01])
    graph_b = infer_occurrence_relation_graph(occurrences * multiplier, n_neighbors=1)
    membership_b = relation_witness_membership(graph_b, candidates * multiplier)
    np.testing.assert_allclose(membership_a, membership_b)
