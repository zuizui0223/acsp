from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd
import pytest

import research.derive_cirsium_fresh_sentinel_movement_capacity_v1 as movement
from research.analyze_cirsium_fresh_sentinel_outcomes_v1 import (
    analyze_prospective_outcomes,
)
from research.build_cirsium_fresh_sentinel_private_field_schedule_v1 import (
    ARM_TO_ORDER,
    ARMS,
    UNITS,
    build_private_field_schedule,
)
from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_ANALYSIS_PLAN_REPO_PATH,
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
    CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
    CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
)
from research.export_cirsium_fresh_sentinel_public_field_schedule_receipt_v1 import (
    build_public_field_schedule_receipt,
)
from research.export_cirsium_fresh_sentinel_public_freeze_receipt_v1 import (
    build_public_freeze_receipt,
)
from research.freeze_cirsium_fresh_sentinel_movement_constraint_v1 import build_movement_constraint
from research.validate_cirsium_fresh_sentinel_analysis_plan_v1 import DEFAULT_PLAN
from research.validate_cirsium_fresh_sentinel_field_evaluation_contract_v1 import (
    DEFAULT_CONTRACT,
    DEFAULT_FIELD_LOG_TEMPLATE,
)
from research.validate_cirsium_fresh_sentinel_field_log_against_schedule_v1 import (
    FRESH_COHORT,
)
from research.verify_cirsium_fresh_sentinel_pre_outcome_gate_v1 import (
    FINAL_STATUS,
    verify_pre_outcome_gate,
)


SPECIES = {
    "CIR02": "Cirsium inundatum",
    "CIR06": "Cirsium yezoalpinum",
    "CIR12": "Cirsium dipsacolepis",
    "CIR13": "Cirsium lineare",
}
FAMILIES = {
    "CIR02": "WETLAND_MOISTURE_STRUCTURE",
    "CIR06": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR12": "OPEN_GRASSLAND_STRUCTURE",
    "CIR13": "OPEN_GRASSLAND_STRUCTURE",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_order(path: Path, ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate_cell_id", "decision_rank"])
        writer.writeheader()
        for rank, candidate_id in enumerate(ids, 1):
            writer.writerow({"candidate_cell_id": candidate_id, "decision_rank": rank})


def _prepare_private_freeze(private_root: Path) -> None:
    for unit_index, unit in enumerate(UNITS):
        unit_dir = private_root / unit
        unit_dir.mkdir(parents=True, exist_ok=True)
        ids = [f"{unit}_cand_{index}" for index in range(1, 4)]
        frame = pd.DataFrame(
            {
                "candidate_cell_id": ids,
                "latitude": [35.0 + unit_index * 0.1 + index * 0.01 for index in range(3)],
                "longitude": [139.0 + unit_index * 0.1 + index * 0.01 for index in range(3)],
                "coverage_cell_id": [f"{unit}_cov_{index}" for index in range(1, 4)],
            }
        )
        frame_path = unit_dir / "candidate_frame_pre_field.csv"
        frame.to_csv(frame_path, index=False)

        permutations = {
            "coverage_then_fine_structure": ids,
            "coverage_only": [ids[1], ids[2], ids[0]],
            "fine_spatial_balance": [ids[2], ids[0], ids[1]],
        }
        order_files: dict[str, str] = {}
        order_hashes: dict[str, str] = {}
        for order_name, ordered_ids in permutations.items():
            filename = f"order_{order_name}.csv"
            path = unit_dir / filename
            _write_order(path, ordered_ids)
            order_files[order_name] = filename
            order_hashes[order_name] = _sha256(path)

        _write_json(
            unit_dir / "pre_field_freeze_receipt.json",
            {
                "status": "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
                "cohort_unit_id": unit,
                "species_binomial": SPECIES[unit],
                "feature_family": FAMILIES[unit],
                "candidate_frame_sha256": _sha256(frame_path),
                "order_files": order_files,
                "order_sha256": order_hashes,
                "field_outcomes_opened": False,
                "replacement_taxon_allowed": False,
                "retuning_after_failure_allowed": False,
            },
        )

    _write_json(
        private_root / "pre_field_freeze_receipt.json",
        {
            "status": "ALL_FOUR_PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
            "units": list(UNITS),
            "method_identity": "COVERAGE_THEN_FINE_STRUCTURE_V1",
            "coverage_identity": "MORTON_DYADIC_COVERAGE_ORDER_V1",
            "coverage_only_comparator": "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1",
            "fine_spatial_comparator": "MORTON_DYADIC_COVERAGE_ORDER_V1",
            "fine_candidate_spacing_m": 100,
            "coarse_coverage_cell_size_m": 5000,
            "graph_radius_cells": 1,
            "field_outcomes_opened": False,
            "replacement_taxon_allowed": False,
            "ready_for_public_hash_receipt_freeze": True,
            "ready_for_future_prospective_outcome_opening": False,
            "public_hash_receipt_committed": False,
        },
    )


def _effort_protocol() -> dict:
    return {
        "schema_version": "cirsium-fresh-sentinel-standardized-effort-protocol-v1",
        "status": "PRE_OUTCOME_STANDARDIZED_EFFORT_PROTOCOL_FROZEN",
        "cohort_unit_ids": list(UNITS),
        "protocol_source_identity": "ACSP_CIRSIUM_FIXED_TIMED_SEARCH_3X30MIN_1OBSERVER_V1",
        "unit_effort": {
            unit: {
                "visits_per_candidate": 3,
                "search_minutes_per_visit": 30.0,
                "observer_count": 1,
            }
            for unit in UNITS
        },
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_effort": False,
        "candidate_identity_used_to_set_effort": False,
        "arm_specific_effort_allowed": False,
        "movement_constraint_used_to_set_effort": False,
        "post_outcome_effort_edits_allowed": False,
    }


def _fake_osm_reachability(
    representatives: pd.DataFrame,
    *,
    max_network_transition_km: float,
    area_col: str,
):
    ids = representatives["candidate_patch_id"].astype(str).tolist()
    edges = pd.DataFrame(
        [
            {"from_patch_id": left, "to_patch_id": right}
            for index, left in enumerate(ids)
            for right in ids[index + 1 :]
        ]
    )
    empty = pd.DataFrame()
    audit = {
        "provider": {
            "successful_area_count": 1,
            "failed_area_count": 0,
        }
    }
    return edges, empty, empty, empty, empty, audit


def _copy_static_contracts(repo: Path) -> None:
    targets = {
        CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH: DEFAULT_CONTRACT,
        CANONICAL_ANALYSIS_PLAN_REPO_PATH: DEFAULT_PLAN,
        CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH: DEFAULT_FIELD_LOG_TEMPLATE,
    }
    for relative, source in targets.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(source).read_bytes())


def _species_by_unit() -> dict[str, str]:
    with Path(FRESH_COHORT).open(newline="", encoding="utf-8") as handle:
        return {
            str(row["cohort_unit_id"]): str(row["species_binomial"])
            for row in csv.DictReader(handle)
        }


def _write_synthetic_complete_field_log(
    path: Path,
    schedule_path: Path,
    template_path: Path,
) -> None:
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    with template_path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    species = _species_by_unit()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for assignment in schedule["assignments"]:
            unit = str(assignment["cohort_unit_id"])
            row = {key: "" for key in header}
            row.update(
                {
                    "validation_unit_id": unit,
                    "species_binomial": species[unit],
                    "method_arm": assignment["method_arm"],
                    "comparator_assignment": "FROZEN_ORDER_PREFIX_V1",
                    "analysis_unit_id": assignment["analysis_unit_id"],
                    "visit_index": assignment["visit_index"],
                    "search_minutes": assignment["planned_search_minutes"],
                    "observer_count": assignment["planned_observer_count"],
                    "field_outcome_state": "SEARCH_COMPLETED_NOT_DETECTED",
                    "focal_detection_count": 0,
                }
            )
            writer.writerow(row)


def test_synthetic_downstream_protocol_rehearsal_reaches_analysis_without_opening_real_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "ACSP rehearsal")

    private_root = tmp_path / "private-pre-field"
    private_schedule = tmp_path / "private-field-schedule.json"
    field_log = tmp_path / "synthetic-field-log.csv"
    _prepare_private_freeze(private_root)
    _copy_static_contracts(repo)

    effort_path = repo / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH
    _write_json(effort_path, _effort_protocol())
    movement_path = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    _write_json(movement_path, build_movement_constraint(5.0))

    _git(repo, "add", "validation")
    _git(repo, "commit", "-m", "Freeze synthetic pre-geometry protocols")
    movement_pin = _git(repo, "rev-parse", "HEAD")

    candidate_path = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    _write_json(candidate_path, build_public_freeze_receipt(private_root))
    _git(repo, "add", CANONICAL_CANDIDATE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Freeze synthetic candidate prescription")
    candidate_pin = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(movement, "build_osm_patch_reachability_edges", _fake_osm_reachability)
    capacity_path = repo / CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH
    capacity = movement.derive_operational_capacity_profile(
        private_root,
        effort_path,
        max_network_transition_km=5.0,
        out_json=capacity_path,
        repo_root=repo,
    )
    assert capacity["prospective_field_outcomes_opened"] is False
    assert all(capacity["movement_provider_successful_by_unit"].values())

    build_result = build_private_field_schedule(
        private_root,
        candidate_path,
        repo / CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        capacity_path,
        effort_path,
        private_schedule,
        repo_root=repo,
    )
    assert build_result["status"] == "PRIVATE_FIELD_SCHEDULE_BUILT_AND_VALIDATED"

    schedule_receipt = build_public_field_schedule_receipt(
        private_schedule,
        candidate_path,
        repo / CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        private_root,
        capacity_path,
        effort_path,
        repo / CANONICAL_ANALYSIS_PLAN_REPO_PATH,
        repo / CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        repo_root=repo,
    )
    schedule_receipt_path = repo / CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH
    _write_json(schedule_receipt_path, schedule_receipt)

    _git(repo, "add", "validation")
    _git(repo, "commit", "-m", "Pin synthetic field schedule provenance")
    schedule_pin = _git(repo, "rev-parse", "HEAD")

    gate = verify_pre_outcome_gate(
        candidate_path,
        schedule_receipt_path,
        repo / CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        repo / CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        repo / CANONICAL_ANALYSIS_PLAN_REPO_PATH,
        repo_root=repo,
        expected_candidate_pin_commit=candidate_pin,
        expected_schedule_pin_commit=schedule_pin,
        expected_movement_pin_commit=movement_pin,
    )
    assert gate["status"] == FINAL_STATUS
    assert gate["outcome_opening_gate_satisfied"] is True
    assert gate["prospective_field_outcomes_opened"] is False
    assert gate["standardized_effort_protocol_pin_gate_satisfied"] is True
    assert gate["movement_constraint_pin_gate_satisfied"] is True
    assert gate["movement_constraint_pinned_before_candidate_prescription"] is True

    _write_synthetic_complete_field_log(
        field_log,
        private_schedule,
        repo / CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    )
    result = analyze_prospective_outcomes(
        field_log,
        private_schedule,
        repo_root=repo,
        expected_candidate_pin_commit=candidate_pin,
        expected_schedule_pin_commit=schedule_pin,
    )
    assert result["status"] == "FRESH_SENTINEL_PROSPECTIVE_ANALYSIS_COMPLETE"
    assert result["pre_outcome_gate_status"] == FINAL_STATUS
    assert result["field_log_linkage_status"] == "FRESH_SENTINEL_FIELD_LOG_EXACTLY_LINKED_TO_FROZEN_SCHEDULE"
    assert result["primary_estimand"]["equal_taxon_macro_mean"] == pytest.approx(0.0)
    assert result["universal_promotion_authorized"] is False
    assert result["retuning_on_these_outcomes_authorized"] is False
