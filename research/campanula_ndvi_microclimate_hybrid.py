#!/usr/bin/env python3
"""Development-only NDVI + microclimate hybrid discovery for Campanula.

The generator combines the strongest public-data signal found so far (ESA
WorldCover annual NDVI state) with a deliberately weak correction from GSI DEM
aspect and coastal-exposure proxies. All candidate score vectors are constructed
before the inspected 2026 field clusters are read. The weight grid is explicitly
Campanula-development-tuned and is not a confirmatory result.
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
from rasterio.transform import rowcol
from scipy.ndimage import distance_transform_edt

from campanula_ndvi_transition_discovery import ndvi_surfaces, sample_surfaces
from campanula_worldcover_discovery import (
    evaluate,
    haversine_km,
    minimum_count_for_complete_recovery,
    nearest_environment,
    robust_fit,
    transform,
)

NDVI_STATE = [
    "ndvi_p50",
    "ndvi_amp",
    "ndvi_mean100",
    "ndvi_mean250",
    "ndvi_amp_mean100",
]
MICROCLIMATE = ["northness", "eastness", "log_coast_distance"]
JOINT_STATE = NDVI_STATE + MICROCLIMATE
BASELINE_CANDIDATES = 867
BASELINE_GRID_FRACTION = 0.038053
BASELINE_RANDOM_COMPLETE = 0.2975


def fit_distance_rank(grid: pd.DataFrame, proto: pd.DataFrame, columns: list[str]):
    good_p = proto[columns].notna().all(axis=1)
    good_g = grid[columns].notna().all(axis=1)
    distance = np.full(len(grid), np.inf)
    if int(good_p.sum()) < 3 or int(good_g.sum()) < 1:
        return distance, np.ones(len(grid), dtype=float)
    median, scale = robust_fit(proto.loc[good_p, columns].to_numpy(float))
    pz = transform(proto.loc[good_p, columns].to_numpy(float), median, scale)
    gz = transform(grid.loc[good_g, columns].to_numpy(float), median, scale)
    distance[good_g.to_numpy()] = nearest_environment(gz, pz)
    rank = pd.Series(distance).replace([np.inf, -np.inf], np.nan).rank(
        method="average", pct=True
    )
    return distance, rank.fillna(1.0).to_numpy(float)


def terrain_microclimate_surface(path: Path, target_res=25.0):
    with rasterio.open(path) as src:
        factor = max(1, int(round(target_res / abs(float(src.res[0])))))
        height = max(1, src.height // factor)
        width = max(1, src.width // factor)
        elevation = src.read(
            1, out_shape=(height, width), resampling=Resampling.average
        ).astype("float32")
        transform_out = src.transform * src.transform.scale(
            src.width / width, src.height / height
        )
        if src.nodata is not None:
            elevation[elevation == src.nodata] = np.nan
        elevation[elevation < -1000] = np.nan
        valid = np.isfinite(elevation)
        if not valid.any():
            raise RuntimeError(f"No usable DEM cells in {path}")
        fill_value = float(np.nanmedian(elevation))
        filled = np.where(valid, elevation, fill_value)
        res = abs(float(transform_out.a))
        dy, dx = np.gradient(filled, res, res)
        norm = np.sqrt(dx * dx + dy * dy)
        with np.errstate(divide="ignore", invalid="ignore"):
            eastness = np.where(norm > 1e-9, -dx / norm, 0.0)
            northness = np.where(norm > 1e-9, dy / norm, 0.0)
        # Distance from valid land-like DEM support to its nearest invalid edge.
        # This is a coastal/exposure proxy, not a literal shoreline distance.
        coast_distance = distance_transform_edt(valid) * res
        northness[~valid] = np.nan
        eastness[~valid] = np.nan
        coast_distance[~valid] = np.nan
        return {
            "crs": src.crs,
            "transform": transform_out,
            "shape": elevation.shape,
            "northness": northness.astype("float32"),
            "eastness": eastness.astype("float32"),
            "log_coast_distance": np.log1p(coast_distance).astype("float32"),
        }


def sample_microclimate(frame: pd.DataFrame, surfaces: dict[str, dict], dem_map: dict[str, Path]):
    out = pd.DataFrame(index=frame.index, columns=MICROCLIMATE, dtype=float)
    for island, idx in frame.groupby("island").groups.items():
        island = str(island)
        if island not in dem_map:
            continue
        surface = surfaces[str(dem_map[island])]
        tr = Transformer.from_crs("EPSG:4326", surface["crs"], always_xy=True)
        idx = np.asarray(list(idx), dtype=int)
        x, y = tr.transform(frame.loc[idx, "lon"].to_numpy(), frame.loc[idx, "lat"].to_numpy())
        rr, cc = rowcol(surface["transform"], x, y)
        rr = np.asarray(rr)
        cc = np.asarray(cc)
        ok = (
            (rr >= 0) & (cc >= 0)
            & (rr < surface["shape"][0]) & (cc < surface["shape"][1])
        )
        for name in MICROCLIMATE:
            values = np.full(len(idx), np.nan)
            values[ok] = surface[name][rr[ok], cc[ok]]
            out.loc[idx, name] = values
    return out


def fast_matched_random_success(
    universe: pd.DataFrame,
    detections: pd.DataFrame,
    selected: pd.DataFrame,
    radius_km: float,
    iterations: int,
    seed: int,
):
    rng = np.random.default_rng(seed)
    per_island = selected.groupby("island").size().to_dict()
    detections = detections.reset_index(drop=True)
    matrices = {}
    for island, frame in universe.groupby("island"):
        frame = frame.reset_index(drop=True)
        m = np.zeros((len(frame), len(detections)), dtype=bool)
        for j, point in detections.iterrows():
            if str(point["island"]) != str(island):
                continue
            d = haversine_km(
                float(point["latitude"]), float(point["longitude"]),
                frame["lat"].to_numpy(), frame["lon"].to_numpy(),
            )
            m[:, j] = d <= radius_km
        matrices[str(island)] = m
    recovered = np.zeros(iterations, dtype=int)
    for rep in range(iterations):
        covered = np.zeros(len(detections), dtype=bool)
        for island, count in per_island.items():
            m = matrices[str(island)]
            n = min(int(count), len(m))
            if n:
                draw = rng.choice(len(m), size=n, replace=False)
                covered |= m[draw].any(axis=0)
        recovered[rep] = int(covered.sum())
    return {
        "iterations": int(iterations),
        "complete_recovery_probability": float(np.mean(recovered == len(detections))),
        "mean_recovered": float(np.mean(recovered)),
        "q05_recovered": float(np.quantile(recovered, 0.05)),
        "q95_recovered": float(np.quantile(recovered, 0.95)),
    }


def pareto_rows(rows: list[dict]):
    result = []
    for row in rows:
        dominated = False
        for other in rows:
            if other is row:
                continue
            if (
                other["candidate_count"] <= row["candidate_count"]
                and other["matched_random"]["complete_recovery_probability"]
                    <= row["matched_random"]["complete_recovery_probability"]
                and (
                    other["candidate_count"] < row["candidate_count"]
                    or other["matched_random"]["complete_recovery_probability"]
                        < row["matched_random"]["complete_recovery_probability"]
                )
            ):
                dominated = True
                break
        if not dominated:
            result.append(row)
    return sorted(result, key=lambda r: (r["candidate_count"], r["matched_random"]["complete_recovery_probability"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--dem", action="append", required=True, help="ISLAND=path.tif")
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--radius-km", type=float, default=1.0)
    parser.add_argument("--random-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    dem_map = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    lon = pd.concat([universe["lon"], prototypes["lon"]], ignore_index=True)
    lat = pd.concat([universe["lat"], prototypes["lat"]], ignore_index=True)

    # Generator stage: no 2026 outcomes are visible here.
    with rasterio.open(args.ndvi) as src:
        tr, crs, surfaces_ndvi = ndvi_surfaces(src, lon, lat)
        u_ndvi = sample_surfaces(tr, crs, surfaces_ndvi, universe["lon"], universe["lat"])
        p_ndvi = sample_surfaces(tr, crs, surfaces_ndvi, prototypes["lon"], prototypes["lat"])
    universe = pd.concat([universe.reset_index(drop=True), u_ndvi], axis=1)
    prototypes = pd.concat([prototypes.reset_index(drop=True), p_ndvi], axis=1)

    surfaces = {}
    for path in sorted(set(dem_map.values()), key=str):
        surfaces[str(path)] = terrain_microclimate_surface(path)
    universe = pd.concat(
        [universe, sample_microclimate(universe, surfaces, dem_map)], axis=1
    )
    prototypes = pd.concat(
        [prototypes, sample_microclimate(prototypes, surfaces, dem_map)], axis=1
    )

    ndvi_distance, ndvi_rank = fit_distance_rank(universe, prototypes, NDVI_STATE)
    joint_distance, joint_rank = fit_distance_rank(universe, prototypes, JOINT_STATE)
    universe["ndvi_state_nn"] = ndvi_distance
    universe["joint_ndvi_aspect_coast_nn"] = joint_distance

    # This fine grid was motivated by inspected Campanula development outcomes.
    weights = np.round(np.arange(0.85, 1.0001, 0.005), 3)
    score_vectors = {
        f"ndvi_weight_{weight:.3f}": weight * ndvi_rank + (1.0 - weight) * joint_rank
        for weight in weights
    }

    # Development evaluation starts only here.
    detections = pd.read_csv(args.detections)
    rows = []
    candidates = {}
    for offset, (name, score) in enumerate(score_vectors.items()):
        order = np.argsort(score, kind="mergesort")
        count, witness = minimum_count_for_complete_recovery(
            universe, detections, order, args.radius_km
        )
        if count is None:
            continue
        chosen = universe.iloc[order[:count]].copy()
        recovery = evaluate(chosen, detections, args.radius_km)
        random = fast_matched_random_success(
            universe, detections, chosen, args.radius_km,
            args.random_iterations, args.seed + offset,
        )
        row = {
            "score": name,
            "ndvi_weight": float(name.rsplit("_", 1)[-1]),
            "candidate_count": int(count),
            "grid_fraction": float(count / len(universe)),
            "candidate_counts_by_island": {
                str(k): int(v) for k, v in chosen.groupby("island").size().to_dict().items()
            },
            "detection_witness_ranks": [int(x) for x in witness],
            **recovery,
            "matched_random": random,
        }
        rows.append(row)
        candidates[name] = chosen

    if not rows:
        raise RuntimeError("No hybrid score achieved complete development recovery")
    frontier = pareto_rows(rows)
    count_best = min(frontier, key=lambda r: (r["candidate_count"], r["matched_random"]["complete_recovery_probability"]))
    random_best = min(frontier, key=lambda r: (r["matched_random"]["complete_recovery_probability"], r["candidate_count"]))
    promoted = [
        r for r in frontier
        if r["grid_fraction"] < BASELINE_GRID_FRACTION
        and r["matched_random"]["complete_recovery_probability"] < BASELINE_RANDOM_COMPLETE
        and r["recovered"] == r["total"] == 19
    ]

    args.out.mkdir(parents=True, exist_ok=True)
    candidates[count_best["score"]].to_csv(args.out / "best_hybrid_candidates.csv", index=False)
    universe.to_csv(args.out / "hybrid_scored_universe.csv", index=False)
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "development_tuning_note": "weight grid 0.85-1.00 by 0.005 was motivated by inspected Campanula development outcomes",
        "baseline": {
            "candidate_count": BASELINE_CANDIDATES,
            "grid_fraction": BASELINE_GRID_FRACTION,
            "matched_random_complete_recovery_probability": BASELINE_RANDOM_COMPLETE,
        },
        "features": {"ndvi_state": NDVI_STATE, "microclimate": MICROCLIMATE},
        "experiments": rows,
        "pareto_frontier": frontier,
        "candidate_count_best": count_best,
        "matched_random_best": random_best,
        "promotion_candidates": promoted,
    }
    (args.out / "hybrid_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
