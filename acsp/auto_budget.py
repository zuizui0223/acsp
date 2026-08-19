"""Infer survey effort from a reachable value-cost frontier.

Users do not predeclare field days here. They provide physical movement
constraints: a start hub, an explicit travel matrix, and the movement modes
that are actually available. ACSP evaluates the fixed upstream coverage order
on that reachable network and recommends the value-cost knee: the point after
which extra field effort yields sharply smaller gains in candidate-space
coverage.

This is an operational recommendation, not a biological probability. Monetary
cost is deliberately out of scope unless real prices are supplied separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable, Iterable, Mapping

import numpy as np
import pandas as pd

from .movement_constraints import apply_movement_constraints
from .travel_matrix import estimate_matrix_trip, normalize_travel_time_matrix

TripEstimator = Callable[..., Mapping[str, object]]


@dataclass(frozen=True)
class AutoEffortAudit:
    selected_count: int
    recommended_days: int
    recommended_total_hours: float
    cumulative_coverage_fraction: float
    knee_score: float
    evaluated_prefixes: int
    unreachable_prefixes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "selected_count": self.selected_count,
            "recommended_days": self.recommended_days,
            "recommended_total_hours": self.recommended_total_hours,
            "cumulative_coverage_fraction": self.cumulative_coverage_fraction,
            "knee_score": self.knee_score,
            "evaluated_prefixes": self.evaluated_prefixes,
            "unreachable_prefixes": self.unreachable_prefixes,
        }


def infer_recommended_effort(
    ordered_sites: pd.DataFrame,
    *,
    hub_latitude: float,
    hub_longitude: float,
    trip_estimator: TripEstimator,
    survey_protocol: Mapping[str, object],
    max_sites: int | None = None,
) -> tuple[pd.DataFrame, AutoEffortAudit, pd.DataFrame]:
    """Return the reachable prefix at the coverage-versus-effort knee.

    ``ordered_sites`` must already be ordered by the set-level survey selector
    and contain ``cumulative_coverage_fraction``. No target-day budget is
    accepted. Each prefix is scheduled with a deliberately non-binding day
    ceiling; unreachable prefixes remain in the audit but cannot be selected.

    The knee is the feasible prefix maximizing ``normalized coverage -
    normalized total hours``. This is deterministic and favors the point of
    strongest diminishing returns. Exact ties prefer the shorter prefix.
    """
    if not callable(trip_estimator):
        raise TypeError("trip_estimator must be callable")
    if "cumulative_coverage_fraction" not in ordered_sites.columns:
        raise ValueError("ordered_sites lacks cumulative_coverage_fraction")
    if max_sites is not None and int(max_sites) < 1:
        raise ValueError("max_sites must be at least 1 when supplied")

    ordered = ordered_sites.copy().reset_index(drop=True)
    if ordered.empty:
        raise ValueError("ordered_sites must contain at least one site")
    limit = len(ordered) if max_sites is None else min(len(ordered), int(max_sites))

    rows: list[dict[str, object]] = []
    for k in range(1, limit + 1):
        prefix = ordered.iloc[:k].copy()
        result = dict(
            trip_estimator(
                prefix,
                float(hub_latitude),
                float(hub_longitude),
                survey_protocol=survey_protocol,
                target_days=max(366, limit * 10),
            )
        )
        unreachable = result.get("unreachable_site_ids", []) or []
        total_hours = pd.to_numeric(pd.Series([result.get("total_hours")]), errors="coerce").iloc[0]
        estimated_days = pd.to_numeric(pd.Series([result.get("estimated_days")]), errors="coerce").iloc[0]
        coverage = float(pd.to_numeric(prefix["cumulative_coverage_fraction"], errors="coerce").iloc[-1])
        feasible = len(unreachable) == 0 and pd.notna(total_hours) and np.isfinite(float(total_hours))
        rows.append({
            "k": int(k),
            "cumulative_coverage_fraction": coverage,
            "total_hours": float(total_hours) if pd.notna(total_hours) else np.nan,
            "estimated_days": int(estimated_days) if pd.notna(estimated_days) else np.nan,
            "reachable": bool(feasible),
            "unreachable_site_ids": list(unreachable),
        })

    frontier = pd.DataFrame(rows)
    feasible = frontier[frontier["reachable"]].copy()
    if feasible.empty:
        raise ValueError("No non-empty ordered prefix is reachable under the supplied movement constraints")

    max_hours = float(feasible["total_hours"].max())
    if max_hours <= 0:
        feasible["normalized_effort"] = 0.0
    else:
        feasible["normalized_effort"] = feasible["total_hours"].astype(float) / max_hours
    feasible["normalized_coverage"] = feasible["cumulative_coverage_fraction"].astype(float).clip(0.0, 1.0)
    feasible["knee_score"] = feasible["normalized_coverage"] - feasible["normalized_effort"]

    best_score = float(feasible["knee_score"].max())
    chosen = feasible[np.isclose(feasible["knee_score"], best_score)].sort_values("k", kind="mergesort").iloc[0]
    selected_count = int(chosen["k"])
    selected = ordered.iloc[:selected_count].copy()

    frontier = frontier.merge(
        feasible[["k", "normalized_effort", "normalized_coverage", "knee_score"]],
        on="k",
        how="left",
    )
    frontier["recommended"] = frontier["k"].eq(selected_count)

    audit = AutoEffortAudit(
        selected_count=selected_count,
        recommended_days=int(chosen["estimated_days"]),
        recommended_total_hours=float(chosen["total_hours"]),
        cumulative_coverage_fraction=float(chosen["cumulative_coverage_fraction"]),
        knee_score=best_score,
        evaluated_prefixes=int(limit),
        unreachable_prefixes=int((~frontier["reachable"]).sum()),
    )
    return selected, audit, frontier


def infer_recommended_effort_from_matrix(
    ordered_sites: pd.DataFrame,
    *,
    travel_matrix: pd.DataFrame,
    hub_id: object,
    allowed_modes: Iterable[str],
    survey_protocol: Mapping[str, object],
    max_sites: int | None = None,
    undirected: bool = False,
) -> tuple[pd.DataFrame, AutoEffortAudit, pd.DataFrame]:
    """Infer survey effort using only explicitly allowed movement edges.

    This is the preferred automatic operational interface. There is no user
    day budget and no straight-line routing fallback. ``allowed_modes`` defines
    the human movement network; every other edge is removed before scheduling.
    Missing edges remain unreachable.
    """
    normalized = normalize_travel_time_matrix(travel_matrix, undirected=undirected)
    constrained = apply_movement_constraints(normalized, allowed_modes=allowed_modes)
    if constrained.empty:
        raise ValueError("No travel edges remain after applying movement constraints")
    estimator = partial(
        estimate_matrix_trip,
        travel_matrix=constrained,
        hub_id=hub_id,
    )
    selected, audit, frontier = infer_recommended_effort(
        ordered_sites,
        hub_latitude=0.0,
        hub_longitude=0.0,
        trip_estimator=estimator,
        survey_protocol=survey_protocol,
        max_sites=max_sites,
    )
    frontier.attrs["allowed_modes"] = list(constrained.attrs.get("allowed_modes", []))
    frontier.attrs["removed_edge_count"] = int(constrained.attrs.get("removed_edge_count", 0))
    return selected, audit, frontier
