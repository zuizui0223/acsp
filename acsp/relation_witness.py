"""Candidate evidence for occurrence relations without interpolating habitat states."""

from __future__ import annotations

import numpy as np

from .relations import OccurrenceRelationGraph, _as_finite_matrix


def relation_witness_membership(
    graph: OccurrenceRelationGraph,
    candidate_features: np.ndarray,
) -> np.ndarray:
    """Measure whether candidates jointly witness both endpoints of each relation.

    The original line-segment membership treated every state between two
    occurrences as ecologically supported. That is an unobserved interpolation
    assumption. A relation witness instead requires a candidate to be close to
    both endpoints. Membership is the geometric mean of endpoint kernels, so a
    candidate close to only one endpoint cannot fully represent the relation.

    The returned matrix is not a probability surface and has shape
    ``(n_candidates, n_relations)``.
    """

    raw = _as_finite_matrix(candidate_features, name="candidate_features")
    if raw.shape[1] != graph.nodes.shape[1]:
        raise ValueError("candidate and occurrence matrices must have equal columns")

    candidates = (raw - graph.center) / graph.scale
    starts = graph.nodes[graph.edges[:, 0]]
    ends = graph.nodes[graph.edges[:, 1]]
    start_distance = np.linalg.norm(candidates[:, None, :] - starts[None, :, :], axis=2)
    end_distance = np.linalg.norm(candidates[:, None, :] - ends[None, :, :], axis=2)

    start_scale = np.where(
        graph.local_scales[graph.edges[:, 0]] > 0,
        graph.local_scales[graph.edges[:, 0]],
        1.0,
    )
    end_scale = np.where(
        graph.local_scales[graph.edges[:, 1]] > 0,
        graph.local_scales[graph.edges[:, 1]],
        1.0,
    )
    start_kernel = np.exp(-0.5 * (start_distance / start_scale[None, :]) ** 2)
    end_kernel = np.exp(-0.5 * (end_distance / end_scale[None, :]) ** 2)
    return np.sqrt(start_kernel * end_kernel)
