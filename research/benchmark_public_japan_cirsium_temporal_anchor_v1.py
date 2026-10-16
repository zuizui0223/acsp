#!/usr/bin/env python3
"""Public-data temporal benchmark for occurrence-anchored local discovery in Japan.

The benchmark is frozen by validation/public_japan_cirsium_temporal_anchor_benchmark_v1.json.
It uses only public GBIF occurrence records and the already frozen 13-species Cirsium
cohort. Pre-2021 records define historical clusters; 2021-2025 records are evaluated
as later public observations. No field outcome, private locality, habitat score, route,
or budget information is used.

This is retrospective development evidence only. It does not modify the validated
2.5% robust candidate-patch product and does not validate occupancy or field yield.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "validation" / "public_japan_cirsium_temporal_anchor_benchmark_v1.json"
DEFAULT_COHORT = ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"
GBIF_ENDPOINT = "https://api.gbif.org/v1/occurrence/search"
EARTH_RADIUS_KM = 6371.0088

GEOSPATIAL_ISSUES = {
    "COUNTRY_COORDINATE_MISMATCH",
    "ZERO_COORDINATE",
    "COORDINATE_INVALID",
    "COORDINATE_OUT_OF_RANGE",
    "PRESUMED_NEGATED_LATITUDE",
    "PRESUMED_NEGATED_LONGITUDE",
    "GEODETIC_DATUM_INVALID",
    "COORDINATE_UNCERTAINTY_METERS_INVALID",
}


@dataclass(frozen=True)
class Cluster:
    members: tuple[tuple[float, float, str], ...]

    @property
    def size(self) -> int:
        return len(self.members)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a1 = math.radians(float(lat1))
    o1 = math.radians(float(lon1))
    a2 = math.radians(float(lat2))
    o2 = math.radians(float(lon2))
    dlat = a2 - a1
    dlon = o2 - o1
    value = math.sin(dlat / 2.0) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def cluster_min_distance_km(left: Cluster, right: Cluster) -> float:
    best = float("inf")
    for lat1, lon1, _ in left.members:
        for lat2, lon2, _ in right.members:
            best = min(best, haversine_km(lat1, lon1, lat2, lon2))
    return best


def _complete_link_eligible(cluster: list[tuple[float, float, str]], point: tuple[float, float, str], radius_km: float) -> bool:
    lat, lon, _ = point
    return all(haversine_km(lat, lon, other_lat, other_lon) <= radius_km + 1e-12 for other_lat, other_lon, _ in cluster)


def deterministic_complete_link_greedy(records: pd.DataFrame, radius_km: float = 0.5) -> list[Cluster]:
    if records.empty:
        return []
    required = {"latitude", "longitude", "gbif_key"}
    missing = sorted(required.difference(records.columns))
    if missing:
        raise ValueError(f"records missing clustering columns: {missing}")
    ordered = records.sort_values(["latitude", "longitude", "gbif_key"], kind="mergesort")
    clusters: list[list[tuple[float, float, str]]] = []
    for row in ordered.itertuples(index=False):
        point = (float(row.latitude), float(row.longitude), str(row.gbif_key))
        placed = False
        for cluster in clusters:
            if _complete_link_eligible(cluster, point, radius_km):
                cluster.append(point)
                placed = True
                break
        if not placed:
            clusters.append([point])
    return [Cluster(tuple(cluster)) for cluster in clusters]


def _has_forbidden_geospatial_issue(record: dict[str, object]) -> bool:
    issues = record.get("issues") or []
    return bool(GEOSPATIAL_ISSUES.intersection(str(issue) for issue in issues))


def normalize_record(record: dict[str, object], species_name: str) -> dict[str, object] | None:
    if str(record.get("species") or "") != species_name:
        return None
    if str(record.get("occurrenceStatus") or "PRESENT").upper() != "PRESENT":
        return None
    if _has_forbidden_geospatial_issue(record):
        return None
    try:
        lat = float(record["decimalLatitude"])
        lon = float(record["decimalLongitude"])
        year = int(record["year"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 2000 <= year <= 2025):
        return None
    uncertainty = record.get("coordinateUncertaintyInMeters")
    if uncertainty is None:
        return None
    try:
        uncertainty_m = float(uncertainty)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(uncertainty_m) or uncertainty_m < 0 or uncertainty_m > 1000:
        return None
    return {
        "gbif_key": str(record.get("key") or record.get("occurrenceID") or ""),
        "latitude": lat,
        "longitude": lon,
        "year": year,
        "coordinate_uncertainty_m": uncertainty_m,
    }


def fetch_gbif_species(
    species_name: str,
    *,
    session: requests.Session | None = None,
    page_size: int = 300,
    maximum_records: int = 10000,
    pause_seconds: float = 0.05,
) -> tuple[pd.DataFrame, dict[str, object]]:
    client = session or requests.Session()
    rows: list[dict[str, object]] = []
    offset = 0
    pages = 0
    raw_seen = 0
    while offset < maximum_records:
        limit = min(page_size, maximum_records - offset)
        params = {
            "scientificName": species_name,
            "country": "JP",
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "year": "2000,2025",
            "limit": limit,
            "offset": offset,
        }
        response = client.get(GBIF_ENDPOINT, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("results") or []
        pages += 1
        raw_seen += len(batch)
        for record in batch:
            normalized = normalize_record(record, species_name)
            if normalized is not None:
                rows.append(normalized)
        if payload.get("endOfRecords", False) or not batch:
            break
        offset += len(batch)
        if len(batch) < limit:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    frame = pd.DataFrame(rows, columns=["gbif_key", "latitude", "longitude", "year", "coordinate_uncertainty_m"])
    audit = {
        "species_binomial": species_name,
        "raw_api_records_seen": int(raw_seen),
        "eligible_records": int(len(frame)),
        "pages": int(pages),
        "maximum_records_reached": bool(raw_seen >= maximum_records),
    }
    return frame, audit


def _dedupe_period(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return (
        frame.sort_values(["latitude", "longitude", "year", "gbif_key"], kind="mergesort")
        .drop_duplicates(subset=["latitude", "longitude"], keep="first")
        .reset_index(drop=True)
    )


def evaluate_species(species_name: str, records: pd.DataFrame, *, cluster_radius_km: float = 0.5) -> dict[str, object]:
    historical = _dedupe_period(records.loc[records["year"].between(2000, 2020)].copy())
    recent = _dedupe_period(records.loc[records["year"].between(2021, 2025)].copy())
    historical_clusters = deterministic_complete_link_greedy(historical, cluster_radius_km)
    recent_clusters = deterministic_complete_link_greedy(recent, cluster_radius_km)

    novel_distances: list[float] = []
    reobserved = 0
    if historical_clusters:
        for recent_cluster in recent_clusters:
            nearest = min(cluster_min_distance_km(recent_cluster, old_cluster) for old_cluster in historical_clusters)
            if nearest <= 0.5 + 1e-12:
                reobserved += 1
            else:
                novel_distances.append(float(nearest))

    novel_count = len(novel_distances) if historical_clusters else len(recent_clusters)
    within_2 = int(sum(distance <= 2.0 + 1e-12 for distance in novel_distances)) if historical_clusters else 0
    within_5 = int(sum(distance <= 5.0 + 1e-12 for distance in novel_distances)) if historical_clusters else 0
    detached_gt5 = int(sum(distance > 5.0 + 1e-12 for distance in novel_distances)) if historical_clusters else 0
    return {
        "species_binomial": species_name,
        "eligible_records": int(len(records)),
        "historical_unique_coordinates": int(len(historical)),
        "recent_unique_coordinates": int(len(recent)),
        "historical_clusters": int(len(historical_clusters)),
        "recent_clusters": int(len(recent_clusters)),
        "recent_reobserved_clusters_le_0_5km": int(reobserved),
        "novel_recent_clusters": int(novel_count),
        "novel_recent_within_2km": int(within_2),
        "novel_recent_within_5km": int(within_5),
        "novel_recent_detached_gt_5km": int(detached_gt5),
        "fraction_novel_recent_within_2km": float(within_2 / novel_count) if historical_clusters and novel_count else None,
        "fraction_novel_recent_within_5km": float(within_5 / novel_count) if historical_clusters and novel_count else None,
        "nearest_historical_km_median_for_novel_recent": float(np.median(novel_distances)) if novel_distances else None,
        "nearest_historical_km_max_for_novel_recent": float(np.max(novel_distances)) if novel_distances else None,
        "sentinel_no_historical_anchor": bool(not historical_clusters and bool(recent_clusters)),
        "temporally_evaluable": bool(historical_clusters and recent_clusters),
    }


def summarize(species_rows: list[dict[str, object]], audits: list[dict[str, object]]) -> dict[str, object]:
    evaluable = [row for row in species_rows if row["temporally_evaluable"]]
    with_novel = [row for row in evaluable if int(row["novel_recent_clusters"]) > 0]
    novel_total = sum(int(row["novel_recent_clusters"]) for row in with_novel)
    within_2_total = sum(int(row["novel_recent_within_2km"]) for row in with_novel)
    within_5_total = sum(int(row["novel_recent_within_5km"]) for row in with_novel)
    species_2 = [float(row["fraction_novel_recent_within_2km"]) for row in with_novel if row["fraction_novel_recent_within_2km"] is not None]
    species_5 = [float(row["fraction_novel_recent_within_5km"]) for row in with_novel if row["fraction_novel_recent_within_5km"] is not None]
    return {
        "schema_version": "public-japan-cirsium-temporal-anchor-benchmark-result-v1",
        "status": "PUBLIC_RETROSPECTIVE_DEVELOPMENT_COMPLETE",
        "field_outcomes_used": False,
        "private_localities_used": False,
        "validated_product_changed": False,
        "declared_species": int(len(species_rows)),
        "species_with_any_eligible_records": int(sum(int(row["eligible_records"]) > 0 for row in species_rows)),
        "temporally_evaluable_species": int(len(evaluable)),
        "species_with_novel_recent_clusters": int(len(with_novel)),
        "sentinel_species_count": int(sum(bool(row["sentinel_no_historical_anchor"]) for row in species_rows)),
        "novel_recent_cluster_count": int(novel_total),
        "pooled_fraction_novel_recent_within_2km": float(within_2_total / novel_total) if novel_total else None,
        "pooled_fraction_novel_recent_within_5km": float(within_5_total / novel_total) if novel_total else None,
        "species_level_fraction_within_2km_median": float(np.median(species_2)) if species_2 else None,
        "species_level_fraction_within_5km_median": float(np.median(species_5)) if species_5 else None,
        "gbif_raw_records_seen": int(sum(int(audit["raw_api_records_seen"]) for audit in audits)),
        "gbif_eligible_records": int(sum(int(audit["eligible_records"]) for audit in audits)),
        "interpretation_boundary": "Tests public temporal proximity of later occurrence clusters to historical clusters in Japan; does not validate structural habitat ranking, occupancy, field efficiency, route optimization, days or budget.",
    }


def run_benchmark(contract_path: Path = DEFAULT_CONTRACT, cohort_path: Path = DEFAULT_COHORT) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract["status"] != "PRE_OUTCOME_PUBLIC_DATA_BENCHMARK_FROZEN":
        raise ValueError("public benchmark contract is not frozen")
    if contract.get("field_outcomes_used") is not False:
        raise ValueError("public benchmark contract cannot use field outcomes")
    cohort = pd.read_csv(cohort_path)
    species = list(dict.fromkeys(cohort[contract["species_column"]].astype(str).tolist()))
    if len(species) != int(contract["species_count"]):
        raise ValueError(f"frozen species count mismatch: expected {contract['species_count']}, got {len(species)}")

    rows: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for name in species:
        records, audit = fetch_gbif_species(
            name,
            page_size=int(contract["gbif_query"]["page_size"]),
            maximum_records=int(contract["gbif_query"]["maximum_records_per_species"]),
        )
        rows.append(evaluate_species(name, records, cluster_radius_km=float(contract["cluster_rule"]["maximum_within_cluster_distance_km"])))
        audits.append(audit)
    result = pd.DataFrame(rows)
    audit_frame = pd.DataFrame(audits)
    summary = summarize(rows, audits)
    return result, summary, audit_frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    species_table, summary, audit = run_benchmark(args.contract, args.cohort)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    species_table.to_csv(args.out_dir / "species_temporal_anchor_metrics.csv", index=False)
    audit.to_csv(args.out_dir / "gbif_fetch_audit.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
