#!/usr/bin/env python3
"""Freeze pre-outcome broad uncertainty-footprint evidence for CIR02 and CIR12.

Exact coordinates remain in private workflow artifacts. Public-safe output contains
only identities, counts, hashes and provider status. Provider failure is
indeterminate and never becomes biological absence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from audit_cirsium_aza3_gbif_occurrences_v1 import fetch_occurrences, gbif_taxon_match
from materialize_cirsium_fresh_sentinel_public_sources_v1 import qualified_uncertainty_evidence

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_uncertainty_evidence_freeze_v1.json"
UNITS = {
    "CIR02": "Cirsium inundatum",
    "CIR12": "Cirsium dipsacolepis",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside_repo(path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_UNCERTAINTY_EVIDENCE_FETCH":
        raise ValueError("uncertainty evidence contract is not frozen")
    if tuple((value.get("eligible_units") or {}).keys()) != tuple(UNITS):
        raise ValueError("uncertainty evidence unit set drifted")
    return value


def unique_footprints(evidence: pd.DataFrame) -> pd.DataFrame:
    required = ["gbif_key", "latitude", "longitude", "coordinate_uncertainty_m", "year"]
    missing = [column for column in required if column not in evidence.columns]
    if missing:
        raise ValueError(f"qualified uncertainty evidence missing columns: {missing}")
    work = evidence.loc[:, required].copy()
    work = work.sort_values(
        ["latitude", "longitude", "coordinate_uncertainty_m", "year", "gbif_key"],
        kind="mergesort",
    )
    work = work.drop_duplicates(
        subset=["latitude", "longitude", "coordinate_uncertainty_m"],
        keep="first",
    ).reset_index(drop=True)
    return work


def freeze_uncertainty_evidence(private_dir: Path) -> dict[str, Any]:
    contract = _load_contract()
    private_dir = Path(private_dir).resolve()
    if _inside_repo(private_dir):
        raise ValueError("coordinate-bearing uncertainty evidence must remain outside the public repository")
    if private_dir.exists():
        raise ValueError("private uncertainty evidence directory must not already exist")
    private_dir.mkdir(parents=True)

    units: dict[str, Any] = {}
    provider_complete = True
    for unit_id, species in UNITS.items():
        try:
            match = gbif_taxon_match(species)
            if match.get("classification") != "AUTO_EXACT_ACCEPTED":
                units[unit_id] = {
                    "species_binomial": species,
                    "status": "INDETERMINATE_TAXON_MATCH_REVIEW_REQUIRED",
                    "taxon_match_classification": str(match.get("classification") or ""),
                    "eligible_record_count": 0,
                    "unique_footprint_count": 0,
                    "private_evidence_sha256": "",
                    "provider_error_class": "",
                }
                provider_complete = False
                continue

            raw_records = fetch_occurrences(str(match["usage_key"]))
            qualified = qualified_uncertainty_evidence(raw_records)
            unique = unique_footprints(qualified)
            if unique.empty:
                units[unit_id] = {
                    "species_binomial": species,
                    "status": "FROZEN_ZERO_ELIGIBLE_UNCERTAINTY_FOOTPRINTS",
                    "taxon_match_classification": "AUTO_EXACT_ACCEPTED",
                    "matched_usage_key": str(match["usage_key"]),
                    "eligible_record_count": 0,
                    "unique_footprint_count": 0,
                    "private_evidence_sha256": "",
                    "provider_error_class": "",
                }
                continue

            path = private_dir / f"{unit_id}_uncertainty_footprints.csv"
            unique.to_csv(path, index=False, lineterminator="\n")
            units[unit_id] = {
                "species_binomial": species,
                "status": "UNCERTAINTY_FOOTPRINT_EVIDENCE_FROZEN",
                "taxon_match_classification": "AUTO_EXACT_ACCEPTED",
                "matched_usage_key": str(match["usage_key"]),
                "eligible_record_count": int(len(qualified)),
                "unique_footprint_count": int(len(unique)),
                "private_evidence_sha256": _sha256(path),
                "private_evidence_filename": path.name,
                "provider_error_class": "",
            }
        except Exception as exc:
            units[unit_id] = {
                "species_binomial": species,
                "status": "INDETERMINATE_PROVIDER_FAILURE",
                "taxon_match_classification": "",
                "eligible_record_count": 0,
                "unique_footprint_count": 0,
                "private_evidence_sha256": "",
                "provider_error_class": type(exc).__name__,
            }
            provider_complete = False

    result = {
        "schema_version": "cirsium-fresh-sentinel-v2-uncertainty-evidence-freeze-result-v1",
        "status": "UNCERTAINTY_EVIDENCE_FREEZE_COMPLETE",
        "eligible_units": list(UNITS),
        "units": units,
        "all_provider_queries_complete": provider_complete,
        "eligibility_rule": contract["eligibility_rule"],
        "support_rule_identity": contract["support_rule_after_freeze"]["identity"],
        "coordinate_bearing_evidence_public": False,
        "private_evidence_hashes_recorded": True,
        "provider_failure_is_biological_negative": False,
        "zero_eligible_footprints_is_exact_absence_claim": False,
        "candidate_membership_changed": False,
        "candidate_ranking_added": False,
        "habitat_threshold_added": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "private_exact_site_geometry_used": False,
        "p02_result_used": False,
        "human_access_used": False,
        "next_gate": (
            "Freeze this public-safe evidence receipt. If both units have frozen evidence, "
            "use the private footprint hashes as fixed inputs to the coarse evidence order."
            if provider_complete
            else "Do not construct uncertainty-footprint support until the same frozen provider queries complete without substitution."
        ),
    }
    (private_dir / "public_safe_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    args = parser.parse_args()
    result = freeze_uncertainty_evidence(args.private_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
