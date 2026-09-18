#!/usr/bin/env python3
"""Retrieve and type pre-2026 GBIF evidence for the frozen aza3 Cirsium slots.

This script is intentionally public-safe. Exact occurrence coordinates are used only
in memory for evidence typing and are never written to the output directory. The
outputs are a query queue, taxon-match audit, species-level evidence counts, and a
slot-level discovery-regime preflight.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

AZA3_REPO = "zuizui0223/aza3"
AZA3_PINNED_COMMIT = "b4ef6b45da377a0be1f0265935aafa20ec411450"
AZA3_BASE = f"https://raw.githubusercontent.com/{AZA3_REPO}/{AZA3_PINNED_COMMIT}/data/planning"
SECTOR_FILES = {
    1: "chapter3_holefill_priority1_sample_sectors_v7.csv",
    2: "chapter3_holefill_priority2_sample_sectors_v7.csv",
    3: "chapter3_holefill_priority3_sample_sectors_v7.csv",
    4: "chapter3_holefill_priority4_sample_sectors_v7.csv",
    5: "chapter3_holefill_priority5_sample_sectors_v7.csv",
    6: "chapter3_holefill_priority6_sample_sectors_v7.csv",
}
GBIF_MATCH = "https://api.gbif.org/v1/species/match"
GBIF_OCC = "https://api.gbif.org/v1/occurrence/search"
USER_AGENT = "ACSP-Cirsium-aza3-prospective-bridge/1.0"
MAX_EVENT_YEAR = 2025
PRIMARY_MIN_YEAR = 2000
LEGACY_MIN_YEAR = 1950
MAX_PRIMARY_UNCERTAINTY_M = 1000.0
SERIOUS_GEOSPATIAL_ISSUES = {
    "ZERO_COORDINATE",
    "COORDINATE_INVALID",
    "COORDINATE_OUT_OF_RANGE",
    "COUNTRY_COORDINATE_MISMATCH",
    "COORDINATE_REPROJECTION_FAILED",
}


def get_json(url: str, *, retries: int = 4) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (2**attempt))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last}")


def get_text(url: str, *, retries: int = 4) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read().decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (2**attempt))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last}")


def safe_id(species: str) -> str:
    return species.replace(" ", "_").replace(".", "")


def fetch_sector_rows(priority: int) -> list[dict[str, str]]:
    text = get_text(f"{AZA3_BASE}/{SECTOR_FILES[priority]}")
    return list(csv.DictReader(io.StringIO(text)))


def build_query_queue() -> list[dict[str, str]]:
    queue: list[dict[str, str]] = []
    for priority in range(1, 6):
        rows = fetch_sector_rows(priority)
        for row in rows:
            for slot, key in (("A", "sample_A_sector"), ("B", "sample_B_sector")):
                queue.append(
                    {
                        "aza3_slot_id": f"P{priority}_{safe_id(row['species_binomial'])}_{slot}",
                        "priority": f"P{priority}",
                        "species_binomial": row["species_binomial"],
                        "japanese_names": row.get("japanese_names", ""),
                        "sample_slot": slot,
                        "range_sector": row[key],
                        "sector_design": row.get("sector_design", ""),
                        "aza3_source_file": SECTOR_FILES[priority],
                        "aza3_source_commit": AZA3_PINNED_COMMIT,
                    }
                )
    for row in fetch_sector_rows(6):
        queue.append(
            {
                "aza3_slot_id": f"P6_{safe_id(row['species_binomial'])}_OWN",
                "priority": "P6",
                "species_binomial": row["species_binomial"],
                "japanese_names": row.get("japanese_names", ""),
                "sample_slot": "OWN",
                "range_sector": row["own_sample_sector_rule"],
                "sector_design": row.get("sector_design", ""),
                "aza3_source_file": SECTOR_FILES[6],
                "aza3_source_commit": AZA3_PINNED_COMMIT,
            }
        )
    if len(queue) != 228:
        raise AssertionError(f"expected 228 required aza3 slots, got {len(queue)}")
    species = {r["species_binomial"] for r in queue}
    if len(species) != 127:
        # P7 is the 128th core species but has zero required tree slots.
        raise AssertionError(f"expected 127 species represented by required slots, got {len(species)}")
    return queue


def gbif_taxon_match(name: str) -> dict[str, Any]:
    url = GBIF_MATCH + "?" + urllib.parse.urlencode({"name": name, "strict": "true"})
    data = get_json(url)
    canonical = str(data.get("canonicalName") or "")
    status = str(data.get("status") or "")
    match_type = str(data.get("matchType") or "")
    rank = str(data.get("rank") or "")
    usage_key = data.get("usageKey")
    exact_auto = (
        match_type == "EXACT"
        and status == "ACCEPTED"
        and canonical.casefold() == name.casefold()
        and usage_key is not None
    )
    if exact_auto:
        classification = "AUTO_EXACT_ACCEPTED"
    elif match_type == "EXACT" and usage_key is not None:
        classification = "EXACT_MATCH_REVIEW_REQUIRED"
    elif usage_key is not None:
        classification = "NONEXACT_MATCH_REVIEW_REQUIRED"
    else:
        classification = "NO_GBIF_MATCH"
    return {
        "query_name": name,
        "classification": classification,
        "match_type": match_type,
        "status": status,
        "rank": rank,
        "canonical_name": canonical,
        "scientific_name": str(data.get("scientificName") or ""),
        "accepted_scientific_name": str(data.get("acceptedScientificName") or ""),
        "usage_key": "" if usage_key is None else str(usage_key),
        "confidence": str(data.get("confidence") or ""),
        "note": str(data.get("note") or ""),
    }


def fetch_occurrences(taxon_key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    limit = 300
    offset = 0
    while True:
        params = {
            "taxon_key": taxon_key,
            "country": "JP",
            "occurrence_status": "PRESENT",
            "limit": limit,
            "offset": offset,
        }
        # GBIF accepts camelCase public parameters; keep a fallback below if a
        # deployment rejects the snake_case aliases emitted by urlencode here.
        query = urllib.parse.urlencode(params)
        try:
            page = get_json(GBIF_OCC + "?" + query)
        except RuntimeError:
            query = urllib.parse.urlencode(
                {
                    "taxonKey": taxon_key,
                    "country": "JP",
                    "occurrenceStatus": "PRESENT",
                    "limit": limit,
                    "offset": offset,
                }
            )
            page = get_json(GBIF_OCC + "?" + query)
        batch = list(page.get("results") or [])
        rows.extend(batch)
        if page.get("endOfRecords") is True or not batch:
            break
        offset += len(batch)
        if offset >= int(page.get("count") or 0):
            break
        if offset > 100000:
            raise RuntimeError(f"unexpectedly large GBIF result set for taxon key {taxon_key}")
        time.sleep(0.03)
    return rows


def parse_year(record: dict[str, Any]) -> int | None:
    raw = record.get("year")
    try:
        if raw is not None and str(raw).strip():
            year = int(raw)
            if 1000 <= year <= 9999:
                return year
    except (TypeError, ValueError):
        pass
    event = str(record.get("eventDate") or "")
    if len(event) >= 4 and event[:4].isdigit():
        year = int(event[:4])
        if 1000 <= year <= 9999:
            return year
    return None


def temporal_class(year: int | None) -> str:
    if year is None:
        return "DATE_UNKNOWN"
    if PRIMARY_MIN_YEAR <= year <= MAX_EVENT_YEAR:
        return "RECENT"
    if LEGACY_MIN_YEAR <= year < PRIMARY_MIN_YEAR:
        return "LEGACY"
    if year < LEGACY_MIN_YEAR:
        return "HISTORICAL"
    return "POST_CUTOFF"


def uncertainty_m(record: dict[str, Any]) -> float | None:
    raw = record.get("coordinateUncertaintyInMeters")
    try:
        if raw is None or str(raw).strip() == "":
            return None
        value = float(raw)
        if math.isfinite(value) and value >= 0:
            return value
    except (TypeError, ValueError):
        return None
    return None


def spatial_class(record: dict[str, Any]) -> str:
    generalized = bool(str(record.get("informationWithheld") or "").strip()) or bool(
        str(record.get("dataGeneralizations") or "").strip()
    )
    lat = record.get("decimalLatitude")
    lon = record.get("decimalLongitude")
    if lat is None or lon is None:
        if any(str(record.get(k) or "").strip() for k in ("stateProvince", "county", "municipality", "locality", "island", "islandGroup")):
            return "REGION_ONLY"
        return "NO_LOCALITY"
    if generalized:
        return "COORDINATE_OBSCURED"
    issues = {str(x) for x in (record.get("issues") or [])}
    if issues.intersection(SERIOUS_GEOSPATIAL_ISSUES):
        return "COORDINATE_UNCERTAIN"
    unc = uncertainty_m(record)
    if unc is not None and unc <= MAX_PRIMARY_UNCERTAINTY_M:
        return "EXACT_OR_DECLARED_PRECISE_COORDINATE"
    return "COORDINATE_UNCERTAIN"


def summarize_occurrences(species: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    spatial = Counter()
    temporal = Counter()
    basis = Counter()
    joint = Counter()
    years: list[int] = []
    primary_coordinate_pairs: set[tuple[float, float]] = set()
    legacy_coordinate_pairs: set[tuple[float, float]] = set()
    retained_records = 0
    post_cutoff = 0
    for record in records:
        year = parse_year(record)
        tclass = temporal_class(year)
        if tclass == "POST_CUTOFF":
            post_cutoff += 1
            continue
        retained_records += 1
        sclass = spatial_class(record)
        spatial[sclass] += 1
        temporal[tclass] += 1
        basis[str(record.get("basisOfRecord") or "UNKNOWN")] += 1
        joint[(sclass, tclass)] += 1
        if year is not None:
            years.append(year)
        if sclass == "EXACT_OR_DECLARED_PRECISE_COORDINATE" and tclass in {"RECENT", "LEGACY"}:
            try:
                pair = (round(float(record["decimalLatitude"]), 6), round(float(record["decimalLongitude"]), 6))
            except (TypeError, ValueError, KeyError):
                pair = None
            if pair is not None:
                if tclass == "RECENT":
                    primary_coordinate_pairs.add(pair)
                else:
                    legacy_coordinate_pairs.add(pair)
    recent_primary = joint[("EXACT_OR_DECLARED_PRECISE_COORDINATE", "RECENT")]
    legacy_precise = joint[("EXACT_OR_DECLARED_PRECISE_COORDINATE", "LEGACY")]
    if recent_primary > 0:
        mode = "LOCAL_CONTINUATION_INPUT_AVAILABLE"
    elif legacy_precise > 0:
        mode = "SENTINEL_OR_ABSTAIN_WITH_LEGACY_CONTEXT"
    elif retained_records > 0:
        mode = "SENTINEL_OR_ABSTAIN_NO_PRIMARY_ANCHOR"
    else:
        mode = "SENTINEL_OR_ABSTAIN_ZERO_GBIF_RECORDS"
    return {
        "species_binomial": species,
        "gbif_records_retrieved_all_years": len(records),
        "records_retained_through_2025": retained_records,
        "records_excluded_post_2025": post_cutoff,
        "recent_primary_anchor_records": recent_primary,
        "recent_primary_unique_coordinate_pairs": len(primary_coordinate_pairs),
        "legacy_precise_records": legacy_precise,
        "legacy_unique_coordinate_pairs": len(legacy_coordinate_pairs),
        "historical_records": temporal["HISTORICAL"],
        "date_unknown_records": temporal["DATE_UNKNOWN"],
        "coordinate_uncertain_records": spatial["COORDINATE_UNCERTAIN"],
        "coordinate_obscured_records": spatial["COORDINATE_OBSCURED"],
        "region_only_records": spatial["REGION_ONLY"],
        "no_locality_records": spatial["NO_LOCALITY"],
        "earliest_retained_year": "" if not years else min(years),
        "latest_retained_year": "" if not years else max(years),
        "basis_of_record_counts_json": json.dumps(dict(sorted(basis.items())), ensure_ascii=False, sort_keys=True),
        "preflight_regime": mode,
        "public_exact_coordinates_written": "false",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise AssertionError(f"cannot write empty table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("validation/cirsium_aza3_occurrence_audit_v1"))
    args = parser.parse_args()

    queue = build_query_queue()
    species_names = sorted({r["species_binomial"] for r in queue})
    matches: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    summary_by_species: dict[str, dict[str, Any]] = {}

    for index, species in enumerate(species_names, start=1):
        match = gbif_taxon_match(species)
        matches.append(match)
        if match["classification"] == "AUTO_EXACT_ACCEPTED":
            records = fetch_occurrences(match["usage_key"])
            summary = summarize_occurrences(species, records)
        else:
            summary = {
                "species_binomial": species,
                "gbif_records_retrieved_all_years": 0,
                "records_retained_through_2025": 0,
                "records_excluded_post_2025": 0,
                "recent_primary_anchor_records": 0,
                "recent_primary_unique_coordinate_pairs": 0,
                "legacy_precise_records": 0,
                "legacy_unique_coordinate_pairs": 0,
                "historical_records": 0,
                "date_unknown_records": 0,
                "coordinate_uncertain_records": 0,
                "coordinate_obscured_records": 0,
                "region_only_records": 0,
                "no_locality_records": 0,
                "earliest_retained_year": "",
                "latest_retained_year": "",
                "basis_of_record_counts_json": "{}",
                "preflight_regime": "TAXON_MATCH_REVIEW_BEFORE_OCCURRENCE_QUERY",
                "public_exact_coordinates_written": "false",
            }
        summary["gbif_taxon_match_classification"] = match["classification"]
        summaries.append(summary)
        summary_by_species[species] = summary
        print(f"[{index}/{len(species_names)}] {species}: {match['classification']} -> {summary['preflight_regime']}")
        time.sleep(0.02)

    slot_rows: list[dict[str, Any]] = []
    for row in queue:
        s = summary_by_species[row["species_binomial"]]
        slot_rows.append(
            {
                **row,
                "gbif_taxon_match_classification": s["gbif_taxon_match_classification"],
                "records_retained_through_2025": s["records_retained_through_2025"],
                "recent_primary_anchor_records": s["recent_primary_anchor_records"],
                "recent_primary_unique_coordinate_pairs": s["recent_primary_unique_coordinate_pairs"],
                "legacy_precise_records": s["legacy_precise_records"],
                "coordinate_uncertain_records": s["coordinate_uncertain_records"],
                "coordinate_obscured_records": s["coordinate_obscured_records"],
                "region_only_records": s["region_only_records"],
                "occurrence_preflight_regime": s["preflight_regime"],
                "candidate_patch_status": "NOT_BUILT_PENDING_STRUCTURAL_GRAPH_V1",
                "public_exact_coordinates_written": "false",
            }
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "aza3_required_slot_occurrence_query_queue.csv", queue)
    write_csv(args.out_dir / "gbif_taxon_match_audit.csv", matches)
    write_csv(args.out_dir / "species_occurrence_evidence_summary.csv", summaries)
    write_csv(args.out_dir / "slot_occurrence_preflight.csv", slot_rows)

    match_counts = Counter(r["classification"] for r in matches)
    regime_species = Counter(r["preflight_regime"] for r in summaries)
    regime_slots = Counter(r["occurrence_preflight_regime"] for r in slot_rows)
    result = {
        "schema_version": "cirsium-aza3-occurrence-audit-v1",
        "aza3_source_repository": AZA3_REPO,
        "aza3_source_commit": AZA3_PINNED_COMMIT,
        "required_tree_slots": len(queue),
        "unique_required_slot_species": len(species_names),
        "p7_zero-required-slot_species_not_queried_here": 1,
        "event_date_max": "2025-12-31",
        "primary_anchor_event_years": "2000-2025",
        "primary_anchor_max_declared_uncertainty_m": MAX_PRIMARY_UNCERTAINTY_M,
        "gbif_taxon_match_counts": dict(sorted(match_counts.items())),
        "species_preflight_regime_counts": dict(sorted(regime_species.items())),
        "slot_preflight_regime_counts": dict(sorted(regime_slots.items())),
        "species_with_primary_anchor_input": sum(r["recent_primary_anchor_records"] > 0 for r in summaries),
        "species_with_legacy_only_or_nonprimary_context": sum(
            r["recent_primary_anchor_records"] == 0 and r["records_retained_through_2025"] > 0 for r in summaries
        ),
        "species_with_zero_retained_records_after_exact_match": sum(
            r["gbif_taxon_match_classification"] == "AUTO_EXACT_ACCEPTED" and r["records_retained_through_2025"] == 0
            for r in summaries
        ),
        "species_requiring_taxon_match_review": sum(r["gbif_taxon_match_classification"] != "AUTO_EXACT_ACCEPTED" for r in summaries),
        "public_exact_coordinates_written": False,
        "candidate_patches_built": False,
        "next_gate": "Resolve taxon-match reviews, then build frozen ecological structural candidate graphs/patches under ACSP issue #192 before prospective field outcome inspection.",
    }
    (args.out_dir / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
