from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import pytest

from research.verify_cirsium_fresh_sentinel_v2_same_mosaic_result import (
    RESULT,FROZEN_PATCH,UNITS,FEATURES,PAIRS,check_summary,check_receipts,
)


def _inputs():
    return json.loads(RESULT.read_text()),json.loads(FROZEN_PATCH.read_text())


def test_exact_frozen_summary_does_not_claim_cross_run_replay():
    result,original=_inputs()
    assert check_summary(result,original)["status"]=="FOUR_UNIT_NUMERICAL_SUMMARY_REVERIFIED"
    assert result["total_probed_source_complete_cells"]==288
    assert result["claim_boundary"]["historical_CIR02_drift_resolved"] is False
    assert result["claim_boundary"]["full_cross_run_GSI_reproducibility_proven"] is False


def test_invalid_sample_count_and_field_claim_rejected():
    report,source=_inputs()
    report["units"]["CIR06"]["probed_source_complete_cells"]=73
    with pytest.raises(ValueError,match="sample denominator"):
        check_summary(report,source)
    report,source=_inputs()
    report["claim_boundary"]["historical_CIR02_drift_resolved"]=True
    with pytest.raises(ValueError,match="claim boundary"):
        check_summary(report,source)


def test_wrong_patch_sha_fails_closed():
    report,source=_inputs()
    report["units"]["CIR02"]["original_frozen_patch_sha256"]="0"*64
    with pytest.raises(ValueError,match="original patch SHA"):
        check_summary(report,source)


def _frozen_synthetic(tmp_path:Path):
    report,source=_inputs()
    for unit in UNITS:
        row=report["units"][unit]
        compare={
            name:{
                "all_exact":True,"all_near":True,
                "exact_mismatch_by_feature":{k:0 for k in FEATURES},
                "near_mismatch_by_feature":{k:0 for k in FEATURES},
                "max_abs_difference_by_feature":{k:0.0 for k in FEATURES},
            }
            for name in PAIRS
        }
        receipt={
            "cohort_unit_id":unit,"field_outcomes_opened":False,
            "coordinate_bearing_artifacts_uploaded":False,
            "fine_patch_transfer":{"private_patch_sha256":row["original_frozen_patch_sha256"]},
            "same_mosaic_numerical_replay":{
                "status":"SELECTED_ORIGINAL_GSI_MOSAIC_NUMERICAL_DIAGNOSTIC_COMPLETE",
                "source_chunk_count":row["source_chunk_count"],
                "probed_chunk_count":3,
                "source_complete_cells_probed":72,
                "same_mosaic_bytes_before_after_all_probes":True,
                "field_outcomes_opened":False,
                "field_selector_or_habitat_connectivity_claim":False,
                "comparison":compare,
            },
        }
        path=tmp_path/unit/f"{unit}_receipt.json"
        path.parent.mkdir(parents=True,exist_ok=True)
        data=json.dumps(receipt,sort_keys=True).encode()
        path.write_bytes(data)
        row["receipt_content_sha256"]=hashlib.sha256(data).hexdigest()
    return report,source


def test_pinned_byte_content_and_zero_difference_verifier(tmp_path:Path):
    report,source=_frozen_synthetic(tmp_path)
    assert check_receipts(tmp_path,report,source)["status"]=="FOUR_EXACT_NUMERICAL_REPLAY_RECEIPTS_REVERIFIED"
    file=tmp_path/"CIR02"/"CIR02_receipt.json"
    file.write_bytes(file.read_bytes()+b" ")
    with pytest.raises(ValueError,match="receipt SHA mismatch"):
        check_receipts(tmp_path,report,source)


def test_mismatched_terrain_and_coordinate_leak_not_accepted(tmp_path:Path):
    report,source=_frozen_synthetic(tmp_path)
    file=tmp_path/"CIR13"/"CIR13_receipt.json"
    payload=json.loads(file.read_bytes())
    payload["same_mosaic_numerical_replay"]["comparison"]["original_vs_replay_1"][
        "exact_mismatch_by_feature"]["elev"]=1
    data=json.dumps(payload,sort_keys=True).encode()
    file.write_bytes(data)
    report["units"]["CIR13"]["receipt_content_sha256"]=hashlib.sha256(data).hexdigest()
    with pytest.raises(ValueError,match="feature mismatch"):
        check_receipts(tmp_path,report,source)
    payload["same_mosaic_numerical_replay"]["comparison"]["original_vs_replay_1"][
        "exact_mismatch_by_feature"]["elev"]=0
    payload["latitude"]=35.0
    data=json.dumps(payload,sort_keys=True).encode()
    file.write_bytes(data)
    report["units"]["CIR13"]["receipt_content_sha256"]=hashlib.sha256(data).hexdigest()
    with pytest.raises(ValueError,match="coordinate fields leaked"):
        check_receipts(tmp_path,report,source)
