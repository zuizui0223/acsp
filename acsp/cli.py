"""Command-line interface for reproducible ACSP candidate selection."""

from __future__ import annotations

import argparse
from functools import partial
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from .auto_budget import infer_recommended_effort_from_matrix
from .coverage import select_maximum_coverage_sites
from .operational_budget import select_largest_feasible_prefix
from .planning import recommend_candidates, recommend_survey_zones
from .travel_matrix import estimate_matrix_trip, read_travel_time_matrix
from .trip_proxy import estimate_operational_trip


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected an integer, got {value!r}.") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("Value must be at least 1.")
    return number


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected a number, got {value!r}.") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than 0.")
    return number


def _add_common_geometry_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--coverage-radius-km", type=_positive_float, default=1.0)
    parser.add_argument("--max-sites", type=_positive_int, default=40)
    parser.add_argument("--latitude-column", default="latitude")
    parser.add_argument("--longitude-column", default="longitude")
    parser.add_argument("--area-column", default="survey_area_id")
    parser.add_argument("--site-column", default="site_id")
    parser.add_argument(
        "--taxon-profile",
        required=True,
        choices=["plant", "bird", "amphibian", "reptile", "arthropod", "mammal", "fish", "unknown"],
        help="Operational effort profile used for per-site search assumptions.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acsp-recommend",
        description="Select transparent ACSP field-survey candidates from a CSV file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    recommend = subparsers.add_parser(
        "recommend",
        help="Rank candidate rows and apply an equal per-area quota when multiple survey areas exist.",
    )
    recommend.add_argument("--input", required=True, help="Input candidate CSV path.")
    recommend.add_argument("--output", required=True, help="Output CSV path for selected candidates.")
    recommend.add_argument("--summary-json", default="acsp-summary.json")
    recommend.add_argument("--per-area", type=_positive_int, default=3)
    recommend.add_argument("--default-total", type=_positive_int, default=8)
    recommend.add_argument("--area-column", default="survey_area_id")
    recommend.add_argument("--score-column", default="priority_score")
    recommend.add_argument("--site-column", default="site_id")
    recommend.add_argument("--extent", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    recommend.add_argument("--latitude-column", default="latitude")
    recommend.add_argument("--longitude-column", default="longitude")

    zones = subparsers.add_parser(
        "zones",
        help="Consolidate nearby candidate points and rank practical survey zones.",
    )
    zones.add_argument("--input", required=True, help="Input candidate CSV path.")
    zones.add_argument("--output", required=True, help="Output CSV path for recommended zones.")
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
            "Infer survey size, hours, and field days from an explicit human-reachable movement network. "
            "No target-day budget and no straight-line fallback are used."
        ),
    )
    auto.add_argument("--input", required=True, help="Prefiltered candidate CSV.")
    auto.add_argument("--output", required=True, help="Output CSV for the automatically recommended survey set.")
    auto.add_argument("--summary-json", default="acsp-auto-effort-summary.json")
    auto.add_argument("--frontier-audit", default="acsp-auto-effort-frontier.csv")
    auto.add_argument("--travel-matrix", required=True, help="Long-form travel matrix with explicit mode column.")
    auto.add_argument("--hub-id", default="__hub__", help="Start/end hub endpoint ID in the travel matrix.")
    auto.add_argument(
        "--allowed-mode",
        action="append",
        required=True,
        dest="allowed_modes",
        help="Physically available movement mode; repeat for walk/road/trail/ferry as applicable.",
    )
    auto.add_argument("--undirected-travel-matrix", action="store_true")
    _add_common_geometry_args(auto)

    budget = subparsers.add_parser(
        "budget",
        help="Legacy what-if: truncate a geometry sequence to an explicitly supplied field-day budget.",
    )
    budget.add_argument("--input", required=True, help="Prefiltered candidate CSV.")
    budget.add_argument("--output", required=True, help="Output CSV path for the feasible ordered survey set.")
    budget.add_argument("--summary-json", default="acsp-budget-summary.json")
    budget.add_argument("--prefix-audit", default="acsp-budget-prefix-audit.csv")
    budget.add_argument("--hub-latitude", type=float, required=True)
    budget.add_argument("--hub-longitude", type=float, required=True)
    budget.add_argument("--hub-id", default="__hub__")
    budget.add_argument("--days", type=_positive_int, required=True)
    budget.add_argument(
        "--travel-matrix",
        help=(
            "Optional long-form CSV with from_id,to_id,travel_minutes and optional "
            "distance_km,mode,available columns. Missing directed pairs are unreachable."
        ),
    )
    budget.add_argument("--undirected-travel-matrix", action="store_true")
    _add_common_geometry_args(budget)
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


def _rename_budget_columns(
    ordered: pd.DataFrame,
    *,
    latitude_column: str,
    longitude_column: str,
    site_column: str,
    area_column: str,
) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    for source, target in (
        (latitude_column, "latitude"),
        (longitude_column, "longitude"),
        (site_column, "site_id"),
        (area_column, "survey_area_id"),
    ):
        if source == target or source not in ordered.columns:
            continue
        if target in ordered.columns:
            raise ValueError(f"Cannot rename {source!r} to {target!r}: both columns are present.")
        rename_map[source] = target
    return ordered.rename(columns=rename_map)


def _prepare_geometry_order(args: argparse.Namespace, *, require_site_ids: bool) -> tuple[pd.DataFrame, pd.DataFrame, object, list[str]]:
    input_path = Path(args.input)
    if not input_path.is_file():
        raise FileNotFoundError(f"Candidate CSV was not found: {input_path}")
    dtypes = {args.site_column: "string"} if require_site_ids else None
    candidates = pd.read_csv(input_path, dtype=dtypes)
    if candidates.empty:
        raise ValueError("Candidate CSV is empty.")
    if require_site_ids and args.site_column not in candidates.columns:
        raise ValueError(f"Candidate CSV lacks site column {args.site_column!r} required for routing.")
    areas: list[str] = []
    if args.area_column in candidates.columns:
        areas = candidates[args.area_column].dropna().astype(str).unique().tolist()
    group_col = args.area_column if args.area_column in candidates.columns else None
    ordered, coverage_audit = select_maximum_coverage_sites(
        candidates,
        radius_km=float(args.coverage_radius_km),
        max_sites=int(args.max_sites),
        latitude_col=args.latitude_column,
        longitude_col=args.longitude_column,
        group_col=group_col,
    )
    ordered = _rename_budget_columns(
        ordered,
        latitude_column=args.latitude_column,
        longitude_column=args.longitude_column,
        site_column=args.site_column,
        area_column=args.area_column,
    )
    if "site_id" not in ordered.columns:
        ordered["site_id"] = [str(i) for i in range(1, len(ordered) + 1)]
    ordered["site_id"] = ordered["site_id"].astype(str)
    if ordered["site_id"].isna().any() or ordered["site_id"].duplicated().any():
        raise ValueError("Selected candidate site IDs must be unique and non-missing.")
    return candidates, ordered, coverage_audit, areas


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
        area_counts = {str(area): int(count) for area, count in selected.groupby(args.area_column, dropna=False).size().items()}
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
    output_path = Path(args.output)
    summary_path = Path(args.summary_json)
    frontier_path = Path(args.frontier_audit)
    matrix_path = Path(args.travel_matrix)
    if not matrix_path.is_file():
        raise FileNotFoundError(f"Travel-time matrix CSV was not found: {matrix_path}")
    candidates, ordered, coverage_audit, areas = _prepare_geometry_order(args, require_site_ids=True)
    matrix = read_travel_time_matrix(matrix_path, undirected=bool(args.undirected_travel_matrix))
    protocol = _protocol_for_profile(args.taxon_profile)
    selected, effort_audit, frontier = infer_recommended_effort_from_matrix(
        ordered,
        travel_matrix=matrix,
        hub_id=args.hub_id,
        allowed_modes=args.allowed_modes,
        survey_protocol=protocol,
        max_sites=int(args.max_sites),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(output_path, index=False)
    frontier_path.parent.mkdir(parents=True, exist_ok=True)
    frontier.to_csv(frontier_path, index=False)
    summary: dict[str, object] = {
        "input_csv": str(args.input),
        "output_csv": str(output_path),
        "frontier_audit_csv": str(frontier_path),
        "input_candidate_count": int(len(candidates)),
        "geometry_order_count": int(len(ordered)),
        "selected_count": int(len(selected)),
        "survey_area_count": int(len(areas)) if areas else 1,
        "hub_id": str(args.hub_id),
        "allowed_modes": sorted(set(str(x) for x in args.allowed_modes)),
        "taxon_profile": str(args.taxon_profile),
        "survey_protocol": protocol,
        "coverage_selection": coverage_audit.as_dict(),
        "automatic_effort": effort_audit.as_dict(),
        "routing_mode": "explicit_human_reachable_travel_matrix_only",
        "travel_matrix_csv": str(matrix_path),
        "travel_matrix_undirected": bool(args.undirected_travel_matrix),
        "target_days_user_supplied": False,
        "straight_line_fallback": False,
        "selection_rule": (
            "geometry-only maximum coverage order followed by an automatically inferred "
            "coverage-versus-effort knee on explicitly allowed movement edges"
        ),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def run_budget(args: argparse.Namespace) -> dict[str, object]:
    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary_json)
    audit_path = Path(args.prefix_audit)
    matrix_path = Path(args.travel_matrix) if args.travel_matrix else None
    candidates, ordered, coverage_audit, areas = _prepare_geometry_order(
        args, require_site_ids=matrix_path is not None
    )
    if len(areas) > 1 and matrix_path is None:
        raise ValueError(
            "Multiple survey areas require --travel-matrix with explicit inter-area costs. "
            "The straight-line proxy supports one survey area at a time."
        )
    protocol = _protocol_for_profile(args.taxon_profile)
    travel_matrix = None
    if matrix_path is not None:
        travel_matrix = read_travel_time_matrix(matrix_path, undirected=bool(args.undirected_travel_matrix))
        trip_estimator = partial(estimate_matrix_trip, travel_matrix=travel_matrix, hub_id=args.hub_id)
        routing_mode = "external_travel_time_matrix"
        routing_claim = "user-supplied pairwise travel costs; no straight-line fallback for missing matrix legs"
    else:
        trip_estimator = estimate_operational_trip
        routing_mode = "straight_line_distance_factor_proxy"
        routing_claim = "legacy what-if proxy only; road/trail/ferry topology is not validated"
    selected, budget_audit, prefix_audit = select_largest_feasible_prefix(
        ordered,
        hub_latitude=float(args.hub_latitude),
        hub_longitude=float(args.hub_longitude),
        target_days=int(args.days),
        trip_estimator=trip_estimator,
        survey_protocol=protocol,
        max_sites=int(args.max_sites),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(output_path, index=False)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    prefix_audit.to_csv(audit_path, index=False)
    summary: dict[str, object] = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "prefix_audit_csv": str(audit_path),
        "input_candidate_count": int(len(candidates)),
        "geometry_order_count": int(len(ordered)),
        "selected_count": int(len(selected)),
        "survey_area_count": int(len(areas)) if areas else 1,
        "hub_latitude": float(args.hub_latitude),
        "hub_longitude": float(args.hub_longitude),
        "hub_id": str(args.hub_id),
        "target_days": int(args.days),
        "taxon_profile": str(args.taxon_profile),
        "survey_protocol": protocol,
        "coverage_selection": coverage_audit.as_dict(),
        "operational_budget": budget_audit.as_dict(),
        "routing_mode": routing_mode,
        "travel_matrix_csv": str(matrix_path) if matrix_path is not None else None,
        "travel_matrix_row_count": int(len(travel_matrix)) if travel_matrix is not None else None,
        "travel_matrix_undirected": bool(args.undirected_travel_matrix) if matrix_path is not None else None,
        "selection_rule": "legacy explicit-day what-if truncation",
        "routing_claim": routing_claim,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command in {"recommend", "zones"}:
        summary = run_recommendation(args)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    if args.command == "auto-effort":
        summary = run_auto_effort(args)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    if args.command == "budget":
        summary = run_budget(args)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
