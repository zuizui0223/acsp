"""Exact OSM highway reverse lookup for unmatched ferry stop nodes.

This module never connects a ferry terminal by coordinate proximity. It asks
Overpass which ``highway=*`` ways explicitly reference unmatched ferry stop raw
OSM node IDs. A returned highway component is imported only if that same raw-node
component also contains at least one node already present in the land transport
graph, providing an exact topological anchor to a declared survey area.
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
    provider: str = "openstreetmap_overpass_ferry_stop_highway_reverse"
    exact_raw_osm_topology_required: bool = True
    proximity_terminal_fallback: bool = False
    candidate_to_terminal_straight_line_used: bool = False
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
            "provider": self.provider,
            "exact_raw_osm_topology_required": self.exact_raw_osm_topology_required,
            "proximity_terminal_fallback": self.proximity_terminal_fallback,
            "candidate_to_terminal_straight_line_used": self.candidate_to_terminal_straight_line_used,
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


def _highway_reverse_query(stop_ids: list[str]) -> str:
    """Query exact node IDs, highway ways referencing them, and complete geometry."""
    ids = sorted({str(value) for value in stop_ids if str(value).strip()})
    if not ids:
        raise ValueError("at least one ferry stop node ID is required")
    if any(not value.isdigit() for value in ids):
        raise ValueError("ferry stop node IDs must be numeric OSM node IDs")
    id_list = ",".join(ids)
    return (
        "[out:json][timeout:25];"
        f"node(id:{id_list})->.st;"
        "way(bn.st)[\"highway\"]->.hw;"
        "(.st;.hw;>;);"
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
    """Import only stop highway components with an exact existing land anchor."""
    queried_stops = set(str(value) for value in stop_ids)
    land_by_raw = _land_nodes_by_raw_osm_id(land_nodes)
    ways = _highway_way_elements(payload)
    referenced_stops: set[str] = set()
    anchored_stops: set[str] = set()
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
        anchor_raw_ids = set(land_by_raw).intersection(component_nodes)
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

    if node_tables:
        extension_nodes = pd.concat(node_tables, ignore_index=True, sort=False)
        extension_nodes = extension_nodes.drop_duplicates(
            subset=["network_node_id"], keep="first"
        ).sort_values("network_node_id").reset_index(drop=True)
    else:
        extension_nodes = _empty_transport_nodes()

    if edge_tables:
        extension_edges = pd.concat(edge_tables, ignore_index=True, sort=False)
        extension_edges = (
            extension_edges.sort_values("distance_m")
            .drop_duplicates(["from_node_id", "to_node_id"], keep="first")
            .sort_values(["from_node_id", "to_node_id"])
            .reset_index(drop=True)
        )
    else:
        extension_edges = _empty_transport_edges()

    counts = {
        "queried_stop_count": int(len(queried_stops)),
        "stops_with_highway_way_count": int(len(referenced_stops)),
        "returned_highway_way_count": int(len(ways)),
        "anchored_stop_count": int(len(anchored_stops)),
        "imported_extension_node_count": int(len(extension_nodes)),
        "imported_extension_edge_count": int(len(extension_edges)),
        "remaining_unconnected_stop_count": int(len(queried_stops - anchored_stops)),
    }
    return extension_nodes, extension_edges, counts


def fetch_explicit_highway_extensions_for_ferry_stops(
    stop_audit: pd.DataFrame,
    land_nodes: pd.DataFrame,
    *,
    overpass_url: str = OVERPASS_API_URL,
    timeout_s: int = DEFAULT_OVERPASS_TIMEOUT_S,
    attempts: int = DEFAULT_OVERPASS_ATTEMPTS,
) -> tuple[pd.DataFrame, pd.DataFrame, OsmFerryStopHighwayAudit]:
    """Reverse-query exact highway ways for unmatched ferry stop raw node IDs."""
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
        )
        return _empty_transport_nodes(), _empty_transport_edges(), audit

    try:
        payload = _post_overpass(
            _highway_reverse_query(stop_ids),
            overpass_url=overpass_url,
            timeout_s=timeout_s,
            attempts=attempts,
        )
        nodes, edges, counts = highway_reverse_payload_to_extensions(
            payload,
            stop_ids,
            land_nodes,
        )
    except Exception:
        audit = OsmFerryStopHighwayAudit(
            queried_stop_count=int(len(stop_ids)),
            stops_with_highway_way_count=0,
            returned_highway_way_count=0,
            anchored_stop_count=0,
            imported_extension_node_count=0,
            imported_extension_edge_count=0,
            remaining_unconnected_stop_count=int(len(stop_ids)),
        )
        return _empty_transport_nodes(), _empty_transport_edges(), audit

    audit = OsmFerryStopHighwayAudit(**counts)
    return nodes, edges, audit
