"""Extract environmental values for coordinates from an explicit reference grid.

The sampler is intentionally conservative: every returned value is tied to the nearest
reference cell, the geodesic match distance is reported, and points beyond the caller's
maximum distance are not imputed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class EnvironmentSample:
    values: np.ndarray
    distances_km: np.ndarray
    matched_point_indices: np.ndarray
    matched_reference_indices: np.ndarray
    feature_names: tuple[str, ...]


def _coordinates(frame: pd.DataFrame, latitude: str, longitude: str) -> np.ndarray:
    if latitude not in frame.columns or longitude not in frame.columns:
        raise ValueError(f"missing coordinate columns: {latitude}, {longitude}")
    coordinates = frame[[latitude, longitude]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    return coordinates


def _haversine_matrix_km(points: np.ndarray, reference: np.ndarray) -> np.ndarray:
    points_rad = np.radians(points)
    reference_rad = np.radians(reference)
    point_lat = points_rad[:, 0][:, None]
    point_lon = points_rad[:, 1][:, None]
    ref_lat = reference_rad[:, 0][None, :]
    ref_lon = reference_rad[:, 1][None, :]
    dlat = ref_lat - point_lat
    dlon = ref_lon - point_lon
    a = np.sin(dlat / 2.0) ** 2 + np.cos(point_lat) * np.cos(ref_lat) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def sample_environment_at_points(
    points: pd.DataFrame,
    reference: pd.DataFrame,
    feature_names: Sequence[str],
    *,
    point_latitude: str = "latitude",
    point_longitude: str = "longitude",
    reference_latitude: str = "latitude",
    reference_longitude: str = "longitude",
    maximum_distance_km: float = 1.0,
) -> EnvironmentSample:
    """Match point coordinates to the nearest complete environmental reference cell.

    Points or reference rows with invalid coordinates are ignored. Reference rows with any
    missing requested feature are removed. A point is returned only when its nearest valid
    reference cell is within ``maximum_distance_km``.
    """
    features = tuple(map(str, feature_names))
    if len(features) < 2:
        raise ValueError("at least two environmental features are required")
    missing = [name for name in features if name not in reference.columns]
    if missing:
        raise ValueError("reference lacks environmental features: " + ", ".join(missing))
    if maximum_distance_km < 0:
        raise ValueError("maximum_distance_km must be non-negative")

    point_coordinates = _coordinates(points, point_latitude, point_longitude)
    reference_coordinates = _coordinates(reference, reference_latitude, reference_longitude)
    reference_values = reference[list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(float)

    valid_points = np.isfinite(point_coordinates).all(axis=1)
    valid_reference = np.isfinite(reference_coordinates).all(axis=1) & np.isfinite(reference_values).all(axis=1)
    point_indices = np.flatnonzero(valid_points)
    reference_indices = np.flatnonzero(valid_reference)
    if len(point_indices) == 0:
        raise ValueError("no valid point coordinates")
    if len(reference_indices) == 0:
        raise ValueError("no complete environmental reference cells")

    distances = _haversine_matrix_km(point_coordinates[valid_points], reference_coordinates[valid_reference])
    nearest_local = np.argmin(distances, axis=1)
    nearest_distances = distances[np.arange(len(nearest_local)), nearest_local]
    matched = nearest_distances <= float(maximum_distance_km)
    matched_points = point_indices[matched]
    matched_reference = reference_indices[nearest_local[matched]]

    return EnvironmentSample(
        values=reference_values[matched_reference],
        distances_km=nearest_distances[matched],
        matched_point_indices=matched_points,
        matched_reference_indices=matched_reference,
        feature_names=features,
    )
