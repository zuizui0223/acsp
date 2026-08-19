"""Command-line interface for reproducible ACSP survey planning."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from .auto_plan import plan_auto_effort
from .planning import recommend_candidates, recommend_survey_zones

AUTO_COVERAGE_RADIUS_KM = 1.0


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected an integer, got {value!r}.") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("Value must be at least 1.")
    return number


def _add_column_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--latitude-column", default="latitude")
    parser.add_argument("--longitude-column", default="longitude")
    parser.add_argument("--area-column", default="survey_area_id")
    parser.add_argument("--site-column", default="site_id")
    parser.add_argument(
        "--taxon-profile",
        required=True,
        choices=["plant", "bird", "amphibian", "reptile", "arthropod", "mammal", "fish", "unknown"],
        help="Taxon metadata used to select internal field-effort assumptions.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acsp-recommend",
        description="Select survey candidates or infer a reachable automatic field plan.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    recommend = subparsers.add_parser("recommend")
    recommend.add_argument("--input", required=True)
    recommend.add_argument("--output", required=True)
    recommend.add_argument("--summary-json", default="acsp-summary.json")
    recommend.add_argument("--per-area", type=_positive_int, default=3)
    recommend.add_argument("--default-total", type=_positive_int, default=8)
    recommend.add_argument("--area-column", default="survey_area_id")
    recommend.add_argument("--score-column", default="priority_score")
    recommend.add_argument("--site-column", default="site_id")
    recommend.add_argument("--extent", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    recommend.add_argument("--latitude-column", default="latitude")
    recommend.add_argument("--longitude-column", default="longitude")

    zones = subparsers.add_parser("zones")
    zones.add_argument("--input", required=True)
    zones.add_argument("--output", required=True)
    zones.add_argument("--summary-json", default="acsp-summary.json")
    zones.add_argument("--per-area", type=_positive_int, default=3)
    zones.add_argument("--default-total", type=_positive_int, default=8)
    zones.add_argument("--area-column", default="survey_area_id")
    zones.add_argument("--score-column", default="priority_score")
    zones.add_argument("--site-column", default="site_id")
    zones.add_argument("--extent", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    zones.add_argument("--latitude-column", default="latitude")
    zones.add_argument("--longitude-column", default="longitude")
    zones.add_argument("--merge-distance-m", type=float, default=None)

    auto = subparsers.add_parser(
        "auto-effort",
        help=(
            "Infer survey size, hours, and field days from an explicit human-reachable movement graph. "
            "Target days, target site count, and straight-line routing are not accepted."
        ),
    )
    auto.add_argument("--input", required=True, help="Prefiltered candidate CSV.")
    auto.add_argument("--output", required=True)
    auto.add_argument("--summary-json", default="acsp-auto-effort-summary.json")
    auto.add_argument("--frontier-audit", default="acsp-auto-effort-frontier.csv")
    auto.add_argument("--reachability-audit", default="acsp-auto-effort-reachability.csv")
    auto.add_argument(
        "--movement-edges",
        "--travel-matrix",
        dest="movement_edges",
        required=True,
        help="Sparse directed movement-edge CSV with from_id,to_id,travel_minutes,mode.",
    )
    auto.add_argument("--hub-id", default="__hub__")
    auto.add_argument(
        "--allowed-mode",
        action="append",
        required=True,
        dest="allowed_modes",
        help="Physically available movement mode; repeat for walk/road/trail/ferry as applicable.",
    )
    auto.add_argument(
        "--undirected-movement-edges",
        "--undirected-travel-matrix",
        dest="undirected_movement_edges",
        action="store_true",
        help="Mirror supplied edges only when both directions genuinely have identical cost.",
    )
    _add_column_args(auto)
    return parser


def _protocol_for_profile(profile: str) -> dict[str, object]:
    from acsp_discover import infer_survey_protocol

    metadata_by_profile = {
        "plant": {"kingdom": "Plantae"},
        "bird": {"kingdom": "Animalia", "class": "Aves"},
        "amphibian": {"kingdom": "Animalia", "class": "Amphibia"},
        "reptile": {"kingdom": "Animalia", "class": "Reptilia"},
        "arthropod": {"kingdom": "Animalia", "class": "Insecta"},
        "mammal": {"kingdom": "Animalia", "class": "Mammalia"},
        "fish": {"kingdom": "Animalia", "class": "Actinopterygii"},
        "unknown": {},
    }
    protocol = infer_survey_protocol(metadata_by_profile[str(profile)]).as_dict()
    protocol["surface_domain"] = "inland_aquatic" if profile == "fish" else "terrestrial"
    return protocol


def run_recommendation(args: argparse.Namespace) -> dict[str, object]:
    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary_json)
    if not input_path.is_file():
        raise FileNotFoundError(f"Candidate CSV was not found: {input_path}")
    candidates = pd.read_csv(input_path)
    if args.extent is not None:
        from .planning import filter_candidates_to_extent

        candidates_for_selection = filter_candidates_to_extent(
            candidates, args.extent, args.latitude_column, args.longitude_column
        )
    else:
        candidates_for_selection = candidates

    if args.command == "zones":
        selected = recommend_survey_zones(
            candidates_for_selection,
            per_area=args.per_area,
            default_total=args.default_total,
            merge_distance_m=args.merge_distance_m,
            area_col=args.area_column,
            latitude_col=args.latitude_column,
            longitude_col=args.longitude_column,
            id_col=args.site_column,
            score_col=args.score_column,
        )
    else:
        selected = recommend_candidates(
            candidates_for_selection,
            per_area=args.per_area,
            default_total=args.default_total,
            area_col=args.area_column,
            score_col=args.score_column,
            id_col=args.site_column,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(output_path, index=False)
    area_counts: dict[str, int] = {}
    if args.area_column in selected.columns:
        area_counts = {
            str(area): int(count)
            for area, count in selected.groupby(args.area_column, dropna=False).size().items()
        }
    summary: dict[str, object] = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "input_candidate_count": int(len(candidates)),
        "selected_count": int(len(selected)),
        "output_unit": "survey_zone" if args.command == "zones" else "candidate_point",
        "per_area": int(args.per_area),
        "default_total": int(args.default_total),
        "area_column": args.area_column,
        "area_column_present": bool(args.area_column in candidates.columns),
        "score_column": args.score_column,
        "site_column": args.site_column,
        "extent": list(args.extent) if args.extent is not None else None,
        "selected_count_by_area": area_counts,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def run_auto_effort(args: argparse.Namespace) -> dict[str, object]:
    input_path = Path(args.input)
    movement_path = Path(args.movement_edges)
    output_path = Path(args.output)
    summary_path = Path(args.summary_json)
    frontier_path = Path(args.frontier_audit)
    reachability_path = Path(args.reachability_audit)
    if not input_path.is_file():
        raise FileNotFoundError(f"Candidate CSV was not found: {input_path}")
    if not movement_path.is_file():
        raise FileNotFoundError(f"Movement-edge CSV was not found: {movement_path}")

    candidates = pd.read_csv(input_path, dtype={args.site_column: "string"})
    movement_edges = pd.read_csv(
        movement_path,
        dtype={"from_id": "string", "to_id": "string"},
    )
    protocol = _protocol_for_profile(args.taxon_profile)
    selected, plan_audit, frontier, reachability = plan_auto_effort(
        candidates,
        movement_edges=movement_edges,
        hub_id=args.hub_id,
        allowed_modes=args.allowed_modes,
        survey_protocol=protocol,
        coverage_radius_km=AUTO_COVERAGE_RADIUS_KM,
        site_id_col=args.site_column,
        latitude_col=args.latitude_column,
        longitude_col=args.longitude_column,
        group_col=args.area_column,
        undirected=bool(args.undirected_movement_edges),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(output_path, index=False)
    frontier_path.parent.mkdir(parents=True, exist_ok=True)
    frontier.to_csv(frontier_path, index=False)
    reachability_path.parent.mkdir(parents=True, exist_ok=True)
    reachability.to_csv(reachability_path, index=False)

    summary: dict[str, object] = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "frontier_audit_csv": str(frontier_path),
        "reachability_audit_csv": str(reachability_path),
        "input_candidate_count": int(len(candidates)),
        "reachable_candidate_count": int(plan_audit.reachable_candidates),
        "unreachable_candidate_count": int(plan_audit.unreachable_candidates),
        "selected_count": int(len(selected)),
        "hub_id": str(args.hub_id),
        "allowed_modes": sorted(set(str(x) for x in args.allowed_modes)),
        "taxon_profile": str(args.taxon_profile),
        "survey_protocol": protocol,
        "automatic_plan": plan_audit.as_dict(),
        "routing_mode": "explicit_sparse_human_movement_graph",
        "movement_edges_csv": str(movement_path),
        "movement_graph_undirected": bool(args.undirected_movement_edges),
        "reachability_applied_before_coverage": True,
        "target_days_user_supplied": False,
        "target_site_count_user_supplied": False,
        "survey_budget_user_supplied": False,
        "straight_line_fallback": False,
        "coverage_radius_km_internal": AUTO_COVERAGE_RADIUS_KM,
        "selection_rule": (
            "filter to candidates with explicit directed hub round trips; construct full maximum-coverage "
            "order on that reachable set; then choose the deterministic coverage-versus-effort knee"
        ),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command in {"recommend", "zones"}:
        summary = run_recommendation(args)
    elif args.command == "auto-effort":
        summary = run_auto_effort(args)
    else:
        parser.error(f"Unsupported command: {args.command}")
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
