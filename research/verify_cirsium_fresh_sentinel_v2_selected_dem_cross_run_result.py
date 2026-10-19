#!/usr/bin/env python3
"""Reverify original SHA-bound public GSI source-world comparisons, no private sites."""
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
RESULT = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_selected_mosaic_cross_run_result_v1.json"
FROZEN_PATCH = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
FEATURES = ("elev", "slope100", "tpi300", "rough300")
PRECISIONS = ("0", "2", "4", "6", "8")


def load_json(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("expected JSON object")
    return result


def assert_ok(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_summary(result: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    assert_ok(result.get("status") ==
              "ORIGINAL_SHA_PINNED_CROSS_RUN_DIAGNOSTIC_SELECTED_INPUT_EQUIVALENCE_UNVERIFIED",
              "frozen selected-source comparison status changed")
    assert_ok(tuple(result.get("cohort_unit_ids", ())) == UNITS, "frozen cohort changed")
    assert_ok(result["first_source"] == {
        "pr": 260, "run_id": 37765932839,
        "head_sha": "84b3bc8590a1a253a37d3b45cf57da16734227b3"
    }, "first original source changed")
    assert_ok(result["second_source"] == {
        "pr": 263, "run_id": 37785966356,
        "head_sha": "66267116b7b17745ac0c22b7880ca4e87e1b53fc"
    }, "second original source changed")
    assert_ok(frozen.get("source_pr") == 247 and set(frozen.get("units", ())) == set(UNITS),
              "original frozen patch source changed")
    limits = result.get("limits", {})
    for key in ("whole_cache_inventory_not_actual_selected_source_identity",
                "per_feature_rounded_digest_differences_do_not_bound_numeric_error",
                "no_private_site_ids_or_coordinates_public",
                "original_frozen_2p5pct_and_1km_patch_unchanged"):
        assert_ok(limits.get(key) is True, f"required caveat changed: {key}")
    for key in ("actual_selected_dem_comparison_to_first_source_available",
                "full_source_order_reproducibility_proven",
                "field_selector_validated", "prospective_field_outcomes_opened"):
        assert_ok(limits.get(key) is False, f"unsupported promotion: {key}")
    observed = result.get("units")
    assert_ok(isinstance(observed, dict) and tuple(observed) == UNITS,
              "missing four frozen units")
    for unit in UNITS:
        row = observed[unit]
        assert_ok(row.get("original_patch_sha256") ==
                  frozen["units"][unit]["private_patch_sha256"],
                  f"{unit} original patch changed")
        assert_ok(all(isinstance(row.get(k), str) and len(row[k]) == 64 for k in (
            "first_receipt_sha256", "second_receipt_sha256",
            "second_selected_mosaic_sequence_sha256"
        )), f"{unit} missing SHA fingerprints")
        assert_ok(row.get("selected_dem_sequence_equality_between_first_and_second") is None,
                  f"{unit} selected-source parity improperly claimed")
        assert_ok(row["second_chunk_count"] == row["second_selected_dem_chunk_count"] > 0,
                  f"{unit} selected chunk denominator changed")
        assert_ok(row["gsi_source_complete_count"] ==
                  frozen["units"][unit]["gsi_source_complete_count"],
                  f"{unit} source complete count differs from freeze")
        for key in ("candidate_grid_sha_equal", "source_state_sha_equal",
                    "cache_png_inventory_sha_equal", "cache_dem_mosaic_inventory_sha_equal",
                    "exact_original_patch_sha_equal"):
            assert_ok(row.get(key) is True, f"{unit} evidence accounting changed: {key}")
        expected_equal = unit != "CIR02"
        for key in ("aggregate_terrain_feature_digest_equal",
                    "full_structural_order_sha_equal"):
            assert_ok(row.get(key) is expected_equal,
                      f"{unit} structural/terrain result changed: {key}")
        features = row.get("feature_precision_equal", {})
        assert_ok(set(features) == set(FEATURES), f"{unit} precision features missing")
        for feature in FEATURES:
            actual = features[feature]
            assert_ok(set(actual) == set(PRECISIONS), f"{unit} precision levels missing")
            for precision in PRECISIONS:
                expected = not (unit == "CIR02" and feature == "slope100" and precision != "0")
                assert_ok(actual[precision] is expected, f"{unit} rounded hash identity changed")
    partial = result.get("independent_partial_confirmation", {})
    assert_ok(partial.get("pr") == 262 and partial.get("run_id") == 37777351033
              and partial.get("unit") == "CIR02"
              and partial.get("artifact_id") == 11552480775,
              "independent partial confirmation changed")
    for key in ("selected_mosaic_sequence_equal_to_second",
                "all_four_feature_fingerprints_equal_to_second",
                "full_terrain_digest_equal_to_second",
                "patch_digest_equal_to_second"):
        assert_ok(partial.get(key) is True, f"independent partial confirmation {key} changed")
    return {"status": "FOUR_UNIT_CROSS_RUN_FROZEN_RESULT_CONSISTENT", "unit_count": 4}


def read_byte_pinned(path: Path, expected_sha: str) -> dict[str, Any]:
    assert_ok(path.is_file() and not path.is_symlink(), "pinned public receipt missing or unsafe")
    raw = path.read_bytes()
    assert_ok(hashlib.sha256(raw).hexdigest() == expected_sha,
              "original public receipt SHA mismatch")
    out = json.loads(raw)
    assert_ok(out.get("field_outcomes_opened") is False and
              out.get("coordinate_bearing_artifacts_uploaded") is False,
              "unsafe public receipt")
    return out


def check_original_receipts(
    result: dict[str, Any], frozen: dict[str, Any],
    first_root: Path, second_root: Path, cir02_partial: Path,
) -> dict[str, Any]:
    check_summary(result, frozen)
    first, second = {}, {}
    for unit in UNITS:
        row = result["units"][unit]
        first[unit] = read_byte_pinned(
            first_root / unit / f"{unit}_receipt.json", row["first_receipt_sha256"])
        second[unit] = read_byte_pinned(
            second_root / unit / f"{unit}_receipt.json", row["second_receipt_sha256"])
        for observed in (first[unit], second[unit]):
            assert_ok(observed.get("cohort_unit_id") == unit, "GSI cohort identity changed")
            assert_ok(observed["fine_patch_transfer"]["private_patch_sha256"] ==
                      row["original_patch_sha256"], "original patch byte identity changed")
        s = second[unit]["gsi_selected_mosaic_sequence"]
        assert_ok(s["selected_mosaic_content_sequence_sha256"] ==
                  row["second_selected_mosaic_sequence_sha256"],
                  "actual selected mosaic sequence does not match frozen result")
        assert_ok(s["chunk_count"] == row["second_chunk_count"] and
                  s["selected_dem_chunks"] == row["second_selected_dem_chunk_count"],
                  "actual selected DEM denominator changed")
        assert_ok("gsi_selected_mosaic_sequence" not in first[unit],
                  "old run unexpectedly contains selected source identity")
    compared = compare_complete_public_runs(
        first, second,
        first_run_id=result["first_source"]["run_id"],
        second_run_id=result["second_source"]["run_id"],
        frozen=frozen,
    )
    for unit in UNITS:
        row = result["units"][unit]
        comparison = compared["units"][unit]
        assert_ok(comparison["selected_mosaic_content_sequence_equal"] is None,
                  f"{unit} old actual selected-source identity improperly inferred")
        assert_ok(comparison["source_complete_counts_equal"] == row["source_state_sha_equal"] is True,
                  f"{unit} old/new completeness changed")
        for field, source_name in (
            ("candidate_grid_sha_equal", "fine_grid_hashes_equal"),
            ("source_state_sha_equal", "source_state_digests_equal"),
            ("cache_png_inventory_sha_equal", "gsi_png_inventory_equal"),
            ("cache_dem_mosaic_inventory_sha_equal", "gsi_mosaic_inventory_equal"),
            ("aggregate_terrain_feature_digest_equal", "gsi_terrain_feature_digest_equal"),
            ("full_structural_order_sha_equal", "structural_order_sha_equal"),
            ("exact_original_patch_sha_equal", "final_patch_sha_equal"),
        ):
            assert_ok(comparison[source_name] is row[field], f"{unit} {field} changed")
        assert_ok(comparison["feature_precision_equal"] == row["feature_precision_equal"],
                  f"{unit} per-feature precision evidence changed")
        expected_stage = (
            "SAME_CACHE_AND_SOURCE_STATES_SELECTED_DEM_IDENTITY_UNVERIFIED"
            if unit == "CIR02"
            else "RECORDED_HASH_STAGES_EQUAL_SELECTED_DEM_IDENTITY_UNVERIFIED"
        )
        assert_ok(comparison["stage_diagnosis"] == expected_stage,
                  f"{unit} unsupported source-world interpretation")
    third = read_byte_pinned(
        cir02_partial, result["independent_partial_confirmation"]["public_receipt_sha256"]
    )
    new = second["CIR02"]
    assert_ok(third["cohort_unit_id"] == "CIR02", "independent confirmation unit wrong")
    assert_ok(third["gsi_selected_mosaic_sequence"] ==
              new["gsi_selected_mosaic_sequence"], "independent source sequence differs")
    assert_ok(third["gsi_feature_precision_fingerprints"]["feature_precision_sha256"] ==
              new["gsi_feature_precision_fingerprints"]["feature_precision_sha256"],
              "independent complete terrain feature precision differs")
    assert_ok(third["gsi"]["terrain_feature_digest_sha256"] ==
              new["gsi"]["terrain_feature_digest_sha256"], "independent terrain digest differs")
    assert_ok(third["fine_patch_transfer"]["private_patch_sha256"] ==
              new["fine_patch_transfer"]["private_patch_sha256"],
              "independent original patch digest differs")
    return {"status": "NINE_ORIGINAL_PUBLIC_RECEIPTS_REVERIFIED",
            "complete_unit_pairs": len(UNITS),
            "independent_selected_dem_parity_units": ["CIR02"],
            "first_run_selected_dem_inputs_proven_same": False,
            "coordinates_or_outcomes_opened": False}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first", type=Path)
    p.add_argument("--second", type=Path)
    p.add_argument("--third-cir02", type=Path)
    args = p.parse_args()
    data, source = load_json(RESULT), load_json(FROZEN_PATCH)
    if all(x is None for x in (args.first, args.second, args.third_cir02)):
        outcome = check_summary(data, source)
    elif all(x is not None for x in (args.first, args.second, args.third_cir02)):
        outcome = check_original_receipts(data, source, args.first, args.second, args.third_cir02)
    else:
        raise ValueError("all three public receipt sources must be provided together")
    print(json.dumps(outcome, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
