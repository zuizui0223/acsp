"""Sparse explicit movement-graph routing for automatic ACSP effort.

Only supplied movement edges exist. The graph never adds Euclidean shortcuts.
For automatic survey effort we need only hub-to-site and site-to-hub shortest
paths, so two Dijkstra passes are sufficient even when the graph is sparse.
"""
from __future__ import annotations

from collections import defaultdict
import heapq
from typing import Iterable

import numpy as np
import pandas as pd

from .movement_constraints import apply_movement_constraints
from .travel_matrix import normalize_travel_time_matrix


def _endpoint(value: object) -> str:
    if value is None or bool(pd.isna(value)):
        raise ValueError("movement graph endpoint IDs must be non-missing")
    text = str(value).strip()
    if not text:
        raise ValueError("movement graph endpoint IDs must be non-empty")
    return text


def _adjacency(edges: pd.DataFrame, *, reverse: bool = False) -> dict[str, list[tuple[float, str]]]:
    graph: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for row in edges.itertuples(index=False):
        origin = _endpoint(row.to_id if reverse else row.from_id)
        destination = _endpoint(row.from_id if reverse else row.to_id)
        graph[origin].append((float(row.travel_minutes), destination))
    for origin in graph:
        graph[origin].sort(key=lambda item: (item[0], item[1]))
    return dict(graph)


def dijkstra_minutes(edges: pd.DataFrame, source: object, *, reverse: bool = False) -> dict[str, float]:
    """Shortest travel minutes from one node using only supplied directed edges."""
    src = _endpoint(source)
    graph = _adjacency(edges, reverse=reverse)
    distances: dict[str, float] = {src: 0.0}
    queue: list[tuple[float, str]] = [(0.0, src)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        for weight, neighbour in graph.get(node, []):
            candidate = distance + float(weight)
            if candidate < distances.get(neighbour, float("inf")):
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    return distances


def hub_roundtrip_table(
    movement_edges: pd.DataFrame,
    *,
    hub_id: object,
    site_ids: Iterable[object],
    allowed_modes: Iterable[str],
    undirected: bool = False,
) -> pd.DataFrame:
    """Return shortest explicit hub round-trip costs for candidate endpoints.

    A candidate is operationally reachable only when both hub->site and
    site->hub directed paths exist. The input must declare every edge's movement
    mode explicitly. Missing paths are never replaced by straight-line distance.
    """
    if movement_edges is None or "mode" not in movement_edges.columns:
        raise ValueError("movement graph requires an explicit mode column")
    normalized = normalize_travel_time_matrix(movement_edges, undirected=undirected)
    constrained = apply_movement_constraints(normalized, allowed_modes=allowed_modes)
    if constrained.empty:
        raise ValueError("No movement edges remain after applying allowed modes")
    hub = _endpoint(hub_id)
    outward = dijkstra_minutes(constrained, hub, reverse=False)
    inward = dijkstra_minutes(constrained, hub, reverse=True)

    rows: list[dict[str, object]] = []
    for raw_site in site_ids:
        site = _endpoint(raw_site)
        outbound = outward.get(site, float("inf"))
        returning = inward.get(site, float("inf"))
        reachable = np.isfinite(outbound) and np.isfinite(returning)
        rows.append(
            {
                "site_id": site,
                "outbound_minutes": float(outbound),
                "return_minutes": float(returning),
                "roundtrip_minutes": float(outbound + returning) if reachable else float("inf"),
                "roundtrip_reachable": bool(reachable),
            }
        )
    result = pd.DataFrame(rows)
    result.attrs["hub_id"] = hub
    result.attrs["allowed_modes"] = list(constrained.attrs.get("allowed_modes", []))
    result.attrs["removed_edge_count"] = int(constrained.attrs.get("removed_edge_count", 0))
    result.attrs["constrained_edge_count"] = int(len(constrained))
    return result


def estimate_hub_roundtrip_effort(
    plan: pd.DataFrame,
    hub_latitude: float,
    hub_longitude: float,
    survey_protocol=None,
    target_days: int = 999999,
    *,
    roundtrip_table: pd.DataFrame,
) -> dict[str, object]:
    """Conservative prefix effort using explicit shortest hub round trips.

    This estimator ignores hub coordinates and the caller's target-day ceiling.
    Each site is conservatively costed as a hub round trip; no direct
    site-to-site edge is invented.
    """
    if survey_protocol is None:
        raise ValueError("survey_protocol is required")
    required = {
        "daily_field_hours",
        "search_minutes_per_cell",
        "access_buffer_minutes_per_cell",
    }
    missing = required - set(survey_protocol)
    if missing:
        raise ValueError("survey_protocol lacks required fields: " + ", ".join(sorted(missing)))
    if "site_id" not in plan.columns:
        raise ValueError("plan lacks site_id")

    lookup = roundtrip_table.set_index("site_id", drop=False)
    site_ids = [str(value).strip() for value in plan["site_id"]]
    unreachable = [
        site
        for site in site_ids
        if site not in lookup.index or not bool(lookup.loc[site, "roundtrip_reachable"])
    ]
    service = float(survey_protocol["search_minutes_per_cell"]) + float(
        survey_protocol["access_buffer_minutes_per_cell"]
    )
    usable = float(survey_protocol["daily_field_hours"]) * 60.0 * 0.85
    if usable <= 0:
        raise ValueError("daily_field_hours must be positive")

    costs: list[float] = []
    if not unreachable:
        costs = [float(lookup.loc[site, "roundtrip_minutes"]) + service for site in site_ids]

    days = 0
    current = 0.0
    long_day_sites: list[str] = []
    for site, cost in zip(site_ids, costs):
        if cost > usable:
            if current > 0:
                days += 1
                current = 0.0
            days += int(np.ceil(cost / usable))
            long_day_sites.append(site)
            continue
        if current > 0 and current + cost > usable:
            days += 1
            current = 0.0
        current += cost
    if current > 0:
        days += 1

    total_minutes = float(sum(costs)) if not unreachable else float("nan")
    return {
        "total_hours": total_minutes / 60.0 if np.isfinite(total_minutes) else float("nan"),
        "estimated_days": int(days) if not unreachable else None,
        "unreachable_site_ids": unreachable,
        "long_day_site_ids": long_day_sites,
        "fits_target_days": not unreachable,
        "routing_source": "explicit_sparse_movement_graph_hub_roundtrips",
        "hub_coordinates_used_for_routing": False,
    }
