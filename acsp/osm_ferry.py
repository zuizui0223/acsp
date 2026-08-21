"""Conservative OSM ``route=ferry`` extension for ACSP transport networks.

Ferry movement is added only when OSM ferry topology connects raw OSM node IDs
that already exist in the land highway network. Directly tagged ferry ways and
``type=route, route=ferry`` relations are supported. No proximity-based terminal
snapping or island bridging is performed.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from .coverage import EARTH_RADIUS_KM
from .osm_transport import (
    DEFAULT_OVERPASS_ATTEMPTS,
    DEFAULT_OVERPASS_TIMEOUT_S,
    OVERPASS_API_URL,
    _area_bounds,
    _haversine_m,
    _post_overpass,
)

_RAW_NODE_RE = re.compile(r":node:(\d+)$")
_FERRY_EDGE_COLUMNS = [
    "from_node_id",
    "to_node_id",
    "distance_m",
    "survey_area_id",
    "network_mode",
    "highway",
    "osm_way_id",
    "network_source",
    "ferry_relation_id",
    "ferry_name",
    "ferry_ref",
    "ferry_access",
    "ferry_foot",
    "ferry_motorcar",
    "ferry_bicycle",
    "ferry_duration",
]


@dataclass(frozen=True)
class OsmFerryProviderAudit:
    query_count: int
    successful_query_count: int
    failed_query_count: int
    ferry_way_count: int
    endpoint_matched_way_count: int
    emitted_ferry_edge_count: int
    ferry_relation_count: int = 0
    relation_member_way_count: int = 0
    relation_endpoint_matched_count: int = 0
    incomplete_relation_member_way_count: int = 0
    provider: str = "openstreetmap_overpass_route_ferry"
    direct_way_support: bool = True
    relation_only_support: bool = True
    endpoint_osm_node_id_match_required: bool = True
    proximity_terminal_fallback: bool = False
    access_restrictions_enforced: bool = False
    timetable_claim: bool = False
    service_currentness_claim: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "query_count": self.query_count,
            "successful_query_count": self.successful_query_count,
            "failed_query_count": self.failed_query_count,
            "ferry_way_count": self.ferry_way_count,
            "endpoint_matched_way_count": self.endpoint_matched_way_count,
            "emitted_ferry_edge_count": self.emitted_ferry_edge_count,
            "ferry_relation_count": self.ferry_relation_count,
            "relation_member_way_count": self.relation_member_way_count,
            "relation_endpoint_matched_count": self.relation_endpoint_matched_count,
            "incomplete_relation_member_way_count": self.incomplete_relation_member_way_count,
            "provider": self.provider,
            "direct_way_support": self.direct_way_support,
            "relation_only_support": self.relation_only_support,
            "endpoint_osm_node_id_match_required": self.endpoint_osm_node_id_match_required,
            "proximity_terminal_fallback": self.proximity_terminal_fallback,
            "access_restrictions_enforced": self.access_restrictions_enforced,
            "timetable_claim": self.timetable_claim,
            "service_currentness_claim": self.service_currentness_claim,
        }


def _empty_ferry_edges() -> pd.DataFrame:
    return pd.DataFrame(columns=_FERRY_EDGE_COLUMNS)


def _raw_osm_node_id(network_node_id: object) -> str | None:
    match = _RAW_NODE_RE.search(str(network_node_id))
    return match.group(1) if match else None


def _land_nodes_by_raw_osm_id(land_nodes: pd.DataFrame) -> dict[str, list[dict[str, str]]]:
    required = {"network_node_id", "survey_area_id"}
    missing = required.difference(land_nodes.columns)
    if missing:
        raise ValueError(f"land transport nodes lack required columns: {sorted(missing)}")
    mapping: dict[str, list[dict[str, str]]] = {}
    for row in land_nodes[["network_node_id", "survey_area_id"]].itertuples(index=False):
        raw_id = _raw_osm_node_id(row.network_node_id)
        if raw_id is None:
            continue
        mapping.setdefault(raw_id, []).append(
            {
                "network_node_id": str(row.network_node_id),
                "survey_area_id": str(row.survey_area_id),
            }
        )
    return mapping


def _edge_row(
    *,
    left_id: str,
    right_id: str,
    left_area: str,
    right_area: str,
    distance_m: float,
    network_source: str,
    osm_way_id: str = "",
    ferry_relation_id: str = "",
    tags: dict[str, Any] | None = None,
) -> dict[str, object]:
    tags = tags or {}
    a, b = sorted((str(left_id), str(right_id)))
    area_a = str(left_area) if str(left_id) == a else str(right_area)
    area_b = str(right_area) if str(right_id) == b else str(left_area)
    return {
        "from_node_id": a,
        "to_node_id": b,
        "distance_m": float(distance_m),
        "survey_area_id": f"{area_a}|{area_b}",
        "network_mode": "ferry",
        "highway": "",
        "osm_way_id": str(osm_way_id),
        "network_source": str(network_source),
        "ferry_relation_id": str(ferry_relation_id),
        "ferry_name": str(tags.get("name", "")),
        "ferry_ref": str(tags.get("ref", "")),
        "ferry_access": str(tags.get("access", "")),
        "ferry_foot": str(tags.get("foot", "")),
        "ferry_motorcar": str(tags.get("motorcar", "")),
        "ferry_bicycle": str(tags.get("bicycle", "")),
        "ferry_duration": str(tags.get("duration", "")),
    }


def ferry_ways_to_transport_edges(
    payload: dict[str, Any],
    land_nodes: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Convert directly tagged ferry ways whose endpoints match land OSM nodes."""
    land_by_raw = _land_nodes_by_raw_osm_id(land_nodes)
    edge_rows: dict[tuple[str, str], dict[str, object]] = {}
    ferry_way_count = 0
    matched_way_count = 0

    for element in payload.get("elements", []):
        if element.get("type") != "way":
            continue
        tags = element.get("tags") or {}
        if str(tags.get("route", "")) != "ferry":
            continue
        raw_nodes = element.get("nodes")
        geometry = element.get("geometry")
        if (
            not isinstance(raw_nodes, list)
            or not isinstance(geometry, list)
            or len(raw_nodes) != len(geometry)
            or len(raw_nodes) < 2
        ):
            continue
        if any("lat" not in point or "lon" not in point for point in geometry):
            continue

        ferry_way_count += 1
        start_raw = str(raw_nodes[0])
        end_raw = str(raw_nodes[-1])
        start_land = land_by_raw.get(start_raw, [])
        end_land = land_by_raw.get(end_raw, [])
        if not start_land or not end_land:
            continue

        distance_m = 0.0
        valid = True
        for left, right in zip(geometry[:-1], geometry[1:]):
            segment = _haversine_m(left["lat"], left["lon"], right["lat"], right["lon"])
            if not math.isfinite(segment) or segment < 0.0:
                valid = False
                break
            distance_m += float(segment)
        if not valid or distance_m <= 0.0:
            continue

        emitted_for_way = False
        for start in start_land:
            for end in end_land:
                left_id = start["network_node_id"]
                right_id = end["network_node_id"]
                if left_id == right_id:
                    continue
                row = _edge_row(
                    left_id=left_id,
                    right_id=right_id,
                    left_area=start["survey_area_id"],
                    right_area=end["survey_area_id"],
                    distance_m=distance_m,
                    network_source="osm_overpass_route_ferry",
                    osm_way_id=str(element.get("id", "unknown")),
                    tags=tags,
                )
                key = (str(row["from_node_id"]), str(row["to_node_id"]))
                existing = edge_rows.get(key)
                if existing is None or distance_m < float(existing["distance_m"]):
                    edge_rows[key] = row
                emitted_for_way = True
        if emitted_for_way:
            matched_way_count += 1

    edges = pd.DataFrame(
        sorted(edge_rows.values(), key=lambda row: (str(row["from_node_id"]), str(row["to_node_id"]))),
        columns=_FERRY_EDGE_COLUMNS,
    )
    return edges, {
        "ferry_way_count": int(ferry_way_count),
        "endpoint_matched_way_count": int(matched_way_count),
        "ferry_edge_count": int(len(edges)),
    }


def _relation_way_graph(
    relation: dict[str, Any],
    way_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, list[tuple[str, float]]], int, int]:
    adjacency: dict[str, list[tuple[str, float]]] = {}
    valid_member_count = 0
    incomplete_member_count = 0
    member_refs = [
        str(member.get("ref"))
        for member in relation.get("members", [])
        if member.get("type") == "way" and member.get("ref") is not None
    ]
    for ref in member_refs:
        way = way_by_id.get(ref)
        if way is None:
            incomplete_member_count += 1
            continue
        raw_nodes = way.get("nodes")
        geometry = way.get("geometry")
        if (
            not isinstance(raw_nodes, list)
            or not isinstance(geometry, list)
            or len(raw_nodes) != len(geometry)
            or len(raw_nodes) < 2
            or any("lat" not in point or "lon" not in point for point in geometry)
        ):
            incomplete_member_count += 1
            continue
        valid_member_count += 1
        for left_raw, right_raw, left, right in zip(
            raw_nodes[:-1], raw_nodes[1:], geometry[:-1], geometry[1:]
        ):
            left_id = str(left_raw)
            right_id = str(right_raw)
            if left_id == right_id:
                continue
            distance_m = _haversine_m(left["lat"], left["lon"], right["lat"], right["lon"])
            if not math.isfinite(distance_m) or distance_m <= 0.0:
                continue
            adjacency.setdefault(left_id, []).append((right_id, float(distance_m)))
            adjacency.setdefault(right_id, []).append((left_id, float(distance_m)))
    return adjacency, valid_member_count, incomplete_member_count


def _raw_graph_distances(
    adjacency: dict[str, list[tuple[str, float]]],
    source: str,
) -> dict[str, float]:
    distances: dict[str, float] = {str(source): 0.0}
    queue: list[tuple[float, str]] = [(0.0, str(source))]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        for neighbour, edge_distance in adjacency.get(node, []):
            next_distance = distance + float(edge_distance)
            if next_distance < distances.get(neighbour, float("inf")):
                distances[neighbour] = next_distance
                heapq.heappush(queue, (next_distance, neighbour))
    return distances


def ferry_relations_to_transport_edges(
    payload: dict[str, Any],
    land_nodes: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Convert ferry relations by shortest paths across their member-way graph.

    Relation member ways need not carry ``route=ferry`` themselves. Only raw OSM
    graph nodes that exactly match nodes in the land highway network can serve as
    ferry terminals. Missing/incomplete member ways remain absent; no geometry is
    interpolated or bridged.
    """
    land_by_raw = _land_nodes_by_raw_osm_id(land_nodes)
    way_by_id = {
        str(element.get("id")): element
        for element in payload.get("elements", [])
        if element.get("type") == "way" and element.get("id") is not None
    }
    edge_rows: dict[tuple[str, str], dict[str, object]] = {}
    relation_count = 0
    member_way_count = 0
    incomplete_member_way_count = 0
    matched_relation_count = 0

    relations = [
        element
        for element in payload.get("elements", [])
        if element.get("type") == "relation"
        and str((element.get("tags") or {}).get("type", "")) == "route"
        and str((element.get("tags") or {}).get("route", "")) == "ferry"
    ]
    for relation in relations:
        relation_count += 1
        adjacency, valid_members, incomplete_members = _relation_way_graph(relation, way_by_id)
        member_way_count += int(valid_members)
        incomplete_member_way_count += int(incomplete_members)
        if not adjacency:
            continue
        terminal_raw_ids = sorted(set(adjacency).intersection(land_by_raw))
        if len(terminal_raw_ids) < 2:
            continue

        tags = relation.get("tags") or {}
        emitted_for_relation = False
        distance_cache: dict[str, dict[str, float]] = {}
        for i, left_raw in enumerate(terminal_raw_ids):
            distance_cache[left_raw] = _raw_graph_distances(adjacency, left_raw)
            for right_raw in terminal_raw_ids[i + 1 :]:
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
                            network_source="osm_overpass_ferry_relation",
                            ferry_relation_id=str(relation.get("id", "unknown")),
                            tags=tags,
                        )
                        key = (str(row["from_node_id"]), str(row["to_node_id"]))
                        existing = edge_rows.get(key)
                        if existing is None or float(distance_m) < float(existing["distance_m"]):
                            edge_rows[key] = row
                        emitted_for_relation = True
        if emitted_for_relation:
            matched_relation_count += 1

    edges = pd.DataFrame(
        sorted(edge_rows.values(), key=lambda row: (str(row["from_node_id"]), str(row["to_node_id"]))),
        columns=_FERRY_EDGE_COLUMNS,
    )
    return edges, {
        "ferry_relation_count": int(relation_count),
        "relation_member_way_count": int(member_way_count),
        "relation_endpoint_matched_count": int(matched_relation_count),
        "incomplete_relation_member_way_count": int(incomplete_member_way_count),
        "ferry_edge_count": int(len(edges)),
    }


def _minimum_area_distance_km(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    latitude_col: str,
    longitude_col: str,
) -> float:
    if left.empty or right.empty:
        return float("inf")
    left_coords = np.radians(left[[latitude_col, longitude_col]].to_numpy(float))
    right_coords = np.radians(right[[latitude_col, longitude_col]].to_numpy(float))
    tree = BallTree(right_coords, metric="haversine")
    distances, _ = tree.query(left_coords, k=1)
    return float(distances[:, 0].min() * EARTH_RADIUS_KM)


def _ferry_query(west: float, south: float, east: float, north: float) -> str:
    bbox = f"{float(south):.7f},{float(west):.7f},{float(north):.7f},{float(east):.7f}"
    return (
        "[out:json][timeout:25];"
        f'relation["type"="route"]["route"="ferry"]({bbox})->.fr;'
        "way(r.fr)->.rw;"
        "("
        f'way["route"="ferry"]({bbox});'
        ".fr;"
        ".rw;"
        ");"
        "out body geom;"
    )


def fetch_osm_ferry_edges_for_patches(
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
) -> tuple[pd.DataFrame, pd.DataFrame, OsmFerryProviderAudit]:
    """Fetch direct and relation-based OSM ferries for relevant area pairs.

    Geodesic area separation is used only as a safe lower-bound query-pruning
    test: if every candidate pair is farther apart than the network movement
    limit, no network path can satisfy that limit. It never creates an edge.
    """
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
                combined = pd.concat([groups[left_id], groups[right_id]], ignore_index=True)
                query_specs.append((left_id, right_id, combined))

    edge_tables: list[pd.DataFrame] = []
    audit_rows: list[dict[str, object]] = []
    total_ways = 0
    total_direct_matched = 0
    total_relations = 0
    total_relation_members = 0
    total_relation_matched = 0
    total_incomplete_relation_members = 0
    success_count = 0
    failure_count = 0
    for left_id, right_id, query_candidates in query_specs:
        west, south, east, north = _area_bounds(
            query_candidates,
            latitude_col=latitude_col,
            longitude_col=longitude_col,
            margin_km=float(max_network_transition_km),
        )
        try:
            payload = _post_overpass(
                _ferry_query(west, south, east, north),
                overpass_url=overpass_url,
                timeout_s=timeout_s,
                attempts=attempts,
            )
            direct_edges, direct_counts = ferry_ways_to_transport_edges(payload, land_nodes)
            relation_edges, relation_counts = ferry_relations_to_transport_edges(payload, land_nodes)
            query_edges = pd.concat([direct_edges, relation_edges], ignore_index=True, sort=False)
            if not query_edges.empty:
                query_edges = query_edges.sort_values("distance_m").drop_duplicates(
                    subset=["from_node_id", "to_node_id"], keep="first"
                ).reset_index(drop=True)
                edge_tables.append(query_edges)

            total_ways += int(direct_counts["ferry_way_count"])
            total_direct_matched += int(direct_counts["endpoint_matched_way_count"])
            total_relations += int(relation_counts["ferry_relation_count"])
            total_relation_members += int(relation_counts["relation_member_way_count"])
            total_relation_matched += int(relation_counts["relation_endpoint_matched_count"])
            total_incomplete_relation_members += int(
                relation_counts["incomplete_relation_member_way_count"]
            )
            success_count += 1
            audit_rows.append(
                {
                    "left_survey_area_id": left_id,
                    "right_survey_area_id": right_id,
                    "status": "success",
                    "ferry_way_count": int(direct_counts["ferry_way_count"]),
                    "endpoint_matched_way_count": int(direct_counts["endpoint_matched_way_count"]),
                    "ferry_relation_count": int(relation_counts["ferry_relation_count"]),
                    "relation_member_way_count": int(relation_counts["relation_member_way_count"]),
                    "relation_endpoint_matched_count": int(
                        relation_counts["relation_endpoint_matched_count"]
                    ),
                    "incomplete_relation_member_way_count": int(
                        relation_counts["incomplete_relation_member_way_count"]
                    ),
                    "ferry_edge_count": int(len(query_edges)),
                    "error": "",
                }
            )
        except Exception as exc:
            failure_count += 1
            audit_rows.append(
                {
                    "left_survey_area_id": left_id,
                    "right_survey_area_id": right_id,
                    "status": "failed",
                    "ferry_way_count": 0,
                    "endpoint_matched_way_count": 0,
                    "ferry_relation_count": 0,
                    "relation_member_way_count": 0,
                    "relation_endpoint_matched_count": 0,
                    "incomplete_relation_member_way_count": 0,
                    "ferry_edge_count": 0,
                    "error": str(exc),
                }
            )

    if edge_tables:
        combined_edges = pd.concat(edge_tables, ignore_index=True, sort=False)
        combined_edges = combined_edges.sort_values("distance_m").drop_duplicates(
            subset=["from_node_id", "to_node_id"], keep="first"
        ).sort_values(["from_node_id", "to_node_id"]).reset_index(drop=True)
        combined_edges = combined_edges.reindex(columns=_FERRY_EDGE_COLUMNS)
    else:
        combined_edges = _empty_ferry_edges()

    pair_audit = pd.DataFrame(audit_rows)
    audit = OsmFerryProviderAudit(
        query_count=int(len(query_specs)),
        successful_query_count=int(success_count),
        failed_query_count=int(failure_count),
        ferry_way_count=int(total_ways),
        endpoint_matched_way_count=int(total_direct_matched),
        emitted_ferry_edge_count=int(len(combined_edges)),
        ferry_relation_count=int(total_relations),
        relation_member_way_count=int(total_relation_members),
        relation_endpoint_matched_count=int(total_relation_matched),
        incomplete_relation_member_way_count=int(total_incomplete_relation_members),
    )
    return combined_edges, pair_audit, audit
