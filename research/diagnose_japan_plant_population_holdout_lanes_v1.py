#!/usr/bin/env python3
"""Post-hoc LOCAL/DETACHED diagnosis for the terminal #207 holdout result.

This runner never rebuilds or rescored selectors. It reconstructs only the exact
population clusters and #207 holdout identities, computes hidden-to-retained
population distance, assigns the pre-existing 5-km LOCAL/DETACHED lane, and then
summarizes the already-frozen #207 recovery columns within those lanes.
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

from benchmark_public_japan_96pair_temporal_anchor_v1 import (
    cluster_min_distance,
    complete_link_clusters,
    dedupe_period,
    fetch_pair_records,
)
from develop_japan_plant_population_holdout_selector_v1 import select_holdout_clusters

PROTOCOL_PATH = ROOT / "validation" / "japan_plant_population_holdout_lane_diagnostic_v1.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("protocol_id") != "japan_plant_population_holdout_lane_diagnostic_v1":
        raise ValueError("protocol id drift")
    if cfg.get("status") != "POSTHOC_DIAGNOSTIC_FROZEN_BEFORE_RECONSTRUCTION":
        raise ValueError("protocol freeze state drift")
    if cfg.get("independent_confirmation") is not False:
        raise ValueError("post-hoc consumed cohort cannot be independent confirmation")
    if float(cfg["lane_definition"]["boundary_km"]) != 5.0:
        raise ValueError("LOCAL/DETACHED boundary drift")
    if int(cfg["source_207"]["successful_folds"]) != 25:
        raise ValueError("source fold-count drift")
    forbidden = cfg["forbidden"]
    for key in (
        "selector_rebuild", "selector_rescoring", "lane_boundary_tuning",
        "radius_tuning", "k_tuning", "cluster_threshold_tuning",
        "selector_weight_tuning", "environment_distance_blending",
        "source_207_rescue", "production_selector_change",
    ):
        if forbidden.get(key) is not True:
            raise ValueError(f"forbidden boundary drift: {key}")
    return cfg


def load_frozen_inputs(
    folds_path: Path, sample_path: Path, cfg: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if _sha256_file(folds_path) != str(cfg["source_207"]["folds_sha256"]):
        raise ValueError("#207 folds bytes drift")
    if _sha256_file(sample_path) != str(cfg["source_cohort"]["sample_sha256"]):
        raise ValueError("source cohort bytes drift")

    folds = pd.read_csv(folds_path)
    required_folds = {
        "pair_id", "fold_number", "heldout_cluster_sha256", "speciesKey",
        "scientific_name", "population_clusters", "training_population_clusters",
        "status",
    }
    for radius in (2, 5, 10):
        required_folds.update({
            f"environment_recovery_{radius}km",
            f"nearest_known_recovery_{radius}km",
            f"spatial_balance_recovery_{radius}km",
            f"random_recovery_{radius}km",
            f"environment_minus_nearest_{radius}km",
            f"environment_minus_spatial_balance_{radius}km",
            f"environment_minus_random_{radius}km",
        })
    missing = sorted(required_folds.difference(folds.columns))
    if missing:
        raise ValueError(f"#207 folds missing columns: {missing}")
    if len(folds) != int(cfg["source_207"]["successful_folds"]):
        raise ValueError("#207 successful fold count drift")
    if not folds["status"].eq("OK").all():
        raise ValueError("#207 diagnostic input must contain only successful folds")
    if folds[["pair_id", "fold_number"]].duplicated().any():
        raise ValueError("duplicate #207 fold key")

    sample = pd.read_csv(sample_path)
    required_sample = {
        "pair_id", "status", "taxon_group", "region_name", "west", "south",
        "east", "north", "speciesKey", "scientific_name",
    }
    missing = sorted(required_sample.difference(sample.columns))
    if missing:
        raise ValueError(f"source cohort missing columns: {missing}")
    sample = sample.loc[
        sample["status"].eq("predeclared") & sample["taxon_group"].eq("plant")
    ].copy()
    if sample["pair_id"].duplicated().any():
        raise ValueError("source plant pair IDs are not unique")
    requested = set(pd.to_numeric(folds["pair_id"], errors="raise").astype(int))
    available = set(pd.to_numeric(sample["pair_id"], errors="raise").astype(int))
    if not requested.issubset(available):
        raise ValueError("#207 fold pair missing from source cohort")
    return folds.sort_values(["pair_id", "fold_number"]).reset_index(drop=True), sample


def classify_lane(distance_km: float, boundary_km: float = 5.0) -> str:
    if not np.isfinite(float(distance_km)) or float(distance_km) < 0:
        raise ValueError("nearest training-population distance must be finite and non-negative")
    return "LOCAL" if float(distance_km) <= float(boundary_km) + 1e-12 else "DETACHED"


def reconstruct_lane_rows(
    folds: pd.DataFrame,
    sample: pd.DataFrame,
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    sample_by_id = sample.set_index("pair_id", drop=False)
    boundary = float(cfg["lane_definition"]["boundary_km"])
    cluster_radius = float(cfg["reconstruction"]["population_cluster_maximum_within_distance_km"])
    max_folds = int(cfg["reconstruction"]["maximum_folds_per_pair"])
    page_size = int(cfg["reconstruction"]["page_size"])
    maximum_records = int(cfg["reconstruction"]["maximum_records_per_pair"])

    output_rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    for pair_id, frozen_pair_folds in folds.groupby("pair_id", sort=True):
        pair_id = int(pair_id)
        if pair_id not in sample_by_id.index:
            raise RuntimeError(f"source pair missing: {pair_id}")
        pair = sample_by_id.loc[pair_id]
        expected_key = int(frozen_pair_folds["speciesKey"].iloc[0])
        expected_name = str(frozen_pair_folds["scientific_name"].iloc[0])
        if int(pair.speciesKey) != expected_key or str(pair.scientific_name) != expected_name:
            raise RuntimeError(f"provider identity drift for pair {pair_id}")

        records, provider_audit = fetch_pair_records(
            pair,
            page_size=page_size,
            maximum_records=maximum_records,
        )
        unique = dedupe_period(records.copy())
        clusters = complete_link_clusters(unique, cluster_radius)
        selected = select_holdout_clusters(clusters, max_folds)
        selected_by_fold = {
            fold_number: (heldout_index, cluster_hash, heldout_cluster)
            for fold_number, (heldout_index, cluster_hash, heldout_cluster)
            in enumerate(selected, start=1)
        }
        if int(frozen_pair_folds["population_clusters"].iloc[0]) != len(clusters):
            raise RuntimeError(
                f"population reconstruction drift pair={pair_id}: "
                f"frozen={int(frozen_pair_folds['population_clusters'].iloc[0])} live={len(clusters)}"
            )

        for frozen in frozen_pair_folds.sort_values("fold_number").to_dict(orient="records"):
            fold_number = int(frozen["fold_number"])
            if fold_number not in selected_by_fold:
                raise RuntimeError(f"selected fold missing pair={pair_id} fold={fold_number}")
            heldout_index, cluster_hash, heldout_cluster = selected_by_fold[fold_number]
            if str(cluster_hash) != str(frozen["heldout_cluster_sha256"]):
                raise RuntimeError(
                    f"heldout fingerprint drift pair={pair_id} fold={fold_number}"
                )
            retained = [cluster for index, cluster in enumerate(clusters) if index != int(heldout_index)]
            if len(retained) != int(frozen["training_population_clusters"]):
                raise RuntimeError(
                    f"training population-count drift pair={pair_id} fold={fold_number}"
                )
            if not retained:
                raise RuntimeError(f"no retained population pair={pair_id} fold={fold_number}")
            nearest_km = min(cluster_min_distance(heldout_cluster, old) for old in retained)
            output_rows.append({
                **frozen,
                "nearest_training_population_km": float(nearest_km),
                "discovery_lane": classify_lane(float(nearest_km), boundary),
            })

        audits.append({
            "pair_id": pair_id,
            "speciesKey": expected_key,
            "scientific_name": expected_name,
            "frozen_successful_folds": int(len(frozen_pair_folds)),
            "live_population_clusters": int(len(clusters)),
            "provider_raw_api_records_seen": int(provider_audit["raw_api_records_seen"]),
            "provider_strict_eligible_records": int(provider_audit["strict_eligible_records"]),
            "fold_identity_match": True,
        })

    out = pd.DataFrame(output_rows).sort_values(["pair_id", "fold_number"]).reset_index(drop=True)
    if len(out) != len(folds):
        raise RuntimeError("diagnostic output fold count drift")
    return out, audits


def _win_tie_loss(values: pd.Series) -> dict[str, int]:
    numeric = pd.to_numeric(values, errors="raise")
    return {
        "win": int((numeric > 1e-12).sum()),
        "tie": int(numeric.abs().le(1e-12).sum()),
        "loss": int((numeric < -1e-12).sum()),
    }


def summarize_lanes(table: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": "japan-plant-population-holdout-lane-diagnostic-result-v1",
        "status": "POSTHOC_DIAGNOSTIC_COMPLETE",
        "source_issue": 208,
        "source_207_terminal_unchanged": True,
        "independent_confirmation": False,
        "selector_rebuilt": False,
        "selector_rescored": False,
        "lane_boundary_km": float(cfg["lane_definition"]["boundary_km"]),
        "lane_boundary_tuned": False,
        "successful_source_folds": int(len(table)),
        "source_unique_pairs": int(table["pair_id"].nunique()),
        "lanes": {},
        "claim_boundary": cfg["claim_boundary"],
    }
    for lane in ("LOCAL", "DETACHED"):
        subset = table.loc[table["discovery_lane"].eq(lane)].copy()
        lane_summary: dict[str, Any] = {
            "folds": int(len(subset)),
            "unique_pairs": int(subset["pair_id"].nunique()),
            "nearest_training_population_km_mean": None if subset.empty else float(subset["nearest_training_population_km"].mean()),
            "nearest_training_population_km_median": None if subset.empty else float(subset["nearest_training_population_km"].median()),
        }
        for radius in [int(float(v)) for v in cfg["recovery_radii_km"]]:
            suffix = f"{radius}km"
            radius_summary: dict[str, Any] = {}
            for method in ("environment", "nearest_known", "spatial_balance", "random"):
                column = f"{method}_recovery_{suffix}"
                radius_summary[f"mean_{method}_recovery"] = (
                    None if subset.empty else float(pd.to_numeric(subset[column], errors="raise").mean())
                )
            for label, column in (
                ("environment_minus_nearest", f"environment_minus_nearest_{suffix}"),
                ("environment_minus_spatial_balance", f"environment_minus_spatial_balance_{suffix}"),
                ("environment_minus_random", f"environment_minus_random_{suffix}"),
            ):
                radius_summary[f"mean_{label}"] = (
                    None if subset.empty else float(pd.to_numeric(subset[column], errors="raise").mean())
                )
                if not subset.empty and label != "environment_minus_random":
                    radius_summary[f"{label}_win_tie_loss"] = _win_tie_loss(subset[column])
            lane_summary[suffix] = radius_summary
        summary["lanes"][lane] = lane_summary

    primary_suffix = f"{int(float(cfg['primary_diagnostic_radius_km']))}km"
    local = summary["lanes"]["LOCAL"][primary_suffix]
    detached = summary["lanes"]["DETACHED"][primary_suffix]
    summary["primary_5km_pattern"] = {
        "local_environment_minus_nearest": local["mean_environment_minus_nearest"],
        "detached_environment_minus_nearest": detached["mean_environment_minus_nearest"],
        "local_environment_minus_spatial_balance": local["mean_environment_minus_spatial_balance"],
        "detached_environment_minus_spatial_balance": detached["mean_environment_minus_spatial_balance"],
        "directional_lane_separation": bool(
            local["mean_environment_minus_nearest"] is not None
            and detached["mean_environment_minus_nearest"] is not None
            and float(local["mean_environment_minus_nearest"]) <= 0.0
            and float(detached["mean_environment_minus_nearest"]) > 0.0
        ),
    }
    return summary


def run(
    folds_path: Path,
    sample_path: Path,
    protocol_path: Path = PROTOCOL_PATH,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    cfg = load_protocol(protocol_path)
    folds, sample = load_frozen_inputs(folds_path, sample_path, cfg)
    lane_table, audits = reconstruct_lane_rows(folds, sample, cfg)
    summary = summarize_lanes(lane_table, cfg)
    return summary, lane_table, pd.DataFrame(audits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folds", type=Path, required=True)
    parser.add_argument("--sample-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    args = parser.parse_args()

    summary, lane_table, audits = run(args.folds, args.sample_file, args.protocol)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lane_table.to_csv(args.out_dir / "lane_folds.csv", index=False)
    audits.to_csv(args.out_dir / "reconstruction_audit.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
