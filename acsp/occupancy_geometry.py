"""Environmental occupancy geometry from arbitrary occurrence feature matrices.

The module describes how observed ecological states occupy feature space. It does
not estimate raster suitability or presence probability. The primary objects are
robust pairwise span, minimum-spanning-tree continuity, and data-driven gap
components separated by unusually long MST edges.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OccupancyGeometry:
    """Summary of the geometry formed by occurrence states."""

    n_occurrences: int
    n_features: int
    span: float
    mst_length: float
    continuity: float
    gap_strength: float
    component_count: int
    labels: np.ndarray
    mst_edges: np.ndarray


def _feature_matrix(values: np.ndarray) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 2 or matrix.shape[1] < 1:
        raise ValueError("values must contain at least two rows and one feature")
    if not np.isfinite(matrix).all():
        raise ValueError("values contains non-finite entries")
    return matrix


def robust_scale(values: np.ndarray) -> np.ndarray:
    """Median/MAD scale features while making constant columns neutral."""
    matrix = _feature_matrix(values)
    median = np.median(matrix, axis=0)
    mad = np.median(np.abs(matrix - median), axis=0) * 1.4826
    scale = np.where(mad > 0.0, mad, 1.0)
    scaled = (matrix - median) / scale
    scaled[:, mad == 0.0] = 0.0
    return scaled


def pairwise_distances(values: np.ndarray) -> np.ndarray:
    """Return the Euclidean distance matrix after robust feature scaling."""
    scaled = robust_scale(values)
    delta = scaled[:, None, :] - scaled[None, :, :]
    return np.sqrt(np.sum(delta * delta, axis=2))


def minimum_spanning_tree(distances: np.ndarray) -> np.ndarray:
    """Return MST edges as ``(source, target, distance)`` using Prim's method."""
    matrix = np.asarray(distances, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] < 2:
        raise ValueError("distances must be a square matrix with at least two rows")
    if not np.isfinite(matrix).all() or np.any(matrix < 0.0):
        raise ValueError("distances must be finite and non-negative")
    n = matrix.shape[0]
    visited = np.zeros(n, dtype=bool)
    visited[0] = True
    best = matrix[0].copy()
    parent = np.zeros(n, dtype=int)
    edges: list[tuple[int, int, float]] = []
    for _ in range(n - 1):
        candidates = np.where(~visited, best, np.inf)
        target = int(np.argmin(candidates))
        if not np.isfinite(candidates[target]):
            raise ValueError("distance graph is disconnected")
        source = int(parent[target])
        edges.append((source, target, float(matrix[source, target])))
        visited[target] = True
        improve = (~visited) & (matrix[target] < best)
        best[improve] = matrix[target, improve]
        parent[improve] = target
    return np.asarray(edges, dtype=float)


def _gap_threshold(edge_lengths: np.ndarray, multiplier: float) -> float:
    if edge_lengths.size <= 1:
        return np.inf
    median = float(np.median(edge_lengths))
    mad = float(np.median(np.abs(edge_lengths - median)) * 1.4826)
    if mad > 0.0:
        return median + float(multiplier) * mad

    tolerance = max(1e-12, abs(median) * 1e-9)
    clearly_larger = edge_lengths[edge_lengths > median + tolerance]
    if clearly_larger.size == 0:
        return np.inf
    return 0.5 * (median + float(np.min(clearly_larger)))


def _component_labels(n: int, edges: np.ndarray, threshold: float) -> np.ndarray:
    adjacency: list[list[int]] = [[] for _ in range(n)]
    for source, target, length in edges:
        if float(length) <= threshold:
            i, j = int(source), int(target)
            adjacency[i].append(j)
            adjacency[j].append(i)
    labels = np.full(n, -1, dtype=int)
    component = 0
    for start in range(n):
        if labels[start] >= 0:
            continue
        stack = [start]
        labels[start] = component
        while stack:
            current = stack.pop()
            for neighbour in adjacency[current]:
                if labels[neighbour] < 0:
                    labels[neighbour] = component
                    stack.append(neighbour)
        component += 1
    return labels


def infer_occupancy_geometry(
    values: np.ndarray,
    *,
    gap_multiplier: float = 3.0,
    span_quantile: float = 0.90,
) -> OccupancyGeometry:
    """Infer scale-free occupancy span, continuity, and gap components.

    ``span`` is the requested upper quantile of non-zero pairwise distances.
    ``continuity`` is the direct environmental span divided by MST length and lies
    in ``(0, 1]``. Lower values indicate a more winding or fragmented occupation.
    ``gap_strength`` is the largest MST edge relative to the median MST edge.
    Components are obtained by cutting MST edges above a robust threshold.
    """
    if gap_multiplier < 0.0:
        raise ValueError("gap_multiplier must be non-negative")
    if not 0.0 < span_quantile <= 1.0:
        raise ValueError("span_quantile must lie in (0, 1]")
    matrix = _feature_matrix(values)
    distances = pairwise_distances(matrix)
    upper = distances[np.triu_indices(len(matrix), k=1)]
    positive = upper[upper > 0.0]
    span = float(np.quantile(positive, span_quantile)) if positive.size else 0.0
    edges = minimum_spanning_tree(distances)
    lengths = edges[:, 2]
    mst_length = float(lengths.sum())
    diameter = float(upper.max()) if upper.size else 0.0
    continuity = 1.0 if mst_length == 0.0 else float(diameter / mst_length)
    positive_edges = lengths[lengths > 0.0]
    if positive_edges.size:
        median_edge = float(np.median(positive_edges))
        gap_strength = float(positive_edges.max() / median_edge) if median_edge > 0 else 1.0
    else:
        gap_strength = 1.0
    threshold = _gap_threshold(positive_edges, gap_multiplier)
    labels = _component_labels(len(matrix), edges, threshold)
    return OccupancyGeometry(
        n_occurrences=int(matrix.shape[0]),
        n_features=int(matrix.shape[1]),
        span=span,
        mst_length=mst_length,
        continuity=continuity,
        gap_strength=gap_strength,
        component_count=int(labels.max() + 1),
        labels=labels,
        mst_edges=edges,
    )


def project_states(
    occurrence_values: np.ndarray,
    candidate_values: np.ndarray,
    geometry: OccupancyGeometry,
) -> tuple[np.ndarray, np.ndarray]:
    """Project candidates to the nearest occupied state and its component.

    Returns ``(nearest_distance, component_label)``. This is deliberately a
    diagnostic projection, not a suitability score or recommendation ranking.
    """
    occurrences = _feature_matrix(occurrence_values)
    candidates = np.asarray(candidate_values, dtype=float)
    if candidates.ndim != 2 or candidates.shape[1] != occurrences.shape[1]:
        raise ValueError("candidate_values must match the occurrence feature dimension")
    if not np.isfinite(candidates).all():
        raise ValueError("candidate_values contains non-finite entries")
    if len(geometry.labels) != len(occurrences):
        raise ValueError("geometry labels do not match occurrence rows")
    median = np.median(occurrences, axis=0)
    mad = np.median(np.abs(occurrences - median), axis=0) * 1.4826
    scale = np.where(mad > 0.0, mad, 1.0)
    scaled_occ = (occurrences - median) / scale
    scaled_cand = (candidates - median) / scale
    scaled_occ[:, mad == 0.0] = 0.0
    scaled_cand[:, mad == 0.0] = 0.0
    delta = scaled_cand[:, None, :] - scaled_occ[None, :, :]
    distances = np.sqrt(np.sum(delta * delta, axis=2))
    nearest = np.argmin(distances, axis=1)
    return distances[np.arange(len(candidates)), nearest], geometry.labels[nearest]
