"""Strong same-frame comparators for experimental N4 discovery."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class ComparatorAudit:
    method: str
    input_candidate_count: int
    requested_count: int
    selected_count: int
    memory_complexity: str
    time_complexity_note: str
    field_outcomes_used: bool = False


def _stable_key(candidate_id: object, latitude: float, longitude: float) -> str:
    token = f"{candidate_id}|{float(latitude):.8f}|{float(longitude):.8f}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _work(frame: pd.DataFrame, *, candidate_id_col: str) -> pd.DataFrame:
    required = {candidate_id_col, "latitude", "longitude"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing columns: {missing}")
    out = frame.copy().reset_index(drop=True)
    out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
    out = out.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    if out[candidate_id_col].isna().any() or out[candidate_id_col].astype(str).duplicated().any():
        raise ValueError("candidate IDs must be complete and unique")
    out["_stable_key"] = [
        _stable_key(candidate_id, lat, lon)
        for candidate_id, lat, lon in zip(out[candidate_id_col], out["latitude"], out["longitude"])
    ]
    return out


def rank_nearest_anchor(
    frame: pd.DataFrame,
    *,
    distance_col: str = "nearest_anchor_km",
    candidate_id_col: str = "candidate_cell_id",
) -> pd.DataFrame:
    """Return the complete direct-distance baseline order."""
    work = _work(frame, candidate_id_col=candidate_id_col)
    if distance_col not in work.columns:
        raise ValueError(f"candidate frame missing distance column: {distance_col}")
    work[distance_col] = pd.to_numeric(work[distance_col], errors="coerce")
    if work[distance_col].isna().any() or (work[distance_col] < 0).any():
        raise ValueError("nearest-anchor distance must be complete and non-negative")
    ordered = work.sort_values([distance_col, "_stable_key"], kind="mergesort").drop(columns="_stable_key").reset_index(drop=True)
    ordered["decision_method"] = "ANNULAR_NEAREST_KNOWN"
    ordered["decision_rank"] = range(1, len(ordered) + 1)
    return ordered


def _distance_vector(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    p1 = math.radians(float(lat))
    p2 = np.radians(lats.astype(float))
    dp = p2 - p1
    dl = np.radians(lons.astype(float) - float(lon))
    value = np.sin(dp / 2.0) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(value, 0.0, 1.0)))


def select_stable_start_maximin(
    frame: pd.DataFrame,
    *,
    count: int,
    candidate_id_col: str = "candidate_cell_id",
) -> tuple[pd.DataFrame, ComparatorAudit]:
    """Memory-safe deterministic geographic maximin selection.

    The first point is the smallest stable candidate hash; subsequent points
    maximize distance to the nearest already selected point. This matches the
    explicitly frozen development comparator used by the 96-pair public test.
    It avoids an n-by-n distance matrix, but a very large full ranking remains
    O(n^2) time. Callers must not silently switch comparator algorithms by size.
    """
    work = _work(frame, candidate_id_col=candidate_id_col)
    requested = int(count)
    if requested < 0:
        raise ValueError("count cannot be negative")
    target = min(requested, len(work))
    if target == 0:
        selected = work.iloc[:0].drop(columns="_stable_key").copy()
        return selected, ComparatorAudit(
            method="stable_start_maximin",
            input_candidate_count=int(len(work)),
            requested_count=requested,
            selected_count=0,
            memory_complexity="O(n)",
            time_complexity_note="O(n*k)",
        )

    keys = work["_stable_key"].astype(str).to_numpy()
    lats = work["latitude"].to_numpy(float)
    lons = work["longitude"].to_numpy(float)
    first = int(np.argmin(keys))
    selected_indices = [first]
    chosen = np.zeros(len(work), dtype=bool)
    chosen[first] = True
    nearest = _distance_vector(lats[first], lons[first], lats, lons)
    nearest[first] = -np.inf

    while len(selected_indices) < target:
        candidates = np.where(~chosen)[0]
        best_distance = float(np.max(nearest[candidates]))
        tied = candidates[np.isclose(nearest[candidates], best_distance, rtol=0.0, atol=1e-12)]
        best = int(min(tied, key=lambda index: keys[int(index)]))
        selected_indices.append(best)
        chosen[best] = True
        nearest = np.minimum(nearest, _distance_vector(lats[best], lons[best], lats, lons))
        nearest[chosen] = -np.inf

    selected = work.iloc[selected_indices].drop(columns="_stable_key").reset_index(drop=True)
    selected["decision_method"] = "DETERMINISTIC_SPATIAL_BALANCE"
    selected["decision_rank"] = range(1, len(selected) + 1)
    return selected, ComparatorAudit(
        method="stable_start_maximin",
        input_candidate_count=int(len(work)),
        requested_count=requested,
        selected_count=int(len(selected)),
        memory_complexity="O(n)",
        time_complexity_note="O(n*k); full k=n is quadratic time",
    )


def _morton_code(row: int, col: int) -> int:
    """Interleave non-negative grid bits into one deterministic Morton code."""
    rr = int(row)
    cc = int(col)
    if rr < 0 or cc < 0:
        raise ValueError("Morton coordinates must be non-negative after normalization")
    bits = max(1, rr.bit_length(), cc.bit_length())
    code = 0
    for bit in range(bits):
        code |= ((cc >> bit) & 1) << (2 * bit)
        code |= ((rr >> bit) & 1) << (2 * bit + 1)
    return code


def _dyadic_positions(length: int) -> list[int]:
    """Return endpoint-first recursive midpoint positions covering every index once."""
    n = int(length)
    if n <= 0:
        return []
    if n == 1:
        return [0]
    order = [0, n - 1]
    seen = {0, n - 1}
    intervals = [(0, n - 1)]
    cursor = 0
    while cursor < len(intervals):
        left, right = intervals[cursor]
        cursor += 1
        if right - left <= 1:
            continue
        middle = (left + right) // 2
        if middle not in seen:
            order.append(middle)
            seen.add(middle)
        intervals.append((left, middle))
        intervals.append((middle, right))
    if len(order) < n:
        order.extend(index for index in range(n) if index not in seen)
    if len(order) != n or len(set(order)) != n:
        raise AssertionError("dyadic coverage order is not a complete permutation")
    return order


def rank_morton_dyadic_spatial_balance(
    frame: pd.DataFrame,
    *,
    candidate_id_col: str = "candidate_cell_id",
    grid_row_col: tuple[str, str] = ("grid_row", "grid_col"),
) -> tuple[pd.DataFrame, ComparatorAudit]:
    """Return an O(n log n) progressively distributed grid order.

    Candidates are first placed on the space-filling Morton curve using their
    declared regular-grid indices. The sequence then visits both ends and
    recursively bisects the sorted curve, yielding a deterministic multiscale
    coverage order without constructing pairwise distances.

    This is a distinct comparator identity: ``MORTON_DYADIC_COVERAGE_ORDER_V1``.
    It is not GRTS and must never silently replace the separately frozen maximin
    comparator in experiments that predeclared maximin.
    """
    work = _work(frame, candidate_id_col=candidate_id_col)
    row_col, col_col = grid_row_col
    for column in (row_col, col_col):
        if column not in work.columns:
            raise ValueError(f"candidate frame missing grid column: {column}")
        numeric = pd.to_numeric(work[column], errors="coerce")
        if numeric.isna().any() or not np.allclose(numeric.to_numpy(float), np.rint(numeric.to_numpy(float))):
            raise ValueError(f"grid column must be complete and integer-valued: {column}")
        work[column] = np.rint(numeric.to_numpy(float)).astype(np.int64)
    rows = work[row_col].to_numpy(np.int64)
    cols = work[col_col].to_numpy(np.int64)
    rows = rows - int(rows.min())
    cols = cols - int(cols.min())
    work["_morton"] = [_morton_code(int(row), int(col)) for row, col in zip(rows, cols)]
    along_curve = work.sort_values(["_morton", "_stable_key"], kind="mergesort").reset_index(drop=True)
    positions = _dyadic_positions(len(along_curve))
    ordered = along_curve.iloc[positions].drop(columns=["_morton", "_stable_key"]).reset_index(drop=True)
    ordered["decision_method"] = "DETERMINISTIC_SPATIAL_BALANCE"
    ordered["decision_rank"] = range(1, len(ordered) + 1)
    return ordered, ComparatorAudit(
        method="MORTON_DYADIC_COVERAGE_ORDER_V1",
        input_candidate_count=int(len(work)),
        requested_count=int(len(work)),
        selected_count=int(len(ordered)),
        memory_complexity="O(n)",
        time_complexity_note="O(n log n) sort plus O(n log coordinate-range) Morton coding",
    )
