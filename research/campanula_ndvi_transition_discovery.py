#!/usr/bin/env python3
"""Development-only Campanula discovery using vegetation transitions.

Candidate scores are built only from pre-2026 GBIF-derived terrain support plus
public ESA WorldCover NDVI/land-cover composites. The inspected 2026 field
clusters are opened only after every score vector has been constructed, and are
used solely to measure the development Pareto frontier.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.windows import Window, from_bounds
from scipy.ndimage import distance_transform_edt, uniform_filter

from campanula_worldcover_discovery import (
    evaluate,
    matched_random_success,
    minimum_count_for_complete_recovery,
    nearest_environment,
    robust_fit,
    transform,
)

NDVI_NODATA = 25
NDVI_SCALE = 0.008
NDVI_OFFSET = -1.0
WORLD_COVER_CLASSES = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100])


def decode_ndvi(raw: np.ndarray) -> np.ndarray:
    out = raw.astype("float32")
    out[raw == NDVI_NODATA] = np.nan
    out = out * NDVI_SCALE + NDVI_OFFSET
    out[(out < -1.01) | (out > 1.01)] = np.nan
    return out


def crop_stack(src, lon, lat, margin_deg=0.01):
    west = float(np.nanmin(lon)) - margin_deg
    east = float(np.nanmax(lon)) + margin_deg
    south = float(np.nanmin(lat)) - margin_deg
    north = float(np.nanmax(lat)) + margin_deg
    if src.crs.to_epsg() == 4326:
        bounds = (west, south, east, north)
    else:
        tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        xs, ys = tr.transform([west, east], [south, north])
        bounds = (min(xs), min(ys), max(xs), max(ys))
    window = from_bounds(*bounds, transform=src.transform)
    window = window.round_offsets().round_lengths()
    window = window.intersection(Window(0, 0, src.width, src.height))
    arr = src.read(window=window)
    return arr, src.window_transform(window)


def local_mean(arr, valid, size):
    support = uniform_filter(valid.astype("float32"), size=size, mode="nearest")
    total = uniform_filter(np.nan_to_num(arr, nan=0.0), size=size, mode="nearest")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(support > 1e-6, total / support, np.nan)


def local_sd(arr, valid, size):
    mean = local_mean(arr, valid, size)
    second = local_mean(np.square(arr), valid, size)
    return np.sqrt(np.maximum(second - mean * mean, 0))


def sample_surfaces(transform, crs, surfaces, lon, lat):
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x, y = tr.transform(np.asarray(lon), np.asarray(lat))
    rows, cols = rasterio.transform.rowcol(transform, x, y)
    rows = np.asarray(rows)
    cols = np.asarray(cols)
    out = {name: np.full(len(rows), np.nan) for name in surfaces}
    shape = next(iter(surfaces.values())).shape
    ok = (
        (rows >= 0)
        & (cols >= 0)
        & (rows < shape[0])
        & (cols < shape[1])
    )
    idx = np.flatnonzero(ok)
    for name, surface in surfaces.items():
        out[name][idx] = surface[rows[idx], cols[idx]]
    return pd.DataFrame(out)


def ndvi_surfaces(src, lon, lat):
    raw, transform = crop_stack(src, lon, lat)
    if raw.shape[0] < 3:
        raise RuntimeError(f"NDVI composite needs 3 bands; found {raw.shape[0]}")
    p90, p50, p10 = (decode_ndvi(raw[i]) for i in range(3))
    amplitude = p90 - p10
    pixel_m = abs(float(transform.a)) * 111_320.0 * math.cos(math.radians(34.5))
    valid = np.isfinite(p50)
    size100 = max(3, int(round(200 / pixel_m)) | 1)
    size250 = max(3, int(round(500 / pixel_m)) | 1)
    mean100 = local_mean(p50, valid, size100)
    mean250 = local_mean(p50, valid, size250)
    sd100 = local_sd(p50, valid, size100)
    sd250 = local_sd(p50, valid, size250)
    amp_valid = np.isfinite(amplitude)
    amp_mean100 = local_mean(amplitude, amp_valid, size100)
    amp_sd100 = local_sd(amplitude, amp_valid, size100)

    fill = np.where(valid, p50, mean100)
    dy, dx = np.gradient(fill, pixel_m, pixel_m)
    gradient = np.sqrt(dx * dx + dy * dy)
    grad_valid = np.isfinite(gradient)
    grad100 = local_mean(gradient, grad_valid, size100)
    grad250 = local_mean(gradient, grad_valid, size250)

    surfaces = {
        "ndvi_p50": p50,
        "ndvi_amp": amplitude,
        "ndvi_mean100": mean100,
        "ndvi_mean250": mean250,
        "ndvi_sd100": sd100,
        "ndvi_sd250": sd250,
        "ndvi_grad100": grad100,
        "ndvi_grad250": grad250,
        "ndvi_amp_mean100": amp_mean100,
        "ndvi_amp_sd100": amp_sd100,
        "ndvi_scale_contrast": mean100 - mean250,
        "ndvi_hetero_contrast": sd100 - sd250,
    }
    return transform, src.crs, surfaces


def cover_boundary_surfaces(src, lon, lat):
    raw, transform = crop_stack(src, lon, lat)
    land = raw[0]
    valid = np.isin(land, WORLD_COVER_CLASSES)
    boundary = np.zeros_like(valid, dtype=bool)
    boundary[1:, :] |= valid[1:, :] & valid[:-1, :] & (land[1:, :] != land[:-1, :])
    boundary[:-1, :] |= valid[:-1, :] & valid[1:, :] & (land[:-1, :] != land[1:, :])
    boundary[:, 1:] |= valid[:, 1:] & valid[:, :-1] & (land[:, 1:] != land[:, :-1])
    boundary[:, :-1] |= valid[:, :-1] & valid[:, 1:] & (land[:, :-1] != land[:, 1:])
    pixel_m = abs(float(transform.a)) * 111_320.0 * math.cos(math.radians(34.5))
    distance = distance_transform_edt(~boundary) * pixel_m
    distance[~valid] = np.nan
    return transform, src.crs, {"cover_boundary_distance_m": distance}


def distance_rank(universe, prototypes, columns):
    usable_proto = prototypes[list(columns)].notna().all(axis=1)
    usable_grid = universe[list(columns)].notna().all(axis=1)
    distance = np.full(len(universe), np.inf)
    if usable_proto.sum() < 3 or usable_grid.sum() < 1:
        return distance, pd.Series(distance).rank(method="average", pct=True).to_numpy(float)
    median, scale = robust_fit(prototypes.loc[usable_proto, list(columns)].to_numpy(float))
    proto_z = transform(prototypes.loc[usable_proto, list(columns)].to_numpy(float), median, scale)
    distance[usable_grid] = nearest_environment(
        transform(universe.loc[usable_grid, list(columns)].to_numpy(float), median, scale), proto_z
    )
    rank = pd.Series(distance).rank(method="average", pct=True).to_numpy(float)
    return distance, rank


def field_percentiles(universe, detections, distance_col):
    rows = []
    for _, point in detections.iterrows():
        island = str(point["island"])
        subset = universe[universe["island"].eq(island)]
        if subset.empty:
            continue
        coords = np.radians(subset[["lat", "lon"]].to_numpy(float))
        plat, plon = np.radians([float(point["latitude"]), float(point["longitude"])])
        a = np.sin((coords[:, 0] - plat) / 2) ** 2 + np.cos(plat) * np.cos(coords[:, 0]) * np.sin((coords[:, 1] - plon) / 2) ** 2
        nearest_idx = subset.index[int(np.argmin(a))]
        value = float(universe.loc[nearest_idx, distance_col])
        finite = subset[distance_col].replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
        percentile = float((finite <= value).mean()) if finite.size else float("nan")
        rows.append({
            "detection_cluster_id": int(point["detection_cluster_id"]),
            "island": island,
            "transition_distance": value,
            "within_island_percentile": percentile,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--worldcover", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--radius-km", type=float, default=1.0)
    parser.add_argument("--random-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    all_lon = pd.concat([universe["lon"], prototypes["lon"]], ignore_index=True)
    all_lat = pd.concat([universe["lat"], prototypes["lat"]], ignore_index=True)

    # Generator stage: only public layers and pre-2026 GBIF-derived prototypes.
    with rasterio.open(args.ndvi) as src:
        tr, crs, surfaces = ndvi_surfaces(src, all_lon, all_lat)
        u_ndvi = sample_surfaces(tr, crs, surfaces, universe["lon"], universe["lat"])
        p_ndvi = sample_surfaces(tr, crs, surfaces, prototypes["lon"], prototypes["lat"])
    with rasterio.open(args.worldcover) as src:
        tr, crs, surfaces = cover_boundary_surfaces(src, all_lon, all_lat)
        u_boundary = sample_surfaces(tr, crs, surfaces, universe["lon"], universe["lat"])
        p_boundary = sample_surfaces(tr, crs, surfaces, prototypes["lon"], prototypes["lat"])

    universe = pd.concat([universe.reset_index(drop=True), u_ndvi, u_boundary], axis=1)
    prototypes = pd.concat([prototypes.reset_index(drop=True), p_ndvi, p_boundary], axis=1)

    feature_sets = {
        "ndvi_state": ["ndvi_p50", "ndvi_amp", "ndvi_mean100", "ndvi_mean250", "ndvi_amp_mean100"],
        "ndvi_heterogeneity": ["ndvi_sd100", "ndvi_sd250", "ndvi_grad100", "ndvi_grad250", "ndvi_amp_sd100"],
        "vegetation_transition": [
            "ndvi_grad100", "ndvi_grad250", "ndvi_sd100", "ndvi_sd250",
            "ndvi_scale_contrast", "ndvi_hetero_contrast", "cover_boundary_distance_m",
        ],
        "state_plus_transition": [
            "ndvi_p50", "ndvi_amp", "ndvi_mean100", "ndvi_mean250",
            "ndvi_sd100", "ndvi_grad100", "ndvi_grad250", "ndvi_scale_contrast",
            "cover_boundary_distance_m",
        ],
    }

    terrain_rank = universe["env_nn"].rank(method="average", pct=True).to_numpy(float)
    transition_ranks = {}
    for name, columns in feature_sets.items():
        distance, rank = distance_rank(universe, prototypes, columns)
        universe[f"{name}_nn"] = distance
        transition_ranks[name] = rank

    # Development outcomes become visible only below this line; all score components are frozen.
    detections = pd.read_csv(args.detections)
    experiments = []
    candidates_by_key = {}
    for name, veg_rank in transition_ranks.items():
        score_specs = []
        for terrain_weight in np.linspace(0.0, 1.0, 21):
            score_specs.append((f"weighted_{terrain_weight:.2f}", terrain_weight * terrain_rank + (1 - terrain_weight) * veg_rank))
        score_specs.extend([
            ("and_max", np.maximum(terrain_rank, veg_rank)),
            ("euclid_and", np.sqrt(terrain_rank * terrain_rank + veg_rank * veg_rank)),
        ])
        for fusion, score in score_specs:
            order = np.argsort(score, kind="mergesort")
            count, witness = minimum_count_for_complete_recovery(universe, detections, order, args.radius_km)
            if count is None:
                continue
            chosen = universe.iloc[order[:count]].copy()
            result = evaluate(chosen, detections, args.radius_km)
            key = (name, fusion)
            candidates_by_key[key] = chosen
            experiments.append({
                "feature_set": name,
                "fusion": fusion,
                "candidate_count": int(count),
                "grid_fraction": float(count / len(universe)),
                "detection_witness_ranks": [int(x) for x in witness],
                **result,
            })

    if not experiments:
        raise RuntimeError("No NDVI/transition configuration achieved complete 1-km recovery")
    experiments.sort(key=lambda row: (row["candidate_count"], row["max_nearest_km"]))
    best_row = dict(experiments[0])
    best_candidates = candidates_by_key[(best_row["feature_set"], best_row["fusion"])]
    best_random = matched_random_success(
        universe, detections, best_candidates, args.radius_km, args.random_iterations, args.seed
    )
    best_row["matched_random"] = best_random

    distance_col = f"{best_row['feature_set']}_nn"
    residual_audit = field_percentiles(universe, detections, distance_col)

    args.out.mkdir(parents=True, exist_ok=True)
    best_candidates.to_csv(args.out / "best_ndvi_transition_candidates.csv", index=False)
    prototypes.to_csv(args.out / "ndvi_transition_gbif_prototypes.csv", index=False)
    pd.DataFrame(residual_audit).to_csv(args.out / "field_transition_percentiles.csv", index=False)
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "ndvi_source": "ESA WorldCover annual Sentinel-2 NDVI composite 2021 v2; bands p90,p50,p10",
        "feature_sets": feature_sets,
        "experiments": experiments,
        "best": best_row,
        "field_transition_percentiles": residual_audit,
    }
    (args.out / "ndvi_transition_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
