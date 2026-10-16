"""Fail-closed tests for eight original SHA-pinned public GSI unit receipts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.verify_cirsium_fresh_sentinel_v2_complete_selected_mosaic_replay import (
    FROZEN, RESULT, UNITS, check_frozen_summary, verify_exact_receipts,
)


def _inputs():
    return json.loads(RESULT.read_text()), json.loads(FROZEN.read_text())


def test_four_unit_public_evidence_freeze_is_explicitly_noncaual():
    record, source = _inputs()
    r = check_frozen_summary(record, source)
    assert r["status"] == "FOUR_UNIT_SOURCE_SELECTED_COMPARISON_SUMMARY_COHERENT"
    assert r["compared_units"] == list(UNITS)
    assert record["aggregate"]["same_actually_selected_mosaic_sequence_units"] == 3
    assert record["aggregate"]["same_structural_full_order_units"] == 2
    assert record["aggregate"]["same_exact_frozen_patch_sha_units"] == 4
    assert record["claim_boundary"]["full_structural_order_reproducibility_achieved_all_four"] is False
    assert record["claim_boundary"]["prospective_field_outcomes_opened"] is False


@pytest.mark.parametrize("unit", UNITS)
def test_cannot_change_original_frozen_patch_digest(unit):
    r, f = _inputs()
    r["units"][unit]["original_frozen_patch_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="original frozen patch SHA"):
        check_frozen_summary(r, f)


def test_cir02_same_actual_dem_not_suppressed():
    r, f = _inputs()
    r["units"]["CIR02"]["feature_precision_equal"]["slope100"]["2"] = True
    with pytest.raises(ValueError, match="original feature fingerprint"):
        check_frozen_summary(r, f)


def test_cir12_source_change_cannot_be_reclassified_as_identical():
    r, f = _inputs()
    r["units"]["CIR12"]["actual_selected_mosaic_content_sequence_equal"] = True
    with pytest.raises(ValueError, match="actual source"):
        check_frozen_summary(r, f)


def test_unavailable_biological_outcomes_cannot_be_imputed():
    r, f = _inputs()
    r["claim_boundary"]["field_selector_validated"] = True
    with pytest.raises(ValueError, match="unsupported source or biological promotion"):
        check_frozen_summary(r, f)


def test_incomplete_eight_receipt_source_must_fail(tmp_path: Path):
    r, f = _inputs()
    with pytest.raises(ValueError, match="original public GSI receipt missing"):
        verify_exact_receipts(tmp_path / "missing_a", tmp_path / "missing_b", r, f)


def test_exactly_eight_original_receipt_hashes_required():
    r, f = _inputs()
    r["units"]["CIR13"]["source_b_receipt_content_sha256"] = "too-short"
    with pytest.raises(ValueError, match="receipt or selected DEM SHA"):
        check_frozen_summary(r, f)
