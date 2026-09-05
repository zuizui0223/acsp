#!/usr/bin/env python3
"""Compare frozen environmental support with distance and spatial-balance baselines.

Development-only reuse of the already-consumed 96 Japanese taxon-region pairs.
The comparative methods are frozen in
``validation/public_japan_96pair_environment_vs_distance_development_v1.json``.
No result from this script is an independent confirmation claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "research") not in sys.path:
    sys.path.insert(0, str(ROOT / "research"))

from acsp.taxon_patches import ROBUST_TERRAIN_FEATURES, _terrain_inputs
from acsp.validated_robust import validated_robust_candidate_patches
from benchmark_public_japan_96pair_temporal_anchor_v1 import (
    cluster_min_distance,
    complete_link_clusters,
    dedupe_period,
    fetch_pair_records,
    haversine_km,
)

DEFAULT_CONTRACT = ROOT / "validation" / "public_japan_96pair_environment_vs_distance_development_v1.json"
EARTH_RADIUS_KM = 6371.0088


def stable_candidate_key(pair_id: int, lat: float, lon: float) -> str:
    token = f"{int(pair_id)}|{float(lat):.8f}|{float(lon):.8f}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _surface_points(surface: pd.DataFrame, pair_id: int) -> pd.DataFrame:
    required = {"latitude", "longitude"}
    missing = sorted(required.difference(surface.columns))
    if missing:
        raise ValueError(f"candidate surface missing columns: {missing}")
    out = surface.copy().reset_index(drop=True)
    out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
    out = out.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    out["_stable_key"] = [
        stable_candidate_key(pair_id, lat, lon)
        for lat, lon in zip(out["latitude"], out["longitude"])
    ]
    if out.empty:
        raise ValueError("candidate surface has no complete coordinates")
    return out


def _haversine_vector(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    p1 = math.radians(float(lat))
    p2 = np.radians(lats.astype(float))
    dp = p2 - p1
    dl = np.radians(lons.astype(float) - float(lon))
    a = np.sin(dp / 2.0) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def min_distance_to_historical(surface: pd.DataFrame, historical: pd.DataFrame) -> np.ndarray:
    if historical.empty:
        raise ValueError("historical evidence is empty")
    hlat = historical["latitude"].to_numpy(float)
    hlon = historical["longitude"].to_numpy(float)
    values = []
    for row in surface.itertuples(index=False):
        values.append(float(np.min(_haversine_vector(float(row.latitude), float(row.longitude), hlat, hlon))))
    return np.asarray(values, dtype=float)


def select_nearest_known(
    surface: pd.DataFrame,
    historical: pd.DataFrame,
    *,
    pair_id: int,
    count: int,
    exclusion_km: float,
) -> pd.DataFrame:
    work = _surface_points(surface, pair_id)
    work["_nearest_historical_km"] = min_distance_to_historical(work, historical)
    eligible = work.loc[work["_nearest_historical_km"] > float(exclusion_km) + 1e-12].copy()
    eligible = eligible.sort_values(["_nearest_historical_km", "_stable_key"], kind="mergesort")
    if int(count) < 0:
        raise ValueError("selection count must be non-negative")
    if len(eligible) < int(count):
        raise ValueError(f"nearest-known has {len(eligible)} eligible points for required k={int(count)}")
    return eligible.head(int(count)).reset_index(drop=True)


def select_spatial_balance(surface: pd.DataFrame, *, pair_id: int, count: int) -> pd.DataFrame:
    work = _surface_points(surface, pair_id)
    k = int(count)
    if k < 0:
        raise ValueError("selection count must be non-negative")
    if k > len(work):
        raise ValueError(f"spatial balance requires k={k} from only {len(work)} candidates")
    if k == 0:
        return work.iloc[:0].copy()

    keys = work["_stable_key"].astype(str).to_numpy()
    lats = work["latitude"].to_numpy(float)
    lons = work["longitude"].to_numpy(float)
    first = int(np.argmin(keys))
    selected = [first]
    chosen = np.zeros(len(work), dtype=bool)
    chosen[first] = True
    min_dist = _haversine_vector(lats[first], lons[first], lats, lons)
    min_dist[first] = -np.inf

    while len(selected) < k:
        candidates = np.where(~chosen)[0]
        if len(candidates) == 0:
            break
        best_distance = float(np.max(min_dist[candidates]))
        tied = candidates[np.isclose(min_dist[candidates], best_distance, rtol=0.0, atol=1e-12)]
        best = int(min(tied, key=lambda idx: keys[int(idx)]))
        selected.append(best)
        chosen[best] = True
        new_dist = _haversine_vector(lats[best], lons[best], lats, lons)
        min_dist = np.minimum(min_dist, new_dist)
        min_dist[chosen] = -np.inf

    if len(selected) != k:
        raise AssertionError("spatial-balance selector did not return exact k")
    return work.iloc[selected].reset_index(drop=True)


def novel_recent_clusters(records: pd.DataFrame) -> tuple[pd.DataFrame, list[list[tuple[float, float, str]]]]:
    historical = dedupe_period(records.loc[records["year"].between(2000, 2020)].copy())
    recent = dedupe_period(records.loc[records["year"].between(2021, 2025)].copy())
    h_clusters = complete_link_clusters(historical, 0.5)
    r_clusters = complete_link_clusters(recent, 0.5)
    novel = []
    if h_clusters:
        for cluster in r_clusters:
            nearest = min(cluster_min_distance(cluster, old) for old in h_clusters)
            if nearest > 0.5 + 1e-12:
                novel.append(cluster)
    return historical, novel


def recovery_fraction(selected: pd.DataFrame, clusters: list[list[tuple[float, float, str]]], radius_km: float) -> float:
    if not clusters or selected.empty:
        return 0.0
    recovered = 0
    points = list(zip(selected["latitude"].astype(float), selected["longitude"].astype(float)))
    for cluster in clusters:
        hit = any(
            haversine_km(lat, lon, member[0], member[1]) <= float(radius_km) + 1e-12
            for lat, lon in points
            for member in cluster
        )
        recovered += int(hit)
    return float(recovered / len(clusters))


def random_recovery_mean(
    surface: pd.DataFrame,
    clusters: list[list[tuple[float, float, str]]],
    *,
    pair_id: int,
    count: int,
    radius_km: float,
    repetitions: int,
    seed_base: int,
) -> float:
    if not clusters or int(count) <= 0:
        return 0.0
    if int(count) > len(surface):
        raise ValueError("random comparator selection count exceeds candidate surface")
    rng = np.random.default_rng(int(seed_base) + int(pair_id))
    values = []
    for _ in range(int(repetitions)):
        indices = rng.choice(len(surface), size=int(count), replace=False)
        values.append(recovery_fraction(surface.iloc[indices], clusters, radius_km))
    return float(np.mean(values))


def zero_result(pair: pd.Series, status: str, reason: str, *, strict_records: int = 0, historical_rows: int = 0, novel_clusters: int = 0) -> dict[str, object]:
    row: dict[str, object] = {
        "pair_id": int(pair.pair_id),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "species_key": int(pair.speciesKey),
        "scientific_name": str(pair.scientific_name),
        "status": str(status),
        "failure_reason": str(reason),
        "strict_records": int(strict_records),
        "historical_rows": int(historical_rows),
        "novel_recent_clusters": int(novel_clusters),
        "surface_points": 0,
        "prototype_rows": 0,
        "environment_patch_count_k": 0,
    }
    for radius in (2, 5, 10):
        for method in ("environment", "nearest", "spatial_balance", "random"):
            row[f"{method}_recall_{radius}km"] = 0.0
        row[f"environment_minus_nearest_{radius}km"] = 0.0
        row[f"environment_minus_spatial_balance_{radius}km"] = 0.0
        row[f"environment_minus_random_{radius}km"] = 0.0
    return row


def evaluate_pair(pair: pd.Series, records: pd.DataFrame, contract: dict[str, object]) -> dict[str, object]:
    historical, novel = novel_recent_clusters(records)
    if not novel:
        return zero_result(
            pair,
            "no_novel_recent_target_zero",
            "no novel 2021-2025 cluster after 0.5-km reobservation exclusion",
            strict_records=len(records),
            historical_rows=len(historical),
            novel_clusters=0,
        )
    if len(historical) < int(contract["shared_historical_evidence"]["minimum_historical_rows_for_environmental_generation"]):
        return zero_result(
            pair,
            "insufficient_historical_evidence_zero",
            f"strict historical rows={len(historical)} < minimum",
            strict_records=len(records),
            historical_rows=len(historical),
            novel_clusters=len(novel),
        )

    bounds = (float(pair.west), float(pair.south), float(pair.east), float(pair.north))
    area_id = f"pair-{int(pair.pair_id):03d}"
    try:
        surface, prototypes, _ = _terrain_inputs(historical, bounds, area_id=area_id)
        patches, _ = validated_robust_candidate_patches(
            surface,
            prototypes,
            feature_columns=ROBUST_TERRAIN_FEATURES,
            area_col="survey_area_id",
        )
        k = int(len(patches))
        if k <= 0:
            raise ValueError("environmental support produced zero candidate patches")
        nearest = select_nearest_known(
            surface,
            historical,
            pair_id=int(pair.pair_id),
            count=k,
            exclusion_km=float(contract["scientific_methods"]["nearest_known"]["known_reobservation_exclusion_km"]),
        )
        balanced = select_spatial_balance(surface, pair_id=int(pair.pair_id), count=k)
    except Exception as exc:
        return zero_result(
            pair,
            "comparative_generation_failure_zero",
            f"{type(exc).__name__}: {str(exc)[:240]}",
            strict_records=len(records),
            historical_rows=len(historical),
            novel_clusters=len(novel),
        )

    result: dict[str, object] = {
        "pair_id": int(pair.pair_id),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "species_key": int(pair.speciesKey),
        "scientific_name": str(pair.scientific_name),
        "status": "compared",
        "failure_reason": "",
        "strict_records": int(len(records)),
        "historical_rows": int(len(historical)),
        "novel_recent_clusters": int(len(novel)),
        "surface_points": int(len(surface)),
        "prototype_rows": int(len(prototypes)),
        "environment_patch_count_k": int(k),
    }
    random_cfg = contract["scientific_methods"]["random"]
    for radius in (2, 5, 10):
        env = recovery_fraction(patches, novel, radius)
        near = recovery_fraction(nearest, novel, radius)
        bal = recovery_fraction(balanced, novel, radius)
        rnd = random_recovery_mean(
            surface,
            novel,
            pair_id=int(pair.pair_id),
            count=k,
            radius_km=radius,
            repetitions=int(random_cfg["repetitions"]),
            seed_base=int(random_cfg["seed_base"]),
        )
        result[f"environment_recall_{radius}km"] = env
        result[f"nearest_recall_{radius}km"] = near
        result[f"spatial_balance_recall_{radius}km"] = bal
        result[f"random_recall_{radius}km"] = rnd
        result[f"environment_minus_nearest_{radius}km"] = env - near
        result[f"environment_minus_spatial_balance_{radius}km"] = env - bal
        result[f"environment_minus_random_{radius}km"] = env - rnd
    return result


def summarize(table: pd.DataFrame) -> dict[str, object]:
    if len(table) != 96:
        raise ValueError(f"intention-to-evaluate table must have 96 rows, got {len(table)}")
    out: dict[str, object] = {
        "schema_version": "public-japan-96pair-environment-vs-distance-development-result-v1",
        "status": "DEVELOPMENT_ONLY_COMPARISON_COMPLETE",
        "validated_product_changed": False,
        "new_independent_confirmation_claim": False,
        "declared_pairs": 96,
        "compared_pairs": int(table["status"].eq("compared").sum()),
        "status_counts": {str(k): int(v) for k, v in table["status"].value_counts().items()},
        "novel_recent_clusters_in_declared_denominator": int(table["novel_recent_clusters"].sum()),
    }
    for radius in (2, 5, 10):
        for method in ("environment", "nearest", "spatial_balance", "random"):
            out[f"mean_{method}_recall_{radius}km_all96"] = float(table[f"{method}_recall_{radius}km"].mean())
        for diff in ("environment_minus_nearest", "environment_minus_spatial_balance", "environment_minus_random"):
            out[f"mean_{diff}_{radius}km_all96"] = float(table[f"{diff}_{radius}km"].mean())
    subgroup: dict[str, object] = {}
    for group in ("plant", "animal"):
        frame = table.loc[table["taxon_group"].eq(group)]
        subgroup[group] = {
            "declared_pairs": int(len(frame)),
            "compared_pairs": int(frame["status"].eq("compared").sum()),
            "mean_environment_minus_nearest_10km": float(frame["environment_minus_nearest_10km"].mean()),
            "mean_environment_minus_spatial_balance_10km": float(frame["environment_minus_spatial_balance_10km"].mean()),
            "mean_environment_minus_random_10km": float(frame["environment_minus_random_10km"].mean()),
        }
    out["subgroup_primary"] = subgroup
    overall_near = float(table["environment_minus_nearest_10km"].mean())
    overall_bal = float(table["environment_minus_spatial_balance_10km"].mean())
    group_direction = all(
        subgroup[group]["mean_environment_minus_nearest_10km"] > 0
        and subgroup[group]["mean_environment_minus_spatial_balance_10km"] > 0
        for group in ("plant", "animal")
    )
    passed = bool(overall_near > 0 and overall_bal > 0 and group_direction)
    out["development_nomination_gate"] = {
        "overall_environment_minus_nearest_positive": bool(overall_near > 0),
        "overall_environment_minus_spatial_balance_positive": bool(overall_bal > 0),
        "plant_and_animal_positive_against_both": bool(group_direction),
        "passed": passed,
    }
    out["decision"] = (
        "NOMINATE_ENVIRONMENTAL_SUPPORT_FOR_NEW_DISJOINT_CONFIRMATION"
        if passed
        else "DO_NOT_NOMINATE_OR_RETUNE_ON_THESE_96_OPENED_PAIRS"
    )
    out["interpretation_boundary"] = (
        "Development-only comparison on an already-consumed 96-pair cohort. Positive results can nominate an unchanged method for a new disjoint confirmation, not establish a new validation claim."
    )
    return out


def run(sample_file: Path, contract_path: Path = DEFAULT_CONTRACT) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("status") != "DEVELOPMENT_ONLY_METHOD_FROZEN_BEFORE_COMPARATIVE_EXECUTION":
        raise ValueError("comparative development contract is not in the frozen pre-execution state")
    if contract.get("comparative_execution_opened") is not False:
        raise ValueError("contract must record comparative_execution_opened=false before first run")
    sample = pd.read_csv(sample_file)
    sample = sample.loc[sample["status"].eq("predeclared")].sort_values("pair_id").reset_index(drop=True)
    if len(sample) != 96 or sample["scientific_name"].nunique() != 96:
        raise ValueError("expected exact frozen 96-pair unique-taxon cohort")

    rows: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for _, pair in sample.iterrows():
        try:
            records, audit = fetch_pair_records(pair, page_size=300, maximum_records=10000, pause_seconds=0.02)
            result = evaluate_pair(pair, records, contract)
            audit["status"] = "ok"
        except Exception as exc:
            result = zero_result(pair, "provider_or_fetch_failure_zero", f"{type(exc).__name__}: {str(exc)[:240]}")
            audit = {
                "pair_id": int(pair.pair_id),
                "species_name": str(pair.scientific_name),
                "region_name": str(pair.region_name),
                "raw_api_records_seen": 0,
                "strict_eligible_records": 0,
                "pages": 0,
                "maximum_records_reached": False,
                "status": f"failed:{type(exc).__name__}:{str(exc)[:160]}",
            }
        rows.append(result)
        audits.append(audit)
    table = pd.DataFrame(rows).sort_values("pair_id").reset_index(drop=True)
    return table, summarize(table), pd.DataFrame(audits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-file", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    table, summary, audit = run(args.sample_file, args.contract)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "pair_method_comparison.csv", index=False)
    audit.to_csv(args.out_dir / "gbif_fetch_audit.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
