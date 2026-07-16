"""Survey selection by ecological hypothesis discrimination.

This module does not estimate suitability or presence probability. It accepts
competing ecological hypotheses evaluated on the same candidate set, constructs
an explicit candidate-by-hypothesis-pair discrimination object, and selects a
survey batch that covers distinct unresolved hypothesis contrasts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _finite_matrix(values: np.ndarray, *, name: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] < 2:
        raise ValueError(f"{name} must contain candidates by at least two hypotheses")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} contains non-finite values")
    return matrix


def _empirical_midrank(values: np.ndarray) -> np.ndarray:
    """Map each hypothesis column to deterministic empirical ranks in [0, 1]."""

    matrix = _finite_matrix(values, name="hypothesis_values")
    ranked = np.empty_like(matrix, dtype=float)
    n = len(matrix)
    for column in range(matrix.shape[1]):
        order = np.argsort(matrix[:, column], kind="mergesort")
        sorted_values = matrix[order, column]
        start = 0
        while start < n:
            stop = start + 1
            while stop < n and sorted_values[stop] == sorted_values[start]:
                stop += 1
            midrank = 0.5 * (start + stop - 1)
            ranked[order[start:stop], column] = 0.5 if n == 1 else midrank / (n - 1)
            start = stop
    return ranked


@dataclass(frozen=True)
class HypothesisDiscrimination:
    """Candidate evidence for separating every pair of ecological hypotheses."""

    normalized_hypotheses: np.ndarray
    hypothesis_pairs: np.ndarray
    pairwise_discrimination: np.ndarray
    pair_weights: np.ndarray


def infer_hypothesis_discrimination(
    hypothesis_values: np.ndarray,
    *,
    hypothesis_priors: np.ndarray | None = None,
) -> HypothesisDiscrimination:
    """Infer candidate-wise disagreement among competing ecological hypotheses.

    Hypothesis columns may be on arbitrary scales. Each is converted to empirical
    midranks before pairwise absolute disagreement is calculated. Optional priors
    weight a pair by the product of its two prior probabilities; uniform priors
    are used by default.
    """

    raw = _finite_matrix(hypothesis_values, name="hypothesis_values")
    normalized = _empirical_midrank(raw)
    hypothesis_count = raw.shape[1]
    pairs = np.asarray(
        [(first, second) for first in range(hypothesis_count) for second in range(first + 1, hypothesis_count)],
        dtype=int,
    )
    discrimination = np.abs(
        normalized[:, pairs[:, 0]] - normalized[:, pairs[:, 1]]
    )

    if hypothesis_priors is None:
        priors = np.full(hypothesis_count, 1.0 / hypothesis_count)
    else:
        priors = np.asarray(hypothesis_priors, dtype=float)
        if priors.shape != (hypothesis_count,) or not np.isfinite(priors).all() or np.any(priors < 0):
            raise ValueError("hypothesis_priors must be a finite non-negative vector")
        total = float(priors.sum())
        if total <= 0:
            raise ValueError("hypothesis_priors must contain positive mass")
        priors = priors / total
    weights = priors[pairs[:, 0]] * priors[pairs[:, 1]]
    weights = weights / weights.sum()
    return HypothesisDiscrimination(
        normalized_hypotheses=normalized,
        hypothesis_pairs=pairs,
        pairwise_discrimination=discrimination,
        pair_weights=weights,
    )


def select_discriminating_sites(
    discrimination: HypothesisDiscrimination,
    *,
    n_select: int,
) -> np.ndarray:
    """Select sites by marginal coverage of unresolved hypothesis pairs.

    The objective is

    ``F(S) = sum_(h,k) w_hk max_(c in S) D[c,h,k]``.

    It rewards a batch that distinguishes different hypothesis pairs rather than
    repeatedly selecting sites where the same pair disagrees.
    """

    matrix = discrimination.pairwise_discrimination
    if not 1 <= int(n_select) <= len(matrix):
        raise ValueError("n_select must be between one and the candidate count")
    covered = np.zeros(matrix.shape[1], dtype=float)
    available = np.ones(len(matrix), dtype=bool)
    selected: list[int] = []
    for _ in range(int(n_select)):
        gain = np.sum(
            discrimination.pair_weights[None, :]
            * np.maximum(matrix - covered[None, :], 0.0),
            axis=1,
        )
        gain[~available] = -np.inf
        chosen = int(np.argmax(gain))
        selected.append(chosen)
        available[chosen] = False
        covered = np.maximum(covered, matrix[chosen])
    return np.asarray(selected, dtype=int)
