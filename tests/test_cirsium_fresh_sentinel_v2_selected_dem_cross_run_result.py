from __future__ import annotations

import copy
import json

import pytest

from research.verify_cirsium_fresh_sentinel_v2_selected_dem_cross_run_result import (
    RESULT, FROZEN_PATCH, check_summary, check_original_receipts,
)


def _sources() -> tuple[dict, dict]:
    return (
        json.loads(RESULT.read_text(encoding="utf-8")),
        json.loads(FROZEN_PATCH.read_text(encoding="utf-8")),
    )


def test_four_unit_publicly_frozen_numerical_comparison_is_coherent() -> None:
    result, frozen = _sources()
    assert check_summary(result, frozen) == {
        "status": "FOUR_UNIT_CROSS_RUN_FROZEN_RESULT_CONSISTENT", "unit_count": 4
    }
    assert result["units"]["CIR02"]["feature_precision_equal"]["slope100"] == {
        "0": True, "2": False, "4": False, "6": False, "8": False
    }
    assert result["limits"]["actual_selected_dem_comparison_to_first_source_available"] is False
    assert result["limits"]["full_source_order_reproducibility_proven"] is False


@pytest.mark.parametrize("unit", ["CIR02", "CIR06", "CIR12", "CIR13"])
def test_selected_dem_fingerprint_cannot_be_claimed_equivalent_to_first_run(unit: str) -> None:
    result, frozen = _sources()
    result["units"][unit]["selected_dem_sequence_equality_between_first_and_second"] = True
    with pytest.raises(ValueError, match="selected-source parity improperly claimed"):
        check_summary(result, frozen)


def test_frozen_slope_hash_mismatch_must_not_be_suppressed() -> None:
    result, frozen = _sources()
    result["units"]["CIR02"]["feature_precision_equal"]["slope100"]["2"] = True
    with pytest.raises(ValueError, match="rounded hash identity"):
        check_summary(result, frozen)


def test_frozen_patch_source_cannot_be_substituted() -> None:
    result, frozen = _sources()
    result["units"]["CIR06"]["original_patch_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="original patch changed"):
        check_summary(result, frozen)


def test_source_outcome_claims_cannot_be_promoted() -> None:
    result, frozen = _sources()
    result["limits"]["prospective_field_outcomes_opened"] = True
    with pytest.raises(ValueError, match="unsupported promotion"):
        check_summary(result, frozen)


def test_independent_partial_confirmation_is_not_four_unit_source_proof() -> None:
    result, frozen = _sources()
    result["independent_partial_confirmation"]["unit"] = "CIR06"
    with pytest.raises(ValueError, match="partial confirmation changed"):
        check_summary(result, frozen)


def test_source_files_are_required_as_complete_triplet() -> None:
    result, frozen = _sources()
    with pytest.raises((TypeError, ValueError, AttributeError)):
        check_original_receipts(result, frozen, None, None, None)
