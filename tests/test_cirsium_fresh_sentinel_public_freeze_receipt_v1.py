from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_ANALYSIS_PLAN_REPO_PATH,
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
)
from research.export_cirsium_fresh_sentinel_public_freeze_receipt_v1 import (
    EXPECTED_UNITS,
    FIELD_EVALUATION_CONTRACT,
    build_public_freeze_receipt,
)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _private_root(tmp_path: Path) -> Path:
    root = tmp_path / "private"
    root.mkdir()
    top = {
        "status": "ALL_FOUR_PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
        "units": list(EXPECTED_UNITS),
        "method_identity": "COVERAGE_THEN_FINE_STRUCTURE_V1",
        "coverage_identity": "MORTON_DYADIC_COVERAGE_ORDER_V1",
        "coverage_only_comparator": "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1",
        "fine_spatial_comparator": "MORTON_DYADIC_COVERAGE_ORDER_V1",
        "fine_candidate_spacing_m": 100,
        "coarse_coverage_cell_size_m": 5000,
        "graph_radius_cells": 1,
        "field_outcomes_opened": False,
        "replacement_taxon_allowed": False,
        "public_hash_receipt_committed": False,
        "ready_for_public_hash_receipt_freeze": True,
        "ready_for_future_prospective_outcome_opening": False,
    }
    _write(root / "pre_field_freeze_receipt.json", top)
    for index, unit in enumerate(EXPECTED_UNITS):
        _write(
            root / unit / "pre_field_freeze_receipt.json",
            {
                "status": "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
                "cohort_unit_id": unit,
                "species_binomial": f"Species {index}",
                "feature_family": "OPEN_GRASSLAND_STRUCTURE",
                "candidate_frame_sha256": "a" * 64,
                "order_sha256": {
                    "coverage_then_fine_structure": "b" * 64,
                    "coverage_only": "c" * 64,
                    "fine_spatial_balance": "d" * 64,
                },
                "field_outcomes_opened": False,
                "replacement_taxon_allowed": False,
                "retuning_after_failure_allowed": False,
                "public_hash_receipt_committed": False,
            },
        )
    return root


def test_public_receipt_contains_only_hash_level_provenance(tmp_path: Path) -> None:
    receipt = build_public_freeze_receipt(_private_root(tmp_path))
    assert receipt["status"] == "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT"
    assert receipt["coordinate_bearing_data_included"] is False
    assert receipt["private_paths_included"] is False
    assert receipt["prospective_field_outcomes_opened"] is False
    assert receipt["public_safe_to_commit"] is True
    assert receipt["outcome_opening_authorized_by_generation_alone"] is False
    assert receipt["public_receipt_commit_required_before_outcome_opening"] is True
    assert receipt["public_receipt_commit_verified"] is False
    assert receipt["canonical_receipt_repo_path"] == CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    assert receipt["canonical_field_schedule_receipt_repo_path"] == CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH
    assert receipt["field_evaluation_contract"] == FIELD_EVALUATION_CONTRACT
    assert receipt["analysis_plan"] == CANONICAL_ANALYSIS_PLAN_REPO_PATH
    assert receipt["field_log_template"] == CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH
    assert receipt["field_allocation_and_effort_schedule_required_before_outcome_opening"] is True
    assert receipt["field_allocation_and_effort_schedule_pinned"] is False
    assert "closes only the candidate/order prescription gate" in receipt["outcome_opening_gate"]
    assert list(receipt["units"]) == list(EXPECTED_UNITS)
    rendered = json.dumps(receipt)
    assert str(tmp_path) not in rendered


def test_public_receipt_rejects_opened_outcome(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    path = root / "CIR12" / "pre_field_freeze_receipt.json"
    value = json.loads(path.read_text())
    value["field_outcomes_opened"] = True
    _write(path, value)
    with pytest.raises(ValueError):
        build_public_freeze_receipt(root)


def test_public_receipt_rejects_private_top_that_claims_opening_ready(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    path = root / "pre_field_freeze_receipt.json"
    value = json.loads(path.read_text())
    value["ready_for_future_prospective_outcome_opening"] = True
    _write(path, value)
    with pytest.raises(ValueError, match="authorize"):
        build_public_freeze_receipt(root)


def test_public_receipt_rejects_missing_order_hash(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    path = root / "CIR06" / "pre_field_freeze_receipt.json"
    value = json.loads(path.read_text())
    value["order_sha256"].pop("coverage_only")
    _write(path, value)
    with pytest.raises(ValueError):
        build_public_freeze_receipt(root)
