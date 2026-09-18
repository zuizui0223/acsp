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
    require_canonical_repo_path,
)
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

    evaluation = validate_field_evaluation_contract(evaluation_path, log_template_path)
    if evaluation.get("prospective_outcome_opening_allowed_now") is not False:
        raise ValueError("static evaluation contract must remain pre-outcome and schedule-pending on its own")
    analysis = validate_analysis_plan(analysis_path)
    if analysis.get("prospective_outcomes_opened") is not False:
        raise ValueError("analysis plan must remain outcome-blind")

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
    if schedule_receipt.get("candidate_order_public_receipt_sha256") != candidate_hash:
        raise ValueError("field schedule receipt is not linked to the exact immutable candidate/order receipt")
    if schedule_receipt.get("field_evaluation_contract_sha256") != evaluation_hash:
        raise ValueError("field schedule receipt is not linked to the exact current field evaluation contract")
    if schedule_receipt.get("analysis_plan_sha256") != analysis_hash:
        raise ValueError("field schedule receipt is not linked to the exact current fresh-SENTINEL analysis plan")
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
