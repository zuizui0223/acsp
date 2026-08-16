#!/usr/bin/env python3
"""Isolate within-island NDVI support from between-island allocation effects."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

import benchmark_izu_microenvironment_random_taxa as bench
from campanula_ndvi_microclimate_hybrid import NDVI_STATE, evaluate, fit_distance_rank
from campanula_ndvi_transition_discovery import ndvi_surfaces
from develop_izu_strong_coverage_comparator import build_geometry, greedy_max_coverage, infer
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transfer-protocol", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--dem", action="append", required=True, help="ISLAND=path.tif")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    transfer = json.loads(args.transfer_protocol.read_text())
    sample = pd.read_csv(args.sample)
    q = 0.05
    budget = 20
    radius = 1.0
    dem_map = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    grid = bench.build_public_grid(dem_map)
    geometry = build_geometry(grid)
    # For each island, precompute a pure geographic max-coverage order. Later we
    # take exactly the number of slots allocated by the support-constrained set.
    island_orders = {}
    for island in sorted(geometry):
        mask = grid["island"].eq(island).to_numpy()
        island_orders[island] = greedy_max_coverage(
            grid, geometry, mask, budget=budget, radius_km=radius
        )

    rows = []
    failures = []
    with rasterio.open(args.ndvi) as src:
        tr, crs, surfaces = ndvi_surfaces(src, grid["lon"], grid["lat"])
        ndvi_grid = bench.attach_public_features(
            grid,
            ndvi_transform=tr,
            ndvi_crs=crs,
            ndvi_surface_dict=surfaces,
            micro_surfaces={},
            dem_map={},
        )
        for taxon_index, taxon in sample.iterrows():
            name = str(taxon["scientific_name"])
            try:
                occurrences = bench.fetch_occurrences(
                    int(taxon["speciesKey"]),
                    int(transfer["occurrences"]["max_records_per_taxon"]),
                )
                _, folds = bench.make_folds(
                    occurrences,
                    block_degrees=0.03,
                    repeats=5,
                    holdout_fraction=0.2,
                    min_train=int(transfer["validation"]["minimum_training_prototypes"]),
                    seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 100,
                )
                if len(folds) != 5:
                    failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"only_{len(folds)}_folds"})
                    continue
                for repeat_index, fold in enumerate(folds, start=1):
                    train = bench.attach_public_features(
                        fold["train"],
                        ndvi_transform=tr,
                        ndvi_crs=crs,
                        ndvi_surface_dict=surfaces,
                        micro_surfaces={},
                        dem_map={},
                    )
                    _, support_rank = fit_distance_rank(ndvi_grid, train, NDVI_STATE)
                    support = greedy_max_coverage(
                        grid,
                        geometry,
                        support_rank <= q + 1e-12,
                        budget=budget,
                        radius_km=radius,
                    )
                    parts = []
                    allocation = support.groupby("island").size().to_dict()
                    for island, count in allocation.items():
                        parts.append(island_orders[str(island)].iloc[: int(count)].copy())
                    matched = pd.concat(parts, ignore_index=True) if parts else grid.iloc[0:0].copy()

                    held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
                    support_recall = evaluate(support, held, radius)["recovered"] / len(held)
                    matched_recall = evaluate(matched, held, radius)["recovered"] / len(held)
                    rows.append(
                        {
                            "sample_id": int(taxon["sample_id"]),
                            "scientific_name": name,
                            "repeat": repeat_index,
                            "support_recall": support_recall,
                            "allocation_matched_coverage_recall": matched_recall,
                            "island_allocation": json.dumps({str(k): int(v) for k, v in allocation.items()}, sort_keys=True),
                        }
                    )
            except Exception as exc:
                failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"{type(exc).__name__}: {exc}"})

    fold = pd.DataFrame(rows)
    if fold.empty:
        raise RuntimeError("No allocation-matched folds completed")
    taxon = (
        fold.groupby(["sample_id", "scientific_name"], as_index=False)
        .agg(
            support_recall=("support_recall", "mean"),
            allocation_matched_coverage_recall=("allocation_matched_coverage_recall", "mean"),
            folds=("repeat", "count"),
        )
    )
    comparison = infer(taxon, "support_recall", "allocation_matched_coverage_recall", 20260820)
    summary = {
        "status": "development_only",
        "support_quantile": q,
        "budget": budget,
        "radius_km": radius,
        "taxa": int(len(taxon)),
        "failures": failures,
        "mean_support_recall": float(taxon["support_recall"].mean()),
        "mean_allocation_matched_coverage_recall": float(taxon["allocation_matched_coverage_recall"].mean()),
        "support_vs_allocation_matched_coverage": comparison,
        "within_island_environment_value": bool(comparison["passes"]),
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    fold.to_csv(args.out / "allocation_matched_fold_results.csv", index=False)
    taxon.to_csv(args.out / "allocation_matched_taxon_results.csv", index=False)
    (args.out / "allocation_matched_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
