"""Convert a weighted transport network into explicit ACSP patch reachability edges.

This module is provider-neutral and strictly downstream of validated candidate
patch generation. Candidate-to-candidate reachability is based on weighted
network shortest paths, not straight-line proximity. Straight-line geometry is
used only to attach each candidate to the nearest supplied transport node in the
same survey area; that off-network access distance is included in the movement
limit.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from .coverage import EARTH_RADIUS_KM


@dataclass(frozen=True)
class TransportReachabilityAudit:
    candidate_count: int
    network_node_count: int
    network_edge_count: int
    attached_candidate_count: int
    unattached_candidate_count: int
    emitted_patch_edge_count: int
    max_network_transition_km: float
    candidate_group_column: str
    network_group_column: str
    network_distance_used: bool = True
    off_network_access_included: bool = True
    candidate_pair_straight_line_used: bool = False
    user_site_count_required: bool = False
    user_coverage_target_required: bool = False
    route_time_claim: bool = False
    timetable_claim: bool = False
    legal_access_claim: bool = False
    safety_claim: bool = False
    field_efficiency_claim: bool = False
    validated_candidate_membership_changed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_count": self.candidate_count,
            "network_node_count": self.network_node_count,
            "network_edge_count": self.network_edge_count,
            "attached_candidate_count": self.attached_candidate_count,
            "unattached_candidate_count": self.unattached_candidate_count,
            "emitted_patch_edge_count": self.emitted_patch_edge_count,
            "max_network_transition_km": self.max_network_transition_km,
            "candidate_group_column": self.candidate_group_column,
            "network_group_column": self.network_group_column,
            "network_distance_used": self.network_distance_used,
            "off_network_access_included": self.off_network_access_included,
            "candidate_pair_straight_line_used": self.candidate_pair_straight_line_used,
            "user_site_count_required": self.user_site_count_required,
            "user_coverage_target_required": self.user_coverage_target_required,
            "route_time_claim": self.route_time_claim,
            "timetable_claim": self.timetable_claim,
            "legal_access_claim": self.legal_access_claim,
            "safety_claim": self.safety_claim,
            "field_efficiency_claim": self.field_efficiency_claim,
            "validated_candidate_membership_changed": self.validated_candidate_membership_changed,
        }


def _validate_transport_inputs(
    candidates: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    patch_id_col: str,
    candidate_group_col: str,
    node_id_col: str,
    network_group_col: str,
    latitude_col: str,
    longitude_col: str,
    edge_from_col: str,
    edge_to_col: str,
    edge_distance_col: str,
) -> tuple[pd.Series, pd.Series, dict[str, int], list[list[tuple[int, float]]], int]:
    for column in (patch_id_col, candidate_group_col, latitude_col, longitude_col):
        if column not in candidates.columns:
            raise ValueError(f"candidate table lacks required column {column!r}")
    for column in (node_id_col, network_group_col, latitude_col, longitude_col):
        if column not in nodes.columns:
            raise ValueError(f"transport-node table lacks required column {column!r}")
    for column in (edge_from_col, edge_to_col, edge_distance_col):
        if column not in edges.columns:
            raise ValueError(f"transport-edge table lacks required column {column!r}")

    if candidates[patch_id_col].isna().any() or candidates[candidate_group_col].isna().any():
        raise ValueError("candidate patch IDs and survey-area IDs must not be missing")
    patch_ids = candidates[patch_id_col].astype(str)
    if patch_ids.duplicated().any():
        duplicates = sorted(patch_ids[patch_ids.duplicated(keep=False)].unique())
        raise ValueError(f"candidate patch IDs must be unique; duplicates: {duplicates}")

    if nodes[node_id_col].isna().any() or nodes[network_group_col].isna().any():
        raise ValueError("transport node IDs and survey-area IDs must not be missing")
    node_ids = nodes[node_id_col].astype(str)
    if node_ids.duplicated().any():
        duplicates = sorted(node_ids[node_ids.duplicated(keep=False)].unique())
        raise ValueError(f"transport node IDs must be unique; duplicates: {duplicates}")

    candidate_coords = candidates[[latitude_col, longitude_col]].apply(pd.to_numeric, errors="coerce")
    node_coords = nodes[[latitude_col, longitude_col]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(candidate_coords.to_numpy(float)).all():
        raise ValueError("candidate coordinates must be finite")
    if len(nodes) and not np.isfinite(node_coords.to_numpy(float)).all():
        raise ValueError("transport-node coordinates must be finite")

    if edges[edge_from_col].isna().any() or edges[edge_to_col].isna().any():
        raise ValueError("transport edge node IDs must not be missing")
    edge_distances = pd.to_numeric(edges[edge_distance_col], errors="coerce").to_numpy(float)
    if not np.isfinite(edge_distances).all() or (edge_distances < 0.0).any():
        raise ValueError("transport edge distances must be finite and non-negative")

    node_to_row = {node_id: i for i, node_id in enumerate(node_ids.tolist())}
    edge_from = edges[edge_from_col].astype(str).tolist()
    edge_to = edges[edge_to_col].astype(str).tolist()
    unknown = sorted((set(edge_from) | set(edge_to)).difference(node_to_row))
    if unknown:
        raise ValueError(f"transport graph references unknown node IDs: {unknown}")

    # Collapse duplicate/reversed undirected edges to their minimum supplied distance.
    unique_edges: dict[tuple[int, int], float] = {}
    for from_id, to_id, distance_m in zip(edge_from, edge_to, edge_distances):
        left = int(node_to_row[from_id])
        right = int(node_to_row[to_id])
        if left == right:
            continue
        a, b = sorted((left, right))
        key = (a, b)
        current = unique_edges.get(key)
        distance = float(distance_m)
        if current is None or distance < current:
            unique_edges[key] = distance

    adjacency: list[list[tuple[int, float]]] = [[] for _ in range(len(nodes))]
    for (left, right), distance_m in sorted(unique_edges.items()):
        adjacency[left].append((right, distance_m))
        adjacency[right].append((left, distance_m))

    return patch_ids, node_ids, node_to_row, adjacency, int(len(unique_edges))


def _snap_candidates_to_same_area_nodes(
    candidates: pd.DataFrame,
    nodes: pd.DataFrame,
    *,
    patch_ids: pd.Series,
    node_ids: pd.Series,
    candidate_group_col: str,
    network_group_col: str,
    latitude_col: str,
    longitude_col: str,
) -> pd.DataFrame:
    attachments = pd.DataFrame(
        {
            "candidate_patch_id": patch_ids.to_numpy(),
            "network_node_id": pd.array([pd.NA] * len(candidates), dtype="string"),
            "off_network_access_distance_m": np.full(len(candidates), np.nan, dtype=float),
            "network_attached": np.zeros(len(candidates), dtype=bool),
        }
    )
    if candidates.empty or nodes.empty:
        return attachments

    candidate_groups = candidates[candidate_group_col].astype(str)
    network_groups = nodes[network_group_col].astype(str)
    for group in candidate_groups.drop_duplicates().tolist():
        candidate_idx = np.flatnonzero(candidate_groups.to_numpy() == group)
        node_idx = np.flatnonzero(network_groups.to_numpy() == group)
        if len(candidate_idx) == 0 or len(node_idx) == 0:
            continue
        node_coords = np.radians(nodes.iloc[node_idx][[latitude_col, longitude_col]].to_numpy(float))
        candidate_coords = np.radians(
            candidates.iloc[candidate_idx][[latitude_col, longitude_col]].to_numpy(float)
        )
        tree = BallTree(node_coords, metric="haversine")
        distances_rad, nearest_local = tree.query(candidate_coords, k=1)
        nearest_global = node_idx[nearest_local[:, 0].astype(int)]
        attachments.loc[candidate_idx, "network_node_id"] = pd.array(
            node_ids.iloc[nearest_global].astype(str).tolist(), dtype="string"
        )
        attachments.loc[candidate_idx, "off_network_access_distance_m"] = (
            distances_rad[:, 0] * EARTH_RADIUS_KM * 1000.0
        )
        attachments.loc[candidate_idx, "network_attached"] = True
    return attachments


def _dijkstra_distances(
    adjacency: list[list[tuple[int, float]]],
    source: int,
    *,
    cutoff_m: float,
) -> dict[int, float]:
    distances: dict[int, float] = {int(source): 0.0}
    queue: list[tuple[float, int]] = [(0.0, int(source))]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        if distance > cutoff_m:
            continue
        for neighbour, edge_distance in adjacency[node]:
            next_distance = distance + float(edge_distance)
            if next_distance > cutoff_m:
                continue
            if next_distance < distances.get(neighbour, float("inf")):
                distances[neighbour] = next_distance
                heapq.heappush(queue, (next_distance, int(neighbour)))
    return distances


def build_patch_reachability_edges_from_transport_network(
    candidates: pd.DataFrame,
    transport_nodes: pd.DataFrame,
    transport_edges: pd.DataFrame,
    *,
    max_network_transition_km: float,
    patch_id_col: str = "candidate_patch_id",
    candidate_group_col: str = "survey_area_id",
    node_id_col: str = "network_node_id",
    network_group_col: str = "survey_area_id",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    edge_from_col: str = "from_node_id",
    edge_to_col: str = "to_node_id",
    edge_distance_col: str = "distance_m",
) -> tuple[pd.DataFrame, pd.DataFrame, TransportReachabilityAudit]:
    """Build explicit patch edges from a weighted undirected transport graph.

    The only movement tuning input is ``max_network_transition_km``. A patch is
    attached to the nearest supplied transport node in the same survey area.
    For two attached patches, the total transition distance is:

        source off-network access + transport shortest path + target access.

    A cross-area transition can therefore exist only when the supplied transport
    graph itself contains a cross-area edge (for example a ferry connection).
    """
    if float(max_network_transition_km) <= 0.0:
        raise ValueError("max_network_transition_km must be positive")

    work = candidates.reset_index(drop=True).copy()
    nodes = transport_nodes.reset_index(drop=True).copy()
    graph_edges = transport_edges.reset_index(drop=True).copy()
    patch_ids, node_ids, node_to_row, adjacency, network_edge_count = _validate_transport_inputs(
        work,
        nodes,
        graph_edges,
        patch_id_col=patch_id_col,
        candidate_group_col=candidate_group_col,
        node_id_col=node_id_col,
        network_group_col=network_group_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
        edge_from_col=edge_from_col,
        edge_to_col=edge_to_col,
        edge_distance_col=edge_distance_col,
    )
    attachments = _snap_candidates_to_same_area_nodes(
        work,
        nodes,
        patch_ids=patch_ids,
        node_ids=node_ids,
        candidate_group_col=candidate_group_col,
        network_group_col=network_group_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )

    max_transition_m = float(max_network_transition_km) * 1000.0
    attached_indices = np.flatnonzero(attachments["network_attached"].to_numpy(bool))
    anchor_rows: dict[int, int] = {}
    for candidate_index in attached_indices:
        anchor_id = str(attachments.iloc[candidate_index]["network_node_id"])
        anchor_rows[int(candidate_index)] = int(node_to_row[anchor_id])

    distance_cache: dict[int, dict[int, float]] = {}
    rows: list[dict[str, object]] = []
    for position, left_idx in enumerate(attached_indices):
        left_idx = int(left_idx)
        source_node = anchor_rows[left_idx]
        if source_node not in distance_cache:
            distance_cache[source_node] = _dijkstra_distances(
                adjacency,
                source_node,
                cutoff_m=max_transition_m,
            )
        network_distances = distance_cache[source_node]
        left_access = float(attachments.iloc[left_idx]["off_network_access_distance_m"])
        for right_idx_raw in attached_indices[position + 1 :]:
            right_idx = int(right_idx_raw)
            target_node = anchor_rows[right_idx]
            network_distance = network_distances.get(target_node)
            if network_distance is None:
                continue
            right_access = float(attachments.iloc[right_idx]["off_network_access_distance_m"])
            total_distance = left_access + float(network_distance) + right_access
            if total_distance > max_transition_m + 1e-9:
                continue
            rows.append(
                {
                    "from_patch_id": str(patch_ids.iloc[left_idx]),
                    "to_patch_id": str(patch_ids.iloc[right_idx]),
                    "from_network_node_id": str(attachments.iloc[left_idx]["network_node_id"]),
                    "to_network_node_id": str(attachments.iloc[right_idx]["network_node_id"]),
                    "from_access_distance_m": left_access,
                    "network_path_distance_m": float(network_distance),
                    "to_access_distance_m": right_access,
                    "total_transition_distance_m": float(total_distance),
                }
            )

    edge_columns = [
        "from_patch_id",
        "to_patch_id",
        "from_network_node_id",
        "to_network_node_id",
        "from_access_distance_m",
        "network_path_distance_m",
        "to_access_distance_m",
        "total_transition_distance_m",
    ]
    patch_edges = pd.DataFrame(rows, columns=edge_columns)
    attached_count = int(attachments["network_attached"].sum())
    audit = TransportReachabilityAudit(
        candidate_count=int(len(work)),
        network_node_count=int(len(nodes)),
        network_edge_count=network_edge_count,
        attached_candidate_count=attached_count,
        unattached_candidate_count=int(len(work) - attached_count),
        emitted_patch_edge_count=int(len(patch_edges)),
        max_network_transition_km=float(max_network_transition_km),
        candidate_group_column=candidate_group_col,
        network_group_column=network_group_col,
    )
    return patch_edges, attachments, audit
