#!/usr/bin/env python3
"""Development-only Campanula microenvironment discovery with ESA WorldCover.

The generator uses only pre-2026 GBIF occurrences, the cached GSI DEM-derived
microterrain universe, and ESA WorldCover 2021. 2026 field detections are read
only after every candidate score has been frozen, and are used only to measure
the development Pareto frontier.
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
from rasterio.windows import Window

WORLD_COVER_CLASSES = (10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100)
CLASS_NAMES = {
    10: "tree",
    20: "shrub",
    30: "grass",
    40: "crop",
    50: "built",
    60: "bare",
    70: "snow_ice",
    80: "water",
    90: "wetland",
    95: "mangrove",
    100: "moss_lichen",
}


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


def robust_fit(values):
    median = np.nanmedian(values, axis=0)
    q1 = np.nanquantile(values, 0.25, axis=0)
    q3 = np.nanquantile(values, 0.75, axis=0)
    scale = np.where((q3 - q1) > 1e-9, q3 - q1, 1.0)
    return median, scale


def transform(values, median, scale):
    return (values - median) / scale


def nearest_environment(values, prototypes, chunk=3000):
    result = np.full(len(values), np.inf)
    for start in range(0, len(values), chunk):
        block = values[start : start + chunk]
        d2 = ((block[:, None, :] - prototypes[None, :, :]) ** 2).sum(axis=2)
        result[start : start + len(block)] = np.sqrt(d2.min(axis=1))
    return result


def sample_nearest(src, lon, lat):
    transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
    x, y = transformer.transform(np.asarray(lon), np.asarray(lat))
    rows, cols = rasterio.transform.rowcol(src.transform, x, y)
    rows = np.asarray(rows)
    cols = np.asarray(cols)
    ok = (
        (rows >= 0)
        & (rows < src.height)
        & (cols >= 0)
        & (cols < src.width)
    )
    out = np.full(len(rows), np.nan)
    if not ok.any():
        return out
    for idx in np.flatnonzero(ok):
        value = next(src.sample([(x[idx], y[idx])]))[0]
        if src.nodata is None or value != src.nodata:
            out[idx] = value
    return out


def neighborhood_features(src, lon, lat, radii_m=(100, 250)):
    """Extract local class fractions, entropy, and edge mixing around coordinates."""
    transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
    x, y = transformer.transform(np.asarray(lon), np.asarray(lat))
    rows, cols = rasterio.transform.rowcol(src.transform, x, y)
    deg = abs(float(src.transform.a))
    pixel_m = deg * 111_320.0 * math.cos(math.radians(34.5))
    features = []
    names = []
    for radius in radii_m:
        for code in WORLD_COVER_CLASSES:
            names.append(f"wc_{CLASS_NAMES[code]}_frac_{radius}m")
        names.extend([f"wc_entropy_{radius}m", f"wc_edge_mix_{radius}m"])

    for row, col in zip(rows, cols):
        values = []
        for radius in radii_m:
            half = max(1, int(math.ceil(radius / max(pixel_m, 1e-6))))
            r0 = max(0, row - half)
            c0 = max(0, col - half)
            r1 = min(src.height, row + half + 1)
            c1 = min(src.width, col + half + 1)
            if r1 <= r0 or c1 <= c0:
                values.extend([np.nan] * (len(WORLD_COVER_CLASSES) + 2))
                continue
            arr = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
            sample = arr[np.isin(arr, WORLD_COVER_CLASSES)]
            if sample.size == 0:
                values.extend([np.nan] * (len(WORLD_COVER_CLASSES) + 2))
                continue
            fractions = np.array([(sample == code).mean() for code in WORLD_COVER_CLASSES])
            nz = fractions[fractions > 0]
            entropy = float(-(nz * np.log(nz)).sum() / math.log(len(WORLD_COVER_CLASSES)))
            edge_mix = float(1.0 - np.square(fractions).sum())
            values.extend(fractions.tolist() + [entropy, edge_mix])
        features.append(values)
    return pd.DataFrame(features, columns=names)


def evaluate(candidates, detections, radius_km):
    nearest = []
    for _, point in detections.iterrows():
        subset = candidates[candidates["island"].eq(point["island"])]
        if subset.empty:
            nearest.append(float("inf"))
            continue
        d = haversine_km(
            float(point["latitude"]),
            float(point["longitude"]),
            subset["lat"].to_numpy(),
            subset["lon"].to_numpy(),
        )
        nearest.append(float(np.min(d)))
    return {
        "recovered": int(sum(v <= radius_km for v in nearest)),
        "total": int(len(detections)),
        "max_nearest_km": float(max(nearest)),
        "nearest_km": nearest,
    }


def minimum_count_for_complete_recovery(universe, detections, order, radius_km):
    """Exact smallest score-prefix that reaches every detection within radius."""
    rank = np.empty(len(order), dtype=int)
    rank[order] = np.arange(len(order), dtype=int)
    required_rank = -1
    witness = []
    for _, point in detections.iterrows():
        island_mask = universe["island"].eq(point["island"]).to_numpy()
        indices = np.flatnonzero(island_mask)
        if not len(indices):
            return None, []
        d = haversine_km(
            float(point["latitude"]),
            float(point["longitude"]),
            universe.iloc[indices]["lat"].to_numpy(),
            universe.iloc[indices]["lon"].to_numpy(),
        )
        reachable = indices[d <= radius_km]
        if not len(reachable):
            return None, []
        best = int(rank[reachable].min())
        required_rank = max(required_rank, best)
        witness.append(best)
    return required_rank + 1, witness


def matched_random_success(universe, detections, selected, radius_km, iterations, seed):
    rng = np.random.default_rng(seed)
    per_island = selected.groupby("island").size().to_dict()
    groups = {name: frame.index.to_numpy() for name, frame in universe.groupby("island")}
    complete = 0
    recovery = []
    for _ in range(iterations):
        indices = []
        for island, count in per_island.items():
            pool = groups[island]
            count = min(int(count), len(pool))
            indices.extend(rng.choice(pool, size=count, replace=False).tolist())
        result = evaluate(universe.loc[indices], detections, radius_km)
        recovery.append(result["recovered"])
        complete += int(result["recovered"] == len(detections))
    return {
        "iterations": int(iterations),
        "complete_recovery_probability": float(complete / iterations),
        "mean_recovered": float(np.mean(recovery)),
        "q05_recovered": float(np.quantile(recovery, 0.05)),
        "q95_recovered": float(np.quantile(recovery, 0.95)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--worldcover", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--radius-km", type=float, default=1.0)
    parser.add_argument("--random-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)

    with rasterio.open(args.worldcover) as src:
        universe_cover = neighborhood_features(src, universe["lon"], universe["lat"])
        prototype_cover = neighborhood_features(src, prototypes["lon"], prototypes["lat"])
        universe_class = sample_nearest(src, universe["lon"], universe["lat"])
        prototype_class = sample_nearest(src, prototypes["lon"], prototypes["lat"])

    universe = pd.concat([universe.reset_index(drop=True), universe_cover], axis=1)
    prototypes = pd.concat([prototypes.reset_index(drop=True), prototype_cover], axis=1)
    universe["wc_class"] = universe_class
    prototypes["wc_class"] = prototype_class

    cover_cols = list(universe_cover.columns)
    usable_proto = prototypes[cover_cols].notna().all(axis=1)
    if usable_proto.sum() < 3:
        raise RuntimeError("Too few GBIF prototypes have usable WorldCover neighborhoods")
    median, scale = robust_fit(prototypes.loc[usable_proto, cover_cols].to_numpy(float))
    proto_cover_z = transform(prototypes.loc[usable_proto, cover_cols].to_numpy(float), median, scale)
    usable_universe = universe[cover_cols].notna().all(axis=1)
    cover_distance = np.full(len(universe), np.inf)
    cover_distance[usable_universe] = nearest_environment(
        transform(universe.loc[usable_universe, cover_cols].to_numpy(float), median, scale),
        proto_cover_z,
    )
    universe["cover_env_nn"] = cover_distance

    terrain_rank = universe["env_nn"].rank(method="average", pct=True).to_numpy(float)
    cover_rank = pd.Series(universe["cover_env_nn"]).rank(method="average", pct=True).to_numpy(float)

    # Field outcomes become visible only below this line. The score vectors above
    # are already frozen from pre-2026 occurrences and public layers.
    detections = pd.read_csv(args.detections)
    experiments = []
    best = None
    for terrain_weight in np.linspace(0.0, 1.0, 21):
        score = terrain_weight * terrain_rank + (1.0 - terrain_weight) * cover_rank
        order = np.argsort(score, kind="mergesort")
        count, witness_ranks = minimum_count_for_complete_recovery(
            universe, detections, order, args.radius_km
        )
        if count is None:
            continue
        chosen = universe.iloc[order[:count]].copy()
        result = evaluate(chosen, detections, args.radius_km)
        if result["recovered"] != len(detections):
            raise RuntimeError("exact frontier calculation failed its own recovery audit")
        random = matched_random_success(
            universe,
            detections,
            chosen,
            args.radius_km,
            args.random_iterations,
            args.seed + int(round(terrain_weight * 1000)),
        )
        row = {
            "terrain_weight": float(terrain_weight),
            "cover_weight": float(1.0 - terrain_weight),
            "candidate_count": int(len(chosen)),
            "grid_fraction": float(len(chosen) / len(universe)),
            "detection_witness_ranks": [int(value) for value in witness_ranks],
            **result,
            "matched_random": random,
        }
        experiments.append(row)
        key = (row["grid_fraction"], random["complete_recovery_probability"])
        if best is None or key < best[0]:
            best = (key, row, chosen)

    args.out.mkdir(parents=True, exist_ok=True)
    universe.to_csv(args.out / "worldcover_scored_universe.csv", index=False)
    prototypes.to_csv(args.out / "worldcover_gbif_prototypes.csv", index=False)
    if best is not None:
        best[2].to_csv(args.out / "best_worldcover_candidates.csv", index=False)
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "worldcover_source": "ESA WorldCover 2021 v200 10 m",
        "cover_features": cover_cols,
        "experiments": experiments,
        "best": None if best is None else best[1],
    }
    (args.out / "worldcover_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
