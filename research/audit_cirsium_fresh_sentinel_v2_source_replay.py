#!/usr/bin/env python3
"""Compare two *frozen public-safe* fine-grid execution receipts, without sites.

This does not read private per-cell terrain data, inferred locations, survey
outcomes or field effort. Equality of final patch bytes cannot rescue source
drift. Only the two pre-specified GitHub Actions runs are compared.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_RECEIPT = (
    ROOT / "validation" /
    "coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
)
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
SOURCE_RUN_ID = 37647225829
REPLAY_RUN_ID = 37705751756
DIGEST_FIELDS = (
    ("grid", "private_grid_sha256"),
    ("gsi", "terrain_feature_digest_sha256"),
    ("gsi", "private_gsi_frame_sha256"),
    ("structural", "source_state_digest_sha256"),
    ("structural", "private_structural_order_sha256"),
    ("fine_patch_transfer", "private_patch_sha256"),
)
COUNT_FIELDS = (
    ("grid", "candidate_rows"),
    ("gsi", "source_complete_rows"),
    ("gsi", "provider_unavailable_rows"),
    ("gsi", "terrain_vector_unavailable_rows"),
    ("gsi", "chunk_count"),
    ("structural", "source_complete_rows"),
    ("structural", "source_indeterminate_rows"),
    ("structural", "structural_order_rows"),
    ("fine_patch_transfer", "retained_support_cell_count"),
    ("fine_patch_transfer", "patch_count"),
    ("fine_patch_transfer", "singleton_patch_count"),
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON receipt must be an object: {path}")
    return value


def _read_unit(root: Path, unit: str) -> dict[str, Any]:
    path = Path(root) / unit / f"{unit}_receipt.json"
    if not path.is_file():
        raise ValueError(f"missing required {unit} receipt: {path}")
    value = _read_json(path)
    if value.get("schema_version") != "cirsium-fresh-sentinel-v2-fixed-gsi-unit-receipt-v2":
        raise ValueError(f"{unit} receipt schema drifted")
    if value.get("status") != "FIXED_GSI_TERRAIN_EXECUTION_COMPLETE_PRE_OUTCOME":
        raise ValueError(f"{unit} receipt status drifted")
    if value.get("cohort_unit_id") != unit:
        raise ValueError(f"{unit} receipt unit identity drifted")
    if value.get("coordinate_bearing_artifacts_uploaded") is not False:
        raise ValueError(f"{unit} receipt cannot expose coordinate-bearing artifacts")
    if value.get("field_outcomes_opened") is not False:
        raise ValueError(f"{unit} has opened field outcomes")
    if value.get("fine_patch_transfer", {}).get("transfer_is_validated_selector") is not False:
        raise ValueError(f"{unit} cannot promote patch selector")
    for section, key in DIGEST_FIELDS:
        digest = value.get(section, {}).get(key)
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"{unit} missing {section}.{key} SHA256")
        if any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"{unit} invalid hexadecimal digest {section}.{key}")
    for section, key in COUNT_FIELDS:
        number = value.get(section, {}).get(key)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            raise ValueError(f"{unit} invalid {section}.{key} count")
    if (
        value["structural"]["source_complete_rows"]
        + value["structural"]["source_indeterminate_rows"]
        != value["grid"]["candidate_rows"]
    ):
        raise ValueError(f"{unit} structural denominator not preserved")
    if (
        value["gsi"]["source_complete_rows"]
        + value["gsi"]["provider_unavailable_rows"]
        + value["gsi"]["terrain_vector_unavailable_rows"]
        != value["grid"]["candidate_rows"]
    ):
        raise ValueError(f"{unit} GSI denominator not preserved")
    return value


def audit_two_replays(
    original_root: Path,
    replay_root: Path,
    *,
    frozen_result_path: Path = SOURCE_RECEIPT,
) -> dict[str, Any]:
    frozen = _read_json(frozen_result_path)
    if frozen.get("status") != "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED":
        raise ValueError("original patch representation receipt is not frozen")
    if set(frozen.get("units", {})) != set(UNITS):
        raise ValueError("frozen four-unit set changed")
    if frozen.get("source_workflow_run") != SOURCE_RUN_ID:
        raise ValueError("frozen original run identity changed")

    details: dict[str, Any] = {}
    equal_gsi: list[str] = []
    equal_structural: list[str] = []
    equal_patches: list[str] = []

    for unit in UNITS:
        original = _read_unit(original_root, unit)
        replay = _read_unit(replay_root, unit)
        pinned = frozen["units"][unit]
        for key, from_receipt in (
            ("fine_grid_candidate_count", ("grid", "candidate_rows")),
            ("gsi_source_complete_count", ("gsi", "source_complete_rows")),
            ("structural_source_complete_count", ("structural", "source_complete_rows")),
            ("transferred_2p5pct_retained_cell_count", ("fine_patch_transfer", "retained_support_cell_count")),
            ("complete_link_patch_count", ("fine_patch_transfer", "patch_count")),
        ):
            section, field = from_receipt
            if original[section][field] != pinned[key]:
                raise ValueError(f"{unit} original count differs from frozen PR248 {key}")
        for frozen_field, (section, key) in (
            ("structural_order_sha256", ("structural", "private_structural_order_sha256")),
            ("private_patch_sha256", ("fine_patch_transfer", "private_patch_sha256")),
        ):
            if original[section][key] != pinned[frozen_field]:
                raise ValueError(f"{unit} original SHA differs from frozen PR248 {frozen_field}")

        count_matches = all(original[s][k] == replay[s][k] for s, k in COUNT_FIELDS)
        if not count_matches:
            raise ValueError(f"{unit} source/replay count denominator drifted")
        same_attributions = original["gsi"]["attributions"] == replay["gsi"]["attributions"]
        feature_same = (
            original["gsi"]["terrain_feature_digest_sha256"]
            == replay["gsi"]["terrain_feature_digest_sha256"]
        )
        order_same = (
            original["structural"]["private_structural_order_sha256"]
            == replay["structural"]["private_structural_order_sha256"]
        )
        patch_same = (
            original["fine_patch_transfer"]["private_patch_sha256"]
            == replay["fine_patch_transfer"]["private_patch_sha256"]
        )
        if feature_same:
            equal_gsi.append(unit)
        if order_same:
            equal_structural.append(unit)
        if patch_same:
            equal_patches.append(unit)
        same_digests = {
            f"{section}.{field}": {
                "original_sha256": original[section][field],
                "replay_sha256": replay[section][field],
                "byte_or_digest_equal": original[section][field] == replay[section][field],
            }
            for section, field in DIGEST_FIELDS
        }
        details[unit] = {
            "source_counts_identical": count_matches,
            "gsi_attribution_categories_identical": same_attributions,
            "source_state_digest_identical": same_digests[
                "structural.source_state_digest_sha256"
            ]["byte_or_digest_equal"],
            "selected_patch_count": original["fine_patch_transfer"]["patch_count"],
            "retained_support_cells": original["fine_patch_transfer"]["retained_support_cell_count"],
            "digests": same_digests,
        }

    final_patch_reproducible = len(equal_patches) == len(UNITS)
    full_source_reproducible = len(equal_gsi) == len(UNITS)
    full_structural_reproducible = len(equal_structural) == len(UNITS)
    return {
        "schema_version": "cirsium-fresh-sentinel-v2-source-replay-integrity-v1",
        "status": (
            "UPSTREAM_GSI_REPLAY_DRIFT_FINAL_PATCHES_IDENTICAL"
            if not full_source_reproducible and final_patch_reproducible
            else "REPLAY_STATE_REQUIRES_REVIEW"
        ),
        "source_run_id": SOURCE_RUN_ID,
        "replay_run_id": REPLAY_RUN_ID,
        "source_pr": 247,
        "replay_pr": 249,
        "cohort_unit_ids": list(UNITS),
        "units": details,
        "summary": {
            "gsi_terrain_feature_digest_matching_units": equal_gsi,
            "structural_full_order_sha_matching_units": equal_structural,
            "final_patch_csv_sha_matching_units": equal_patches,
            "source_complete_and_patch_counts_preserved_all_units": True,
            "all_four_patch_representations_byte_identical": final_patch_reproducible,
            "upstream_gsi_content_reproducible_all_units": full_source_reproducible,
            "structural_full_order_reproducible_all_units": full_structural_reproducible,
            "upstream_drift_cause_identified": False,
        },
        "claim_boundary": {
            "pre_outcome_receipts_only": True,
            "private_coordinates_opened": False,
            "prospective_field_outcomes_opened": False,
            "source_indeterminate_is_biological_absence": False,
            "matching_patch_sha_rescues_upstream_reproducibility": False,
            "may_retune_gsi_chunk_phase_or_source_on_replay": False,
            "may_promote_fine_field_selector": False,
        },
        "next_gate": (
            "Fail closed on original structural-order SHA mismatches in PR250; "
            "diagnose earliest GSI source/terrain difference without private "
            "coordinates or field outcomes, and keep 4/4 patch stability "
            "separate from 2/4 upstream replay mismatch."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dir", type=Path, required=True)
    parser.add_argument("--replay-dir", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    if args.out_json.exists():
        raise SystemExit("refusing to overwrite source-replay integrity audit")
    result = audit_two_replays(args.original_dir, args.replay_dir)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
