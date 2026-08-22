"""Movement-limit impossibility certificates for ferry-stop topology retrieval.

Geodesic distance is used only as a mathematical lower bound to prove that a
ferry stop cannot participate in any admissible candidate transition. It never
creates reachability. Expensive highway-topology retrieval is skipped only when
the conservative patch-footprint lower bound is already greater than the same
user movement limit used by the downstream network selector.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd

from .osm_ferry_stop_highways import (
    OsmFerryStopHighwayAudit,
    _empty_transport_edges,
    _empty_transport_nodes,
    _unmatched_stop_ids,
    fetch_explicit_highway_extensions_for_ferry_stops,
)
from .osm_transport import (
    DEFAULT_OVERPASS_ATTEMPTS,
    DEFAULT_OVERPASS_TIMEOUT_S,
    OVERPASS_API_URL,
    _haversine_m,
    _post_overpass,
)


@dataclass(frozen=True)
class FerryStopImpossibilityAudit:
    movement_limit_km: float
    unmatched_stop_count: int
    stop_coordinate_query_count: int
    stop_coordinate_query_failed: bool
    coordinate_available_stop_count: int
    movement_impossible_stop_count: int
    topology_eligible_stop_count: int
    skipped_by_geodesic_lower_bound_count: int
    minimum_center_geodesic_km: float | None
    minimum_patch_footprint_lower_bound_km: float | None
    topology_provider: dict[str, object]
    geodesic_is_lower_bound_only: bool = True
    geodesic_used_to_create_reachability: bool = False
    geodesic_used_to_rank_candidates: bool = False
    proximity_terminal_fallback: bool = False
    candidate_to_terminal_straight_line_edge: bool = False
    provider: str = "ferry_stop_movement_impossibility_certificate"

    def as_dict(self) -> dict[str, object]:
        return {
            "movement_limit_km": self.movement_limit_km,
            "unmatched_stop_count": self.unmatched_stop_count,
            "stop_coordinate_query_count": self.stop_coordinate_query_count,
            "stop_coordinate_query_failed": self.stop_coordinate_query_failed,
            "coordinate_available_stop_count": self.coordinate_available_stop_count,
            "movement_impossible_stop_count": self.movement_impossible_stop_count,
            "topology_eligible_stop_count": self.topology_eligible_stop_count,
            "skipped_by_geodesic_lower_bound_count": self.skipped_by_geodesic_lower_bound_count,
            "minimum_center_geodesic_km": self.minimum_center_geodesic_km,
            "minimum_patch_footprint_lower_bound_km": self.minimum_patch_footprint_lower_bound_km,
            "geodesic_is_lower_bound_only": self.geodesic_is_lower_bound_only,
            "geodesic_used_to_create_reachability": self.geodesic_used_to_create_reachability,
            "geodesic_used_to_rank_candidates": self.geodesic_used_to_rank_candidates,
            "proximity_terminal_fallback": self.proximity_terminal_fallback,
            "candidate_to_terminal_straight_line_edge": self.candidate_to_terminal_straight_line_edge,
            "provider": self.provider,
            "topology_provider": self.topology_provider,
        }


def _empty_topology_audit(movement_km: float) -> OsmFerryStopHighwayAudit:
    return OsmFerryStopHighwayAudit(
        queried_stop_count=0,
        stops_with_highway_way_count=0,
        returned_highway_way_count=0,
        anchored_stop_count=0,
        imported_extension_node_count=0,
        imported_extension_edge_count=0,
        remaining_unconnected_stop_count=0,
        bounded_query_radius_m=float(movement_km) * 1000.0,
    )


def _stop_coordinate_query(stop_ids: list[str]) -> str:
    ids = sorted({str(value) for value in stop_ids if str(value).strip()})
    if not ids:
        raise ValueError("at least one stop ID is required")
    if any(not value.isdigit() for value in ids):
        raise ValueError("stop IDs must be numeric OSM node IDs")
    return f"[out:json][timeout:25];node(id:{','.join(ids)});out body;"


def _stop_coordinates_from_payload(
    payload: dict[str, Any],
    stop_ids: list[str],
) -> dict[str, tuple[float, float]]:
    wanted = set(str(value) for value in stop_ids)
    coordinates: dict[str, tuple[float, float]] = {}
    for element in payload.get("elements", []):
        if element.get("type") != "node" or element.get("id") is None:
            continue
        raw_id = str(element["id"])
        if raw_id not in wanted or "lat" not in element or "lon" not in element:
            continue
        lat = float(element["lat"])
        lon = float(element["lon"])
        if math.isfinite(lat) and math.isfinite(lon):
            coordinates[raw_id] = (lat, lon)
    return coordinates


def _candidate_columns(candidates: pd.DataFrame) -> tuple[str, str]:
    if "latitude" in candidates.columns and "longitude" in candidates.columns:
        return "latitude", "longitude"
    raise ValueError("candidate patches require latitude and longitude for lower-bound audit")


def ferry_stop_candidate_lower_bounds(
    stop_coordinates: dict[str, tuple[float, float]],
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    """Return geodesic lower bounds from stop nodes to candidate patch footprints.

    The footprint lower bound is ``max(0, centre distance - patch radius)``. It
    is conservative even if the candidate patch is treated as a disk around its
    representative coordinate. No distance in this table is a reachability edge.
    """
    columns = [
        "stop_node_id",
        "minimum_center_geodesic_km",
        "minimum_patch_footprint_lower_bound_km",
        "nearest_candidate_patch_id",
    ]
    if not stop_coordinates:
        return pd.DataFrame(columns=columns)
    if candidates is None or candidates.empty:
        return pd.DataFrame(columns=columns)
    lat_col, lon_col = _candidate_columns(candidates)
    work = candidates.copy()
    work[lat_col] = pd.to_numeric(work[lat_col], errors="coerce")
    work[lon_col] = pd.to_numeric(work[lon_col], errors="coerce")
    work = work.dropna(subset=[lat_col, lon_col]).reset_index(drop=True)
    if work.empty:
        return pd.DataFrame(columns=columns)
    if "candidate_patch_radius_m" in work.columns:
        radii = pd.to_numeric(work["candidate_patch_radius_m"], errors="coerce").fillna(0.0).clip(lower=0.0)
    else:
        radii = pd.Series(0.0, index=work.index)
    patch_ids = (
        work["candidate_patch_id"].astype(str)
        if "candidate_patch_id" in work.columns
        else pd.Series([str(index) for index in work.index], index=work.index)
    )

    rows: list[dict[str, object]] = []
    for stop_id, (stop_lat, stop_lon) in sorted(stop_coordinates.items()):
        centre_distances_m: list[float] = []
        lower_bounds_m: list[float] = []
        for index, row in work.iterrows():
            distance_m = _haversine_m(stop_lat, stop_lon, row[lat_col], row[lon_col])
            centre_distances_m.append(float(distance_m))
            lower_bounds_m.append(max(0.0, float(distance_m) - float(radii.loc[index])))
        nearest_index = min(range(len(lower_bounds_m)), key=lambda index: lower_bounds_m[index])
        rows.append(
            {
                "stop_node_id": str(stop_id),
                "minimum_center_geodesic_km": min(centre_distances_m) / 1000.0,
                "minimum_patch_footprint_lower_bound_km": lower_bounds_m[nearest_index] / 1000.0,
                "nearest_candidate_patch_id": str(patch_ids.iloc[nearest_index]),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _eligible_stop_audit(stop_audit: pd.DataFrame, eligible_ids: set[str]) -> pd.DataFrame:
    if stop_audit is None or stop_audit.empty:
        return stop_audit.copy() if stop_audit is not None else pd.DataFrame()
    return stop_audit[
        stop_audit["stop_node_id"].astype(str).isin(eligible_ids)
    ].copy().reset_index(drop=True)


def fetch_movement_pruned_highway_extensions_for_ferry_stops(
    stop_audit: pd.DataFrame,
    land_nodes: pd.DataFrame,
    candidates: pd.DataFrame,
    *,
    max_network_transition_km: float,
    overpass_url: str = OVERPASS_API_URL,
    timeout_s: int = DEFAULT_OVERPASS_TIMEOUT_S,
    attempts: int = DEFAULT_OVERPASS_ATTEMPTS,
) -> tuple[pd.DataFrame, pd.DataFrame, FerryStopImpossibilityAudit]:
    """Prune impossible ferry-stop topology retrieval, never create reachability.

    Stops whose conservative patch-footprint geodesic lower bound is already
    greater than the movement limit cannot participate in any admissible network
    transition. Only such proven-impossible stops are removed before the existing
    exact-topology recovery provider is called.
    """
    movement_km = float(max_network_transition_km)
    if movement_km <= 0.0:
        raise ValueError("max_network_transition_km must be positive")
    stop_ids = _unmatched_stop_ids(stop_audit)
    if not stop_ids:
        topology_audit = _empty_topology_audit(movement_km)
        audit = FerryStopImpossibilityAudit(
            movement_limit_km=movement_km,
            unmatched_stop_count=0,
            stop_coordinate_query_count=0,
            stop_coordinate_query_failed=False,
            coordinate_available_stop_count=0,
            movement_impossible_stop_count=0,
            topology_eligible_stop_count=0,
            skipped_by_geodesic_lower_bound_count=0,
            minimum_center_geodesic_km=None,
            minimum_patch_footprint_lower_bound_km=None,
            topology_provider=topology_audit.as_dict(),
        )
        return _empty_transport_nodes(), _empty_transport_edges(), audit

    coordinate_failed = False
    coordinates: dict[str, tuple[float, float]] = {}
    try:
        payload = _post_overpass(
            _stop_coordinate_query(stop_ids),
            overpass_url=overpass_url,
            timeout_s=timeout_s,
            attempts=attempts,
        )
        coordinates = _stop_coordinates_from_payload(payload, stop_ids)
    except Exception:
        # Missing coordinate evidence cannot prove impossibility. Fail open into
        # the exact-topology provider, which itself remains fail-closed for edges.
        coordinate_failed = True

    lower_bounds = ferry_stop_candidate_lower_bounds(coordinates, candidates)
    bound_by_id = {
        str(row.stop_node_id): float(row.minimum_patch_footprint_lower_bound_km)
        for row in lower_bounds.itertuples(index=False)
    }
    impossible_ids = {
        stop_id
        for stop_id, lower_km in bound_by_id.items()
        if lower_km > movement_km + 1e-9
    }
    # Stops lacking coordinate/lower-bound evidence stay eligible; uncertainty
    # must never be converted into an impossibility claim.
    eligible_ids = set(stop_ids) - impossible_ids

    if eligible_ids:
        eligible_audit = _eligible_stop_audit(stop_audit, eligible_ids)
        nodes, edges, topology_audit = fetch_explicit_highway_extensions_for_ferry_stops(
            eligible_audit,
            land_nodes,
            max_network_transition_km=movement_km,
            overpass_url=overpass_url,
            timeout_s=timeout_s,
            attempts=attempts,
        )
    else:
        nodes = _empty_transport_nodes()
        edges = _empty_transport_edges()
        topology_audit = _empty_topology_audit(movement_km)

    min_center = (
        float(lower_bounds["minimum_center_geodesic_km"].min())
        if not lower_bounds.empty
        else None
    )
    min_patch_lower = (
        float(lower_bounds["minimum_patch_footprint_lower_bound_km"].min())
        if not lower_bounds.empty
        else None
    )
    audit = FerryStopImpossibilityAudit(
        movement_limit_km=movement_km,
        unmatched_stop_count=int(len(stop_ids)),
        stop_coordinate_query_count=1,
        stop_coordinate_query_failed=bool(coordinate_failed),
        coordinate_available_stop_count=int(len(coordinates)),
        movement_impossible_stop_count=int(len(impossible_ids)),
        topology_eligible_stop_count=int(len(eligible_ids)),
        skipped_by_geodesic_lower_bound_count=int(len(impossible_ids)),
        minimum_center_geodesic_km=min_center,
        minimum_patch_footprint_lower_bound_km=min_patch_lower,
        topology_provider=topology_audit.as_dict(),
    )
    return nodes, edges, audit
