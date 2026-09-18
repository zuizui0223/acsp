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
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    require_canonical_repo_path,
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
    counts = validated["assignment_count_by_unit_arm"]
    return {
        "schema_version": "cirsium-fresh-sentinel-public-field-schedule-receipt-v1",
        "status": PUBLIC_STATUS,
        "canonical_receipt_repo_path": CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        "candidate_order_public_receipt_repo_path": CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        "field_evaluation_contract_repo_path": CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        "field_log_template_repo_path": CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        "private_field_schedule_sha256": _sha256(private_schedule_path),
        "candidate_order_public_receipt_sha256": validated["candidate_order_public_receipt_sha256"],
        "field_evaluation_contract_sha256": validated["field_evaluation_contract_sha256"],
        "private_pre_field_top_receipt_sha256": membership["private_pre_field_top_receipt_sha256"],
        "cohort_unit_ids": validated["cohort_unit_ids"],
        "method_arms": validated["method_arms"],
        "primary_analysis_unit_identity": validated["primary_analysis_unit_identity"],
        "repeated_visit_aggregation_identity": validated["repeated_visit_aggregation_identity"],
        "shared_candidate_handling_identity": validated["shared_candidate_handling_identity"],
        "comparator_assignment_identity": validated["comparator_assignment_identity"],
        "numeric_effort_metric": validated["numeric_effort_metric"],
        "assignment_count": validated["assignment_count"],
        "assignment_count_by_unit_arm": counts,
        "selected_unique_candidate_count_by_unit_arm": membership["selected_unique_candidate_count_by_unit_arm"],
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
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--field-evaluation-contract", type=Path, required=True)
    parser.add_argument("--private-pre-field-root", type=Path, required=True)
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
    )
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "out_json": str(out_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
