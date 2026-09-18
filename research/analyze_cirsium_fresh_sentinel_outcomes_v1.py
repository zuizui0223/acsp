#!/usr/bin/env python3
"""Analyze fresh-SENTINEL prospective outcomes under the frozen v1 analysis plan.

The executable opens/reads prospective field outcomes only after the repository
pre-outcome gate passes. The pure summarizer is separately testable on synthetic
rows and contains no tuning or threshold selection.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_ANALYSIS_PLAN_REPO_PATH,
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
)
from research.validate_cirsium_fresh_sentinel_analysis_plan_v1 import validate_analysis_plan
from research.validate_cirsium_fresh_sentinel_field_log_against_schedule_v1 import (
    validate_field_log_against_schedule,
)
from research.verify_cirsium_fresh_sentinel_pre_outcome_gate_v1 import verify_pre_outcome_gate

ROOT = Path(__file__).resolve().parents[1]
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
PRIMARY = "COVERAGE_THEN_FINE_STRUCTURE_V1"
COVERAGE = "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1"
SPATIAL = "MORTON_DYADIC_COVERAGE_ORDER_V1"
ARMS = (PRIMARY, COVERAGE, SPATIAL)
VERIFIED = "SEARCH_COMPLETED_DETECTED_VERIFIED"
NONDETECTED = "SEARCH_COMPLETED_NOT_DETECTED"
UNRESOLVED = "SEARCH_COMPLETED_DETECTED_IDENTITY_UNRESOLVED"
NON_EVALUABLE = "NON_BIOLOGICAL_OR_NON_EVALUABLE"
PRIMARY_NOT_EVALUABLE = "PRIMARY_FOUR_TAXON_MACRO_NOT_EVALUABLE"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_rows(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _aggregate_analysis_unit(states: list[str]) -> str:
    if VERIFIED in states:
        return VERIFIED
    if states and all(state == NONDETECTED for state in states):
        return NONDETECTED
    if UNRESOLVED in states:
        return UNRESOLVED
    return NON_EVALUABLE


def _safe_prop(success: int, nondetect: int) -> float | None:
    denominator = success + nondetect
    return success / denominator if denominator > 0 else None


def _macro_contrast(
    by_unit_arm: dict[str, dict[str, dict[str, Any]]],
    left: str,
    right: str,
) -> tuple[str, dict[str, float | None], float | None]:
    contrasts: dict[str, float | None] = {}
    for unit in UNITS:
        lp = by_unit_arm[unit][left]["resolved_binary_success_proportion"]
        rp = by_unit_arm[unit][right]["resolved_binary_success_proportion"]
        contrasts[unit] = None if lp is None or rp is None else float(lp) - float(rp)
    if any(contrasts[unit] is None for unit in UNITS):
        return "NOT_EVALUABLE_ALL_FOUR_TAXA_REQUIRED", contrasts, None
    macro = sum(float(contrasts[unit]) for unit in UNITS) / 4.0
    return "EVALUABLE", contrasts, macro


def summarize_outcomes(
    private_schedule: dict[str, Any],
    field_rows: list[dict[str, str]],
) -> dict[str, Any]:
    assignments = private_schedule.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        raise ValueError("private schedule lacks assignments")

    assignment_by_visit: dict[tuple[str, int], dict[str, Any]] = {}
    planned_by_unit_arm = {unit: {arm: 0.0 for arm in ARMS} for unit in UNITS}
    candidate_sets = {unit: {arm: set() for arm in ARMS} for unit in UNITS}
    visit_count_by_unit_arm = {unit: {arm: 0 for arm in ARMS} for unit in UNITS}
    for row in assignments:
        analysis_unit = str(row["analysis_unit_id"])
        visit_index = int(row["visit_index"])
        key = (analysis_unit, visit_index)
        assignment_by_visit[key] = row
        unit = str(row["cohort_unit_id"])
        arm = str(row["method_arm"])
        planned_by_unit_arm[unit][arm] += float(row["planned_effort_value"])
        candidate_sets[unit][arm].add(str(row["private_candidate_ref"]))
        visit_count_by_unit_arm[unit][arm] += 1

    visits_by_analysis: dict[str, list[dict[str, str]]] = {}
    analysis_metadata: dict[str, tuple[str, str]] = {}
    actual_by_unit_arm = {unit: {arm: 0.0 for arm in ARMS} for unit in UNITS}
    visit_state_counts = {
        unit: {arm: {
            VERIFIED: 0,
            NONDETECTED: 0,
            UNRESOLVED: 0,
            "ACCESS_FAILED": 0,
            "PERMISSION_BLOCKED": 0,
            "PHENOLOGY_NOT_EVALUABLE": 0,
            "SEARCH_INCOMPLETE_OTHER": 0,
        } for arm in ARMS}
        for unit in UNITS
    }
    for row in field_rows:
        key = (str(row["analysis_unit_id"]), int(row["visit_index"]))
        plan = assignment_by_visit[key]
        unit = str(plan["cohort_unit_id"])
        arm = str(plan["method_arm"])
        analysis_unit = key[0]
        visits_by_analysis.setdefault(analysis_unit, []).append(row)
        analysis_metadata[analysis_unit] = (unit, arm)
        minutes = float(row["search_minutes"])
        observers = int(row["observer_count"])
        actual_by_unit_arm[unit][arm] += minutes * observers
        state = str(row["field_outcome_state"])
        visit_state_counts[unit][arm][state] += 1

    by_unit_arm = {
        unit: {
            arm: {
                "scheduled_unique_candidate_count": len(candidate_sets[unit][arm]),
                "scheduled_visit_count": visit_count_by_unit_arm[unit][arm],
                "planned_person_minutes": planned_by_unit_arm[unit][arm],
                "actual_person_minutes": actual_by_unit_arm[unit][arm],
                "resolved_verified_detection_count": 0,
                "resolved_non_detection_count": 0,
                "identity_unresolved_analysis_unit_count": 0,
                "non_biological_or_non_evaluable_analysis_unit_count": 0,
                "resolved_binary_denominator": 0,
                "resolved_binary_success_proportion": None,
                "visit_state_counts": visit_state_counts[unit][arm],
            }
            for arm in ARMS
        }
        for unit in UNITS
    }

    analysis_unit_states: dict[str, str] = {}
    for analysis_unit, rows in visits_by_analysis.items():
        unit, arm = analysis_metadata[analysis_unit]
        state = _aggregate_analysis_unit([str(row["field_outcome_state"]) for row in rows])
        analysis_unit_states[analysis_unit] = state
        target = by_unit_arm[unit][arm]
        if state == VERIFIED:
            target["resolved_verified_detection_count"] += 1
        elif state == NONDETECTED:
            target["resolved_non_detection_count"] += 1
        elif state == UNRESOLVED:
            target["identity_unresolved_analysis_unit_count"] += 1
        else:
            target["non_biological_or_non_evaluable_analysis_unit_count"] += 1

    for unit in UNITS:
        for arm in ARMS:
            target = by_unit_arm[unit][arm]
            success = int(target["resolved_verified_detection_count"])
            nondetect = int(target["resolved_non_detection_count"])
            target["resolved_binary_denominator"] = success + nondetect
            target["resolved_binary_success_proportion"] = _safe_prop(success, nondetect)

    primary_status, primary_taxon, primary_macro = _macro_contrast(by_unit_arm, PRIMARY, COVERAGE)
    p_vs_s_status, p_vs_s_taxon, p_vs_s_macro = _macro_contrast(by_unit_arm, PRIMARY, SPATIAL)
    c_vs_s_status, c_vs_s_taxon, c_vs_s_macro = _macro_contrast(by_unit_arm, COVERAGE, SPATIAL)

    pooled = {}
    for arm in ARMS:
        success = sum(int(by_unit_arm[unit][arm]["resolved_verified_detection_count"]) for unit in UNITS)
        nondetect = sum(int(by_unit_arm[unit][arm]["resolved_non_detection_count"]) for unit in UNITS)
        pooled[arm] = {
            "resolved_verified_detection_count": success,
            "resolved_non_detection_count": nondetect,
            "resolved_binary_denominator": success + nondetect,
            "resolved_binary_success_proportion": _safe_prop(success, nondetect),
        }

    micro_contrasts: dict[str, float | None] = {}
    for label, left, right in (
        ("primary_minus_coverage_only", PRIMARY, COVERAGE),
        ("primary_minus_fine_spatial", PRIMARY, SPATIAL),
        ("coverage_only_minus_fine_spatial", COVERAGE, SPATIAL),
    ):
        lp = pooled[left]["resolved_binary_success_proportion"]
        rp = pooled[right]["resolved_binary_success_proportion"]
        micro_contrasts[label] = None if lp is None or rp is None else float(lp) - float(rp)

    loo: dict[str, float] | None = None
    if primary_macro is not None:
        loo = {}
        for omitted in UNITS:
            retained = [float(primary_taxon[unit]) for unit in UNITS if unit != omitted]
            loo[omitted] = sum(retained) / 3.0

    overlap_counts = {}
    for unit in UNITS:
        overlap_counts[unit] = {
            "primary_and_coverage_only": len(candidate_sets[unit][PRIMARY] & candidate_sets[unit][COVERAGE]),
            "primary_and_fine_spatial": len(candidate_sets[unit][PRIMARY] & candidate_sets[unit][SPATIAL]),
            "coverage_only_and_fine_spatial": len(candidate_sets[unit][COVERAGE] & candidate_sets[unit][SPATIAL]),
            "all_three_arms": len(candidate_sets[unit][PRIMARY] & candidate_sets[unit][COVERAGE] & candidate_sets[unit][SPATIAL]),
        }

    return {
        "schema_version": "cirsium-fresh-sentinel-prospective-outcome-analysis-v1",
        "status": "FRESH_SENTINEL_PROSPECTIVE_ANALYSIS_COMPLETE" if primary_macro is not None else PRIMARY_NOT_EVALUABLE,
        "cohort_unit_ids": list(UNITS),
        "method_arms": list(ARMS),
        "analysis_unit_reporting_state_identity": "VERIFIED_THEN_ALL_NONDETECTION_THEN_UNRESOLVED_THEN_NON_EVALUABLE_V1",
        "by_taxon_by_arm": by_unit_arm,
        "primary_estimand": {
            "identity": "EQUAL_TAXON_MACRO_PRIMARY_MINUS_COVERAGE_ONLY_V1",
            "evaluability": primary_status,
            "per_taxon_contrast": primary_taxon,
            "equal_taxon_macro_mean": primary_macro,
            "taxon_weights": {unit: 0.25 for unit in UNITS},
            "dichotomous_pass_fail_threshold": None,
        },
        "secondary_estimands": {
            "primary_minus_fine_spatial": {
                "identity": "EQUAL_TAXON_MACRO_PRIMARY_MINUS_FINE_SPATIAL_V1",
                "evaluability": p_vs_s_status,
                "per_taxon_contrast": p_vs_s_taxon,
                "equal_taxon_macro_mean": p_vs_s_macro,
            },
            "coverage_only_minus_fine_spatial": {
                "identity": "EQUAL_TAXON_MACRO_COVERAGE_ONLY_MINUS_FINE_SPATIAL_V1",
                "evaluability": c_vs_s_status,
                "per_taxon_contrast": c_vs_s_taxon,
                "equal_taxon_macro_mean": c_vs_s_macro,
            },
            "pooled_micro_descriptive_only": {
                "identity": "POOLED_MICRO_ARM_PROPORTIONS_DESCRIPTIVE_ONLY_V1",
                "arm_summaries": pooled,
                "pairwise_contrasts": micro_contrasts,
                "may_replace_primary": False,
            },
        },
        "sensitivity": {
            "leave_one_taxon_out_primary_macro": loo,
            "role": "predeclared influence diagnostic only; never replaces the four-taxon primary",
        },
        "cross_arm_shared_candidate_overlap_counts": overlap_counts,
        "universal_promotion_authorized": False,
        "retuning_on_these_outcomes_authorized": False,
    }


def analyze_prospective_outcomes(
    field_log_path: Path,
    private_schedule_path: Path,
    *,
    repo_root: Path = ROOT,
    expected_candidate_pin_commit: str = "",
    expected_schedule_pin_commit: str = "",
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()

    # Critical ordering: verify every pre-outcome public gate before reading field outcomes.
    gate = verify_pre_outcome_gate(
        Path(CANONICAL_CANDIDATE_RECEIPT_REPO_PATH),
        Path(CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH),
        Path(CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH),
        Path(CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH),
        Path(CANONICAL_ANALYSIS_PLAN_REPO_PATH),
        repo_root=repo,
        expected_candidate_pin_commit=expected_candidate_pin_commit,
        expected_schedule_pin_commit=expected_schedule_pin_commit,
    )
    if gate.get("outcome_opening_gate_satisfied") is not True:
        raise ValueError("pre-outcome gate did not authorize prospective outcome opening")

    validate_analysis_plan(repo / CANONICAL_ANALYSIS_PLAN_REPO_PATH)
    schedule_receipt = _load_json(repo / CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH)
    schedule_path = Path(private_schedule_path).resolve()
    if schedule_receipt.get("private_field_schedule_sha256") != _sha256(schedule_path):
        raise ValueError("private field schedule does not match the immutably pinned public schedule receipt")

    # First read of prospective outcome rows occurs only after all gates above pass.
    linkage = validate_field_log_against_schedule(
        Path(field_log_path),
        schedule_path,
        repo / CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        repo_root=repo,
    )
    if linkage.get("exact_one_row_per_scheduled_visit_verified") is not True:
        raise ValueError("filled field log failed exact schedule linkage")

    schedule = _load_json(schedule_path)
    rows = _read_rows(Path(field_log_path))
    result = summarize_outcomes(schedule, rows)
    result["pre_outcome_gate_status"] = gate["status"]
    result["field_log_linkage_status"] = linkage["status"]
    result["candidate_order_pin_commit"] = gate["candidate_order_pin_commit"]
    result["field_schedule_pin_commit"] = gate["field_schedule_pin_commit"]
    result["analysis_plan_sha256"] = gate["analysis_plan_sha256"]
    result["field_log_sha256"] = _sha256(Path(field_log_path))
    result["private_field_schedule_sha256"] = _sha256(schedule_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-log", type=Path, required=True)
    parser.add_argument("--private-schedule", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--expected-candidate-pin-commit", default="")
    parser.add_argument("--expected-schedule-pin-commit", default="")
    args = parser.parse_args()
    if args.out_json.exists():
        raise SystemExit("refusing to overwrite an existing prospective outcome result")
    result = analyze_prospective_outcomes(
        args.field_log,
        args.private_schedule,
        expected_candidate_pin_commit=args.expected_candidate_pin_commit,
        expected_schedule_pin_commit=args.expected_schedule_pin_commit,
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "out_json": str(args.out_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
