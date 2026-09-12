#!/usr/bin/env python3
"""Uncertainty/provenance-aware public-safe Cirsium occurrence audit v2.

This v2 does not replace the frozen v1 audit. It refines the sentinel side after
the <=1 km local-anchor gate has failed, distinguishing declared broad coordinate
uncertainty from unknown uncertainty, obscuring, region-only evidence and legacy
context. Exact coordinates are never written.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any

from acsp.sentinel_evidence import SentinelEvidenceCounts, classify_sentinel_evidence
from audit_cirsium_aza3_gbif_occurrences_v1 import (
    MAX_EVENT_YEAR,
    MAX_PRIMARY_UNCERTAINTY_M,
    SERIOUS_GEOSPATIAL_ISSUES,
    build_query_queue,
    fetch_occurrences,
    gbif_taxon_match,
    parse_year,
    spatial_class,
    temporal_class,
    uncertainty_m,
)


def _has_coordinates(record: dict[str, Any]) -> bool:
    return record.get("decimalLatitude") is not None and record.get("decimalLongitude") is not None


def _generalized(record: dict[str, Any]) -> bool:
    return bool(str(record.get("informationWithheld") or "").strip()) or bool(
        str(record.get("dataGeneralizations") or "").strip()
    )


def _serious_issue(record: dict[str, Any]) -> bool:
    return bool({str(x) for x in (record.get("issues") or [])}.intersection(SERIOUS_GEOSPATIAL_ISSUES))


def summarize_v2(species: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter()
    recent_basis = Counter()
    all_basis = Counter()
    declared_uncertainties: list[float] = []
    retained = 0

    for record in records:
        year = parse_year(record)
        tclass = temporal_class(year)
        if tclass == "POST_CUTOFF":
            continue
        retained += 1
        basis = str(record.get("basisOfRecord") or "UNKNOWN")
        all_basis[basis] += 1
        sclass = spatial_class(record)

        if tclass == "RECENT":
            recent_basis[basis] += 1
            if sclass == "EXACT_OR_DECLARED_PRECISE_COORDINATE":
                counts["primary"] += 1
                continue
            if _has_coordinates(record):
                if _serious_issue(record):
                    counts["recent_serious_geospatial_issue_coordinate"] += 1
                    continue
                if _generalized(record) or sclass == "COORDINATE_OBSCURED":
                    counts["recent_obscured_coordinate"] += 1
                    continue
                unc = uncertainty_m(record)
                if unc is None:
                    counts["recent_unknown_uncertainty_coordinate"] += 1
                elif unc > MAX_PRIMARY_UNCERTAINTY_M:
                    counts["recent_declared_uncertainty_coordinate"] += 1
                    declared_uncertainties.append(float(unc))
                else:
                    # A <=1 km coordinate should already have entered the primary
                    # class unless another non-serious source issue prevented it.
                    counts["recent_other_nonprimary_coordinate"] += 1
            elif sclass == "REGION_ONLY":
                counts["recent_region_only"] += 1
            else:
                counts["recent_no_locality"] += 1
        elif tclass in {"LEGACY", "HISTORICAL", "DATE_UNKNOWN"}:
            if sclass != "NO_LOCALITY":
                counts["legacy_or_historical_spatial"] += 1

    evidence = SentinelEvidenceCounts(
        primary_anchor_count=counts["primary"],
        recent_declared_uncertainty_coordinate_count=counts["recent_declared_uncertainty_coordinate"],
        recent_unknown_uncertainty_coordinate_count=(
            counts["recent_unknown_uncertainty_coordinate"]
            + counts["recent_other_nonprimary_coordinate"]
            + counts["recent_serious_geospatial_issue_coordinate"]
        ),
        recent_obscured_coordinate_count=counts["recent_obscured_coordinate"],
        recent_region_only_count=counts["recent_region_only"],
        legacy_or_historical_spatial_count=counts["legacy_or_historical_spatial"],
    )
    gate = classify_sentinel_evidence(evidence)

    def stat(values: list[float], fn) -> float | str:
        return "" if not values else float(fn(values))

    return {
        "species_binomial": species,
        "records_retained_through_2025": retained,
        "primary_anchor_records": counts["primary"],
        "recent_declared_uncertainty_coordinate_records": counts["recent_declared_uncertainty_coordinate"],
        "recent_unknown_uncertainty_coordinate_records": counts["recent_unknown_uncertainty_coordinate"],
        "recent_obscured_coordinate_records": counts["recent_obscured_coordinate"],
        "recent_serious_geospatial_issue_coordinate_records": counts["recent_serious_geospatial_issue_coordinate"],
        "recent_other_nonprimary_coordinate_records": counts["recent_other_nonprimary_coordinate"],
        "recent_region_only_records": counts["recent_region_only"],
        "recent_no_locality_records": counts["recent_no_locality"],
        "legacy_or_historical_spatial_records": counts["legacy_or_historical_spatial"],
        "recent_human_observation_records": recent_basis["HUMAN_OBSERVATION"],
        "recent_preserved_specimen_records": recent_basis["PRESERVED_SPECIMEN"],
        "all_human_observation_records": all_basis["HUMAN_OBSERVATION"],
        "all_preserved_specimen_records": all_basis["PRESERVED_SPECIMEN"],
        "declared_broad_uncertainty_m_min": stat(declared_uncertainties, min),
        "declared_broad_uncertainty_m_median": stat(declared_uncertainties, lambda x: sorted(x)[len(x) // 2]),
        "declared_broad_uncertainty_m_max": stat(declared_uncertainties, max),
        "sentinel_evidence_class": gate.evidence_class,
        "local_kernel_allowed": str(gate.local_kernel_allowed).lower(),
        "uncertainty_kernel_allowed": str(gate.uncertainty_kernel_allowed).lower(),
        "broad_sector_context_available": str(gate.broad_sector_context_available).lower(),
        "public_exact_coordinates_written": "false",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty audit table")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("validation/cirsium_aza3_occurrence_audit_v2"))
    args = parser.parse_args()

    queue = build_query_queue()
    species_names = sorted({row["species_binomial"] for row in queue})
    rows: list[dict[str, Any]] = []
    match_counts = Counter()
    evidence_counts = Counter()

    for index, species in enumerate(species_names, start=1):
        match = gbif_taxon_match(species)
        match_counts[match["classification"]] += 1
        if match["classification"] == "AUTO_EXACT_ACCEPTED":
            summary = summarize_v2(species, fetch_occurrences(match["usage_key"]))
        else:
            summary = {
                "species_binomial": species,
                "records_retained_through_2025": 0,
                "primary_anchor_records": 0,
                "recent_declared_uncertainty_coordinate_records": 0,
                "recent_unknown_uncertainty_coordinate_records": 0,
                "recent_obscured_coordinate_records": 0,
                "recent_serious_geospatial_issue_coordinate_records": 0,
                "recent_other_nonprimary_coordinate_records": 0,
                "recent_region_only_records": 0,
                "recent_no_locality_records": 0,
                "legacy_or_historical_spatial_records": 0,
                "recent_human_observation_records": 0,
                "recent_preserved_specimen_records": 0,
                "all_human_observation_records": 0,
                "all_preserved_specimen_records": 0,
                "declared_broad_uncertainty_m_min": "",
                "declared_broad_uncertainty_m_median": "",
                "declared_broad_uncertainty_m_max": "",
                "sentinel_evidence_class": "TAXON_REVIEW",
                "local_kernel_allowed": "false",
                "uncertainty_kernel_allowed": "false",
                "broad_sector_context_available": "false",
                "public_exact_coordinates_written": "false",
            }
        summary["gbif_taxon_match_classification"] = match["classification"]
        rows.append(summary)
        evidence_counts[summary["sentinel_evidence_class"]] += 1
        print(f"[{index}/{len(species_names)}] {species}: {summary['sentinel_evidence_class']}")
        time.sleep(0.02)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "species_sentinel_evidence_summary_v2.csv", rows)

    lookup = {row["species_binomial"]: row for row in rows}
    slot_rows = [
        {
            "aza3_slot_id": slot["aza3_slot_id"],
            "priority": slot["priority"],
            "species_binomial": slot["species_binomial"],
            "sample_slot": slot["sample_slot"],
            "range_sector": slot["range_sector"],
            "sentinel_evidence_class": lookup[slot["species_binomial"]]["sentinel_evidence_class"],
            "primary_anchor_records": lookup[slot["species_binomial"]]["primary_anchor_records"],
            "recent_declared_uncertainty_coordinate_records": lookup[slot["species_binomial"]]["recent_declared_uncertainty_coordinate_records"],
            "broad_sector_context_available": lookup[slot["species_binomial"]]["broad_sector_context_available"],
            "public_exact_coordinates_written": "false",
        }
        for slot in queue
    ]
    write_csv(args.out_dir / "slot_sentinel_evidence_summary_v2.csv", slot_rows)

    summary = {
        "schema_version": "cirsium-aza3-occurrence-audit-v2",
        "status": "PRE_FIELD_UNCERTAINTY_PROVENANCE_AUDIT",
        "event_date_max": f"{MAX_EVENT_YEAR}-12-31",
        "primary_anchor_max_uncertainty_m": MAX_PRIMARY_UNCERTAINTY_M,
        "species_count": len(species_names),
        "required_tree_slots": len(queue),
        "taxon_match_counts": dict(sorted(match_counts.items())),
        "sentinel_evidence_class_counts": dict(sorted(evidence_counts.items())),
        "public_exact_coordinates_written": False,
        "interpretation": "Raw occurrence abundance is not anchor adequacy. Declared >1 km uncertainty can support a broad uncertainty-aware sentinel kernel, whereas unknown/obscured/region-only evidence remains context only.",
        "field_outcomes_opened": False,
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
