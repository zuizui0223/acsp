from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from research.verify_cirsium_fresh_sentinel_v2_frozen_patch_topology_result import (
    ORIGINAL_PATH,
    RESULT_PATH,
    TOPOLOGY_KEYS,
    UNITS,
    verify_exact_saved_receipts,
    verify_frozen_public_summary,
)


def _read() -> tuple[dict, dict]:
    return (
        json.loads(RESULT_PATH.read_text(encoding="utf-8")),
        json.loads(ORIGINAL_PATH.read_text(encoding="utf-8")),
    )


def test_frozen_four_unit_result_matches_original_patch_hashes_and_denominators() -> None:
    result, source = _read()
    audit = verify_frozen_public_summary(result, source)
    assert audit == {"status": "PUBLIC_TOPOLOGY_FREEZE_CONSISTENT", "unit_count": 4}
    assert result["distinct_declared_structural_family_count"] == 3
    assert set(result["cohort_unit_ids"]) == set(UNITS)
    assert sum(x["disconnected_patch_count"] for x in result["units"].values()) == 4168
    assert result["units"]["CIR13"]["disconnected_patch_count"] == 278
    assert result["interpretation"]["full_structural_order_sha_replay_tested_by_this_route"] is False
    assert result["interpretation"]["prospective_field_outcomes_opened"] is False


@pytest.mark.parametrize(
    ("unit", "edit", "error"),
    [
        ("CIR02", lambda row: row.update(disconnected_patch_count=321), "disconnected patch accounting"),
        ("CIR06", lambda row: row.update(connected_patch_count=592), "disconnected patch accounting"),
        ("CIR12", lambda row: row.update(disconnected_patch_fraction=0.0), "patch fraction incorrect"),
        ("CIR13", lambda row: row.update(cells_in_disconnected_patches=16000), "disconnected cell accounting"),
        ("CIR02", lambda row: row.update(verified_original_patch_sha256="0" * 64), "original frozen patch SHA"),
        ("CIR06", lambda row: row.update(receipt_content_sha256="broken"), "receipt SHA missing"),
        ("CIR12", lambda row: row.update(original_frozen_singleton_patch_count=42), "singleton count changed"),
    ],
)
def test_corrupted_public_summary_fails_closed(unit, edit, error) -> None:
    result, source = _read()
    edit(result["units"][unit])
    with pytest.raises(ValueError, match=error):
        verify_frozen_public_summary(result, source)


def test_cohort_or_field_outcome_promotion_fails_closed() -> None:
    result, source = _read()
    result["interpretation"]["prospective_field_outcomes_opened"] = True
    with pytest.raises(ValueError, match="interpretation boundary"):
        verify_frozen_public_summary(result, source)
    result, source = _read()
    result["distinct_declared_structural_family_count"] = 4
    with pytest.raises(ValueError, match="structural policy family"):
        verify_frozen_public_summary(result, source)


def _receipt_payload(unit: str, result: dict) -> bytes:
    row = result["units"][unit]
    topology = {
        "status": "FROZEN_PATCH_MASK_TOPOLOGY_AUDITED_UPSTREAM_UNCERTAINTY_RETAINED",
        **{
            key: row[key] for key in TOPOLOGY_KEYS
            if key in row and key != "cells_in_disconnected_patch_fraction"
        },
        "field_selector_validation": False,
        "ecological_connectivity_claim_authorized": False,
        "full_structural_order_reproduction_tested": False,
    }
    payload = {
        "status": "FIXED_GSI_TERRAIN_EXECUTION_COMPLETE_PRE_OUTCOME",
        "cohort_unit_id": unit,
        "coordinate_bearing_artifacts_uploaded": False,
        "field_outcomes_opened": False,
        "fine_patch_transfer": {
            "transfer_is_validated_selector": False,
            "private_patch_sha256": row["verified_original_patch_sha256"],
        },
        "frozen_patch_membership_topology": topology,
    }
    return (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")


def _synthetic_public_receipts(tmp_path: Path) -> tuple[dict, dict]:
    report, source = _read()
    for unit in UNITS:
        path = tmp_path / unit / f"{unit}_receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _receipt_payload(unit, report)
        path.write_bytes(data)
        report["units"][unit]["receipt_content_sha256"] = hashlib.sha256(data).hexdigest()
    return report, source


def test_four_byte_pinned_source_receipts_validate_without_coordinates(tmp_path: Path) -> None:
    report, source = _synthetic_public_receipts(tmp_path)
    audit = verify_exact_saved_receipts(tmp_path, report, source)
    assert audit["status"] == "FOUR_PUBLIC_SOURCE_RECEIPTS_REVERIFIED"
    assert audit["reverified_units"] == list(UNITS)
    assert audit["coordinate_bearing_data_exposed"] is False


def test_tampered_saved_bytes_fail_before_topology_inference(tmp_path: Path) -> None:
    report, source = _synthetic_public_receipts(tmp_path)
    file = tmp_path / "CIR06" / "CIR06_receipt.json"
    file.write_bytes(file.read_bytes() + b" ")
    with pytest.raises(ValueError, match="receipt bytes differ"):
        verify_exact_saved_receipts(tmp_path, report, source)


def test_coordinate_leak_even_with_updated_receipt_hash_is_rejected(tmp_path: Path) -> None:
    report, source = _synthetic_public_receipts(tmp_path)
    file = tmp_path / "CIR13" / "CIR13_receipt.json"
    obj = json.loads(file.read_bytes())
    obj["latitude"] = 0.0
    data = (json.dumps(obj, sort_keys=True) + "\n").encode("utf-8")
    file.write_bytes(data)
    report["units"]["CIR13"]["receipt_content_sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(ValueError, match="leaked location keys"):
        verify_exact_saved_receipts(tmp_path, report, source)
