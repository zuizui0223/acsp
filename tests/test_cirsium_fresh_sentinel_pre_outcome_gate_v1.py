from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_ANALYSIS_PLAN_REPO_PATH,
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
    CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH,
    CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
    CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
)
from research.validate_cirsium_fresh_sentinel_analysis_plan_v1 import DEFAULT_PLAN
from research.freeze_cirsium_fresh_sentinel_movement_constraint_v1 import build_movement_constraint
from research.validate_cirsium_fresh_sentinel_field_evaluation_contract_v1 import DEFAULT_CONTRACT, DEFAULT_FIELD_LOG_TEMPLATE
from research.verify_cirsium_fresh_sentinel_pre_outcome_gate_v1 import FINAL_STATUS, verify_pre_outcome_gate
from research.verify_cirsium_fresh_sentinel_public_field_schedule_pin_v1 import verify_public_field_schedule_pin
from research.verify_cirsium_fresh_sentinel_public_freeze_pin_v1 import verify_public_freeze_pin
from research.verify_cirsium_fresh_sentinel_range_sector_provenance_pin_v1 import EXPECTED, EXPECTED_UNITS


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


def _candidate_receipt(
    *,
    pregeometry_pin_commit: str,
    effort_sha256: str,
    movement_sha256: str,
    range_sha256: str,
) -> dict:
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
        "analysis_plan": CANONICAL_ANALYSIS_PLAN_REPO_PATH,
        "field_log_template": CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        "field_allocation_and_effort_schedule_required_before_outcome_opening": True,
        "field_allocation_and_effort_schedule_pinned": False,
        "pre_geometry_standardized_effort_pin_commit": pregeometry_pin_commit,
        "pre_geometry_standardized_effort_sha256": effort_sha256,
        "pre_geometry_movement_constraint_pin_commit": pregeometry_pin_commit,
        "pre_geometry_movement_constraint_sha256": movement_sha256,
        "pre_geometry_range_sector_provenance_pin_commit": pregeometry_pin_commit,
        "pre_geometry_range_sector_provenance_sha256": range_sha256,
        "pre_geometry_protocol_pins_verified_before_private_execution": True,
    }


def _effort_protocol() -> dict:
    return {
        "schema_version": "cirsium-fresh-sentinel-standardized-effort-protocol-v1",
        "status": "PRE_OUTCOME_STANDARDIZED_EFFORT_PROTOCOL_FROZEN",
        "cohort_unit_ids": ["CIR02", "CIR06", "CIR12", "CIR13"],
        "protocol_source_identity": "ACSP_CIRSIUM_FIXED_TIMED_SEARCH_3X30MIN_1OBSERVER_V1",
        "unit_effort": {
            unit: {
                "visits_per_candidate": 3,
                "search_minutes_per_visit": 30.0,
                "observer_count": 1,
            }
            for unit in ["CIR02", "CIR06", "CIR12", "CIR13"]
        },
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_effort": False,
        "candidate_identity_used_to_set_effort": False,
        "arm_specific_effort_allowed": False,
        "movement_constraint_used_to_set_effort": False,
        "post_outcome_effort_edits_allowed": False,
    }


def _range_provenance() -> dict:
    units = {}
    for unit in EXPECTED_UNITS:
        expected = EXPECTED[unit]
        p02 = bool(expected["p02_required"])
        units[unit] = {
            "species_binomial": expected["species_binomial"],
            "aza3_slot_id": expected["aza3_slot_id"],
            "range_sector_label": expected["range_sector_label"],
            "freeze_status": "FROZEN_FOR_FIELD_COLLECTION",
            "current_occurrence_supported": True,
            "permission_gate_satisfied": True,
            "target_locality_id": f"{unit}-LOCALITY",
            "private_exact_site_record_exists": True,
            "range_sector_geometry_may_now_be_materialized": True,
            "p02_first_validated_wild_population_required": p02,
            "p02_first_validated_wild_population_link_satisfied": p02,
        }
    return {
        "schema_version": "cirsium-fresh-sentinel-range-sector-provenance-v1",
        "status": "PRE_GEOMETRY_RANGE_SECTOR_PROVENANCE_FROZEN",
        "cohort_unit_ids": list(EXPECTED_UNITS),
        "aza3_exact_site_contract_version": "chapter3_exact_site_freeze_v8",
        "upstream_snapshot_commit": "a" * 40,
        "unit_provenance": units,
        "exact_coordinates_included": False,
        "sensitive_access_instructions_included": False,
        "prospective_acsp_field_outcomes_opened": False,
        "acsp_field_outcomes_used_to_define_sector": False,
        "post_geometry_edits_allowed": False,
        "post_outcome_edits_allowed": False,
        "public_safe_to_commit": True,
    }


def _capacity_profile(effort_path: Path) -> dict:
    return {
        "schema_version": "cirsium-fresh-sentinel-operational-capacity-profile-v1",
        "status": "PRE_OUTCOME_OPERATIONAL_CAPACITY_FROZEN",
        "cohort_unit_ids": ["CIR02", "CIR06", "CIR12", "CIR13"],
        "capacity_source_identity": "OSM_COMPLETE_COARSE_COVERAGE_SELECTED_COUNT_V1",
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": 5.0,
        "automatic_prefix_depth_method": "OSM_COMPLETE_COARSE_COVERAGE_SELECTED_COUNT_V1",
        "coarse_redundancy_scale_m": 5000.0,
        "coarse_representative_rule": "STABLE_HASH_WITHIN_FROZEN_COARSE_CELL_V1",
        "standardized_effort_protocol_sha256": _sha256(effort_path),
        "private_candidate_frame_sha256_by_unit": {
            unit: "0" * 64 for unit in ["CIR02", "CIR06", "CIR12", "CIR13"]
        },
        "unit_capacity": {
            unit: {
                "prefix_depth": 1,
                "visits_per_candidate": 3,
                "search_minutes_per_visit": 30.0,
                "observer_count": 1,
            }
            for unit in ["CIR02", "CIR06", "CIR12", "CIR13"]
        },
        "movement_provider_successful_by_unit": {
            unit: True for unit in ["CIR02", "CIR06", "CIR12", "CIR13"]
        },
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_capacity": False,
        "frozen_common_candidate_geometry_used_for_movement_capacity": True,
        "arm_rank_used_to_set_prefix_depth": False,
        "candidate_identity_or_coordinates_exported": False,
        "structural_score_used_to_set_prefix_depth": False,
        "arm_specific_capacity_allowed": False,
        "survey_days_input": False,
        "monetary_budget_input": False,
        "user_site_count_input": False,
        "user_coverage_target_input": False,
        "post_outcome_capacity_edits_allowed": False,
    }


def _schedule_receipt(candidate: Path, evaluation: Path, analysis_plan: Path, *, candidate_hash_override: str = "") -> dict:
    return {
        "status": "PUBLIC_FIELD_ALLOCATION_EFFORT_SCHEDULE_READY_FOR_COMMIT",
        "canonical_receipt_repo_path": CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        "candidate_order_public_receipt_repo_path": CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        "field_evaluation_contract_repo_path": CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        "analysis_plan_repo_path": CANONICAL_ANALYSIS_PLAN_REPO_PATH,
        "field_log_template_repo_path": CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        "candidate_order_public_receipt_sha256": candidate_hash_override or _sha256(candidate),
        "field_evaluation_contract_sha256": _sha256(evaluation),
        "analysis_plan_sha256": _sha256(analysis_plan),
        "field_log_template_sha256": _sha256(analysis_plan.parent / "cirsium_aza3_acsp_field_log_template_v1.csv"),
        "primary_cross_taxon_estimand_identity": "EQUAL_TAXON_MACRO_PRIMARY_MINUS_COVERAGE_ONLY_V1",
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
        "operational_capacity_profile_repo_path": CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
        "standardized_effort_protocol_repo_path": CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
        "operational_capacity_profile_sha256": _sha256(candidate.parents[1] / CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH),
        "standardized_effort_protocol_sha256": _sha256(candidate.parents[1] / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH),
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": 5.0,
        "automatic_prefix_depth_method": "OSM_COMPLETE_COARSE_COVERAGE_SELECTED_COUNT_V1",
        "coarse_redundancy_scale_m": 5000.0,
        "coarse_representative_rule": "STABLE_HASH_WITHIN_FROZEN_COARSE_CELL_V1",
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
    analysis_plan = repo / CANONICAL_ANALYSIS_PLAN_REPO_PATH
    analysis_plan.write_bytes(DEFAULT_PLAN.read_bytes())
    effort_protocol = repo / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH
    _write(effort_protocol, _effort_protocol())
    capacity_profile = repo / CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH
    _write(capacity_profile, _capacity_profile(effort_protocol))
    movement_constraint = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    _write(movement_constraint, build_movement_constraint())
    range_provenance = repo / CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH
    _write(range_provenance, _range_provenance())
    _git(repo, "add", "validation")
    _git(repo, "commit", "-m", "Freeze evaluation semantics")
    pregeometry_pin = _git(repo, "rev-parse", "HEAD")

    candidate = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    _write(
        candidate,
        _candidate_receipt(
            pregeometry_pin_commit=pregeometry_pin,
            effort_sha256=_sha256(effort_protocol),
            movement_sha256=_sha256(movement_constraint),
            range_sha256=_sha256(range_provenance),
        ),
    )
    _git(repo, "add", CANONICAL_CANDIDATE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Pin candidate order receipt")
    candidate_pin = _git(repo, "rev-parse", "HEAD")

    schedule = repo / CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH
    _write(schedule, _schedule_receipt(candidate, evaluation, analysis_plan, candidate_hash_override=candidate_hash_override))
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
    assert final["analysis_plan_valid"] is True
    assert final["field_log_template_sha256"] == _sha256(log_template)
    assert final["operational_capacity_profile_sha256"] == _sha256(repo / CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH)
    assert final["standardized_effort_protocol_sha256"] == _sha256(repo / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH)
    assert final["standardized_effort_protocol_pin_gate_satisfied"] is True
    assert final["standardized_effort_protocol_pin_commit"]
    assert final["movement_constraint_pin_gate_satisfied"] is True
    assert final["movement_constraint_pin_commit"]
    assert final["movement_constraint_pinned_before_candidate_prescription"] is True
    assert final["primary_cross_taxon_estimand_identity"] == "EQUAL_TAXON_MACRO_PRIMARY_MINUS_COVERAGE_ONLY_V1"
    assert final["exact_hash_linkage_satisfied"] is True
    assert final["private_candidate_membership_verified"] is True
    assert final["frozen_order_prefix_verified"] is True
    assert final["arm_symmetric_prefix_effort_template_verified"] is True
    assert final["capacity_schedule_linkage_verified"] is True
    assert final["standardized_effort_protocol_linkage_verified"] is True
    assert final["movement_constraint_mode"] == "osm_weighted_transport_network"
    assert final["max_network_transition_km"] == 5.0
    assert final["automatic_prefix_depth_method"] == "OSM_COMPLETE_COARSE_COVERAGE_SELECTED_COUNT_V1"
    assert final["user_site_count_input"] is False
    assert final["survey_days_input"] is False
    assert final["monetary_budget_input"] is False
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


def test_analysis_plan_change_after_schedule_pin_breaks_final_linkage(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, _, _ = _prepare_repo(tmp_path)
    analysis_plan = repo / CANONICAL_ANALYSIS_PLAN_REPO_PATH
    value = json.loads(analysis_plan.read_text())
    value["sensitivity_reporting"]["post_pin_tamper"] = "not allowed"
    analysis_plan.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_ANALYSIS_PLAN_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt analysis plan change")
    with pytest.raises(ValueError, match="exact current fresh-SENTINEL analysis plan|analysis plan"):
        verify_pre_outcome_gate(candidate, schedule, evaluation, log_template, repo_root=repo)


def test_final_gate_rejects_alternate_analysis_plan_path(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, _, _ = _prepare_repo(tmp_path)
    analysis_plan = repo / CANONICAL_ANALYSIS_PLAN_REPO_PATH
    alternate = repo / "validation" / "alternate-analysis-plan.json"
    alternate.write_bytes(analysis_plan.read_bytes())
    _git(repo, "add", "validation/alternate-analysis-plan.json")
    _git(repo, "commit", "-m", "Attempt alternate analysis-plan path")
    with pytest.raises(ValueError, match="canonical repo path"):
        verify_pre_outcome_gate(candidate, schedule, evaluation, log_template, alternate, repo_root=repo)


def test_field_log_template_change_after_schedule_pin_breaks_final_linkage(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, _, _ = _prepare_repo(tmp_path)
    log_template.write_text(log_template.read_text() + "extra", encoding="utf-8")
    _git(repo, "add", CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt field-log template change")
    with pytest.raises(ValueError, match="field-log template|missing required columns"):
        verify_pre_outcome_gate(candidate, schedule, evaluation, log_template, repo_root=repo)


def test_capacity_profile_change_after_schedule_pin_breaks_final_linkage(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, _, _ = _prepare_repo(tmp_path)
    capacity = repo / CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH
    value = json.loads(capacity.read_text())
    value["max_network_transition_km"] = 6.0
    capacity.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt movement-capacity change after schedule pin")
    with pytest.raises(ValueError, match="exact current operational capacity profile"):
        verify_pre_outcome_gate(candidate, schedule, evaluation, log_template, repo_root=repo)


def test_standardized_effort_change_after_schedule_pin_breaks_final_linkage(tmp_path: Path) -> None:
    repo, candidate, schedule, evaluation, log_template, _, _ = _prepare_repo(tmp_path)
    effort = repo / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH
    value = json.loads(effort.read_text())
    value["unit_effort"]["CIR02"]["search_minutes_per_visit"] = 31.0
    effort.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt standardized-effort change after schedule pin")
    with pytest.raises(ValueError, match="not linked to the exact standardized effort protocol|exact current standardized effort protocol"):
        verify_pre_outcome_gate(candidate, schedule, evaluation, log_template, repo_root=repo)
