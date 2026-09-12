#!/usr/bin/env python3
"""Development-only whole-population spatial holdout on frozen Japanese plants.

The frozen 48 plant taxon-region pairs are already consumed. This runner removes
whole 0.5-km population clusters before rebuilding the training-only terrain
selector, then compares matched-k environmental support, nearest-known, spatial
balance, and random selection on one common eligible surface. Hidden populations
are used only for final recovery scoring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.taxon_patches import ROBUST_TERRAIN_FEATURES, _terrain_inputs
from acsp.validated_robust import validated_robust_candidate_patches
from benchmark_public_japan_96pair_temporal_anchor_v1 import (
    complete_link_clusters,
    dedupe_period,
    fetch_pair_records,
)
from compare_public_japan_96pair_environment_vs_distance_v1 import (
    min_distance_to_historical,
    random_recovery_mean,
    recovery_fraction,
    select_nearest_known,
    select_spatial_balance,
)

PROTOCOL_PATH = ROOT / "validation" / "japan_plant_population_holdout_selector_development_v1.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("protocol_id") != "japan_plant_population_holdout_selector_development_v1":
        raise ValueError("protocol id drift")
    if cfg.get("status") != "DEVELOPMENT_PROTOCOL_FROZEN_BEFORE_POPULATION_HOLDOUT_EXECUTION":
        raise ValueError("protocol freeze state drift")
    if cfg.get("independent_confirmation") is not False:
        raise ValueError("consumed cohort cannot be independent confirmation")
    if int(cfg["cohort"]["declared_plant_pairs"]) != 48:
        raise ValueError("plant pair count drift")
    if int(cfg["known_truth"]["minimum_population_clusters_for_pair_evaluation"]) != 3:
        raise ValueError("minimum population threshold drift")
    if int(cfg["holdout"]["maximum_folds_per_pair"]) != 2:
        raise ValueError("fold-count drift")
    if cfg["holdout"]["heldout_cluster_available_to_generation_or_ranking"] is not False:
        raise ValueError("hidden population leakage is forbidden")
    if [float(v) for v in cfg["recovery_radii_km"]] != [2.0, 5.0, 10.0]:
        raise ValueError("recovery radii drift")
    return cfg


def load_frozen_plants(sample_file: Path, cfg: dict[str, Any]) -> pd.DataFrame:
    cohort_cfg = cfg["cohort"]
    if _sha256_file(sample_file) != str(cohort_cfg["predeclared_pairs_sha256"]):
        raise ValueError("frozen cohort bytes drift")
    sample = pd.read_csv(sample_file)
    required = {
        "pair_id", "status", "taxon_group", "region_name", "west", "south", "east", "north",
        "speciesKey", "scientific_name",
    }
    if not required.issubset(sample.columns):
        raise ValueError(f"sample missing columns: {sorted(required.difference(sample.columns))}")
    declared = sample.loc[sample["status"].eq("predeclared")].copy()
    if len(declared) != int(cohort_cfg["declared_source_pairs"]):
        raise ValueError("frozen source-pair count drift")
    plants = declared.loc[declared["taxon_group"].eq("plant")].copy().sort_values("pair_id").reset_index(drop=True)
    if len(plants) != int(cohort_cfg["declared_plant_pairs"]):
        raise ValueError("frozen plant-pair count drift")
    if plants["speciesKey"].nunique() != len(plants) or plants["scientific_name"].nunique() != len(plants):
        raise ValueError("frozen plant cohort must contain unique provider identities")
    return plants


def stable_cluster_fingerprint(cluster: list[tuple[float, float, str]]) -> str:
    payload = [
        f"{float(lat):.8f}|{float(lon):.8f}|{str(key)}"
        for lat, lon, key in sorted(cluster, key=lambda x: (float(x[0]), float(x[1]), str(x[2])))
    ]
    return hashlib.sha256(("\n".join(payload) + "\n").encode("utf-8")).hexdigest()


def select_holdout_clusters(
    clusters: list[list[tuple[float, float, str]]], maximum_folds: int
) -> list[tuple[int, str, list[tuple[float, float, str]]]]:
    ranked = sorted(
        [(index, stable_cluster_fingerprint(cluster), cluster) for index, cluster in enumerate(clusters)],
        key=lambda item: (item[1], item[0]),
    )
    return ranked[: min(int(maximum_folds), len(ranked))]


def clusters_to_training_frame(
    clusters: list[list[tuple[float, float, str]]], heldout_index: int
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, cluster in enumerate(clusters):
        if int(index) == int(heldout_index):
            continue
        for lat, lon, key in cluster:
            rows.append({"gbif_key": str(key), "latitude": float(lat), "longitude": float(lon)})
    if not rows:
        return pd.DataFrame(columns=["gbif_key", "latitude", "longitude"])
    return (
        pd.DataFrame(rows)
        .drop_duplicates(["latitude", "longitude"], keep="first")
        .sort_values(["latitude", "longitude", "gbif_key"], kind="mergesort")
        .reset_index(drop=True)
    )


def build_training_selectors(
    training: pd.DataFrame,
    *,
    bounds: tuple[float, float, float, float],
    pair_id: int,
    fold_number: int,
    known_exclusion_km: float,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Build all matched-k selectors without receiving any heldout coordinates."""
    if training.empty:
        raise ValueError("training population rows are empty")
    area_id = f"JPPOP_{int(pair_id):03d}_F{int(fold_number):02d}"
    surface, prototypes, surface_seed = _terrain_inputs(training, bounds, area_id=area_id)
    nearest_training = min_distance_to_historical(surface, training)
    eligible_surface = surface.loc[
        nearest_training > float(known_exclusion_km) + 1e-12
    ].copy().reset_index(drop=True)
    if eligible_surface.empty:
        raise ValueError("common eligible surface is empty after known-point exclusion")

    environment, support_audit = validated_robust_candidate_patches(
        eligible_surface,
        prototypes,
        feature_columns=ROBUST_TERRAIN_FEATURES,
        area_col="survey_area_id",
    )
    k = int(len(environment))
    if k <= 0:
        raise ValueError("environment selector returned zero matched-k candidates")
    if len(eligible_surface) < k:
        raise ValueError("matched k exceeds common eligible surface")

    nearest = select_nearest_known(
        eligible_surface,
        training,
        pair_id=int(pair_id),
        count=k,
        exclusion_km=float(known_exclusion_km),
    )
    spatial = select_spatial_balance(eligible_surface, pair_id=int(pair_id), count=k)
    if not (len(environment) == len(nearest) == len(spatial) == k):
        raise AssertionError("matched-k selector count mismatch")
    return (
        {
            "environment": environment.reset_index(drop=True),
            "nearest_known": nearest.reset_index(drop=True),
            "spatial_balance": spatial.reset_index(drop=True),
            "eligible_surface": eligible_surface,
        },
        {
            "surface_points": int(len(surface)),
            "eligible_surface_points": int(len(eligible_surface)),
            "prototype_rows": int(len(prototypes)),
            "matched_k": k,
            "surface_seed": int(surface_seed),
            "support_audit": support_audit.as_dict(),
        },
    )


def score_fold(
    selectors: dict[str, pd.DataFrame],
    heldout_cluster: list[tuple[float, float, str]],
    *,
    pair_id: int,
    fold_number: int,
    cfg: dict[str, Any],
) -> dict[str, float]:
    """Score one already-built selector set; hidden truth enters only here."""
    k = int(len(selectors["environment"]))
    rows: dict[str, float] = {}
    random_cfg = cfg["random"]
    for radius in [float(v) for v in cfg["recovery_radii_km"]]:
        env = recovery_fraction(selectors["environment"], [heldout_cluster], radius)
        nearest = recovery_fraction(selectors["nearest_known"], [heldout_cluster], radius)
        spatial = recovery_fraction(selectors["spatial_balance"], [heldout_cluster], radius)
        random_mean = random_recovery_mean(
            selectors["eligible_surface"],
            [heldout_cluster],
            pair_id=int(pair_id),
            count=k,
            radius_km=radius,
            repetitions=int(random_cfg["repetitions_per_fold"]),
            seed_base=int(random_cfg["seed_base"]) + 10000 * int(fold_number),
        )
        suffix = f"{int(radius)}km"
        rows[f"environment_recovery_{suffix}"] = float(env)
        rows[f"nearest_known_recovery_{suffix}"] = float(nearest)
        rows[f"spatial_balance_recovery_{suffix}"] = float(spatial)
        rows[f"random_recovery_{suffix}"] = float(random_mean)
        rows[f"environment_minus_nearest_{suffix}"] = float(env - nearest)
        rows[f"environment_minus_spatial_balance_{suffix}"] = float(env - spatial)
        rows[f"environment_minus_random_{suffix}"] = float(env - random_mean)
    return rows


def evaluate_pair(pair: pd.Series, records: pd.DataFrame, cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    unique = dedupe_period(records.copy())
    clusters = complete_link_clusters(
        unique,
        float(cfg["known_truth"]["population_cluster_maximum_within_distance_km"]),
    )
    pair_base = {
        "pair_id": int(pair.pair_id),
        "region_name": str(pair.region_name),
        "speciesKey": int(pair.speciesKey),
        "scientific_name": str(pair.scientific_name),
        "strict_unique_coordinates": int(len(unique)),
        "population_clusters": int(len(clusters)),
    }
    minimum = int(cfg["known_truth"]["minimum_population_clusters_for_pair_evaluation"])
    if len(clusters) < minimum:
        return [], {**pair_base, "status": "NOT_EVALUABLE_FEWER_THAN_3_POPULATIONS", "successful_folds": 0}

    bounds = (float(pair.west), float(pair.south), float(pair.east), float(pair.north))
    selected = select_holdout_clusters(clusters, int(cfg["holdout"]["maximum_folds_per_pair"]))
    fold_rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for fold_number, (heldout_index, cluster_hash, heldout_cluster) in enumerate(selected, start=1):
        training = clusters_to_training_frame(clusters, heldout_index)
        try:
            selectors, audit = build_training_selectors(
                training,
                bounds=bounds,
                pair_id=int(pair.pair_id),
                fold_number=fold_number,
                known_exclusion_km=float(cfg["candidate_surface"]["known_reobservation_exclusion_km"]),
            )
            scored = score_fold(
                selectors,
                heldout_cluster,
                pair_id=int(pair.pair_id),
                fold_number=fold_number,
                cfg=cfg,
            )
            fold_rows.append({
                **pair_base,
                "fold_number": int(fold_number),
                "heldout_cluster_sha256": str(cluster_hash),
                "heldout_cluster_source_rows": int(len(heldout_cluster)),
                "training_population_clusters": int(len(clusters) - 1),
                "training_unique_coordinates": int(len(training)),
                "status": "OK",
                "surface_points": int(audit["surface_points"]),
                "eligible_surface_points": int(audit["eligible_surface_points"]),
                "prototype_rows": int(audit["prototype_rows"]),
                "matched_k": int(audit["matched_k"]),
                "surface_seed": int(audit["surface_seed"]),
                **scored,
            })
        except Exception as exc:
            failures.append(f"fold{fold_number}:{type(exc).__name__}:{str(exc)[:180]}")
    status = "EVALUATED" if fold_rows else "PAIR_GENERATION_FAILED"
    return fold_rows, {
        **pair_base,
        "status": status,
        "attempted_folds": int(len(selected)),
        "successful_folds": int(len(fold_rows)),
        "failure_notes": " | ".join(failures),
    }


def summarize(folds: pd.DataFrame, pair_status: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    if len(pair_status) != int(cfg["cohort"]["declared_plant_pairs"]):
        raise ValueError("intention-to-evaluate plant denominator drift")
    ok = folds.loc[folds["status"].eq("OK")].copy() if not folds.empty else folds.copy()
    summary: dict[str, Any] = {
        "schema_version": "japan-plant-population-holdout-selector-development-result-v1",
        "status": "DEVELOPMENT_COMPLETE",
        "source_issue": 207,
        "independent_confirmation": False,
        "declared_plant_pairs": int(len(pair_status)),
        "pairs_with_three_or_more_populations": int((pair_status["population_clusters"] >= 3).sum()),
        "pairs_with_at_least_one_successful_fold": int((pair_status["successful_folds"] > 0).sum()),
        "successful_population_holdout_folds": int(len(ok)),
        "pair_status_counts": {str(k): int(v) for k, v in pair_status["status"].value_counts().items()},
        "heldout_used_for_generation_or_ranking": False,
        "matched_k": True,
        "radius_tuning_performed": False,
        "selector_weight_tuning_performed": False,
        "production_selector_changed": False,
    }
    for radius in [int(float(v)) for v in cfg["recovery_radii_km"]]:
        suffix = f"{radius}km"
        for method in ("environment", "nearest_known", "spatial_balance", "random"):
            column = f"{method}_recovery_{suffix}"
            summary[f"mean_{column}"] = None if ok.empty else float(pd.to_numeric(ok[column], errors="coerce").mean())
        for contrast in ("environment_minus_nearest", "environment_minus_spatial_balance", "environment_minus_random"):
            column = f"{contrast}_{suffix}"
            values = pd.to_numeric(ok[column], errors="coerce") if not ok.empty else pd.Series(dtype=float)
            summary[f"mean_{column}"] = None if values.empty else float(values.mean())
            summary[f"median_{column}"] = None if values.empty else float(values.median())
            if not values.empty and contrast != "environment_minus_random":
                summary[f"{contrast}_{suffix}_win_tie_loss"] = {
                    "win": int((values > 1e-12).sum()),
                    "tie": int(values.abs().le(1e-12).sum()),
                    "loss": int((values < -1e-12).sum()),
                }
    primary = cfg["primary_development_contrast"]
    primary_radius = int(float(primary["radius_km"]))
    summary["primary_development_radius_km"] = primary_radius
    summary["primary_environment_minus_nearest_mean"] = summary.get(
        f"mean_environment_minus_nearest_{primary_radius}km"
    )
    summary["primary_environment_minus_spatial_balance_mean"] = summary.get(
        f"mean_environment_minus_spatial_balance_{primary_radius}km"
    )
    summary["claim_boundary"] = cfg["claim_boundary"]
    return summary


def run(sample_file: Path, protocol_path: Path = PROTOCOL_PATH) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    cfg = load_protocol(protocol_path)
    plants = load_frozen_plants(sample_file, cfg)
    fold_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    for _, pair in plants.iterrows():
        try:
            records, provider_audit = fetch_pair_records(pair, page_size=300, maximum_records=10000)
            folds, status = evaluate_pair(pair, records, cfg)
            status["provider_raw_api_records_seen"] = int(provider_audit["raw_api_records_seen"])
            status["provider_strict_eligible_records"] = int(provider_audit["strict_eligible_records"])
            fold_rows.extend(folds)
            status_rows.append(status)
        except Exception as exc:
            status_rows.append({
                "pair_id": int(pair.pair_id),
                "region_name": str(pair.region_name),
                "speciesKey": int(pair.speciesKey),
                "scientific_name": str(pair.scientific_name),
                "strict_unique_coordinates": 0,
                "population_clusters": 0,
                "status": "PROVIDER_OR_PREPARATION_FAILURE",
                "attempted_folds": 0,
                "successful_folds": 0,
                "failure_notes": f"{type(exc).__name__}:{str(exc)[:220]}",
                "provider_raw_api_records_seen": 0,
                "provider_strict_eligible_records": 0,
            })
    folds = pd.DataFrame(fold_rows)
    pair_status = pd.DataFrame(status_rows).sort_values("pair_id").reset_index(drop=True)
    summary = summarize(folds, pair_status, cfg)
    return summary, folds, pair_status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-file", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    summary, folds, pair_status = run(args.sample_file, args.protocol)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    folds.to_csv(args.out_dir / "population_holdout_folds.csv", index=False)
    pair_status.to_csv(args.out_dir / "pair_status.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
