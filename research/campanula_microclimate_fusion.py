#!/usr/bin/env python3
"""Development-only physical microclimate fusion for Campanula discovery.

All candidate scores are constructed before the inspected 2026 field clusters
are read. The experiment combines occurrence-conditioned NDVI state with
physics-motivated terrain proxies derived from public GSI DEMs and explicit
coast distance from ESA WorldCover water cells.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from pyproj import Transformer
from scipy.ndimage import distance_transform_edt

from campanula_fast_random import fast_matched_random_success
from campanula_microterrain_discovery import block_nanmean, block_valid_fraction
from campanula_ndvi_transition_discovery import (
    crop_stack,
    ndvi_surfaces,
    sample_surfaces,
)
from campanula_worldcover_discovery import (
    evaluate,
    minimum_count_for_complete_recovery,
    robust_fit,
    transform,
)

FULL_NDVI = [
    "ndvi_p50",
    "ndvi_amp",
    "ndvi_mean100",
    "ndvi_mean250",
    "ndvi_amp_mean100",
]


def parse_dem(values):
    out = {}
    for item in values:
        island, path = item.split("=", 1)
        out[island] = Path(path)
    return out


def summer_solar_proxy(normal_east, normal_north, normal_up):
    """Mean direct-beam incidence over five representative summer sun positions."""
    # Azimuth is degrees clockwise from north. These fixed positions are a
    # transparent geometric proxy, not a claim of calibrated solar radiation.
    positions = [(90, 30), (135, 50), (180, 75), (225, 50), (270, 30)]
    total = np.zeros_like(normal_up, dtype=float)
    for azimuth_deg, altitude_deg in positions:
        az = math.radians(azimuth_deg)
        alt = math.radians(altitude_deg)
        sun_east = math.cos(alt) * math.sin(az)
        sun_north = math.cos(alt) * math.cos(az)
        sun_up = math.sin(alt)
        incidence = (
            normal_east * sun_east
            + normal_north * sun_north
            + normal_up * sun_up
        )
        total += np.maximum(incidence, 0.0)
    return total / len(positions)


def dem_physics(path):
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        if src.nodata is not None:
            arr[arr == src.nodata] = np.nan
        arr[~np.isfinite(arr)] = np.nan
        native_m = abs(float(src.transform.a)) * 111_320.0 * math.cos(math.radians(34.5))
        factor = max(1, int(round(25.0 / max(native_m, 1e-6))))
        elev = block_nanmean(arr, factor)
        valid_fraction = block_valid_fraction(np.isfinite(arr), factor)
        elev[valid_fraction < 0.2] = np.nan
        transform25 = src.transform * Affine.scale(factor, factor)
        resolution_m = native_m * factor
        crs = src.crs

    row_grad_south, east_grad = np.gradient(elev, resolution_m, resolution_m)
    north_grad = -row_grad_south
    norm = np.sqrt(1.0 + east_grad * east_grad + north_grad * north_grad)
    normal_east = -east_grad / norm
    normal_north = -north_grad / norm
    normal_up = 1.0 / norm
    solar = summer_solar_proxy(normal_east, normal_north, normal_up)
    slope = np.degrees(np.arctan(np.sqrt(east_grad * east_grad + north_grad * north_grad)))
    invalid = ~np.isfinite(elev)
    for surface in (normal_east, normal_north, normal_up, solar, slope):
        surface[invalid] = np.nan
    return transform25, crs, {
        "phys_normal_east": normal_east,
        "phys_normal_north": normal_north,
        "phys_solar": solar,
        "phys_slope": slope,
    }


def sample_dem_physics(universe, prototypes, dem_paths):
    grid_rows = []
    proto_rows = []
    for island in sorted(set(universe["island"].astype(str))):
        if island not in dem_paths:
            raise RuntimeError(f"missing DEM for {island}")
        tr, crs, surfaces = dem_physics(dem_paths[island])
        ug = universe[universe["island"].astype(str).eq(island)]
        pg = prototypes[prototypes["island"].astype(str).eq(island)]
        g = sample_surfaces(tr, crs, surfaces, ug["lon"], ug["lat"])
        g.index = ug.index
        grid_rows.append(g)
        if len(pg):
            p = sample_surfaces(tr, crs, surfaces, pg["lon"], pg["lat"])
            p.index = pg.index
            proto_rows.append(p)
    grid = pd.concat(grid_rows).sort_index().reindex(universe.index)
    if proto_rows:
        proto = pd.concat(proto_rows).sort_index().reindex(prototypes.index)
    else:
        proto = pd.DataFrame(index=prototypes.index, columns=grid.columns)
    return grid, proto


def coast_surfaces(src, lon, lat):
    raw, transform_ = crop_stack(src, lon, lat, margin_deg=0.03)
    landcover = raw[0]
    water = landcover == 80
    valid = np.isin(landcover, [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100])
    pixel_m = abs(float(transform_.a)) * 111_320.0 * math.cos(math.radians(34.5))
    if not water.any():
        distance = np.full_like(landcover, np.nan, dtype=float)
    else:
        distance = distance_transform_edt(~water) * pixel_m
        distance[~valid] = np.nan
    return transform_, src.crs, {"coast_distance_m": distance}


def add_public_surfaces(universe, prototypes, ndvi_path, worldcover_path, dem_paths):
    all_lon = pd.concat([universe["lon"], prototypes["lon"]], ignore_index=True)
    all_lat = pd.concat([universe["lat"], prototypes["lat"]], ignore_index=True)
    with rasterio.open(ndvi_path) as src:
        tr, crs, surfaces = ndvi_surfaces(src, all_lon, all_lat)
        u_ndvi = sample_surfaces(tr, crs, surfaces, universe["lon"], universe["lat"])
        p_ndvi = sample_surfaces(tr, crs, surfaces, prototypes["lon"], prototypes["lat"])
    with rasterio.open(worldcover_path) as src:
        tr, crs, surfaces = coast_surfaces(src, all_lon, all_lat)
        u_coast = sample_surfaces(tr, crs, surfaces, universe["lon"], universe["lat"])
        p_coast = sample_surfaces(tr, crs, surfaces, prototypes["lon"], prototypes["lat"])
    u_phys, p_phys = sample_dem_physics(universe, prototypes, dem_paths)
    universe = pd.concat(
        [universe.reset_index(drop=True), u_ndvi.reset_index(drop=True), u_coast.reset_index(drop=True), u_phys.reset_index(drop=True)],
        axis=1,
    )
    prototypes = pd.concat(
        [prototypes.reset_index(drop=True), p_ndvi.reset_index(drop=True), p_coast.reset_index(drop=True), p_phys.reset_index(drop=True)],
        axis=1,
    )
    return universe, prototypes


def add_interactions(frame):
    frame = frame.copy()
    frame["log_coast"] = np.log1p(pd.to_numeric(frame["coast_distance_m"], errors="coerce").clip(lower=0))
    frame["solar_x_open"] = frame["phys_solar"] * (1.0 - frame["ndvi_mean100"].clip(-1, 1))
    frame["solar_x_amp"] = frame["phys_solar"] * frame["ndvi_amp"]
    frame["coast_x_amp"] = frame["log_coast"] * frame["ndvi_amp"]
    frame["solar_x_tpi100"] = frame["phys_solar"] * frame["tpi100"]
    return frame


def distance_rank(universe, prototypes, columns):
    columns = list(columns)
    proto_ok = prototypes[columns].notna().all(axis=1)
    grid_ok = universe[columns].notna().all(axis=1)
    distance = np.full(len(universe), np.inf)
    if proto_ok.sum() < 3 or grid_ok.sum() < 1:
        return distance, pd.Series(distance).rank(method="average", pct=True).to_numpy(float)
    median, scale = robust_fit(prototypes.loc[proto_ok, columns].to_numpy(float))
    p = transform(prototypes.loc[proto_ok, columns].to_numpy(float), median, scale)
    g = transform(universe.loc[grid_ok, columns].to_numpy(float), median, scale)
    chunk = 3000
    values = np.full(len(g), np.inf)
    for start in range(0, len(g), chunk):
        block = g[start : start + chunk]
        d2 = np.square(block[:, None, :] - p[None, :, :]).sum(axis=2)
        values[start : start + len(block)] = np.sqrt(d2.min(axis=1))
    distance[grid_ok.to_numpy()] = values
    rank = pd.Series(distance).rank(method="average", pct=True).to_numpy(float)
    return distance, rank


def build_scores(universe, prototypes):
    feature_sets = {
        "aspect_coast": ["phys_normal_north", "phys_normal_east", "log_coast"],
        "solar_coast": ["phys_solar", "phys_slope", "log_coast"],
        "terrain_physics": [
            "phys_normal_north", "phys_normal_east", "phys_solar", "phys_slope",
            "log_coast", "tpi100", "tpi300", "rough100", "rough300",
        ],
        "ndvi_plus_physics": FULL_NDVI + [
            "phys_normal_north", "phys_normal_east", "phys_solar", "log_coast",
        ],
        "microclimate_compact": [
            "ndvi_p50", "ndvi_amp", "ndvi_mean100", "phys_solar", "log_coast", "tpi100",
        ],
        "microclimate_interaction": [
            "ndvi_p50", "ndvi_amp", "ndvi_mean100", "phys_solar", "log_coast",
            "solar_x_open", "solar_x_amp", "coast_x_amp", "solar_x_tpi100",
        ],
    }
    scores = {}
    ranks = {}
    for name, columns in feature_sets.items():
        distance, rank = distance_rank(universe, prototypes, columns)
        scores[f"nearest_{name}"] = distance
        ranks[name] = rank

    _, ndvi_rank = distance_rank(universe, prototypes, FULL_NDVI)
    scores["nearest_ndvi_state"] = distance_rank(universe, prototypes, FULL_NDVI)[0]
    for physics_name in ("aspect_coast", "solar_coast", "terrain_physics"):
        physics_rank = ranks[physics_name]
        for physics_weight in (0.10, 0.20, 0.30, 0.40, 0.50):
            scores[f"rankblend_ndvi_{physics_name}_{physics_weight:.2f}"] = (
                (1.0 - physics_weight) * ndvi_rank + physics_weight * physics_rank
            )
        scores[f"rankand_ndvi_{physics_name}"] = np.maximum(ndvi_rank, physics_rank)
    return scores, feature_sets


def frontiers(universe, detections, score_families, radius):
    rows = []
    orders = {}
    for name, values in score_families.items():
        order = np.argsort(values, kind="mergesort")
        count, witness = minimum_count_for_complete_recovery(universe, detections, order, radius)
        if count is None:
            continue
        result = evaluate(universe.iloc[order[:count]], detections, radius)
        rows.append({
            "method": name,
            "radius_km": float(radius),
            "candidate_count": int(count),
            "grid_fraction": float(count / len(universe)),
            "detection_witness_ranks": [int(x) for x in witness],
            **result,
        })
        orders[name] = order
    rows.sort(key=lambda row: (row["candidate_count"], row["max_nearest_km"]))
    return rows, orders


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--worldcover", type=Path, required=True)
    parser.add_argument("--dem", action="append", default=[], required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--random-iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = add_public_surfaces(
        universe, prototypes, args.ndvi, args.worldcover, parse_dem(args.dem)
    )
    universe = add_interactions(universe)
    prototypes = add_interactions(prototypes)

    # Generator stage ends here: all scores are outcome-blind.
    score_families, feature_sets = build_scores(universe, prototypes)

    detections = pd.read_csv(args.detections)
    results = {}
    orders = {}
    for radius in (1.0, 0.5):
        rows, order_map = frontiers(universe, detections, score_families, radius)
        results[str(radius)] = rows
        orders[str(radius)] = order_map

    audited = []
    for i, row in enumerate(results["1.0"]):
        if row["candidate_count"] >= 867:
            continue
        order = orders["1.0"][row["method"]]
        chosen = universe.iloc[order[: row["candidate_count"]]]
        copy = dict(row)
        copy["matched_random"] = fast_matched_random_success(
            universe, detections, chosen, 1.0, args.random_iterations, args.seed + 1009 * i
        )
        copy["joint_improvement_vs_ndvi_state"] = bool(
            copy["candidate_count"] < 867
            and copy["matched_random"]["complete_recovery_probability"] < 0.2975
        )
        audited.append(copy)
    promoted = [row for row in audited if row["joint_improvement_vs_ndvi_state"]]
    best_promoted = min(
        promoted,
        key=lambda row: (row["candidate_count"], row["matched_random"]["complete_recovery_probability"]),
    ) if promoted else None

    best_1km = results["1.0"][0]
    best_500m = results["0.5"][0]
    export_row = best_promoted or best_1km
    export_order = orders["1.0"][export_row["method"]]
    export_candidates = universe.iloc[export_order[: export_row["candidate_count"]]].copy()

    args.out.mkdir(parents=True, exist_ok=True)
    export_candidates.to_csv(args.out / "best_microclimate_candidates.csv", index=False)
    pd.DataFrame(results["1.0"]).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "microclimate_frontier_1km.csv", index=False
    )
    pd.DataFrame(results["0.5"]).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "microclimate_frontier_500m.csv", index=False
    )
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "solar_proxy": "mean terrain-normal incidence over five fixed representative summer sun positions; relative proxy only",
        "feature_sets": feature_sets,
        "prior_joint_frontier_1km": {
            "candidate_count": 867,
            "grid_fraction": 867 / len(universe),
            "matched_random_complete_probability": 0.2975,
        },
        "prior_count_frontier_500m": {"candidate_count": 7853, "grid_fraction": 7853 / len(universe)},
        "frontier_1km": results["1.0"],
        "frontier_500m": results["0.5"],
        "random_audited_below_prior_count": audited,
        "best_promoted_1km": best_promoted,
        "best_count_only_1km": best_1km,
        "best_count_only_500m": best_500m,
    }
    (args.out / "microclimate_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
