#!/usr/bin/env python3
"""Validate a filled fresh-SENTINEL field log against the exact frozen private schedule."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    require_canonical_repo_path,
)
from research.validate_cirsium_fresh_sentinel_field_evaluation_contract_v1 import validate_field_evaluation_contract

ROOT = Path(__file__).resolve().parents[1]
FRESH_COHORT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_cohort_v1.csv"
ALLOWED_STATES = {
    "SEARCH_COMPLETED_DETECTED_VERIFIED",
    "SEARCH_COMPLETED_NOT_DETECTED",
    "SEARCH_COMPLETED_DETECTED_IDENTITY_UNRESOLVED",
    "ACCESS_FAILED",
    "PERMISSION_BLOCKED",
    "PHENOLOGY_NOT_EVALUABLE",
    "SEARCH_INCOMPLETE_OTHER",
}
COMPLETED_STATES = {
    "SEARCH_COMPLETED_DETECTED_VERIFIED",
    "SEARCH_COMPLETED_NOT_DETECTED",
    "SEARCH_COMPLETED_DETECTED_IDENTITY_UNRESOLVED",
}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


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


def _template_header(path: Path) -> list[str]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


def _species_by_unit(path: Path) -> dict[str, str]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    mapping = {str(row["cohort_unit_id"]): str(row["species_binomial"]) for row in rows}
    expected = {"CIR02", "CIR06", "CIR12", "CIR13"}
    if set(mapping) != expected:
        raise ValueError("fresh cohort mapping no longer contains exactly CIR02/CIR06/CIR12/CIR13")
    return mapping


def validate_field_log_against_schedule(
    field_log_path: Path,
    private_schedule_path: Path,
    public_schedule_receipt_path: Path,
    *,
    repo_root: Path = ROOT,
    field_evaluation_contract_path: Path | None = None,
    field_log_template_path: Path | None = None,
    cohort_path: Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    field_log = Path(field_log_path).resolve()
    schedule_path = Path(private_schedule_path).resolve()
    if _inside(field_log, repo):
        raise ValueError("filled prospective field log must remain outside the public repository")
    if _inside(schedule_path, repo):
        raise ValueError("private field schedule must remain outside the public repository")
    if not field_log.is_file():
        raise ValueError(f"missing filled field log: {field_log}")
    if not schedule_path.is_file():
        raise ValueError(f"missing private field schedule: {schedule_path}")

    schedule_receipt = require_canonical_repo_path(
        Path(public_schedule_receipt_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        label="public field-schedule receipt",
    )
    evaluation_path = require_canonical_repo_path(
        Path(field_evaluation_contract_path or CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH),
        repo_root=repo,
        expected_repo_path=CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        label="field evaluation contract",
    )
    template_path = require_canonical_repo_path(
        Path(field_log_template_path or CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH),
        repo_root=repo,
        expected_repo_path=CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        label="field-log template",
    )
    validate_field_evaluation_contract(evaluation_path, template_path)

    receipt = _load_json(schedule_receipt)
    if receipt.get("status") != "PUBLIC_FIELD_ALLOCATION_EFFORT_SCHEDULE_READY_FOR_COMMIT":
        raise ValueError("public field-schedule receipt is not frozen")
    if receipt.get("private_field_schedule_sha256") != _sha256(schedule_path):
        raise ValueError("private field schedule bytes do not match the immutable public schedule receipt")

    schedule = _load_json(schedule_path)
    assignments = schedule.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        raise ValueError("private field schedule lacks assignments")
    scheduled: dict[tuple[str, int], dict[str, Any]] = {}
    for row in assignments:
        key = (str(row.get("analysis_unit_id") or ""), int(row.get("visit_index")))
        if not key[0] or key in scheduled:
            raise ValueError(f"private schedule has invalid/duplicate analysis-unit visit key: {key}")
        scheduled[key] = row

    expected_header = _template_header(template_path)
    with field_log.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if (reader.fieldnames or []) != expected_header:
            raise ValueError("filled field-log header must exactly match the frozen canonical template")
        rows = list(reader)
    if not rows:
        raise ValueError("filled field log is empty")

    species_by_unit = _species_by_unit(Path(cohort_path or FRESH_COHORT))
    observed: dict[tuple[str, int], dict[str, Any]] = {}
    state_counts = {state: 0 for state in sorted(ALLOWED_STATES)}
    actual_person_minutes_by_unit_arm: dict[str, dict[str, float]] = {
        unit: {
            "COVERAGE_THEN_FINE_STRUCTURE_V1": 0.0,
            "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1": 0.0,
            "MORTON_DYADIC_COVERAGE_ORDER_V1": 0.0,
        }
        for unit in species_by_unit
    }

    for index, row in enumerate(rows, 1):
        analysis_unit = str(row.get("analysis_unit_id") or "").strip()
        try:
            visit_index = int(str(row.get("visit_index") or ""))
        except ValueError as exc:
            raise ValueError(f"field-log row {index} has invalid visit_index") from exc
        key = (analysis_unit, visit_index)
        if key not in scheduled:
            raise ValueError(f"field-log row {index} is not a scheduled analysis-unit visit: {key}")
        if key in observed:
            raise ValueError(f"duplicate field-log row for scheduled visit: {key}")
        plan = scheduled[key]

        unit = str(plan["cohort_unit_id"])
        arm = str(plan["method_arm"])
        if str(row.get("validation_unit_id") or "").strip() != unit:
            raise ValueError(f"field-log row {index} validation_unit_id differs from frozen schedule")
        if str(row.get("method_arm") or "").strip() != arm:
            raise ValueError(f"field-log row {index} method_arm differs from frozen schedule")
        if str(row.get("comparator_assignment") or "").strip() != "FROZEN_ORDER_PREFIX_V1":
            raise ValueError(f"field-log row {index} comparator_assignment differs from frozen schedule identity")
        if str(row.get("species_binomial") or "").strip() != species_by_unit[unit]:
            raise ValueError(f"field-log row {index} species_binomial differs from frozen cohort identity")

        state = str(row.get("field_outcome_state") or "").strip()
        if state not in ALLOWED_STATES:
            raise ValueError(f"field-log row {index} has invalid field_outcome_state: {state}")
        try:
            detection_count = int(str(row.get("focal_detection_count") or "0"))
        except ValueError as exc:
            raise ValueError(f"field-log row {index} focal_detection_count must be integer-valued") from exc
        if detection_count < 0:
            raise ValueError(f"field-log row {index} focal_detection_count cannot be negative")
        if state in {"SEARCH_COMPLETED_DETECTED_VERIFIED", "SEARCH_COMPLETED_DETECTED_IDENTITY_UNRESOLVED"} and detection_count <= 0:
            raise ValueError(f"field-log row {index} detection state requires positive focal_detection_count")
        if state == "SEARCH_COMPLETED_NOT_DETECTED" and detection_count != 0:
            raise ValueError(f"field-log row {index} non-detection requires focal_detection_count=0")

        try:
            minutes = float(str(row.get("search_minutes") or ""))
            observers = int(str(row.get("observer_count") or ""))
        except ValueError as exc:
            raise ValueError(f"field-log row {index} has malformed search_minutes/observer_count") from exc
        if not math.isfinite(minutes) or minutes < 0 or observers < 1:
            raise ValueError(f"field-log row {index} has invalid search_minutes/observer_count")
        actual_person_minutes = minutes * observers
        actual_person_minutes_by_unit_arm[unit][arm] += actual_person_minutes

        if state in COMPLETED_STATES:
            planned_minutes = float(plan["planned_search_minutes"])
            planned_observers = int(plan["planned_observer_count"])
            if not math.isclose(minutes, planned_minutes, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError(f"field-log row {index} completed search minutes differ from frozen schedule")
            if observers != planned_observers:
                raise ValueError(f"field-log row {index} completed search observer_count differs from frozen schedule")

        state_counts[state] += 1
        observed[key] = row

    missing = sorted(set(scheduled) - set(observed))
    extra = sorted(set(observed) - set(scheduled))
    if missing:
        raise ValueError(f"field log is incomplete; missing scheduled visits: {missing[:5]}")
    if extra:
        raise ValueError(f"field log contains unscheduled extra visits: {extra[:5]}")

    return {
        "status": "FRESH_SENTINEL_FIELD_LOG_EXACTLY_LINKED_TO_FROZEN_SCHEDULE",
        "scheduled_visit_count": len(scheduled),
        "field_log_row_count": len(rows),
        "exact_one_row_per_scheduled_visit_verified": True,
        "unscheduled_extra_rows": 0,
        "field_log_template_sha256": _sha256(template_path),
        "private_field_schedule_sha256": _sha256(schedule_path),
        "public_field_schedule_receipt_sha256": _sha256(schedule_receipt),
        "field_outcome_state_visit_counts": state_counts,
        "actual_person_minutes_by_unit_arm": actual_person_minutes_by_unit_arm,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-log", type=Path, required=True)
    parser.add_argument("--private-schedule", type=Path, required=True)
    parser.add_argument("--public-schedule-receipt", type=Path, default=Path(CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH))
    args = parser.parse_args()
    result = validate_field_log_against_schedule(
        args.field_log,
        args.private_schedule,
        args.public_schedule_receipt,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
