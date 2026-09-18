from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
)
from research.validate_cirsium_fresh_sentinel_field_evaluation_contract_v1 import DEFAULT_CONTRACT, DEFAULT_FIELD_LOG_TEMPLATE
from research.verify_cirsium_fresh_sentinel_pre_outcome_gate_v1 import FINAL_STATUS, verify_pre_outcome_gate
from research.verify_cirsium_fresh_sentinel_public_field_schedule_pin_v1 import verify_public_field_schedule_pin
from research.verify_cirsium_fresh_sentinel_public_freeze_pin_v1 import verify_public_freeze_pin


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "ACSP test")


def _candidate_receipt() -> dict:
    return {
        "status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT",
        "coordinate_bearing_data_included": False,
        "private_paths_included": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_choose_or_rank": False,
        "outcome_opening_authorized_by_generation_alone": False,
        "public_receipt_commit_required_before_outcome_opening": True,
        "public_receipt_commit_verified": False,
        "canonical_receipt_repo_path": CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        "canonical_field_schedule_receipt_repo_path": CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        "field_evaluation_contract": CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        "field_log_template": CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        "field_allocation_and_effort_schedule_required_before_outcome_opening": True,
        "field_allocation_and_effort_schedule_pinned": False,
    }


def _schedule_receipt(candidate: Path, evaluation: Path, *, candidate_hash_override: str = "") -> dict:
    return {
        "status": "PUBLIC_FIELD_ALLOCATION_EFFORT_SCHEDULE_READY_FOR_COMMIT",
        "canonical_receipt_repo_path": CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        "candidate_order_public_receipt_repo_path": CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        "field_evaluation_contract_repo_path": CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        "field_log_template_repo_path": CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        "candidate_order_public_receipt_sha256": candidate_hash_override or _sha256(candidate),
        "field_evaluation_contract_sha256": _sha256(evaluation),
        "method_arms": [
            "COVERAGE_THEN_FINE_STRUCTURE_V1",
            "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1",
            "MORTON_DYADIC_COVERAGE_ORDER_V1",
        ],
        "comparator_assignment_identity": "FROZEN_ORDER_PREFIX_V1",
        "arm_symmetry_identity": "ARM_SYMMETRIC_PREFIX_EFFORT_TEMPLATE_V1",
        "arm_symmetric_prefix_effort_template_verified": True,
        "numeric_effort_metric": {
            "identity": "PERSON_MINUTES_V1",
            "unit": "person-minute",
            "formula": "search_minutes * observer_count",
        },
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
        "outcome_opening_authorized_by_generation_alone": False,
        "public_schedule_receipt_commit_required_before_outcome_opening": True,
        "public_schedule_receipt_commit_verified": False,
        "final_pre_outcome_gate_required": True,
    }


def _prepare_repo(tmp_path: Path, *, candidate_hash_override: str = "") -> tuple[Path, Path, Path, Path, Path, str, str]:
    repo = tmp_path / "repo"
    _init_repo(repo)
    evaluation = repo / CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH
    log_template = repo / CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH
    evaluation.parent.mkdir(parents=True)
    evaluation.write_bytes(DEFAULT_CONTRACT.read_bytes())
    log_template.write_bytes(DEFAULT_FIELD_LOG_TEMPLATE.read_bytes())
    _git(repo, "add", "validation")
    _git(repo, "commit", "-m", "Freeze evaluation semantics")

    candidate = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    _write(candidate, _candidate_receipt())
    _git(repo, "add", CANONICAL_CANDIDATE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Pin candidate order receipt")
    candidate_pin = _git(repo, "rev-parse", "HEAD")

    schedule = repo / CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH
    _write(schedule, _schedule_receipt(candidate, evaluation, candidate_hash_override=candidate_hash_override))
    _git(repo, "add", CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Pin field schedule receipt")
    schedule_pin = _git(repo, "rev-parse", "HEAD")
    return repo, candidate, schedule, evaluation, log_template, candidate_pin, schedule_pin


def test_candidate_and_schedule_pins_link_to_authorize_outcome_opening(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, candidate_pin, schedule_pin = _prepare_repo(tmp_path)
    candidate_result = verify_public_freeze_pin(candidate, repo_root=repo, expected_pin_commit=candidate_pin)
    schedule_result = verify_public_field_schedule_pin(schedule, repo_root=repo, expected_pin_commit=schedule_pin)
    assert candidate_result["outcome_opening_gate_satisfied"] is False
    assert schedule_result["outcome_opening_gate_satisfied"] is False

    final = verify_pre_outcome_gate(
        candidate,
        schedule,
        evaluation,
        log_template,
        repo_root=repo,
        expected_candidate_pin_commit=candidate_pin,
        expected_schedule_pin_commit=schedule_pin,
    )
    assert final["status"] == FINAL_STATUS
    assert final["static_evaluation_semantics_valid"] is True
    assert final["candidate_order_pin_gate_satisfied"] is True
    assert final["field_schedule_pin_gate_satisfied"] is True
    assert final["exact_hash_linkage_satisfied"] is True
    assert final["private_candidate_membership_verified"] is True
    assert final["frozen_order_prefix_verified"] is True
    assert final["arm_symmetric_prefix_effort_template_verified"] is True
    assert final["prospective_field_outcomes_opened"] is False
    assert final["outcome_opening_gate_satisfied"] is True


def test_candidate_pin_alone_cannot_authorize_outcome_opening(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, candidate_pin, _ = _prepare_repo(tmp_path)
    _git(repo, "rm", CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Remove schedule receipt for negative test")
    candidate_result = verify_public_freeze_pin(candidate, repo_root=repo, expected_pin_commit=candidate_pin)
    assert candidate_result["outcome_opening_gate_satisfied"] is False
    with pytest.raises(ValueError, match="missing public field-schedule"):
        verify_pre_outcome_gate(candidate, schedule, evaluation, log_template, repo_root=repo)


def test_initially_pinned_wrong_candidate_hash_linkage_is_rejected(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, _, schedule_pin = _prepare_repo(tmp_path, candidate_hash_override="0" * 64)
    schedule_result = verify_public_field_schedule_pin(schedule, repo_root=repo, expected_pin_commit=schedule_pin)
    assert schedule_result["field_schedule_pin_gate_satisfied"] is True
    with pytest.raises(ValueError, match="exact immutable candidate/order receipt"):
        verify_pre_outcome_gate(candidate, schedule, evaluation, log_template, repo_root=repo)


def test_schedule_pin_rejects_missing_membership_proof(tmp_path: Path) -> None:
    repo, _, schedule, _, _, _, _ = _prepare_repo(tmp_path)
    value = json.loads(schedule.read_text())
    value["private_candidate_membership_verified"] = False
    schedule.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Create invalid membership receipt")
    with pytest.raises(ValueError, match="private_candidate_membership_verified"):
        verify_public_field_schedule_pin(schedule, repo_root=repo)


def test_schedule_pin_rejects_non_frozen_effort_metric(tmp_path: Path) -> None:
    repo, _, schedule, _, _, _, _ = _prepare_repo(tmp_path)
    value = json.loads(schedule.read_text())
    value["numeric_effort_metric"]["identity"] = "POSTHOC_METRIC"
    schedule.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Create invalid effort metric receipt")
    with pytest.raises(ValueError, match="PERSON_MINUTES_V1"):
        verify_public_field_schedule_pin(schedule, repo_root=repo)


def test_clean_recommit_of_changed_schedule_receipt_cannot_repin(tmp_path: Path) -> None:
    repo, _, schedule, _, _, _, original_schedule_pin = _prepare_repo(tmp_path)
    value = json.loads(schedule.read_text())
    value["tampered_after_pin"] = True
    schedule.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt schedule re-pin")
    with pytest.raises(ValueError, match="first-add"):
        verify_public_field_schedule_pin(schedule, repo_root=repo, expected_pin_commit=original_schedule_pin)


def test_evaluation_contract_change_after_schedule_pin_breaks_final_linkage(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, _, _ = _prepare_repo(tmp_path)
    value = json.loads(evaluation.read_text())
    value["promotion_claim_ceiling"]["post_pin_tamper"] = "not allowed"
    evaluation.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", evaluation.relative_to(repo).as_posix())
    _git(repo, "commit", "-m", "Attempt evaluation contract change")
    with pytest.raises(ValueError, match="exact current field evaluation contract"):
        verify_pre_outcome_gate(candidate, schedule, evaluation, log_template, repo_root=repo)


def test_candidate_pin_rejects_alternate_receipt_path_even_with_valid_bytes(tmp_path: Path) -> None:
    repo, candidate, _, _, _, _, _ = _prepare_repo(tmp_path)
    alternate = repo / "validation" / "alternate-candidate-receipt.json"
    alternate.write_bytes(candidate.read_bytes())
    _git(repo, "add", "validation/alternate-candidate-receipt.json")
    _git(repo, "commit", "-m", "Attempt alternate candidate pin")
    with pytest.raises(ValueError, match="canonical repo path"):
        verify_public_freeze_pin(alternate, repo_root=repo)


def test_schedule_pin_rejects_alternate_receipt_path_even_with_valid_bytes(tmp_path: Path) -> None:
    repo, _, schedule, _, _, _, _ = _prepare_repo(tmp_path)
    alternate = repo / "validation" / "alternate-field-schedule-receipt.json"
    alternate.write_bytes(schedule.read_bytes())
    _git(repo, "add", "validation/alternate-field-schedule-receipt.json")
    _git(repo, "commit", "-m", "Attempt alternate schedule pin")
    with pytest.raises(ValueError, match="canonical repo path"):
        verify_public_field_schedule_pin(alternate, repo_root=repo)


def test_final_gate_rejects_alternate_evaluation_contract_path(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, _, _ = _prepare_repo(tmp_path)
    alternate = repo / "validation" / "alternate-field-evaluation.json"
    alternate.write_bytes(evaluation.read_bytes())
    _git(repo, "add", "validation/alternate-field-evaluation.json")
    _git(repo, "commit", "-m", "Attempt alternate evaluation path")
    with pytest.raises(ValueError, match="canonical repo path"):
        verify_pre_outcome_gate(candidate, schedule, alternate, log_template, repo_root=repo)
