#!/usr/bin/env python3
"""Run the frozen ACSP low-budget confirmation for one predeclared island cell.

The cohort and execution protocol must already be frozen. Candidate sets are
constructed from each training fold before held-out coordinates are exposed to
scoring. No parameter is tuned from confirmation outcomes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.transform import rowcol, xy

from acsp.benchmarking import get_json
from acsp_training_domain_gate import infer_training_domain
from benchmark_izu_microenvironment_random_taxa import attach_public_features, make_folds
from campanula_microterrain_discovery import evaluate, terrain_surface
from campanula_ndvi_microclimate_hybrid import NDVI_STATE, fit_distance_rank
from campanula_ndvi_transition_discovery import ndvi_surfaces
from develop_izu_strong_coverage_comparator import build_geometry
from fast_max_coverage import SparseCoverageIndex

GBIF_SEARCH = "https://api.gbif.org/v1/occurrence/search"
EXPECTED_EXECUTION = "24a5cc0d21bcfd4fdfce5dc9b8ccbb2cd8dc1fc717928d8ed6775c79ef8591e1"
EXPECTED_COHORT_SHA256 = "0bf03cdbf338f57de129a904b29beef91bfa8dd60a31af13c44f94f596ab4843"
EXPECTED_METHOD = "1bff5eb8571928e9b26c193bc7bc0756f239b30def062ab49e0b94ed0c3029f0"


def canonical_fingerprint(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated:
        raise ValueError(f"protocol fingerprint mismatch: {path}")
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rectangle_wkt(bounds) -> str:
    west, south, east, north = map(float, bounds)
    return f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"


def fetch_occurrences(species_key: int, bounds, cap: int, island: str) -> pd.DataFrame:
    rows: list[dict] = []
    offset = 0
    while len(rows) < int(cap):
        limit = min(300, int(cap) - len(rows))
        payload = get_json(
            GBIF_SEARCH,
            {
                "taxonKey": int(species_key),
                "geometry": rectangle_wkt(bounds),
                "hasCoordinate": "true",
                "hasGeospatialIssue": "false",
                "occurrenceStatus": "PRESENT",
                "limit": limit,
                "offset": offset,
            },
            timeout=60,
            attempts=8,
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
                lat = float(lat); lon = float(lon)
            except (TypeError, ValueError):
                continue
            rows.append({"gbif_key": item.get("key"), "lat": lat, "lon": lon, "island": island})
        offset += len(batch)
        if payload.get("endOfRecords") or len(batch) < limit:
            break
    if not rows:
        return pd.DataFrame(columns=["gbif_key", "lat", "lon", "island"])
    return pd.DataFrame(rows).drop_duplicates(["lat", "lon"], keep="first").reset_index(drop=True)


def build_grid(dem_path: Path, island: str, bounds, grid_m: float) -> tuple[pd.DataFrame, dict]:
    surface = terrain_surface(dem_path)
    inverse = Transformer.from_crs(surface["crs"], "EPSG:4326", always_xy=True)
    step = max(1, int(round(float(grid_m) / float(surface["res"]))))
    rr = np.arange(0, surface["arr"].shape[0], step)
    cc = np.arange(0, surface["arr"].shape[1], step)
    rr, cc = np.meshgrid(rr, cc, indexing="ij")
    rr = rr.ravel(); cc = cc.ravel()
    usable = np.isfinite(surface["arr"][rr, cc])
    rr = rr[usable]; cc = cc[usable]
    xs, ys = xy(surface["transform"], rr, cc, offset="center")
    lon, lat = inverse.transform(np.asarray(xs), np.asarray(ys))
    west, south, east, north = map(float, bounds)
    inside = (
        (np.asarray(lon) >= west) & (np.asarray(lon) <= east)
        & (np.asarray(lat) >= south) & (np.asarray(lat) <= north)
    )
    grid = pd.DataFrame(
        {"island": island, "lat": np.asarray(lat)[inside], "lon": np.asarray(lon)[inside]}
    ).drop_duplicates(["lat", "lon"]).reset_index(drop=True)
    return grid, surface


def training_land_fraction(train: pd.DataFrame, surface: dict) -> float:
    if train.empty:
        return 0.0
    forward = Transformer.from_crs("EPSG:4326", surface["crs"], always_xy=True)
    x, y = forward.transform(train["lon"].to_numpy(float), train["lat"].to_numpy(float))
    rr, cc = rowcol(surface["transform"], x, y)
    rr = np.asarray(rr); cc = np.asarray(cc)
    ok = (
        (rr >= 0) & (cc >= 0)
        & (rr < surface["arr"].shape[0]) & (cc < surface["arr"].shape[1])
    )
    supported = np.zeros(len(train), dtype=bool)
    indices = np.flatnonzero(ok)
    supported[indices] = np.isfinite(surface["arr"][rr[indices], cc[indices]])
    return float(supported.mean())


def selected_jaccard(left: pd.DataFrame, right: pd.DataFrame) -> float:
    def keys(frame):
        return {
            (round(float(row.lat), 7), round(float(row.lon), 7))
            for _, row in frame.iterrows()
        }
    a = keys(left); b = keys(right)
    union = a | b
    return float(len(a & b) / len(union)) if union else 1.0


def score_set(selected: pd.DataFrame, held: pd.DataFrame, radius: float) -> float:
    if held.empty:
        return float("nan")
    detections = held.rename(columns={"lat": "latitude", "lon": "longitude"})
    return float(evaluate(selected, detections, radius)["recovered"] / len(held))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-protocol", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--island", required=True)
    parser.add_argument("--dem", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--layer-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol, fingerprint = canonical_fingerprint(args.execution_protocol)
    if fingerprint != EXPECTED_EXECUTION:
        raise ValueError(f"unexpected execution protocol {fingerprint}")
    if protocol["method_freeze"]["fingerprint"] != EXPECTED_METHOD:
        raise ValueError("method freeze fingerprint mismatch")
    if sha256_file(args.cohort) != EXPECTED_COHORT_SHA256:
        raise ValueError("predeclared cohort checksum mismatch")

    layer_manifest = json.loads(args.layer_manifest.read_text())
    if layer_manifest["execution_protocol_fingerprint"] != fingerprint:
        raise ValueError("public-layer execution fingerprint mismatch")
    if layer_manifest["selected_taxon_occurrences_read"] is not False:
        raise ValueError("public-layer boundary was violated")

    cohort = pd.read_csv(args.cohort)
    pairs = cohort[cohort["island_id"].astype(str).eq(args.island)].copy()
    if len(pairs) != 2:
        raise RuntimeError(f"expected exactly two pairs for {args.island}; found {len(pairs)}")
    bounds = tuple(float(pairs.iloc[0][key]) for key in ("west", "south", "east", "north"))
    if not all(np.allclose(pairs[key].to_numpy(float), bounds[i]) for i, key in enumerate(("west", "south", "east", "north"))):
        raise RuntimeError("pair bounds disagree within island cell")

    grid, dem_surface = build_grid(
        args.dem,
        args.island,
        bounds,
        float(protocol["public_layers"]["candidate_grid_m"]),
    )
    budget = int(protocol["selection"]["budget"])
    radius = float(protocol["selection"]["survey_radius_km"])
    if len(grid) < budget:
        raise RuntimeError(f"candidate land grid has only {len(grid)} cells")
    geometry = build_geometry(grid)
    sparse = SparseCoverageIndex.from_geometry(grid, geometry, radius)
    global_selected = sparse.select(grid, np.ones(len(grid), dtype=bool), max_budget=budget)
    if len(global_selected) != budget:
        raise RuntimeError("global max-coverage control could not fill K=5")

    fold_rows: list[dict] = []
    pair_rows: list[dict] = []
    infrastructure_failures: list[dict] = []
    sensitivity = [float(x) for x in protocol["practicality_and_robustness"]["non_gating_recovery_radius_sensitivity_km"]]
    radii = sorted(set(sensitivity + [radius]))

    with rasterio.open(args.ndvi) as src:
        ndvi_transform, ndvi_crs, ndvi_surface_dict = ndvi_surfaces(src, grid["lon"], grid["lat"])
        grid_features = attach_public_features(
            grid,
            ndvi_transform=ndvi_transform,
            ndvi_crs=ndvi_crs,
            ndvi_surface_dict=ndvi_surface_dict,
            micro_surfaces={},
            dem_map={},
        )

        for _, pair in pairs.sort_values("pair_id").iterrows():
            pair_id = int(pair["pair_id"])
            name = str(pair["scientific_name"])
            base = {
                "pair_id": pair_id,
                "island_id": args.island,
                "scientific_name": name,
                "record_count_stratum": int(pair["record_count_stratum"]),
            }
            try:
                occurrences = fetch_occurrences(
                    int(pair["speciesKey"]),
                    bounds,
                    int(protocol["occurrences"]["max_records_per_pair"]),
                    args.island,
                )
                thinned, folds = make_folds(
                    occurrences,
                    block_degrees=float(protocol["spatial_validation"]["block_degrees"]),
                    repeats=int(protocol["spatial_validation"]["repeats"]),
                    holdout_fraction=float(protocol["spatial_validation"]["holdout_fraction"]),
                    min_train=int(protocol["spatial_validation"]["minimum_training_prototypes"]),
                    seed=int(protocol["spatial_validation"]["seed_base"]) + pair_id * 100,
                )
                pair_base = {
                    **base,
                    "raw_unique_occurrences": int(len(occurrences)),
                    "thinned_occurrences": int(len(thinned)),
                    "valid_folds": int(len(folds)),
                }
                if len(folds) != int(protocol["spatial_validation"]["repeats"]):
                    pair_rows.append({**pair_base, "status": "information_inapplicable", "reason": f"only_{len(folds)}_valid_folds"})
                    continue

                domain_decisions = []
                for repeat_index, fold in enumerate(folds, start=1):
                    land_fraction = training_land_fraction(fold["train"], dem_surface)
                    decision = infer_training_domain(
                        {"kingdom": "Plantae", "phylum": pair["phylum"], "class": pair["class"]},
                        training_land_fraction=land_fraction,
                    )
                    domain_decisions.append((repeat_index, land_fraction, decision))
                if not all(item[2].terrestrial_policy_applicable for item in domain_decisions):
                    pair_rows.append({
                        **pair_base,
                        "status": "domain_inapplicable",
                        "reason": "; ".join(
                            f"fold{rep}:{decision.domain}:{land:.3f}"
                            for rep, land, decision in domain_decisions
                            if not decision.terrestrial_policy_applicable
                        ),
                    })
                    continue

                pair_fold_rows = []
                for repeat_index, fold in enumerate(folds, start=1):
                    land_fraction = domain_decisions[repeat_index - 1][1]
                    train_features = attach_public_features(
                        fold["train"],
                        ndvi_transform=ndvi_transform,
                        ndvi_crs=ndvi_crs,
                        ndvi_surface_dict=ndvi_surface_dict,
                        micro_surfaces={},
                        dem_map={},
                    )
                    _, support_rank = fit_distance_rank(grid_features, train_features, NDVI_STATE)
                    eligible = support_rank <= 0.10 + 1e-12
                    start = time.perf_counter()
                    support_selected = sparse.select(grid, eligible, max_budget=budget)
                    selection_seconds = float(time.perf_counter() - start)
                    method_failed = len(support_selected) != budget

                    # Candidate sets are now frozen. Held-out coordinates are
                    # accessed only below this point for scoring.
                    held = fold["held"]
                    row = {
                        **base,
                        "repeat": repeat_index,
                        "status": "method_failure" if method_failed else "ok",
                        "training_land_fraction": land_fraction,
                        "training_points": int(len(fold["train"])),
                        "heldout_points": int(len(held)),
                        "candidate_grid_cells": int(len(grid)),
                        "support_eligible_cells": int(eligible.sum()),
                        "support_eligible_grid_fraction": float(eligible.mean()),
                        "support_selected_sites": int(len(support_selected)),
                        "control_selected_sites": int(len(global_selected)),
                        "selected_set_jaccard": selected_jaccard(support_selected, global_selected),
                        "support_selection_runtime_seconds": selection_seconds,
                    }
                    for evaluation_radius in radii:
                        suffix = str(evaluation_radius).replace(".", "p")
                        row[f"support_recall_r{suffix}"] = 0.0 if method_failed else score_set(support_selected, held, evaluation_radius)
                        row[f"control_recall_r{suffix}"] = score_set(global_selected, held, evaluation_radius)
                    pair_fold_rows.append(row)
                    fold_rows.append(row)

                primary_suffix = str(radius).replace(".", "p")
                pair_frame = pd.DataFrame(pair_fold_rows)
                pair_rows.append({
                    **pair_base,
                    "status": "ok",
                    "method_failure_folds": int(pair_frame["status"].eq("method_failure").sum()),
                    "mean_support_recall": float(pair_frame[f"support_recall_r{primary_suffix}"].mean()),
                    "mean_control_recall": float(pair_frame[f"control_recall_r{primary_suffix}"].mean()),
                    "mean_lift": float((pair_frame[f"support_recall_r{primary_suffix}"] - pair_frame[f"control_recall_r{primary_suffix}"]).mean()),
                    "mean_support_eligible_grid_fraction": float(pair_frame["support_eligible_grid_fraction"].mean()),
                    "mean_selected_set_jaccard": float(pair_frame["selected_set_jaccard"].mean()),
                    "mean_support_selection_runtime_seconds": float(pair_frame["support_selection_runtime_seconds"].mean()),
                    **{
                        f"mean_support_recall_r{str(r).replace('.', 'p')}": float(pair_frame[f"support_recall_r{str(r).replace('.', 'p')}"] .mean())
                        for r in sensitivity
                    },
                    **{
                        f"mean_control_recall_r{str(r).replace('.', 'p')}": float(pair_frame[f"control_recall_r{str(r).replace('.', 'p')}"] .mean())
                        for r in sensitivity
                    },
                })
            except Exception as exc:
                infrastructure_failures.append({**base, "reason": f"{type(exc).__name__}: {exc}"})
                pair_rows.append({**base, "status": "infrastructure_failure", "reason": f"{type(exc).__name__}: {exc}"})

    fold_frame = pd.DataFrame(fold_rows)
    pair_frame = pd.DataFrame(pair_rows)
    args.out.mkdir(parents=True, exist_ok=True)
    fold_frame.to_csv(args.out / "fold_results.csv", index=False)
    pair_frame.to_csv(args.out / "pair_results.csv", index=False)
    summary = {
        "status": "confirmation_partial_island_result",
        "island_id": args.island,
        "execution_protocol_fingerprint": fingerprint,
        "method_freeze_fingerprint": EXPECTED_METHOD,
        "cohort_sha256": EXPECTED_COHORT_SHA256,
        "declared_pairs": 2,
        "eligible_pairs": int(pair_frame.get("status", pd.Series(dtype=str)).eq("ok").sum()),
        "domain_inapplicable_pairs": int(pair_frame.get("status", pd.Series(dtype=str)).eq("domain_inapplicable").sum()),
        "information_inapplicable_pairs": int(pair_frame.get("status", pd.Series(dtype=str)).eq("information_inapplicable").sum()),
        "infrastructure_failures": infrastructure_failures,
        "candidate_grid_cells": int(len(grid)),
        "public_layer_manifest": layer_manifest,
        "outer_heldout_coordinates_used_during_selection": False,
        "retuning_performed": False,
        "frozen_192_consumed": False,
    }
    (args.out / "island_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
