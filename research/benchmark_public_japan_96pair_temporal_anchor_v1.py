#!/usr/bin/env python3
"""Development-only public temporal proximity benchmark on the frozen 96 Japan pairs.

The 96 taxon-region cohort was already consumed by the validated robust-core
confirmation. Here it is reused only to diagnose whether later public occurrence
clusters tend to lie near historical occurrence clusters inside the same fixed
Japanese region. No new independent validation claim is allowed.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "validation" / "public_japan_96pair_temporal_anchor_benchmark_v1.json"
GBIF_ENDPOINT = "https://api.gbif.org/v1/occurrence/search"
EARTH_RADIUS_KM = 6371.0088

FORBIDDEN_GEOSPATIAL_ISSUES = {
    "COUNTRY_COORDINATE_MISMATCH",
    "ZERO_COORDINATE",
    "COORDINATE_INVALID",
    "COORDINATE_OUT_OF_RANGE",
    "PRESUMED_NEGATED_LATITUDE",
    "PRESUMED_NEGATED_LONGITUDE",
    "GEODETIC_DATUM_INVALID",
    "COORDINATE_UNCERTAINTY_METERS_INVALID",
}


def rectangle_wkt(west: float, south: float, east: float, north: float) -> str:
    return f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = p2 - p1
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def complete_link_clusters(frame: pd.DataFrame, radius_km: float = 0.5) -> list[list[tuple[float, float, str]]]:
    if frame.empty:
        return []
    ordered = frame.sort_values(["latitude", "longitude", "gbif_key"], kind="mergesort")
    clusters: list[list[tuple[float, float, str]]] = []
    for row in ordered.itertuples(index=False):
        point = (float(row.latitude), float(row.longitude), str(row.gbif_key))
        for cluster in clusters:
            if all(haversine_km(point[0], point[1], old[0], old[1]) <= radius_km + 1e-12 for old in cluster):
                cluster.append(point)
                break
        else:
            clusters.append([point])
    return clusters


def cluster_min_distance(left: list[tuple[float, float, str]], right: list[tuple[float, float, str]]) -> float:
    return min(haversine_km(a[0], a[1], b[0], b[1]) for a in left for b in right)


def normalize_record(record: dict[str, object], species_key: int) -> dict[str, object] | None:
    try:
        if int(record.get("speciesKey")) != int(species_key):
            return None
    except (TypeError, ValueError):
        return None
    try:
        lat = float(record["decimalLatitude"])
        lon = float(record["decimalLongitude"])
        year = int(record["year"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 2000 <= year <= 2025):
        return None
    issues = {str(issue) for issue in (record.get("issues") or [])}
    if issues.intersection(FORBIDDEN_GEOSPATIAL_ISSUES):
        return None
    uncertainty = record.get("coordinateUncertaintyInMeters")
    if uncertainty in (None, ""):
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
    }


def fetch_pair_records(
    pair: pd.Series,
    *,
    page_size: int = 300,
    maximum_records: int = 10000,
    pause_seconds: float = 0.03,
    session: requests.Session | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    client = session or requests.Session()
    geometry = rectangle_wkt(float(pair.west), float(pair.south), float(pair.east), float(pair.north))
    offset = 0
    raw_seen = 0
    rows: list[dict[str, object]] = []
    pages = 0
    while offset < maximum_records:
        limit = min(page_size, maximum_records - offset)
        response = client.get(
            GBIF_ENDPOINT,
            params={
                "taxonKey": int(pair.speciesKey),
                "geometry": geometry,
                "hasCoordinate": "true",
                "hasGeospatialIssue": "false",
                "occurrenceStatus": "PRESENT",
                "year": "2000,2025",
                "limit": limit,
                "offset": offset,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("results") or []
        pages += 1
        raw_seen += len(batch)
        for record in batch:
            normalized = normalize_record(record, int(pair.speciesKey))
            if normalized is not None:
                rows.append(normalized)
        if payload.get("endOfRecords", False) or not batch or len(batch) < limit:
            break
        offset += len(batch)
        if pause_seconds:
            time.sleep(pause_seconds)
    frame = pd.DataFrame(rows, columns=["gbif_key", "latitude", "longitude", "year"])
    return frame, {
        "pair_id": int(pair.pair_id),
        "species_name": str(pair.scientific_name),
        "region_name": str(pair.region_name),
        "raw_api_records_seen": int(raw_seen),
        "strict_eligible_records": int(len(frame)),
        "pages": int(pages),
        "maximum_records_reached": bool(raw_seen >= maximum_records),
    }


def dedupe_period(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return (
        frame.sort_values(["latitude", "longitude", "year", "gbif_key"], kind="mergesort")
        .drop_duplicates(["latitude", "longitude"], keep="first")
        .reset_index(drop=True)
    )


def evaluate_pair(pair: pd.Series, records: pd.DataFrame) -> dict[str, object]:
    historical = dedupe_period(records.loc[records["year"].between(2000, 2020)].copy())
    recent = dedupe_period(records.loc[records["year"].between(2021, 2025)].copy())
    h_clusters = complete_link_clusters(historical, 0.5)
    r_clusters = complete_link_clusters(recent, 0.5)
    novel_distances: list[float] = []
    reobserved = 0
    if h_clusters:
        for recent_cluster in r_clusters:
            nearest = min(cluster_min_distance(recent_cluster, old) for old in h_clusters)
            if nearest <= 0.5 + 1e-12:
                reobserved += 1
            else:
                novel_distances.append(float(nearest))
    novel_count = len(novel_distances) if h_clusters else len(r_clusters)
    result: dict[str, object] = {
        "pair_id": int(pair.pair_id),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "region_cell_index": int(pair.region_cell_index),
        "species_key": int(pair.speciesKey),
        "scientific_name": str(pair.scientific_name),
        "strict_records": int(len(records)),
        "historical_unique_coordinates": int(len(historical)),
        "recent_unique_coordinates": int(len(recent)),
        "historical_clusters": int(len(h_clusters)),
        "recent_clusters": int(len(r_clusters)),
        "recent_reobserved_clusters_le_0_5km": int(reobserved),
        "novel_recent_clusters": int(novel_count),
        "sentinel_no_historical_anchor": bool(not h_clusters and bool(r_clusters)),
        "temporally_evaluable": bool(h_clusters and r_clusters),
    }
    for radius in (2.0, 5.0, 10.0):
        count = int(sum(distance <= radius + 1e-12 for distance in novel_distances)) if h_clusters else 0
        result[f"novel_recent_within_{int(radius)}km"] = count
        result[f"fraction_novel_recent_within_{int(radius)}km"] = float(count / novel_count) if h_clusters and novel_count else None
    result["nearest_historical_km_median_for_novel_recent"] = float(np.median(novel_distances)) if novel_distances else None
    result["nearest_historical_km_max_for_novel_recent"] = float(np.max(novel_distances)) if novel_distances else None
    return result


def summarize(rows: list[dict[str, object]], audits: list[dict[str, object]]) -> dict[str, object]:
    evaluable = [row for row in rows if row["temporally_evaluable"]]
    novel = [row for row in evaluable if int(row["novel_recent_clusters"]) > 0]
    total_novel = sum(int(row["novel_recent_clusters"]) for row in novel)
    summary: dict[str, object] = {
        "schema_version": "public-japan-96pair-temporal-anchor-benchmark-result-v1",
        "status": "DEVELOPMENT_ONLY_COMPLETE",
        "validated_product_changed": False,
        "new_independent_confirmation_claim": False,
        "declared_pairs": int(len(rows)),
        "pairs_with_any_strict_records": int(sum(int(row["strict_records"]) > 0 for row in rows)),
        "temporally_evaluable_pairs": int(len(evaluable)),
        "pairs_with_novel_recent_clusters": int(len(novel)),
        "sentinel_pairs": int(sum(bool(row["sentinel_no_historical_anchor"]) for row in rows)),
        "novel_recent_cluster_count": int(total_novel),
        "raw_api_records_seen": int(sum(int(audit["raw_api_records_seen"]) for audit in audits)),
        "strict_eligible_records": int(sum(int(audit["strict_eligible_records"]) for audit in audits)),
    }
    for radius in (2, 5, 10):
        numerator = sum(int(row[f"novel_recent_within_{radius}km"]) for row in novel)
        fractions = [float(row[f"fraction_novel_recent_within_{radius}km"]) for row in novel if row[f"fraction_novel_recent_within_{radius}km"] is not None]
        summary[f"pooled_fraction_novel_recent_within_{radius}km"] = float(numerator / total_novel) if total_novel else None
        summary[f"pair_level_fraction_within_{radius}km_median"] = float(np.median(fractions)) if fractions else None
    for group in ("plant", "animal"):
        group_novel = [row for row in novel if row["taxon_group"] == group]
        group_total = sum(int(row["novel_recent_clusters"]) for row in group_novel)
        summary[f"{group}_evaluable_pairs"] = int(sum(row["taxon_group"] == group for row in evaluable))
        summary[f"{group}_novel_recent_clusters"] = int(group_total)
        for radius in (2, 5, 10):
            numerator = sum(int(row[f"novel_recent_within_{radius}km"]) for row in group_novel)
            summary[f"{group}_pooled_fraction_within_{radius}km"] = float(numerator / group_total) if group_total else None
    summary["interpretation_boundary"] = "Already-consumed 96-pair cohort reused for public-data development only; diagnoses occurrence proximity within fixed Japanese regions and cannot independently validate a new local-discovery method."
    return summary


def run(sample_file: Path, contract_path: Path = DEFAULT_CONTRACT) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract["status"] != "DEVELOPMENT_ONLY_FROZEN_BEFORE_TEMPORAL_FETCH":
        raise ValueError("96-pair temporal benchmark contract is not frozen")
    sample = pd.read_csv(sample_file)
    sample = sample.loc[sample["status"].eq("predeclared")].copy()
    if len(sample) != int(contract["cohort_provenance"]["declared_pairs"]):
        raise ValueError(f"expected 96 frozen pairs, got {len(sample)}")
    if sample["scientific_name"].nunique() != int(contract["cohort_provenance"]["unique_taxa"]):
        raise ValueError("frozen cohort unique-taxon count mismatch")
    rows: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for _, pair in sample.sort_values("pair_id").iterrows():
        try:
            records, audit = fetch_pair_records(
                pair,
                page_size=int(contract["gbif_query"]["page_size"]),
                maximum_records=int(contract["gbif_query"]["maximum_records_per_pair"]),
            )
            rows.append(evaluate_pair(pair, records))
            audit["status"] = "ok"
            audits.append(audit)
        except Exception as exc:
            rows.append({
                "pair_id": int(pair.pair_id),
                "taxon_group": str(pair.taxon_group),
                "region_name": str(pair.region_name),
                "region_cell_index": int(pair.region_cell_index),
                "species_key": int(pair.speciesKey),
                "scientific_name": str(pair.scientific_name),
                "strict_records": 0,
                "historical_unique_coordinates": 0,
                "recent_unique_coordinates": 0,
                "historical_clusters": 0,
                "recent_clusters": 0,
                "recent_reobserved_clusters_le_0_5km": 0,
                "novel_recent_clusters": 0,
                "sentinel_no_historical_anchor": False,
                "temporally_evaluable": False,
                "novel_recent_within_2km": 0,
                "fraction_novel_recent_within_2km": None,
                "novel_recent_within_5km": 0,
                "fraction_novel_recent_within_5km": None,
                "novel_recent_within_10km": 0,
                "fraction_novel_recent_within_10km": None,
                "nearest_historical_km_median_for_novel_recent": None,
                "nearest_historical_km_max_for_novel_recent": None,
            })
            audits.append({
                "pair_id": int(pair.pair_id),
                "species_name": str(pair.scientific_name),
                "region_name": str(pair.region_name),
                "raw_api_records_seen": 0,
                "strict_eligible_records": 0,
                "pages": 0,
                "maximum_records_reached": False,
                "status": f"failed:{type(exc).__name__}:{str(exc)[:160]}",
            })
    return pd.DataFrame(rows), summarize(rows, audits), pd.DataFrame(audits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-file", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    table, summary, audit = run(args.sample_file, args.contract)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "pair_temporal_anchor_metrics.csv", index=False)
    audit.to_csv(args.out_dir / "gbif_fetch_audit.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
