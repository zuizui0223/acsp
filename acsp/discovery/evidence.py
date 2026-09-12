"""Taxon-neutral occurrence evidence primitives for N4 discovery development."""
from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class OccurrenceCluster:
    """One deterministic spatial cluster of occurrence evidence."""

    members: tuple[tuple[float, float, str], ...]

    @property
    def size(self) -> int:
        return len(self.members)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = p2 - p1
    dl = math.radians(float(lon2) - float(lon1))
    value = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def cluster_min_distance_km(left: OccurrenceCluster, right: OccurrenceCluster) -> float:
    if not left.members or not right.members:
        return float("inf")
    return min(
        haversine_km(a_lat, a_lon, b_lat, b_lon)
        for a_lat, a_lon, _ in left.members
        for b_lat, b_lon, _ in right.members
    )


def complete_link_clusters(
    frame: pd.DataFrame,
    *,
    radius_km: float = 0.5,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    id_col: str = "occurrence_id",
) -> list[OccurrenceCluster]:
    """Greedy deterministic complete-link clustering with a bounded diameter.

    A point can join a cluster only when it is within ``radius_km`` of every
    existing member, preventing single-link chaining from creating arbitrarily
    extended population anchors.
    """
    if float(radius_km) <= 0:
        raise ValueError("radius_km must be positive")
    required = {latitude_col, longitude_col, id_col}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"occurrence evidence missing columns: {missing}")
    if frame.empty:
        return []
    work = frame[[latitude_col, longitude_col, id_col]].copy()
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).copy()
    work[id_col] = work[id_col].astype(str)
    work = work.sort_values([latitude_col, longitude_col, id_col], kind="mergesort")

    clusters: list[list[tuple[float, float, str]]] = []
    for row in work.itertuples(index=False, name=None):
        lat, lon, occurrence_id = float(row[0]), float(row[1]), str(row[2])
        point = (lat, lon, occurrence_id)
        for cluster in clusters:
            if all(haversine_km(lat, lon, old_lat, old_lon) <= float(radius_km) + 1e-12 for old_lat, old_lon, _ in cluster):
                cluster.append(point)
                break
        else:
            clusters.append([point])
    return [OccurrenceCluster(tuple(cluster)) for cluster in clusters]


def cluster_medoid(cluster: OccurrenceCluster) -> dict[str, object]:
    """Return one observed member minimizing total within-cluster distance."""
    if not cluster.members:
        raise ValueError("cluster cannot be empty")
    candidates: list[tuple[float, float, float, str]] = []
    for lat, lon, occurrence_id in cluster.members:
        total = sum(haversine_km(lat, lon, old_lat, old_lon) for old_lat, old_lon, _ in cluster.members)
        candidates.append((float(total), float(lat), float(lon), str(occurrence_id)))
    total, lat, lon, occurrence_id = min(candidates)
    return {
        "latitude": lat,
        "longitude": lon,
        "occurrence_id": occurrence_id,
        "cluster_size": int(cluster.size),
        "medoid_total_distance_km": total,
    }


def cluster_medoid_table(clusters: list[OccurrenceCluster], *, prefix: str = "H") -> pd.DataFrame:
    """Project clusters to one deterministic population-anchor table."""
    rows: list[dict[str, object]] = []
    for index, cluster in enumerate(clusters):
        row = cluster_medoid(cluster)
        row["cluster_index"] = int(index)
        row["cluster_id"] = f"{prefix}{index:04d}"
        rows.append(row)
    return pd.DataFrame(rows)
