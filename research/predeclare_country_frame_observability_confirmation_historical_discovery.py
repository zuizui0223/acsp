#!/usr/bin/env python3
"""Historical-only discovery wrapper for the prospective observability freeze.

This module applies the pre-heldout issue #163 boundary correction while
preserving the parent protocol's identity hash, country declaration, score,
endpoint, and decision rule.  It additionally excludes any identity that became
human-visible during a quarantined pre-heldout technical run.  The corrected
*discovery species facet* is bounded to 1900--2020, so candidate-pool membership
and generic record-count strata cannot depend on the 2021--2025 held-out interval.
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

ROOT = Path(__file__).resolve().parents[1]
CORRECTION_PATH = (
    ROOT / "validation" / "acsp_country_frame_observability_confirmation_boundary_correction_v1.json"
)
EXPOSURE_BINDING_PATH = (
    ROOT / "validation" / "acsp_country_frame_observability_confirmation_preheldout_exposure_v1.json"
)
EXPOSED_IDENTITY_PATH = (
    ROOT / "validation" / "acsp_country_frame_observability_confirmation_preheldout_exposed_identities_v1.csv"
)
EXPECTED_CORRECTION_FINGERPRINT = "f218782451f7a3a3b248ce8a886a0ccab838eedafd752d8475a9b6682e4fdb1e"
EXPECTED_EXPOSURE_BINDING_FINGERPRINT = "76e708dfbc45daa55c3a6d383c47e1b35074df5b206a1bc27e584ce7cf7ae638"
EXPECTED_EXPOSED_IDENTITY_SHA256 = "057485e27d7da9eccf08ac81cebe1fa996a4a58402299eaa5c70a2e853731602"
DISCOVERY_YEARS = tuple(int(x) for x in base.HISTORICAL_YEARS)
BOUNDARY_CORRECTION_ID = "acsp_country_frame_observability_confirmation_boundary_correction_v1"
EXPOSURE_BINDING_ID = "acsp_country_frame_observability_confirmation_preheldout_exposure_v1"


def correction() -> dict[str, object]:
    """Load and cryptographically verify the pre-heldout boundary correction."""
    payload = json.loads(CORRECTION_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("correction_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_CORRECTION_FINGERPRINT or calculated != EXPECTED_CORRECTION_FINGERPRINT:
        raise ValueError(
            "observability boundary-correction fingerprint mismatch: "
            f"file={stored}, calculated={calculated}, expected={EXPECTED_CORRECTION_FINGERPRINT}"
        )
    if payload["parent_protocol_fingerprint"] != base.EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("boundary correction parent-protocol fingerprint drift")
    boundary = payload["corrected_boundary"]
    if tuple(int(x) for x in boundary["discovery_species_facet_years"]) != DISCOVERY_YEARS:
        raise ValueError("boundary correction discovery-year drift")
    if str(boundary["gbif_year_parameter"]) != "1900,2020":
        raise ValueError("boundary correction GBIF year parameter drift")
    if boundary["heldout_rows_or_country_facets_allowed_during_freeze"] is not False:
        raise ValueError("boundary correction may not open heldout rows/facets during freeze")
    if payload["reason"]["frozen_country_heldout_endpoint_opened_before_correction"] is not False:
        raise ValueError("boundary correction was not frozen pre-heldout")
    payload["correction_fingerprint"] = stored
    return payload


def exposure_binding() -> tuple[dict[str, object], set[int]]:
    """Verify the identity-only quarantine created by the failed technical run."""
    payload = json.loads(EXPOSURE_BINDING_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("binding_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_EXPOSURE_BINDING_FINGERPRINT or calculated != EXPECTED_EXPOSURE_BINDING_FINGERPRINT:
        raise ValueError(
            "observability exposure-binding fingerprint mismatch: "
            f"file={stored}, calculated={calculated}, expected={EXPECTED_EXPOSURE_BINDING_FINGERPRINT}"
        )
    if payload["binding_id"] != EXPOSURE_BINDING_ID:
        raise ValueError("unexpected observability exposure binding id")
    if payload["parent_protocol_fingerprint"] != base.EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("exposure binding parent-protocol fingerprint drift")
    if payload["boundary_correction_fingerprint"] != EXPECTED_CORRECTION_FINGERPRINT:
        raise ValueError("exposure binding correction fingerprint drift")
    if payload["source_run_authoritative"] is not False or payload["source_run_freeze_completed"] is not False:
        raise ValueError("quarantined run status drift")
    if payload["source_run_artifact_created"] is not False:
        raise ValueError("quarantined run unexpectedly created an artifact")
    if payload["frozen_country_heldout_endpoint_opened"] is not False:
        raise ValueError("quarantined run opened the heldout endpoint")
    if payload["identity_file"] != str(EXPOSED_IDENTITY_PATH.relative_to(ROOT)):
        raise ValueError("exposure identity path drift")

    data = EXPOSED_IDENTITY_PATH.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_EXPOSED_IDENTITY_SHA256 or digest != payload["identity_file_sha256"]:
        raise ValueError("exposed identity-only file SHA256 mismatch")
    frame = pd.read_csv(EXPOSED_IDENTITY_PATH, usecols=["speciesKey"])
    keys = set(pd.to_numeric(frame["speciesKey"], errors="raise").astype(int))
    if len(frame) != int(payload["identity_rows"]) or len(keys) != len(frame):
        raise ValueError("exposed identity-only quarantine row/count drift")
    payload["binding_fingerprint"] = stored
    return payload, keys


def corrected_exclusion_sets() -> tuple[set[int], set[str]]:
    """Return original consumed identities plus pre-heldout human-visible exposure."""
    keys, names = base.consumed_exclusion_sets()
    _, exposed_keys = exposure_binding()
    return set(keys) | exposed_keys, set(names)


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


def _boundary_manifest_fields() -> dict[str, object]:
    exposure, exposed_keys = exposure_binding()
    return {
        "parent_protocol_fingerprint": base.EXPECTED_PROTOCOL_FINGERPRINT,
        "boundary_correction_id": BOUNDARY_CORRECTION_ID,
        "boundary_correction_fingerprint": EXPECTED_CORRECTION_FINGERPRINT,
        "discovery_species_facet_years": list(DISCOVERY_YEARS),
        "discovery_species_facets_include_heldout_years": False,
        "preheldout_exposure_binding_id": EXPOSURE_BINDING_ID,
        "preheldout_exposure_binding_fingerprint": EXPECTED_EXPOSURE_BINDING_FINGERPRINT,
        "preheldout_exposed_identity_sha256": EXPECTED_EXPOSED_IDENTITY_SHA256,
        "preheldout_exposed_identity_rows": int(exposure["identity_rows"]),
        "preheldout_exposed_species_keys": len(exposed_keys),
    }


def _abort_manifest(exc: base.FreezeAborted, audit: pd.DataFrame) -> dict[str, object]:
    return {
        "status": "observability_confirmation_freeze_aborted_before_complete_cohort",
        "protocol_fingerprint": base.EXPECTED_PROTOCOL_FINGERPRINT,
        "issue": 163,
        **_boundary_manifest_fields(),
        "attempt_rows": int(len(audit)),
        "recent_outcomes_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "replacement_after_freeze_allowed": False,
        "abort_reason": str(exc),
    }


def freeze(output: Path) -> dict[str, object]:
    """Freeze the corrected prospective cohort with historical-only discovery facets."""
    cfg = base.protocol()
    amended = correction()
    exposure, _ = exposure_binding()
    if DISCOVERY_YEARS != tuple(int(x) for x in cfg["country_declaration"]["historical_years"]):
        raise ValueError("historical discovery years drift from frozen historical window")
    if amended["parent_protocol_fingerprint"] != cfg["protocol_fingerprint"]:
        raise ValueError("boundary correction is not bound to the loaded parent protocol")
    if exposure["boundary_correction_fingerprint"] != amended["correction_fingerprint"]:
        raise ValueError("preheldout exposure binding is not bound to the loaded correction")

    excluded_keys, excluded_names = corrected_exclusion_sets()
    output.mkdir(parents=True, exist_ok=True)
    try:
        selected, audit = base.select_observability_frames(
            frame_provider=historical_taxon_frame,
            excluded_keys=excluded_keys,
            excluded_names=excluded_names,
        )
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
        **_boundary_manifest_fields(),
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
