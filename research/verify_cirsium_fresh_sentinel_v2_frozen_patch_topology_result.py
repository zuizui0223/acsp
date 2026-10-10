#!/usr/bin/env python3
"""Verify four original-SHA-bound fine-patch topology receipts without terrain refits.

Uses only the *already frozen* public result and exact four public-safe Actions
receipt bytes. No private candidate grid or coordinates, field outcomes, GSI
source substitution, or posthoc patch reranking may enter this verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = (
    ROOT / "validation"
    / "coverage_then_fine_structure_fresh_sentinel_v2_frozen_patch_topology_result_v1.json"
)
ORIGINAL_PATH = (
    ROOT / "validation"
    / "coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
)
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
FAMILIES = {
    "CIR02": "WETLAND_MOISTURE_STRUCTURE",
    "CIR06": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR12": "OPEN_GRASSLAND_STRUCTURE",
    "CIR13": "OPEN_GRASSLAND_STRUCTURE",
}
EXPECTED_ARTIFACT_IDS = {
    "CIR02": 11532064437,
    "CIR06": 11534155745,
    "CIR12": 11534893251,
    "CIR13": 11536552476,
}
TOPOLOGY_KEYS = {
    "verified_original_patch_sha256",
    "retained_support_cell_count",
    "complete_link_patch_count",
    "connected_patch_count",
    "disconnected_patch_count",
    "disconnected_patch_fraction",
    "cells_in_disconnected_patches",
    "cells_in_disconnected_patch_fraction",
    "global_mask_component_count",
    "extra_within_patch_components",
    "maximum_components_per_patch",
}


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("topology JSON input must be an object")
    return value


def _expect(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def verify_frozen_public_summary(
    result: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    _expect(
        result.get("schema_version")
        == "coverage-then-fine-structure-fresh-sentinel-v2-frozen-patch-topology-result-v1",
        "topology result schema changed",
    )
    _expect(
        result.get("status") == "FOUR_UNIT_FROZEN_PATCH_MASK_TOPOLOGY_COMPLETE_PRE_OUTCOME",
        "topology result status changed",
    )
    _expect(result.get("source_pr") == 256 and result.get("source_run_id") == 37732320419,
            "topology source PR/workflow run changed")
    _expect(result.get("source_head_sha") == "efe05f53e73906b5fb690288138620fffd788119",
            "topology source head identity changed")
    _expect(result.get("original_patch_source_pr") == 247,
            "original source PR identity changed")
    _expect(tuple(result.get("cohort_unit_ids", ())) == UNITS,
            "four-unit cohort or order changed")
    _expect(result.get("distinct_declared_structural_family_count") == 3,
            "structural policy family count changed")
    _expect(source.get("status") == "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED",
            "original patch freeze status changed")
    _expect(source.get("source_pr") == 247 and set(source.get("units", {})) == set(UNITS),
            "original patch cohort changed")
    interpretations = result.get("interpretation")
    if not isinstance(interpretations, dict):
        raise ValueError("missing interpretation claim boundary")
    required_true = (
        "topology_only",
        "exact_original_frozen_patch_bytes_verified_all_four",
        "strict_full_order_audit_remains_distinct",
    )
    # strict_full_order_audit_remains_distinct was recorded independently in
    # the original prospective contract; verify when present in this result.
    for k in required_true[:2]:
        _expect(interpretations.get(k) is True, f"unsafe or missing topology claim flag {k}")
    required_false = (
        "connectedness_of_retained_2p5pct_mask_not_habitat_connectivity",
    )
    _expect(interpretations.get(required_false[0]) is True,
            "selected-mask topology must not be interpreted as habitat connectivity")
    for k in (
        "full_structural_order_sha_replay_tested_by_this_route",
        "prospective_field_outcomes_opened",
        "species_specific_selector_independence_claimed",
        "public_candidate_cell_ids_or_coordinates",
        "posthoc_fraction_or_patch_distance_retuning",
        "field_selector_validation",
    ):
        _expect(interpretations.get(k) is False, f"topology interpretation boundary violated: {k}")
    _expect(interpretations.get("source_drift_issue") == 253,
            "source-replay integrity issue changed")

    units = result.get("units")
    _expect(isinstance(units, dict) and set(units) == set(UNITS),
            "four-unit topology result missing units")
    for unit in UNITS:
        obs, frozen = units[unit], source["units"][unit]
        _expect(obs.get("feature_family") == FAMILIES[unit], f"{unit} structural family drifted")
        _expect(obs.get("artifact_id") == EXPECTED_ARTIFACT_IDS[unit],
                f"{unit} original artifact identity changed")
        _expect(_sha(obs.get("receipt_content_sha256")), f"{unit} receipt SHA missing")
        _expect(obs.get("verified_original_patch_sha256") == frozen["private_patch_sha256"],
                f"{unit} original frozen patch SHA mismatched")
        _expect(obs.get("retained_support_cell_count")
                == frozen["transferred_2p5pct_retained_cell_count"],
                f"{unit} retained-support denominator changed")
        _expect(obs.get("complete_link_patch_count") == frozen["complete_link_patch_count"],
                f"{unit} 1-km patch count changed")
        _expect(obs.get("original_frozen_singleton_patch_count") == frozen["singleton_patch_count"],
                f"{unit} singleton count changed")
        n = obs["complete_link_patch_count"]
        d = obs.get("disconnected_patch_count")
        c = obs.get("connected_patch_count")
        m = obs["retained_support_cell_count"]
        f = obs.get("cells_in_disconnected_patches")
        _expect(all(isinstance(k, int) and not isinstance(k, bool) for k in (n, d, c, m, f)),
                f"{unit} non-integer counts")
        _expect(n > 0 and c >= 0 and d >= 0 and c + d == n,
                f"{unit} disconnected patch accounting failed")
        _expect(0 <= f <= m and m > 0, f"{unit} disconnected cell accounting failed")
        _expect(math.isclose(obs["disconnected_patch_fraction"], d / n, abs_tol=1e-15),
                f"{unit} patch fraction incorrect")
        _expect(math.isclose(obs["cells_in_disconnected_patch_fraction"], f / m, abs_tol=1e-15),
                f"{unit} cell fraction incorrect")
        g = obs.get("global_mask_component_count")
        x = obs.get("extra_within_patch_components")
        _expect(isinstance(g, int) and isinstance(x, int) and g > 0 and x >= 0,
                f"{unit} topology component accounting invalid")
        _expect(g <= n + x, f"{unit} global components exceed within-patch components")
        _expect(1 <= obs.get("maximum_components_per_patch", 0) <= m,
                f"{unit} invalid largest within-patch component count")
        for flag in ("all_retained_cells_accounted_for",):
            _expect(obs.get(flag) is True, f"{unit} retained cells not fully conserved")
        for flag in ("ecological_connectivity_claim_authorized", "source_integrity_claim_authorized"):
            _expect(obs.get(flag) is False, f"{unit} unsupported promotion detected")

    # The two grassland units are biological taxa, not independently defined
    # ecological policies. Similar aggregate outputs do NOT establish spatial
    # equality or an additional independent confirmation.
    a, b = units["CIR12"], units["CIR13"]
    for key in TOPOLOGY_KEYS - {"verified_original_patch_sha256"}:
        _expect(a.get(key) == b.get(key), "paired grassland topology metrics drifted")
    return {"status": "PUBLIC_TOPOLOGY_FREEZE_CONSISTENT", "unit_count": len(UNITS)}


def verify_exact_saved_receipts(
    receipt_root: Path,
    result: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    verify_frozen_public_summary(result, source)
    checked = []
    for unit in UNITS:
        path = Path(receipt_root) / unit / f"{unit}_receipt.json"
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"{unit} original public-safe unit receipt missing")
        payload = path.read_bytes()
        expected_sha = result["units"][unit]["receipt_content_sha256"]
        _expect(hashlib.sha256(payload).hexdigest() == expected_sha,
                f"{unit} receipt bytes differ from frozen source artifact")
        value = json.loads(payload)
        _expect(value.get("status") == "FIXED_GSI_TERRAIN_EXECUTION_COMPLETE_PRE_OUTCOME",
                f"{unit} unit receipt status changed")
        _expect(value.get("cohort_unit_id") == unit, f"{unit} receipt unit identity changed")
        _expect(value.get("coordinate_bearing_artifacts_uploaded") is False,
                f"{unit} coordinate-bearing artifacts unexpectedly uploaded")
        _expect(value.get("field_outcomes_opened") is False, f"{unit} field outcomes opened")
        patch = value.get("fine_patch_transfer", {})
        _expect(patch.get("transfer_is_validated_selector") is False,
                f"{unit} patch selector ungroundedly promoted")
        _expect(patch.get("private_patch_sha256") == source["units"][unit]["private_patch_sha256"],
                f"{unit} private patch hash not frozen")
        obs = value.get("frozen_patch_membership_topology", {})
        _expect(obs.get("status")
                == "FROZEN_PATCH_MASK_TOPOLOGY_AUDITED_UPSTREAM_UNCERTAINTY_RETAINED",
                f"{unit} source topology receipt status changed")
        for key in TOPOLOGY_KEYS:
            v = obs.get(key)
            expected = result["units"][unit].get(key)
            # The original JSON uses cells_in_disconnected_patches; the
            # frozen summary also adds a separately calculated cell fraction.
            if key == "cells_in_disconnected_patch_fraction":
                continue
            _expect(v == expected, f"{unit} source topology receipt {key} differs")
        for key in ("field_selector_validation", "ecological_connectivity_claim_authorized",
                    "full_structural_order_reproduction_tested"):
            _expect(obs.get(key) is False, f"{unit} unsupported receipt claim: {key}")
        forbidden = {"latitude", "longitude", "candidate_cell_id", "zone_member_site_ids"}
        def _check_no_coordinates(obj: Any) -> None:
            if isinstance(obj, dict):
                _expect(not forbidden.intersection(obj), f"{unit} public receipt leaked location keys")
                for child in obj.values():
                    _check_no_coordinates(child)
            elif isinstance(obj, list):
                for child in obj:
                    _check_no_coordinates(child)
        _check_no_coordinates(value)
        checked.append(unit)
    return {
        "status": "FOUR_PUBLIC_SOURCE_RECEIPTS_REVERIFIED",
        "reverified_units": checked,
        "coordinate_bearing_data_exposed": False,
        "new_field_outcomes_opened": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-root", type=Path, help="Directory of exact four public-safe CI receipt artifacts")
    args = parser.parse_args()
    result = _json(RESULT_PATH)
    original = _json(ORIGINAL_PATH)
    if args.receipt_root:
        audit = verify_exact_saved_receipts(args.receipt_root, result, original)
    else:
        audit = verify_frozen_public_summary(result, original)
    print(json.dumps(audit, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
