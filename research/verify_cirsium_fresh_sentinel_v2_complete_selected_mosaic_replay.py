#!/usr/bin/env python3
"""Reverify two complete 4-unit original public GSI runs with selected-source pins.

Only the eight coordinate-free original GitHub Actions JSON receipts are read.
Candidate locations, actual DEM tiles, field outcomes and score refits are never
downloaded. Missing or tampered artifacts fail closed before interpretation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from research.compare_cirsium_fresh_sentinel_v2_public_gsi_precision_runs import (
    compare_complete_public_runs,
)

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_selected_mosaic_complete_cross_run_result_v1.json"
FROZEN = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
FEATURES = ("elev", "slope100", "tpi300", "rough300")
DECIMALS = ("0", "2", "4", "6", "8")


def load(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("public evidence must be a JSON object")
    return result


def ensure(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def check_frozen_summary(record: dict[str, Any], patch_freeze: dict[str, Any]) -> dict[str, Any]:
    ensure(record.get("status") ==
           "FOUR_ORIGINAL_SHA_VERIFIED_SOURCE_SELECTED_REPLAY_DIAGNOSTIC_COMPLETE_PRE_OUTCOME",
           "public four-unit replay freeze status changed")
    ensure(record.get("source_run_a") == {
        "run_id": 37785966356,
        "source_pr": 263,
        "head_sha": "66267116b7b17745ac0c22b7880ca4e87e1b53fc",
        "description": "first complete actual-selected-mosaic-instrumented run",
    }, "first run original identity changed")
    ensure(record.get("source_run_b") == {
        "run_id": 38058577057,
        "head_sha": "77ac330bb5180bbfa43a25de47206d0f81939415",
        "rerun_cancelled_CIR13_only": True,
        "description": "independent development run with cancelled CIR13 job rerun; original run artifacts preserved",
    }, "second run original identity changed")
    ensure(tuple(record.get("cohort_unit_ids", ())) == UNITS, "unit identities/order changed")
    ensure(tuple(record.get("feature_order", ())) == FEATURES
           and tuple(record.get("fixed_decimal_precision_order", ())) == DECIMALS,
           "source-complete terrain fingerprint features changed")
    ensure(record.get("original_patch_source_pr") == 247
           and record.get("original_fine_patch_freeze_path") ==
           "validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
           and patch_freeze.get("source_pr") == 247,
           "original private patch freeze changed")
    ensure(set(patch_freeze.get("units", {})) == set(UNITS), "original patch cohort changed")
    flags = record.get("claim_boundary") or {}
    for key in (
        "selected_sequence_digest_is_content_order_commitment_not_private_chunk_map",
        "original_frozen_patch_sha_verified_four_of_four",
        "whole_cache_equality_is_not_selected_source_identity",
        "source_same_slopes_differ_does_not_isolate_numeric_root_cause",
        "source_changed_unit_not_evidence_of_identical_input_math",
        "rounded_precision_hashes_do_not_bound_value_difference",
        "different_runner_image_or_patch_python_version_remains_possible",
    ):
        ensure(flags.get(key) is True, "mandatory scientific limitation removed: " + key)
    for key in (
        "full_structural_order_reproducibility_achieved_all_four",
        "real_occupancy_or_habitat_inference_authorized",
        "field_selector_validated", "prospective_field_outcomes_opened",
        "private_coordinates_exported",
        "original_GSI_chunk_source_priority_threshold_or_patch_rule_modified",
    ):
        ensure(flags.get(key) is False, "unsupported source or biological promotion: " + key)
    counts = record.get("aggregate", {})
    expectations = {
        "units": 4, "same_candidate_grid_units": 4,
        "same_source_state_units": 4, "same_tile_and_mosaic_cache_units": 3,
        "same_actually_selected_mosaic_sequence_units": 3,
        "same_all_feature_precision_hashes_units": 2,
        "same_structural_full_order_units": 2, "same_exact_frozen_patch_sha_units": 4,
        "first_source_controlled_slope_precision_drift_unit": "CIR02",
        "different_selected_source_and_slope_precision_drift_unit": "CIR12",
    }
    ensure(all(counts.get(k) == v for k,v in expectations.items()),
           "four-unit evidence aggregate/count contract changed")
    units = record.get("units")
    ensure(isinstance(units, dict) and tuple(units) == UNITS,
           "public source-world freeze needs all four units")
    for unit in UNITS:
        row = units[unit]
        ensure(row.get("original_frozen_patch_sha256") ==
               patch_freeze["units"][unit]["private_patch_sha256"],
               f"{unit} original frozen patch SHA mismatch")
        ensure(all(isinstance(row.get(field), str) and len(row[field]) == 64
                   and all(c in "0123456789abcdef" for c in row[field])
                   for field in (
                       "source_a_receipt_content_sha256", "source_b_receipt_content_sha256",
                       "source_a_selected_mosaic_sequence_sha256",
                       "source_b_selected_mosaic_sequence_sha256",
                   )), f"{unit} receipt or selected DEM SHA absent")
        ensure(row.get("source_chunk_count") in (81, 177, 237)
               and row.get("actual_selected_source_mosaic_chunks_a") == row["source_chunk_count"]
               and row.get("actual_selected_source_mosaic_chunks_b") == row["source_chunk_count"],
               f"{unit} actual selected chunk count drift")
        for key in ("candidate_grid_sha_equal", "source_state_digest_sha_equal",
                    "source_complete_row_count_equal", "final_patch_sha_equal",
                    "final_patch_matches_original_frozen_shas_a_and_b"):
            ensure(row.get(key) is True, f"{unit} shared input/patch drift: {key}")
        expect_source_same = unit != "CIR12"
        for key in ("cache_png_and_mosaic_sha_equal",
                    "actual_selected_mosaic_content_sequence_equal"):
            ensure(row.get(key) is expect_source_same,
                   f"{unit} actual source / cache equivalence changed: {key}")
        expect_numeric_same = unit in ("CIR06", "CIR13")
        for key in ("terrain_digest_equal", "full_structural_order_sha_equal",
                    "original_source_receipt_bytes_equal"):
            ensure(row.get(key) is expect_numeric_same, f"{unit} full numeric/hash result drift: {key}")
        ensure((row["source_a_selected_mosaic_sequence_sha256"] ==
                row["source_b_selected_mosaic_sequence_sha256"]) is expect_source_same,
               f"{unit} recorded actual selected DEM SHA evidence inconsistent")
        feats = row.get("feature_precision_equal")
        ensure(isinstance(feats, dict) and set(feats) == set(FEATURES),
               f"{unit} terrain features incomplete")
        for feat in FEATURES:
            digits = feats[feat]
            ensure(isinstance(digits,dict) and set(digits) == set(DECIMALS),
                   f"{unit} precision labels incomplete")
            for precision in DECIMALS:
                expected = not(unit in ("CIR02", "CIR12") and feat == "slope100" and precision != "0")
                ensure(digits[precision] is expected, f"{unit} original feature fingerprint changed")
        expected_stage = {
            "CIR02": "SAME_ACTUALLY_SELECTED_GSI_SOURCE_DIFFERENT_SLOPE_PRECISION_UNRESOLVED",
            "CIR06": "ACTUAL_SELECTED_INPUT_AND_ALL_CHECKED_DIGESTS_MATCH",
            "CIR12": "GSI_ACTUALLY_SELECTED_MOSAIC_CONTENT_DIFFERS",
            "CIR13": "ACTUAL_SELECTED_INPUT_AND_ALL_CHECKED_DIGESTS_MATCH",
        }[unit]
        ensure(row.get("stage_classification") == expected_stage, f"{unit} diagnostic stage changed")
    return {"status": "FOUR_UNIT_SOURCE_SELECTED_COMPARISON_SUMMARY_COHERENT",
            "compared_units": list(UNITS)}


def _receipt(path: Path, sha: str) -> dict[str, Any]:
    ensure(path.is_file() and not path.is_symlink(), "original public GSI receipt missing")
    raw = path.read_bytes()
    ensure(hashlib.sha256(raw).hexdigest() == sha,
           "original GSI receipt bytes do not match frozen SHA")
    data = json.loads(raw)
    ensure(data.get("field_outcomes_opened") is False and
           data.get("coordinate_bearing_artifacts_uploaded") is False,
           "private/field exposure in public GSI receipt")
    return data


def verify_exact_receipts(
    first_root: Path, second_root: Path, record: dict, patch_freeze: dict,
) -> dict:
    check_frozen_summary(record, patch_freeze)
    first, second = {}, {}
    for unit in UNITS:
        frozen_row = record["units"][unit]
        first[unit] = _receipt(first_root / unit / f"{unit}_receipt.json",
                               frozen_row["source_a_receipt_content_sha256"])
        second[unit] = _receipt(second_root / unit / f"{unit}_receipt.json",
                                frozen_row["source_b_receipt_content_sha256"])
        for block, suffix in ((first[unit], "a"), (second[unit], "b")):
            ensure(block.get("cohort_unit_id") == unit, f"{unit} wrong original unit")
            ensure(block["fine_patch_transfer"]["private_patch_sha256"] ==
                   frozen_row["original_frozen_patch_sha256"],
                   f"{unit} original private patch hash mismatch")
            selected = block["gsi_selected_mosaic_sequence"]
            ensure(selected["selected_mosaic_content_sequence_sha256"] ==
                   frozen_row[f"source_{suffix}_selected_mosaic_sequence_sha256"]
                   and selected["chunk_count"] == frozen_row["source_chunk_count"]
                   and selected["selected_dem_chunks"] == frozen_row["source_chunk_count"]
                   and selected["unavailable_dem_chunks"] == 0,
                   f"{unit} actual selected source SHA/count diverged")
    compared = compare_complete_public_runs(
        first, second,
        first_run_id=record["source_run_a"]["run_id"],
        second_run_id=record["source_run_b"]["run_id"],
        frozen=patch_freeze,
    )
    for unit in UNITS:
        expected = record["units"][unit]
        actual = compared["units"][unit]
        for freeze_key, report_key in (
            ("candidate_grid_sha_equal", "fine_grid_hashes_equal"),
            ("source_state_digest_sha_equal", "source_state_digests_equal"),
            ("source_complete_row_count_equal", "source_complete_counts_equal"),
            ("actual_selected_mosaic_content_sequence_equal", "selected_mosaic_content_sequence_equal"),
            ("terrain_digest_equal", "gsi_terrain_feature_digest_equal"),
            ("full_structural_order_sha_equal", "structural_order_sha_equal"),
            ("final_patch_sha_equal", "final_patch_sha_equal"),
        ):
            ensure(actual[report_key] is expected[freeze_key],
                   f"{unit} {freeze_key} contradicts original public receipts")
        ensure(actual["feature_precision_equal"] == expected["feature_precision_equal"],
               f"{unit} per-feature precision result contradicts original")
        ensure(actual["selected_mosaic_identity_verified_in_both_runs"] is True
               and actual["first_patch_matches_original_freeze"] is True
               and actual["second_patch_matches_original_freeze"] is True,
               f"{unit} selected input or original final patch never verified")
        expected_stage = {
            "CIR02": "SAME_SELECTED_DEM_CONTENT_AND_STATES_DIFFERENT_TERRAIN_UNRESOLVED",
            "CIR06": "ALL_CHECKED_HASH_STAGES_EQUAL",
            "CIR12": "GSI_CACHE_INPUT_CONTENT_DIFFERS",
            "CIR13": "ALL_CHECKED_HASH_STAGES_EQUAL",
        }[unit]
        ensure(actual["stage_diagnosis"] == expected_stage,
               f"{unit} public independent classification changed")
        row = expected
        ensure((first[unit]["gsi_cache_content"]["tile_inventory_sha256"] ==
                second[unit]["gsi_cache_content"]["tile_inventory_sha256"] and
                first[unit]["gsi_cache_content"]["mosaic_inventory_sha256"] ==
                second[unit]["gsi_cache_content"]["mosaic_inventory_sha256"])
               is row["cache_png_and_mosaic_sha_equal"],
               f"{unit} source cache inventory comparison disagreed")
        ensure((row["source_a_receipt_content_sha256"] ==
                row["source_b_receipt_content_sha256"])
               is row["original_source_receipt_bytes_equal"],
               f"{unit} actual receipt byte parity disagreed")
    return {"status": "EIGHT_ORIGINAL_PUBLIC_GSI_RECEIPTS_REVERIFIED",
            "run_ids": [record["source_run_a"]["run_id"], record["source_run_b"]["run_id"]],
            "units": list(UNITS),
            "full_structural_order_reproduced_units": ["CIR06", "CIR13"],
            "selected_dem_equal_but_slope_differs": ["CIR02"],
            "changed_selected_source": ["CIR12"],
            "all_frozen_final_patches_reproduced": True,
            "private_locations_or_field_outcomes_opened": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path)
    parser.add_argument("--second", type=Path)
    args = parser.parse_args()
    record, freeze = load(RESULT), load(FROZEN)
    if args.first is None and args.second is None:
        result = check_frozen_summary(record, freeze)
    elif args.first is not None and args.second is not None:
        result = verify_exact_receipts(args.first, args.second, record, freeze)
    else:
        raise ValueError("must specify both complete source run receipt directories")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
