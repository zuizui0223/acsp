from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.export_cirsium_fresh_sentinel_public_freeze_receipt_v1 import (
    EXPECTED_UNITS,
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


def test_public_receipt_rejects_missing_order_hash(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    path = root / "CIR06" / "pre_field_freeze_receipt.json"
    value = json.loads(path.read_text())
    value["order_sha256"].pop("coverage_only")
    _write(path, value)
    with pytest.raises(ValueError):
        build_public_freeze_receipt(root)
