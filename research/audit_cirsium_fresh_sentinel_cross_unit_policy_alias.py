#!/usr/bin/env python3
"""Audit cross-taxon *method-policy* identity, without opening private sites or outcomes.

This does not establish whether the private 100-m coordinates, support values, or
patches are identical. Those require a separate canonical spatial parity audit.
The goal here is to prevent shared decision recipes from being described as
independently species-conditioned algorithms.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
UNIT_A, UNIT_B = "CIR12", "CIR13"
COHORT = ("CIR02", "CIR06", UNIT_A, UNIT_B)
SOURCE_CONTRACT = "validation/coverage_then_fine_structure_fresh_sentinel_v2_source_indeterminate_retention_v1.json"
COARSE_CONTRACT = "validation/coverage_then_fine_structure_fresh_sentinel_v2_coarse_evidence_order_v1.json"
UNIT_CONTRACT = "validation/coverage_then_fine_structure_fresh_sentinel_v2.json"
COARSE_RECEIPT = "validation/coverage_then_fine_structure_fresh_sentinel_v2_coarse_output_manifest_v1.json"
FINE_GRID_RECEIPT = "validation/coverage_then_fine_structure_fresh_sentinel_v2_primary_fine_grid_materialization_result_v1.json"
FINE_PATCH_RECEIPT = "validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
COUNTS = (
    "fine_grid_candidate_count",
    "gsi_source_complete_count",
    "structural_source_complete_count",
    "structural_source_indeterminate_count",
    "transferred_2p5pct_retained_cell_count",
    "complete_link_patch_count",
    "singleton_patch_count",
    "median_patch_member_count",
    "maximum_patch_member_count",
)


def _read(root: Path, relative: str) -> dict[str, Any]:
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"contract must be an object: {relative}")
    return value


def audit_cross_unit_policy_alias(root: Path = ROOT) -> dict[str, Any]:
    root = Path(root)
    source = _read(root, SOURCE_CONTRACT)
    coarse = _read(root, COARSE_CONTRACT)
    units = _read(root, UNIT_CONTRACT)
    manifest = _read(root, COARSE_RECEIPT)
    fine_grid = _read(root, FINE_GRID_RECEIPT)
    fine = _read(root, FINE_PATCH_RECEIPT)

    expected_statuses = (
        (source, "FROZEN_BEFORE_SOURCE_AVAILABILITY_COMPOSITION"),
        (coarse, "FROZEN_BEFORE_COARSE_EVIDENCE_ORDER_EXECUTION"),
        (units, "FROZEN_BEFORE_PUBLIC_BROAD_FRAME_EXECUTION"),
        (manifest, "PUBLIC_SAFE_COARSE_OUTPUT_MANIFEST_FROZEN"),
        (fine_grid, "PRIMARY_FINE_GRID_MATERIALIZATION_REPRODUCED_PRE_OUTCOME"),
        (fine, "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED"),
    )
    for obj, expected in expected_statuses:
        if obj.get("status") != expected:
            raise ValueError("unexpected source contract/receipt status")

    requirements = source["unit_source_requirements"]
    roles = units["unit_roles"]
    orders = coarse["orders"]
    if set(roles) != set(COHORT) or set(requirements) != set(COHORT):
        raise ValueError("frozen cohort identity drifted")

    family_a = roles[UNIT_A]["structural_feature_family"]
    family_b = roles[UNIT_B]["structural_feature_family"]
    if family_a != "OPEN_GRASSLAND_STRUCTURE" or family_a != family_b:
        raise ValueError("CIR12/CIR13 structural family no longer shared")
    if requirements[UNIT_A]["required_coarse_sources"] != requirements[UNIT_B]["required_coarse_sources"]:
        raise ValueError("CIR12/CIR13 source requirements differ")
    if requirements[UNIT_A]["required_coarse_sources"] != ["terrain", "worldcover"]:
        raise ValueError("grassland source requirements changed")
    for key in ("feature_family",):
        if requirements[UNIT_A][key] != requirements[UNIT_B][key]:
            raise ValueError(f"CIR12/CIR13 source recipe {key} differs")
    for key in ("feature_family", "source_ready_requires", "direct_landcover_signal", "order", "terrain_used_for_order"):
        if orders[UNIT_A][key] != orders[UNIT_B][key]:
            raise ValueError(f"CIR12/CIR13 coarse order {key} differs")
    if orders[UNIT_A]["order"] != ["direct_grass_signal DESC", "stable_candidate_sha256 ASC"]:
        raise ValueError("coarse ranking recipe changed")

    counts = {}
    for unit in (UNIT_A, UNIT_B):
        counts[unit] = {
            "coarse_source_ready": manifest["units"][unit]["source_ready_candidate_count"],
            "retained_coarse_centers": fine_grid["units"][unit]["retained_coarse_center_count"],
            **{k: fine["units"][unit][k] for k in COUNTS},
        }
    if counts[UNIT_A] != counts[UNIT_B]:
        raise ValueError("CIR12/CIR13 source or patch counts diverged")
    if manifest["coarse_order_summary_facts"]["CIR12_direct_grass_signal_count"] != (
        manifest["coarse_order_summary_facts"]["CIR13_direct_grass_signal_count"]
    ):
        raise ValueError("grassland source signal counts diverged")

    families = {u: roles[u]["structural_feature_family"] for u in COHORT}
    return {
        "schema_version": "cirsium-fresh-sentinel-cross-unit-policy-alias-audit-v1",
        "status": "SHARED_GRASSLAND_POLICY_CONFIRMED_SPATIAL_IDENTITY_UNVERIFIED",
        "as_of_date": "2026-10-08",
        "cohort_units": list(COHORT),
        "biological_taxon_count": len(COHORT),
        "distinct_frozen_structural_family_count": len(set(families.values())),
        "families": families,
        "shared_policy_units": [UNIT_A, UNIT_B],
        "shared_source_requirements": requirements[UNIT_A]["required_coarse_sources"],
        "shared_coarse_order_rule": orders[UNIT_A]["order"],
        "same_public_coarse_and_fine_counts": True,
        "shared_counts": counts[UNIT_A],
        "private_coordinate_set_equality_verified": False,
        "private_ecological_support_vector_equality_verified": False,
        "private_patch_membership_equality_verified": False,
        "different_gzip_sha256_establishes_spatial_independence": False,
        "prospective_field_outcomes_opened": False,
        "species_specific_model_generality_claim_authorized": False,
        "field_selector_validation": False,
        "interpretation": (
            "Four biological taxa share three declared structural recipe families; "
            "CIR12 and CIR13 have the same input requirements and coarse rules. "
            "Matching public counts are not a private coordinate-level parity test. "
            "A prospective field contrast may still have four distinct biological "
            "response taxa, but not four independent species-specific selection recipes."
        ),
        "next_gate": (
            "Hash-verify and compare normalized private grid coordinates, "
            "ecological support and patch membership without publishing coordinates; "
            "retain the original preregistered four-taxon estimand unchanged."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    if args.out_json.exists():
        raise SystemExit("refusing to overwrite cross-unit alias audit")
    report = audit_cross_unit_policy_alias()
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
