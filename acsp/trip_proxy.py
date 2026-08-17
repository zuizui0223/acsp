"""Reusable, explicitly approximate ACSP field-trip budget estimator.

The estimator translates an ordered set of survey stops into hub-return field
days. It does not rank sites, infer road topology, or make biological claims.
The implementation mirrors the production ACSP-Discover proxy so package/CLI
workflows can use the same operational assumptions without importing Streamlit.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_008.8


def _point_distances_m(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    lat1, lon1 = math.radians(float(lat)), math.radians(float(lon))
    lat2, lon2 = np.radians(lats), np.radians(lons)
    a = (
        np.sin((lat2 - lat1) / 2.0) ** 2
        + math.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def estimate_operational_trip(
    plan: pd.DataFrame,
    hub_latitude: float,
    hub_longitude: float,
    survey_protocol: Optional[Mapping[str, Any]] = None,
    target_days: int = 2,
    area_hubs_override: Optional[Mapping[str, tuple[float, float]]] = None,
) -> dict[str, Any]:
    """Schedule hub-return field days under the existing ACSP route proxy.

    Required protocol fields are ``daily_field_hours``,
    ``search_minutes_per_cell``, ``access_buffer_minutes_per_cell``,
    ``protocol_id`` and ``taxon_group``. ``surface_domain`` and
    ``minimum_repeat_visits`` are optional.

    Straight-line legs are multiplied by a domain-specific distance factor and
    divided by an assumed transit speed. This is an operational proxy, not a
    road/trail/ferry routing engine.
    """
    if survey_protocol is None:
        raise ValueError("survey_protocol is required for reproducible trip-budget estimation")
    protocol = dict(survey_protocol)
    required = {
        "daily_field_hours",
        "search_minutes_per_cell",
        "access_buffer_minutes_per_cell",
        "protocol_id",
        "taxon_group",
    }
    missing = required - set(protocol)
    if missing:
        raise ValueError(f"survey_protocol lacks required fields: {', '.join(sorted(missing))}")
    if int(target_days) < 1:
        raise ValueError("target_days must be at least 1")

    surface_domain = str(protocol.get("surface_domain", "terrestrial"))
    transport = {
        "terrestrial": ("road/trail proxy", 35.0, 1.35),
        "coastal": ("mixed road/water proxy", 25.0, 1.25),
        "inland_aquatic": ("water-access proxy", 15.0, 1.15),
        "marine": ("small-vessel proxy", 22.0, 1.10),
    }.get(surface_domain, ("unknown transit proxy", 25.0, 1.25))
    assumptions = {
        "daily_field_hours": float(protocol["daily_field_hours"]),
        "operational_reserve_fraction": 0.15,
        "usable_daily_hours": round(float(protocol["daily_field_hours"]) * 0.85, 3),
        "average_road_speed_kmh": transport[1],
        "road_distance_factor": transport[2],
        "transport_mode": transport[0],
        "surface_domain": surface_domain,
        "search_minutes_per_cell": int(protocol["search_minutes_per_cell"]),
        "access_buffer_minutes_per_cell": int(protocol["access_buffer_minutes_per_cell"]),
        "start_end": "local hub within each survey area",
        "target_days": int(target_days),
        "protocol_id": str(protocol["protocol_id"]),
        "taxon_group": str(protocol["taxon_group"]),
    }
    if plan is None or plan.empty:
        return {
            **assumptions,
            "route_order_site_ids": [],
            "day_schedules": [],
            "estimated_road_km": 0.0,
            "total_hours": 0.0,
            "estimated_days": 0,
            "fits_target_days": True,
            "overtime_days": 0,
        }

    required_plan = {"site_id", "latitude", "longitude"}
    missing_plan = required_plan - set(plan.columns)
    if missing_plan:
        raise ValueError(f"plan lacks required columns: {', '.join(sorted(missing_plan))}")

    remaining = set(range(len(plan)))
    area_labels = plan.get("survey_area_id", pd.Series(1, index=plan.index)).astype(str).reset_index(drop=True)
    distinct_areas = area_labels.drop_duplicates().tolist()
    area_hubs: dict[str, tuple[float, float]] = {}
    for area in distinct_areas:
        area_positions = np.flatnonzero(area_labels.eq(area).to_numpy())
        if area_hubs_override and area in area_hubs_override:
            area_hubs[area] = tuple(map(float, area_hubs_override[area]))
        elif len(distinct_areas) == 1:
            area_hubs[area] = (float(hub_latitude), float(hub_longitude))
        else:
            area_hubs[area] = (
                float(pd.to_numeric(plan.iloc[area_positions]["latitude"], errors="coerce").mean()),
                float(pd.to_numeric(plan.iloc[area_positions]["longitude"], errors="coerce").mean()),
            )

    route_positions: list[int] = []
    day_schedules: list[dict[str, Any]] = []
    total_straight_km = 0.0
    service_hours = (
        assumptions["search_minutes_per_cell"] + assumptions["access_buffer_minutes_per_cell"]
    ) / 60.0
    while remaining:
        active_area = str(area_labels.iloc[min(remaining)])
        day_hub_lat, day_hub_lon = area_hubs[active_area]
        current_lat, current_lon = day_hub_lat, day_hub_lon
        day_positions: list[int] = []
        day_straight_km = 0.0
        day_elapsed_hours = 0.0
        overtime = False
        while remaining:
            positions = np.array(
                [position for position in sorted(remaining) if str(area_labels.iloc[position]) == active_area],
                dtype=int,
            )
            distances_km = _point_distances_m(
                current_lat,
                current_lon,
                pd.to_numeric(plan.iloc[positions]["latitude"], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(plan.iloc[positions]["longitude"], errors="coerce").to_numpy(dtype=float),
            ) / 1000.0
            order = np.argsort(distances_km)
            chosen: Optional[tuple[int, float, float]] = None
            for candidate_index in order:
                position = int(positions[int(candidate_index)])
                leg_km = float(distances_km[int(candidate_index)])
                candidate_lat = float(plan.iloc[position]["latitude"])
                candidate_lon = float(plan.iloc[position]["longitude"])
                return_km = float(
                    _point_distances_m(
                        candidate_lat,
                        candidate_lon,
                        np.array([day_hub_lat]),
                        np.array([day_hub_lon]),
                    )[0]
                ) / 1000.0
                projected_hours = day_elapsed_hours + (
                    (leg_km + return_km)
                    * assumptions["road_distance_factor"]
                    / assumptions["average_road_speed_kmh"]
                ) + service_hours
                if projected_hours <= assumptions["usable_daily_hours"]:
                    chosen = position, leg_km, return_km
                    break
            if chosen is None:
                if day_positions:
                    break
                position = int(positions[int(order[0])])
                leg_km = float(distances_km[int(order[0])])
                candidate_lat = float(plan.iloc[position]["latitude"])
                candidate_lon = float(plan.iloc[position]["longitude"])
                return_km = float(
                    _point_distances_m(
                        candidate_lat,
                        candidate_lon,
                        np.array([day_hub_lat]),
                        np.array([day_hub_lon]),
                    )[0]
                ) / 1000.0
                chosen = position, leg_km, return_km
                overtime = True
            next_pos, leg_km, _return_km = chosen
            day_straight_km += leg_km
            day_elapsed_hours += (
                leg_km * assumptions["road_distance_factor"] / assumptions["average_road_speed_kmh"]
            ) + service_hours
            day_positions.append(next_pos)
            route_positions.append(next_pos)
            remaining.remove(next_pos)
            current_lat = float(plan.iloc[next_pos]["latitude"])
            current_lon = float(plan.iloc[next_pos]["longitude"])

        return_km = float(
            _point_distances_m(
                current_lat,
                current_lon,
                np.array([day_hub_lat]),
                np.array([day_hub_lon]),
            )[0]
        ) / 1000.0
        day_straight_km += return_km
        day_elapsed_hours += (
            return_km * assumptions["road_distance_factor"] / assumptions["average_road_speed_kmh"]
        )
        overtime = overtime or day_elapsed_hours > assumptions["usable_daily_hours"]
        total_straight_km += day_straight_km
        day_schedules.append(
            {
                "day": len(day_schedules) + 1,
                "survey_area_id": active_area,
                "site_ids": [int(plan.iloc[pos]["site_id"]) for pos in day_positions],
                "straight_line_km": round(day_straight_km, 1),
                "estimated_road_km": round(day_straight_km * assumptions["road_distance_factor"], 1),
                "estimated_transit_km": round(day_straight_km * assumptions["road_distance_factor"], 1),
                "estimated_hours": round(day_elapsed_hours, 1),
                "overtime": bool(overtime),
            }
        )

    road_km = total_straight_km * assumptions["road_distance_factor"]
    travel_hours = road_km / assumptions["average_road_speed_kmh"]
    site_hours = len(plan) * service_hours
    total_hours = travel_hours + site_hours
    repeat_visits = int(protocol.get("minimum_repeat_visits", 1))
    return {
        **assumptions,
        "route_order_site_ids": [int(plan.iloc[pos]["site_id"]) for pos in route_positions],
        "day_schedules": day_schedules,
        "straight_line_route_km": round(total_straight_km, 1),
        "estimated_road_km": round(road_km, 1),
        "estimated_transit_km": round(road_km, 1),
        "travel_hours": round(travel_hours, 1),
        "site_hours": round(site_hours, 1),
        "total_hours": round(total_hours, 1),
        "estimated_days": len(day_schedules),
        "fits_target_days": len(day_schedules) <= int(target_days) and not any(day["overtime"] for day in day_schedules),
        "overtime_days": sum(bool(day["overtime"]) for day in day_schedules),
        "minimum_repeat_visits": repeat_visits,
        "inference_ready_minimum_field_days": len(day_schedules) * repeat_visits,
        "inter_area_transfers": max(0, len(distinct_areas) - 1),
        "inter_area_transfer_status": "not modeled; verify ferry/flight schedules" if len(distinct_areas) > 1 else "not applicable",
        "routing_confidence": (
            "very low; water access, launch site, navigability, currents, tides, weather, and permits are not modeled"
            if surface_domain in {"marine", "inland_aquatic"}
            else "very low; mixed land/water transfers and launch access are not modeled"
            if surface_domain == "coastal"
            else "very low for multi-island plans; field days never mix survey areas, but ferry/flight schedules are not modeled"
            if len(distinct_areas) > 1
            else "low; straight-line legs use a road-distance factor and do not model road topology, traffic, or trail time"
        ),
    }
