"""Operational budget translation for an already ordered survey-site sequence.

This module does not rank sites and does not estimate biological suitability.
It preserves an upstream site order (for example geometry-only maximum coverage)
and asks how long a prefix fits an explicit hub + field-day budget using a
caller-supplied trip estimator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional

import pandas as pd


TripEstimator = Callable[..., Mapping[str, object]]


@dataclass(frozen=True)
class OperationalBudgetAudit:
    """Audit record for a field-day budget translation."""

    target_days: int
    total_ordered_sites: int
    candidate_prefixes_evaluated: int
    selected_count: int
    hub_latitude: float
    hub_longitude: float
    fits_target_days: bool
    max_sites: Optional[int]
    trip_summary: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "target_days": self.target_days,
            "total_ordered_sites": self.total_ordered_sites,
            "candidate_prefixes_evaluated": self.candidate_prefixes_evaluated,
            "selected_count": self.selected_count,
            "hub_latitude": self.hub_latitude,
            "hub_longitude": self.hub_longitude,
            "fits_target_days": self.fits_target_days,
            "max_sites": self.max_sites,
            "trip_summary": dict(self.trip_summary),
        }


def select_largest_feasible_prefix(
    ordered_sites: pd.DataFrame,
    *,
    hub_latitude: float,
    hub_longitude: float,
    target_days: int,
    trip_estimator: TripEstimator,
    survey_protocol: Mapping[str, object] | None = None,
    max_sites: int | None = None,
) -> tuple[pd.DataFrame, OperationalBudgetAudit, pd.DataFrame]:
    """Return the longest upstream-ordered prefix that fits ``target_days``.

    Every prefix is evaluated independently rather than assuming trip
    feasibility is monotone in prefix length. The site order is never changed.
    ``trip_estimator`` must accept ``(plan, hub_latitude, hub_longitude,\n    survey_protocol=..., target_days=...)`` and return a mapping containing a
    boolean-like ``fits_target_days`` field.

    Returns ``(selected_prefix, audit, prefix_audit)``. If no non-empty prefix
    fits, ``selected_prefix`` is empty and ``selected_count`` is zero.
    """
    if int(target_days) < 1:
        raise ValueError("target_days must be at least 1")
    if max_sites is not None and int(max_sites) < 0:
        raise ValueError("max_sites must be non-negative when supplied")
    if not callable(trip_estimator):
        raise TypeError("trip_estimator must be callable")

    ordered = ordered_sites.copy()
    total = len(ordered)
    limit = total if max_sites is None else min(total, int(max_sites))

    prefix_rows: list[dict[str, object]] = []
    feasible: list[tuple[int, dict[str, object]]] = []
    for k in range(1, limit + 1):
        prefix = ordered.iloc[:k].copy()
        result = dict(
            trip_estimator(
                prefix,
                float(hub_latitude),
                float(hub_longitude),
                survey_protocol=survey_protocol,
                target_days=int(target_days),
            )
        )
        fits = bool(result.get("fits_target_days", False))
        row = {"k": int(k), "fits_target_days": fits}
        for key, value in result.items():
            if key == "fits_target_days":
                continue
            row[str(key)] = value
        prefix_rows.append(row)
        if fits:
            feasible.append((int(k), result))

    if feasible:
        selected_count, selected_trip = max(feasible, key=lambda item: item[0])
        selected = ordered.iloc[:selected_count].copy()
        selected_fits = True
    else:
        selected_count = 0
        selected_trip = {}
        selected = ordered.iloc[:0].copy()
        selected_fits = False

    audit = OperationalBudgetAudit(
        target_days=int(target_days),
        total_ordered_sites=int(total),
        candidate_prefixes_evaluated=int(limit),
        selected_count=int(selected_count),
        hub_latitude=float(hub_latitude),
        hub_longitude=float(hub_longitude),
        fits_target_days=bool(selected_fits),
        max_sites=None if max_sites is None else int(max_sites),
        trip_summary=selected_trip,
    )
    return selected, audit, pd.DataFrame(prefix_rows)
