"""Retrospective evaluation helpers for experimental discovery development.

These functions may read held-out outcomes and therefore MUST NOT be called by
candidate generation or ranking code.  Their purpose is to diagnose the
candidate-universe ceiling before blaming or tuning a selector.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from .evidence import OccurrenceCluster, haversine_km


@dataclass(frozen=True)
class FrameReachabilityAudit:
    candidate_count: int
    heldout_population_count: int
    recovery_radii_km: tuple[float, ...]
    recovered_counts: tuple[int, ...]
    recalls: tuple[float, ...]
    field_outcomes_used: bool = True
    candidate_generation_modified: bool = False
    selector_used: bool = False


def population_reached(
    candidate_frame: pd.DataFrame,
    population: OccurrenceCluster,
    *,
    radius_km: float,
) -> bool:
    if candidate_frame is None or candidate_frame.empty or not population.members:
        return False
    if float(radius_km) < 0:
        raise ValueError("radius_km cannot be negative")
    required = {"latitude", "longitude"}
    missing = sorted(required.difference(candidate_frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing coordinates: {missing}")
    points = list(zip(candidate_frame["latitude"].astype(float), candidate_frame["longitude"].astype(float)))
    return any(
        haversine_km(lat, lon, member_lat, member_lon) <= float(radius_km) + 1e-12
        for lat, lon in points
        for member_lat, member_lon, _ in population.members
    )


def audit_candidate_frame_reachability(
    candidate_frame: pd.DataFrame,
    heldout_populations: Iterable[OccurrenceCluster],
    *,
    recovery_radii_km: Iterable[float] = (0.25, 0.5, 1.0),
) -> FrameReachabilityAudit:
    """Measure the maximum possible recovery of a frozen candidate universe.

    This ignores ranking entirely.  If the full candidate frame cannot reach a
    held-out population at the declared radius, no selector on that frame can
    recover it.
    """
    populations = list(heldout_populations)
    radii = tuple(float(value) for value in recovery_radii_km)
    if not radii or any(value < 0 for value in radii):
        raise ValueError("recovery_radii_km must contain non-negative values")
    if candidate_frame is None or candidate_frame.empty:
        counts = tuple(0 for _ in radii)
    else:
        counts = tuple(
            int(sum(population_reached(candidate_frame, population, radius_km=radius) for population in populations))
            for radius in radii
        )
    denominator = len(populations)
    recalls = tuple(float(count / denominator) if denominator else 0.0 for count in counts)
    return FrameReachabilityAudit(
        candidate_count=int(0 if candidate_frame is None else len(candidate_frame)),
        heldout_population_count=int(denominator),
        recovery_radii_km=radii,
        recovered_counts=counts,
        recalls=recalls,
    )
