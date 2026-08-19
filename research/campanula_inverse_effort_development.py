#!/usr/bin/env python3
"""Use Campanula field detections as development labels, not validation.

The candidate pool is ordered without reading 2026 field outcomes. Only after
that outcome-free order is fixed are the 19 detection clusters read to diagnose
how much of the realized distribution each prefix would have recovered. This
script is explicitly a reverse-engineering/development instrument and must not
be used as independent confirmation.

If a real travel matrix is supplied, ACSP also infers the recommended effort
from the explicitly allowed human movement modes. No straight-line routing
fallback is used in that mode.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from acsp.auto_budget import infer_recommended_effort_from_matrix
from acsp.coverage import select_maximum_coverage_sites
from acsp.field_validation import detection_recovery_table, recovery_summary
from acsp.travel_matrix import read_travel_time_matrix

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POOL = ROOT / "field_validation/campanula_microdonta/development_data/candidate_pool.csv"
DEFAULT_DETECTIONS = ROOT / "field_validation/campanula_microdonta/development_data/detection_clusters.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--detections", default=str(DEFAULT_DETECTIONS))
    parser.add_argument("--output-dir", default="campanula_inverse_effort_development")
    parser.add_argument("--coverage-radius-km", type=float, default=1.0)
    parser.add_argument("--recovery-radius-km", type=float, default=1.0)
    parser.add_argument("--max-sites", type=int, default=400)
    parser.add_argument("--travel-matrix")
    parser.add_argument("--hub-id", default="__hub__")
    parser.add_argument(
        "--allowed-mode",
        action="append",
        dest="allowed_modes",
        help="Explicitly available movement mode; repeat for walk/road/trail/ferry as applicable.",
    )
    parser.add_argument("--undirected-travel-matrix", action="store_true")
    return parser.parse_args()


def plant_protocol() -> dict[str, object]:
    # Development default inherited from the existing reconnaissance protocol.
    # These are algorithm defaults, not user-set target days or target budget.
    return {
        "daily_field_hours": 8.0,
        "search_minutes_per_cell": 30,
        "access_buffer_minutes_per_cell": 10,
        "protocol_id": "campanula_inverse_development_v1",
        "taxon_group": "plant",
        "surface_domain": "terrestrial",
    }


def prefix_recovery_curve(
    ordered: pd.DataFrame,
    detections: pd.DataFrame,
    *,
    radius_km: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for k in range(1, len(ordered) + 1):
        prefix = ordered.iloc[:k].copy()
        recovery = detection_recovery_table(
            prefix,
            detections,
            radii_km=(float(radius_km),),
            candidate_id_col="site_id",
            area_col="survey_area_id",
            detection_area_col="island",
            require_same_area=True,
        )
        summary = recovery_summary(recovery, radii_km=(float(radius_km),)).iloc[0]
        rows.append(
            {
                "k": int(k),
                "cumulative_coverage_fraction": float(prefix["cumulative_coverage_fraction"].iloc[-1]),
                "n_recovered_clusters": int(summary["n_recovered"]),
                "detection_recall": float(summary["detection_recall"]),
            }
        )
    curve = pd.DataFrame(rows)
    curve["marginal_recovered_clusters"] = curve["n_recovered_clusters"].diff().fillna(
        curve["n_recovered_clusters"]
    ).astype(int)
    return curve


def main() -> None:
    args = parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # Outcome-free stage: construct the full geometry order before reading field labels.
    pool = pd.read_csv(args.candidate_pool, dtype={"site_id": "string"})
    if pool.empty:
        raise ValueError("candidate pool is empty")
    ordered, coverage_audit = select_maximum_coverage_sites(
        pool,
        radius_km=float(args.coverage_radius_km),
        max_sites=min(int(args.max_sites), len(pool)),
        group_col="survey_area_id" if "survey_area_id" in pool.columns else None,
    )
    if "site_id" not in ordered.columns:
        ordered["site_id"] = [str(i) for i in range(1, len(ordered) + 1)]
    ordered["site_id"] = ordered["site_id"].astype(str)
    ordered.to_csv(output / "outcome_free_geometry_order.csv", index=False)

    # Development-label stage: field clusters are read only after the order is fixed.
    detections = pd.read_csv(args.detections)
    curve = prefix_recovery_curve(
        ordered,
        detections,
        radius_km=float(args.recovery_radius_km),
    )
    curve.to_csv(output / "inverse_prefix_recovery_curve.csv", index=False)

    max_recovered = int(curve["n_recovered_clusters"].max())
    first_max = int(curve.loc[curve["n_recovered_clusters"].eq(max_recovered), "k"].min())
    complete = max_recovered == len(detections)
    summary: dict[str, object] = {
        "status": "development_only_not_independent_validation",
        "field_labels_used_for_candidate_order": False,
        "field_labels_used_after_order_for_inverse_diagnosis": True,
        "candidate_pool_rows": int(len(pool)),
        "geometry_order_rows": int(len(ordered)),
        "field_detection_clusters": int(len(detections)),
        "coverage_radius_km": float(args.coverage_radius_km),
        "recovery_radius_km": float(args.recovery_radius_km),
        "maximum_recovered_clusters": max_recovered,
        "candidate_generation_complete_for_field_clusters": bool(complete),
        "first_prefix_reaching_maximum_recovery": first_max,
        "coverage_selection": coverage_audit.as_dict(),
        "interpretation": (
            "Campanula outcomes are development labels used to reverse-engineer the survey decision rule; "
            "they do not establish generalization."
        ),
    }

    if args.travel_matrix:
        allowed_modes = args.allowed_modes or []
        if not allowed_modes:
            raise ValueError("--travel-matrix requires at least one explicit --allowed-mode")
        matrix = read_travel_time_matrix(
            args.travel_matrix,
            undirected=bool(args.undirected_travel_matrix),
        )
        selected, effort_audit, effort_frontier = infer_recommended_effort_from_matrix(
            ordered,
            travel_matrix=matrix,
            hub_id=args.hub_id,
            allowed_modes=allowed_modes,
            survey_protocol=plant_protocol(),
            max_sites=int(args.max_sites),
        )
        effort_frontier.to_csv(output / "movement_constrained_effort_frontier.csv", index=False)
        selected.to_csv(output / "auto_recommended_survey_set.csv", index=False)
        recovery = detection_recovery_table(
            selected,
            detections,
            radii_km=(float(args.recovery_radius_km),),
            candidate_id_col="site_id",
            area_col="survey_area_id",
            detection_area_col="island",
            require_same_area=True,
        )
        auto_summary = recovery_summary(recovery, radii_km=(float(args.recovery_radius_km),)).iloc[0]
        summary["auto_effort"] = effort_audit.as_dict()
        summary["auto_effort_allowed_modes"] = sorted(set(allowed_modes))
        summary["auto_effort_recovered_clusters"] = int(auto_summary["n_recovered"])
        summary["auto_effort_detection_recall"] = float(auto_summary["detection_recall"])
    else:
        summary["auto_effort"] = None
        summary["auto_effort_status"] = (
            "not computed: a real movement matrix is required; ACSP does not invent straight-line travel"
        )

    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
