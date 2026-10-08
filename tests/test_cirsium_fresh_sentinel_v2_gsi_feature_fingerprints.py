from __future__ import annotations
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.audit_cirsium_fresh_sentinel_v2_gsi_feature_fingerprints import (
    FEATURES, DECIMALS, fingerprint_gsi_features, main,
)


def _source() -> pd.DataFrame:
    frame=pd.DataFrame({
        "cohort_unit_id":["CIR02"]*5,
        "candidate_cell_id":[f"CIR02_r{i}_c{i}" for i in range(5)],
        "gsi_source_state":["SOURCE_COMPLETE"]*4+["INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE"],
        "latitude":[35.0+i/100 for i in range(5)],
        "longitude":[139.0+i/100 for i in range(5)],
    })
    for n,feature in enumerate(FEATURES):
        frame[feature]=[float(10+n+i/10) for i in range(4)]+[np.nan]
    return frame


def test_public_digest_is_row_order_invariant_and_coordinate_free():
    frame=_source()
    result=fingerprint_gsi_features(frame,unit_id="CIR02")
    reversed_result=fingerprint_gsi_features(frame.iloc[::-1],unit_id="CIR02")
    assert result==reversed_result
    assert result["candidate_count"]==5
    assert result["source_complete_count"]==4
    assert result["source_indeterminate_count"]==1
    assert set(result["feature_precision_sha256"])==set(FEATURES)
    for f in FEATURES:
        assert set(result["feature_precision_sha256"][f])==set(map(str,DECIMALS))
        assert all(len(z)==64 for z in result["feature_precision_sha256"][f].values())
    dumped=json.dumps(result)
    for term in ("latitude","longitude","CIR02_r0_c0","candidate_cell_id"):
        assert term not in dumped
    assert result["full_cross_run_reproducibility_proven"] is False


def test_high_precision_detects_small_change_while_coarse_precision_ignores_it():
    frame=_source()
    baseline=fingerprint_gsi_features(frame,unit_id="CIR02")
    frame.loc[0,"slope100"]+=0.00003
    shifted=fingerprint_gsi_features(frame,unit_id="CIR02")
    assert baseline["feature_precision_sha256"]["slope100"]["8"]!=shifted["feature_precision_sha256"]["slope100"]["8"]
    assert baseline["feature_precision_sha256"]["slope100"]["0"]==shifted["feature_precision_sha256"]["slope100"]["0"]
    for f in ("elev","tpi300","rough300"):
        assert baseline["feature_precision_sha256"][f]==shifted["feature_precision_sha256"][f]


def test_source_indeterminate_is_not_treated_as_zero():
    frame=_source()
    initial=fingerprint_gsi_features(frame,unit_id="CIR02")
    frame.loc[4,list(FEATURES)]=[999.0]*len(FEATURES)
    after=fingerprint_gsi_features(frame,unit_id="CIR02")
    assert initial["feature_precision_sha256"]==after["feature_precision_sha256"]
    assert initial["source_indeterminate_count"]==1


@pytest.mark.parametrize("problem",["duplicate_id","fractional_feature_nan","unknown_source_state","wrong_unit","zero_complete"])
def test_source_integrity_errors_fail_closed(problem:str):
    f=_source()
    if problem=="duplicate_id":
        f.loc[1,"candidate_cell_id"]=f.loc[0,"candidate_cell_id"]
    elif problem=="fractional_feature_nan":
        f.loc[0,"elev"]=np.nan
    elif problem=="unknown_source_state":
        f.loc[0,"gsi_source_state"]="MISSING_ASSUMED_ZERO"
    elif problem=="wrong_unit":
        f.loc[0,"cohort_unit_id"]="CIR06"
    else:
        f["gsi_source_state"]="INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE"
    with pytest.raises(ValueError):
        fingerprint_gsi_features(f,unit_id="CIR02")


def test_cli_writes_only_public_digest_and_never_overwrites(tmp_path:Path,monkeypatch:pytest.MonkeyPatch):
    import sys
    src=tmp_path/"private.csv.gz"
    out=tmp_path/"summary.json"
    _source().to_csv(src,index=False,compression={"method":"gzip","mtime":0})
    monkeypatch.setattr(sys,"argv",["audit","--unit-id","CIR02","--private-gsi-csv-gz",str(src),"--public-safe-summary-json",str(out)])
    assert main()==0
    x=json.loads(out.read_text())
    assert x["source_complete_count"]==4
    assert len(x["private_gsi_frame_sha256"])==64
    assert "latitude" not in json.dumps(x)
    with pytest.raises(SystemExit,match="refusing to overwrite"):
        main()
