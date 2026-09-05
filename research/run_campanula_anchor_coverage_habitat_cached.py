"""Runtime-only wrapper for the frozen coverage-constrained habitat selector.

The scientific selector is unchanged. This wrapper replaces only the implementation of
repeated Morton ordering with an equivalent cached/numpy implementation so each annular
frame is ordered once and reused across the six declared selection fractions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import evaluate_campanula_anchor_coverage_habitat as base
from evaluate_campanula_anchor_spatial_balance import morton_order

_CACHE_KEY = "_coverage_habitat_morton_order_v1"


def cached_coverage_constrained_habitat_sample(
    frame: pd.DataFrame, count: int
) -> pd.DataFrame:
    """Exact semantic equivalent of the frozen selector with cached Morton order."""
    target = int(count)
    if target < 0:
        raise ValueError("count must be non-negative")
    if target == 0 or frame.empty:
        return frame.iloc[0:0].copy()
    if "environment_distance" not in frame.columns:
        raise ValueError("frame must contain environment_distance")
    if target >= len(frame):
        return frame.copy().reset_index(drop=True)

    distance = pd.to_numeric(frame["environment_distance"], errors="coerce").to_numpy(float)
    if not np.isfinite(distance).all():
        raise ValueError("environment_distance must be complete and finite")
    stable_ids = pd.to_numeric(frame["candidate_cell_id"], errors="coerce").to_numpy(float)
    if not np.isfinite(stable_ids).all():
        raise ValueError("candidate_cell_id must be complete and finite")

    cached = frame.attrs.get(_CACHE_KEY)
    if cached is None:
        order = morton_order(frame)
        frame.attrs[_CACHE_KEY] = order.copy()
    else:
        order = np.asarray(cached, dtype=int)
        if order.shape != (len(frame),):
            raise RuntimeError("cached Morton order shape drifted")

    boundaries = np.floor(np.arange(target + 1, dtype=float) * len(order) / target).astype(int)
    boundaries[-1] = len(order)
    chosen: list[int] = []
    for start, stop in zip(boundaries[:-1], boundaries[1:], strict=True):
        if stop <= start:
            raise RuntimeError("Morton coverage stratum unexpectedly empty")
        candidate_indices = order[start:stop]
        local_order = np.lexsort(
            (stable_ids[candidate_indices], distance[candidate_indices])
        )
        chosen.append(int(candidate_indices[int(local_order[0])]))
    if len(set(chosen)) != target:
        raise RuntimeError("coverage-constrained habitat selection produced duplicates")
    return frame.iloc[chosen].copy().reset_index(drop=True)


def main() -> None:
    base.coverage_constrained_habitat_sample = cached_coverage_constrained_habitat_sample
    base.main()


if __name__ == "__main__":
    main()
