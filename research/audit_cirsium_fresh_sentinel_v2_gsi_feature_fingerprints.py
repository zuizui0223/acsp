#!/usr/bin/env python3
"""Read-only four-feature, five-precision digest of frozen source-complete GSI terrain.

Private candidate IDs and coordinates participate only in a cryptographic
digest. Public output contains no individual IDs, coordinates, terrain values,
or per-chunk site mappings. It is diagnostic, never a selector or outcome model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/"validation/coverage_then_fine_structure_fresh_sentinel_v2_gsi_feature_precision_fingerprints_v1.json"
UNITS=("CIR02","CIR06","CIR12","CIR13")
FEATURES=("elev","slope100","tpi300","rough300")
DECIMALS=(0,2,4,6,8)


def _sha256(path:Path)->str:
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(4*1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def _check_contract()->None:
    c=json.loads(CONTRACT.read_text(encoding="utf-8"))
    if c.get("status")!="FROZEN_PRE_OUTCOME_FEATURE_DIGEST_DIAGNOSTIC":
        raise ValueError("feature fingerprint contract is not frozen")
    if tuple(c.get("units",()))!=UNITS or tuple(c.get("feature_columns",()))!=FEATURES or tuple(c.get("precision_decimals",()))!=DECIMALS:
        raise ValueError("feature fingerprint family or precision drift")
    for key in ("source_priority_changed","merge_phase_or_threshold_changed",
                "individual_candidate_or_coordinate_export","field_outcomes_opened",
                "field_selector_validated"):
        if c.get(key) is not False:
            raise ValueError("unsafe public feature fingerprint claim")
    if c.get("read_only") is not True:
        raise ValueError("feature fingerprint is not read-only")


def fingerprint_gsi_features(
    frame:pd.DataFrame, *, unit_id:str,
)->dict[str,Any]:
    _check_contract()
    if unit_id not in UNITS:
        raise ValueError("unknown GSI unit")
    required={"cohort_unit_id","candidate_cell_id","gsi_source_state",*FEATURES}
    missing=required-set(frame.columns)
    if missing or frame.empty:
        raise ValueError(f"missing required source-complete GSI frame: {sorted(missing)}")
    if set(frame["cohort_unit_id"].astype(str))!={unit_id}:
        raise ValueError("GSI unit mismatch")
    ids=frame["candidate_cell_id"]
    if ids.isna().any() or ids.astype(str).str.strip().eq("").any() or ids.astype(str).duplicated().any():
        raise ValueError("invalid or duplicate GSI candidate IDs")
    allowed_states={
        "SOURCE_COMPLETE",
        "INDETERMINATE_GSI_PROVIDER_UNAVAILABLE",
        "INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE",
    }
    states=frame["gsi_source_state"].astype(str)
    if not set(states).issubset(allowed_states):
        raise ValueError("unknown GSI source state")
    mask=states.eq("SOURCE_COMPLETE")
    if not mask.any():
        raise ValueError("no source-complete GSI rows to fingerprint")
    work=frame.loc[mask,["candidate_cell_id",*FEATURES]].copy().sort_values(
        "candidate_cell_id",kind="mergesort"
    )
    vectors=work[list(FEATURES)].apply(pd.to_numeric,errors="raise").to_numpy(dtype=np.float64)
    if not np.isfinite(vectors).all():
        raise ValueError("nonfinite declared source-complete GSI feature")
    hashes:dict[str,dict[str,str]]={}
    candidate_ids=work["candidate_cell_id"].astype(str).tolist()
    for fidx,feature in enumerate(FEATURES):
        feature_hashes={}
        for precision in DECIMALS:
            h=hashlib.sha256()
            fmt=f".{precision}f"
            for cid,value in zip(candidate_ids,vectors[:,fidx]):
                h.update((cid+"\t"+format(float(value),fmt)+"\n").encode("utf-8"))
            feature_hashes[str(precision)]=h.hexdigest()
        hashes[feature]=feature_hashes
    return {
        "schema_version":"cirsium-fresh-sentinel-v2-gsi-feature-fingerprints-result-v1",
        "status":"SOURCE_COMPLETE_GSI_PRECISION_FINGERPRINTED_PRE_OUTCOME",
        "cohort_unit_id":unit_id,
        "candidate_count":len(frame),
        "source_complete_count":int(mask.sum()),
        "source_indeterminate_count":int((~mask).sum()),
        "feature_precision_sha256":hashes,
        "per_candidate_data_exported":False,
        "private_coordinates_or_IDs_exported":False,
        "source_identity_changed_by_audit":False,
        "ranking_or_patch_selection_changed":False,
        "field_outcomes_opened":False,
        "full_cross_run_reproducibility_proven":False,
    }


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id",choices=UNITS,required=True)
    parser.add_argument("--private-gsi-csv-gz",type=Path,required=True)
    parser.add_argument("--public-safe-summary-json",type=Path,required=True)
    args=parser.parse_args()
    if not args.private_gsi_csv_gz.is_file() or args.private_gsi_csv_gz.is_symlink():
        raise SystemExit("missing or unsafe private GSI source file")
    if args.public_safe_summary_json.exists():
        raise SystemExit("refusing to overwrite feature fingerprint result")
    result=fingerprint_gsi_features(
        pd.read_csv(args.private_gsi_csv_gz,low_memory=False),
        unit_id=args.unit_id
    )
    result["private_gsi_frame_sha256"]=_sha256(args.private_gsi_csv_gz)
    args.public_safe_summary_json.parent.mkdir(parents=True,exist_ok=True)
    args.public_safe_summary_json.write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    print(json.dumps({"unit":args.unit_id,"source_complete_count":result["source_complete_count"],"status":result["status"]}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
