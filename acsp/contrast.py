"""Local ecological contrast inference for survey selection.

The module does not estimate occurrence probability. It represents each occupied
state by its empirical position within the environmental availability of its own
region, then transfers those relative states to candidate regions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _matrix(values: np.ndarray, *, name: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError(f"{name} must be a non-empty two-dimensional matrix")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} contains non-finite values")
    return matrix


def _groups(values: np.ndarray, *, n_rows: int, name: str) -> np.ndarray:
    groups = np.asarray(values)
    if groups.ndim != 1 or len(groups) != n_rows:
        raise ValueError(f"{name} must contain one label per row")
    return groups


def empirical_contrast(values: np.ndarray, availability: np.ndarray) -> np.ndarray:
    """Map feature values to centred empirical ranks within availability.

    The result lies in [-1, 1]. A value of -1 is below all available states,
    zero is locally typical, and +1 is above all available states. Mid-ranks are
    used for ties, making constant features map to zero rather than appearing
    informative.
    """

    query = _matrix(values, name="values")
    frame = _matrix(availability, name="availability")
    if query.shape[1] != frame.shape[1]:
        raise ValueError("values and availability must have equal columns")

    result = np.empty_like(query, dtype=float)
    for feature in range(query.shape[1]):
        ordered = np.sort(frame[:, feature])
        left = np.searchsorted(ordered, query[:, feature], side="left")
        right = np.searchsorted(ordered, query[:, feature], side="right")
        percentile = (left + right) / (2.0 * len(ordered))
        result[:, feature] = 2.0 * percentile - 1.0
    return result


@dataclass(frozen=True)
class EcologicalContrastOperator:
    """Repeated occupied-relative states inferred across availability regions."""

    group_labels: np.ndarray
    group_contrasts: np.ndarray
    median_contrast: np.ndarray
    feature_reliability: np.ndarray


def fit_ecological_contrast(
    occupied_features: np.ndarray,
    occupied_groups: np.ndarray,
    availability_features: np.ndarray,
    availability_groups: np.ndarray,
) -> EcologicalContrastOperator:
    """Infer group-level occupied contrasts relative to local availability.

    Each group's occupied rows are transformed only against availability rows
    from the same group. Group medians prevent record-rich regions from
    dominating the inferred operator. Feature reliability is the absolute
    median contrast discounted by disagreement among groups.
    """

    occupied = _matrix(occupied_features, name="occupied_features")
    available = _matrix(availability_features, name="availability_features")
    if occupied.shape[1] != available.shape[1]:
        raise ValueError("occupied and availability matrices must have equal columns")
    occupied_group = _groups(occupied_groups, n_rows=len(occupied), name="occupied_groups")
    available_group = _groups(availability_groups, n_rows=len(available), name="availability_groups")

    labels = np.asarray(sorted(set(occupied_group.tolist()), key=str), dtype=object)
    contrasts = []
    retained = []
    for label in labels:
        occ = occupied[occupied_group == label]
        frame = available[available_group == label]
        if len(frame) < 2 or len(occ) < 1:
            continue
        contrasts.append(np.median(empirical_contrast(occ, frame), axis=0))
        retained.append(label)
    if not contrasts:
        raise ValueError("no occupied group has at least two availability rows")

    group_contrasts = np.vstack(contrasts)
    median = np.median(group_contrasts, axis=0)
    disagreement = np.median(np.abs(group_contrasts - median[None, :]), axis=0)
    reliability = np.abs(median) * (1.0 - np.clip(disagreement, 0.0, 1.0))
    return EcologicalContrastOperator(
        group_labels=np.asarray(retained, dtype=object),
        group_contrasts=group_contrasts,
        median_contrast=median,
        feature_reliability=reliability,
    )


def candidate_contrasts(
    candidate_features: np.ndarray,
    candidate_groups: np.ndarray,
    availability_features: np.ndarray,
    availability_groups: np.ndarray,
) -> np.ndarray:
    """Transform candidates relative to the availability of their own group."""

    candidates = _matrix(candidate_features, name="candidate_features")
    available = _matrix(availability_features, name="availability_features")
    if candidates.shape[1] != available.shape[1]:
        raise ValueError("candidate and availability matrices must have equal columns")
    candidate_group = _groups(candidate_groups, n_rows=len(candidates), name="candidate_groups")
    available_group = _groups(availability_groups, n_rows=len(available), name="availability_groups")

    result = np.empty_like(candidates, dtype=float)
    for label in np.unique(candidate_group):
        frame = available[available_group == label]
        if len(frame) < 2:
            raise ValueError(f"candidate group {label!r} has fewer than two availability rows")
        mask = candidate_group == label
        result[mask] = empirical_contrast(candidates[mask], frame)
    return result


def contrast_membership(
    operator: EcologicalContrastOperator,
    contrasts: np.ndarray,
    *,
    bandwidth: float = 0.5,
) -> np.ndarray:
    """Return candidate support for each observed group-level contrast state."""

    values = _matrix(contrasts, name="contrasts")
    if values.shape[1] != operator.group_contrasts.shape[1]:
        raise ValueError("contrast dimensions do not match the operator")
    if bandwidth <= 0:
        raise ValueError("bandwidth must be positive")

    reliability = operator.feature_reliability
    if not np.any(reliability > 0):
        reliability = np.ones_like(reliability)
    reliability = reliability / reliability.sum()
    delta = values[:, None, :] - operator.group_contrasts[None, :, :]
    distance2 = np.sum(reliability[None, None, :] * delta * delta, axis=2)
    return np.exp(-0.5 * distance2 / (bandwidth * bandwidth))


def select_contrast_cover(membership: np.ndarray, *, n_select: int) -> np.ndarray:
    """Select a batch by marginal coverage of occupied contrast states."""

    matrix = _matrix(membership, name="membership")
    if np.any(matrix < 0) or np.any(matrix > 1):
        raise ValueError("membership values must lie in [0, 1]")
    if not 1 <= n_select <= len(matrix):
        raise ValueError("n_select must be between 1 and the candidate count")

    covered = np.zeros(matrix.shape[1], dtype=float)
    available = np.ones(len(matrix), dtype=bool)
    selected = []
    for _ in range(n_select):
        gain = np.maximum(matrix - covered[None, :], 0.0).sum(axis=1)
        gain[~available] = -np.inf
        chosen = int(np.argmax(gain))
        selected.append(chosen)
        available[chosen] = False
        covered = np.maximum(covered, matrix[chosen])
    return np.asarray(selected, dtype=int)
