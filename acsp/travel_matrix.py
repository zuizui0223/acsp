"""Normalize explicit movement-edge inputs used by ACSP routing.

This module deliberately does not schedule trips or infer missing routes.
Sparse directed edges are validated here; shortest-path reachability and effort
are handled by :mod:`acsp.movement_graph`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_REQUIRED_MATRIX_COLUMNS = {"from_id", "to_id", "travel_minutes"}
_TRUE_VALUES = {"1", "true", "t", "yes", "y"}
_FALSE_VALUES = {"0", "false", "f", "no", "n"}


def _normalize_endpoint(value: object) -> str:
    if value is None or bool(pd.isna(value)):
        raise ValueError("movement-edge endpoint IDs must be non-missing")
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    text = str(value).strip()
    if not text:
        raise ValueError("movement-edge endpoint IDs must be non-empty")
    return text


def _coerce_available(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise ValueError(f"Unsupported available value in movement edges: {value!r}")


def normalize_travel_time_matrix(
    matrix: pd.DataFrame,
    *,
    undirected: bool = False,
) -> pd.DataFrame:
    """Validate and normalize sparse directed movement edges.

    The historical function name is retained for compatibility. Required
    columns are ``from_id``, ``to_id`` and ``travel_minutes``. ``mode`` is
    optional at this layer but is required when an allow-list is applied.
    Missing directed pairs remain missing and therefore unreachable.
    """
    if matrix is None:
        raise ValueError("movement edges are required")
    missing = _REQUIRED_MATRIX_COLUMNS - set(matrix.columns)
    if missing:
        raise ValueError("movement edges lack required columns: " + ", ".join(sorted(missing)))

    work = matrix.copy()
    if "available" in work.columns:
        work = work.loc[work["available"].map(_coerce_available)].copy()
    work["from_id"] = work["from_id"].map(_normalize_endpoint)
    work["to_id"] = work["to_id"].map(_normalize_endpoint)
    work["travel_minutes"] = pd.to_numeric(work["travel_minutes"], errors="coerce")
    if work["travel_minutes"].isna().any() or not np.isfinite(work["travel_minutes"]).all():
        raise ValueError("travel_minutes must be finite numbers")
    if (work["travel_minutes"] < 0).any():
        raise ValueError("travel_minutes must be non-negative")

    if "distance_km" not in work.columns:
        work["distance_km"] = np.nan
    else:
        work["distance_km"] = pd.to_numeric(work["distance_km"], errors="coerce")
        supplied = work["distance_km"].notna()
        if not np.isfinite(work.loc[supplied, "distance_km"]).all():
            raise ValueError("finite distance_km values are required when supplied")
        if (work.loc[supplied, "distance_km"] < 0).any():
            raise ValueError("distance_km must be non-negative")
    if "mode" not in work.columns:
        work["mode"] = "unspecified"
    else:
        work["mode"] = work["mode"].fillna("unspecified").astype(str)

    work = work[["from_id", "to_id", "travel_minutes", "distance_km", "mode"]].reset_index(drop=True)
    duplicated = work.duplicated(["from_id", "to_id"], keep=False)
    if duplicated.any():
        pairs = work.loc[duplicated, ["from_id", "to_id"]].drop_duplicates()
        formatted = ", ".join(f"{row.from_id}->{row.to_id}" for row in pairs.itertuples())
        raise ValueError(f"movement edges contain duplicate directed pairs: {formatted}")

    if undirected and not work.empty:
        lookup = {(row.from_id, row.to_id): row for row in work.itertuples(index=False)}
        for row in work.itertuples(index=False):
            reverse = lookup.get((row.to_id, row.from_id))
            if reverse is None:
                continue
            if not np.isclose(float(row.travel_minutes), float(reverse.travel_minutes)):
                raise ValueError(
                    "undirected movement edges have conflicting reverse travel times for "
                    f"{row.from_id}<->{row.to_id}"
                )
            a = float(row.distance_km) if pd.notna(row.distance_km) else np.nan
            b = float(reverse.distance_km) if pd.notna(reverse.distance_km) else np.nan
            if np.isfinite(a) and np.isfinite(b) and not np.isclose(a, b):
                raise ValueError(
                    "undirected movement edges have conflicting reverse distances for "
                    f"{row.from_id}<->{row.to_id}"
                )
        mirrored = work.rename(columns={"from_id": "to_id", "to_id": "from_id"})
        work = pd.concat([work, mirrored], ignore_index=True).drop_duplicates(
            ["from_id", "to_id"], keep="first"
        )

    return work.sort_values(["from_id", "to_id"], kind="mergesort").reset_index(drop=True)


def read_travel_time_matrix(path: str | Path, *, undirected: bool = False) -> pd.DataFrame:
    """Read and normalize a movement-edge CSV.

    The historical function name is retained so old data-loading code can feed
    the new movement graph without retaining the old budget scheduler.
    """
    matrix_path = Path(path)
    if not matrix_path.is_file():
        raise FileNotFoundError(f"Movement-edge CSV was not found: {matrix_path}")
    raw = pd.read_csv(matrix_path, dtype={"from_id": "string", "to_id": "string"})
    normalized = normalize_travel_time_matrix(raw, undirected=undirected)
    normalized.attrs["source_path"] = str(matrix_path)
    normalized.attrs["undirected_input"] = bool(undirected)
    return normalized
