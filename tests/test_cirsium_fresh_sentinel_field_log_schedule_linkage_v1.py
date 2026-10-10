from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
)
from research.validate_cirsium_fresh_sentinel_field_evaluation_contract_v1 import (
    DEFAULT_CONTRACT,
    DEFAULT_FIELD_LOG_TEMPLATE,
)
from research.validate_cirsium_fresh_sentinel_field_log_against_schedule_v1 import (
    validate_field_log_against_schedule,
)

UNITS = {
    "CIR02": "Cirsium inundatum",
    "CIR06": "Cirsium yezoalpinum",
    "CIR12": "Cirsium dipsacolepis",
    "CIR13": "Cirsium lineare",
}
ARMS = [
    "COVERAGE_THEN_FINE_STRUCTURE_V1",
    "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1",
    "MORTON_DYADIC_COVERAGE_ORDER_V1",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, list[dict[str, str]]]:
    repo = tmp_path / "repo"
    (repo / "validation").mkdir(parents=True)
    evaluation = repo / CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH
    template = repo / CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH
    evaluation.write_bytes(DEFAULT_CONTRACT.read_bytes())
    template.write_bytes(DEFAULT_FIELD_LOG_TEMPLATE.read_bytes())

    schedule_path = tmp_path / "private-field-schedule.json"
    assignments = []
    field_rows: list[dict[str, str]] = []
    with template.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))

    for unit, species in UNITS.items():
        for arm_index, arm in enumerate(ARMS):
            analysis_unit = f"{unit}-analysis-{arm_index}"
            assignments.append({
                "cohort_unit_id": unit,
                "analysis_unit_id": analysis_unit,
                "private_candidate_ref": f"{unit}-candidate-{arm_index}",
                "method_arm": arm,
                "visit_index": 1,
                "planned_effort_value": 60.0,
                "planned_search_minutes": 30.0,
                "planned_observer_count": 2,
            })
            row = {column: "" for column in header}
            row.update({
                "validation_unit_id": unit,
                "species_binomial": species,
                "method_arm": arm,
                "comparator_assignment": "FROZEN_ORDER_PREFIX_V1",
                "analysis_unit_id": analysis_unit,
                "visit_index": "1",
                "search_minutes": "30",
                "observer_count": "2",
                "field_outcome_state": "SEARCH_COMPLETED_NOT_DETECTED",
                "focal_detection_count": "0",
            })
            field_rows.append(row)

    schedule_path.write_text(json.dumps({"assignments": assignments}, indent=2) + "\n", encoding="utf-8")
    receipt = repo / CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH
    receipt.write_text(json.dumps({
        "status": "PUBLIC_FIELD_ALLOCATION_EFFORT_SCHEDULE_READY_FOR_COMMIT",
        "private_field_schedule_sha256": _sha256(schedule_path),
    }, indent=2) + "\n", encoding="utf-8")
    return repo, schedule_path, receipt, field_rows


def _write_log(path: Path, rows: list[dict[str, str]]) -> None:
    with DEFAULT_FIELD_LOG_TEMPLATE.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def test_complete_field_log_links_exactly_to_frozen_schedule(tmp_path: Path) -> None:
    repo, schedule, receipt, rows = _fixture(tmp_path)
    field_log = tmp_path / "private-field-log.csv"
    _write_log(field_log, rows)
    result = validate_field_log_against_schedule(field_log, schedule, receipt, repo_root=repo)
    assert result["status"] == "FRESH_SENTINEL_FIELD_LOG_EXACTLY_LINKED_TO_FROZEN_SCHEDULE"
    assert result["scheduled_visit_count"] == 12
    assert result["field_log_row_count"] == 12
    assert result["exact_one_row_per_scheduled_visit_verified"] is True
    assert result["field_outcome_state_visit_counts"]["SEARCH_COMPLETED_NOT_DETECTED"] == 12


def test_missing_scheduled_visit_is_rejected(tmp_path: Path) -> None:
    repo, schedule, receipt, rows = _fixture(tmp_path)
    field_log = tmp_path / "private-field-log.csv"
    _write_log(field_log, rows[:-1])
    with pytest.raises(ValueError, match="incomplete"):
        validate_field_log_against_schedule(field_log, schedule, receipt, repo_root=repo)


def test_unscheduled_extra_visit_is_rejected(tmp_path: Path) -> None:
    repo, schedule, receipt, rows = _fixture(tmp_path)
    extra = dict(rows[0])
    extra["analysis_unit_id"] = "UNSCHEDULED"
    field_log = tmp_path / "private-field-log.csv"
    _write_log(field_log, rows + [extra])
    with pytest.raises(ValueError, match="not a scheduled"):
        validate_field_log_against_schedule(field_log, schedule, receipt, repo_root=repo)


def test_completed_search_effort_must_match_frozen_schedule(tmp_path: Path) -> None:
    repo, schedule, receipt, rows = _fixture(tmp_path)
    rows[0]["search_minutes"] = "29"
    field_log = tmp_path / "private-field-log.csv"
    _write_log(field_log, rows)
    with pytest.raises(ValueError, match="completed search minutes"):
        validate_field_log_against_schedule(field_log, schedule, receipt, repo_root=repo)


def test_detection_state_requires_positive_detection_count(tmp_path: Path) -> None:
    repo, schedule, receipt, rows = _fixture(tmp_path)
    rows[0]["field_outcome_state"] = "SEARCH_COMPLETED_DETECTED_VERIFIED"
    rows[0]["focal_detection_count"] = "0"
    field_log = tmp_path / "private-field-log.csv"
    _write_log(field_log, rows)
    with pytest.raises(ValueError, match="positive focal_detection_count"):
        validate_field_log_against_schedule(field_log, schedule, receipt, repo_root=repo)


def test_nonbiological_failure_may_deviate_in_effort_without_becoming_absence(tmp_path: Path) -> None:
    repo, schedule, receipt, rows = _fixture(tmp_path)
    rows[0]["field_outcome_state"] = "ACCESS_FAILED"
    rows[0]["search_minutes"] = "0"
    rows[0]["observer_count"] = "2"
    field_log = tmp_path / "private-field-log.csv"
    _write_log(field_log, rows)
    result = validate_field_log_against_schedule(field_log, schedule, receipt, repo_root=repo)
    assert result["field_outcome_state_visit_counts"]["ACCESS_FAILED"] == 1
    assert result["field_outcome_state_visit_counts"]["SEARCH_COMPLETED_NOT_DETECTED"] == 11
