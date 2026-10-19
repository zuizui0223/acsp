from __future__ import annotations

import copy
import json

import pytest

from research.compare_cirsium_fresh_sentinel_v2_cir02_real_slope_stages import (
    STAGES, PRECISIONS, compare_original_CIR02_slope_stage_receipts,
)


def _digest(n: int) -> str:
    return f"{n:064x}"


def _one_original_receipt() -> dict:
    from research.compare_cirsium_fresh_sentinel_v2_cir02_real_slope_stages import (
        ORIGINAL, HISTORICAL_SELECTED, FROZEN_GRID,
    )
    frozen = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    historical = json.loads(HISTORICAL_SELECTED.read_text(encoding="utf-8"))
    original_grid = json.loads(FROZEN_GRID.read_text(encoding="utf-8"))
    return {
        "status": "FIXED_GSI_TERRAIN_EXECUTION_COMPLETE_PRE_OUTCOME",
        "cohort_unit_id": "CIR02",
        "coordinate_bearing_artifacts_uploaded": False,
        "field_outcomes_opened": False,
        "grid": {
            "candidate_rows": frozen["units"]["CIR02"]["fine_grid_candidate_count"],
            "private_grid_sha256": original_grid["units"]["CIR02"]["private_grid_sha256"],
        },
        "structural": {"source_state_digest_sha256": _digest(2)},
        "gsi": {
            "source_complete_rows": frozen["units"]["CIR02"]["gsi_source_complete_count"],
        },
        "fine_patch_transfer": {
            "private_patch_sha256": frozen["units"]["CIR02"]["private_patch_sha256"],
            "transfer_is_validated_selector": False,
        },
        "gsi_selected_mosaic_sequence": {
            "status": "ACTUAL_SELECTED_DEM_CONTENT_SEQUENCE_AUDITED_PRE_OUTCOME",
            "chunk_count": 177,
            "selected_dem_chunks": 177,
            "unavailable_dem_chunks": 0,
            "selected_mosaic_content_sequence_sha256": historical["units"]["CIR02"]["source_a_selected_mosaic_sequence_sha256"],
        },
        "real_cir02_slope_stages": {
            "status": "ORIGINAL_REAL_DEM_CIR02_THREE_CHUNK_STAGE_AUDIT_COMPLETE",
            "cohort_unit_id": "CIR02",
            "source_chunk_count": 177,
            "probed_chunk_count": 3,
            "source_complete_cells_probed": 72,
            "all_predeclared_chunks_eligible": True,
            "sampled_mosaics_content_order_sha256": _digest(4),
            "stages_exact_float64_sha256": {name: _digest(100+i) for i,name in enumerate(STAGES)},
            "stages_decimal_sha256": {
                name: {p: _digest(200+i*2+k) for k,p in enumerate(PRECISIONS)}
                for i,name in enumerate(STAGES)
            },
            "native_python_patch_version": "3.11.17",
            "stage_sampled_individual_coordinates_or_ids_public": False,
            "individual_slope_values_public": False,
            "per_chunk_stage_hashes_public": False,
            "primary_source_selection_or_sampled_vectors_changed": False,
            "field_outcomes_opened": False,
            "all_177_chunks_or_actual_historical_CIR02_cause_reproduced": False,
        },
    }


def _compare(a: dict, b: dict) -> dict:
    return compare_original_CIR02_slope_stage_receipts(
        a, b, first_run_id=1001, second_run_id=1002,
    )


def test_two_original_source_identical_receipts_may_be_compared_without_coordinates():
    a = _one_original_receipt()
    b = copy.deepcopy(a)
    result = _compare(a, b)
    assert result["source_input_identity_verified"] is True
    assert result["source_identity_gates"]["historical_frozen_full_selected_dem_sequence_equal"] is True
    assert result["status"] == "MATCHED_SELECTED_SOURCE_REAL_NUMERICAL_STAGES_COMPARED"
    assert result["first_differing_exact_stage"] is None
    assert result["first_differing_decimal2_stage"] is None
    assert all(all(v.values()) for v in result["per_stage_equal_if_source_matched"].values())
    assert result["all_177_chunks_covered_by_numerical_stage_comparison"] is False
    assert result["sampled_stage_cause_identifies_real_CIR02_root_cause"] is False
    assert "candidate_cell_id" not in json.dumps(result)
    assert "longitude" not in json.dumps(result)


def test_gradient_stage_disagreement_is_identified_without_causal_promotion():
    a = _one_original_receipt()
    b = copy.deepcopy(a)
    b["real_cir02_slope_stages"]["stages_exact_float64_sha256"]["gradient_dx"] = _digest(999)
    b["real_cir02_slope_stages"]["stages_decimal_sha256"]["gradient_dx"]["8"] = _digest(998)
    b["real_cir02_slope_stages"]["stages_decimal_sha256"]["slope100"]["2"] = _digest(997)
    observed = _compare(a, b)
    assert observed["first_differing_exact_stage"] == "gradient_dx"
    assert observed["first_differing_decimal8_stage"] == "gradient_dx"
    assert observed["first_differing_decimal2_stage"] == "slope100"
    assert observed["sampled_stage_cause_identifies_real_CIR02_root_cause"] is False


@pytest.mark.parametrize("mismatch", [
    "full_selected", "three_selected", "source_state",
])
def test_missing_real_source_equivalence_blocks_stage_inference(mismatch):
    a = _one_original_receipt()
    b = copy.deepcopy(a)
    if mismatch == "full_selected":
        b["gsi_selected_mosaic_sequence"]["selected_mosaic_content_sequence_sha256"] = _digest(91)
    elif mismatch == "three_selected":
        b["real_cir02_slope_stages"]["sampled_mosaics_content_order_sha256"] = _digest(92)
    else:
        b["structural"]["source_state_digest_sha256"] = _digest(94)
    result = _compare(a, b)
    assert result["status"] == "REAL_DEM_SOURCE_IDENTITY_GATE_BLOCKED_STAGE_COMPARISON"
    assert result["source_input_identity_verified"] is False
    assert result["per_stage_equal_if_source_matched"] == {}
    assert result["first_differing_exact_stage"] is None


@pytest.mark.parametrize("bad", [
    "duplicate_run_id", "missing_stage", "missing_24_cell_chunk", "opened_field",
    "coordinate_release", "wrong_taxon", "wrong_patch",
])
def test_invalid_original_run_or_private_outcome_claim_fails_closed(bad):
    a = _one_original_receipt()
    b = copy.deepcopy(a)
    if bad == "duplicate_run_id":
        with pytest.raises(ValueError, match="two independent"):
            compare_original_CIR02_slope_stage_receipts(
                a, b, first_run_id=10, second_run_id=10)
        return
    if bad == "missing_stage":
        b["real_cir02_slope_stages"]["stages_exact_float64_sha256"].pop("slope100")
    elif bad == "missing_24_cell_chunk":
        b["real_cir02_slope_stages"]["source_complete_cells_probed"] = 71
    elif bad == "opened_field":
        b["field_outcomes_opened"] = True
    elif bad == "coordinate_release":
        b["real_cir02_slope_stages"]["stage_sampled_individual_coordinates_or_ids_public"] = True
    elif bad == "wrong_taxon":
        b["cohort_unit_id"] = "CIR13"
    else:
        b["fine_patch_transfer"]["private_patch_sha256"] = _digest(0)
    with pytest.raises(ValueError):
        _compare(a, b)


@pytest.mark.parametrize("denominator", ["primary_grid", "gsi_source_complete"])
@pytest.mark.parametrize("changed_receipts", ["both", "second_only"])
def test_frozen_pr247_denominator_cannot_drift_even_when_two_runs_agree(
    denominator, changed_receipts,
):
    a = _one_original_receipt()
    b = copy.deepcopy(a)
    receipts = (a, b) if changed_receipts == "both" else (b,)
    for row in receipts:
        if denominator == "primary_grid":
            row["grid"]["candidate_rows"] -= 1
        else:
            row["gsi"]["source_complete_rows"] -= 1
    with pytest.raises(ValueError, match="original frozen"):
        _compare(a, b)


@pytest.mark.parametrize("field", ["candidate_rows", "source_complete_rows"])
def test_missing_original_denominator_fails_closed(field):
    a = _one_original_receipt()
    b = copy.deepcopy(a)
    block = b["grid"] if field == "candidate_rows" else b["gsi"]
    block.pop(field)
    with pytest.raises(ValueError, match="original frozen"):
        _compare(a, b)


@pytest.mark.parametrize("changes", ["both", "second_only"])
def test_both_new_runs_can_agree_but_not_replay_historical_selected_dem(changes):
    first = _one_original_receipt()
    second = copy.deepcopy(first)
    for receipt in ((first, second) if changes == "both" else (second,)):
        receipt["gsi_selected_mosaic_sequence"]["selected_mosaic_content_sequence_sha256"] = _digest(91)
    compared = _compare(first, second)
    assert compared["status"] == "REAL_DEM_SOURCE_IDENTITY_GATE_BLOCKED_STAGE_COMPARISON"
    assert compared["source_input_identity_verified"] is False
    assert compared["source_identity_gates"]["historical_frozen_full_selected_dem_sequence_equal"] is False
    assert compared["source_identity_gates"]["full_selected_mosaic_sequence_equal"] is (changes == "both")
    assert compared["per_stage_equal_if_source_matched"] == {}
    assert compared["first_differing_exact_stage"] is None


@pytest.mark.parametrize("changed", ["both", "second_only", "missing"])
def test_original_pr241_grid_content_must_match_not_just_grid_count(changed):
    first = _one_original_receipt()
    second = copy.deepcopy(first)
    if changed == "both":
        first["grid"]["private_grid_sha256"] = _digest(97)
        second["grid"]["private_grid_sha256"] = _digest(97)
    elif changed == "second_only":
        second["grid"]["private_grid_sha256"] = _digest(97)
    else:
        second["grid"].pop("private_grid_sha256")
    with pytest.raises(ValueError, match="original frozen candidate-grid content SHA"):
        _compare(first, second)
