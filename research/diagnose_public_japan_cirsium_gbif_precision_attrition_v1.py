#!/usr/bin/env python3
"""Diagnose public GBIF precision attrition for the frozen 13 Japan Cirsium species.

This is a post-benchmark aggregate diagnostic only. It never writes occurrence
coordinates and it does not loosen the parent <=1 km declared-uncertainty rule.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "validation" / "public_japan_cirsium_gbif_precision_attrition_diagnostic_v1.json"
DEFAULT_COHORT = ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"
GBIF_ENDPOINT = "https://api.gbif.org/v1/occurrence/search"

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

ATTRITION_ORDER = [
    "exact_species_field_mismatch",
    "invalid_or_missing_coordinate_or_year",
    "forbidden_geospatial_issue",
    "missing_declared_coordinate_uncertainty",
    "invalid_declared_coordinate_uncertainty",
    "declared_coordinate_uncertainty_gt_1000m",
    "eligible_declared_uncertainty_le_1000m",
]


def classify_record(record: dict[str, object], species_name: str) -> str:
    if str(record.get("species") or "") != species_name:
        return "exact_species_field_mismatch"
    try:
        lat = float(record["decimalLatitude"])
        lon = float(record["decimalLongitude"])
        year = int(record["year"])
    except (KeyError, TypeError, ValueError):
        return "invalid_or_missing_coordinate_or_year"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 2000 <= year <= 2025):
        return "invalid_or_missing_coordinate_or_year"
    issues = {str(issue) for issue in (record.get("issues") or [])}
    if issues.intersection(FORBIDDEN_GEOSPATIAL_ISSUES):
        return "forbidden_geospatial_issue"
    uncertainty = record.get("coordinateUncertaintyInMeters")
    if uncertainty in (None, ""):
        return "missing_declared_coordinate_uncertainty"
    try:
        value = float(uncertainty)
    except (TypeError, ValueError):
        return "invalid_declared_coordinate_uncertainty"
    if value < 0 or value != value or value == float("inf") or value == float("-inf"):
        return "invalid_declared_coordinate_uncertainty"
    if value > 1000:
        return "declared_coordinate_uncertainty_gt_1000m"
    return "eligible_declared_uncertainty_le_1000m"


def fetch_raw_species(
    species_name: str,
    *,
    page_size: int = 300,
    maximum_records: int = 10000,
    session: requests.Session | None = None,
    pause_seconds: float = 0.05,
) -> list[dict[str, object]]:
    client = session or requests.Session()
    results: list[dict[str, object]] = []
    offset = 0
    while offset < maximum_records:
        limit = min(page_size, maximum_records - offset)
        response = client.get(
            GBIF_ENDPOINT,
            params={
                "scientificName": species_name,
                "country": "JP",
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
        results.extend(batch)
        if payload.get("endOfRecords", False) or not batch or len(batch) < limit:
            break
        offset += len(batch)
        if pause_seconds:
            time.sleep(pause_seconds)
    return results


def diagnose_species(species_name: str, raw: list[dict[str, object]]) -> dict[str, object]:
    classes = Counter(classify_record(record, species_name) for record in raw)
    historical_eligible = 0
    recent_eligible = 0
    for record in raw:
        if classify_record(record, species_name) != "eligible_declared_uncertainty_le_1000m":
            continue
        year = int(record["year"])
        if 2000 <= year <= 2020:
            historical_eligible += 1
        elif 2021 <= year <= 2025:
            recent_eligible += 1
    row: dict[str, object] = {
        "species_binomial": species_name,
        "raw_records": int(len(raw)),
        **{name: int(classes.get(name, 0)) for name in ATTRITION_ORDER},
        "strict_historical_records": int(historical_eligible),
        "strict_recent_records": int(recent_eligible),
        "strict_both_periods": bool(historical_eligible > 0 and recent_eligible > 0),
    }
    if raw:
        row["fraction_missing_uncertainty"] = float(classes.get("missing_declared_coordinate_uncertainty", 0) / len(raw))
        row["fraction_uncertainty_gt_1000m"] = float(classes.get("declared_coordinate_uncertainty_gt_1000m", 0) / len(raw))
        row["fraction_strict_eligible"] = float(classes.get("eligible_declared_uncertainty_le_1000m", 0) / len(raw))
    else:
        row["fraction_missing_uncertainty"] = None
        row["fraction_uncertainty_gt_1000m"] = None
        row["fraction_strict_eligible"] = None
    return row


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    raw_total = sum(int(row["raw_records"]) for row in rows)
    totals = {name: sum(int(row[name]) for row in rows) for name in ATTRITION_ORDER}
    return {
        "schema_version": "public-japan-cirsium-gbif-precision-attrition-diagnostic-result-v1",
        "status": "POST_TEMPORAL_BENCHMARK_DIAGNOSTIC_COMPLETE",
        "field_outcomes_used": False,
        "private_localities_used": False,
        "parent_precision_rule_changed": False,
        "declared_species": int(len(rows)),
        "raw_records": int(raw_total),
        "attrition_totals": totals,
        "fraction_missing_declared_coordinate_uncertainty": float(totals["missing_declared_coordinate_uncertainty"] / raw_total) if raw_total else None,
        "fraction_declared_uncertainty_gt_1000m": float(totals["declared_coordinate_uncertainty_gt_1000m"] / raw_total) if raw_total else None,
        "fraction_strict_eligible": float(totals["eligible_declared_uncertainty_le_1000m"] / raw_total) if raw_total else None,
        "species_with_strict_historical_records": int(sum(int(row["strict_historical_records"]) > 0 for row in rows)),
        "species_with_strict_recent_records": int(sum(int(row["strict_recent_records"]) > 0 for row in rows)),
        "species_with_both_periods": int(sum(bool(row["strict_both_periods"]) for row in rows)),
        "interpretation_boundary": "Counts aggregate public-record attrition only. Missing uncertainty is not treated as evidence of precise coordinates, and the parent local-recovery benchmark is not recomputed with looser eligibility."
    }


def run(contract_path: Path = DEFAULT_CONTRACT, cohort_path: Path = DEFAULT_COHORT) -> tuple[pd.DataFrame, dict[str, object]]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract["status"] != "POST_TEMPORAL_BENCHMARK_DIAGNOSTIC_FROZEN_BEFORE_EXECUTION":
        raise ValueError("precision attrition diagnostic contract is not frozen")
    cohort = pd.read_csv(cohort_path)
    species = list(dict.fromkeys(cohort["species_binomial"].astype(str).tolist()))
    if len(species) != int(contract["species_count"]):
        raise ValueError("frozen species count mismatch")
    rows = []
    for species_name in species:
        raw = fetch_raw_species(
            species_name,
            page_size=int(contract["gbif_query"]["page_size"]),
            maximum_records=int(contract["gbif_query"]["maximum_records_per_species"]),
        )
        rows.append(diagnose_species(species_name, raw))
    return pd.DataFrame(rows), summarize(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    table, summary = run(args.contract, args.cohort)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "species_attrition.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
