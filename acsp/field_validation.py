"""Prospective field-validation helpers for ACSP recommendations.

These functions evaluate whether a frozen recommendation set recovers
independent field detections. Positive-only locations do not identify absence,
occupancy, or detection probability.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import math

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_008.8
DEFAULT_RECOVERY_RADII_KM = (0.5, 1.0, 2.0, 5.0, 10.0)


def haversine_distance_m(lat: float, lon: float, other_lats: np.ndarray, other_lons: np.ndarray) -> np.ndarray:
    """Return great-circle distances from one point to arrays of points."""
    lat1 = math.radians(float(lat))
    lon1 = math.radians(float(lon))
    lat2 = np.radians(np.asarray(other_lats, dtype=float))
    lon2 = np.radians(np.asarray(other_lons, dtype=float))
    a = (
        np.sin((lat2 - lat1) / 2.0) ** 2
        + math.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def normalize_field_locations(
    locations: pd.DataFrame,
    *,
    island_col: str = "island",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
) -> pd.DataFrame:
    """Clean a field-location table and forward-fill repeated area labels."""
    required = {island_col, latitude_col, longitude_col}
    missing = required.difference(locations.columns)
    if missing:
        raise ValueError(f"Missing field-location columns: {', '.join(sorted(missing))}")

    out = locations.copy().reset_index(drop=True)
    out[island_col] = out[island_col].replace(r"^\s*$", np.nan, regex=True).ffill()
    if out[island_col].isna().any():
        raise ValueError("The first field-location row must contain an island/area label.")
    out[latitude_col] = pd.to_numeric(out[latitude_col], errors="coerce")
    out[longitude_col] = pd.to_numeric(out[longitude_col], errors="coerce")
    if out[[latitude_col, longitude_col]].isna().any().any():
        raise ValueError("Field locations contain non-numeric coordinates.")
    if not out[latitude_col].between(-90.0, 90.0).all():
        raise ValueError("Field locations contain latitude outside [-90, 90].")
    if not out[longitude_col].between(-180.0, 180.0).all():
        raise ValueError("Field locations contain longitude outside [-180, 180].")
    out[island_col] = out[island_col].astype(str).str.strip().str.lower()
    out["field_row_id"] = np.arange(1, len(out) + 1)
    return out


def cluster_field_detections(
    locations: pd.DataFrame,
    *,
    cluster_radius_m: float = 500.0,
    area_col: str = "island",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collapse nearby positive GPS rows into independent detection clusters.

    Connected components are built separately within each survey area. Each
    cluster is represented by an observed medoid coordinate, never an artificial
    centroid that could fall outside the searched habitat.
    """
    work = normalize_field_locations(
        locations,
        island_col=area_col,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )
    radius = max(0.0, float(cluster_radius_m))
    assigned = np.full(len(work), -1, dtype=int)
    clusters: list[dict[str, object]] = []
    next_cluster = 1

    for area, group in work.groupby(area_col, sort=True):
        positions = group.index.to_numpy(dtype=int)
        lats = group[latitude_col].to_numpy(dtype=float)
        lons = group[longitude_col].to_numpy(dtype=float)
        adjacency = np.zeros((len(group), len(group)), dtype=bool)
        for i in range(len(group)):
            adjacency[i] = haversine_distance_m(lats[i], lons[i], lats, lons) <= radius

        unvisited = set(range(len(group)))
        while unvisited:
            seed = min(unvisited)
            stack = [seed]
            members: list[int] = []
            unvisited.remove(seed)
            while stack:
                current = stack.pop()
                members.append(current)
                neighbours = [j for j in sorted(unvisited) if adjacency[current, j]]
                for neighbour in neighbours:
                    unvisited.remove(neighbour)
                    stack.append(neighbour)

            member_lats = lats[members]
            member_lons = lons[members]
            distance_sums = [
                float(haversine_distance_m(lats[i], lons[i], member_lats, member_lons).sum())
                for i in members
            ]
            medoid = members[int(np.argmin(distance_sums))]
            global_positions = positions[members]
            assigned[global_positions] = next_cluster
            clusters.append(
                {
                    "detection_cluster_id": next_cluster,
                    area_col: area,
                    latitude_col: float(lats[medoid]),
                    longitude_col: float(lons[medoid]),
                    "n_source_points": int(len(members)),
                    "source_field_row_ids": ";".join(
                        str(int(value)) for value in work.loc[global_positions, "field_row_id"]
                    ),
                    "cluster_radius_m": radius,
                }
            )
            next_cluster += 1

    rows = work.copy()
    rows["detection_cluster_id"] = assigned
    return rows, pd.DataFrame(clusters)


def _valid_points(frame: pd.DataFrame, latitude_col: str, longitude_col: str, label: str) -> pd.DataFrame:
    missing = {latitude_col, longitude_col}.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing {label} columns: {', '.join(sorted(missing))}")
    out = frame.copy().reset_index(drop=True)
    out[latitude_col] = pd.to_numeric(out[latitude_col], errors="coerce")
    out[longitude_col] = pd.to_numeric(out[longitude_col], errors="coerce")
    out = out.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if out.empty:
        raise ValueError(f"No valid {label} coordinates were supplied.")
    return out


def detection_recovery_table(
    selected_candidates: pd.DataFrame,
    detection_clusters: pd.DataFrame,
    *,
    radii_km: Sequence[float] = DEFAULT_RECOVERY_RADII_KM,
    candidate_id_col: str = "site_id",
    area_col: str = "survey_area_id",
) -> pd.DataFrame:
    """Measure whether each independent detection is recovered by a candidate set."""
    candidates = _valid_points(selected_candidates, "latitude", "longitude", "candidate")
    detections = _valid_points(detection_clusters, "latitude", "longitude", "detection")
    cand_lats = candidates["latitude"].to_numpy(dtype=float)
    cand_lons = candidates["longitude"].to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    for _, detection in detections.iterrows():
        distances = haversine_distance_m(
            float(detection["latitude"]), float(detection["longitude"]), cand_lats, cand_lons
        )
        nearest_pos = int(np.argmin(distances))
        nearest = candidates.iloc[nearest_pos]
        row = detection.to_dict()
        row["nearest_candidate_id"] = nearest.get(candidate_id_col, nearest_pos + 1)
        row["nearest_candidate_distance_km"] = float(distances[nearest_pos] / 1000.0)
        if area_col in candidates.columns:
            row["nearest_candidate_area"] = nearest.get(area_col)
        for radius in radii_km:
            row[f"recovered_{float(radius):g}km"] = bool(distances[nearest_pos] <= float(radius) * 1000.0)
        rows.append(row)
    return pd.DataFrame(rows)


def recovery_summary(
    recovery: pd.DataFrame,
    *,
    radii_km: Sequence[float] = DEFAULT_RECOVERY_RADII_KM,
) -> pd.DataFrame:
    """Summarize detection-cluster recall and nearest-candidate distance."""
    if recovery.empty:
        return pd.DataFrame()
    distances = pd.to_numeric(recovery["nearest_candidate_distance_km"], errors="coerce")
    rows = []
    for radius in radii_km:
        values = recovery[f"recovered_{float(radius):g}km"].astype(bool)
        rows.append(
            {
                "radius_km": float(radius),
                "n_detection_clusters": int(len(recovery)),
                "n_recovered": int(values.sum()),
                "detection_recall": float(values.mean()),
                "median_nearest_candidate_km": float(distances.median()),
                "max_nearest_candidate_km": float(distances.max()),
            }
        )
    return pd.DataFrame(rows)


def stratified_random_recovery_benchmark(
    candidate_pool: pd.DataFrame,
    selected_candidate_ids: Iterable[object],
    detection_clusters: pd.DataFrame,
    *,
    radii_km: Sequence[float] = DEFAULT_RECOVERY_RADII_KM,
    iterations: int = 10_000,
    seed: int = 20260715,
    candidate_id_col: str = "site_id",
    area_col: str = "survey_area_id",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare frozen ACSP selections with same-pool, same-area random sets."""
    pool = _valid_points(candidate_pool, "latitude", "longitude", "candidate")
    if candidate_id_col not in pool.columns:
        raise ValueError(f"Candidate pool is missing {candidate_id_col}.")
    selected_ids = set(selected_candidate_ids)
    selected = pool[pool[candidate_id_col].isin(selected_ids)].copy()
    if len(selected) != len(selected_ids):
        missing = selected_ids.difference(set(selected[candidate_id_col]))
        raise ValueError(f"Selected candidate IDs missing from pool: {sorted(missing)}")

    if area_col in pool.columns:
        quotas = selected.groupby(area_col, dropna=False).size().astype(int).to_dict()
    else:
        quotas = {"__all__": int(len(selected))}

    observed = recovery_summary(
        detection_recovery_table(
            selected,
            detection_clusters,
            radii_km=radii_km,
            candidate_id_col=candidate_id_col,
            area_col=area_col,
        ),
        radii_km=radii_km,
    ).set_index("radius_km")

    rng = np.random.default_rng(int(seed))
    random_rows: list[dict[str, object]] = []
    total_iterations = max(1, int(iterations))
    for iteration in range(1, total_iterations + 1):
        sampled_parts = []
        if area_col in pool.columns and "__all__" not in quotas:
            for area, quota in quotas.items():
                area_pool = pool[pool[area_col].eq(area)]
                if len(area_pool) < int(quota):
                    raise ValueError(f"Area {area!r} has {len(area_pool)} candidates but quota is {quota}.")
                sampled_parts.append(
                    area_pool.iloc[rng.choice(len(area_pool), size=int(quota), replace=False)]
                )
        else:
            quota = int(quotas["__all__"])
            sampled_parts.append(pool.iloc[rng.choice(len(pool), size=quota, replace=False)])
        sampled = pd.concat(sampled_parts, ignore_index=True)
        summary = recovery_summary(
            detection_recovery_table(
                sampled,
                detection_clusters,
                radii_km=radii_km,
                candidate_id_col=candidate_id_col,
                area_col=area_col,
            ),
            radii_km=radii_km,
        )
        for row in summary.itertuples(index=False):
            random_rows.append(
                {
                    "iteration": iteration,
                    "radius_km": float(row.radius_km),
                    "random_detection_recall": float(row.detection_recall),
                }
            )

    random_draws = pd.DataFrame(random_rows)
    benchmark_rows = []
    for radius, group in random_draws.groupby("radius_km", sort=True):
        observed_recall = float(observed.loc[radius, "detection_recall"])
        random_values = group["random_detection_recall"].to_numpy(dtype=float)
        benchmark_rows.append(
            {
                "radius_km": float(radius),
                "acsp_detection_recall": observed_recall,
                "random_mean_recall": float(np.mean(random_values)),
                "random_q025": float(np.quantile(random_values, 0.025)),
                "random_q975": float(np.quantile(random_values, 0.975)),
                "lift_over_random": observed_recall - float(np.mean(random_values)),
                "randomization_p_one_sided": float(
                    (1 + np.sum(random_values >= observed_recall)) / (len(random_values) + 1)
                ),
                "iterations": total_iterations,
                "seed": int(seed),
            }
        )
    return pd.DataFrame(benchmark_rows), random_draws
