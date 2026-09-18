#!/usr/bin/env python3
"""Verify every public pre-outcome gate for the fresh-SENTINEL field test.

This verifier reads no prospective field outcomes. Outcome opening is authorized only
when: (1) static evaluation semantics still validate, (2) the candidate/order receipt
is immutably pinned, (3) the field allocation/effort receipt is immutably pinned,
(4) the schedule receipt is hash-bound to the exact candidate/order and evaluation
contract bytes currently present in the repository, and (5) the schedule receipt
proves membership in no-skip prefixes of the exact frozen private arm orders.
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
from research.build_cirsium_fresh_sentinel_private_field_schedule_v1 import _validate_capacity_profile
from research.derive_cirsium_fresh_sentinel_movement_capacity_v1 import validate_effort_protocol
from research.validate_cirsium_fresh_sentinel_analysis_plan_v1 import validate_analysis_plan
from research.validate_cirsium_fresh_sentinel_field_evaluation_contract_v1 import validate_field_evaluation_contract
from research.verify_cirsium_fresh_sentinel_public_field_schedule_pin_v1 import verify_public_field_schedule_pin
from research.verify_cirsium_fresh_sentinel_public_freeze_pin_v1 import verify_public_freeze_pin

ROOT = Path(__file__).resolve().parents[1]
FINAL_STATUS = "ALL_FRESH_SENTINEL_PRE_OUTCOME_GATES_SATISFIED"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def verify_pre_outcome_gate(
    candidate_receipt_path: Path,
    field_schedule_receipt_path: Path,
    field_evaluation_contract_path: Path,
    field_log_template_path: Path,
    analysis_plan_path: Path | None = None,
    *,
    repo_root: Path = ROOT,
    expected_candidate_pin_commit: str = "",
    expected_schedule_pin_commit: str = "",
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    candidate_path = require_canonical_repo_path(
        Path(candidate_receipt_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        label="candidate/order public receipt",
    )
    schedule_path = require_canonical_repo_path(
        Path(field_schedule_receipt_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        label="field-schedule public receipt",
    )
    evaluation_path = require_canonical_repo_path(
        Path(field_evaluation_contract_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        label="field evaluation contract",
    )
    log_template_path = require_canonical_repo_path(
        Path(field_log_template_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        label="field-log template",
    )
    analysis_path = require_canonical_repo_path(
        Path(analysis_plan_path or CANONICAL_ANALYSIS_PLAN_REPO_PATH),
        repo_root=repo,
        expected_repo_path=CANONICAL_ANALYSIS_PLAN_REPO_PATH,
        label="fresh-SENTINEL analysis plan",
    )

    capacity_path = require_canonical_repo_path(
        Path(CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH),
        repo_root=repo,
        expected_repo_path=CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
        label="operational capacity profile",
    )
    effort_protocol_path = require_canonical_repo_path(
        Path(CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH),
        repo_root=repo,
        expected_repo_path=CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
        label="standardized effort protocol",
    )
    if not capacity_path.is_file() or not effort_protocol_path.is_file():
        raise ValueError("missing canonical operational capacity profile or standardized effort protocol")

    evaluation = validate_field_evaluation_contract(evaluation_path, log_template_path)
    if evaluation.get("prospective_outcome_opening_allowed_now") is not False:
        raise ValueError("static evaluation contract must remain pre-outcome and schedule-pending on its own")
    analysis = validate_analysis_plan(analysis_path)
    if analysis.get("prospective_outcomes_opened") is not False:
        raise ValueError("analysis plan must remain outcome-blind")

    capacity_profile = _load(capacity_path)
    _validate_capacity_profile(capacity_profile)
    effort_protocol = _load(effort_protocol_path)
    validate_effort_protocol(effort_protocol)
    if capacity_profile.get("standardized_effort_protocol_sha256") != _sha256(effort_protocol_path):
        raise ValueError("operational capacity profile is not linked to the exact standardized effort protocol")

    candidate_pin = verify_public_freeze_pin(candidate_path, repo_root=repo, expected_pin_commit=expected_candidate_pin_commit)
    if candidate_pin.get("pre_field_prescription_pin_gate_satisfied") is not True:
        raise ValueError("candidate/order immutable pin gate not satisfied")

    schedule_pin = verify_public_field_schedule_pin(schedule_path, repo_root=repo, expected_pin_commit=expected_schedule_pin_commit)
    if schedule_pin.get("field_schedule_pin_gate_satisfied") is not True:
        raise ValueError("field allocation/effort immutable pin gate not satisfied")

    candidate_receipt = _load(candidate_path)
    schedule_receipt = _load(schedule_path)
    candidate_hash = _sha256(candidate_path)
    evaluation_hash = _sha256(evaluation_path)
    analysis_hash = _sha256(analysis_path)
    field_log_template_hash = _sha256(log_template_path)
    capacity_hash = _sha256(capacity_path)
    effort_protocol_hash = _sha256(effort_protocol_path)
    if schedule_receipt.get("candidate_order_public_receipt_sha256") != candidate_hash:
        raise ValueError("field schedule receipt is not linked to the exact immutable candidate/order receipt")
    if schedule_receipt.get("field_evaluation_contract_sha256") != evaluation_hash:
        raise ValueError("field schedule receipt is not linked to the exact current field evaluation contract")
    if schedule_receipt.get("analysis_plan_sha256") != analysis_hash:
        raise ValueError("field schedule receipt is not linked to the exact current fresh-SENTINEL analysis plan")
    if schedule_receipt.get("field_log_template_sha256") != field_log_template_hash:
        raise ValueError("field schedule receipt is not linked to the exact current field-log template")
    if schedule_receipt.get("operational_capacity_profile_repo_path") != CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH:
        raise ValueError("field schedule receipt does not name the canonical operational capacity profile")
    if schedule_receipt.get("standardized_effort_protocol_repo_path") != CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH:
        raise ValueError("field schedule receipt does not name the canonical standardized effort protocol")
    if schedule_receipt.get("operational_capacity_profile_sha256") != capacity_hash:
        raise ValueError("field schedule receipt is not linked to the exact current operational capacity profile")
    if schedule_receipt.get("standardized_effort_protocol_sha256") != effort_protocol_hash:
        raise ValueError("field schedule receipt is not linked to the exact current standardized effort protocol")
    if schedule_receipt.get("movement_constraint_mode") != capacity_profile.get("movement_constraint_mode"):
        raise ValueError("field schedule receipt movement mode differs from the canonical operational capacity profile")
    if float(schedule_receipt.get("max_network_transition_km")) != float(capacity_profile.get("max_network_transition_km")):
        raise ValueError("field schedule receipt movement constraint differs from the canonical operational capacity profile")
    if schedule_receipt.get("automatic_prefix_depth_method") != capacity_profile.get("automatic_prefix_depth_method"):
        raise ValueError("field schedule receipt prefix-depth method differs from the canonical operational capacity profile")
    if candidate_receipt.get("canonical_receipt_repo_path") != CANONICAL_CANDIDATE_RECEIPT_REPO_PATH:
        raise ValueError("candidate/order receipt path identity is not canonical")
    if candidate_receipt.get("canonical_field_schedule_receipt_repo_path") != CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH:
        raise ValueError("candidate/order receipt does not name the canonical field-schedule receipt")
    if candidate_receipt.get("field_evaluation_contract") != CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH:
        raise ValueError("candidate/order receipt does not name the frozen field evaluation contract")
    if candidate_receipt.get("analysis_plan") != CANONICAL_ANALYSIS_PLAN_REPO_PATH:
        raise ValueError("candidate/order receipt does not name the canonical frozen analysis plan")
    if candidate_receipt.get("field_log_template") != CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH:
        raise ValueError("candidate/order receipt does not name the frozen field-log template")
    if schedule_receipt.get("canonical_receipt_repo_path") != CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH:
        raise ValueError("field-schedule receipt path identity is not canonical")
    if schedule_receipt.get("candidate_order_public_receipt_repo_path") != CANONICAL_CANDIDATE_RECEIPT_REPO_PATH:
        raise ValueError("field-schedule receipt does not name the canonical candidate/order receipt")
    if schedule_receipt.get("field_evaluation_contract_repo_path") != CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH:
        raise ValueError("field-schedule receipt does not name the canonical field evaluation contract")
    if schedule_receipt.get("analysis_plan_repo_path") != CANONICAL_ANALYSIS_PLAN_REPO_PATH:
        raise ValueError("field-schedule receipt does not name the canonical analysis plan")
    if schedule_receipt.get("primary_cross_taxon_estimand_identity") != "EQUAL_TAXON_MACRO_PRIMARY_MINUS_COVERAGE_ONLY_V1":
        raise ValueError("field-schedule receipt does not preserve the frozen primary cross-taxon estimand")
    if schedule_receipt.get("field_log_template_repo_path") != CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH:
        raise ValueError("field-schedule receipt does not name the canonical field-log template")
    if candidate_receipt.get("field_allocation_and_effort_schedule_required_before_outcome_opening") is not True:
        raise ValueError("candidate/order receipt does not preserve the field schedule gate")
    if candidate_receipt.get("field_allocation_and_effort_schedule_pinned") is not False:
        raise ValueError("candidate/order receipt must not self-assert a later schedule pin")
    if schedule_receipt.get("prospective_field_outcomes_opened") is not False:
        raise ValueError("field schedule receipt cannot declare opened outcomes")
    if schedule_receipt.get("field_outcomes_used_to_allocate") is not False:
        raise ValueError("field schedule receipt cannot be outcome-informed")
    for key in (
        "private_candidate_membership_verified",
        "private_pre_field_receipt_hash_linkage_verified",
        "frozen_order_hash_linkage_verified",
        "frozen_order_prefix_verified",
    ):
        if schedule_receipt.get(key) is not True:
            raise ValueError(f"field schedule receipt lacks required pre-outcome proof: {key}")

    if schedule_receipt.get("capacity_schedule_linkage_verified") is not True:
        raise ValueError("field schedule receipt lacks movement-derived capacity linkage proof")
    if schedule_receipt.get("standardized_effort_protocol_linkage_verified") is not True:
        raise ValueError("field schedule receipt lacks standardized effort protocol linkage proof")
    if schedule_receipt.get("movement_constraint_mode") != "osm_weighted_transport_network":
        raise ValueError("field schedule receipt movement constraint mode changed")
    if schedule_receipt.get("automatic_prefix_depth_method") != "OSM_COMPLETE_COARSE_COVERAGE_SELECTED_COUNT_V1":
        raise ValueError("field schedule receipt automatic prefix-depth method changed")
    if schedule_receipt.get("user_site_count_input") is not False:
        raise ValueError("field schedule receipt cannot use a user site-count input")
    if schedule_receipt.get("survey_days_input") is not False or schedule_receipt.get("monetary_budget_input") is not False:
        raise ValueError("field schedule receipt cannot use survey-day or monetary-budget inputs")

    expected_arms = [
        "COVERAGE_THEN_FINE_STRUCTURE_V1",
        "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1",
        "MORTON_DYADIC_COVERAGE_ORDER_V1",
    ]
    if schedule_receipt.get("method_arms") != expected_arms:
        raise ValueError("field schedule receipt method arms differ from the frozen comparison")
    if schedule_receipt.get("comparator_assignment_identity") != "FROZEN_ORDER_PREFIX_V1":
        raise ValueError("field schedule receipt does not preserve the frozen order-prefix assignment identity")
    if schedule_receipt.get("arm_symmetry_identity") != "ARM_SYMMETRIC_PREFIX_EFFORT_TEMPLATE_V1":
        raise ValueError("field schedule receipt does not preserve the frozen arm-symmetry identity")
    if schedule_receipt.get("arm_symmetric_prefix_effort_template_verified") is not True:
        raise ValueError("field schedule receipt lacks arm-symmetric prefix/effort proof")

    return {
        "schema_version": "cirsium-fresh-sentinel-pre-outcome-gate-verification-v1",
        "status": FINAL_STATUS,
        "candidate_order_receipt_sha256": candidate_hash,
        "candidate_order_pin_commit": candidate_pin["pin_commit"],
        "field_evaluation_contract_sha256": evaluation_hash,
        "analysis_plan_sha256": analysis_hash,
        "analysis_plan_valid": True,
        "field_log_template_sha256": field_log_template_hash,
        "operational_capacity_profile_sha256": capacity_hash,
        "standardized_effort_protocol_sha256": effort_protocol_hash,
        "primary_cross_taxon_estimand_identity": "EQUAL_TAXON_MACRO_PRIMARY_MINUS_COVERAGE_ONLY_V1",
        "field_schedule_receipt_sha256": _sha256(schedule_path),
        "field_schedule_pin_commit": schedule_pin["pin_commit"],
        "static_evaluation_semantics_valid": True,
        "candidate_order_pin_gate_satisfied": True,
        "field_schedule_pin_gate_satisfied": True,
        "exact_hash_linkage_satisfied": True,
        "private_candidate_membership_verified": True,
        "frozen_order_prefix_verified": True,
        "arm_symmetric_prefix_effort_template_verified": True,
        "capacity_schedule_linkage_verified": True,
        "standardized_effort_protocol_linkage_verified": True,
        "movement_constraint_mode": schedule_receipt["movement_constraint_mode"],
        "max_network_transition_km": float(schedule_receipt["max_network_transition_km"]),
        "automatic_prefix_depth_method": schedule_receipt["automatic_prefix_depth_method"],
        "user_site_count_input": False,
        "survey_days_input": False,
        "monetary_budget_input": False,
        "prospective_field_outcomes_opened": False,
        "outcome_opening_gate_satisfied": True,
        "authorization_scope": "provenance authorization to open the preregistered prospective outcomes; no biological result or field-efficiency claim is implied",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-receipt", type=Path, default=Path(CANONICAL_CANDIDATE_RECEIPT_REPO_PATH))
    parser.add_argument("--field-schedule-receipt", type=Path, default=Path(CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH))
    parser.add_argument("--field-evaluation-contract", type=Path, default=Path(CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH))
    parser.add_argument("--field-log-template", type=Path, default=Path(CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH))
    parser.add_argument("--analysis-plan", type=Path, default=Path(CANONICAL_ANALYSIS_PLAN_REPO_PATH))
    parser.add_argument("--expected-candidate-pin-commit", default="")
    parser.add_argument("--expected-schedule-pin-commit", default="")
    args = parser.parse_args()
    result = verify_pre_outcome_gate(
        args.candidate_receipt,
        args.field_schedule_receipt,
        args.field_evaluation_contract,
        args.field_log_template,
        args.analysis_plan,
        expected_candidate_pin_commit=args.expected_candidate_pin_commit,
        expected_schedule_pin_commit=args.expected_schedule_pin_commit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
