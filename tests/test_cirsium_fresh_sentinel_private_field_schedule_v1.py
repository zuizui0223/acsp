from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
)
from research.export_cirsium_fresh_sentinel_public_field_schedule_receipt_v1 import PUBLIC_STATUS, build_public_field_schedule_receipt
from research.validate_cirsium_fresh_sentinel_private_field_schedule_v1 import EXPECTED_ARMS, EXPECTED_UNITS, validate_private_field_schedule
from research.validate_cirsium_fresh_sentinel_private_schedule_membership_v1 import validate_private_schedule_membership

ANALYSIS_UNIT_IDENTITY = "COHORT_ARM_CANDIDATE_V1"
REPEAT_IDENTITY = "ANY_VERIFIED_DETECTION_ELSE_ALL_RESOLVED_NONDETECTION_V1"
REPEAT_RULE = "Within one COHORT_ARM_CANDIDATE_V1 unit, any SEARCH_COMPLETED_DETECTED_VERIFIED visit makes the unit a verified detection success. If no verified detection occurs, classify the unit SEARCH_COMPLETED_NOT_DETECTED only when every scheduled visit is SEARCH_COMPLETED_NOT_DETECTED. Identity-unresolved or non-biological/non-evaluable visits never become absence; without a verified detection they keep the unit outside the resolved binary denominator."
SHARED_IDENTITY = "RETAIN_IN_EACH_NOMINATING_ARM_WITH_SHARED_OBSERVATION_V1"
SHARED_RULE = "If the same physical candidate is selected by multiple frozen arms, retain one arm-specific analysis unit in every nominating arm; do not drop, substitute, or assign exclusive ownership. A single physical search may supply the same observed biological outcome to each nominating arm-specific unit, while PERSON_MINUTES_V1 is charged to each arm's preregistered counterfactual schedule. Cross-arm candidate overlap must be reported, and summed arm effort must not be interpreted as total expedition effort."


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _private_root(tmp_path: Path) -> tuple[Path, dict[str, dict[str, str]]]:
    root = tmp_path / "private-pre-field"
    root.mkdir()
    first: dict[str, dict[str, str]] = {}
    top_units = {}
    order_specs = {
        "coverage_then_fine_structure": (EXPECTED_ARMS[0], [0, 1, 2]),
        "coverage_only": (EXPECTED_ARMS[1], [1, 0, 2]),
        "fine_spatial_balance": (EXPECTED_ARMS[2], [2, 1, 0]),
    }
    for unit in EXPECTED_UNITS:
        unit_dir = root / unit
        ids = [f"{unit}-candidate-{i}" for i in range(1, 4)]
        frame = unit_dir / "candidate_frame_pre_field.csv"
        _write_csv(frame, [{"candidate_cell_id": value} for value in ids])
        order_files = {}
        order_hashes = {}
        first[unit] = {}
        for order_name, (arm, indexes) in order_specs.items():
            path = unit_dir / f"order_{order_name}.csv"
            ordered = [ids[index] for index in indexes]
            _write_csv(path, [{"candidate_cell_id": value, "decision_rank": rank} for rank, value in enumerate(ordered, 1)])
            order_files[order_name] = path.name
            order_hashes[order_name] = _sha256(path)
            first[unit][arm] = ordered[0]
        receipt = {
            "status": "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
            "cohort_unit_id": unit,
            "candidate_frame_sha256": _sha256(frame),
            "order_files": order_files,
            "order_sha256": order_hashes,
        }
        receipt_path = unit_dir / "pre_field_freeze_receipt.json"
        _write(receipt_path, receipt)
        top_units[unit] = {"candidate_frame_sha256": receipt["candidate_frame_sha256"], "order_sha256": order_hashes}
    _write(root / "pre_field_freeze_receipt.json", {
        "status": "ALL_FOUR_PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
        "units": list(EXPECTED_UNITS),
        "unit_receipts": top_units,
    })
    return root, first


def _public_inputs(repo: Path, private_root: Path) -> tuple[Path, Path]:
    candidate = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    evaluation = repo / CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH
    units = {}
    for unit in EXPECTED_UNITS:
        unit_dir = private_root / unit
        private_receipt = json.loads((unit_dir / "pre_field_freeze_receipt.json").read_text())
        units[unit] = {
            "candidate_frame_sha256": private_receipt["candidate_frame_sha256"],
            "order_sha256": private_receipt["order_sha256"],
            "private_unit_receipt_sha256": _sha256(unit_dir / "pre_field_freeze_receipt.json"),
        }
    _write(candidate, {
        "status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT",
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_choose_or_rank": False,
        "private_top_receipt_sha256": _sha256(private_root / "pre_field_freeze_receipt.json"),
        "units": units,
    })
    _write(evaluation, {
        "status": "FROZEN_PRE_OUTCOME_EVALUATION_SEMANTICS_ALLOCATION_SCHEDULE_PENDING",
        "cohort_unit_ids": list(EXPECTED_UNITS),
        "effort_accounting": {
            "numeric_effort_metric": {
                "identity": "PERSON_MINUTES_V1",
                "unit": "person-minute",
                "formula": "search_minutes * observer_count",
            }
        },
        "schedule_selection_mechanics": {
            "comparator_assignment_identity": "FROZEN_ORDER_PREFIX_V1",
        },
        "analysis_unit_and_repeated_visits": {
            "primary_analysis_unit_identity": ANALYSIS_UNIT_IDENTITY,
            "analysis_unit_id_must_map_one_to_one_to_cohort_arm_candidate": True,
            "visit_indices_must_be_contiguous_from_one_within_analysis_unit": True,
            "repeated_visit_aggregation_identity": REPEAT_IDENTITY,
            "repeated_visit_aggregation_rule": REPEAT_RULE,
            "shared_candidate_handling_identity": SHARED_IDENTITY,
            "shared_candidate_handling_rule": SHARED_RULE,
        },
    })
    return candidate, evaluation


def _schedule(candidate: Path, evaluation: Path, first: dict[str, dict[str, str]]) -> dict:
    assignments = []
    for unit in EXPECTED_UNITS:
        for arm_index, arm in enumerate(EXPECTED_ARMS):
            assignments.append({
                "cohort_unit_id": unit,
                "analysis_unit_id": f"{unit}-analysis-{arm_index}",
                "private_candidate_ref": first[unit][arm],
                "method_arm": arm,
                "visit_index": 1,
                "planned_effort_value": 60.0,
                "planned_search_minutes": 30.0,
                "planned_observer_count": 2,
            })
    return {
        "schema_version": "cirsium-fresh-sentinel-private-field-schedule-v1",
        "status": "PRIVATE_FIELD_ALLOCATION_AND_EFFORT_SCHEDULE_FROZEN",
        "cohort_unit_ids": list(EXPECTED_UNITS),
        "candidate_order_public_receipt_sha256": _sha256(candidate),
        "field_evaluation_contract_sha256": _sha256(evaluation),
        "primary_analysis_unit_identity": ANALYSIS_UNIT_IDENTITY,
        "repeated_visit_aggregation_identity": REPEAT_IDENTITY,
        "repeated_visit_aggregation_rule": REPEAT_RULE,
        "shared_candidate_handling_identity": SHARED_IDENTITY,
        "shared_candidate_handling_rule": SHARED_RULE,
        "comparator_assignment_identity": "FROZEN_ORDER_PREFIX_V1",
        "numeric_effort_metric": {
            "identity": "PERSON_MINUTES_V1",
            "unit": "person-minute",
            "formula": "search_minutes * observer_count",
        },
        "matched_effort_scope": "WITHIN_COHORT_UNIT_ACROSS_ALL_THREE_ARMS",
        "assignments": assignments,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_allocate": False,
        "post_outcome_schedule_edits_allowed": False,
    }


def _fixture(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    private_root, first = _private_root(tmp_path)
    candidate, evaluation = _public_inputs(repo, private_root)
    schedule_path = tmp_path / "private-field-schedule.json"
    value = _schedule(candidate, evaluation, first)
    _write(schedule_path, value)
    return repo, private_root, first, candidate, evaluation, schedule_path, value


def test_private_schedule_validates_and_public_receipt_leaks_no_candidate_refs(tmp_path: Path) -> None:
    repo, private_root, _, candidate, evaluation, schedule_path, _ = _fixture(tmp_path)
    validated = validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)
    membership = validate_private_schedule_membership(schedule_path, candidate, private_root, repo_root=repo)
    assert validated["assignment_count"] == 12
    assert membership["private_candidate_membership_verified"] is True
    assert membership["frozen_order_prefix_verified"] is True
    assert membership["numeric_effort_metric_verified"] is True
    receipt = build_public_field_schedule_receipt(schedule_path, candidate, evaluation, private_root, repo_root=repo)
    assert receipt["status"] == PUBLIC_STATUS
    assert receipt["canonical_receipt_repo_path"] == CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH
    assert receipt["candidate_order_public_receipt_repo_path"] == CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    assert receipt["field_evaluation_contract_repo_path"] == CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH
    assert receipt["field_log_template_repo_path"] == CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH
    assert receipt["private_candidate_membership_verified"] is True
    assert receipt["frozen_order_prefix_verified"] is True
    assert receipt["coordinate_bearing_data_included"] is False
    assert receipt["private_candidate_refs_included"] is False
    assert receipt["private_paths_included"] is False
    rendered = json.dumps(receipt)
    assert "CIR02-candidate" not in rendered
    assert str(tmp_path) not in rendered


def test_private_schedule_rejects_analysis_semantics_not_equal_to_contract(tmp_path: Path) -> None:
    repo, _, _, candidate, evaluation, schedule_path, value = _fixture(tmp_path)
    value["primary_analysis_unit_identity"] = "POSTHOC_ANALYSIS_UNIT"
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="analysis unit identity"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)

    value = _schedule(candidate, evaluation, _private_root(tmp_path / "repeat-fixture")[1]) if False else value
    value = json.loads(schedule_path.read_text())
    value["primary_analysis_unit_identity"] = ANALYSIS_UNIT_IDENTITY
    value["repeated_visit_aggregation_identity"] = "POSTHOC_REPEAT_RULE"
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="repeated-visit aggregation"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)

    value = json.loads(schedule_path.read_text())
    value["repeated_visit_aggregation_identity"] = REPEAT_IDENTITY
    value["shared_candidate_handling_identity"] = "POSTHOC_SHARED_RULE"
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="shared-candidate handling"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)


def test_private_schedule_rejects_analysis_unit_id_reused_for_different_arm_candidate(tmp_path: Path) -> None:
    repo, _, _, candidate, evaluation, schedule_path, value = _fixture(tmp_path)
    value["assignments"][1]["analysis_unit_id"] = value["assignments"][0]["analysis_unit_id"]
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="one-to-one"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)


def test_private_schedule_rejects_noncontiguous_visit_indices(tmp_path: Path) -> None:
    repo, _, _, candidate, evaluation, schedule_path, value = _fixture(tmp_path)
    value["assignments"][0]["visit_index"] = 2
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="contiguous"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)


def test_schedule_rejects_candidate_not_in_frozen_arm_order(tmp_path: Path) -> None:
    repo, private_root, _, candidate, _, schedule_path, value = _fixture(tmp_path)
    value["assignments"][0]["private_candidate_ref"] = "NOT-A-FROZEN-CANDIDATE"
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="not present in the exact frozen order"):
        validate_private_schedule_membership(schedule_path, candidate, private_root, repo_root=repo)


def test_schedule_rejects_skipping_higher_ranked_frozen_candidate(tmp_path: Path) -> None:
    repo, private_root, _, candidate, _, schedule_path, value = _fixture(tmp_path)
    value["assignments"][0]["private_candidate_ref"] = "CIR02-candidate-2"
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="no-skip frozen-order prefix"):
        validate_private_schedule_membership(schedule_path, candidate, private_root, repo_root=repo)


def test_schedule_rejects_private_receipt_not_bound_to_public_receipt(tmp_path: Path) -> None:
    repo, private_root, _, candidate, _, schedule_path, _ = _fixture(tmp_path)
    unit_receipt = private_root / "CIR06" / "pre_field_freeze_receipt.json"
    value = json.loads(unit_receipt.read_text())
    value["tampered"] = True
    _write(unit_receipt, value)
    with pytest.raises(ValueError, match="private unit receipt hash"):
        validate_private_schedule_membership(schedule_path, candidate, private_root, repo_root=repo)


def test_schedule_rejects_non_frozen_effort_metric(tmp_path: Path) -> None:
    repo, private_root, _, candidate, _, schedule_path, value = _fixture(tmp_path)
    value["numeric_effort_metric"]["identity"] = "POSTHOC_METRIC"
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="PERSON_MINUTES_V1"):
        validate_private_schedule_membership(schedule_path, candidate, private_root, repo_root=repo)


def test_schedule_rejects_inconsistent_person_minute_value(tmp_path: Path) -> None:
    repo, private_root, _, candidate, _, schedule_path, value = _fixture(tmp_path)
    value["assignments"][0]["planned_effort_value"] = 61.0
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="search_minutes \* observer_count"):
        validate_private_schedule_membership(schedule_path, candidate, private_root, repo_root=repo)


def test_private_schedule_rejects_effort_mismatch_between_arms(tmp_path: Path) -> None:
    repo, _, _, candidate, evaluation, schedule_path, value = _fixture(tmp_path)
    value["assignments"][0]["planned_effort_value"] = 61.0
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="not matched"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)


def test_private_schedule_rejects_wrong_candidate_receipt_hash(tmp_path: Path) -> None:
    repo, _, _, candidate, evaluation, schedule_path, value = _fixture(tmp_path)
    value["candidate_order_public_receipt_sha256"] = "0" * 64
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="exact candidate/order"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)


def test_private_schedule_rejects_outcome_field_in_assignment(tmp_path: Path) -> None:
    repo, _, _, candidate, evaluation, schedule_path, value = _fixture(tmp_path)
    value["assignments"][0]["field_outcome_state"] = "SEARCH_COMPLETED_DETECTED_VERIFIED"
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="keys"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)
