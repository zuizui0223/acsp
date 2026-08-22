"""Explicit OSM ferry-relation stop terminals for ACSP transport networks.

This provider diagnoses and uses only relation node members with role ``stop``.
A stop can become a ferry/land interchange only when the same raw OSM node ID
is present both in the relation's ferry member-way graph and in the already
retrieved land highway graph. No coordinate-distance terminal snapping exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd

from .osm_ferry import (
    _edge_row,
    _empty_ferry_edges,
    _land_nodes_by_raw_osm_id,
    _minimum_area_distance_km,
    _raw_graph_distances,
    _relation_way_graph,
)
from .osm_transport import (
    DEFAULT_OVERPASS_ATTEMPTS,
    DEFAULT_OVERPASS_TIMEOUT_S,
    OVERPASS_API_URL,
    _area_bounds,
    _post_overpass,
)


_STOP_AUDIT_COLUMNS = [
    "ferry_relation_id",
    "stop_node_id",
    "role",
    "amenity",
    "public_transport",
    "ferry",
    "name",
    "operator",
    "ref",
    "node_body_present",
    "in_ferry_member_way_graph",
    "in_land_highway_graph",
    "exact_terminal_usable",
]


@dataclass(frozen=True)
class OsmFerryStopProviderAudit:
    query_count: int
    successful_query_count: int
    failed_query_count: int
    ferry_relation_count: int
    relation_stop_member_count: int
    unique_stop_node_count: int
    ferry_terminal_tagged_stop_count: int
    public_transport_ferry_stop_count: int
    stop_in_ferry_graph_count: int
    stop_in_land_graph_count: int
    stop_in_both_graphs_count: int
    unmatched_land_stop_count: int
    emitted_ferry_edge_count: int
    provider: str = "openstreetmap_overpass_ferry_relation_stops"
    relation_stop_role_required: bool = True
    exact_raw_osm_node_match_required: bool = True
    proximity_terminal_fallback: bool = False
    timetable_claim: bool = False
    service_currentness_claim: bool = False
    legal_access_claim: bool = False
    safety_claim: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "query_count": self.query_count,
            "successful_query_count": self.successful_query_count,
            "failed_query_count": self.failed_query_count,
            "ferry_relation_count": self.ferry_relation_count,
            "relation_stop_member_count": self.relation_stop_member_count,
            "unique_stop_node_count": self.unique_stop_node_count,
            "ferry_terminal_tagged_stop_count": self.ferry_terminal_tagged_stop_count,
            "public_transport_ferry_stop_count": self.public_transport_ferry_stop_count,
            "stop_in_ferry_graph_count": self.stop_in_ferry_graph_count,
            "stop_in_land_graph_count": self.stop_in_land_graph_count,
            "stop_in_both_graphs_count": self.stop_in_both_graphs_count,
            "unmatched_land_stop_count": self.unmatched_land_stop_count,
            "emitted_ferry_edge_count": self.emitted_ferry_edge_count,
            "provider": self.provider,
            "relation_stop_role_required": self.relation_stop_role_required,
            "exact_raw_osm_node_match_required": self.exact_raw_osm_node_match_required,
            "proximity_terminal_fallback": self.proximity_terminal_fallback,
            "timetable_claim": self.timetable_claim,
            "service_currentness_claim": self.service_currentness_claim,
            "legal_access_claim": self.legal_access_claim,
            "safety_claim": self.safety_claim,
        }


def _empty_stop_audit() -> pd.DataFrame:
    return pd.DataFrame(columns=_STOP_AUDIT_COLUMNS)


def _ferry_stop_query(west: float, south: float, east: float, north: float) -> str:
    """Return ferry relations, member ways, and member node bodies/tags."""
    bbox = f"{float(south):.7f},{float(west):.7f},{float(north):.7f},{float(east):.7f}"
    return (
        "[out:json][timeout:25];"
        f"relation[\"type\"=\"route\"][\"route\"=\"ferry\"]({bbox})->.fr;"
        "way(r.fr)->.fw;"
        "node(r.fr)->.fn;"
        "(.fr;.fw;.fn;);"
        "out body geom;"
    )


def ferry_relation_stops_to_transport_edges(
    payload: dict[str, Any],
    land_nodes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Diagnose ferry ``stop`` members and emit exact-topology ferry edges.

    A usable terminal must satisfy all of the following:
    - it is a node member of a ``type=route, route=ferry`` relation with role
      exactly ``stop``;
    - its raw OSM node ID occurs in the relation's reconstructed member-way graph;
    - the same raw OSM node ID occurs in the supplied land highway graph.

    Coordinates and terminal proximity are never used to create connectivity.
    """
    land_by_raw = _land_nodes_by_raw_osm_id(land_nodes)
    elements = payload.get("elements", [])
    way_by_id = {
        str(element.get("id")): element
        for element in elements
        if element.get("type") == "way" and element.get("id") is not None
    }
    node_by_id = {
        str(element.get("id")): element
        for element in elements
        if element.get("type") == "node" and element.get("id") is not None
    }
    relations = [
        element
        for element in elements
        if element.get("type") == "relation"
        and str((element.get("tags") or {}).get("type", "")) == "route"
        and str((element.get("tags") or {}).get("route", "")) == "ferry"
    ]

    edge_rows: dict[tuple[str, str], dict[str, object]] = {}
    stop_rows: list[dict[str, object]] = []
    relation_stop_member_count = 0

    for relation in relations:
        relation_id = str(relation.get("id", "unknown"))
        relation_tags = relation.get("tags") or {}
        adjacency, _valid_members, _incomplete_members = _relation_way_graph(
            relation, way_by_id
        )
        stop_refs = [
            str(member.get("ref"))
            for member in relation.get("members", [])
            if member.get("type") == "node"
            and str(member.get("role", "")) == "stop"
            and member.get("ref") is not None
        ]
        relation_stop_member_count += len(stop_refs)
        usable_raw_ids: list[str] = []

        for raw_id in stop_refs:
            node = node_by_id.get(raw_id)
            tags = (node or {}).get("tags") or {}
            in_ferry_graph = raw_id in adjacency
            in_land_graph = raw_id in land_by_raw
            usable = bool(in_ferry_graph and in_land_graph)
            if usable:
                usable_raw_ids.append(raw_id)
            stop_rows.append(
                {
                    "ferry_relation_id": relation_id,
                    "stop_node_id": raw_id,
                    "role": "stop",
                    "amenity": str(tags.get("amenity", "")),
                    "public_transport": str(tags.get("public_transport", "")),
                    "ferry": str(tags.get("ferry", "")),
                    "name": str(tags.get("name", "")),
                    "operator": str(tags.get("operator", "")),
                    "ref": str(tags.get("ref", "")),
                    "node_body_present": node is not None,
                    "in_ferry_member_way_graph": bool(in_ferry_graph),
                    "in_land_highway_graph": bool(in_land_graph),
                    "exact_terminal_usable": usable,
                }
            )

        usable_raw_ids = sorted(set(usable_raw_ids))
        distance_cache: dict[str, dict[str, float]] = {}
        for i, left_raw in enumerate(usable_raw_ids):
            distance_cache[left_raw] = _raw_graph_distances(adjacency, left_raw)
            for right_raw in usable_raw_ids[i + 1 :]:
                distance_m = distance_cache[left_raw].get(right_raw)
                if distance_m is None or not math.isfinite(distance_m) or distance_m <= 0.0:
                    continue
                for left_land in land_by_raw[left_raw]:
                    for right_land in land_by_raw[right_raw]:
                        left_id = left_land["network_node_id"]
                        right_id = right_land["network_node_id"]
                        if left_id == right_id:
                            continue
                        row = _edge_row(
                            left_id=left_id,
                            right_id=right_id,
                            left_area=left_land["survey_area_id"],
                            right_area=right_land["survey_area_id"],
                            distance_m=float(distance_m),
                            network_source="osm_overpass_ferry_relation_stop",
                            ferry_relation_id=relation_id,
                            tags=relation_tags,
                        )
                        key = (str(row["from_node_id"]), str(row["to_node_id"]))
                        existing = edge_rows.get(key)
                        if existing is None or float(distance_m) < float(existing["distance_m"]):
                            edge_rows[key] = row

    stop_audit = pd.DataFrame(stop_rows, columns=_STOP_AUDIT_COLUMNS)
    if edge_rows:
        edges = pd.DataFrame(
            sorted(
                edge_rows.values(),
                key=lambda row: (str(row["from_node_id"]), str(row["to_node_id"])),
            )
        )
    else:
        edges = _empty_ferry_edges()

    unique_stops = (
        stop_audit.drop_duplicates("stop_node_id") if not stop_audit.empty else stop_audit
    )
    counts = {
        "ferry_relation_count": int(len(relations)),
        "relation_stop_member_count": int(relation_stop_member_count),
        "unique_stop_node_count": int(len(unique_stops)),
        "ferry_terminal_tagged_stop_count": int(
            (unique_stops["amenity"] == "ferry_terminal").sum()
        ) if not unique_stops.empty else 0,
        "public_transport_ferry_stop_count": int(
            (
                (unique_stops["public_transport"] == "stop_position")
                & (unique_stops["ferry"] == "yes")
            ).sum()
        ) if not unique_stops.empty else 0,
        "stop_in_ferry_graph_count": int(
            unique_stops["in_ferry_member_way_graph"].sum()
        ) if not unique_stops.empty else 0,
        "stop_in_land_graph_count": int(
            unique_stops["in_land_highway_graph"].sum()
        ) if not unique_stops.empty else 0,
        "stop_in_both_graphs_count": int(
            unique_stops["exact_terminal_usable"].sum()
        ) if not unique_stops.empty else 0,
        "unmatched_land_stop_count": int(
            (~unique_stops["in_land_highway_graph"]).sum()
        ) if not unique_stops.empty else 0,
        "ferry_edge_count": int(len(edges)),
    }
    return edges, stop_audit, counts


def fetch_osm_ferry_stop_edges_for_patches(
    candidates: pd.DataFrame,
    land_nodes: pd.DataFrame,
    *,
    max_network_transition_km: float,
    area_col: str = "survey_area_id",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    overpass_url: str = OVERPASS_API_URL,
    timeout_s: int = DEFAULT_OVERPASS_TIMEOUT_S,
    attempts: int = DEFAULT_OVERPASS_ATTEMPTS,
) -> tuple[pd.DataFrame, pd.DataFrame, OsmFerryStopProviderAudit]:
    """Fetch explicit ferry relation stops for movement-relevant area pairs."""
    if float(max_network_transition_km) <= 0.0:
        raise ValueError("max_network_transition_km must be positive")
    for column in (area_col, latitude_col, longitude_col):
        if column not in candidates.columns:
            raise ValueError(f"candidate table lacks required column {column!r}")

    groups = {
        str(area): frame.reset_index(drop=True)
        for area, frame in candidates.groupby(area_col, sort=True)
    }
    area_ids = sorted(groups)
    query_specs: list[tuple[str, str, pd.DataFrame]] = []
    for i, left_id in enumerate(area_ids):
        query_specs.append((left_id, left_id, groups[left_id]))
        for right_id in area_ids[i + 1 :]:
            minimum_km = _minimum_area_distance_km(
                groups[left_id],
                groups[right_id],
                latitude_col=latitude_col,
                longitude_col=longitude_col,
            )
            if minimum_km <= float(max_network_transition_km) + 1e-9:
                query_specs.append(
                    (
                        left_id,
                        right_id,
                        pd.concat([groups[left_id], groups[right_id]], ignore_index=True),
                    )
                )

    edge_tables: list[pd.DataFrame] = []
    stop_tables: list[pd.DataFrame] = []
    successful = 0
    failed = 0
    totals = {
        "ferry_relation_count": 0,
        "relation_stop_member_count": 0,
        "unique_stop_node_count": 0,
        "ferry_terminal_tagged_stop_count": 0,
        "public_transport_ferry_stop_count": 0,
        "stop_in_ferry_graph_count": 0,
        "stop_in_land_graph_count": 0,
        "stop_in_both_graphs_count": 0,
        "unmatched_land_stop_count": 0,
    }

    for _left_id, _right_id, query_candidates in query_specs:
        west, south, east, north = _area_bounds(
            query_candidates,
            latitude_col=latitude_col,
            longitude_col=longitude_col,
            margin_km=float(max_network_transition_km),
        )
        try:
            payload = _post_overpass(
                _ferry_stop_query(west, south, east, north),
                overpass_url=overpass_url,
                timeout_s=timeout_s,
                attempts=attempts,
            )
            edges, stop_audit, counts = ferry_relation_stops_to_transport_edges(
                payload, land_nodes
            )
            if not edges.empty:
                edge_tables.append(edges)
            if not stop_audit.empty:
                stop_tables.append(stop_audit)
            successful += 1
            for key in totals:
                totals[key] += int(counts[key])
        except Exception:
            failed += 1

    if edge_tables:
        edges = pd.concat(edge_tables, ignore_index=True, sort=False)
        edges = (
            edges.sort_values("distance_m")
            .drop_duplicates(["from_node_id", "to_node_id"], keep="first")
            .sort_values(["from_node_id", "to_node_id"])
            .reset_index(drop=True)
        )
    else:
        edges = _empty_ferry_edges()

    if stop_tables:
        stop_audit = pd.concat(stop_tables, ignore_index=True, sort=False)
        stop_audit = stop_audit.drop_duplicates(
            ["ferry_relation_id", "stop_node_id"], keep="first"
        ).reset_index(drop=True)
        unique_stops = stop_audit.drop_duplicates("stop_node_id")
        totals["unique_stop_node_count"] = int(len(unique_stops))
        totals["ferry_terminal_tagged_stop_count"] = int(
            (unique_stops["amenity"] == "ferry_terminal").sum()
        )
        totals["public_transport_ferry_stop_count"] = int(
            (
                (unique_stops["public_transport"] == "stop_position")
                & (unique_stops["ferry"] == "yes")
            ).sum()
        )
        totals["stop_in_ferry_graph_count"] = int(
            unique_stops["in_ferry_member_way_graph"].sum()
        )
        totals["stop_in_land_graph_count"] = int(
            unique_stops["in_land_highway_graph"].sum()
        )
        totals["stop_in_both_graphs_count"] = int(
            unique_stops["exact_terminal_usable"].sum()
        )
        totals["unmatched_land_stop_count"] = int(
            (~unique_stops["in_land_highway_graph"]).sum()
        )
    else:
        stop_audit = _empty_stop_audit()

    audit = OsmFerryStopProviderAudit(
        query_count=int(len(query_specs)),
        successful_query_count=int(successful),
        failed_query_count=int(failed),
        ferry_relation_count=int(totals["ferry_relation_count"]),
        relation_stop_member_count=int(totals["relation_stop_member_count"]),
        unique_stop_node_count=int(totals["unique_stop_node_count"]),
        ferry_terminal_tagged_stop_count=int(totals["ferry_terminal_tagged_stop_count"]),
        public_transport_ferry_stop_count=int(totals["public_transport_ferry_stop_count"]),
        stop_in_ferry_graph_count=int(totals["stop_in_ferry_graph_count"]),
        stop_in_land_graph_count=int(totals["stop_in_land_graph_count"]),
        stop_in_both_graphs_count=int(totals["stop_in_both_graphs_count"]),
        unmatched_land_stop_count=int(totals["unmatched_land_stop_count"]),
        emitted_ferry_edge_count=int(len(edges)),
    )
    return edges, stop_audit, audit
