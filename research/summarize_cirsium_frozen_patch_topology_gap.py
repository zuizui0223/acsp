#!/usr/bin/env python3
"""Secondary, public-only synthesis of the already-frozen Cirsium patch topology.

No new high-support cells or biological cohorts are generated. The output
separates within-patch fragmentation and between-patch grid adjacency;
neither count represents independent occupied field sites.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_TOPOLOGY = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_frozen_patch_topology_result_v1.json"
ORIGINAL_PATCHES = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
DEFAULT_OUTPUT = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_patch_topology_component_gap_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
FAMILIES = {
    "CIR02": "WETLAND_MOISTURE_STRUCTURE",
    "CIR06": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR12": "OPEN_GRASSLAND_STRUCTURE",
    "CIR13": "OPEN_GRASSLAND_STRUCTURE",
}
METRICS = (
    "retained_support_cell_count", "complete_link_patch_count",
    "connected_patch_count", "disconnected_patch_count",
    "disconnected_patch_fraction", "cells_in_disconnected_patches",
    "cells_in_disconnected_patch_fraction", "global_mask_component_count",
    "extra_within_patch_components", "maximum_components_per_patch",
)


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _count(x: Any, name: str, *, can_be_zero: bool = False) -> int:
    require(isinstance(x, int) and not isinstance(x, bool), f"{name} must be an integer")
    require(x >= (0 if can_be_zero else 1), f"{name} invalid count")
    return x


def _fraction(x: Any, numerator: int, denominator: int, *, name: str) -> float:
    require(isinstance(x, (float, int)) and not isinstance(x, bool), f"{name} missing")
    require(math.isfinite(float(x)) and math.isclose(float(x), numerator / denominator, rel_tol=0, abs_tol=2e-15),
            f"{name} failed source fraction accounting")
    return numerator / denominator


def build_topology_component_gap(result: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    """Derive exact component-count identities from existing source-bound summaries.

    Does not change or reproduce any source GSI, high-support mask, ranking,
    site assignment, ecological trait, or field/effort result.
    """
    require(result.get("schema_version") == "coverage-then-fine-structure-fresh-sentinel-v2-frozen-patch-topology-result-v1"
            and result.get("status") == "FOUR_UNIT_FROZEN_PATCH_MASK_TOPOLOGY_COMPLETE_PRE_OUTCOME",
            "original frozen topology source changed")
    require(result.get("source_pr") == 256 and result.get("source_run_id") == 37732320419,
            "original topology source provenance changed")
    require(result.get("distinct_declared_structural_family_count") == 3,
            "original three family policy count changed")
    require(tuple(result.get("cohort_unit_ids", ())) == UNITS
            and isinstance(result.get("units"), dict)
            and set(result["units"]) == set(UNITS),
            "the four original Cirsium topology units are not available")
    flags = result.get("interpretation", {})
    require(flags.get("topology_only") is True
            and flags.get("exact_original_frozen_patch_bytes_verified_all_four") is True
            and flags.get("connectedness_of_retained_2p5pct_mask_not_habitat_connectivity") is True,
            "unverified or biological interpretation of frozen topology")
    for key in ("prospective_field_outcomes_opened", "full_structural_order_sha_replay_tested_by_this_route",
                "field_selector_validation", "species_specific_selector_independence_claimed"):
        require(flags.get(key) is False, "unsupported ecological or full-order promotion: " + key)
    require(frozen.get("status") == "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED"
            and frozen.get("source_pr") == 247 and set(frozen.get("units", {})) == set(UNITS),
            "original 2.5%-support patch freeze changed")
    constants = frozen.get("transferred_constants", {})
    require(constants.get("support_fraction") == 0.025
            and constants.get("complete_link_max_distance_m") == 1000,
            "original candidate support or patch diameter changed")

    units: dict[str, Any] = {}
    for unit in UNITS:
        original = result["units"][unit]
        baseline = frozen["units"][unit]
        require(original.get("feature_family") == FAMILIES[unit], f"{unit} family changed")
        require(original.get("verified_original_patch_sha256") == baseline.get("private_patch_sha256"),
                f"{unit} frozen patch SHA differs")
        require(original.get("all_retained_cells_accounted_for") is True,
                f"{unit} original source count incomplete")
        require(original.get("ecological_connectivity_claim_authorized") is False,
                f"{unit} unsupported ecological connectivity claim")
        require(original.get("source_integrity_claim_authorized") is False,
                f"{unit} full GSI source integrity not verified by topology")

        patch_count = _count(original.get("complete_link_patch_count"), f"{unit} patches")
        selected_cells = _count(original.get("retained_support_cell_count"), f"{unit} cells")
        disconnected = _count(original.get("disconnected_patch_count"), f"{unit} disconnected", can_be_zero=True)
        connected = _count(original.get("connected_patch_count"), f"{unit} connected", can_be_zero=True)
        require(connected + disconnected == patch_count, f"{unit} patch accounting does not balance")
        require(patch_count == baseline.get("complete_link_patch_count")
                and selected_cells == baseline.get("transferred_2p5pct_retained_cell_count"),
                f"{unit} original frozen patch denominators changed")
        cells_in_disconnected = _count(original.get("cells_in_disconnected_patches"), f"{unit} fragmented cells", can_be_zero=True)
        require(cells_in_disconnected <= selected_cells, f"{unit} fragmented cell count exceeds total")
        dfrac = _fraction(original.get("disconnected_patch_fraction"), disconnected, patch_count, name="disconnected patch fraction")
        cfrac = _fraction(original.get("cells_in_disconnected_patch_fraction"), cells_in_disconnected, selected_cells, name="fragmented cell fraction")
        global_components = _count(original.get("global_mask_component_count"), f"{unit} global component")
        within_patch_extra = _count(original.get("extra_within_patch_components"), f"{unit} extra", can_be_zero=True)
        largest = _count(original.get("maximum_components_per_patch"), f"{unit} largest component count")
        require(largest <= selected_cells and (largest == 1 if disconnected == 0 else largest >= 2),
                f"{unit} impossible within-patch fragmentation")
        within_patch_total = patch_count + within_patch_extra
        require(global_components <= within_patch_total,
                f"{unit} global component count exceeds within-patch components")
        require(global_components <= selected_cells, f"{unit} global component count exceeds retained cells")

        net_cross_patch_unions = within_patch_total - global_components
        signed_gap = global_components - patch_count
        require(signed_gap == within_patch_extra - net_cross_patch_unions,
                f"{unit} signed-component identity failed")
        units[unit] = {
            "feature_family": FAMILIES[unit],
            "frozen_private_patch_sha256": original["verified_original_patch_sha256"],
            "retained_support_cell_count": selected_cells,
            "complete_link_patch_count": patch_count,
            "connected_patch_count": connected,
            "disconnected_patch_count": disconnected,
            "disconnected_patch_fraction": dfrac,
            "cells_in_disconnected_patches": cells_in_disconnected,
            "cells_in_disconnected_patch_fraction": cfrac,
            "extra_within_patch_components": within_patch_extra,
            "within_patch_component_total": within_patch_total,
            "global_mask_component_count": global_components,
            "net_cross_patch_component_unions": net_cross_patch_unions,
            "global_components_minus_patches": signed_gap,
            "global_components_per_patch": global_components / patch_count,
            "gap_direction": (
                "MORE_COMPONENTS_THAN_PATCHES" if signed_gap > 0
                else "FEWER_COMPONENTS_THAN_PATCHES" if signed_gap < 0
                else "EQUAL_COUNTS_NOT_EQUAL_GEOMETRY"
            ),
            "maximum_components_per_patch": largest,
            "fragmentation_burden_cells_minus_patches_pp": 100 * (cfrac - dfrac),
        }

    grass_a, grass_b = units["CIR12"], units["CIR13"]
    repeated = all(grass_a[key] == grass_b[key] for key in METRICS if key in grass_a)
    require(repeated, "paired grassland aggregate metrics unexpectedly differ")
    # Identical aggregate counts do not mean spatial congruence; their exact
    # compressed frozen patch membership hashes are different.
    different_archive_sha = grass_a["frozen_private_patch_sha256"] != grass_b["frozen_private_patch_sha256"]
    require(different_archive_sha, "paired grassland compressed patch archives unexpectedly identical")

    return {
        "schema_version": "acsp-cirsium-frozen-patch-topology-component-gap-secondary-v1",
        "status": "POSTHOC_DESCRIPTIVE_SYNTHESIS_OF_PREVIOUSLY_FROZEN_TOPOLOGY",
        "source": {
            "source_result": "validation/coverage_then_fine_structure_fresh_sentinel_v2_frozen_patch_topology_result_v1.json",
            "source_pr": 256,
            "source_run_id": 37732320419,
            "patch_source_pr": 247,
            "support_fraction": 0.025,
            "patch_complete_link_diameter_m": 1000,
            "grid_cell_spacing_m": 100,
            "connectivity_definition": "MOORE_8_NEIGHBOUR_WITHIN_SELECTED_100M_HIGH_SUPPORT_MASK",
            "scope": "FOUR_CIRSIUM_UNITS_THREE_DECLARED_STRUCTURAL_FAMILIES_NO_INDEPENDENT_BIOLOGICAL_CONFIRMATION",
        },
        "units": units,
        "grassland_aggregate_metrics_equal": repeated,
        "grassland_compressed_patch_archive_sha_equal": not different_archive_sha,
        "interpretation": {
            "component_count_identity": "within_patch_component_total = patch_count + extra_within_patch_components",
            "cross_patch_identity": "net_cross_patch_component_unions = within_patch_component_total - global_mask_component_count",
            "signed_gap_identity": "global_components_minus_patches = extra_within_patch_components - net_cross_patch_component_unions",
            "unions_are_net_component_reductions_not_unique_adjacency_edges": True,
        },
        "claims": {
            "this_is_new_biological_sampling": False,
            "treat_four_units_as_independent_ecological_replicates": False,
            "grassland_units_are_spatially_identical": False,
            "use_connected_component_count_as_field_visit_count": False,
            "source_integrity_or_full_structural_order_replay_verified_here": False,
            "treat_disconnected_support_as_habitat_barriers_or_absences": False,
            "field_recovery_efficiency_or_occupancy_inferred": False,
            "validated_Japan_candidate_patch_algorithm_changed": False,
            "field_outcomes_opened": False,
        },
    }


def verify_saved_summary(saved: dict[str, Any], source: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    expected = build_topology_component_gap(source, frozen)
    require(saved == expected, "derived topology snapshot differs from exact frozen inputs")
    return {"status": "FROZEN_TOPOLOGY_GAP_DERIVATION_REPRODUCED", "unit_count": len(UNITS)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-topology", type=Path, default=ORIGINAL_TOPOLOGY)
    p.add_argument("--frozen-patches", type=Path, default=ORIGINAL_PATCHES)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--out-json", type=Path)
    group.add_argument("--verify-json", type=Path)
    args = p.parse_args()
    original = json.loads(args.original_topology.read_text(encoding="utf-8"))
    patches = json.loads(args.frozen_patches.read_text(encoding="utf-8"))
    if args.out_json:
        if args.out_json.is_symlink() or args.out_json.exists():
            raise ValueError("refusing to overwrite preexisting derived topology result")
        data = build_topology_component_gap(original, patches)
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)+"\n", encoding="utf-8")
        print(json.dumps({"status": data["status"], "unit_count": len(data["units"])}))
    else:
        data = json.loads(args.verify_json.read_text(encoding="utf-8"))
        print(json.dumps(verify_saved_summary(data, original, patches)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
