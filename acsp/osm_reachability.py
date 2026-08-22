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
    audited explicitly. If a ferry stop is on the ferry member-way graph but is
    missing from the candidate-window highway graph, ACSP performs one exact OSM
    node-to-highway reverse lookup. A returned highway component is imported only
    if it also contains a raw OSM node already present in the land graph, giving
    an exact topological anchor. No coordinate-distance terminal snapping exists.

    Direct/relation ferry matching is then evaluated against the augmented land
    graph. All reachability remains weighted network shortest path; provider
    failures never trigger candidate straight-line connectivity.

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

    # First stop pass is diagnostic. It identifies exact ferry-graph stop nodes
    # missing from the candidate-window highway graph without creating a fallback.
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
        )
    )
    augmented_nodes = _combine_nodes(nodes, extension_nodes)
    augmented_road_edges = _combine_edges(road_edges, extension_edges)

    # If exact reverse lookup imported land topology, re-evaluate stop membership
    # against the augmented graph. Otherwise reuse the first pass and avoid a
    # redundant live provider request.
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

    # Direct and relation-only ferry matching also benefits from any exact land
    # topology imported by the stop-node reverse lookup.
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
        "ferry_stop_provider_before_highway_reverse_lookup": initial_stop_audit.as_dict(),
        "ferry_stop_highway_provider": stop_highway_audit.as_dict(),
        "ferry_stop_provider": ferry_stop_audit.as_dict(),
        "reachability": reachability_audit.as_dict(),
    }
    return patch_edges, attachments, augmented_nodes, network_edges, area_audit, audit
