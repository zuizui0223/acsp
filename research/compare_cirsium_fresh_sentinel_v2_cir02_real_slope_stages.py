#!/usr/bin/env python3
"""Compare two original CIR02 real-GSI stage receipts without private locations.

A stage-level numerical verdict is permitted only when the selected actual
mosaic sequence, the three chosen mosaic bytes, candidate-grid identity and
source-state membership are *all* identical. All comparisons are hashes of
preregistered public-safe aggregate samples, not raster/site disclosure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_cir02_real_slope_stage_pair_v1.json"
ORIGINAL = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
STAGES = (
    "resampled_elevation", "local_mean100", "filled_elevation",
    "gradient_dx", "gradient_dy", "instantaneous_slope",
    "slope_valid_support", "slope_smoothing_numerator", "slope100",
)
PRECISIONS = ("2", "8")


def _expect(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _sha(v: Any) -> bool:
    return isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)


def _contract() -> None:
    v = json.loads(CONTRACT.read_text(encoding="utf-8"))
    _expect(v.get("status") == "FROZEN_BEFORE_TWO_INDEPENDENT_REAL_CIR02_STAGE_RUNS",
            "CIR02 two-real-run stage comparison contract not frozen")
    _expect(v.get("required_taxon") == "CIR02" and v.get("source_run_count") == 2,
            "real-GSI comparison taxon or run count drift")
    _expect(v.get("required_chunk_count") == 177 and
            v.get("required_probed_chunks") == 3 and v.get("required_sampled_cells") == 72,
            "real-GSI stage sample denominator changed")
    _expect(tuple(v.get("required_stage_order", ())) == STAGES and
            tuple(v.get("decimal_precisions", ())) == PRECISIONS,
            "real-GSI stage/precision labels changed")
    flags = v.get("interpretation", {})
    for k in ("require_selected_dem_content_equality_before_any_numeric_stage_comparison",
              "require_candidate_grid_and_source_complete_membership_equality"):
        _expect(flags.get(k) is True, "source identity gate removed")
    for k in ("full_177_chunk_slope_replay_conclusion_authorized",
              "real_slope_cause_identified", "selected_source_provider_priority_changed",
              "source_indeterminate_recoded_as_absence",
              "private_coordinate_or_candidate_id_export",
              "prospective_field_outcomes_opened",
              "field_selector_or_habitat_validated"):
        _expect(flags.get(k) is False, "unsupported causal or private claim")


def _verified_unit(
    receipt: dict[str, Any], expected_patch: str,
    frozen_original_unit: dict[str, Any],
) -> dict[str, Any]:
    _expect(isinstance(receipt, dict) and receipt.get("cohort_unit_id") == "CIR02",
            "paired GSI receipt must be CIR02")
    _expect(receipt.get("status") == "FIXED_GSI_TERRAIN_EXECUTION_COMPLETE_PRE_OUTCOME",
            "original fixed-policy GSI receipt incomplete")
    _expect(receipt.get("field_outcomes_opened") is False and
            receipt.get("coordinate_bearing_artifacts_uploaded") is False,
            "source result has unexpected outcomes or coordinates")
    for k in ("grid", "structural", "gsi", "fine_patch_transfer",
              "gsi_selected_mosaic_sequence", "real_cir02_slope_stages"):
        _expect(isinstance(receipt.get(k), dict), "missing original GSI source block: " + k)
    _expect(receipt["fine_patch_transfer"].get("private_patch_sha256") == expected_patch and
            receipt["fine_patch_transfer"].get("transfer_is_validated_selector") is False,
            "original frozen private patch hash or selector claim invalid")
    # In addition to cross-run identity, require the already frozen PR #247
    # source population. Two runs can match each other yet both silently use
    # a different primary candidate frame or source-complete denominator.
    _expect(
        type(receipt["grid"].get("candidate_rows")) is int
        and receipt["grid"]["candidate_rows"] == frozen_original_unit["fine_grid_candidate_count"],
        "CIR02 original frozen primary candidate denominator changed",
    )
    _expect(
        type(receipt["gsi"].get("source_complete_rows")) is int
        and receipt["gsi"]["source_complete_rows"] == frozen_original_unit["gsi_source_complete_count"],
        "CIR02 original frozen GSI source-complete denominator changed",
    )
    stage = receipt["real_cir02_slope_stages"]
    _expect(stage.get("status") == "ORIGINAL_REAL_DEM_CIR02_THREE_CHUNK_STAGE_AUDIT_COMPLETE"
            and stage.get("cohort_unit_id") == "CIR02"
            and stage.get("source_chunk_count") == 177
            and stage.get("probed_chunk_count") == 3
            and stage.get("source_complete_cells_probed") == 72
            and stage.get("all_predeclared_chunks_eligible") is True,
            "CIR02 sampled original real DEM stages incomplete")
    _expect(_sha(stage.get("sampled_mosaics_content_order_sha256")),
            "selected three source DEM SHA missing")
    for k in ("stage_sampled_individual_coordinates_or_ids_public",
              "individual_slope_values_public", "per_chunk_stage_hashes_public",
              "primary_source_selection_or_sampled_vectors_changed",
              "field_outcomes_opened",
              "all_177_chunks_or_actual_historical_CIR02_cause_reproduced"):
        _expect(stage.get(k) is False, "stage privacy/causal firewall violated: " + k)
    exact = stage.get("stages_exact_float64_sha256")
    rounded = stage.get("stages_decimal_sha256")
    _expect(isinstance(exact, dict) and tuple(exact) == STAGES
            and isinstance(rounded, dict) and tuple(rounded) == STAGES,
            "nine required real numerical stages missing")
    for step in STAGES:
        _expect(_sha(exact[step]) and isinstance(rounded[step], dict)
                and set(rounded[step]) == set(PRECISIONS)
                and all(_sha(rounded[step][p]) for p in PRECISIONS),
                f"invalid original GSI stage hashes: {step}")
    selected = receipt["gsi_selected_mosaic_sequence"]
    _expect(selected.get("status") == "ACTUAL_SELECTED_DEM_CONTENT_SEQUENCE_AUDITED_PRE_OUTCOME"
            and selected.get("chunk_count") == 177
            and selected.get("selected_dem_chunks") == 177
            and selected.get("unavailable_dem_chunks") == 0
            and _sha(selected.get("selected_mosaic_content_sequence_sha256")),
            "complete actual selected DEM content identities missing")
    _expect(_sha(receipt["grid"].get("private_grid_sha256"))
            and _sha(receipt["structural"].get("source_state_digest_sha256"))
            and isinstance(receipt["gsi"].get("source_complete_rows"), int)
            and receipt["gsi"]["source_complete_rows"] > 0,
            "primary grid and source-state census not fingerprinted")
    return receipt


def compare_original_CIR02_slope_stage_receipts(
    first: dict[str, Any], second: dict[str, Any],
    *, first_run_id: int, second_run_id: int,
) -> dict[str, Any]:
    _contract()
    _expect(all(isinstance(n, int) and not isinstance(n, bool) and n > 0
                for n in (first_run_id, second_run_id))
            and first_run_id != second_run_id, "two independent source workflow runs required")
    patch = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    _expect(patch.get("source_pr") == 247, "original frozen private patch source changed")
    original_unit = patch["units"]["CIR02"]
    frozen_patch = original_unit["private_patch_sha256"]
    a = _verified_unit(first, frozen_patch, original_unit)
    b = _verified_unit(second, frozen_patch, original_unit)
    gates = {
        "grid_sha_equal": a["grid"]["private_grid_sha256"] == b["grid"]["private_grid_sha256"],
        "source_state_sha_equal": (a["structural"]["source_state_digest_sha256"]
                                   == b["structural"]["source_state_digest_sha256"]),
        "source_complete_count_equal": (a["gsi"]["source_complete_rows"] ==
                                       b["gsi"]["source_complete_rows"]),
        "full_selected_mosaic_sequence_equal": (
            a["gsi_selected_mosaic_sequence"]["selected_mosaic_content_sequence_sha256"] ==
            b["gsi_selected_mosaic_sequence"]["selected_mosaic_content_sequence_sha256"]
        ),
        "sampled_three_mosaic_sequence_equal": (
            a["real_cir02_slope_stages"]["sampled_mosaics_content_order_sha256"] ==
            b["real_cir02_slope_stages"]["sampled_mosaics_content_order_sha256"]
        ),
    }
    same_inputs = all(gates.values())
    pairs = {}
    if same_inputs:
        a_st = a["real_cir02_slope_stages"]
        b_st = b["real_cir02_slope_stages"]
        for name in STAGES:
            pairs[name] = {
                "exact_float64_equal": (
                    a_st["stages_exact_float64_sha256"][name] ==
                    b_st["stages_exact_float64_sha256"][name]
                ),
                "decimal_2_equal": (
                    a_st["stages_decimal_sha256"][name]["2"] ==
                    b_st["stages_decimal_sha256"][name]["2"]
                ),
                "decimal_8_equal": (
                    a_st["stages_decimal_sha256"][name]["8"] ==
                    b_st["stages_decimal_sha256"][name]["8"]
                ),
            }
        first_exact = next(
            (name for name in STAGES if not pairs[name]["exact_float64_equal"]), None
        )
        first_dec2 = next(
            (name for name in STAGES if not pairs[name]["decimal_2_equal"]), None
        )
        first_dec8 = next(
            (name for name in STAGES if not pairs[name]["decimal_8_equal"]), None
        )
    else:
        first_exact = first_dec2 = first_dec8 = None
    return {
        "schema_version": "cirsium-CIR02-original-real-DEM-slope-nine-stage-pair-v1",
        "status": (
            "MATCHED_SELECTED_SOURCE_REAL_NUMERICAL_STAGES_COMPARED"
            if same_inputs else "REAL_DEM_SOURCE_IDENTITY_GATE_BLOCKED_STAGE_COMPARISON"
        ),
        "source_run_ids": [first_run_id, second_run_id],
        "source_identity_gates": gates,
        "source_input_identity_verified": same_inputs,
        "per_stage_equal_if_source_matched": pairs,
        "first_differing_exact_stage": first_exact,
        "first_differing_decimal2_stage": first_dec2,
        "first_differing_decimal8_stage": first_dec8,
        "native_python_patch_versions": [
            a["real_cir02_slope_stages"]["native_python_patch_version"],
            b["real_cir02_slope_stages"]["native_python_patch_version"],
        ],
        "all_177_chunks_covered_by_numerical_stage_comparison": False,
        "sampled_stage_cause_identifies_real_CIR02_root_cause": False,
        "private_coordinates_or_candidate_ids_exported": False,
        "prospective_field_outcomes_opened": False,
        "field_selector_validated": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-run-id", type=int, required=True)
    p.add_argument("--second-run-id", type=int, required=True)
    p.add_argument("--first-json", type=Path, required=True)
    p.add_argument("--second-json", type=Path, required=True)
    p.add_argument("--output-json", type=Path)
    args = p.parse_args()
    result = compare_original_CIR02_slope_stage_receipts(
        json.loads(args.first_json.read_text(encoding="utf-8")),
        json.loads(args.second_json.read_text(encoding="utf-8")),
        first_run_id=args.first_run_id, second_run_id=args.second_run_id,
    )
    result_text = json.dumps(result, indent=2) + "\n"
    if args.output_json:
        if args.output_json.exists():
            raise SystemExit("refusing to overwrite source comparison result")
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(result_text, encoding="utf-8")
    print(result_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
