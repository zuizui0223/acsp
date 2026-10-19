#!/usr/bin/env python3
"""Export a public-safe receipt for a validated private fresh-SENTINEL field schedule.

The private schedule and private pre-field root stay outside the repository. This
exporter retains only hashes, methodological identities, verification booleans and
non-spatial assignment counts. It never exports private candidate references or
prospective field outcomes. Receipt generation alone does not authorize outcome
opening; the receipt must be immutably committed and the final pre-outcome gate
must verify both prescription and schedule pins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_ANALYSIS_PLAN_REPO_PATH,
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
    CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
    require_canonical_repo_path,
)
from research.derive_cirsium_fresh_sentinel_movement_capacity_v1 import validate_effort_protocol
from research.validate_cirsium_fresh_sentinel_analysis_plan_v1 import validate_analysis_plan
from research.build_cirsium_fresh_sentinel_private_field_schedule_v1 import (
    UNITS as CAPACITY_UNITS,
    _validate_capacity_profile,
)
from research.validate_cirsium_fresh_sentinel_private_field_schedule_v1 import (
    validate_private_field_schedule,
)
from research.validate_cirsium_fresh_sentinel_private_schedule_membership_v1 import (
    validate_private_schedule_membership,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STATUS = "PUBLIC_FIELD_ALLOCATION_EFFORT_SCHEDULE_READY_FOR_COMMIT"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_public_field_schedule_receipt(
    private_schedule_path: Path,
    candidate_receipt_path: Path,
    field_evaluation_contract_path: Path,
    private_pre_field_root: Path,
    operational_capacity_profile_path: Path,
    standardized_effort_protocol_path: Path,
    analysis_plan_path: Path | None = None,
    field_log_template_path: Path | None = None,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    private_schedule_path = Path(private_schedule_path).resolve()
    repo = Path(repo_root).resolve()
    candidate_receipt_path = require_canonical_repo_path(
        Path(candidate_receipt_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        label="candidate/order public receipt",
    )
    field_evaluation_contract_path = require_canonical_repo_path(
        Path(field_evaluation_contract_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        label="field evaluation contract",
    )
    analysis_plan_path = require_canonical_repo_path(
        Path(analysis_plan_path or CANONICAL_ANALYSIS_PLAN_REPO_PATH),
        repo_root=repo,
        expected_repo_path=CANONICAL_ANALYSIS_PLAN_REPO_PATH,
        label="fresh-SENTINEL analysis plan",
    )
    validate_analysis_plan(analysis_plan_path)
    field_log_template_path = require_canonical_repo_path(
        Path(field_log_template_path or CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH),
        repo_root=repo,
        expected_repo_path=CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        label="field-log template",
    )
    validated = validate_private_field_schedule(
        private_schedule_path,
        candidate_receipt_path,
        field_evaluation_contract_path,
        repo_root=repo_root,
    )
    membership = validate_private_schedule_membership(
        private_schedule_path,
        candidate_receipt_path,
        Path(private_pre_field_root),
        repo_root=repo_root,
    )

    capacity_path = require_canonical_repo_path(
        Path(operational_capacity_profile_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
        label="operational capacity profile",
    )
    effort_protocol_path = require_canonical_repo_path(
        Path(standardized_effort_protocol_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
        label="standardized effort protocol",
    )
    if not capacity_path.is_file() or not effort_protocol_path.is_file():
        raise ValueError("operational capacity profile and standardized effort protocol must both exist")
    capacity_profile = json.loads(capacity_path.read_text(encoding="utf-8"))
    if not isinstance(capacity_profile, dict):
        raise ValueError("operational capacity profile must be a JSON object")
    capacity = _validate_capacity_profile(capacity_profile)
    if capacity_profile["standardized_effort_protocol_sha256"] != _sha256(effort_protocol_path):
        raise ValueError("operational capacity profile is not bound to the exact standardized effort protocol")

    effort_protocol_value = json.loads(effort_protocol_path.read_text(encoding="utf-8"))
    if not isinstance(effort_protocol_value, dict):
        raise ValueError("standardized effort protocol must be a JSON object")
    effort_by_unit = validate_effort_protocol(effort_protocol_value)
    for unit in CAPACITY_UNITS:
        cap = capacity[unit]
        effort = effort_by_unit[unit]
        for key in ("visits_per_candidate", "observer_count"):
            if int(cap[key]) != int(effort[key]):
                raise ValueError(f"operational capacity {key} differs from standardized effort protocol for {unit}")
        if float(cap["search_minutes_per_visit"]) != float(effort["search_minutes_per_visit"]):
            raise ValueError(f"operational capacity search minutes differ from standardized effort protocol for {unit}")

    private_root = Path(private_pre_field_root).resolve()
    frame_hashes = capacity_profile["private_candidate_frame_sha256_by_unit"]
    for unit in CAPACITY_UNITS:
        frame_path = private_root / unit / "candidate_frame_pre_field.csv"
        if not frame_path.is_file() or frame_hashes[unit] != _sha256(frame_path):
            raise ValueError(f"operational capacity profile is not bound to the exact private candidate frame for {unit}")

    counts = validated["assignment_count_by_unit_arm"]
    selected_counts = membership["selected_unique_candidate_count_by_unit_arm"]
    schedule_value = json.loads(private_schedule_path.read_text(encoding="utf-8"))
    assignments = schedule_value.get("assignments") or []
    for unit in CAPACITY_UNITS:
        cap = capacity[unit]
        for arm, selected_count in selected_counts[unit].items():
            if int(selected_count) != int(cap["prefix_depth"]):
                raise ValueError(f"private schedule prefix depth does not match movement-derived capacity for {unit}/{arm}")
        unit_rows = [row for row in assignments if row.get("cohort_unit_id") == unit]
        expected_visits = int(cap["visits_per_candidate"])
        expected_minutes = float(cap["search_minutes_per_visit"])
        expected_observers = int(cap["observer_count"])
        by_analysis: dict[str, list[dict[str, Any]]] = {}
        for row in unit_rows:
            if float(row["planned_search_minutes"]) != expected_minutes:
                raise ValueError(f"private schedule search minutes differ from standardized effort protocol for {unit}")
            if int(row["planned_observer_count"]) != expected_observers:
                raise ValueError(f"private schedule observer count differs from standardized effort protocol for {unit}")
            by_analysis.setdefault(str(row["analysis_unit_id"]), []).append(row)
        if any(len(rows) != expected_visits for rows in by_analysis.values()):
            raise ValueError(f"private schedule visit count differs from standardized effort protocol for {unit}")
    return {
        "schema_version": "cirsium-fresh-sentinel-public-field-schedule-receipt-v1",
        "status": PUBLIC_STATUS,
        "canonical_receipt_repo_path": CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        "candidate_order_public_receipt_repo_path": CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        "field_evaluation_contract_repo_path": CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        "analysis_plan_repo_path": CANONICAL_ANALYSIS_PLAN_REPO_PATH,
        "field_log_template_repo_path": CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        "private_field_schedule_sha256": _sha256(private_schedule_path),
        "operational_capacity_profile_repo_path": CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
        "standardized_effort_protocol_repo_path": CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
        "operational_capacity_profile_sha256": _sha256(capacity_path),
        "standardized_effort_protocol_sha256": _sha256(effort_protocol_path),
        "movement_constraint_mode": capacity_profile["movement_constraint_mode"],
        "max_network_transition_km": float(capacity_profile["max_network_transition_km"]),
        "automatic_prefix_depth_method": capacity_profile["automatic_prefix_depth_method"],
        "coarse_redundancy_scale_m": float(capacity_profile["coarse_redundancy_scale_m"]),
        "coarse_representative_rule": capacity_profile["coarse_representative_rule"],
        "frozen_common_candidate_geometry_used_for_movement_capacity": True,
        "arm_rank_used_to_set_prefix_depth": False,
        "structural_score_used_to_set_prefix_depth": False,
        "candidate_identity_or_coordinates_exported_from_capacity": False,
        "user_site_count_input": False,
        "user_coverage_target_input": False,
        "survey_days_input": False,
        "monetary_budget_input": False,
        "capacity_schedule_linkage_verified": True,
        "standardized_effort_protocol_linkage_verified": True,
        "candidate_order_public_receipt_sha256": validated["candidate_order_public_receipt_sha256"],
        "field_evaluation_contract_sha256": validated["field_evaluation_contract_sha256"],
        "analysis_plan_sha256": _sha256(analysis_plan_path),
        "field_log_template_sha256": _sha256(field_log_template_path),
        "primary_cross_taxon_estimand_identity": "EQUAL_TAXON_MACRO_PRIMARY_MINUS_COVERAGE_ONLY_V1",
        "private_pre_field_top_receipt_sha256": membership["private_pre_field_top_receipt_sha256"],
        "cohort_unit_ids": validated["cohort_unit_ids"],
        "method_arms": validated["method_arms"],
        "primary_analysis_unit_identity": validated["primary_analysis_unit_identity"],
        "repeated_visit_aggregation_identity": validated["repeated_visit_aggregation_identity"],
        "shared_candidate_handling_identity": validated["shared_candidate_handling_identity"],
        "comparator_assignment_identity": validated["comparator_assignment_identity"],
        "arm_symmetry_identity": validated["arm_symmetry_identity"],
        "arm_symmetric_prefix_effort_template_verified": membership["arm_symmetric_prefix_effort_template_verified"],
        "numeric_effort_metric": validated["numeric_effort_metric"],
        "assignment_count": validated["assignment_count"],
        "assignment_count_by_unit_arm": counts,
        "selected_unique_candidate_count_by_unit_arm": selected_counts,
        "private_candidate_membership_verified": True,
        "private_pre_field_receipt_hash_linkage_verified": True,
        "frozen_order_hash_linkage_verified": True,
        "frozen_order_prefix_verified": True,
        "coordinate_bearing_data_included": False,
        "private_candidate_refs_included": False,
        "private_paths_included": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_allocate": False,
        "post_outcome_schedule_edits_allowed": False,
        "public_safe_to_commit": True,
        "outcome_opening_authorized_by_generation_alone": False,
        "public_schedule_receipt_commit_required_before_outcome_opening": True,
        "public_schedule_receipt_commit_verified": False,
        "final_pre_outcome_gate_required": True,
        "outcome_opening_gate": "Commit this exact receipt immutably, then verify the candidate/order pin, this field-schedule pin, exact hash linkage, private candidate membership and no-skip frozen-order prefixes before prospective outcomes are opened."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-schedule", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, default=Path(CANONICAL_CANDIDATE_RECEIPT_REPO_PATH))
    parser.add_argument("--field-evaluation-contract", type=Path, default=Path(CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH))
    parser.add_argument("--analysis-plan", type=Path, default=Path(CANONICAL_ANALYSIS_PLAN_REPO_PATH))
    parser.add_argument("--field-log-template", type=Path, default=Path(CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH))
    parser.add_argument("--private-pre-field-root", type=Path, required=True)
    parser.add_argument("--operational-capacity-profile", type=Path, default=Path(CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH))
    parser.add_argument("--standardized-effort-protocol", type=Path, default=Path(CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH))
    parser.add_argument("--out-json", type=Path, default=Path(CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH))
    args = parser.parse_args()
    out_json = require_canonical_repo_path(
        args.out_json,
        repo_root=ROOT,
        expected_repo_path=CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        label="public field-schedule receipt",
    )
    if out_json.exists():
        raise SystemExit("refusing to overwrite an existing public field-schedule receipt")
    receipt = build_public_field_schedule_receipt(
        args.private_schedule,
        args.candidate_receipt,
        args.field_evaluation_contract,
        args.private_pre_field_root,
        args.operational_capacity_profile,
        args.standardized_effort_protocol,
        args.analysis_plan,
        args.field_log_template,
    )
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "out_json": str(out_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
