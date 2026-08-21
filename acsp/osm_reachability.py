"""One-input OSM transport reachability pipeline for ACSP candidate patches."""
from __future__ import annotations

import pandas as pd

from .osm_transport import fetch_osm_transport_network_for_patches
from .transport_reachability import build_patch_reachability_edges_from_transport_network


def build_osm_patch_reachability_edges(
    candidates: pd.DataFrame,
    *,
    max_network_transition_km: float,
    area_col: str = "survey_area_id",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, object],
]:
    """Fetch OSM road/trail topology and derive explicit patch reachability.

    The sole movement tuning input is ``max_network_transition_km``. The same
    distance is used as the automatic per-area OSM query margin, so callers do
    not choose a separate fetch radius. Provider failures remain explicit: an
    area with no returned network leaves its candidates unattached and does not
    trigger a geometric candidate-to-candidate fallback.

    Returns ``(patch_edges, attachments, network_nodes, network_edges,
    area_provider_audit, audit)``.
    """
    if float(max_network_transition_km) <= 0.0:
        raise ValueError("max_network_transition_km must be positive")

    nodes, network_edges, area_audit, provider_audit = fetch_osm_transport_network_for_patches(
        candidates,
        query_margin_km=float(max_network_transition_km),
        area_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )
    patch_edges, attachments, reachability_audit = build_patch_reachability_edges_from_transport_network(
        candidates,
        nodes,
        network_edges,
        max_network_transition_km=float(max_network_transition_km),
        candidate_group_col=area_col,
        network_group_col="survey_area_id",
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )
    audit: dict[str, object] = {
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": float(max_network_transition_km),
        "query_margin_derived_from_movement_limit": True,
        "candidate_pair_straight_line_used": False,
        "straight_line_candidate_fallback": False,
        "ferry_edges_included": False,
        "route_time_claim": False,
        "legal_access_claim": False,
        "safety_claim": False,
        "field_efficiency_claim": False,
        "provider": provider_audit.as_dict(),
        "reachability": reachability_audit.as_dict(),
    }
    return patch_edges, attachments, nodes, network_edges, area_audit, audit
