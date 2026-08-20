#!/usr/bin/env python3
"""Evaluate generic robust support on a dense, training-only environmental surface.

This is a development-only bridge for already-inspected historical cohorts. The
predeclared taxon-region bounds are fixed before spatial holdout outcomes are
opened. Each predeclared region receives one deterministic land-point surface
shared by all folds in that region. Training prototypes vary by fold; the
candidate universe does not. Held-out coordinates are opened only for recovery
measurement.

The script intentionally does not use the compressed ``potential_candidates``
pool: that object is designed for Top-k field decisions and is too sparse to be
the universe of a percentile support envelope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.field_validation import detection_recovery_table, recovery_summary
from acsp.robust_patches import leave_one_out_consensus_support, support_cells_to_patches
from gbif_fieldmap_builder_app import extract_environment, generate_land_points, spatial_thin

RAW_FEATURES = ("elevation", "slope", "aspect", "roughness", "tpi")
ROBUST_FEATURES = ("elevation", "slope", "aspect_sin", "aspect_cos", "roughness", "tpi")
DEFAULT_TIERS = (0.025, 0.05, 0.10, 0.20)
DEFAULT_RADII_KM = (1.0, 2.0, 5.0, 10.0)
MAX_PROTOTYPES = 32
_SURFACE_CACHE: dict[tuple[tuple[float, float, float, float], int, int], pd.DataFrame] = {}


def _csv_floats(value: str) -> tuple[float, ...]:
    values = tuple(sorted(set(float(item.strip()) for item in value.split(",") if item.strip())))
    if not values:
        raise argparse.ArgumentTypeError("expected comma-separated numeric values")
    return values


def _with_robust_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in RAW_FEATURES:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    radians = np.radians(out["aspect"].to_numpy(float))
    out["aspect_sin"] = np.sin(radians)
    out["aspect_cos"] = np.cos(radians)
    return out


def _bounds_from_manifest(path: Path) -> tuple[float, float, float, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    provenance = payload.get("provenance") or {}
    values = tuple(float(provenance[key]) for key in ("west", "south", "east", "north"))
    west, south, east, north = values
    if not (west < east and south < north):
        raise ValueError("invalid predeclared region bounds in fold provenance")
    return values


def _stable_surface_seed(bounds: tuple[float, float, float, float], base_seed: int) -> int:
    token = ",".join(f"{value:.6f}" for value in bounds)
    offset = int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:8], 16)
    return int((int(base_seed) + offset) % (2**31 - 1))


def _dense_land_surface(
    bounds: tuple[float, float, float, float],
    *,
    n_points: int,
    seed: int,
) -> pd.DataFrame:
    key = (tuple(float(value) for value in bounds), int(n_points), int(seed))
    if key in _SURFACE_CACHE:
        return _SURFACE_CACHE[key].copy()
    west, south, east, north = bounds
    corners = pd.DataFrame(
        {
            "_latitude": [south, south, north, north],
            "_longitude": [west, east, west, east],
        }
    )
    surface = generate_land_points(
        corners,
        int(n_points),
        "bounding box",
        0.0,
        0.0,
        random_state=int(seed),
    )
    if len(surface) < max(20, int(n_points * 0.5)):
        raise ValueError(f"dense land surface produced only {len(surface)} usable points")
    surface = extract_environment(
        surface,
        list(RAW_FEATURES),
        "latitude",
        "longitude",
        "2.5m",
    )
    surface = _with_robust_features(surface)
    surface = surface.loc[surface[list(ROBUST_FEATURES)].notna().all(axis=1)].copy().reset_index(drop=True)
    surface["survey_area_id"] = "region"
    _SURFACE_CACHE[key] = surface.copy()
    return surface


def _prototype_coordinates(training: pd.DataFrame) -> pd.DataFrame:
    work = training.copy()
    work["_latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["_longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    work = work.dropna(subset=["_latitude", "_longitude"]).reset_index(drop=True)
    if len(work) < 5:
        raise ValueError("fewer than five training coordinates")
    chosen = work
    for thinning_m in (5_000.0, 10_000.0, 20_000.0, 40_000.0, 80_000.0):
        candidate = spatial_thin(work, thinning_m)
        if len(candidate) >= 5:
            chosen = candidate
        if 5 <= len(candidate) <= MAX_PROTOTYPES:
            chosen = candidate
            break
    if len(chosen) > MAX_PROTOTYPES:
        chosen = chosen.iloc[:MAX_PROTOTYPES].copy()
    return chosen[["_latitude", "_longitude"]].rename(
        columns={"_latitude": "latitude", "_longitude": "longitude"}
    ).reset_index(drop=True)


def _training_prototypes(training: pd.DataFrame) -> pd.DataFrame:
    points = _prototype_coordinates(training)
    enriched = extract_environment(
        points,
        list(RAW_FEATURES),
        "latitude",
        "longitude",
        "2.5m",
    )
    enriched = _with_robust_features(enriched)
    enriched = enriched.loc[enriched[list(ROBUST_FEATURES)].notna().all(axis=1)].copy().reset_index(drop=True)
    enriched = enriched.drop_duplicates(list(ROBUST_FEATURES)).reset_index(drop=True)
    if len(enriched) < 5:
        raise ValueError("fewer than five unique complete training environment prototypes")
    return enriched


def _evaluate_fold(
    fold_dir: Path,
    *,
    tiers: tuple[float, ...],
    radii_km: tuple[float, ...],
    surface_points: int,
    random_draws: int,
    surface_seed_base: int,
    random_seed: int,
) -> list[dict[str, object]]:
    training = pd.read_csv(fold_dir / "training_occurrences.csv")
    heldout = pd.read_csv(fold_dir / "held_out_occurrences.csv")
    if training.empty or heldout.empty:
        return []
    bounds = _bounds_from_manifest(fold_dir / "fold_manifest.json")
    surface_seed = _stable_surface_seed(bounds, surface_seed_base)
    surface = _dense_land_surface(bounds, n_points=surface_points, seed=surface_seed)
    prototypes = _training_prototypes(training)
    consensus, uncertainty, audit = leave_one_out_consensus_support(
        surface,
        prototypes,
        feature_columns=ROBUST_FEATURES,
        support_world_dtype="float32",
    )
    surface["consensus_support_rank"] = consensus
    surface["consensus_support_uncertainty"] = uncertainty
    held = heldout[["latitude", "longitude"]].apply(pd.to_numeric, errors="coerce").dropna().copy()
    held["survey_area_id"] = "region"
    if held.empty:
        return []

    rng = np.random.default_rng(int(random_seed) + 991)
    rows: list[dict[str, object]] = []
    for tier in tiers:
        selected, patches = support_cells_to_patches(
            surface,
            consensus,
            threshold=float(tier),
            merge_distance_m=1000.0,
            area_col="survey_area_id",
        )
        if selected.empty:
            continue
        observed = recovery_summary(
            detection_recovery_table(
                selected,
                held,
                radii_km=radii_km,
                area_col="survey_area_id",
                detection_area_col="survey_area_id",
            ),
            radii_km=radii_km,
        )
        random_by_radius = {float(radius): [] for radius in radii_km}
        draw_n = len(selected)
        for _ in range(int(random_draws)):
            draw = surface.iloc[rng.choice(len(surface), size=draw_n, replace=False)].copy()
            draw["site_id"] = np.arange(len(draw)).astype(str)
            summary = recovery_summary(
                detection_recovery_table(
                    draw,
                    held,
                    radii_km=radii_km,
                    area_col="survey_area_id",
                    detection_area_col="survey_area_id",
                ),
                radii_km=radii_km,
            )
            for record in summary.itertuples(index=False):
                random_by_radius[float(record.radius_km)].append(float(record.detection_recall))
        for record in observed.itertuples(index=False):
            values = np.asarray(random_by_radius[float(record.radius_km)], dtype=float)
            random_mean = float(values.mean()) if len(values) else float("nan")
            rows.append(
                {
                    "fold": str(fold_dir),
                    "support_fraction": float(tier),
                    "radius_km": float(record.radius_km),
                    "surface_points": int(len(surface)),
                    "surface_seed": int(surface_seed),
                    "prototype_count": int(audit.prototype_count),
                    "selected_cells": int(len(selected)),
                    "patch_count": int(len(patches)),
                    "heldout_count": int(record.n_detection_clusters),
                    "recall": float(record.detection_recall),
                    "random_mean_recall": random_mean,
                    "lift_over_random": float(record.detection_recall) - random_mean,
                    "median_nearest_km": float(record.median_nearest_candidate_km),
                    "max_nearest_km": float(record.max_nearest_candidate_km),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-root", type=Path, required=True)
    parser.add_argument("--tiers", type=_csv_floats, default=DEFAULT_TIERS)
    parser.add_argument("--radii-km", type=_csv_floats, default=DEFAULT_RADII_KM)
    parser.add_argument("--surface-points", type=int, default=800)
    parser.add_argument("--random-draws", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    fold_dirs = sorted(path.parent for path in args.export_root.glob("pair_*/fold_*/fold_manifest.json"))
    rows: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for index, fold_dir in enumerate(fold_dirs):
        try:
            result = _evaluate_fold(
                fold_dir,
                tiers=args.tiers,
                radii_km=args.radii_km,
                surface_points=int(args.surface_points),
                random_draws=int(args.random_draws),
                surface_seed_base=int(args.seed),
                random_seed=int(args.seed) + index * 1009,
            )
            if result:
                rows.extend(result)
            else:
                skipped.append({"fold": str(fold_dir), "reason": "no evaluable rows"})
        except Exception as exc:
            skipped.append({"fold": str(fold_dir), "reason": f"{type(exc).__name__}: {exc}"})

    results = pd.DataFrame(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.out / "dense_robust_patch_fold_results.csv", index=False)
    pd.DataFrame(skipped).to_csv(args.out / "dense_robust_patch_skips.csv", index=False)
    if results.empty:
        summary = pd.DataFrame()
    else:
        summary = (
            results.groupby(["support_fraction", "radius_km"], as_index=False)
            .agg(
                folds=("fold", "nunique"),
                mean_recall=("recall", "mean"),
                mean_random_recall=("random_mean_recall", "mean"),
                mean_lift=("lift_over_random", "mean"),
                median_selected_cells=("selected_cells", "median"),
                median_patches=("patch_count", "median"),
            )
        )
    summary.to_csv(args.out / "dense_robust_patch_summary.csv", index=False)
    manifest = {
        "status": "historical_development_only",
        "untouched_confirmation_opened": False,
        "universe_rule": "one deterministic land surface per predeclared region, shared across folds; WorldClim 2.5m terrain extracted independently of held-out outcomes",
        "prototype_rule": "training occurrences deterministically spatially thinned to at most 32 prototypes; terrain extracted directly at retained training coordinates",
        "terrain_features": list(ROBUST_FEATURES),
        "folds_discovered": int(len(fold_dirs)),
        "folds_evaluated": int(results["fold"].nunique()) if not results.empty else 0,
        "folds_skipped": int(len(skipped)),
        "surface_points_requested": int(args.surface_points),
        "max_prototypes": MAX_PROTOTYPES,
        "tiers": list(args.tiers),
        "radii_km": list(args.radii_km),
        "tier_auto_selection": False,
    }
    (args.out / "dense_robust_patch_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(summary.to_string(index=False) if not summary.empty else "no evaluable folds")
    print(json.dumps(manifest, indent=2))
    if not results.empty and results["fold"].nunique() < max(1, int(len(fold_dirs) * 0.75)):
        raise RuntimeError("dense-surface evaluator covered fewer than 75% of discovered folds")


if __name__ == "__main__":
    main()
