"""Exact OSM highway topology recovery for unmatched ferry stop nodes.

No ferry terminal is connected by coordinate proximity. The provider first asks
which ``highway=*`` ways explicitly reference each unmatched ferry-stop raw OSM
node. If those direct ways do not already meet the existing land graph, it makes
a second provider-only query for highways inside the same movement-limit radius
around the exact stop-node set. Only the raw-node connected component that
actually contains the stop may be imported, and only when that component also
contains an exact raw OSM node already present in the land transport graph.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .osm_ferry import _land_nodes_by_raw_osm_id
from .osm_transport import (
    DEFAULT_OVERPASS_ATTEMPTS,
    DEFAULT_OVERPASS_TIMEOUT_S,
    OVERPASS_API_URL,
    _post_overpass,
    overpass_ways_to_transport_tables,
)


@dataclass(frozen=True)
class OsmFerryStopHighwayAudit:
    queried_stop_count: int
    stops_with_highway_way_count: int
    returned_highway_way_count: int
    anchored_stop_count: int
    imported_extension_node_count: int
    imported_extension_edge_count: int
    remaining_unconnected_stop_count: int
    bounded_query_count: int = 0
    bounded_query_radius_m: float = 0.0
    bounded_returned_highway_way_count: int = 0
    bounded_stop_component_way_count: int = 0
    bounded_stop_component_node_count: int = 0
    bounded_stop_component_existing_land_anchor_count: int = 0
    provider: str = "openstreetmap_overpass_ferry_stop_highway_topology"
    exact_raw_osm_topology_required: bool = True
    bounded_radius_is_retrieval_only: bool = True
    proximity_terminal_fallback: bool = False
    candidate_to_terminal_straight_line_used: bool = False
    provider_query_failed: bool = False
    direct_query_failed: bool = False
    bounded_query_failed: bool = False
    provider_error: str = ""
    legal_access_claim: bool = False
    safety_claim: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "queried_stop_count": self.queried_stop_count,
            "stops_with_highway_way_count": self.stops_with_highway_way_count,
            "returned_highway_way_count": self.returned_highway_way_count,
            "anchored_stop_count": self.anchored_stop_count,
            "imported_extension_node_count": self.imported_extension_node_count,
            "imported_extension_edge_count": self.imported_extension_edge_count,
            "remaining_unconnected_stop_count": self.remaining_unconnected_stop_count,
            "bounded_query_count": self.bounded_query_count,
            "bounded_query_radius_m": self.bounded_query_radius_m,
            "bounded_returned_highway_way_count": self.bounded_returned_highway_way_count,
            "bounded_stop_component_way_count": self.bounded_stop_component_way_count,
            "bounded_stop_component_node_count": self.bounded_stop_component_node_count,
            "bounded_stop_component_existing_land_anchor_count": self.bounded_stop_component_existing_land_anchor_count,
            "provider": self.provider,
            "exact_raw_osm_topology_required": self.exact_raw_osm_topology_required,
            "bounded_radius_is_retrieval_only": self.bounded_radius_is_retrieval_only,
            "proximity_terminal_fallback": self.proximity_terminal_fallback,
            "candidate_to_terminal_straight_line_used": self.candidate_to_terminal_straight_line_used,
            "provider_query_failed": self.provider_query_failed,
            "direct_query_failed": self.direct_query_failed,
            "bounded_query_failed": self.bounded_query_failed,
            "provider_error": self.provider_error,
            "legal_access_claim": self.legal_access_claim,
            "safety_claim": self.safety_claim,
        }


def _empty_transport_nodes() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "network_node_id",
            "survey_area_id",
            "latitude",
            "longitude",
            "network_source",
        ]
    )


def _empty_transport_edges() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "from_node_id",
            "to_node_id",
            "distance_m",
            "survey_area_id",
            "network_mode",
            "highway",
            "osm_way_id",
            "network_source",
        ]
    )


def _combine_nodes(*frames: pd.DataFrame) -> pd.DataFrame:
    usable = [frame for frame in frames if frame is not None and not frame.empty]
    if not usable:
        return _empty_transport_nodes()
    return (
        pd.concat(usable, ignore_index=True, sort=False)
        .drop_duplicates("network_node_id", keep="first")
        .sort_values("network_node_id")
        .reset_index(drop=True)
    )


def _combine_edges(*frames: pd.DataFrame) -> pd.DataFrame:
    usable = [frame for frame in frames if frame is not None and not frame.empty]
    if not usable:
        return _empty_transport_edges()
    return (
        pd.concat(usable, ignore_index=True, sort=False)
        .sort_values("distance_m")
        .drop_duplicates(["from_node_id", "to_node_id"], keep="first")
        .sort_values(["from_node_id", "to_node_id"])
        .reset_index(drop=True)
    )


def _unmatched_stop_ids(stop_audit: pd.DataFrame) -> list[str]:
    if stop_audit is None or stop_audit.empty:
        return []
    required = {
        "stop_node_id",
        "in_ferry_member_way_graph",
        "in_land_highway_graph",
    }
    missing = required.difference(stop_audit.columns)
    if missing:
        raise ValueError(f"ferry stop audit lacks required columns: {sorted(missing)}")
    mask = (
        stop_audit["in_ferry_member_way_graph"].astype(bool)
        & ~stop_audit["in_land_highway_graph"].astype(bool)
    )
    return sorted(set(stop_audit.loc[mask, "stop_node_id"].astype(str)))


def _validate_stop_ids(stop_ids: list[str]) -> list[str]:
    ids = sorted({str(value) for value in stop_ids if str(value).strip()})
    if not ids:
        raise ValueError("at least one ferry stop node ID is required")
    if any(not value.isdigit() for value in ids):
        raise ValueError("ferry stop node IDs must be numeric OSM node IDs")
    return ids


def _highway_reverse_query(stop_ids: list[str]) -> str:
    """Query exact stop IDs and highway ways directly referencing them."""
    ids = _validate_stop_ids(stop_ids)
    id_list = ",".join(ids)
    return (
        "[out:json][timeout:25];"
        f"node(id:{id_list})->.st;"
        "way(bn.st)[\"highway\"]->.hw;"
        "node(w.hw)->.hwn;"
        "(.st;.hw;.hwn;);"
        "out body geom;"
    )


def _bounded_highway_query(stop_ids: list[str], radius_m: float) -> str:
    """Retrieve highways in a movement-derived radius around exact stop nodes.

    The radius bounds provider retrieval only. Returned ways do not become
    connected unless raw OSM node topology places them in the stop-containing
    component and that component has an exact existing land-graph anchor.
    """
    ids = _validate_stop_ids(stop_ids)
    radius = float(radius_m)
    if radius <= 0.0:
        raise ValueError("bounded highway query radius must be positive")
    id_list = ",".join(ids)
    return (
        "[out:json][timeout:25];"
        f"node(id:{id_list})->.st;"
        f"way(around.st:{radius:.3f})[\"highway\"]->.hw;"
        "node(w.hw)->.hwn;"
        "(.st;.hw;.hwn;);"
        "out body geom;"
    )


def _highway_way_elements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        element
        for element in payload.get("elements", [])
        if element.get("type") == "way"
        and str((element.get("tags") or {}).get("highway", "")).strip()
        and isinstance(element.get("nodes"), list)
        and len(element.get("nodes")) >= 2
        and isinstance(element.get("geometry"), list)
        and len(element.get("geometry")) == len(element.get("nodes"))
    ]


def _way_components(ways: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group returned highway ways by exact shared raw OSM node IDs."""
    if not ways:
        return []
    node_sets = [set(str(node) for node in way.get("nodes", [])) for way in ways]
    adjacency: list[set[int]] = [set() for _ in ways]
    node_to_ways: dict[str, list[int]] = {}
    for index, nodes in enumerate(node_sets):
        for node in nodes:
            node_to_ways.setdefault(node, []).append(index)
    for indices in node_to_ways.values():
        for left in indices:
            adjacency[left].update(index for index in indices if index != left)

    seen: set[int] = set()
    components: list[list[dict[str, Any]]] = []
    for start in range(len(ways)):
        if start in seen:
            continue
        stack = [start]
        component_indices: list[int] = []
        seen.add(start)
        while stack:
            current = stack.pop()
            component_indices.append(current)
            for neighbour in adjacency[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        components.append([ways[index] for index in sorted(component_indices)])
    return components


def highway_reverse_payload_to_extensions(
    payload: dict[str, Any],
    stop_ids: list[str],
    land_nodes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Import only stop-containing highway components with exact land anchors."""
    queried_stops = set(str(value) for value in stop_ids)
    land_by_raw = _land_nodes_by_raw_osm_id(land_nodes)
    ways = _highway_way_elements(payload)
    referenced_stops: set[str] = set()
    anchored_stops: set[str] = set()
    stop_component_nodes: set[str] = set()
    stop_component_anchors: set[str] = set()
    stop_component_way_count = 0
    node_tables: list[pd.DataFrame] = []
    edge_tables: list[pd.DataFrame] = []

    for way in ways:
        referenced_stops.update(queried_stops.intersection(str(node) for node in way["nodes"]))

    for component in _way_components(ways):
        component_nodes: set[str] = set()
        for way in component:
            component_nodes.update(str(node) for node in way.get("nodes", []))
        component_stops = queried_stops.intersection(component_nodes)
        if not component_stops:
            continue
        stop_component_way_count += len(component)
        stop_component_nodes.update(component_nodes)
        anchor_raw_ids = set(land_by_raw).intersection(component_nodes)
        stop_component_anchors.update(anchor_raw_ids)
        if not anchor_raw_ids:
            continue
        anchor_areas = sorted(
            {
                entry["survey_area_id"]
                for raw_id in anchor_raw_ids
                for entry in land_by_raw[raw_id]
            }
        )
        if not anchor_areas:
            continue
        anchored_stops.update(component_stops)
        component_payload = {"elements": component}
        for area_id in anchor_areas:
            nodes, edges, _counts = overpass_ways_to_transport_tables(
                component_payload,
                survey_area_id=area_id,
            )
            if not nodes.empty:
                node_tables.append(nodes)
            if not edges.empty:
                edge_tables.append(edges)

    extension_nodes = _combine_nodes(*node_tables)
    extension_edges = _combine_edges(*edge_tables)
    counts = {
        "queried_stop_count": int(len(queried_stops)),
        "stops_with_highway_way_count": int(len(referenced_stops)),
        "returned_highway_way_count": int(len(ways)),
        "anchored_stop_count": int(len(anchored_stops)),
        "imported_extension_node_count": int(len(extension_nodes)),
        "imported_extension_edge_count": int(len(extension_edges)),
        "remaining_unconnected_stop_count": int(len(queried_stops - anchored_stops)),
        "stop_component_way_count": int(stop_component_way_count),
        "stop_component_node_count": int(len(stop_component_nodes)),
        "stop_component_existing_land_anchor_count": int(len(stop_component_anchors)),
    }
    return extension_nodes, extension_edges, counts


def _anchored_stop_ids(extension_nodes: pd.DataFrame, stop_ids: list[str]) -> set[str]:
    if extension_nodes is None or extension_nodes.empty:
        return set()
    extension_by_raw = _land_nodes_by_raw_osm_id(extension_nodes)
    return set(str(value) for value in stop_ids).intersection(extension_by_raw)


def fetch_explicit_highway_extensions_for_ferry_stops(
    stop_audit: pd.DataFrame,
    land_nodes: pd.DataFrame,
    *,
    max_network_transition_km: float,
    overpass_url: str = OVERPASS_API_URL,
    timeout_s: int = DEFAULT_OVERPASS_TIMEOUT_S,
    attempts: int = DEFAULT_OVERPASS_ATTEMPTS,
) -> tuple[pd.DataFrame, pd.DataFrame, OsmFerryStopHighwayAudit]:
    """Recover exact land topology for unmatched ferry stops, fail closed.

    First query exact highway ways directly referencing the stop. Stops not
    anchored by that result receive one movement-bounded ``around.<set>`` highway
    query. The radius equals the existing network movement limit and is not a new
    control. Only exact raw-node connected components can be imported.
    """
    movement_km = float(max_network_transition_km)
    if movement_km <= 0.0:
        raise ValueError("max_network_transition_km must be positive")
    stop_ids = _unmatched_stop_ids(stop_audit)
    if not stop_ids:
        audit = OsmFerryStopHighwayAudit(
            queried_stop_count=0,
            stops_with_highway_way_count=0,
            returned_highway_way_count=0,
            anchored_stop_count=0,
            imported_extension_node_count=0,
            imported_extension_edge_count=0,
            remaining_unconnected_stop_count=0,
            bounded_query_radius_m=movement_km * 1000.0,
        )
        return _empty_transport_nodes(), _empty_transport_edges(), audit

    direct_nodes = _empty_transport_nodes()
    direct_edges = _empty_transport_edges()
    direct_counts = {
        "stops_with_highway_way_count": 0,
        "returned_highway_way_count": 0,
    }
    direct_failed = False
    bounded_failed = False
    errors: list[str] = []
    try:
        payload = _post_overpass(
            _highway_reverse_query(stop_ids),
            overpass_url=overpass_url,
            timeout_s=timeout_s,
            attempts=attempts,
        )
        direct_nodes, direct_edges, direct_counts = highway_reverse_payload_to_extensions(
            payload,
            stop_ids,
            land_nodes,
        )
    except Exception as exc:
        direct_failed = True
        errors.append(f"direct:{type(exc).__name__}: {exc}")

    directly_anchored = _anchored_stop_ids(direct_nodes, stop_ids)
    unresolved = sorted(set(stop_ids) - directly_anchored)

    bounded_nodes = _empty_transport_nodes()
    bounded_edges = _empty_transport_edges()
    bounded_counts = {
        "returned_highway_way_count": 0,
        "stop_component_way_count": 0,
        "stop_component_node_count": 0,
        "stop_component_existing_land_anchor_count": 0,
    }
    bounded_query_count = 0
    if unresolved:
        bounded_query_count = 1
        try:
            bounded_payload = _post_overpass(
                _bounded_highway_query(unresolved, movement_km * 1000.0),
                overpass_url=overpass_url,
                timeout_s=timeout_s,
                attempts=attempts,
            )
            bounded_nodes, bounded_edges, bounded_counts = highway_reverse_payload_to_extensions(
                bounded_payload,
                unresolved,
                land_nodes,
            )
        except Exception as exc:
            bounded_failed = True
            errors.append(f"bounded:{type(exc).__name__}: {exc}")

    extension_nodes = _combine_nodes(direct_nodes, bounded_nodes)
    extension_edges = _combine_edges(direct_edges, bounded_edges)
    finally_anchored = _anchored_stop_ids(extension_nodes, stop_ids)
    audit = OsmFerryStopHighwayAudit(
        queried_stop_count=int(len(stop_ids)),
        stops_with_highway_way_count=int(direct_counts.get("stops_with_highway_way_count", 0)),
        returned_highway_way_count=int(direct_counts.get("returned_highway_way_count", 0)),
        anchored_stop_count=int(len(finally_anchored)),
        imported_extension_node_count=int(len(extension_nodes)),
        imported_extension_edge_count=int(len(extension_edges)),
        remaining_unconnected_stop_count=int(len(set(stop_ids) - finally_anchored)),
        bounded_query_count=int(bounded_query_count),
        bounded_query_radius_m=float(movement_km * 1000.0),
        bounded_returned_highway_way_count=int(bounded_counts.get("returned_highway_way_count", 0)),
        bounded_stop_component_way_count=int(bounded_counts.get("stop_component_way_count", 0)),
        bounded_stop_component_node_count=int(bounded_counts.get("stop_component_node_count", 0)),
        bounded_stop_component_existing_land_anchor_count=int(
            bounded_counts.get("stop_component_existing_land_anchor_count", 0)
        ),
        provider_query_failed=bool(direct_failed or bounded_failed),
        direct_query_failed=bool(direct_failed),
        bounded_query_failed=bool(bounded_failed),
        provider_error=" | ".join(errors),
    )
    return extension_nodes, extension_edges, audit
