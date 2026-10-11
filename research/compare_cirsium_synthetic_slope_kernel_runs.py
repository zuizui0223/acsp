#!/usr/bin/env python3
"""Fail-closed comparison of two independent public synthetic slope-runner receipts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

STAGES = (
    "resampled_elevation", "local_mean100", "filled_elevation",
    "gradient_dx", "gradient_dy", "instantaneous_slope",
    "slope_valid_support", "slope_smoothing_numerator", "slope100",
)


def compare_public_slope_kernel_runs(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    for name, row in (("first", first), ("second", second)):
        if row.get("status") != "SYNTHETIC_SLOPE_STAGE_DOUBLE_REPLAY_CONSISTENT":
            raise ValueError(f"{name} synthetic runner did not complete")
        if row.get("replay_same_process_exact") is not True or row.get(
            "synthetic_stage_source_compared_to_production"
        ) is not True:
            raise ValueError(f"{name} production equivalence and double replay required")
        if row.get("prospective_field_outcomes_opened") is not False or row.get(
            "private_dem_or_candidate_locations_opened"
        ) is not False or row.get("real_CIR02_root_cause_identified") is not False:
            raise ValueError(f"{name} unsupported private/field/causal promotion")
        hashes = row.get("stage_sha256")
        if not isinstance(hashes, dict) or tuple(hashes) != STAGES or row.get("stage_count") != len(STAGES):
            raise ValueError(f"{name} wrong synthetic slope stage cohort")
        if any(not isinstance(v, str) or len(v) != 64 for v in hashes.values()):
            raise ValueError(f"{name} malformed synthetic kernel digest")
        if not isinstance(row.get("native_versions"), dict) or not row["native_versions"]:
            raise ValueError(f"{name} native runtime provenance missing")
    raw_same = first.get("source_dem_byte_sha256") == second.get("source_dem_byte_sha256")
    pixel_same = (
        first.get("source_resampled_elevation_sha256")
        == second.get("source_resampled_elevation_sha256")
    )
    if not raw_same or not pixel_same:
        raise ValueError("independent synthetic input DEM bytes/pixels differ: cannot compare kernels")
    equal = {name: first["stage_sha256"][name] == second["stage_sha256"][name] for name in STAGES}
    first_difference = next((name for name, identical in equal.items() if not identical), None)
    return {
        "schema_version": "cirsium-synthetic-slope-kernel-public-run-comparison-v1",
        "status": (
            "ALL_SYNTHETIC_KERNEL_STAGES_REPRODUCED_ACROSS_TWO_RUNNERS"
            if first_difference is None
            else "SYNTHETIC_KERNEL_STAGE_DIVERGENCE_DETECTED"
        ),
        "input_dem_byte_sha_equal": raw_same,
        "resampled_elevation_sha_equal": pixel_same,
        "stages_equal": equal,
        "first_differing_stage": first_difference,
        "native_runtime_labels_equal": first["native_versions"] == second["native_versions"],
        "first_native_versions": first["native_versions"],
        "second_native_versions": second["native_versions"],
        "original_real_CIR02_slope_cause_identified": False,
        "field_outcomes_opened": False,
        "real_GSI_selected_dem_equivalence_inferred": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-json", required=True, type=Path)
    p.add_argument("--second-json", required=True, type=Path)
    p.add_argument("--result-json", type=Path)
    args = p.parse_args()
    report = compare_public_slope_kernel_runs(
        json.loads(args.first_json.read_text(encoding="utf-8")),
        json.loads(args.second_json.read_text(encoding="utf-8")),
    )
    if args.result_json is not None:
        if args.result_json.exists():
            raise SystemExit("refusing to overwrite synthetic comparison")
        args.result_json.parent.mkdir(parents=True, exist_ok=True)
        args.result_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
