#!/usr/bin/env python3
"""Source-locked, coordinate-free audit of a possible future Cirsium field-trial cohort.

A screening negative is not evidence that a taxon/sector was never used elsewhere.
No private geometry, occurrence coordinates, field logs or detection results are opened.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_UNIT_IDS = tuple(f"CIR{i:02d}" for i in range(1, 14))
EXPOSED_TOPOLOGY_UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
EXPECTED_FAMILY = {
    "CIR01": "WETLAND_MOISTURE_STRUCTURE",
    "CIR02": "WETLAND_MOISTURE_STRUCTURE",
    "CIR03": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR04": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR05": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR06": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR07": "OPEN_GRASSLAND_STRUCTURE",
    "CIR08": "COASTAL_ISLAND_STRUCTURE",
    "CIR09": "COASTAL_ISLAND_STRUCTURE",
    "CIR10": "FOREST_EDGE_STRUCTURE",
    "CIR11": "GENERAL_SPATIAL_BASELINE_ONLY",
    "CIR12": "OPEN_GRASSLAND_STRUCTURE",
    "CIR13": "OPEN_GRASSLAND_STRUCTURE",
}
SOURCE_GIT_BLOBS = {
    "validation/cirsium_aza3_prospective_validation_cohort_v1.csv": "4084355ae091ec992e4f9e64e26522341c65d058",
    "validation/cirsium_private_frame_source_requirements_v1.csv": "c827ed9ce71379bcc91d54fd5e20434886cd5fda",
    "validation/cirsium_structural_population_holdout_preflight_result_v1.json": "1762e52e1afdd1ff19d89ea7db9d0c3bd2f0ec28",
    "validation/cirsium_structural_population_holdout_development_v1.json": "3b1dd32e190f13a7c363a4bb6d12ec3beb822bd0",
    "validation/cirsium_structural_population_holdout_development_terminal_v1.json": "b2e25aaafd30dde9796678fb68c8825a13f78e2c",
    "validation/public_cirsium_structural_three_family_smoke_v1.json": "34d6d7000de30a4c9bfbf8d501eae03c2ac9af31",
    "validation/public_cirsium_detached_broad_coastal_result_v1.json": "0a809a8c2ddcb58925b3ac6c6bb4873a34bacf80",
    "validation/public_cirsium_portable_coastal_smoke_result_v1.json": "cb46b0ee79d958ccde718ff7d332578ab42a966d",
    "validation/cirsium_japan38_disjoint_v2_roster.csv": "74c4bf7b08cc561ceee9334032aef612c0f34797",
    "validation/coverage_then_fine_structure_patch_connectivity_field_trial_design_v1.json": "ec18c79b126b994a47c9680e5098548e655f88c9",
}
SOURCE_FILES = tuple(SOURCE_GIT_BLOBS)


def git_blob_sha(value: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(value)).encode("ascii") + b"\0" + value).hexdigest()


def verify_git_blob_pin(path: Path, expected_sha: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("source file missing, not a regular file, or a symlink")
    actual = git_blob_sha(path.read_bytes())
    if actual != expected_sha:
        raise ValueError("source Git blob SHA mismatch; review and refreeze separately")


def parse_csv(s: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(s, newline=""))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("source CSV has no valid unique field names")
    rows = list(reader)
    if any(None in row or any(val is None for val in row.values()) for row in rows):
        raise ValueError("source CSV malformed or ragged")
    return rows


def _required(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _unique_by_id(rows: list[dict[str, str]], *, label: str) -> dict[str, dict[str, str]]:
    _required(len(rows) == 13, f"{label} cohort must contain exactly 13 registered rows")
    ids = [r.get("cohort_unit_id") for r in rows]
    _required(tuple(ids) == EXPECTED_UNIT_IDS, f"{label} registry order, cohort IDs or duplicate rows changed")
    return {row["cohort_unit_id"]: row for row in rows}


def _unit_set(entries: Any, *, label: str) -> set[str]:
    _required(isinstance(entries, list), f"{label} must be a list")
    units = [x.get("cohort_unit_id") for x in entries if isinstance(x, dict)]
    _required(len(units) == len(entries) and len(units) == len(set(units)), f"{label} duplicate or malformed unit")
    _required(all(u in EXPECTED_UNIT_IDS for u in units), f"{label} unexpected cohort unit")
    return set(units)


def audit_public_records(
    registry_rows: list[dict[str, str]],
    requirement_rows: list[dict[str, str]],
    preflight: dict[str, Any],
    development: dict[str, Any],
    terminal: dict[str, Any],
    smoke: dict[str, Any],
    coastal: dict[str, Any],
    portable: dict[str, Any],
    japan38_roster: list[dict[str, str]],
    trial_design: dict[str, Any],
) -> dict[str, Any]:
    registry = _unique_by_id(registry_rows, label="aza3")
    requirements = _unique_by_id(requirement_rows, label="private source")
    _required(preflight.get("status") == "DEVELOPMENT_PREFLIGHT_TERMINAL"
              and preflight.get("selector_run") is False, "prior structural preflight provenance changed")
    _required(terminal.get("status") == "DEVELOPMENT_TERMINAL_DO_NOT_NOMINATE_COARSE_STRUCTURAL_SELECTOR",
              "prior structural development terminal status changed")
    _required(smoke.get("public_temporal_outcomes_already_opened_for_unit_choice") is True,
              "previous public temporal outcome exposure evidence missing")
    _required(coastal.get("cohort_unit_id") == "CIR08"
              and coastal.get("status") == "DEVELOPMENT_ONLY_OPENED_RESULT_FROZEN_NO_RETUNE"
              and coastal.get("opened_development_only") is True,
              "CIR08 coastal opened development outcome provenance changed")
    _required(portable.get("cohort_unit_id") == "CIR08"
              and portable.get("status") == "DEVELOPMENT_ONLY_COMPLETE_DO_NOT_RETUNE_ON_CIR08",
              "CIR08 coastal portable method exposure changed")
    _required(trial_design.get("status") == "METHOD_DESIGN_FROZEN_BEFORE_NEW_COHORT_SELECTION_NO_OUTCOMES"
              and trial_design.get("cohort_identity_frozen") is False
              and trial_design.get("field_schedule_frozen") is False
              and trial_design.get("outcomes_may_be_opened") is False,
              "topology method design cannot silently become a cohort/field schedule")
    _required(tuple(trial_design.get("parent_observation", {}).get("previously_exposed_cohort_units", ()))
              == EXPOSED_TOPOLOGY_UNITS, "old topology development-exposed unit registry changed")

    eligible_preflight = _unit_set(preflight.get("eligible_pairs"), label="preflight eligible pairs")
    execution = _unit_set(development.get("execution_pairs"), label="holdout execution pairs")
    deferred = _unit_set(development.get("explicitly_deferred_eligible_pairs"), label="holdout explicitly deferred pairs")
    named_smoke = _unit_set(smoke.get("units"), label="structural smoke selection")
    _required(eligible_preflight == {"CIR01", "CIR04", "CIR07", "CIR08"},
              "prior preflight exposure set drifted")
    _required(execution == {"CIR01", "CIR04", "CIR07"}, "prior executed structural holdout exposure set drifted")
    _required(deferred == {"CIR08"}, "prior deferred method exposure drifted")
    _required(named_smoke == {"CIR01", "CIR04", "CIR08"}, "structural smoke exposure set drifted")
    _required(terminal.get("executed_scope", {}).get("executed_pairs") == 3,
              "holdout execution denominator drifted")

    consumed_japan38 = [r for r in japan38_roster if r.get("provider_query_name") == "Cirsium sieboldii"]
    _required(len(consumed_japan38) == 1 and consumed_japan38[0].get("include_v2") == "false"
              and "CIR01 public outcome opened" in consumed_japan38[0].get("exclusion_reason", ""),
              "CIR01 previously published public temporal outcome exposure not verified")

    report_units: dict[str, Any] = {}
    for unit in EXPECTED_UNIT_IDS:
        r, req = registry[unit], requirements[unit]
        _required(r.get("species_binomial") and r.get("species_binomial") == req.get("species_binomial"),
                  f"{unit} species identity mismatch between pinned registries")
        family = EXPECTED_FAMILY[unit]
        _required(r.get("structural_feature_family") == req.get("structural_feature_family") == family,
                  f"{unit} structural family identity mismatch")
        _required(r.get("outcome_opened") == "false", f"{unit} prospective field outcome register changed")
        _required(r.get("candidate_patch_status") == "NOT_BUILT"
                  and req.get("private_frame_status") == "NOT_BUILT"
                  and req.get("private_source_manifest_status") == "NOT_BUILT"
                  and req.get("public_full_ranking_status") == "NOT_FROZEN",
                  f"{unit} private source/candidate patch/frame/rank state changed")
        evidences: list[str] = []
        if unit in eligible_preflight:
            evidences.append("STRUCTURAL_POPULATION_HOLDOUT_PREFLIGHT_ELIGIBLE")
        if unit in execution:
            evidences.append("STRUCTURAL_HOLDOUT_DEVELOPMENT_EXECUTED")
        if unit in deferred:
            evidences.append("STRUCTURAL_HOLDOUT_COASTAL_DEFERRED")
        if unit in named_smoke:
            evidences.append("THREE_FAMILY_STRUCTURAL_SMOKE_NOMINATED")
        if unit == "CIR08":
            evidences.extend(("COASTAL_DEVELOPMENT_PUBLIC_OUTCOME_OPENED", "PORTABLE_COASTAL_SMOKE_USED"))
        if unit == "CIR01":
            evidences.append("JAPAN38_PUBLIC_TEMPORAL_OUTCOME_OPENED_REGISTRY_EXCLUSION")
        method = ("EXPLICIT_PRIOR_METHOD_DEVELOPMENT_EXPOSURE" if (unit in execution or unit == "CIR08")
                  else "NOT_EVIDENCED_IN_PINNED_SOURCES_NOT_PROVEN_UNTOUCHED")
        report_units[unit] = {
            "species_binomial": r["species_binomial"],
            "structural_feature_family": family,
            "registry_role": "PREVIOUSLY_EXPOSED_TOPOLOGY_METHOD_DEV" if unit in EXPOSED_TOPOLOGY_UNITS else "PUBLIC_SOURCE_SCREEN_ONLY",
            "method_exposure_class": method,
            "exposure_evidence": evidences,
            "public_historical_outcome_exposure": (
                "EXPLICITLY_DOCUMENTED" if unit == "CIR01"
                else ("EXPLICIT_COASTAL_DEVELOPMENT_OPENED" if unit == "CIR08"
                      else "NOT_ASSESSED_PER_UNIT")
            ),
            "prospective_field_outcomes_marked_opened_in_registry": False,
            "patch_status": "NOT_BUILT",
            "private_source_manifest_status": "NOT_BUILT",
            "private_candidate_frame_status": "NOT_BUILT",
            "full_private_structural_order_frozen": False,
            "structural_family_status": ("NO_FROZEN_STRUCTURAL_FAMILY_BASELINE_ONLY" if family == "GENERAL_SPATIAL_BASELINE_ONLY"
                                         else "DECLARED_HABITAT_FAMILY_NOT_NEWLY_VALIDATED_FOR_TRIAL"),
            "private_range_sector_geometry_verified": False,
            "private_patch_sha_and_membership_verified": False,
            "access_permission_and_phenology_preflight_passed": False,
            "candidate_schedule_frozen": False,
            "independent_cohort_authorized": False,
            "actual_field_assignment_authorized": False,
        }

    screened = [u for u in EXPECTED_UNIT_IDS if u not in EXPOSED_TOPOLOGY_UNITS]
    _required(len(screened) == 9, "original exposed-topology subtraction changed")
    exposed = [u for u in screened if report_units[u]["method_exposure_class"] == "EXPLICIT_PRIOR_METHOD_DEVELOPMENT_EXPOSURE"]
    unknown = [u for u in screened if u not in exposed]
    family_counts: dict[str, int] = {}
    for u in screened:
        family = report_units[u]["structural_feature_family"]
        family_counts[family] = family_counts.get(family, 0) + 1

    return {
        "schema_version": "acsp-cirsium-topology-trial-public-exposure-readiness-screen-v1",
        "status": "PUBLIC_REGISTRY_EXPOSURE_SCREEN_COMPLETE_NO_UNTOUCHED_COHORT_AUTHORIZED",
        "basis": "source-locked snapshot of ten previously committed public files; not a census of all past ACSP/aza3 studies",
        "previous_topology_method_units": list(EXPOSED_TOPOLOGY_UNITS),
        "development_exposed_topology_units": list(EXPOSED_TOPOLOGY_UNITS),
        "registered_original_units": len(EXPECTED_UNIT_IDS),
        "candidate_pool_count": len(screened),
        "screened_units": screened,
        "method_exposed_within_screened_count": len(exposed),
        "units_with_explicit_prior_method_exposure": exposed,
        "without_explicit_method_use_in_pinned_sources_count": len(unknown),
        "units_without_explicit_method_use_in_pinned_sources": unknown,
        "structural_family_baseline_only_count": family_counts.get("GENERAL_SPATIAL_BASELINE_ONLY", 0),
        "screened_structural_families": dict(sorted(family_counts.items())),
        "independent_confirmatory_unit_count": 0,
        "ready_for_field_assignment_count": 0,
        "units": report_units,
        "claims": {
            "no_private_geometry_read": True,
            "no_prospective_field_records_opened": True,
            "absence_of_exposure_in_all_other_repositories_proven": False,
            "public_registry_outcome_false_implies_untouched": False,
            "frozen_independent_taxon_sector_cohort_established": False,
            "private_sector_disjointness_established": False,
            "patch_eligibility_established": False,
            "field_detection_advantage_established": False,
            "validated_japan_patch_membership_changed": False,
            "existing_three_arm_field_plan_changed": False,
            "prospective_field_outcomes_may_be_opened": False,
        },
        "next_gate": "Audit method-exposure and spatial/taxon independence across other sources; predeclare NEW independent units and authorize/private-verify polygon/patch source before field allocation.",
    }


def run_public_audit(root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    for rel, sha in SOURCE_GIT_BLOBS.items():
        verify_git_blob_pin(root / rel, sha)
    def raw(rel: str) -> bytes:
        return (root / rel).read_bytes()
    def payload(rel: str) -> dict[str, Any]:
        data = json.loads(raw(rel))
        _required(isinstance(data, dict), "source JSON must contain one object")
        return data
    source = list(SOURCE_FILES)
    report = audit_public_records(
        parse_csv(raw(source[0]).decode("utf-8")),
        parse_csv(raw(source[1]).decode("utf-8")),
        payload(source[2]), payload(source[3]), payload(source[4]),
        payload(source[5]), payload(source[6]), payload(source[7]),
        parse_csv(raw(source[8]).decode("utf-8")), payload(source[9]),
    )
    report["pinned_public_git_blobs"] = dict(SOURCE_GIT_BLOBS)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out-json", type=Path)
    group.add_argument("--verify-saved", type=Path)
    args = parser.parse_args()
    report = run_public_audit(ROOT)
    exact = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out_json is not None:
        target = args.out_json.resolve()
        if target.is_relative_to(ROOT.resolve()):
            raise ValueError("public audit output must first be created outside repository")
        if target.exists() or args.out_json.is_symlink():
            raise ValueError("refusing to overwrite public audit")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(exact, encoding="utf-8")
    else:
        if not args.verify_saved.is_file() or args.verify_saved.is_symlink():
            raise ValueError("saved public result missing or unsafe")
        if args.verify_saved.read_text(encoding="utf-8") != exact:
            raise ValueError("source-locked saved exposure screen differs from regenerated result")
    print(json.dumps({"status": report["status"], "screened": report["candidate_pool_count"],
                      "explicit_prior_method_use": report["method_exposed_within_screened_count"],
                      "not_proven_untouched": report["without_explicit_method_use_in_pinned_sources_count"],
                      "field_ready": report["ready_for_field_assignment_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
