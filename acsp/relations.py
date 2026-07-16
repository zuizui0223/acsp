"""Occurrence-relation inference and relation-cover survey selection.

This module deliberately does not estimate presence probability or raster
suitability.  It infers a sparse graph describing which observed occurrences
are locally related in an arbitrary feature space, then selects candidate
surveys that cover distinct graph relations.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import RobustScaler


@dataclass(frozen=True)
class OccurrenceRelationGraph:
    """Sparse ecological structure inferred from occurrence feature vectors.

    ``nodes`` are robust-scaled occurrence features. ``edges`` contains pairs
    of occurrence indices connected by mutual k-nearest-neighbour relations.
    ``edge_lengths`` and ``local_scales`` are expressed in the same scaled
    feature space.
    """

    nodes: np.ndarray
    edges: np.ndarray
    edge_lengths: np.ndarray
    local_scales: np.ndarray
    center: np.ndarray
    scale: np.ndarray


def _as_finite_matrix(values: np.ndarray, *, name: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2:
        raise ValueError(f"{name} must be a two-dimensional feature matrix")
    if matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError(f"{name} must contain at least one row and one column")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} contains non-finite values")
    return matrix


def infer_occurrence_relation_graph(
    occurrence_features: np.ndarray,
    *,
    n_neighbors: int = 3,
) -> OccurrenceRelationGraph:
    """Infer a mutual-neighbour graph from occurrence features.

    The only structural parameter is ``n_neighbors``.  Mutual neighbourhoods
    suppress one-way bridges from sparse outliers and keep the inferred object
    local.  Robust scaling makes the procedure independent of feature units.
    """

    raw = _as_finite_matrix(occurrence_features, name="occurrence_features")
    n = raw.shape[0]
    if n < 2:
        raise ValueError("at least two occurrence rows are required")
    if not 1 <= n_neighbors < n:
        raise ValueError("n_neighbors must be between 1 and n_occurrences - 1")

    scaler = RobustScaler(quantile_range=(25.0, 75.0)).fit(raw)
    nodes = scaler.transform(raw)
    # Constant columns receive scale 1 in RobustScaler and remain harmless.
    nn = NearestNeighbors(n_neighbors=n_neighbors + 1, metric="euclidean").fit(nodes)
    distances, indices = nn.kneighbors(nodes)
    neighbour_sets = [set(row[1:]) for row in indices]

    edges: list[tuple[int, int]] = []
    for i, neighbours in enumerate(neighbour_sets):
        for j in neighbours:
            if i < j and i in neighbour_sets[j]:
                edges.append((i, j))

    # A small sample or a strict mutual graph can be disconnected with no
    # edges.  Fall back to the Euclidean minimum spanning forest's first links:
    # each node contributes its nearest neighbour, deduplicated.  This retains
    # locality without inventing a global suitability surface.
    if not edges:
        fallback = {tuple(sorted((i, int(indices[i, 1])))) for i in range(n)}
        edges = sorted(fallback)

    edge_array = np.asarray(sorted(set(edges)), dtype=int)
    edge_vectors = nodes[edge_array[:, 1]] - nodes[edge_array[:, 0]]
    edge_lengths = np.linalg.norm(edge_vectors, axis=1)
    positive = distances[:, 1:]
    local_scales = np.median(positive, axis=1)
    nonzero = local_scales[local_scales > 0]
    replacement = float(np.median(nonzero)) if nonzero.size else 1.0
    local_scales = np.where(local_scales > 0, local_scales, replacement)

    return OccurrenceRelationGraph(
        nodes=nodes,
        edges=edge_array,
        edge_lengths=edge_lengths,
        local_scales=local_scales,
        center=np.asarray(scaler.center_, dtype=float),
        scale=np.asarray(scaler.scale_, dtype=float),
    )


def relation_membership(
    graph: OccurrenceRelationGraph,
    candidate_features: np.ndarray,
) -> np.ndarray:
    """Return candidate membership in every inferred occurrence relation.

    Membership is high when a candidate lies near the finite line segment
    between two related occurrence nodes.  Distances are normalized by the
    endpoints' local occurrence spacing, not by a raster resolution.  The
    result has shape ``(n_candidates, n_edges)`` and is not normalized across
    candidates or interpreted as probability.
    """

    raw = _as_finite_matrix(candidate_features, name="candidate_features")
    if raw.shape[1] != graph.nodes.shape[1]:
        raise ValueError("candidate and occurrence matrices must have equal columns")
    candidates = (raw - graph.center) / graph.scale
    starts = graph.nodes[graph.edges[:, 0]]
    ends = graph.nodes[graph.edges[:, 1]]
    vectors = ends - starts
    squared_lengths = np.einsum("ij,ij->i", vectors, vectors)
    squared_lengths = np.where(squared_lengths > 0, squared_lengths, 1.0)

    offset = candidates[:, None, :] - starts[None, :, :]
    t = np.einsum("ced,ed->ce", offset, vectors) / squared_lengths[None, :]
    t = np.clip(t, 0.0, 1.0)
    closest = starts[None, :, :] + t[:, :, None] * vectors[None, :, :]
    distance = np.linalg.norm(candidates[:, None, :] - closest, axis=2)
    endpoint_scale = 0.5 * (
        graph.local_scales[graph.edges[:, 0]] + graph.local_scales[graph.edges[:, 1]]
    )
    endpoint_scale = np.where(endpoint_scale > 0, endpoint_scale, 1.0)
    return np.exp(-0.5 * (distance / endpoint_scale[None, :]) ** 2)


def select_relation_cover(
    membership: np.ndarray,
    *,
    n_select: int,
    edge_weights: np.ndarray | None = None,
) -> np.ndarray:
    """Greedily select candidates by marginal coverage of graph relations.

    The set objective is weighted facility coverage:

    ``F(S) = sum_e w_e max_{i in S} membership[i, e]``.

    Thus repeatedly selecting candidates from the same inferred relation has
    diminishing return.  No presence probability or candidate suitability
    score is fitted.
    """

    matrix = _as_finite_matrix(membership, name="membership")
    n_candidates, n_edges = matrix.shape
    if not 1 <= n_select <= n_candidates:
        raise ValueError("n_select must be between 1 and n_candidates")
    if np.any(matrix < 0) or np.any(matrix > 1):
        raise ValueError("membership values must lie in [0, 1]")

    if edge_weights is None:
        weights = np.ones(n_edges, dtype=float)
    else:
        weights = np.asarray(edge_weights, dtype=float)
        if weights.shape != (n_edges,) or not np.isfinite(weights).all() or np.any(weights < 0):
            raise ValueError("edge_weights must be a finite non-negative vector")

    covered = np.zeros(n_edges, dtype=float)
    available = np.ones(n_candidates, dtype=bool)
    selected: list[int] = []
    for _ in range(n_select):
        gains = np.sum(weights[None, :] * np.maximum(matrix - covered[None, :], 0.0), axis=1)
        gains[~available] = -np.inf
        chosen = int(np.argmax(gains))
        selected.append(chosen)
        available[chosen] = False
        covered = np.maximum(covered, matrix[chosen])
    return np.asarray(selected, dtype=int)
