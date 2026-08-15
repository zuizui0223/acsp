#!/usr/bin/env python3
"""Development-only full-island microterrain discovery for Campanula microdonta.

Generator inputs are restricted to pre-2026 GBIF occurrences plus public DEMs.
2026 field detections are read only after the candidate universe is frozen and
are used solely to report development recall / upper bounds.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import rowcol, xy
from scipy.ndimage import uniform_filter

ISLAND_BOUNDS = {
    "oshima": (139.30, 34.64, 139.47, 34.82),
    "toshima": (139.24, 34.49, 139.31, 34.55),
    "niijima": (139.20, 34.33, 139.31, 34.44),
    "shikinejima": (139.18, 34.30, 139.24, 34.35),
    "kozushima": (139.09, 34.17, 139.18, 34.26),
}
FEATURES = (
    "elev",
    "slope100",
    "slope_sd100",
    "rough100",
    "tpi100",
    "range100",
    "tpi300",
    "rough300",
)


def haversine_km(lat1, lon1, lat2, lon2):
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def assign_island(lat, lon):
    hits = []
    for name, (west, south, east, north) in ISLAND_BOUNDS.items():
        if west <= lon <= east and south <= lat <= north:
            hits.append(name)
    if not hits:
        return None
    return min(
        hits,
        key=lambda name: (
            lat - (ISLAND_BOUNDS[name][1] + ISLAND_BOUNDS[name][3]) / 2
        ) ** 2
        + (
            lon - (ISLAND_BOUNDS[name][0] + ISLAND_BOUNDS[name][2]) / 2
        ) ** 2,
    )


def robust_fit(values):
    median = np.nanmedian(values, axis=0)
    q1 = np.nanquantile(values, 0.25, axis=0)
    q3 = np.nanquantile(values, 0.75, axis=0)
    scale = q3 - q1
    scale = np.where(scale > 1e-9, scale, 1.0)
    return median, scale


def robust_transform(values, median, scale):
    return (values - median) / scale


def nearest_env(values, prototypes):
    out = np.full(len(values), np.inf)
    for start in range(0, len(values), 5000):
        block = values[start : start + 5000]
        distances = ((block[:, None, :] - prototypes[None, :, :]) ** 2).sum(axis=2)
        out[start : start + len(block)] = np.sqrt(distances.min(axis=1))
    return out


def terrain_surface(path, target_res=25.0):
    with rasterio.open(path) as src:
        factor = max(1, int(round(target_res / abs(src.res[0]))))
        height = max(1, src.height // factor)
        width = max(1, src.width // factor)
        elevation = src.read(
            1,
            out_shape=(height, width),
            resampling=Resampling.average,
        ).astype("float32")
        transform = src.transform * src.transform.scale(
            src.width / width,
            src.height / height,
        )
        if src.nodata is not None:
            elevation[elevation == src.nodata] = np.nan
        elevation[elevation < -1000] = np.nan
        resolution = float(abs(transform.a))
        valid = np.isfinite(elevation).astype("float32")
        zero_filled = np.nan_to_num(elevation, nan=0.0)

        def local_mean(size, values=zero_filled):
            support = uniform_filter(valid, size=size, mode="nearest")
            total = uniform_filter(values, size=size, mode="nearest")
            with np.errstate(divide="ignore", invalid="ignore"):
                return np.where(support > 1e-6, total / support, np.nan)

        def local_sd(size):
            mean = local_mean(size)
            squared = np.nan_to_num(elevation * elevation, nan=0.0)
            mean_squared = local_mean(size, squared)
            return np.sqrt(np.maximum(mean_squared - mean * mean, 0))

        size100 = max(3, int(round(200 / resolution)) | 1)
        size300 = max(3, int(round(300 / resolution)) | 1)
        mean100 = local_mean(size100)
        mean300 = local_mean(size300)
        rough100 = local_sd(size100)
        rough300 = local_sd(size300)

        filled = np.where(np.isfinite(elevation), elevation, mean100)
        dy, dx = np.gradient(filled, resolution, resolution)
        slope = np.degrees(np.arctan(np.sqrt(dx * dx + dy * dy)))
        slope_valid = np.isfinite(slope).astype("float32")
        slope_zero = np.nan_to_num(slope, nan=0.0)
        slope_support = uniform_filter(slope_valid, size100)
        with np.errstate(divide="ignore", invalid="ignore"):
            slope100 = np.where(
                slope_support > 1e-6,
                uniform_filter(slope_zero, size100) / slope_support,
                np.nan,
            )
            slope2 = np.nan_to_num(slope * slope, nan=0.0)
            slope2_mean = np.where(
                slope_support > 1e-6,
                uniform_filter(slope2, size100) / slope_support,
                np.nan,
            )
        slope_sd100 = np.sqrt(np.maximum(slope2_mean - slope100 * slope100, 0))

        return {
            "arr": elevation,
            "transform": transform,
            "crs": src.crs,
            "res": resolution,
            "slope100": slope100,
            "slope_sd100": slope_sd100,
            "rough100": rough100,
            "tpi100": elevation - mean100,
            "range100": 4 * rough100,
            "tpi300": elevation - mean300,
            "rough300": rough300,
        }


def surface_vector(surface, row, col):
    return np.asarray(
        [
            surface["arr"][row, col],
            surface["slope100"][row, col],
            surface["slope_sd100"][row, col],
            surface["rough100"][row, col],
            surface["tpi100"][row, col],
            surface["range100"][row, col],
            surface["tpi300"][row, col],
            surface["rough300"][row, col],
        ],
        float,
    )


def thin_500m(frame):
    keep = []
    for _, subset in frame.groupby("island"):
        centers = []
        for index, row in subset.iterrows():
            if not centers:
                centers.append(index)
                continue
            old = frame.loc[centers]
            distances = haversine_km(
                row.lat,
                row.lon,
                old.lat.to_numpy(),
                old.lon.to_numpy(),
            )
            if np.min(distances) > 0.5:
                centers.append(index)
        keep.extend(centers)
    return frame.loc[keep].reset_index(drop=True)


def evaluate(candidates, detections, radius_km):
    distances = []
    for _, detection in detections.iterrows():
        subset = candidates[candidates.island.eq(detection.island)]
        if subset.empty:
            distances.append(float("inf"))
            continue
        distance = haversine_km(
            float(detection.latitude),
            float(detection.longitude),
            subset.lat.to_numpy(),
            subset.lon.to_numpy(),
        )
        distances.append(float(np.min(distance)))
    return {
        "recovered": int(sum(value <= radius_km for value in distances)),
        "total": int(len(distances)),
        "max_nearest_km": float(max(distances)),
        "nearest_km": distances,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gbif", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument(
        "--dem",
        action="append",
        required=True,
        help="ISLAND=path.tif; the Niijima raster may also serve Shikinejima",
    )
    parser.add_argument("--grid-m", type=float, default=100)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    dem = {}
    for specification in args.dem:
        island, value = specification.split("=", 1)
        dem[island] = Path(value)

    gbif = pd.read_csv(args.gbif)
    detections = pd.read_csv(args.detections)
    gbif["island"] = [
        assign_island(lat, lon)
        for lat, lon in zip(gbif["_latitude"], gbif["_longitude"])
    ]
    gbif = gbif.dropna(subset=["island"]).copy()
    gbif["lat"] = gbif["_latitude"]
    gbif["lon"] = gbif["_longitude"]

    surfaces = {}
    forward = {}
    inverse = {}
    for island, path in dem.items():
        key = str(path)
        surfaces.setdefault(key, terrain_surface(path))
        forward[island] = Transformer.from_crs(
            "EPSG:4326", surfaces[key]["crs"], always_xy=True
        )
        inverse[island] = Transformer.from_crs(
            surfaces[key]["crs"], "EPSG:4326", always_xy=True
        )

    # Generator training stage: only pre-2026 GBIF and DEM are visible here.
    occurrence_rows = []
    for _, row in gbif.iterrows():
        if row.island not in dem:
            continue
        surface = surfaces[str(dem[row.island])]
        x, y = forward[row.island].transform(row.lon, row.lat)
        rr, cc = rowcol(surface["transform"], x, y)
        if 0 <= rr < surface["arr"].shape[0] and 0 <= cc < surface["arr"].shape[1]:
            vector = surface_vector(surface, rr, cc)
            if np.isfinite(vector).all():
                occurrence_rows.append(
                    {
                        "island": row.island,
                        "lat": row.lat,
                        "lon": row.lon,
                        **dict(zip(FEATURES, vector)),
                    }
                )
    prototypes = thin_500m(pd.DataFrame(occurrence_rows))
    median, scale = robust_fit(prototypes[list(FEATURES)].to_numpy(float))
    prototype_matrix = robust_transform(
        prototypes[list(FEATURES)].to_numpy(float), median, scale
    )

    rows = []
    for path in sorted(set(dem.values()), key=str):
        surface = surfaces[str(path)]
        islands = [name for name, value in dem.items() if value == path]
        step = max(1, int(round(args.grid_m / surface["res"])))
        rr = np.arange(0, surface["arr"].shape[0], step)
        cc = np.arange(0, surface["arr"].shape[1], step)
        rr, cc = np.meshgrid(rr, cc, indexing="ij")
        rr = rr.ravel()
        cc = cc.ravel()
        values = np.column_stack(
            [surface_vector(surface, row, col) for row, col in zip(rr, cc)]
        ).T
        usable = np.isfinite(values).all(axis=1)
        rr = rr[usable]
        cc = cc[usable]
        values = values[usable]
        xs, ys = xy(surface["transform"], rr, cc, offset="center")
        longitude, latitude = inverse[islands[0]].transform(
            np.asarray(xs), np.asarray(ys)
        )
        environmental_distance = nearest_env(
            robust_transform(values, median, scale), prototype_matrix
        )
        for lat, lon, distance in zip(
            latitude, longitude, environmental_distance
        ):
            island = assign_island(lat, lon)
            if island in islands:
                rows.append((island, float(lat), float(lon), float(distance)))
    universe = pd.DataFrame(rows, columns=["island", "lat", "lon", "env_nn"])

    # Development scoring stage: field outcomes become visible only here.
    frontier = []
    for radius_km in (1.0, 0.5, 0.25, 0.1):
        for quantile in np.linspace(0.001, 1.0, 1000):
            threshold = float(np.quantile(universe.env_nn, quantile))
            selected = universe[universe.env_nn <= threshold]
            result = evaluate(selected, detections, radius_km)
            if result["recovered"] == len(detections):
                frontier.append(
                    {
                        "radius_km": radius_km,
                        "grid_fraction": float(len(selected) / len(universe)),
                        "threshold": threshold,
                        **result,
                    }
                )
                break

    args.out.mkdir(parents=True, exist_ok=True)
    universe.to_csv(args.out / "microterrain_universe.csv", index=False)
    prototypes.to_csv(args.out / "gbif_microterrain_prototypes.csv", index=False)
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "gbif_rows_in_islands": int(len(gbif)),
        "thinned_prototypes": int(len(prototypes)),
        "grid_cells": int(len(universe)),
        "frontier": frontier,
    }
    (args.out / "microterrain_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
