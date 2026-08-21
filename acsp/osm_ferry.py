"""Conservative OSM ``route=ferry`` extension for ACSP transport networks.

Ferry movement is added only when a direct OSM ferry way's endpoint node IDs
match OSM highway node IDs already present in the land transport network. No
proximity-based terminal snapping or island bridging is performed.
"""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class OsmFerryProviderAudit:
    query_count: int
    successful_query_count: int
    failed_query_count: int
    ferry_way_count: int
    endpoint_matched_way_count: int
    emitted_ferry_edge_count: int
    provider: str = "openstreetmap_overpass_route_ferry"
    direct_way_support: bool = True
    relation_only_support: bool = False
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
            "provider": self.provider,
            "direct_way_support": self.direct_way_support,
            "relation_only_support": self.relation_only_support,
            "endpoint_osm_node_id_match_required": self.endpoint_osm_node_id_match_required,
            "proximity_terminal_fallback": self.proximity_terminal_fallback,
            "access_restrictions_enforced": self.access_restrictions_enforced,
            "timetable_claim": self.timetable_claim,
            "service_currentness_claim": self.service_currentness_claim,
        }


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
                a, b = sorted((left_id, right_id))
                key = (a, b)
                area_a = start["survey_area_id"] if left_id == a else end["survey_area_id"]
                area_b = end["survey_area_id"] if right_id == b else start["survey_area_id"]
                row = {
                    "from_node_id": a,
                    "to_node_id": b,
                    "distance_m": float(distance_m),
                    "survey_area_id": f"{area_a}|{area_b}",
                    "network_mode": "ferry",
                    "highway": "",
                    "osm_way_id": str(element.get("id", "unknown")),
                    "network_source": "osm_overpass_route_ferry",
                    "ferry_name": str(tags.get("name", "")),
                    "ferry_access": str(tags.get("access", "")),
                    "ferry_foot": str(tags.get("foot", "")),
                    "ferry_motorcar": str(tags.get("motorcar", "")),
                    "ferry_bicycle": str(tags.get("bicycle", "")),
                    "ferry_duration": str(tags.get("duration", "")),
                }
                existing = edge_rows.get(key)
                if existing is None or distance_m < float(existing["distance_m"]):
                    edge_rows[key] = row
                emitted_for_way = True
        if emitted_for_way:
            matched_way_count += 1

    columns = [
        "from_node_id",
        "to_node_id",
        "distance_m",
        "survey_area_id",
        "network_mode",
        "highway",
        "osm_way_id",
        "network_source",
        "ferry_name",
        "ferry_access",
        "ferry_foot",
        "ferry_motorcar",
        "ferry_bicycle",
        "ferry_duration",
    ]
    edges = pd.DataFrame(
        sorted(edge_rows.values(), key=lambda row: (str(row["from_node_id"]), str(row["to_node_id"]))),
        columns=columns,
    )
    return edges, {
        "ferry_way_count": int(ferry_way_count),
        "endpoint_matched_way_count": int(matched_way_count),
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
    return f'[out:json][timeout:25];way["route"="ferry"]({bbox});out body geom;'


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
    """Fetch direct OSM ferry ways for movement-relevant survey-area pairs.

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
    total_matched = 0
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
            edges, counts = ferry_ways_to_transport_edges(payload, land_nodes)
            if not edges.empty:
                edge_tables.append(edges)
            total_ways += int(counts["ferry_way_count"])
            total_matched += int(counts["endpoint_matched_way_count"])
            success_count += 1
            audit_rows.append(
                {
                    "left_survey_area_id": left_id,
                    "right_survey_area_id": right_id,
                    "status": "success",
                    "ferry_way_count": int(counts["ferry_way_count"]),
                    "endpoint_matched_way_count": int(counts["endpoint_matched_way_count"]),
                    "ferry_edge_count": int(counts["ferry_edge_count"]),
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
                    "ferry_edge_count": 0,
                    "error": str(exc),
                }
            )

    if edge_tables:
        combined_edges = pd.concat(edge_tables, ignore_index=True)
        combined_edges = combined_edges.sort_values("distance_m").drop_duplicates(
            subset=["from_node_id", "to_node_id"], keep="first"
        ).sort_values(["from_node_id", "to_node_id"]).reset_index(drop=True)
    else:
        combined_edges, _ = ferry_ways_to_transport_edges({"elements": []}, land_nodes)

    pair_audit = pd.DataFrame(audit_rows)
    audit = OsmFerryProviderAudit(
        query_count=int(len(query_specs)),
        successful_query_count=int(success_count),
        failed_query_count=int(failure_count),
        ferry_way_count=int(total_ways),
        endpoint_matched_way_count=int(total_matched),
        emitted_ferry_edge_count=int(len(combined_edges)),
    )
    return combined_edges, pair_audit, audit
