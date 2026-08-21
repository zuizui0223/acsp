"""Topology-preserving OpenStreetMap transport-network provider.

This module is downstream operational infrastructure. It retrieves OSM highway
ways around candidate patches per declared survey area and preserves their
node-to-node topology for the provider-neutral weighted transport adapter.
Provider failure is explicit and never falls back to candidate-to-candidate
straight-line connectivity.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any

import pandas as pd
import requests

from .coverage import EARTH_RADIUS_KM

OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_OVERPASS_TIMEOUT_S = 45
DEFAULT_OVERPASS_ATTEMPTS = 3
OSM_PROVIDER_USER_AGENT = "acsp-survey/0.1 (+https://github.com/zuizui0223/acsp)"

_TRAIL_HIGHWAYS = {"path", "footway", "bridleway", "steps", "track"}


@dataclass(frozen=True)
class OsmTransportProviderAudit:
    survey_area_count: int
    successful_area_count: int
    failed_area_count: int
    network_node_count: int
    network_edge_count: int
    way_count: int
    provider: str = "openstreetmap_overpass"
    topology_preserved: bool = True
    query_scope: str = "candidate_around_union"
    query_radius_derived_from_movement_limit: bool = True
    region_spanning_bbox_query: bool = False
    straight_line_candidate_fallback: bool = False
    ferry_edges_included: bool = False
    route_time_claim: bool = False
    legal_access_claim: bool = False
    safety_claim: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "survey_area_count": self.survey_area_count,
            "successful_area_count": self.successful_area_count,
            "failed_area_count": self.failed_area_count,
            "network_node_count": self.network_node_count,
            "network_edge_count": self.network_edge_count,
            "way_count": self.way_count,
            "provider": self.provider,
            "topology_preserved": self.topology_preserved,
            "query_scope": self.query_scope,
            "query_radius_derived_from_movement_limit": self.query_radius_derived_from_movement_limit,
            "region_spanning_bbox_query": self.region_spanning_bbox_query,
            "straight_line_candidate_fallback": self.straight_line_candidate_fallback,
            "ferry_edges_included": self.ferry_edges_included,
            "route_time_claim": self.route_time_claim,
            "legal_access_claim": self.legal_access_claim,
            "safety_claim": self.safety_claim,
        }


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = phi2 - phi1
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * 1000.0 * math.asin(min(1.0, math.sqrt(a)))


def _coord_fallback_id(area_id: str, lat: float, lon: float) -> str:
    return f"osm:{area_id}:coord:{float(lat):.7f},{float(lon):.7f}"


def _way_node_ids(
    element: dict[str, Any],
    geometry: list[dict[str, Any]],
    *,
    survey_area_id: str,
) -> list[str]:
    raw_nodes = element.get("nodes")
    if isinstance(raw_nodes, list) and len(raw_nodes) == len(geometry):
        return [f"osm:{survey_area_id}:node:{int(node_id)}" for node_id in raw_nodes]
    return [
        _coord_fallback_id(survey_area_id, float(point["lat"]), float(point["lon"]))
        for point in geometry
    ]


def overpass_ways_to_transport_tables(
    payload: dict[str, Any],
    *,
    survey_area_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Parse one area's Overpass ``out geom`` highway ways into a weighted graph.

    Consecutive way geometry points become undirected edges. Shared OSM node IDs
    are shared across ways within the same survey area. If a way lacks aligned
    node IDs, a deterministic coordinate key is used instead.
    """
    area_id = str(survey_area_id)
    node_rows: dict[str, dict[str, object]] = {}
    edge_rows: dict[tuple[str, str], dict[str, object]] = {}
    way_count = 0

    for element in payload.get("elements", []):
        if element.get("type") != "way":
            continue
        tags = element.get("tags") or {}
        highway = str(tags.get("highway", "")).strip()
        if not highway:
            continue
        geometry = element.get("geometry")
        if not isinstance(geometry, list) or len(geometry) < 2:
            continue
        if any("lat" not in point or "lon" not in point for point in geometry):
            continue

        way_count += 1
        way_id = str(element.get("id", "unknown"))
        mode = "trail" if highway in _TRAIL_HIGHWAYS else "road"
        node_ids = _way_node_ids(element, geometry, survey_area_id=area_id)

        for node_id, point in zip(node_ids, geometry):
            lat = float(point["lat"])
            lon = float(point["lon"])
            existing = node_rows.get(node_id)
            if existing is not None:
                if abs(float(existing["latitude"]) - lat) > 1e-7 or abs(float(existing["longitude"]) - lon) > 1e-7:
                    raise ValueError(f"OSM node {node_id!r} has inconsistent coordinates within area {area_id!r}")
                continue
            node_rows[node_id] = {
                "network_node_id": node_id,
                "survey_area_id": area_id,
                "latitude": lat,
                "longitude": lon,
                "network_source": "osm_overpass",
            }

        for i in range(len(geometry) - 1):
            left_id = node_ids[i]
            right_id = node_ids[i + 1]
            if left_id == right_id:
                continue
            left = geometry[i]
            right = geometry[i + 1]
            distance_m = _haversine_m(left["lat"], left["lon"], right["lat"], right["lon"])
            if not math.isfinite(distance_m) or distance_m <= 0.0:
                continue
            a, b = sorted((left_id, right_id))
            key = (a, b)
            row = {
                "from_node_id": a,
                "to_node_id": b,
                "distance_m": float(distance_m),
                "survey_area_id": area_id,
                "network_mode": mode,
                "highway": highway,
                "osm_way_id": way_id,
                "network_source": "osm_overpass",
            }
            existing = edge_rows.get(key)
            if existing is None or distance_m < float(existing["distance_m"]):
                edge_rows[key] = row

    nodes = pd.DataFrame(
        sorted(node_rows.values(), key=lambda row: str(row["network_node_id"])),
        columns=["network_node_id", "survey_area_id", "latitude", "longitude", "network_source"],
    )
    edges = pd.DataFrame(
        sorted(edge_rows.values(), key=lambda row: (str(row["from_node_id"]), str(row["to_node_id"]))),
        columns=[
            "from_node_id",
            "to_node_id",
            "distance_m",
            "survey_area_id",
            "network_mode",
            "highway",
            "osm_way_id",
            "network_source",
        ],
    )
    return nodes, edges, {"way_count": int(way_count), "node_count": int(len(nodes)), "edge_count": int(len(edges))}


def _candidate_around_query(
    candidates: pd.DataFrame,
    *,
    latitude_col: str,
    longitude_col: str,
    radius_km: float,
) -> tuple[str, int]:
    """Build one Overpass union of candidate-centered movement windows.

    The query radius equals the downstream network movement limit. Geometric
    neighborhoods bound data retrieval only; they do not create reachability.
    Duplicate candidate coordinates are collapsed because they define identical
    retrieval windows.
    """
    if candidates.empty:
        raise ValueError("cannot derive OSM query windows from an empty area")
    if float(radius_km) <= 0.0:
        raise ValueError("radius_km must be positive")

    coords = candidates[[latitude_col, longitude_col]].copy()
    coords[latitude_col] = pd.to_numeric(coords[latitude_col], errors="raise")
    coords[longitude_col] = pd.to_numeric(coords[longitude_col], errors="raise")
    coords = coords.drop_duplicates(subset=[latitude_col, longitude_col], keep="first")
    radius_m = float(radius_km) * 1000.0
    statements = [
        f'way["highway"](around:{radius_m:.3f},{float(lat):.7f},{float(lon):.7f});'
        for lat, lon in coords[[latitude_col, longitude_col]].itertuples(index=False, name=None)
    ]
    query = "[out:json][timeout:25];(" + "".join(statements) + ");out body geom;"
    return query, int(len(coords))


def _area_bounds(
    candidates: pd.DataFrame,
    *,
    latitude_col: str,
    longitude_col: str,
    margin_km: float,
) -> tuple[float, float, float, float]:
    """Return a bounding envelope retained for ferry-query compatibility."""
    lats = pd.to_numeric(candidates[latitude_col], errors="raise")
    lons = pd.to_numeric(candidates[longitude_col], errors="raise")
    if candidates.empty:
        raise ValueError("cannot derive OSM bounds from an empty area")
    mean_lat = float(lats.mean())
    lat_margin = float(margin_km) / 111.0
    lon_scale = max(0.1, math.cos(math.radians(mean_lat)))
    lon_margin = float(margin_km) / (111.0 * lon_scale)
    return (
        float(lons.min()) - lon_margin,
        float(lats.min()) - lat_margin,
        float(lons.max()) + lon_margin,
        float(lats.max()) + lat_margin,
    )


def _post_overpass(
    query: str,
    *,
    overpass_url: str,
    timeout_s: int,
    attempts: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(max(1, int(attempts))):
        try:
            response = requests.post(
                overpass_url,
                data={"data": query},
                timeout=int(timeout_s),
                headers={"User-Agent": OSM_PROVIDER_USER_AGENT},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Overpass response is not a JSON object")
            return payload
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt + 1 < max(1, int(attempts)):
                time.sleep(min(8.0, 1.5 * (2**attempt)))
    raise RuntimeError(f"Overpass request failed after {max(1, int(attempts))} attempts: {last_error}")


def fetch_osm_transport_network_for_patches(
    candidates: pd.DataFrame,
    *,
    query_margin_km: float,
    area_col: str = "survey_area_id",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    overpass_url: str = OVERPASS_API_URL,
    timeout_s: int = DEFAULT_OVERPASS_TIMEOUT_S,
    attempts: int = DEFAULT_OVERPASS_ATTEMPTS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, OsmTransportProviderAudit]:
    """Fetch movement-relevant road/trail topology per survey area.

    ``query_margin_km`` is derived from the downstream movement limit by the
    caller. For each survey area, one Overpass request unions candidate-centered
    ``around`` filters of that radius. A qualifying network path of total length
    <= L is contained in the L-radius geodesic neighborhood of its start patch,
    so these windows are a safe retrieval superset without querying one broad
    validation-region bounding box.

    Geometric windows only bound provider retrieval. Reachability itself remains
    weighted network shortest path. Failed areas emit audit rows and no transport
    network; the function never substitutes geometric candidate connectivity.
    """
    for column in (area_col, latitude_col, longitude_col):
        if column not in candidates.columns:
            raise ValueError(f"candidate table lacks required column {column!r}")
    if float(query_margin_km) <= 0.0:
        raise ValueError("query_margin_km must be positive")
    if candidates[area_col].isna().any():
        raise ValueError("candidate survey-area IDs must not be missing")

    node_tables: list[pd.DataFrame] = []
    edge_tables: list[pd.DataFrame] = []
    audit_rows: list[dict[str, object]] = []
    total_ways = 0

    for area_value, area_candidates in candidates.groupby(area_col, sort=True):
        area_id = str(area_value)
        query, unique_center_count = _candidate_around_query(
            area_candidates,
            latitude_col=latitude_col,
            longitude_col=longitude_col,
            radius_km=float(query_margin_km),
        )
        candidate_center_count = int(len(area_candidates))
        try:
            payload = _post_overpass(
                query,
                overpass_url=overpass_url,
                timeout_s=timeout_s,
                attempts=attempts,
            )
            nodes, edges, counts = overpass_ways_to_transport_tables(payload, survey_area_id=area_id)
            node_tables.append(nodes)
            edge_tables.append(edges)
            total_ways += int(counts["way_count"])
            audit_rows.append(
                {
                    "survey_area_id": area_id,
                    "status": "success",
                    "query_scope": "candidate_around_union",
                    "candidate_center_count": candidate_center_count,
                    "unique_query_center_count": int(unique_center_count),
                    "query_radius_km": float(query_margin_km),
                    "query_radius_derived_from_movement_limit": True,
                    "region_spanning_bbox_query": False,
                    "way_count": int(counts["way_count"]),
                    "node_count": int(counts["node_count"]),
                    "edge_count": int(counts["edge_count"]),
                    "error": "",
                }
            )
        except Exception as exc:
            audit_rows.append(
                {
                    "survey_area_id": area_id,
                    "status": "failed",
                    "query_scope": "candidate_around_union",
                    "candidate_center_count": candidate_center_count,
                    "unique_query_center_count": int(unique_center_count),
                    "query_radius_km": float(query_margin_km),
                    "query_radius_derived_from_movement_limit": True,
                    "region_spanning_bbox_query": False,
                    "way_count": 0,
                    "node_count": 0,
                    "edge_count": 0,
                    "error": str(exc),
                }
            )

    nodes = pd.concat(node_tables, ignore_index=True) if node_tables else pd.DataFrame(
        columns=["network_node_id", "survey_area_id", "latitude", "longitude", "network_source"]
    )
    edges = pd.concat(edge_tables, ignore_index=True) if edge_tables else pd.DataFrame(
        columns=[
            "from_node_id", "to_node_id", "distance_m", "survey_area_id",
            "network_mode", "highway", "osm_way_id", "network_source",
        ]
    )
    area_audit = pd.DataFrame(audit_rows)
    successful = int((area_audit["status"] == "success").sum()) if not area_audit.empty else 0
    failed = int((area_audit["status"] == "failed").sum()) if not area_audit.empty else 0
    audit = OsmTransportProviderAudit(
        survey_area_count=int(len(audit_rows)),
        successful_area_count=successful,
        failed_area_count=failed,
        network_node_count=int(len(nodes)),
        network_edge_count=int(len(edges)),
        way_count=int(total_ways),
    )
    return nodes, edges, area_audit, audit
