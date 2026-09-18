#!/usr/bin/env python3
"""Verify the immutable public pin of a fresh-SENTINEL field-schedule receipt.

The pin is the first commit that added the receipt path. Current bytes must still
match that first-add commit, so a later clean re-commit cannot silently replace the
pre-outcome schedule after outcomes become known.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    require_canonical_repo_path,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_STATUS = "PUBLIC_FIELD_ALLOCATION_EFFORT_SCHEDULE_READY_FOR_COMMIT"
VERIFIED_STATUS = "PUBLIC_FIELD_ALLOCATION_EFFORT_SCHEDULE_COMMITTED_AND_PINNED"
EXPECTED_ASSIGNMENT_IDENTITY = "FROZEN_ORDER_PREFIX_V1"
EXPECTED_ARM_SYMMETRY_IDENTITY = "ARM_SYMMETRIC_PREFIX_EFFORT_TEMPLATE_V1"
EXPECTED_EFFORT_METRIC = {
    "identity": "PERSON_MINUTES_V1",
    "unit": "person-minute",
    "formula": "search_minutes * observer_count",
}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _git(repo_root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo_root, check=True, capture_output=True, text=text)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _first_add_commit(repo: Path, relative: str) -> str:
    commits = [line.strip() for line in _git(repo, "log", "--diff-filter=A", "--format=%H", "--", relative).stdout.splitlines() if line.strip()]
    if not commits:
        raise ValueError("could not identify the first commit that added the public field-schedule receipt")
    return commits[-1]


def _validate_receipt(value: dict[str, Any]) -> None:
    if value.get("status") != EXPECTED_STATUS:
        raise ValueError("public field-schedule receipt is not in the commit-ready frozen state")
    if value.get("comparator_assignment_identity") != EXPECTED_ASSIGNMENT_IDENTITY:
        raise ValueError("public field-schedule receipt must preserve FROZEN_ORDER_PREFIX_V1")
    if value.get("arm_symmetry_identity") != EXPECTED_ARM_SYMMETRY_IDENTITY:
        raise ValueError("public field-schedule receipt must preserve ARM_SYMMETRIC_PREFIX_EFFORT_TEMPLATE_V1")
    if value.get("arm_symmetric_prefix_effort_template_verified") is not True:
        raise ValueError("public field-schedule receipt must prove arm-symmetric prefix/effort scheduling")
    if value.get("numeric_effort_metric") != EXPECTED_EFFORT_METRIC:
        raise ValueError("public field-schedule receipt must preserve PERSON_MINUTES_V1")
    for key in ("coordinate_bearing_data_included", "private_candidate_refs_included", "private_paths_included"):
        if value.get(key) is not False:
            raise ValueError(f"public field-schedule receipt must keep {key}=false")
    for key in (
        "private_candidate_membership_verified",
        "private_pre_field_receipt_hash_linkage_verified",
        "frozen_order_hash_linkage_verified",
        "frozen_order_prefix_verified",
    ):
        if value.get(key) is not True:
            raise ValueError(f"public field-schedule receipt must prove {key}")
    if value.get("prospective_field_outcomes_opened") is not False:
        raise ValueError("public field-schedule receipt cannot declare opened prospective outcomes")
    if value.get("field_outcomes_used_to_allocate") is not False:
        raise ValueError("public field-schedule receipt cannot be outcome-informed")
    if value.get("post_outcome_schedule_edits_allowed") is not False:
        raise ValueError("post-outcome schedule edits must remain forbidden")
    if value.get("outcome_opening_authorized_by_generation_alone") is not False:
        raise ValueError("schedule receipt generation alone cannot authorize outcome opening")
    if value.get("public_schedule_receipt_commit_required_before_outcome_opening") is not True:
        raise ValueError("schedule receipt must require immutable commit/pin")
    if value.get("public_schedule_receipt_commit_verified") is not False:
        raise ValueError("schedule receipt bytes cannot self-assert their commit verification")
    if value.get("final_pre_outcome_gate_required") is not True:
        raise ValueError("final pre-outcome linkage gate must remain required")
    if value.get("canonical_receipt_repo_path") != CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH:
        raise ValueError("field-schedule receipt does not preserve its canonical repository path")
    if value.get("candidate_order_public_receipt_repo_path") != CANONICAL_CANDIDATE_RECEIPT_REPO_PATH:
        raise ValueError("field-schedule receipt does not preserve the canonical candidate/order receipt path")
    if value.get("field_evaluation_contract_repo_path") != CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH:
        raise ValueError("field-schedule receipt does not preserve the canonical field evaluation contract path")
    if value.get("field_log_template_repo_path") != CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH:
        raise ValueError("field-schedule receipt does not preserve the canonical field-log template path")


def verify_public_field_schedule_pin(receipt_path: Path, *, repo_root: Path = ROOT, expected_pin_commit: str = "") -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    path = require_canonical_repo_path(
        Path(receipt_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        label="public field-schedule receipt",
    )
    if not path.is_file():
        raise ValueError(f"missing public field-schedule receipt: {path}")
    relative = path.relative_to(repo).as_posix()

    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("public field-schedule receipt must be a JSON object")
    _validate_receipt(value)

    try:
        _git(repo, "ls-files", "--error-unmatch", "--", relative)
    except subprocess.CalledProcessError as exc:
        raise ValueError("public field-schedule receipt is not tracked by git") from exc
    if _git(repo, "status", "--porcelain", "--", relative).stdout.strip():
        raise ValueError("public field-schedule receipt has uncommitted changes")

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    head_payload = _git(repo, "show", f"HEAD:{relative}", text=False).stdout
    if head_payload != payload:
        raise ValueError("working field-schedule receipt bytes do not equal HEAD")

    pin_commit = _first_add_commit(repo, relative)
    initial_payload = _git(repo, "show", f"{pin_commit}:{relative}", text=False).stdout
    if initial_payload != payload:
        raise ValueError("public field-schedule receipt bytes differ from the immutable first-add pin commit")
    if expected_pin_commit and pin_commit != str(expected_pin_commit).strip():
        raise ValueError("field-schedule receipt pin commit does not match the expected immutable commit")
    try:
        _git(repo, "merge-base", "--is-ancestor", pin_commit, head)
    except subprocess.CalledProcessError as exc:
        raise ValueError("field-schedule pin commit is not an ancestor of HEAD") from exc

    return {
        "schema_version": "cirsium-fresh-sentinel-public-field-schedule-pin-verification-v1",
        "status": VERIFIED_STATUS,
        "receipt_repo_path": relative,
        "receipt_sha256": _sha256_bytes(payload),
        "pin_commit": pin_commit,
        "pin_rule": "first commit adding the field-schedule receipt; later byte changes are forbidden",
        "verified_head": head,
        "public_schedule_receipt_commit_verified": True,
        "comparator_assignment_identity": EXPECTED_ASSIGNMENT_IDENTITY,
        "arm_symmetry_identity": EXPECTED_ARM_SYMMETRY_IDENTITY,
        "arm_symmetric_prefix_effort_template_verified": True,
        "numeric_effort_metric": EXPECTED_EFFORT_METRIC,
        "private_candidate_membership_verified": True,
        "frozen_order_prefix_verified": True,
        "prospective_field_outcomes_opened": False,
        "field_schedule_pin_gate_satisfied": True,
        "outcome_opening_gate_satisfied": False,
        "remaining_pre_outcome_gate": "Verify exact linkage among the immutable candidate/order receipt, field evaluation contract, and this immutable field-schedule receipt.",
        "authorization_scope": "field allocation/effort schedule provenance only; does not itself authorize outcome opening",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=Path(CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH))
    parser.add_argument("--expected-pin-commit", default="")
    args = parser.parse_args()
    result = verify_public_field_schedule_pin(args.receipt, expected_pin_commit=args.expected_pin_commit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
