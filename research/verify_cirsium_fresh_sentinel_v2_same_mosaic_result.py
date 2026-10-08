#!/usr/bin/env python3
"""Audit pinned coordinate-free numerical GSI replay receipts; never fetch field data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/"validation/coverage_then_fine_structure_fresh_sentinel_v2_same_mosaic_numerical_replay_result_v1.json"
FROZEN_PATCH=ROOT/"validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
UNITS=("CIR02","CIR06","CIR12","CIR13")
FEATURES=("elev","slope100","slope_sd100","rough100","tpi100","range100","tpi300","rough300")
PAIRS=("original_vs_replay_1","replay_1_vs_replay_2")


def _read(path:Path)->dict:
    value=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("expected JSON object")
    return value


def check_summary(summary:dict, original:dict)->dict:
    if summary.get("status")!="FOUR_UNIT_BOUNDED_SAME_MOSAIC_EXACT_REPLAY_PRE_OUTCOME":
        raise ValueError("unexpected frozen result status")
    if summary.get("source_pr")!=258 or summary.get("source_workflow_run_id")!=37752252722:
        raise ValueError("frozen numerical source identity changed")
    if summary.get("source_head_sha")!="fc61f41ea427715a2cf4b4f879bbcee89176cb1e":
        raise ValueError("numerical source commit changed")
    if tuple(summary.get("units",{}))!=UNITS or set(original.get("units",{}))!=set(UNITS):
        raise ValueError("unit identities drifted")
    if summary.get("original_patch_source_pr")!=247 or original.get("source_pr")!=247:
        raise ValueError("frozen patch source changed")
    if summary.get("total_probed_chunks")!=12 or summary.get("total_probed_source_complete_cells")!=288:
        raise ValueError("bounded sample totals changed")
    if summary.get("numeric_feature_count")!=8 or summary.get("replay_comparisons_per_sample")!=2:
        raise ValueError("numerical comparison contract changed")
    boundary=summary.get("claim_boundary",{})
    for key in ("same_process_same_mosaic_only","original_patch_selector_unchanged"):
        if boundary.get(key) is not True:
            raise ValueError("overstated replay claim boundary")
    for key in ("all_chunks_replayed","full_cross_run_GSI_reproducibility_proven",
                "historical_CIR02_drift_resolved","prospective_field_outcomes_opened",
                "private_locations_public","field_recovery_or_habitat_claim"):
        if boundary.get(key) is not False:
            raise ValueError("overstated replay claim boundary")
    for unit, v in summary["units"].items():
        if not isinstance(v.get("receipt_content_sha256"),str) or len(v["receipt_content_sha256"])!=64:
            raise ValueError(f"{unit} missing pinned public receipt SHA")
        if v.get("original_frozen_patch_sha256")!=original["units"][unit]["private_patch_sha256"]:
            raise ValueError(f"{unit} original patch SHA drifted")
        if v.get("probed_chunk_count")!=3 or v.get("probed_source_complete_cells")!=72:
            raise ValueError(f"{unit} sample denominator drifted")
        for key in ("original_vs_replay_1_exact_mismatches","replay_1_vs_replay_2_exact_mismatches",
                    "original_vs_replay_1_near_mismatches","replay_1_vs_replay_2_near_mismatches"):
            if v.get(key)!=0:
                raise ValueError(f"{unit} actual mismatch contradicts frozen zero report")
        if v.get("same_mosaic_sha256_before_after") is not True:
            raise ValueError(f"{unit} mosaic not unchanged")
        if v.get("selected_support_or_patch_membership_changed") is not False:
            raise ValueError(f"{unit} selection changed")
    return {"status":"FOUR_UNIT_NUMERICAL_SUMMARY_REVERIFIED","units":list(UNITS)}


def check_receipts(root:Path,summary:dict,original:dict)->dict:
    check_summary(summary,original)
    forbidden={"latitude","longitude","candidate_cell_id","zone_member_site_ids"}
    for unit in UNITS:
        path=Path(root)/unit/f"{unit}_receipt.json"
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"{unit} pinned receipt not found")
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=summary["units"][unit]["receipt_content_sha256"]:
            raise ValueError(f"{unit} pinned receipt SHA mismatch")
        receipt=json.loads(raw)
        if receipt.get("cohort_unit_id")!=unit or receipt.get("field_outcomes_opened") is not False:
            raise ValueError(f"{unit} wrong cohort or field outcome exposure")
        if receipt.get("coordinate_bearing_artifacts_uploaded") is not False:
            raise ValueError(f"{unit} location exposure")
        if receipt["fine_patch_transfer"]["private_patch_sha256"]!=summary["units"][unit]["original_frozen_patch_sha256"]:
            raise ValueError(f"{unit} patch SHA mismatch")
        row=receipt["same_mosaic_numerical_replay"]
        if row.get("status")!="SELECTED_ORIGINAL_GSI_MOSAIC_NUMERICAL_DIAGNOSTIC_COMPLETE":
            raise ValueError(f"{unit} incomplete same mosaic diagnostic")
        if row.get("source_chunk_count")!=summary["units"][unit]["source_chunk_count"]:
            raise ValueError(f"{unit} source chunk count changed")
        if row.get("probed_chunk_count")!=3 or row.get("source_complete_cells_probed")!=72:
            raise ValueError(f"{unit} numerical replay denominator drifted")
        if row.get("same_mosaic_bytes_before_after_all_probes") is not True:
            raise ValueError(f"{unit} DEM bytes changed")
        if row.get("field_outcomes_opened") is not False or row.get("field_selector_or_habitat_connectivity_claim") is not False:
            raise ValueError(f"{unit} invalid scientific claim")
        for pair in PAIRS:
            compared=row.get("comparison",{}).get(pair,{})
            if compared.get("all_exact") is not True or compared.get("all_near") is not True:
                raise ValueError(f"{unit} mismatch between original and replay")
            for key in ("exact_mismatch_by_feature","near_mismatch_by_feature","max_abs_difference_by_feature"):
                vals=compared.get(key,{})
                if set(vals)!=set(FEATURES) or any(v!=0 for v in vals.values()):
                    raise ValueError(f"{unit} feature mismatch {key}")
        def check_keys(v):
            if isinstance(v,dict):
                if forbidden.intersection(v): raise ValueError(f"{unit} coordinate fields leaked")
                for x in v.values(): check_keys(x)
            elif isinstance(v,list):
                for x in v: check_keys(x)
        check_keys(receipt)
    return {"status":"FOUR_EXACT_NUMERICAL_REPLAY_RECEIPTS_REVERIFIED",
            "units":list(UNITS),"private_coordinates_opened":False}


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-dir",type=Path)
    args=parser.parse_args()
    summary,original=_read(RESULT),_read(FROZEN_PATCH)
    result=check_receipts(args.receipt_dir,summary,original) if args.receipt_dir else check_summary(summary,original)
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
