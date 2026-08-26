#!/usr/bin/env python3
"""Historical-only discovery wrapper for the prospective observability freeze.

This module is a pre-identity boundary hardening of the issue #163 freeze.  It
keeps the frozen protocol, exclusions, identity hash, country declaration,
score, and output schema from ``predeclare_country_frame_observability_confirmation``
but also bounds the *discovery species facet* to 1900--2020.  Therefore neither
candidate-pool membership nor generic record-count strata can depend on records
from the 2021--2025 held-out interval.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from acsp.benchmarking import get_json
from benchmark_general_random_taxa_regions import (
    GBIF_SEARCH,
    _species_metadata,
    rectangle_wkt,
)
import predeclare_country_frame_observability_confirmation as base

DISCOVERY_YEARS = tuple(int(x) for x in base.HISTORICAL_YEARS)
BOUNDARY_CORRECTION_ID = "historical_discovery_species_facets_1900_2020_v1"


def historical_taxon_frame(
    bounds: tuple[float, float, float, float],
    kingdom_key: int,
    facet_limit: int,
    minimum_records: int,
) -> pd.DataFrame:
    """Build the generic discovery frame using 1900--2020 records only."""
    start, end = DISCOVERY_YEARS
    payload = get_json(
        GBIF_SEARCH,
        {
            "kingdomKey": int(kingdom_key),
            "geometry": rectangle_wkt(bounds),
            "year": f"{start},{end}",
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "limit": 0,
            "facet": "speciesKey",
            "facetLimit": int(facet_limit),
            "facetMincount": int(minimum_records),
        },
    )
    counts = payload.get("facets", [{}])[0].get("counts", [])

    def resolve(item: dict[str, Any]) -> dict[str, Any] | None:
        key = int(item["name"])
        metadata = _species_metadata(key)
        if metadata is None:
            return None
        if metadata.get("rank") != "SPECIES" or not metadata.get("scientificName"):
            return None
        return {
            "speciesKey": key,
            "scientific_name": metadata["scientificName"],
            "coordinate_records": int(item["count"]),
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        rows = list(executor.map(resolve, counts))
    return pd.DataFrame([row for row in rows if row is not None])


def _abort_manifest(exc: base.FreezeAborted, audit: pd.DataFrame) -> dict[str, object]:
    return {
        "status": "observability_confirmation_freeze_aborted_before_complete_cohort",
        "protocol_fingerprint": base.EXPECTED_PROTOCOL_FINGERPRINT,
        "issue": 163,
        "boundary_correction_id": BOUNDARY_CORRECTION_ID,
        "discovery_species_facet_years": list(DISCOVERY_YEARS),
        "discovery_species_facets_include_heldout_years": False,
        "attempt_rows": int(len(audit)),
        "recent_outcomes_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "replacement_after_freeze_allowed": False,
        "abort_reason": str(exc),
    }


def freeze(output: Path) -> dict[str, object]:
    """Freeze the same preregistered cohort with historical-only discovery facets."""
    cfg = base.protocol()
    if DISCOVERY_YEARS != tuple(int(x) for x in cfg["country_declaration"]["historical_years"]):
        raise ValueError("historical discovery years drift from frozen historical window")

    output.mkdir(parents=True, exist_ok=True)
    try:
        selected, audit = base.select_observability_frames(frame_provider=historical_taxon_frame)
    except base.FreezeAborted as exc:
        audit = pd.DataFrame(exc.audit_rows)
        audit_path = output / "pre_freeze_declaration_attempts.csv"
        audit.to_csv(audit_path, index=False)
        manifest = _abort_manifest(exc, audit)
        (output / "cohort_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        raise

    selected_path = output / "predeclared_observability_frames.csv"
    audit_path = output / "pre_freeze_declaration_attempts.csv"
    selected.to_csv(selected_path, index=False)
    audit.to_csv(audit_path, index=False)
    manifest = {
        "status": "observability_confirmation_96_frames_frozen_before_heldout",
        "protocol_fingerprint": base.EXPECTED_PROTOCOL_FINGERPRINT,
        "issue": 163,
        "boundary_correction_id": BOUNDARY_CORRECTION_ID,
        "discovery_species_facet_years": list(DISCOVERY_YEARS),
        "discovery_species_facets_include_heldout_years": False,
        "frozen_frames": int(len(selected)),
        "unique_species_keys": int(selected["speciesKey"].nunique()),
        "taxon_group_counts": {
            str(k): int(v) for k, v in selected["taxon_group"].value_counts().sort_index().items()
        },
        "record_count_stratum_counts_by_group": {
            group: {
                str(int(k)): int(v)
                for k, v in selected[selected["taxon_group"].eq(group)]["record_count_stratum"]
                .astype(int)
                .value_counts()
                .sort_index()
                .items()
            }
            for group in base.GROUP_ORDER
        },
        "declaration_attempt_rows": int(len(audit)),
        "no_country_attempt_rows": int(
            audit["attempt_status"].eq("no_eligible_historical_country").sum()
        ),
        "selected_country_counts": {
            str(k): int(v)
            for k, v in selected["selected_country_code"].value_counts().sort_index().items()
        },
        "score_formula": str(cfg["country_declaration"]["score_formula"]),
        "score_min": float(selected["country_frame_observability_score"].min()),
        "score_max": float(selected["country_frame_observability_score"].max()),
        "frames_csv_sha256": hashlib.sha256(selected_path.read_bytes()).hexdigest(),
        "attempt_audit_csv_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        "terminal_fresh_identity_only_sha256": str(
            cfg["exclusions"]["terminal_fresh_identity_only_sha256"]
        ),
        "recent_outcomes_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "replacement_after_freeze_allowed": False,
        "score_cutoff_selected": False,
        "scientific_candidate_method_changed": False,
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(freeze(args.output), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
