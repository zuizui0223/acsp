from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research.audit_cirsium_fresh_sentinel_v2_source_replay import (
    UNITS,
    audit_two_replays,
)


def _receipt(unit: str) -> dict:
    marker = unit.lower().replace("cir", "")
    value = {
        "schema_version": "cirsium-fresh-sentinel-v2-fixed-gsi-unit-receipt-v2",
        "status": "FIXED_GSI_TERRAIN_EXECUTION_COMPLETE_PRE_OUTCOME",
        "cohort_unit_id": unit,
        "coordinate_bearing_artifacts_uploaded": False,
        "field_outcomes_opened": False,
        "grid": {"candidate_rows": 100, "private_grid_sha256": "a" * 64},
        "gsi": {
            "source_complete_rows": 90,
            "provider_unavailable_rows": 0,
            "terrain_vector_unavailable_rows": 10,
            "chunk_count": 2,
            "attributions": ["GSI DEM5A"],
            "terrain_feature_digest_sha256": "b" * 64,
            "private_gsi_frame_sha256": "c" * 64,
        },
        "structural": {
            "source_complete_rows": 80,
            "source_indeterminate_rows": 20,
            "structural_order_rows": 80,
            "source_state_digest_sha256": "d" * 64,
            "private_structural_order_sha256": "e" * 64,
        },
        "fine_patch_transfer": {
            "retained_support_cell_count": 2,
            "patch_count": 1,
            "singleton_patch_count": 0,
            "private_patch_sha256": "f" * 64,
            "transfer_is_validated_selector": False,
        },
    }
    return value


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    before, after = tmp_path / "original", tmp_path / "replay"
    frozen = {
        "status": "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED",
        "source_workflow_run": 37647225829,
        "units": {},
    }
    for unit in UNITS:
        o, r = _receipt(unit), _receipt(unit)
        if unit in ("CIR06", "CIR13"):
            r["gsi"]["terrain_feature_digest_sha256"] = "1" * 64
            r["gsi"]["private_gsi_frame_sha256"] = "2" * 64
            r["structural"]["private_structural_order_sha256"] = "3" * 64
        for root, row in ((before, o), (after, r)):
            path = root / unit / f"{unit}_receipt.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(row), encoding="utf-8")
        frozen["units"][unit] = {
            "fine_grid_candidate_count": 100,
            "gsi_source_complete_count": 90,
            "structural_source_complete_count": 80,
            "transferred_2p5pct_retained_cell_count": 2,
            "complete_link_patch_count": 1,
            "structural_order_sha256": "e" * 64,
            "private_patch_sha256": "f" * 64,
        }
    frozen_file = tmp_path / "frozen.json"
    frozen_file.write_text(json.dumps(frozen), encoding="utf-8")
    return before, after, frozen_file


def test_replay_recovers_four_identical_patch_files_but_two_upstream_drifts(tmp_path: Path) -> None:
    old, new, frozen = _setup(tmp_path)
    result = audit_two_replays(old, new, frozen_result_path=frozen)
    assert result["status"] == "UPSTREAM_GSI_REPLAY_DRIFT_FINAL_PATCHES_IDENTICAL"
    summary = result["summary"]
    assert summary["gsi_terrain_feature_digest_matching_units"] == ["CIR02", "CIR12"]
    assert summary["structural_full_order_sha_matching_units"] == ["CIR02", "CIR12"]
    assert summary["final_patch_csv_sha_matching_units"] == list(UNITS)
    assert summary["all_four_patch_representations_byte_identical"] is True
    assert summary["upstream_gsi_content_reproducible_all_units"] is False
    assert summary["upstream_drift_cause_identified"] is False
    assert result["claim_boundary"]["matching_patch_sha_rescues_upstream_reproducibility"] is False
    assert result["claim_boundary"]["private_coordinates_opened"] is False


def test_bad_replay_denominator_is_rejected(tmp_path: Path) -> None:
    old, new, frozen = _setup(tmp_path)
    path = new / "CIR13" / "CIR13_receipt.json"
    row = json.loads(path.read_text())
    row["gsi"]["source_complete_rows"] = 89
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="GSI denominator not preserved"):
        audit_two_replays(old, new, frozen_result_path=frozen)


def test_field_outcome_or_fake_selector_promotion_is_rejected(tmp_path: Path) -> None:
    old, new, frozen = _setup(tmp_path)
    path = new / "CIR02" / "CIR02_receipt.json"
    row = json.loads(path.read_text())
    row["field_outcomes_opened"] = True
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="opened field outcomes"):
        audit_two_replays(old, new, frozen_result_path=frozen)
    row["field_outcomes_opened"] = False
    row["fine_patch_transfer"]["transfer_is_validated_selector"] = True
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot promote patch selector"):
        audit_two_replays(old, new, frozen_result_path=frozen)


def test_original_must_match_previously_frozen_public_source(tmp_path: Path) -> None:
    old, new, frozen = _setup(tmp_path)
    path = old / "CIR06" / "CIR06_receipt.json"
    row = json.loads(path.read_text())
    row["structural"]["private_structural_order_sha256"] = "1" * 64
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="original SHA differs from frozen PR248"):
        audit_two_replays(old, new, frozen_result_path=frozen)


def test_source_state_equal_does_not_imply_source_feature_equal(tmp_path: Path) -> None:
    old, new, frozen = _setup(tmp_path)
    result = audit_two_replays(old, new, frozen_result_path=frozen)
    assert result["units"]["CIR06"]["source_state_digest_identical"] is True
    assert result["units"]["CIR06"]["digests"][
        "gsi.terrain_feature_digest_sha256"
    ]["byte_or_digest_equal"] is False
