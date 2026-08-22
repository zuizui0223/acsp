"""One-input OSM transport reachability pipeline for ACSP candidate patches."""
from __future__ import annotations

import pandas as pd

from .osm_ferry import fetch_osm_ferry_edges_for_patches
from .osm_ferry_stops import fetch_osm_ferry_stop_edges_for_patches
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
    """Fetch OSM road/trail/ferry topology and derive patch reachability.

    The sole movement tuning input is ``max_network_transition_km``. The same
    distance controls the automatic OSM query margins and the weighted network
    transition limit. Road/trail provider failures and ferry-provider failures
    remain explicit; neither triggers candidate straight-line connectivity.

    Direct ferry ways use exact shared OSM endpoint node IDs already present in
    the land highway network. Relation-only ferry routes are reconstructed from
    their member-way raw-node graph. Relation members with role ``stop`` are
    additionally audited and may serve as terminals only when the same raw OSM
    node is explicitly present in both the ferry member-way graph and the land
    highway graph. Proximity-based terminal snapping is never used.

    Returns ``(patch_edges, attachments, network_nodes, network_edges,
    area_provider_audit, audit)``.
    """
    if float(max_network_transition_km) <= 0.0:
        raise ValueError("max_network_transition_km must be positive")

    nodes, road_edges, area_audit, provider_audit = fetch_osm_transport_network_for_patches(
        candidates,
        query_margin_km=float(max_network_transition_km),
        area_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )
    ferry_edges, _ferry_pair_audit, ferry_audit = fetch_osm_ferry_edges_for_patches(
        candidates,
        nodes,
        max_network_transition_km=float(max_network_transition_km),
        area_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )
    ferry_stop_edges, _ferry_stop_rows, ferry_stop_audit = fetch_osm_ferry_stop_edges_for_patches(
        candidates,
        nodes,
        max_network_transition_km=float(max_network_transition_km),
        area_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )

    edge_tables = [
        frame
        for frame in (road_edges, ferry_edges, ferry_stop_edges)
        if frame is not None and not frame.empty
    ]
    if not edge_tables:
        network_edges = road_edges.copy()
    elif len(edge_tables) == 1:
        network_edges = edge_tables[0].copy()
    else:
        network_edges = pd.concat(edge_tables, ignore_index=True, sort=False)
        network_edges = network_edges.sort_values("distance_m").drop_duplicates(
            subset=["from_node_id", "to_node_id"], keep="first"
        ).reset_index(drop=True)

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
        "ferry_edges_included": bool(len(ferry_edges) or len(ferry_stop_edges)),
        "ferry_relation_only_support": True,
        "ferry_relation_stop_support": True,
        "ferry_proximity_terminal_fallback": False,
        "ferry_access_restrictions_enforced": False,
        "route_time_claim": False,
        "timetable_claim": False,
        "legal_access_claim": False,
        "safety_claim": False,
        "field_efficiency_claim": False,
        "provider": provider_audit.as_dict(),
        "ferry_provider": ferry_audit.as_dict(),
        "ferry_stop_provider": ferry_stop_audit.as_dict(),
        "reachability": reachability_audit.as_dict(),
    }
    return patch_edges, attachments, nodes, network_edges, area_audit, audit
