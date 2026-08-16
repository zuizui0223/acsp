#!/usr/bin/env python3
"""Training-only environmental-mode support for ACSP development.

The implementation reuses the historical ACSP occupancy-geometry idea only for
mode inference: a minimum spanning tree is built in robust-scaled occurrence
feature space and unusually long edges are cut. Candidate support then gives
each inferred mode equal opportunity while holding total eligible-grid size
exactly equal to the current single-envelope q support. This is not a
suitability probability and does not alter the downstream set-level selector.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from campanula_ndvi_microclimate_hybrid import fit_distance_rank
from campanula_worldcover_discovery import nearest_environment, robust_fit, transform


@dataclass(frozen=True)
class ModeGeometry:
    labels: np.ndarray
    component_count: int
    component_sizes: tuple[int, ...]
    gap_threshold: float
    gap_strength: float
    median: np.ndarray
    scale: np.ndarray


def _minimum_spanning_tree(distances: np.ndarray) -> np.ndarray:
    matrix = np.asarray(distances, dtype=float)
    n = matrix.shape[0]
    if matrix.ndim != 2 or matrix.shape != (n, n) or n < 2:
        raise ValueError("distances must be square with at least two rows")
    visited = np.zeros(n, dtype=bool)
    visited[0] = True
    best = matrix[0].copy()
    parent = np.zeros(n, dtype=int)
    edges: list[tuple[int, int, float]] = []
    for _ in range(n - 1):
        candidates = np.where(~visited, best, np.inf)
        target = int(np.argmin(candidates))
        source = int(parent[target])
        edges.append((source, target, float(matrix[source, target])))
        visited[target] = True
        improve = (~visited) & (matrix[target] < best)
        best[improve] = matrix[target, improve]
        parent[improve] = target
    return np.asarray(edges, dtype=float)


def _gap_threshold(edge_lengths: np.ndarray, multiplier: float) -> float:
    edge_lengths = np.asarray(edge_lengths, dtype=float)
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


def infer_modes(
    train_features: pd.DataFrame,
    columns: list[str],
    *,
    gap_multiplier: float = 3.0,
) -> tuple[ModeGeometry, np.ndarray]:
    """Infer deterministic MST-gap modes from complete training rows.

    Returns `(geometry, complete_row_positions)`. Feature scaling is the same
    training median/IQR scaling used by the current nearest-prototype support.
    """
    good = train_features[columns].notna().all(axis=1).to_numpy()
    positions = np.flatnonzero(good)
    if len(positions) < 1:
        raise ValueError("no complete training environmental rows")
    values = train_features.iloc[positions][columns].to_numpy(float)
    median, scale = robust_fit(values)
    scaled = transform(values, median, scale)
    if len(scaled) == 1:
        labels = np.zeros(1, dtype=int)
        return ModeGeometry(labels, 1, (1,), np.inf, 1.0, median, scale), positions

    delta = scaled[:, None, :] - scaled[None, :, :]
    distances = np.sqrt(np.sum(delta * delta, axis=2))
    edges = _minimum_spanning_tree(distances)
    lengths = edges[:, 2]
    positive = lengths[lengths > 0.0]
    threshold = _gap_threshold(positive, float(gap_multiplier))
    labels = _component_labels(len(scaled), edges, threshold)
    counts = np.bincount(labels)
    if positive.size:
        median_edge = float(np.median(positive))
        gap_strength = float(np.max(positive) / median_edge) if median_edge > 0 else 1.0
    else:
        gap_strength = 1.0
    geometry = ModeGeometry(
        labels=labels,
        component_count=int(labels.max() + 1),
        component_sizes=tuple(int(x) for x in counts),
        gap_threshold=float(threshold),
        gap_strength=gap_strength,
        median=np.asarray(median, dtype=float),
        scale=np.asarray(scale, dtype=float),
    )
    return geometry, positions


@dataclass
class ModeSupportFamily:
    """Cache all training-only quantities shared by the declared q family."""

    global_rank: np.ndarray
    geometry: ModeGeometry
    good_grid: np.ndarray
    mode_orders: tuple[np.ndarray, ...]
    n_grid: int

    @classmethod
    def build(
        cls,
        grid_features: pd.DataFrame,
        train_features: pd.DataFrame,
        columns: list[str],
        *,
        gap_multiplier: float = 3.0,
    ) -> "ModeSupportFamily":
        _, global_rank = fit_distance_rank(grid_features, train_features, columns)
        geometry, positions = infer_modes(
            train_features, columns, gap_multiplier=gap_multiplier
        )
        good_grid = grid_features[columns].notna().all(axis=1).to_numpy()
        orders: list[np.ndarray] = []
        if geometry.component_count > 1:
            values = train_features.iloc[positions][columns].to_numpy(float)
            pz = transform(values, geometry.median, geometry.scale)
            gz = np.full((len(grid_features), len(columns)), np.nan, dtype=float)
            gz[good_grid] = transform(
                grid_features.loc[good_grid, columns].to_numpy(float),
                geometry.median,
                geometry.scale,
            )
            global_indices = np.arange(len(grid_features), dtype=int)
            for label in range(geometry.component_count):
                distance = np.full(len(grid_features), np.inf, dtype=float)
                if good_grid.any():
                    distance[good_grid] = nearest_environment(
                        gz[good_grid], pz[geometry.labels == label]
                    )
                orders.append(np.lexsort((global_indices, distance)))
        return cls(
            global_rank=np.asarray(global_rank, dtype=float),
            geometry=geometry,
            good_grid=good_grid,
            mode_orders=tuple(orders),
            n_grid=len(grid_features),
        )

    def mask(self, q: float) -> tuple[np.ndarray, dict]:
        q = float(q)
        if not 0.0 < q <= 1.0:
            raise ValueError("q must lie in (0, 1]")
        if q >= 1.0:
            mask = np.ones(self.n_grid, dtype=bool)
            return mask, self._detail(len(mask), self.geometry.component_count == 1)

        global_mask = self.global_rank <= q + 1e-12
        target_count = int(global_mask.sum())
        if self.geometry.component_count == 1 or target_count <= 0:
            return global_mask.copy(), self._detail(target_count, True)

        selected = np.zeros(self.n_grid, dtype=bool)
        pointers = np.zeros(self.geometry.component_count, dtype=int)
        selected_count = 0
        while selected_count < target_count:
            progressed = False
            for mode in range(self.geometry.component_count):
                order = self.mode_orders[mode]
                pointer = int(pointers[mode])
                while pointer < len(order) and (
                    selected[int(order[pointer])] or not self.good_grid[int(order[pointer])]
                ):
                    pointer += 1
                pointers[mode] = pointer
                if pointer >= len(order):
                    continue
                index = int(order[pointer])
                pointers[mode] += 1
                if not selected[index]:
                    selected[index] = True
                    selected_count += 1
                    progressed = True
                if selected_count >= target_count:
                    break
            if not progressed:
                raise RuntimeError("mode-balanced support could not reach target size")
        return selected, self._detail(target_count, False)

    def _detail(self, target_count: int, single_mode: bool) -> dict:
        return {
            "component_count": self.geometry.component_count,
            "component_sizes": list(self.geometry.component_sizes),
            "gap_strength": self.geometry.gap_strength,
            "target_cells": int(target_count),
            "single_mode_identity": bool(single_mode),
        }


def multimodal_support_mask(
    grid_features: pd.DataFrame,
    train_features: pd.DataFrame,
    columns: list[str],
    q: float,
    *,
    gap_multiplier: float = 3.0,
) -> tuple[np.ndarray, dict]:
    """Compatibility helper for one q; multi-q callers should reuse a family."""
    family = ModeSupportFamily.build(
        grid_features,
        train_features,
        columns,
        gap_multiplier=gap_multiplier,
    )
    return family.mask(q)
