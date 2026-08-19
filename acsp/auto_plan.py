"""End-to-end automatic operational planning on an explicit movement graph.

Reachability is applied before set-level coverage selection. This prevents one
unreachable high-coverage candidate from blocking all later reachable sites.
The only caller-supplied operational choices are the explicit movement graph,
hub, and allowed movement modes. Survey size, hours, and days are outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Iterable, Mapping

import pandas as pd

from .auto_budget import AutoEffortAudit, infer_recommended_effort
from .coverage import CoverageSelectionAudit, select_maximum_coverage_sites
from .movement_graph import estimate_hub_roundtrip_effort, hub_roundtrip_table


@dataclass(frozen=True)
class AutoPlanAudit:
    input_candidates: int
    reachable_candidates: int
    unreachable_candidates: int
    coverage: CoverageSelectionAudit
    effort: AutoEffortAudit

    def as_dict(self) -> dict[str, object]:
        return {
            "input_candidates": self.input_candidates,
            "reachable_candidates": self.reachable_candidates,
            "unreachable_candidates": self.unreachable_candidates,
            "coverage": self.coverage.as_dict(),
            "effort": self.effort.as_dict(),
        }


def plan_auto_effort(
    candidates: pd.DataFrame,
    *,
    movement_edges: pd.DataFrame,
    hub_id: object,
    allowed_modes: Iterable[str],
    survey_protocol: Mapping[str, object],
    coverage_radius_km: float = 1.0,
    site_id_col: str = "site_id",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    group_col: str | None = "survey_area_id",
    undirected: bool = False,
) -> tuple[pd.DataFrame, AutoPlanAudit, pd.DataFrame, pd.DataFrame]:
    """Return an automatically sized survey plan from reachable candidates.

    Returns ``(selected, audit, effort_frontier, reachability_table)``.
    Movement reachability is resolved first using two shortest-path passes on
    the explicit graph. Coverage selection is then performed only on candidates
    with a directed hub round trip. No user site-count or day budget is accepted.
    """
    required = {site_id_col, latitude_col, longitude_col}
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError("candidate table lacks required columns: " + ", ".join(sorted(missing)))
    if candidates.empty:
        raise ValueError("candidate table is empty")
    if candidates[site_id_col].isna().any():
        raise ValueError("candidate site IDs must be non-missing")

    work = candidates.copy().reset_index(drop=True)
    work[site_id_col] = work[site_id_col].astype(str).str.strip()
    if work[site_id_col].duplicated().any():
        raise ValueError("candidate site IDs must be unique")

    reachability = hub_roundtrip_table(
        movement_edges,
        hub_id=hub_id,
        site_ids=work[site_id_col].tolist(),
        allowed_modes=allowed_modes,
        undirected=undirected,
    )
    reachable_ids = set(
        reachability.loc[reachability["roundtrip_reachable"], "site_id"].astype(str)
    )
    reachable = work[work[site_id_col].isin(reachable_ids)].copy().reset_index(drop=True)
    if reachable.empty:
        raise ValueError("No candidate has an explicit directed round trip to the hub")

    actual_group = group_col if group_col is not None and group_col in reachable.columns else None
    ordered, coverage_audit = select_maximum_coverage_sites(
        reachable,
        radius_km=float(coverage_radius_km),
        max_sites=len(reachable),
        latitude_col=latitude_col,
        longitude_col=longitude_col,
        group_col=actual_group,
    )
    rename = {}
    if site_id_col != "site_id":
        rename[site_id_col] = "site_id"
    if latitude_col != "latitude":
        rename[latitude_col] = "latitude"
    if longitude_col != "longitude":
        rename[longitude_col] = "longitude"
    ordered = ordered.rename(columns=rename)
    ordered["site_id"] = ordered["site_id"].astype(str)

    estimator = partial(estimate_hub_roundtrip_effort, roundtrip_table=reachability)
    selected, effort_audit, frontier = infer_recommended_effort(
        ordered,
        hub_latitude=0.0,
        hub_longitude=0.0,
        trip_estimator=estimator,
        survey_protocol=survey_protocol,
        max_sites=None,
    )
    audit = AutoPlanAudit(
        input_candidates=int(len(work)),
        reachable_candidates=int(len(reachable)),
        unreachable_candidates=int(len(work) - len(reachable)),
        coverage=coverage_audit,
        effort=effort_audit,
    )
    frontier.attrs["hub_id"] = str(hub_id)
    frontier.attrs["allowed_modes"] = list(reachability.attrs.get("allowed_modes", []))
    frontier.attrs["routing_source"] = "explicit_sparse_movement_graph_hub_roundtrips"
    return selected, audit, frontier, reachability
