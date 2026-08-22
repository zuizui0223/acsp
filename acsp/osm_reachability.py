"""One-input OSM transport reachability pipeline for ACSP candidate patches."""
from __future__ import annotations

import pandas as pd

from .osm_ferry import fetch_osm_ferry_edges_for_patches
from .osm_ferry_stop_highways import fetch_explicit_highway_extensions_for_ferry_stops
from .osm_ferry_stops import fetch_osm_ferry_stop_edges_for_patches
from .osm_transport import fetch_osm_transport_network_for_patches
from .transport_reachability import build_patch_reachability_edges_from_transport_network


def _combine_nodes(base: pd.DataFrame, extension: pd.DataFrame) -> pd.DataFrame:
    if extension is None or extension.empty:
        return base.copy()
    if base is None or base.empty:
        return extension.copy().reset_index(drop=True)
    return (
        pd.concat([base, extension], ignore_index=True, sort=False)
        .drop_duplicates("network_node_id", keep="first")
        .sort_values("network_node_id")
        .reset_index(drop=True)
    )


def _combine_edges(*frames: pd.DataFrame) -> pd.DataFrame:
    usable = [frame for frame in frames if frame is not None and not frame.empty]
    if not usable:
        if frames:
            return frames[0].copy()
        return pd.DataFrame(columns=["from_node_id", "to_node_id", "distance_m"])
    if len(usable) == 1:
        return usable[0].copy().reset_index(drop=True)
    return (
        pd.concat(usable, ignore_index=True, sort=False)
        .sort_values("distance_m")
        .drop_duplicates(["from_node_id", "to_node_id"], keep="first")
        .sort_values(["from_node_id", "to_node_id"])
        .reset_index(drop=True)
    )


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

    The sole movement tuning input is ``max_network_transition_km``. Road/trail
    topology is retrieved around candidates. Ferry relation ``stop`` nodes are
    audited explicitly. If a stop is on the ferry member-way graph but missing
    from the candidate-window highway graph, ACSP first reverse-queries highway
    ways that reference that exact raw OSM node. If those direct ways do not
    reach an existing land-graph raw-node anchor, it retrieves highways within
    the same movement-limit radius around the exact stop-node set and follows
    raw-node connectivity. The radius bounds provider retrieval only; it never
    creates an edge. No coordinate-distance terminal snapping exists.

    Direct/relation ferry matching is evaluated against any exactly anchored
    augmented land graph. All final reachability remains weighted network
    shortest path; provider failures never trigger candidate straight-line
    connectivity.

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

    (
        initial_stop_edges,
        initial_stop_rows,
        initial_stop_audit,
    ) = fetch_osm_ferry_stop_edges_for_patches(
        candidates,
        nodes,
        max_network_transition_km=float(max_network_transition_km),
        area_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )

    extension_nodes, extension_edges, stop_highway_audit = (
        fetch_explicit_highway_extensions_for_ferry_stops(
            initial_stop_rows,
            nodes,
            max_network_transition_km=float(max_network_transition_km),
        )
    )
    augmented_nodes = _combine_nodes(nodes, extension_nodes)
    augmented_road_edges = _combine_edges(road_edges, extension_edges)

    if extension_nodes is not None and not extension_nodes.empty:
        ferry_stop_edges, _final_stop_rows, ferry_stop_audit = (
            fetch_osm_ferry_stop_edges_for_patches(
                candidates,
                augmented_nodes,
                max_network_transition_km=float(max_network_transition_km),
                area_col=area_col,
                latitude_col=latitude_col,
                longitude_col=longitude_col,
            )
        )
    else:
        ferry_stop_edges = initial_stop_edges
        ferry_stop_audit = initial_stop_audit

    ferry_edges, _ferry_pair_audit, ferry_audit = fetch_osm_ferry_edges_for_patches(
        candidates,
        augmented_nodes,
        max_network_transition_km=float(max_network_transition_km),
        area_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )

    network_edges = _combine_edges(
        augmented_road_edges,
        ferry_edges,
        ferry_stop_edges,
    )

    patch_edges, attachments, reachability_audit = build_patch_reachability_edges_from_transport_network(
        candidates,
        augmented_nodes,
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
        "ferry_stop_highway_reverse_lookup": True,
        "ferry_stop_bounded_highway_component_lookup": True,
        "ferry_highway_extension_used": bool(
            extension_nodes is not None and not extension_nodes.empty
        ),
        "ferry_proximity_terminal_fallback": False,
        "ferry_access_restrictions_enforced": False,
        "route_time_claim": False,
        "timetable_claim": False,
        "legal_access_claim": False,
        "safety_claim": False,
        "field_efficiency_claim": False,
        "provider": provider_audit.as_dict(),
        "ferry_provider": ferry_audit.as_dict(),
        "ferry_stop_provider_before_highway_recovery": initial_stop_audit.as_dict(),
        "ferry_stop_highway_provider": stop_highway_audit.as_dict(),
        "ferry_stop_provider": ferry_stop_audit.as_dict(),
        "reachability": reachability_audit.as_dict(),
    }
    return patch_edges, attachments, augmented_nodes, network_edges, area_audit, audit
