#!/usr/bin/env python3
"""Compare two complete independent *public-only* frozen GSI runs.

The full candidate coordinates and terrain vectors are NEVER read. Only
precomputed coordinate-free per-feature hashes, input-inventory hashes and
aggregate row/patch counts from four pinned public-safe unit receipts enter.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_gsi_public_paired_precision_comparison_v1.json"
FROZEN_PATCH = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
FEATURES = ("elev", "slope100", "tpi300", "rough300")
PRECISIONS = ("0", "2", "4", "6", "8")


def _require(test: bool, msg: str) -> None:
    if not test:
        raise ValueError(msg)


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _check_contract() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    _require(contract.get("status") == "FROZEN_BEFORE_TWO_PUBLIC_RUN_COMPARISON", "public pair contract not frozen")
    _require(tuple(contract.get("cohort_unit_ids", ())) == UNITS, "public pair cohort drift")
    _require(tuple(contract.get("features", ())) == FEATURES, "public pair feature drift")
    _require(tuple(contract.get("precision_decimals", ())) == PRECISIONS, "public pair precision drift")
    policy = contract.get("match_policy") or {}
    _require(policy.get("require_different_workflow_run_id") is True, "two distinct runs required")
    claims = contract.get("interpretation") or {}
    for key in ("any_native_implementation_root_cause_identified","field_selector_validated",
                "habitat_connectivity_validated","biological_absence_imputed",
                "arbitrary_preferred_run_selection"):
        _require(claims.get(key) is False, "public pair cannot establish causal/biological claims")


def _unit_info(data: dict[str, Any], unit: str) -> dict[str, Any]:
    _require(isinstance(data, dict) and data.get("cohort_unit_id") == unit,
             f"{unit} receipt unit identity mismatch")
    _require(data.get("status") == "FIXED_GSI_TERRAIN_EXECUTION_COMPLETE_PRE_OUTCOME",
             f"{unit} receipt not completed")
    _require(data.get("field_outcomes_opened") is False, f"{unit} field outcomes accessed")
    _require(data.get("coordinate_bearing_artifacts_uploaded") is False,
             f"{unit} unsafe candidate export")
    blocks = ("grid","gsi","structural","fine_patch_transfer",
              "gsi_cache_content","gsi_feature_precision_fingerprints")
    _require(all(isinstance(data.get(k),dict) for k in blocks), f"{unit} required provenance missing")
    # Completeness is a source-state census, not a biological absence.
    total = data["grid"].get("candidate_rows")
    states = tuple(data["gsi"].get(k) for k in (
        "source_complete_rows",
        "provider_unavailable_rows",
        "terrain_vector_unavailable_rows",
    ))
    _require(
        isinstance(total, int) and not isinstance(total, bool) and total > 0
        and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in states)
        and sum(states) == total,
        f"{unit} source-state denominator does not conserve all candidate cells",
    )
    f = data["gsi_feature_precision_fingerprints"]
    _require(f.get("status") == "SOURCE_COMPLETE_GSI_PRECISION_FINGERPRINTED_PRE_OUTCOME",
             f"{unit} per-feature provenance missing")
    _require(f.get("field_outcomes_opened") is False and
             f.get("full_cross_run_reproducibility_proven") is False and
             f.get("private_coordinates_or_IDs_exported") is False,
             f"{unit} feature audit claim boundary violated")
    _require(f.get("source_complete_count") == data["gsi"].get("source_complete_rows"),
             f"{unit} per-feature denominator disagrees with source")
    _require(f.get("private_gsi_frame_sha256") == data["gsi"].get("private_gsi_frame_sha256"),
             f"{unit} per-feature source frame SHA mismatched")
    hashes = f.get("feature_precision_sha256")
    _require(isinstance(hashes,dict) and set(hashes) == set(FEATURES),
             f"{unit} incomplete feature-level digests")
    for feature in FEATURES:
        values = hashes[feature]
        _require(isinstance(values,dict) and set(values) == set(PRECISIONS)
                 and all(_sha(values[n]) for n in PRECISIONS),
                 f"{unit} malformed precision digests")
    for b, fields in {
        "grid":("private_grid_sha256",),
        "gsi":("terrain_feature_digest_sha256","private_gsi_frame_sha256"),
        "structural":("source_state_digest_sha256","private_structural_order_sha256"),
        "fine_patch_transfer":("private_patch_sha256",),
        "gsi_cache_content":("tile_inventory_sha256","mosaic_inventory_sha256"),
    }.items():
        _require(all(_sha(data[b].get(k)) for k in fields), f"{unit} invalid {b} input SHA")
    _require(data["fine_patch_transfer"].get("transfer_is_validated_selector") is False,
             f"{unit} unsupported selector promotion")
    _require(data["gsi_cache_content"].get("coordinate_bearing_filenames_exported") is False,
             f"{unit} tile filenames exposed")
    _require(data["gsi_cache_content"].get("field_outcomes_opened") is False,
             f"{unit} tile source used outcomes")
    return data


def compare_complete_public_runs(
    first: dict[str, dict[str, Any]],
    second: dict[str, dict[str, Any]],
    *,
    first_run_id: int,
    second_run_id: int,
    frozen: dict[str, Any],
) -> dict[str, Any]:
    _check_contract()
    _require(isinstance(first_run_id,int) and isinstance(second_run_id,int)
             and first_run_id > 0 and second_run_id > 0
             and first_run_id != second_run_id,
             "two different positive workflow run IDs are required")
    _require(set(first) == set(UNITS) and set(second) == set(UNITS),
             "both independent runs must contain all four units")
    _require(frozen.get("source_pr") == 247 and set(frozen.get("units",{})) == set(UNITS),
             "original patch freeze identity changed")
    units: dict[str,Any] = {}
    for unit in UNITS:
        a,b = _unit_info(first[unit],unit), _unit_info(second[unit],unit)
        af,bf = a["gsi_feature_precision_fingerprints"]["feature_precision_sha256"],b["gsi_feature_precision_fingerprints"]["feature_precision_sha256"]
        feature_equal = {f:{n:af[f][n] == bf[f][n] for n in PRECISIONS} for f in FEATURES}
        different_at = {f:next((n for n in PRECISIONS if not feature_equal[f][n]),None) for f in FEATURES}
        first_patch=a["fine_patch_transfer"]["private_patch_sha256"]
        second_patch=b["fine_patch_transfer"]["private_patch_sha256"]
        expected=frozen["units"][unit]["private_patch_sha256"]
        png_match=a["gsi_cache_content"]["tile_inventory_sha256"]==b["gsi_cache_content"]["tile_inventory_sha256"]
        mosaic_match=a["gsi_cache_content"]["mosaic_inventory_sha256"]==b["gsi_cache_content"]["mosaic_inventory_sha256"]
        feature_match=a["gsi"]["terrain_feature_digest_sha256"]==b["gsi"]["terrain_feature_digest_sha256"]
        grid_match=a["grid"]["private_grid_sha256"]==b["grid"]["private_grid_sha256"]
        state_match=a["structural"]["source_state_digest_sha256"]==b["structural"]["source_state_digest_sha256"]
        counts_match=a["gsi"]["source_complete_rows"]==b["gsi"]["source_complete_rows"]
        if not grid_match:
            stage="FINE_CANDIDATE_GRID_INPUT_DIFFERS"
        elif not counts_match or not state_match:
            stage="GSI_SOURCE_COMPLETENESS_OR_STATE_DIFFERS"
        elif not (png_match and mosaic_match):
            stage="GSI_CACHE_INPUT_CONTENT_DIFFERS"
        elif not feature_match:
            stage="SAME_CACHED_GSI_BYTES_AND_STATES_DIFFERENT_TERRAIN_FEATURES_UNRESOLVED"
        elif not all(all(precisions.values()) for precisions in feature_equal.values()):
            stage="WHOLE_TERRAIN_DIGEST_MATCHES_BUT_PRECISION_FINGERPRINT_DIFFERS"
        elif a["structural"]["private_structural_order_sha256"] != b["structural"]["private_structural_order_sha256"]:
            stage="SAME_GSI_FEATURES_DIFFERENT_STRUCTURAL_ORDER"
        else:
            stage="ALL_CHECKED_HASH_STAGES_EQUAL"
        units[unit] = {
            "source_complete_counts_equal":a["gsi"]["source_complete_rows"]==b["gsi"]["source_complete_rows"],
            "source_state_digests_equal":a["structural"]["source_state_digest_sha256"]==b["structural"]["source_state_digest_sha256"],
            "fine_grid_hashes_equal":a["grid"]["private_grid_sha256"]==b["grid"]["private_grid_sha256"],
            "gsi_png_inventory_equal":png_match,
            "gsi_mosaic_inventory_equal":mosaic_match,
            "gsi_terrain_feature_digest_equal":feature_match,
            "private_gsi_frame_sha_equal":a["gsi"]["private_gsi_frame_sha256"]==b["gsi"]["private_gsi_frame_sha256"],
            "structural_order_sha_equal":a["structural"]["private_structural_order_sha256"]==b["structural"]["private_structural_order_sha256"],
            "final_patch_sha_equal":first_patch==second_patch,
            "first_patch_matches_original_freeze":first_patch==expected,
            "second_patch_matches_original_freeze":second_patch==expected,
            "feature_precision_equal":feature_equal,
            "first_difference_decimal_precision_by_feature":different_at,
            "stage_diagnosis":stage,
            "root_cause_identified":False,
            "field_selector_validated":False,
        }
    return {
        "schema_version":"cirsium-fresh-sentinel-v2-gsi-public-paired-precision-result-v1",
        "status":"TWO_COMPLETE_PUBLIC_GSI_RUNS_COMPARED_PRE_OUTCOME",
        "workflow_run_ids":[first_run_id,second_run_id],
        "compared_unit_count":4,
        "units":units,
        "private_coordinates_or_site_ids_opened":False,
        "field_outcomes_opened":False,
        "full_source_replay_equivalence_claimed":False,
        "native_implementation_root_cause_claimed":False,
        "ecological_habitat_or_field_discovery_claimed":False,
    }


def _load_receipts(directory: Path) -> dict[str,dict[str,Any]]:
    output={}
    for unit in UNITS:
        path=Path(directory)/unit/f"{unit}_receipt.json"
        _require(path.is_file() and not path.is_symlink(), f"{unit} public receipt not found")
        output[unit]=json.loads(path.read_text(encoding="utf-8"))
    return output


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-run-id",required=True,type=int)
    p.add_argument("--second-run-id",required=True,type=int)
    p.add_argument("--first-receipts",required=True,type=Path)
    p.add_argument("--second-receipts",required=True,type=Path)
    p.add_argument("--public-safe-summary-json",type=Path)
    args=p.parse_args()
    result=compare_complete_public_runs(
        _load_receipts(args.first_receipts),
        _load_receipts(args.second_receipts),
        first_run_id=args.first_run_id,second_run_id=args.second_run_id,
        frozen=json.loads(FROZEN_PATCH.read_text(encoding="utf-8")),
    )
    text=json.dumps(result,indent=2,ensure_ascii=False)+"\n"
    if args.public_safe_summary_json:
        _require(not args.public_safe_summary_json.exists(), "refusing to overwrite pair result")
        args.public_safe_summary_json.parent.mkdir(parents=True,exist_ok=True)
        args.public_safe_summary_json.write_text(text,encoding="utf-8")
    print(text)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
