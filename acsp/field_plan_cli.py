"""One-command ACSP orchestration from species name to field-plan artifacts.

The validated candidate-patch product is generated and written unchanged before
any downstream operational processing. OSM reachability then produces a separate
operational visit subset. Provider failure cannot alter candidate-patch membership.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .osm_reachability import build_osm_patch_reachability_edges
from .reachability import select_reachability_constrained_patches
from .taxon_patches import discover_validated_candidate_patches_japan
from .validated_robust import (
    VALIDATED_ROBUST_CONFIRMATION_FOLDS,
    VALIDATED_ROBUST_CONFIRMATION_PAIRS,
    VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
    VALIDATED_ROBUST_STATUS,
    VALIDATED_ROBUST_SUPPORT_FRACTION,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acsp-field-plan",
        description=(
            "Generate the validated non-ranked ACSP candidate-patch product for "
            "one species, then separately derive an automatically sized operational "
            "visit subset using OSM weighted road/trail/ferry reachability."
        ),
    )
    parser.add_argument("--taxon", required=True, help="Scientific species name")
    parser.add_argument(
        "--osm-network-transition-km",
        type=float,
        required=True,
        help=(
            "Maximum weighted transport-network transition distance. This is the "
            "only survey-design input; site count is determined automatically."
        ),
    )
    parser.add_argument("--patches-output", type=Path, required=True)
    parser.add_argument("--visits-output", type=Path, required=True)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("acsp-field-plan-summary.json"),
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if float(args.osm_network_transition_km) <= 0.0:
        raise ValueError("--osm-network-transition-km must be positive")

    # Validated product first. The full table is persisted before any provider or
    # operational selector is invoked so downstream failures cannot change it.
    patches, discovery_audit = discover_validated_candidate_patches_japan(args.taxon)
    args.patches_output.parent.mkdir(parents=True, exist_ok=True)
    patches.to_csv(args.patches_output, index=False)

    (
        patch_edges,
        attachments,
        network_nodes,
        network_edges,
        area_provider_audit,
        osm_audit,
    ) = build_osm_patch_reachability_edges(
        patches,
        max_network_transition_km=float(args.osm_network_transition_km),
    )
    visits, selection_audit = select_reachability_constrained_patches(
        patches,
        patch_edges,
    )
    args.visits_output.parent.mkdir(parents=True, exist_ok=True)
    visits.to_csv(args.visits_output, index=False)

    summary: dict[str, object] = {
        "status": "validated_candidates_plus_downstream_operations",
        "taxon": str(args.taxon),
        "validated_candidate_product": {
            "status": VALIDATED_ROBUST_STATUS,
            "scientific_object": "occurrence-conditioned robust environmental candidate patches",
            "output_unit": "candidate_patch",
            "non_ranked": True,
            "candidate_patch_count": int(len(patches)),
            "validated_support_fraction": float(VALIDATED_ROBUST_SUPPORT_FRACTION),
            "validated_patch_merge_distance_m": float(VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M),
            "validation_confirmation_pairs": int(VALIDATED_ROBUST_CONFIRMATION_PAIRS),
            "validation_confirmation_folds": int(VALIDATED_ROBUST_CONFIRMATION_FOLDS),
            "routing_or_budget_optimization": False,
            "output_csv": str(args.patches_output),
            "discovery_audit": discovery_audit,
        },
        "downstream_operational_selection": {
            "status": "downstream_operational_osm_network",
            "movement_constraint_mode": "osm_weighted_transport_network",
            "max_network_transition_km": float(args.osm_network_transition_km),
            "automatic_selected_count": int(len(visits)),
            "reachability_edge_count": int(len(patch_edges)),
            "attached_candidate_count": int(attachments["network_attached"].sum()) if "network_attached" in attachments else 0,
            "network_node_count": int(len(network_nodes)),
            "network_edge_count": int(len(network_edges)),
            "provider_area_count": int(len(area_provider_audit)),
            "straight_line_movement_assumption": False,
            "user_site_count_required": False,
            "user_coverage_target_required": False,
            "survey_days_input": False,
            "monetary_budget_input": False,
            "route_time_claim": False,
            "timetable_claim": False,
            "legal_access_claim": False,
            "safety_claim": False,
            "field_efficiency_claim": False,
            "validated_candidate_membership_changed": False,
            "output_csv": str(args.visits_output),
            "osm_audit": osm_audit,
            "selection_audit": selection_audit.as_dict(),
        },
        "artifact_boundary": {
            "candidate_patches_written_before_operations": True,
            "candidate_patch_artifact_filtered_by_operations": False,
            "operational_output_is_separate_artifact": True,
        },
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
