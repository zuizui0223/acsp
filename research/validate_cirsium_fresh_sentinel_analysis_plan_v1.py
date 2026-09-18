#!/usr/bin/env python3
"""Validate the frozen fresh-SENTINEL cross-taxon analysis plan pre-outcome.

The plan fixes the primary cross-taxon estimand, evaluability rules, secondary
aggregation roles, and claim ceiling. This validator reads no field outcomes.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_ANALYSIS_PLAN_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / CANONICAL_ANALYSIS_PLAN_REPO_PATH
EXPECTED_UNITS = ["CIR02", "CIR06", "CIR12", "CIR13"]
EXPECTED_ARMS = {
    "primary": "COVERAGE_THEN_FINE_STRUCTURE_V1",
    "coverage_only": "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1",
    "fine_spatial": "MORTON_DYADIC_COVERAGE_ORDER_V1",
}
EXPECTED_PRIMARY_IDENTITY = "EQUAL_TAXON_MACRO_PRIMARY_MINUS_COVERAGE_ONLY_V1"
EXPECTED_UNIT_ESTIMATOR = "RESOLVED_BINARY_SUCCESS_PROPORTION_V1"
EXPECTED_ARM_SYMMETRY = "ARM_SYMMETRIC_PREFIX_EFFORT_TEMPLATE_V1"


def _load(path: Path) -> dict[str, Any]:
    if not Path(path).is_file():
        raise ValueError(f"missing analysis plan: {path}")
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("analysis plan must be a JSON object")
    return value


def validate_analysis_plan(plan_path: Path = DEFAULT_PLAN) -> dict[str, Any]:
    plan = _load(Path(plan_path))
    if plan.get("schema_version") != "coverage-then-fine-structure-fresh-sentinel-analysis-plan-v1":
        raise ValueError("unexpected fresh-SENTINEL analysis-plan schema")
    if plan.get("status") != "FROZEN_PRE_OUTCOME_ANALYSIS_PLAN":
        raise ValueError("analysis plan must remain frozen pre-outcome")
    if plan.get("method_identity") != EXPECTED_ARMS["primary"]:
        raise ValueError("primary method identity changed")
    if plan.get("cohort_unit_ids") != EXPECTED_UNITS:
        raise ValueError("fresh cohort unit set/order changed")

    source = plan.get("source_contracts") or {}
    if source.get("field_evaluation_contract") != CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH:
        raise ValueError("analysis plan does not name the canonical field evaluation contract")
    if source.get("field_log_template") != CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH:
        raise ValueError("analysis plan does not name the canonical field-log template")

    inherited = plan.get("inherited_semantics") or {}
    expected_inherited = {
        "primary_analysis_unit_identity": "COHORT_ARM_CANDIDATE_V1",
        "repeated_visit_aggregation_identity": "ANY_VERIFIED_DETECTION_ELSE_ALL_RESOLVED_NONDETECTION_V1",
        "shared_candidate_handling_identity": "RETAIN_IN_EACH_NOMINATING_ARM_WITH_SHARED_OBSERVATION_V1",
        "numeric_effort_metric_identity": "PERSON_MINUTES_V1",
        "comparator_assignment_identity": "FROZEN_ORDER_PREFIX_V1",
        "arm_symmetry_identity": EXPECTED_ARM_SYMMETRY,
        "success_state": "SEARCH_COMPLETED_DETECTED_VERIFIED",
        "resolved_non_detection_state": "SEARCH_COMPLETED_NOT_DETECTED",
    }
    if inherited != expected_inherited:
        raise ValueError("analysis plan inherited field semantics changed")

    unit = plan.get("unit_level_estimator") or {}
    if unit.get("identity") != EXPECTED_UNIT_ESTIMATOR:
        raise ValueError("unit-level estimator identity changed")
    if unit.get("unresolved_identity_in_denominator") is not False:
        raise ValueError("identity-unresolved units cannot enter the resolved binary denominator")
    if unit.get("non_biological_or_non_evaluable_states_in_denominator") is not False:
        raise ValueError("non-biological/non-evaluable units cannot enter the resolved binary denominator")
    if unit.get("absence_imputation_allowed") is not False:
        raise ValueError("absence imputation must remain forbidden")

    primary = plan.get("primary_estimand") or {}
    if primary.get("identity") != EXPECTED_PRIMARY_IDENTITY:
        raise ValueError("primary cross-taxon estimand identity changed")
    if primary.get("contrast") != "COVERAGE_THEN_FINE_STRUCTURE_V1 minus COVERAGE_ONLY_STABLE_WITHIN_CELL_V1":
        raise ValueError("primary comparison changed")
    weights = primary.get("taxon_weights")
    if not isinstance(weights, dict) or list(weights) != EXPECTED_UNITS:
        raise ValueError("primary taxon weights must cover the exact four taxa in frozen order")
    values = [float(weights[unit_id]) for unit_id in EXPECTED_UNITS]
    if any(not math.isclose(value, 0.25, rel_tol=0, abs_tol=1e-12) for value in values):
        raise ValueError("primary estimator must equal-weight all four taxa")
    if primary.get("dichotomous_pass_fail_threshold") is not None:
        raise ValueError("no post-hoc dichotomous primary threshold is allowed")
    if primary.get("favorable_post_outcome_threshold_selection_allowed") is not False:
        raise ValueError("favorable post-outcome threshold selection must remain forbidden")

    evaluability = plan.get("primary_evaluability") or {}
    required_true = ("all_four_taxa_required",)
    for key in required_true:
        if evaluability.get(key) is not True:
            raise ValueError(f"primary evaluability weakened: {key}")
    required_false = (
        "drop_non_evaluable_taxon_and_recompute_allowed",
        "reweight_remaining_taxa_allowed",
        "substitute_taxon_allowed",
        "impute_missing_or_non_evaluable_taxon_contrast_allowed",
    )
    for key in required_false:
        if evaluability.get(key) is not False:
            raise ValueError(f"post-outcome taxon handling weakened: {key}")
    if evaluability.get("if_requirement_fails") != "PRIMARY_FOUR_TAXON_MACRO_NOT_EVALUABLE":
        raise ValueError("primary non-evaluability status changed")

    secondary = plan.get("secondary_estimands")
    if not isinstance(secondary, list) or [item.get("identity") for item in secondary if isinstance(item, dict)] != [
        "EQUAL_TAXON_MACRO_PRIMARY_MINUS_FINE_SPATIAL_V1",
        "EQUAL_TAXON_MACRO_COVERAGE_ONLY_MINUS_FINE_SPATIAL_V1",
        "POOLED_MICRO_ARM_PROPORTIONS_DESCRIPTIVE_ONLY_V1",
    ]:
        raise ValueError("secondary estimand identities/order changed")
    if secondary[2].get("role") != "secondary descriptive only; never substitutes for the equal-taxon primary estimand":
        raise ValueError("pooled micro analysis must remain secondary/descriptive")

    sensitivity = plan.get("sensitivity_reporting") or {}
    if sensitivity.get("post_outcome_choice_of_alternative_primary_aggregation_allowed") is not False:
        raise ValueError("post-outcome primary aggregation switching must remain forbidden")

    uncertainty = plan.get("uncertainty_and_decision") or {}
    if uncertainty.get("inferential_p_value_threshold_preregistered") is not False:
        raise ValueError("analysis plan must not invent an inferential p-value gate")
    if uncertainty.get("universal_promotion_threshold_preregistered") is not False:
        raise ValueError("four fresh taxa cannot self-authorize a universal promotion threshold")

    failures = plan.get("failure_and_missingness_semantics") or {}
    for key in (
        "identity_unresolved_is_absence",
        "access_failure_is_absence",
        "permission_blocked_is_absence",
        "phenology_not_evaluable_is_absence",
        "incomplete_search_is_absence",
        "cohort_replacement_after_outcome_allowed",
        "method_retuning_after_outcome_allowed",
    ):
        if failures.get(key) is not False:
            raise ValueError(f"failure/missingness semantics weakened: {key}")

    if plan.get("prospective_outcomes_opened") is not False:
        raise ValueError("analysis plan cannot declare opened prospective outcomes")
    if plan.get("outcome_data_used_to_choose_analysis") is not False:
        raise ValueError("analysis plan cannot be outcome-informed")
    if plan.get("post_outcome_primary_estimand_change_allowed") is not False:
        raise ValueError("post-outcome primary estimand changes must remain forbidden")

    return {
        "status": "FRESH_SENTINEL_ANALYSIS_PLAN_VALID",
        "analysis_plan_repo_path": CANONICAL_ANALYSIS_PLAN_REPO_PATH,
        "cohort_unit_ids": EXPECTED_UNITS,
        "primary_estimand_identity": EXPECTED_PRIMARY_IDENTITY,
        "unit_level_estimator_identity": EXPECTED_UNIT_ESTIMATOR,
        "primary_taxon_weights": {unit_id: 0.25 for unit_id in EXPECTED_UNITS},
        "all_four_taxa_required": True,
        "non_evaluable_primary_status": "PRIMARY_FOUR_TAXON_MACRO_NOT_EVALUABLE",
        "pooled_micro_primary_allowed": False,
        "prospective_outcomes_opened": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    args = parser.parse_args()
    result = validate_analysis_plan(args.plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
