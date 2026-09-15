#!/usr/bin/env python3
"""Fast public-safe preflight for primary Cirsium occurrence-anchor availability.

Unlike the exhaustive occurrence audit, this script stops scanning once it can
establish whether at least one frozen-rule primary anchor exists. It writes no
coordinates and does not replace the exhaustive audit.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from audit_cirsium_aza3_gbif_occurrences_v1 import (
    GBIF_OCC,
    MAX_PRIMARY_UNCERTAINTY_M,
    build_query_queue,
    gbif_taxon_match,
    get_json,
    spatial_class,
)


def search_page(taxon_key: str, year_range: str, offset: int = 0, limit: int = 300) -> dict[str, Any]:
    params = {
        "taxonKey": taxon_key,
        "country": "JP",
        "occurrenceStatus": "PRESENT",
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "year": year_range,
        "limit": limit,
        "offset": offset,
    }
    return get_json(GBIF_OCC + "?" + urllib.parse.urlencode(params))


def has_eligible_precise_record(taxon_key: str, year_range: str, max_pages: int) -> tuple[bool, int, int, int]:
    inspected = 0
    precise_found = 0
    provider_count = 0
    for page_no in range(max_pages):
        page = search_page(taxon_key, year_range, offset=page_no * 300)
        provider_count = int(page.get("count") or 0)
        batch = list(page.get("results") or [])
        inspected += len(batch)
        for record in batch:
            if spatial_class(record) == "EXACT_OR_DECLARED_PRECISE_COORDINATE":
                precise_found += 1
                return True, inspected, precise_found, provider_count
        if page.get("endOfRecords") is True or not batch:
            break
        time.sleep(0.02)
    return False, inspected, precise_found, provider_count


def one_species(species: str) -> dict[str, Any]:
    match = gbif_taxon_match(species)
    out: dict[str, Any] = {
        "species_binomial": species,
        "gbif_taxon_match_classification": match["classification"],
        "gbif_usage_key": match["usage_key"],
        "recent_georeferenced_provider_count": 0,
        "recent_records_scanned": 0,
        "primary_anchor_available": "false",
        "legacy_georeferenced_provider_count": 0,
        "legacy_records_scanned": 0,
        "legacy_precise_anchor_available": "false",
        "preflight_regime": "TAXON_MATCH_REVIEW_BEFORE_OCCURRENCE_QUERY",
        "public_exact_coordinates_written": "false",
    }
    if match["classification"] != "AUTO_EXACT_ACCEPTED":
        return out
    primary, scanned, _, total = has_eligible_precise_record(match["usage_key"], "2000,2025", max_pages=5)
    out["recent_georeferenced_provider_count"] = total
    out["recent_records_scanned"] = scanned
    out["primary_anchor_available"] = "true" if primary else "false"
    if primary:
        out["preflight_regime"] = "LOCAL_CONTINUATION_INPUT_AVAILABLE"
        return out
    legacy, scanned_l, _, total_l = has_eligible_precise_record(match["usage_key"], "1950,1999", max_pages=3)
    out["legacy_georeferenced_provider_count"] = total_l
    out["legacy_records_scanned"] = scanned_l
    out["legacy_precise_anchor_available"] = "true" if legacy else "false"
    if legacy:
        out["preflight_regime"] = "SENTINEL_OR_ABSTAIN_WITH_LEGACY_CONTEXT"
    elif total > 0 or total_l > 0:
        out["preflight_regime"] = "SENTINEL_OR_ABSTAIN_NO_PRIMARY_ANCHOR"
    else:
        out["preflight_regime"] = "SENTINEL_OR_ABSTAIN_ZERO_GEOREFERENCED_RECORDS"
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("validation/cirsium_aza3_anchor_preflight_v1"))
    args = parser.parse_args()
    queue = build_query_queue()
    species = sorted({r["species_binomial"] for r in queue})
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(one_species, name): name for name in species}
        for future in as_completed(futures):
            name = futures[future]
            result = future.result()
            results.append(result)
            print(name, result["preflight_regime"])
    results.sort(key=lambda r: r["species_binomial"])
    by_species = {r["species_binomial"]: r for r in results}
    slot_rows: list[dict[str, Any]] = []
    for slot in queue:
        r = by_species[slot["species_binomial"]]
        slot_rows.append(
            {
                "aza3_slot_id": slot["aza3_slot_id"],
                "priority": slot["priority"],
                "species_binomial": slot["species_binomial"],
                "sample_slot": slot["sample_slot"],
                "range_sector": slot["range_sector"],
                "gbif_taxon_match_classification": r["gbif_taxon_match_classification"],
                "primary_anchor_available": r["primary_anchor_available"],
                "legacy_precise_anchor_available": r["legacy_precise_anchor_available"],
                "preflight_regime": r["preflight_regime"],
                "candidate_patch_status": "NOT_BUILT_PENDING_STRUCTURAL_SELECTOR",
                "public_exact_coordinates_written": "false",
            }
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "species_anchor_availability.csv", results)
    write_csv(args.out_dir / "slot_anchor_preflight.csv", slot_rows)
    regimes_species = Counter(r["preflight_regime"] for r in results)
    regimes_slots = Counter(r["preflight_regime"] for r in slot_rows)
    summary = {
        "schema_version": "cirsium-aza3-anchor-preflight-v1",
        "scientific_role": "fast_anchor_availability_preflight_not_exhaustive_occurrence_audit",
        "unique_required_slot_species": len(species),
        "required_tree_slots": len(queue),
        "primary_anchor_uncertainty_rule_m": MAX_PRIMARY_UNCERTAINTY_M,
        "primary_anchor_years": "2000-2025",
        "legacy_sensitivity_years": "1950-1999",
        "species_regime_counts": dict(sorted(regimes_species.items())),
        "slot_regime_counts": dict(sorted(regimes_slots.items())),
        "species_primary_anchor_available": sum(r["primary_anchor_available"] == "true" for r in results),
        "slots_primary_anchor_available": sum(r["primary_anchor_available"] == "true" for r in slot_rows),
        "species_taxon_match_review_required": sum(r["gbif_taxon_match_classification"] != "AUTO_EXACT_ACCEPTED" for r in results),
        "public_exact_coordinates_written": False,
        "next_gate": "Use this only to assign preliminary local-vs-sentinel regimes; exhaustive audit and structural candidate generation remain required before field use."
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
