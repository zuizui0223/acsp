"""Operational trip estimation from an externally supplied travel-time matrix.

The matrix is an operational input, not an ecological predictor. It may be
produced from road, trail, ferry, or other routing systems before ACSP runs.
ACSP preserves the upstream survey-site order and uses the supplied travel
costs only to determine which ordered prefix fits a field-day budget.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

_REQUIRED_MATRIX_COLUMNS = {"from_id", "to_id", "travel_minutes"}
_TRUE_VALUES = {"1", "true", "t", "yes", "y"}
_FALSE_VALUES = {"0", "false", "f", "no", "n"}


def _normalize_endpoint(value: object) -> str:
    if value is None or bool(pd.isna(value)):
        raise ValueError("travel-matrix endpoint IDs must be non-missing")
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    text = str(value).strip()
    if not text:
        raise ValueError("travel-matrix endpoint IDs must be non-empty")
    return text


def _coerce_available(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise ValueError(f"Unsupported available value in travel matrix: {value!r}")


def normalize_travel_time_matrix(
    matrix: pd.DataFrame,
    *,
    undirected: bool = False,
) -> pd.DataFrame:
    """Validate and normalize a long-form pairwise travel-time matrix.

    Required columns are ``from_id``, ``to_id`` and ``travel_minutes``.
    Optional columns are ``distance_km``, ``mode`` and ``available``. Missing
    directed pairs are treated as unreachable. With ``undirected=True``, each
    supplied row is mirrored; conflicting reverse travel times are rejected.
    """
    if matrix is None:
        raise ValueError("travel matrix is required")
    missing = _REQUIRED_MATRIX_COLUMNS - set(matrix.columns)
    if missing:
        raise ValueError(
            "travel matrix lacks required columns: " + ", ".join(sorted(missing))
        )

    work = matrix.copy()
    if "available" in work.columns:
        available = work["available"].map(_coerce_available)
        work = work.loc[available].copy()
    work["from_id"] = work["from_id"].map(_normalize_endpoint)
    work["to_id"] = work["to_id"].map(_normalize_endpoint)
    work["travel_minutes"] = pd.to_numeric(work["travel_minutes"], errors="coerce")
    if work["travel_minutes"].isna().any() or not np.isfinite(work["travel_minutes"]).all():
        raise ValueError("travel_minutes must be finite numbers")
    if (work["travel_minutes"] < 0).any():
        raise ValueError("travel_minutes must be non-negative")

    if "distance_km" not in work.columns:
        work["distance_km"] = np.nan
    else:
        work["distance_km"] = pd.to_numeric(work["distance_km"], errors="coerce")
        finite_distance = work["distance_km"].notna()
        if not np.isfinite(work.loc[finite_distance, "distance_km"]).all():
            raise ValueError("finite distance_km values are required when supplied")
        if (work.loc[finite_distance, "distance_km"] < 0).any():
            raise ValueError("distance_km must be non-negative")
    if "mode" not in work.columns:
        work["mode"] = "unspecified"
    else:
        work["mode"] = work["mode"].fillna("unspecified").astype(str)

    columns = ["from_id", "to_id", "travel_minutes", "distance_km", "mode"]
    work = work[columns].reset_index(drop=True)
    duplicated = work.duplicated(["from_id", "to_id"], keep=False)
    if duplicated.any():
        pairs = work.loc[duplicated, ["from_id", "to_id"]].drop_duplicates()
        formatted = ", ".join(f"{row.from_id}->{row.to_id}" for row in pairs.itertuples())
        raise ValueError(f"travel matrix contains duplicate directed pairs: {formatted}")

    if undirected and not work.empty:
        lookup = {
            (row.from_id, row.to_id): row
            for row in work.itertuples(index=False)
        }
        for row in work.itertuples(index=False):
            reverse = lookup.get((row.to_id, row.from_id))
            if reverse is None:
                continue
            if not np.isclose(float(row.travel_minutes), float(reverse.travel_minutes)):
                raise ValueError(
                    "undirected travel matrix has conflicting reverse travel times for "
                    f"{row.from_id}<->{row.to_id}"
                )
            row_distance = float(row.distance_km) if pd.notna(row.distance_km) else np.nan
            reverse_distance = (
                float(reverse.distance_km) if pd.notna(reverse.distance_km) else np.nan
            )
            if np.isfinite(row_distance) and np.isfinite(reverse_distance) and not np.isclose(
                row_distance, reverse_distance
            ):
                raise ValueError(
                    "undirected travel matrix has conflicting reverse distances for "
                    f"{row.from_id}<->{row.to_id}"
                )
        mirrored = work.rename(columns={"from_id": "to_id", "to_id": "from_id"})
        work = pd.concat([work, mirrored], ignore_index=True).drop_duplicates(
            ["from_id", "to_id"], keep="first"
        )

    return work.sort_values(["from_id", "to_id"], kind="mergesort").reset_index(drop=True)


def read_travel_time_matrix(
    path: str | Path,
    *,
    undirected: bool = False,
) -> pd.DataFrame:
    """Read and normalize a travel-time matrix CSV."""
    matrix_path = Path(path)
    if not matrix_path.is_file():
        raise FileNotFoundError(f"Travel-time matrix CSV was not found: {matrix_path}")
    raw = pd.read_csv(
        matrix_path,
        dtype={"from_id": "string", "to_id": "string"},
    )
    normalized = normalize_travel_time_matrix(raw, undirected=undirected)
    normalized.attrs["source_path"] = str(matrix_path)
    normalized.attrs["undirected_input"] = bool(undirected)
    return normalized


def estimate_matrix_trip(
    plan: pd.DataFrame,
    hub_latitude: float,
    hub_longitude: float,
    survey_protocol: Optional[Mapping[str, Any]] = None,
    target_days: int = 2,
    *,
    travel_matrix: pd.DataFrame,
    hub_id: object = "__hub__",
    undirected: bool = False,
) -> dict[str, Any]:
    """Schedule hub-return field days using supplied pairwise travel costs.

    The input matrix must represent pairwise travel costs between the hub and
    all site IDs. Missing directed pairs are unreachable. Site selection order
    is not changed; this estimator is intended for evaluating prefixes selected
    upstream by :func:`acsp.select_largest_feasible_prefix`.
    """
    if survey_protocol is None:
        raise ValueError("survey_protocol is required for reproducible trip-budget estimation")
    protocol = dict(survey_protocol)
    required_protocol = {
        "daily_field_hours",
        "search_minutes_per_cell",
        "access_buffer_minutes_per_cell",
        "protocol_id",
        "taxon_group",
    }
    missing_protocol = required_protocol - set(protocol)
    if missing_protocol:
        raise ValueError(
            "survey_protocol lacks required fields: " + ", ".join(sorted(missing_protocol))
        )
    if int(target_days) < 1:
        raise ValueError("target_days must be at least 1")

    matrix_was_undirected = bool(
        getattr(travel_matrix, "attrs", {}).get("undirected_input", undirected)
    )
    normalized = normalize_travel_time_matrix(travel_matrix, undirected=undirected)
    hub = _normalize_endpoint(hub_id)
    usable_minutes = float(protocol["daily_field_hours"]) * 60.0 * 0.85
    service_minutes = float(protocol["search_minutes_per_cell"]) + float(
        protocol["access_buffer_minutes_per_cell"]
    )
    if usable_minutes <= 0:
        raise ValueError("daily_field_hours must be positive")
    if service_minutes < 0:
        raise ValueError("site service minutes must be non-negative")

    assumptions: dict[str, Any] = {
        "daily_field_hours": float(protocol["daily_field_hours"]),
        "operational_reserve_fraction": 0.15,
        "usable_daily_hours": round(usable_minutes / 60.0, 3),
        "search_minutes_per_cell": int(protocol["search_minutes_per_cell"]),
        "access_buffer_minutes_per_cell": int(protocol["access_buffer_minutes_per_cell"]),
        "target_days": int(target_days),
        "protocol_id": str(protocol["protocol_id"]),
        "taxon_group": str(protocol["taxon_group"]),
        "routing_source": "user_supplied_pairwise_travel_matrix",
        "matrix_directed": not matrix_was_undirected,
        "matrix_row_count": int(len(normalized)),
        "hub_id": hub,
        "hub_latitude": float(hub_latitude),
        "hub_longitude": float(hub_longitude),
        "hub_coordinates_used_for_routing": False,
        "start_end": "supplied hub ID at the start and end of each field day",
    }
    if plan is None or plan.empty:
        return {
            **assumptions,
            "route_order_site_ids": [],
            "day_schedules": [],
            "total_travel_minutes": 0.0,
            "site_minutes": 0.0,
            "total_hours": 0.0,
            "estimated_days": 0,
            "fits_target_days": True,
            "overtime_days": 0,
            "unreachable_site_ids": [],
            "routing_confidence": "inherits the supplied matrix; ACSP does not verify its source",
        }

    required_plan = {"site_id", "latitude", "longitude"}
    missing_plan = required_plan - set(plan.columns)
    if missing_plan:
        raise ValueError("plan lacks required columns: " + ", ".join(sorted(missing_plan)))
    site_ids = [_normalize_endpoint(value) for value in plan["site_id"].tolist()]
    if len(site_ids) != len(set(site_ids)):
        raise ValueError("plan site_id values must be unique for matrix routing")
    if hub in set(site_ids):
        raise ValueError("hub_id must not duplicate a plan site_id")

    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in normalized.itertuples(index=False):
        lookup[(row.from_id, row.to_id)] = {
            "minutes": float(row.travel_minutes),
            "distance_km": float(row.distance_km) if pd.notna(row.distance_km) else None,
            "mode": str(row.mode),
        }

    def leg(origin: str, destination: str) -> dict[str, Any] | None:
        if origin == destination:
            return {"minutes": 0.0, "distance_km": 0.0, "mode": "same_location"}
        return lookup.get((origin, destination))

    remaining = set(range(len(plan)))
    route_positions: list[int] = []
    day_schedules: list[dict[str, Any]] = []
    total_travel_minutes = 0.0
    total_distance_km = 0.0
    distance_complete = True
    unreachable_site_ids: list[str] = []

    while remaining:
        current = hub
        day_positions: list[int] = []
        day_travel_minutes = 0.0
        day_service_minutes = 0.0
        day_distance_km = 0.0
        day_distance_complete = True
        day_modes: list[str] = []
        overtime = False

        while remaining:
            options: list[tuple[float, int, dict[str, Any], dict[str, Any], float]] = []
            for position in sorted(remaining):
                site = site_ids[position]
                outbound = leg(current, site)
                return_leg = leg(site, hub)
                if outbound is None or return_leg is None:
                    continue
                projected = (
                    day_travel_minutes
                    + day_service_minutes
                    + float(outbound["minutes"])
                    + service_minutes
                    + float(return_leg["minutes"])
                )
                options.append((float(outbound["minutes"]), position, outbound, return_leg, projected))

            feasible = [option for option in options if option[4] <= usable_minutes]
            if feasible:
                chosen = min(feasible, key=lambda item: (item[0], item[1]))
            elif day_positions:
                break
            elif options:
                chosen = min(options, key=lambda item: (item[0], item[1]))
                overtime = True
            else:
                if day_positions:
                    break
                unreachable_site_ids = [site_ids[position] for position in sorted(remaining)]
                break

            _, next_position, outbound, _return_leg, _projected = chosen
            day_travel_minutes += float(outbound["minutes"])
            day_service_minutes += service_minutes
            outbound_distance = outbound["distance_km"]
            if outbound_distance is None:
                day_distance_complete = False
            else:
                day_distance_km += float(outbound_distance)
            day_modes.append(str(outbound["mode"]))
            day_positions.append(next_position)
            route_positions.append(next_position)
            remaining.remove(next_position)
            current = site_ids[next_position]

        if unreachable_site_ids and not day_positions:
            break

        return_leg = leg(current, hub)
        if return_leg is None:
            unreachable_site_ids = [site_ids[position] for position in sorted(remaining)]
            if current != hub:
                unreachable_site_ids = [current, *unreachable_site_ids]
            break
        day_travel_minutes += float(return_leg["minutes"])
        return_distance = return_leg["distance_km"]
        if return_distance is None:
            day_distance_complete = False
        else:
            day_distance_km += float(return_distance)
        day_modes.append(str(return_leg["mode"]))
        day_total_minutes = day_travel_minutes + day_service_minutes
        overtime = overtime or day_total_minutes > usable_minutes
        total_travel_minutes += day_travel_minutes
        if day_distance_complete:
            total_distance_km += day_distance_km
        else:
            distance_complete = False
        schedule_site_ids = [site_ids[position] for position in day_positions]
        schedule_areas: list[str] = []
        if "survey_area_id" in plan.columns:
            schedule_areas = list(
                dict.fromkeys(
                    str(plan.iloc[position]["survey_area_id"]) for position in day_positions
                )
            )
        day_schedules.append(
            {
                "day": len(day_schedules) + 1,
                "site_ids": schedule_site_ids,
                "survey_area_ids": schedule_areas,
                "travel_minutes": round(day_travel_minutes, 1),
                "service_minutes": round(day_service_minutes, 1),
                "estimated_hours": round(day_total_minutes / 60.0, 2),
                "distance_km": round(day_distance_km, 2) if day_distance_complete else None,
                "modes": list(dict.fromkeys(day_modes)),
                "overtime": bool(overtime),
            }
        )
        if unreachable_site_ids:
            break

    site_minutes = len(route_positions) * service_minutes
    repeat_visits = int(protocol.get("minimum_repeat_visits", 1))
    overtime_days = sum(bool(day["overtime"]) for day in day_schedules)
    fits = (
        not unreachable_site_ids
        and len(route_positions) == len(plan)
        and len(day_schedules) <= int(target_days)
        and overtime_days == 0
    )
    return {
        **assumptions,
        "route_order_site_ids": [site_ids[position] for position in route_positions],
        "day_schedules": day_schedules,
        "total_travel_minutes": round(total_travel_minutes, 1),
        "site_minutes": round(site_minutes, 1),
        "total_hours": round((total_travel_minutes + site_minutes) / 60.0, 2),
        "distance_km": round(total_distance_km, 2) if distance_complete else None,
        "distance_complete": bool(distance_complete),
        "estimated_days": len(day_schedules),
        "fits_target_days": bool(fits),
        "overtime_days": int(overtime_days),
        "unreachable_site_ids": unreachable_site_ids,
        "minimum_repeat_visits": repeat_visits,
        "inference_ready_minimum_field_days": len(day_schedules) * repeat_visits,
        "routing_confidence": (
            "inherits the supplied pairwise matrix; ACSP does not verify road/trail topology, "
            "ferry schedules, closures, permissions, traffic, weather, or safety"
        ),
    }
