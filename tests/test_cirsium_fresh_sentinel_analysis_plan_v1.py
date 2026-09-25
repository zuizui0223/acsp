from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.validate_cirsium_fresh_sentinel_analysis_plan_v1 import (
    DEFAULT_PLAN,
    EXPECTED_PRIMARY_IDENTITY,
    validate_analysis_plan,
)


def _load() -> dict:
    return json.loads(DEFAULT_PLAN.read_text(encoding="utf-8"))


def _write(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "analysis-plan.json"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_repository_fresh_sentinel_analysis_plan_is_valid() -> None:
    result = validate_analysis_plan()
    assert result["status"] == "FRESH_SENTINEL_ANALYSIS_PLAN_VALID"
    assert result["primary_estimand_identity"] == EXPECTED_PRIMARY_IDENTITY
    assert result["primary_taxon_weights"] == {
        "CIR02": 0.25,
        "CIR06": 0.25,
        "CIR12": 0.25,
        "CIR13": 0.25,
    }
    assert result["all_four_taxa_required"] is True
    assert result["pooled_micro_primary_allowed"] is False
    assert result["prospective_outcomes_opened"] is False


def test_analysis_plan_rejects_taxon_drop_and_reweight(tmp_path: Path) -> None:
    value = _load()
    value["primary_evaluability"]["drop_non_evaluable_taxon_and_recompute_allowed"] = True
    with pytest.raises(ValueError, match="taxon handling"):
        validate_analysis_plan(_write(tmp_path, value))

    value = _load()
    value["primary_estimand"]["taxon_weights"]["CIR02"] = 0.4
    value["primary_estimand"]["taxon_weights"]["CIR06"] = 0.2
    value["primary_estimand"]["taxon_weights"]["CIR12"] = 0.2
    value["primary_estimand"]["taxon_weights"]["CIR13"] = 0.2
    with pytest.raises(ValueError, match="equal-weight"):
        validate_analysis_plan(_write(tmp_path, value))


def test_analysis_plan_rejects_pooled_micro_as_primary(tmp_path: Path) -> None:
    value = _load()
    value["primary_estimand"]["identity"] = "POOLED_MICRO_ARM_PROPORTIONS_DESCRIPTIVE_ONLY_V1"
    with pytest.raises(ValueError, match="primary cross-taxon estimand"):
        validate_analysis_plan(_write(tmp_path, value))


def test_analysis_plan_rejects_outcome_informed_threshold(tmp_path: Path) -> None:
    value = _load()
    value["primary_estimand"]["dichotomous_pass_fail_threshold"] = 0.01
    with pytest.raises(ValueError, match="dichotomous"):
        validate_analysis_plan(_write(tmp_path, value))

    value = _load()
    value["outcome_data_used_to_choose_analysis"] = True
    with pytest.raises(ValueError, match="outcome-informed"):
        validate_analysis_plan(_write(tmp_path, value))


def test_analysis_plan_rejects_nonbiological_failure_as_absence(tmp_path: Path) -> None:
    value = _load()
    value["failure_and_missingness_semantics"]["access_failure_is_absence"] = True
    with pytest.raises(ValueError, match="failure/missingness"):
        validate_analysis_plan(_write(tmp_path, value))


def test_analysis_plan_requires_primary_not_evaluable_when_any_taxon_missing(tmp_path: Path) -> None:
    value = _load()
    value["primary_evaluability"]["if_requirement_fails"] = "DROP_TAXON_AND_RECOMPUTE"
    with pytest.raises(ValueError, match="non-evaluability"):
        validate_analysis_plan(_write(tmp_path, value))
