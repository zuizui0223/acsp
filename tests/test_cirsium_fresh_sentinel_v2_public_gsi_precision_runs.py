from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research.compare_cirsium_fresh_sentinel_v2_public_gsi_precision_runs import (
    FEATURES, PRECISIONS, UNITS, FROZEN_PATCH,
    compare_complete_public_runs,
)


def _sha(i: int) -> str:
    return f"{i:064x}"


def _inputs():
    frozen=json.loads(FROZEN_PATCH.read_text(encoding="utf-8"))
    def unit_receipt(unit: str):
        patch=frozen["units"][unit]
        return {
            "cohort_unit_id":unit,
            "status":"FIXED_GSI_TERRAIN_EXECUTION_COMPLETE_PRE_OUTCOME",
            "field_outcomes_opened":False,
            "coordinate_bearing_artifacts_uploaded":False,
            "grid":{"private_grid_sha256":_sha(1),"candidate_rows":patch["fine_grid_candidate_count"]},
            "gsi":{
                "source_complete_rows":patch["gsi_source_complete_count"],
                "provider_unavailable_rows":patch["fine_grid_candidate_count"]-patch["gsi_source_complete_count"],
                "terrain_vector_unavailable_rows":0,
                "terrain_feature_digest_sha256":_sha(2),
                "private_gsi_frame_sha256":_sha(3),
            },
            "structural":{
                "source_state_digest_sha256":_sha(4),
                "private_structural_order_sha256":_sha(5),
            },
            "fine_patch_transfer":{
                "private_patch_sha256":patch["private_patch_sha256"],
                "transfer_is_validated_selector":False,
            },
            "gsi_cache_content":{
                "tile_inventory_sha256":_sha(6),
                "mosaic_inventory_sha256":_sha(7),
                "coordinate_bearing_filenames_exported":False,
                "field_outcomes_opened":False,
            },
            "gsi_feature_precision_fingerprints":{
                "status":"SOURCE_COMPLETE_GSI_PRECISION_FINGERPRINTED_PRE_OUTCOME",
                "source_complete_count":patch["gsi_source_complete_count"],
                "private_gsi_frame_sha256":_sha(3),
                "feature_precision_sha256":{
                    k:{p:_sha(10+i*5+j) for j,p in enumerate(PRECISIONS)}
                    for i,k in enumerate(FEATURES)
                },
                "field_outcomes_opened":False,
                "full_cross_run_reproducibility_proven":False,
                "private_coordinates_or_IDs_exported":False,
            },
        }
    first={u:unit_receipt(u) for u in UNITS}
    return first, copy.deepcopy(first), frozen


def _compare(first,second,frozen):
    return compare_complete_public_runs(
        first,second,first_run_id=101,second_run_id=102,frozen=frozen,
    )


def test_two_complete_identical_public_runs_have_no_divergence():
    one,two,frozen=_inputs()
    value=_compare(one,two,frozen)
    assert value["compared_unit_count"]==4
    assert value["workflow_run_ids"]==[101,102]
    assert all(r["stage_diagnosis"]=="ALL_CHECKED_HASH_STAGES_EQUAL"
               and r["final_patch_sha_equal"] is True
               and r["first_patch_matches_original_freeze"] is True
               and r["second_patch_matches_original_freeze"] is True
               and all(v is None for v in r["first_difference_decimal_precision_by_feature"].values())
               for r in value["units"].values())
    assert value["full_source_replay_equivalence_claimed"] is False
    assert "candidate_cell_id" not in json.dumps(value)
    assert "latitude" not in json.dumps(value)


def test_mosaic_bytes_equal_but_numerical_feature_drift_is_separated():
    one,two,frozen=_inputs()
    two["CIR02"]["gsi"]["terrain_feature_digest_sha256"]=_sha(202)
    two["CIR02"]["gsi_feature_precision_fingerprints"]["feature_precision_sha256"]["slope100"]["8"]=_sha(99)
    result=_compare(one,two,frozen)["units"]["CIR02"]
    assert result["gsi_png_inventory_equal"] is True
    assert result["gsi_mosaic_inventory_equal"] is True
    assert result["gsi_terrain_feature_digest_equal"] is False
    assert result["stage_diagnosis"]=="SAME_CACHED_GSI_BYTES_AND_STATES_DIFFERENT_TERRAIN_FEATURES_UNRESOLVED"
    assert result["first_difference_decimal_precision_by_feature"]["slope100"]=="8"
    assert result["first_difference_decimal_precision_by_feature"]["elev"] is None
    assert result["root_cause_identified"] is False


def test_changed_cache_source_does_not_establish_provider_failure():
    one,two,frozen=_inputs()
    two["CIR06"]["gsi_cache_content"]["tile_inventory_sha256"]=_sha(45)
    two["CIR06"]["gsi_cache_content"]["mosaic_inventory_sha256"]=_sha(46)
    result=_compare(one,two,frozen)["units"]["CIR06"]
    assert result["stage_diagnosis"]=="GSI_CACHE_INPUT_CONTENT_DIFFERS"
    assert result["gsi_png_inventory_equal"] is False
    assert result["gsi_mosaic_inventory_equal"] is False
    assert result["root_cause_identified"] is False


def test_grid_or_source_state_divergence_cannot_be_claimed_as_numeric_drift():
    one,two,frozen=_inputs()
    two["CIR02"]["grid"]["private_grid_sha256"]=_sha(300)
    two["CIR02"]["gsi"]["terrain_feature_digest_sha256"]=_sha(301)
    assert _compare(one,two,frozen)["units"]["CIR02"]["stage_diagnosis"]=="FINE_CANDIDATE_GRID_INPUT_DIFFERS"

    one,two,frozen=_inputs()
    two["CIR02"]["structural"]["source_state_digest_sha256"]=_sha(302)
    two["CIR02"]["gsi"]["terrain_feature_digest_sha256"]=_sha(303)
    assert _compare(one,two,frozen)["units"]["CIR02"]["stage_diagnosis"]=="GSI_SOURCE_COMPLETENESS_OR_STATE_DIFFERS"


def test_structural_only_drift_and_patch_failure_reported_without_promotion():
    one,two,frozen=_inputs()
    two["CIR12"]["structural"]["private_structural_order_sha256"]=_sha(47)
    two["CIR12"]["fine_patch_transfer"]["private_patch_sha256"]=_sha(48)
    result=_compare(one,two,frozen)["units"]["CIR12"]
    assert result["stage_diagnosis"]=="SAME_GSI_FEATURES_DIFFERENT_STRUCTURAL_ORDER"
    assert result["final_patch_sha_equal"] is False
    assert result["second_patch_matches_original_freeze"] is False


@pytest.mark.parametrize("what",[
    "same_run","missing_unit","different_species_label","outcomes_open",
    "coordinates_uploaded","missing_precision","fake_source_count","invalid_source_denominator",
    "promoted_selector","bad_source_hash",
])
def test_malformed_pair_fails_closed(what):
    one,two,frozen=_inputs()
    if what=="same_run":
        with pytest.raises(ValueError,match="different positive"):
            compare_complete_public_runs(one,two,first_run_id=7,second_run_id=7,frozen=frozen)
        return
    elif what=="missing_unit":
        two.pop("CIR13")
    elif what=="different_species_label":
        two["CIR02"]["cohort_unit_id"]="CIR06"
    elif what=="outcomes_open":
        two["CIR02"]["field_outcomes_opened"]=True
    elif what=="coordinates_uploaded":
        two["CIR02"]["coordinate_bearing_artifacts_uploaded"]=True
    elif what=="missing_precision":
        two["CIR02"]["gsi_feature_precision_fingerprints"]["feature_precision_sha256"]["elev"].pop("8")
    elif what=="fake_source_count":
        two["CIR02"]["gsi_feature_precision_fingerprints"]["source_complete_count"]=1
    elif what=="invalid_source_denominator":
        two["CIR02"]["gsi"]["provider_unavailable_rows"]+=1
    elif what=="promoted_selector":
        two["CIR02"]["fine_patch_transfer"]["transfer_is_validated_selector"]=True
    elif what=="bad_source_hash":
        two["CIR02"]["gsi_cache_content"]["tile_inventory_sha256"]="invalid"
    with pytest.raises(ValueError):
        _compare(one,two,frozen)


def test_original_patch_freeze_cannot_be_replaced():
    one,two,frozen=_inputs()
    frozen["source_pr"]=0
    with pytest.raises(ValueError,match="original patch freeze"):
        _compare(one,two,frozen)
