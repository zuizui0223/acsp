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


def _write_summary(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _validated_product_summary(
    patches,
    discovery_audit: dict[str, object],
    output_path: Path,
) -> dict[str, object]:
    return {
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
        "output_csv": str(output_path),
        "discovery_audit": discovery_audit,
    }


def _artifact_boundary(candidate_written: bool, operational_written: bool) -> dict[str, object]:
    return {
        "candidate_patches_written_before_operations": bool(candidate_written),
        "candidate_patch_artifact_filtered_by_operations": False,
        "operational_output_is_separate_artifact": True,
        "operational_visits_written": bool(operational_written),
    }


def _failure_summary(
    args: argparse.Namespace,
    *,
    failed_stage: str,
    exc: Exception,
    validated_product: dict[str, object] | None = None,
    downstream: dict[str, object] | None = None,
    candidate_written: bool = False,
) -> dict[str, object]:
    return {
        "status": "field_plan_failed",
        "taxon": str(args.taxon),
        "failed_stage": str(failed_stage),
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
        },
        "validated_candidate_product": validated_product
        if validated_product is not None
        else {
            "status": "not_generated",
            "non_ranked": True,
            "candidate_patch_count": 0,
            "routing_or_budget_optimization": False,
            "output_csv": str(args.patches_output),
        },
        "downstream_operational_selection": downstream
        if downstream is not None
        else {
            "status": "not_started",
            "movement_constraint_mode": "osm_weighted_transport_network",
            "max_network_transition_km": float(args.osm_network_transition_km),
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
        },
        "artifact_boundary": _artifact_boundary(candidate_written, False),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    if float(args.osm_network_transition_km) <= 0.0:
        exc = ValueError("--osm-network-transition-km must be positive")
        _write_summary(
            args.summary_json,
            _failure_summary(args, failed_stage="input_validation", exc=exc),
        )
        raise exc

    # Stage 1: validated product. If this fails there is no scientific artifact.
    try:
        patches, discovery_audit = discover_validated_candidate_patches_japan(args.taxon)
    except Exception as exc:
        _write_summary(
            args.summary_json,
            _failure_summary(args, failed_stage="candidate_generation", exc=exc),
        )
        raise

    # Persist the complete validated artifact before any provider call. If this
    # write fails, downstream operations must never start.
    try:
        args.patches_output.parent.mkdir(parents=True, exist_ok=True)
        patches.to_csv(args.patches_output, index=False)
    except Exception as exc:
        validated_product = _validated_product_summary(
            patches,
            discovery_audit,
            args.patches_output,
        )
        _write_summary(
            args.summary_json,
            _failure_summary(
                args,
                failed_stage="candidate_artifact_write",
                exc=exc,
                validated_product=validated_product,
                candidate_written=False,
            ),
        )
        raise

    validated_product = _validated_product_summary(
        patches,
        discovery_audit,
        args.patches_output,
    )

    # Stage 2: live/provider-derived movement graph. A failure here must retain
    # the already-written validated candidate artifact unchanged.
    try:
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
    except Exception as exc:
        _write_summary(
            args.summary_json,
            _failure_summary(
                args,
                failed_stage="osm_network_provider",
                exc=exc,
                validated_product=validated_product,
                candidate_written=True,
            ),
        )
        raise

    downstream_base: dict[str, object] = {
        "status": "downstream_operational_osm_network",
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": float(args.osm_network_transition_km),
        "reachability_edge_count": int(len(patch_edges)),
        "attached_candidate_count": int(attachments["network_attached"].sum())
        if "network_attached" in attachments
        else 0,
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
    }

    # Stage 3: selector and operational artifact write. No selector failure may
    # alter or delete the validated candidate artifact.
    try:
        visits, selection_audit = select_reachability_constrained_patches(
            patches,
            patch_edges,
        )
        args.visits_output.parent.mkdir(parents=True, exist_ok=True)
        visits.to_csv(args.visits_output, index=False)
    except Exception as exc:
        failed_downstream = {
            **downstream_base,
            "status": "operational_selection_failed",
        }
        _write_summary(
            args.summary_json,
            _failure_summary(
                args,
                failed_stage="operational_selection",
                exc=exc,
                validated_product=validated_product,
                downstream=failed_downstream,
                candidate_written=True,
            ),
        )
        raise

    summary: dict[str, object] = {
        "status": "validated_candidates_plus_downstream_operations",
        "taxon": str(args.taxon),
        "failed_stage": None,
        "validated_candidate_product": validated_product,
        "downstream_operational_selection": {
            **downstream_base,
            "automatic_selected_count": int(len(visits)),
            "selection_audit": selection_audit.as_dict(),
        },
        "artifact_boundary": _artifact_boundary(True, True),
    }
    _write_summary(args.summary_json, summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
