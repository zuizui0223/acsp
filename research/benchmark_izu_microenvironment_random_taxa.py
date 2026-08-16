#!/usr/bin/env python3
"""Evaluate the frozen Campanula-derived microenvironment rule on unseen Izu plant taxa.

The taxon identities must be predeclared before this script is run. For each
taxon/repeat, held-out occurrence coordinates are invisible until the candidate
scores and fixed-budget selections have been created from training occurrences.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd
import rasterio
import requests
from pyproj import Transformer
from rasterio.transform import xy

from campanula_microterrain_discovery import (
    assign_island,
    haversine_km,
    terrain_surface,
    thin_500m,
)
from campanula_ndvi_transition_discovery import ndvi_surfaces, sample_surfaces
from campanula_ndvi_microclimate_hybrid import (
    JOINT_STATE,
    NDVI_STATE,
    evaluate,
    fast_matched_random_success,
    fit_distance_rank,
    sample_microclimate,
    terrain_microclimate_surface,
)

GBIF_SEARCH = "https://api.gbif.org/v1/occurrence/search"


def polygon(bounds):
    w, s, e, n = bounds
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


ISLAND_BOUNDS = {
    "oshima": (139.30, 34.64, 139.47, 34.82),
    "toshima": (139.24, 34.49, 139.31, 34.55),
    "niijima": (139.20, 34.33, 139.31, 34.44),
    "shikinejima": (139.18, 34.30, 139.24, 34.35),
    "kozushima": (139.09, 34.17, 139.18, 34.26),
}


def island_wkt() -> str:
    parts = []
    for bounds in ISLAND_BOUNDS.values():
        coordinates = ",".join(f"{lon} {lat}" for lon, lat in polygon(bounds))
        parts.append(f"(({coordinates}))")
    return f"MULTIPOLYGON({','.join(parts)})"


def get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 60, attempts: int = 4):
    last = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * 2**attempt)
    raise RuntimeError(f"GBIF request failed: {last}")


def fetch_occurrences(species_key: int, cap: int) -> pd.DataFrame:
    rows = []
    offset = 0
    while len(rows) < cap:
        limit = min(300, cap - len(rows))
        payload = get_json(
            GBIF_SEARCH,
            {
                "taxonKey": int(species_key),
                "geometry": island_wkt(),
                "hasCoordinate": "true",
                "hasGeospatialIssue": "false",
                "occurrenceStatus": "PRESENT",
                "limit": limit,
                "offset": offset,
            },
        )
        batch = payload.get("results", [])
        if not batch:
            break
        for item in batch:
            lat = item.get("decimalLatitude")
            lon = item.get("decimalLongitude")
            if lat is None or lon is None:
                continue
            try:
                lat = float(lat)
                lon = float(lon)
            except (TypeError, ValueError):
                continue
            island = assign_island(lat, lon)
            if island is None:
                continue
            rows.append(
                {
                    "gbif_key": item.get("key"),
                    "lat": lat,
                    "lon": lon,
                    "island": island,
                }
            )
        offset += len(batch)
        if payload.get("endOfRecords") or len(batch) < limit:
            break
    if not rows:
        return pd.DataFrame(columns=["gbif_key", "lat", "lon", "island"])
    frame = pd.DataFrame(rows)
    return frame.drop_duplicates(["lat", "lon"], keep="first").reset_index(drop=True)


def build_public_grid(dem_map: dict[str, Path], grid_m: float = 100.0) -> pd.DataFrame:
    rows = []
    surfaces = {}
    inverse = {}
    for island, path in dem_map.items():
        key = str(path)
        if key not in surfaces:
            surfaces[key] = terrain_surface(path)
        surface = surfaces[key]
        inverse.setdefault(
            key, Transformer.from_crs(surface["crs"], "EPSG:4326", always_xy=True)
        )
        step = max(1, int(round(grid_m / surface["res"])))
        rr = np.arange(0, surface["arr"].shape[0], step)
        cc = np.arange(0, surface["arr"].shape[1], step)
        rr, cc = np.meshgrid(rr, cc, indexing="ij")
        rr = rr.ravel()
        cc = cc.ravel()
        usable = np.isfinite(surface["arr"][rr, cc])
        rr = rr[usable]
        cc = cc[usable]
        xs, ys = xy(surface["transform"], rr, cc, offset="center")
        lon, lat = inverse[key].transform(np.asarray(xs), np.asarray(ys))
        for y, x in zip(lat, lon):
            assigned = assign_island(float(y), float(x))
            if assigned == island:
                rows.append((island, float(y), float(x)))
    return pd.DataFrame(rows, columns=["island", "lat", "lon"]).drop_duplicates(
        ["island", "lat", "lon"]
    ).reset_index(drop=True)


def attach_public_features(
    frame: pd.DataFrame,
    *,
    ndvi_transform,
    ndvi_crs,
    ndvi_surface_dict,
    micro_surfaces: dict[str, dict],
    dem_map: dict[str, Path],
) -> pd.DataFrame:
    out = frame.copy().reset_index(drop=True)
    ndvi = sample_surfaces(
        ndvi_transform, ndvi_crs, ndvi_surface_dict, out["lon"], out["lat"]
    )
    micro = sample_microclimate(out, micro_surfaces, dem_map)
    return pd.concat([out, ndvi.reset_index(drop=True), micro.reset_index(drop=True)], axis=1)


def make_folds(
    occurrences: pd.DataFrame,
    *,
    block_degrees: float,
    repeats: int,
    holdout_fraction: float,
    min_train: int,
    seed: int,
):
    work = thin_500m(occurrences).reset_index(drop=True)
    if len(work) < min_train + 1:
        return work, []
    work["block"] = (
        np.floor(work["lat"] / block_degrees).astype(int).astype(str)
        + ":"
        + np.floor(work["lon"] / block_degrees).astype(int).astype(str)
    )
    blocks = work["block"].drop_duplicates().to_numpy()
    if len(blocks) < 3:
        return work, []
    holdout_n = min(
        len(blocks) - 1,
        max(1, int(round(len(blocks) * holdout_fraction))),
    )
    rng = np.random.default_rng(seed)
    folds = []
    attempts = 0
    while len(folds) < repeats and attempts < repeats * 40:
        attempts += 1
        held_blocks = set(rng.choice(blocks, size=holdout_n, replace=False).tolist())
        held = work[work["block"].isin(held_blocks)].drop(columns="block").reset_index(drop=True)
        train = work[~work["block"].isin(held_blocks)].drop(columns="block").reset_index(drop=True)
        if len(train) < min_train or held.empty:
            continue
        signature = tuple(sorted(held_blocks))
        if any(item["signature"] == signature for item in folds):
            continue
        folds.append({"train": train, "held": held, "signature": signature})
    return work.drop(columns="block"), folds


def nearest_training_distance_km(train: pd.DataFrame, held: pd.DataFrame) -> np.ndarray:
    result = np.full(len(held), np.inf)
    for i, row in held.iterrows():
        subset = train[train["island"].eq(row["island"])]
        if subset.empty:
            continue
        result[i] = float(
            np.min(
                haversine_km(
                    float(row["lat"]),
                    float(row["lon"]),
                    subset["lat"].to_numpy(),
                    subset["lon"].to_numpy(),
                )
            )
        )
    return result


def recall(selected: pd.DataFrame, held: pd.DataFrame, radius_km: float) -> float:
    if held.empty:
        return np.nan
    detections = held.rename(columns={"lat": "latitude", "lon": "longitude"})
    return evaluate(selected, detections, radius_km)["recovered"] / len(held)


def bootstrap_mean_ci(values: np.ndarray, draws: int, seed: int):
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    for i in range(draws):
        means[i] = float(np.mean(rng.choice(values, size=len(values), replace=True)))
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def sign_flip_p(values: np.ndarray, draws: int, seed: int) -> float:
    values = np.asarray(values, dtype=float)
    observed = float(np.mean(values))
    if observed <= 0:
        return 1.0
    rng = np.random.default_rng(seed)
    extreme = 0
    for _ in range(draws):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(values), replace=True)
        extreme += int(float(np.mean(values * signs)) >= observed)
    return float((extreme + 1) / (draws + 1))


def summarize_taxa(taxa: pd.DataFrame, protocol: dict, seed: int):
    evaluable = taxa[taxa["status"].eq("ok")].copy()
    out = {
        "declared_taxa": int(len(taxa)),
        "evaluable_taxa": int(len(evaluable)),
        "minimum_evaluable_taxa": int(protocol["inference"]["minimum_evaluable_taxa"]),
    }
    if len(evaluable) < protocol["inference"]["minimum_evaluable_taxa"]:
        out["primary_gate"] = False
        out["microclimate_gate"] = False
        out["reason"] = "insufficient_evaluable_taxa"
        return out
    primary = (evaluable["hybrid_recall"] - evaluable["random_recall"]).to_numpy(float)
    increment = (evaluable["hybrid_recall"] - evaluable["ndvi_recall"]).to_numpy(float)
    boot = int(protocol["inference"]["bootstrap_draws"])
    flips = int(protocol["inference"]["sign_flip_draws"])
    out.update(
        {
            "mean_hybrid_recall": float(evaluable["hybrid_recall"].mean()),
            "mean_ndvi_recall": float(evaluable["ndvi_recall"].mean()),
            "mean_random_recall": float(evaluable["random_recall"].mean()),
            "hybrid_minus_random": float(np.mean(primary)),
            "hybrid_minus_random_bootstrap_95ci": bootstrap_mean_ci(primary, boot, seed),
            "hybrid_minus_random_sign_flip_p": sign_flip_p(primary, flips, seed + 1),
            "hybrid_minus_ndvi": float(np.mean(increment)),
            "hybrid_minus_ndvi_bootstrap_95ci": bootstrap_mean_ci(increment, boot, seed + 2),
            "hybrid_minus_ndvi_sign_flip_p": sign_flip_p(increment, flips, seed + 3),
        }
    )
    out["primary_gate"] = bool(
        out["hybrid_minus_random"] > 0
        and out["hybrid_minus_random_bootstrap_95ci"][0] > 0
        and out["hybrid_minus_random_sign_flip_p"] < 0.05
    )
    out["microclimate_gate"] = bool(
        out["hybrid_minus_ndvi_bootstrap_95ci"][0] > 0
        and out["hybrid_minus_ndvi_sign_flip_p"] < 0.05
    )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--dem", action="append", required=True, help="ISLAND=path.tif")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text())
    sample = pd.read_csv(args.sample)
    if len(sample) != protocol["sampling"]["taxa"]:
        raise RuntimeError("predeclared taxon count does not match protocol")

    dem_map = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    grid = build_public_grid(dem_map)
    if len(grid) < protocol["selection"]["candidate_count"]:
        raise RuntimeError("public grid is smaller than the frozen candidate budget")

    micro_surfaces = {}
    for path in sorted(set(dem_map.values()), key=str):
        micro_surfaces[str(path)] = terrain_microclimate_surface(path)

    with rasterio.open(args.ndvi) as src:
        ndvi_transform, ndvi_crs, ndvi_surface_dict = ndvi_surfaces(
            src, grid["lon"], grid["lat"]
        )
        grid = attach_public_features(
            grid,
            ndvi_transform=ndvi_transform,
            ndvi_crs=ndvi_crs,
            ndvi_surface_dict=ndvi_surface_dict,
            micro_surfaces=micro_surfaces,
            dem_map=dem_map,
        )

        args.out.mkdir(parents=True, exist_ok=True)
        fold_rows = []
        taxon_rows = []
        for taxon_index, taxon in sample.iterrows():
            name = str(taxon["scientific_name"])
            status = {"sample_id": int(taxon["sample_id"]), "scientific_name": name}
            try:
                occurrences = fetch_occurrences(
                    int(taxon["speciesKey"]),
                    int(protocol["occurrences"]["max_records_per_taxon"]),
                )
                thinned, folds = make_folds(
                    occurrences,
                    block_degrees=float(protocol["validation"]["block_degrees"]),
                    repeats=int(protocol["validation"]["repeats"]),
                    holdout_fraction=float(protocol["validation"]["holdout_fraction"]),
                    min_train=int(protocol["validation"]["minimum_training_prototypes"]),
                    seed=int(protocol["sampling"]["seed"]) + int(taxon_index) * 100,
                )
                status["raw_unique_occurrences"] = int(len(occurrences))
                status["thinned_occurrences"] = int(len(thinned))
                if len(folds) != int(protocol["validation"]["repeats"]):
                    status["status"] = "failed"
                    status["reason"] = f"only_{len(folds)}_valid_folds"
                    taxon_rows.append(status)
                    continue

                taxon_fold_rows = []
                for repeat_index, fold in enumerate(folds, start=1):
                    train = attach_public_features(
                        fold["train"],
                        ndvi_transform=ndvi_transform,
                        ndvi_crs=ndvi_crs,
                        ndvi_surface_dict=ndvi_surface_dict,
                        micro_surfaces=micro_surfaces,
                        dem_map=dem_map,
                    )
                    # Freeze both candidate selections before opening held-out coordinates.
                    ndvi_distance, ndvi_rank = fit_distance_rank(grid, train, NDVI_STATE)
                    joint_distance, joint_rank = fit_distance_rank(grid, train, JOINT_STATE)
                    hybrid_score = 0.90 * ndvi_rank + 0.10 * joint_rank
                    budget = int(protocol["selection"]["candidate_count"])
                    hybrid_order = np.argsort(hybrid_score, kind="mergesort")[:budget]
                    ndvi_order = np.argsort(ndvi_rank, kind="mergesort")[:budget]
                    hybrid = grid.iloc[hybrid_order].copy()
                    ndvi_only = grid.iloc[ndvi_order].copy()

                    # Outcome stage starts here. No selected ID or score can change below.
                    held = fold["held"].copy()
                    held_eval = held.rename(columns={"lat": "latitude", "lon": "longitude"})
                    hybrid_result = evaluate(
                        hybrid, held_eval, float(protocol["validation"]["recovery_radius_km"])
                    )
                    ndvi_result = evaluate(
                        ndvi_only, held_eval, float(protocol["validation"]["recovery_radius_km"])
                    )
                    random = fast_matched_random_success(
                        grid,
                        held_eval,
                        hybrid,
                        float(protocol["validation"]["recovery_radius_km"]),
                        int(protocol["comparators"]["matched_random_draws_per_fold"]),
                        int(protocol["sampling"]["seed"]) + int(taxon_index) * 1000 + repeat_index,
                    )
                    nearest_train = nearest_training_distance_km(fold["train"], held)
                    row = {
                        "sample_id": int(taxon["sample_id"]),
                        "scientific_name": name,
                        "repeat": repeat_index,
                        "training_points": int(len(fold["train"])),
                        "heldout_points": int(len(held)),
                        "hybrid_recall": hybrid_result["recovered"] / len(held),
                        "ndvi_recall": ndvi_result["recovered"] / len(held),
                        "random_recall": float(random["mean_recovered"]) / len(held),
                        "hybrid_selected_by_island": json.dumps(
                            {str(k): int(v) for k, v in hybrid.groupby("island").size().items()},
                            sort_keys=True,
                        ),
                    }
                    for threshold in (1.0, 2.0):
                        mask = nearest_train >= threshold
                        subset = held.loc[mask]
                        key = f"novel_{int(threshold)}km"
                        row[f"{key}_n"] = int(mask.sum())
                        row[f"{key}_hybrid_recall"] = recall(
                            hybrid, subset, float(protocol["validation"]["recovery_radius_km"])
                        )
                        row[f"{key}_ndvi_recall"] = recall(
                            ndvi_only, subset, float(protocol["validation"]["recovery_radius_km"])
                        )
                    fold_rows.append(row)
                    taxon_fold_rows.append(row)

                tf = pd.DataFrame(taxon_fold_rows)
                status.update(
                    {
                        "status": "ok",
                        "valid_repeats": int(len(tf)),
                        "hybrid_recall": float(tf["hybrid_recall"].mean()),
                        "ndvi_recall": float(tf["ndvi_recall"].mean()),
                        "random_recall": float(tf["random_recall"].mean()),
                    }
                )
                for threshold in (1, 2):
                    col = f"novel_{threshold}km_hybrid_recall"
                    status[col] = float(tf[col].mean(skipna=True)) if tf[col].notna().any() else np.nan
            except Exception as exc:
                status["status"] = "failed"
                status["reason"] = f"{type(exc).__name__}: {exc}"
            taxon_rows.append(status)
            pd.DataFrame(fold_rows).to_csv(args.out / "fold_results.csv", index=False)
            pd.DataFrame(taxon_rows).to_csv(args.out / "taxon_results.csv", index=False)

    taxa = pd.DataFrame(taxon_rows)
    summary = summarize_taxa(taxa, protocol, int(protocol["sampling"]["seed"]))
    summary.update(
        {
            "protocol_id": protocol["protocol_id"],
            "protocol_fingerprint": protocol["fingerprint"],
            "development_fingerprint": protocol["development_fingerprint"],
            "frozen_formula": protocol["selection"]["hybrid_formula"],
            "frozen_candidate_count": int(protocol["selection"]["candidate_count"]),
            "taxa_replaced_after_declaration": False,
            "campanula_used_in_validation": False,
            "practical_core_untouched_192_consumed": False,
        }
    )
    (args.out / "validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
