"""Compare local-discovery selectors on one exact complete-NDVI candidate frame.

Scientific role: Campanula development only. This runner constructs one NDVI-enriched
candidate universe and one set of historical occurrence clusters, removes cells without
complete NDVI once, then evaluates three selectors on the same leave-one-complete-cluster-
out folds, annuli, selection fractions, recovery radii, and candidate-cell counts:

1. deterministic spatial balance only;
2. retained-anchor NDVI distance only;
3. coverage-constrained retained-anchor NDVI selection.

The hidden cluster is used only for recovery scoring. This comparison does not estimate
field yield, route efficiency, occupancy, or independent generalization and cannot
promote a selector from Campanula.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from evaluate_campanula_anchor_coverage_habitat import evaluate_anchor_coverage_habitat
from evaluate_campanula_anchor_ndvi_filter import (
    NDVI_FEATURES,
    build_and_attach_historical_clusters,
    evaluate_anchor_ndvi_filter,
)
from evaluate_campanula_anchor_spatial_balance import evaluate_anchor_spatial_balance
from evaluate_campanula_occurrence_anchor_loco import PRIMARY_CLUSTER_POLICY

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OCCURRENCES = (
    REPO_ROOT
    / "field_validation"
    / "campanula_microdonta"
    / "development_data"
    / "gbif_training_occurrences_through_2025.csv"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "field_validation"
    / "campanula_microdonta"
    / "development_data"
    / "manifest.json"
)
DEFAULT_OUT_DIR = REPO_ROOT / "validation" / "campanula_anchor_selector_comparison_v1"
KEYS = (
    "cluster_policy",
    "outer_radius_km",
    "selection_fraction",
    "recovery_radius_km",
)


def _normalize_aggregate(
    frame: pd.DataFrame,
    *,
    selector: str,
    fraction_column: str,
    count_column: str,
) -> pd.DataFrame:
    required = {
        "cluster_policy",
        "outer_radius_km",
        fraction_column,
        "recovery_radius_km",
        "anchor_conditioned_recall",
        count_column,
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{selector} aggregate missing columns: {missing}")
    out = frame[
        [
            "cluster_policy",
            "outer_radius_km",
            fraction_column,
            "recovery_radius_km",
            "anchor_conditioned_recall",
            count_column,
        ]
    ].copy()
    out = out.rename(
        columns={
            fraction_column: "selection_fraction",
            "anchor_conditioned_recall": f"{selector}_recall",
            count_column: f"{selector}_median_selected_cells",
        }
    )
    for column in ("outer_radius_km", "selection_fraction", "recovery_radius_km"):
        out[column] = pd.to_numeric(out[column], errors="raise")
    out[f"{selector}_recall"] = pd.to_numeric(
        out[f"{selector}_recall"], errors="coerce"
    )
    out[f"{selector}_median_selected_cells"] = pd.to_numeric(
        out[f"{selector}_median_selected_cells"], errors="raise"
    )
    return out


def compare_selector_aggregates(
    spatial: pd.DataFrame,
    ndvi: pd.DataFrame,
    coverage_habitat: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return exact-key comparison and deterministic win/tie/loss summaries."""
    spatial_n = _normalize_aggregate(
        spatial,
        selector="spatial",
        fraction_column="selection_fraction_of_annulus",
        count_column="median_selected_spatially_balanced_cells",
    )
    ndvi_n = _normalize_aggregate(
        ndvi,
        selector="ndvi",
        fraction_column="selection_fraction_of_complete_annulus",
        count_column="median_selected_ndvi_cells",
    )
    coverage_n = _normalize_aggregate(
        coverage_habitat,
        selector="coverage_habitat",
        fraction_column="selection_fraction_of_complete_annulus",
        count_column="median_selected_coverage_habitat_cells",
    )
    merged = spatial_n.merge(ndvi_n, on=list(KEYS), how="inner", validate="one_to_one")
    merged = merged.merge(coverage_n, on=list(KEYS), how="inner", validate="one_to_one")
    if len(merged) != len(spatial_n) or len(merged) != len(ndvi_n) or len(merged) != len(coverage_n):
        raise ValueError("selector aggregates do not share an identical configuration grid")

    count_columns = [
        "spatial_median_selected_cells",
        "ndvi_median_selected_cells",
        "coverage_habitat_median_selected_cells",
    ]
    counts = merged[count_columns].to_numpy(float)
    matched_counts = np.isclose(counts[:, 0], counts[:, 1], atol=0.0, rtol=0.0) & np.isclose(
        counts[:, 0], counts[:, 2], atol=0.0, rtol=0.0
    )
    merged["exact_median_cell_count_match"] = matched_counts

    tolerance = 1e-12
    for baseline in ("spatial", "ndvi"):
        delta = merged["coverage_habitat_recall"] - merged[f"{baseline}_recall"]
        merged[f"coverage_minus_{baseline}_recall"] = delta
        merged[f"coverage_vs_{baseline}"] = np.where(
            delta > tolerance,
            "win",
            np.where(delta < -tolerance, "loss", "tie"),
        )

    comparable = merged.loc[
        merged["exact_median_cell_count_match"].astype(bool)
        & merged[["spatial_recall", "ndvi_recall", "coverage_habitat_recall"]]
        .notna()
        .all(axis=1)
    ].copy()
    primary = comparable.loc[comparable["cluster_policy"].eq(PRIMARY_CLUSTER_POLICY)].copy()

    def tally(frame: pd.DataFrame, column: str) -> dict[str, int]:
        values = frame[column].value_counts()
        return {name: int(values.get(name, 0)) for name in ("win", "tie", "loss")}

    summary: dict[str, object] = {
        "schema_version": "campanula-anchor-selector-comparison-v1",
        "scientific_role": "development_internal_exact_matched_selector_comparison_only",
        "independent_validation": False,
        "reads_2026_field_outcomes": False,
        "hidden_cluster_used_for_selector_construction": False,
        "configuration_rows": int(len(merged)),
        "exact_median_cell_count_match_rows": int(matched_counts.sum()),
        "comparable_rows": int(len(comparable)),
        "primary_policy": PRIMARY_CLUSTER_POLICY,
        "primary_policy_comparable_rows": int(len(primary)),
        "coverage_habitat_vs_spatial_all": tally(comparable, "coverage_vs_spatial"),
        "coverage_habitat_vs_ndvi_all": tally(comparable, "coverage_vs_ndvi"),
        "coverage_habitat_vs_spatial_primary_policy": tally(primary, "coverage_vs_spatial"),
        "coverage_habitat_vs_ndvi_primary_policy": tally(primary, "coverage_vs_ndvi"),
        "decision_boundary": (
            "A coverage-habitat selector is worth retaining for further development only "
            "if gains over pure spatial balance are not confined to one clustering policy "
            "or one recovery radius. Campanula cannot promote the selector."
        ),
        "effort_boundary": (
            "Exact matched candidate-cell count on one complete-NDVI annular frame; "
            "not matched route length, searched area, time, cost, or field effort."
        ),
    }
    return merged, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--cluster-radius-m", type=float, default=500.0)
    parser.add_argument("--known-point-exclusion-km", type=float, default=0.5)
    parser.add_argument("--outer-radii-km", type=float, nargs="+", default=[2.0, 2.5])
    parser.add_argument(
        "--selection-fractions", type=float, nargs="+", default=[0.025, 0.05, 0.10, 0.25, 0.50, 1.0]
    )
    parser.add_argument(
        "--recovery-radii-km", type=float, nargs="+", default=[0.1, 0.25, 0.5, 1.0]
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    island_bounds = manifest.get("island_bounds")
    if not isinstance(island_bounds, dict):
        raise ValueError("manifest must contain an island_bounds object")

    raw_universe = pd.read_csv(args.universe)
    enriched_universe, enriched_clusters = build_and_attach_historical_clusters(
        raw_universe,
        pd.read_csv(args.occurrences),
        island_bounds,
        args.ndvi,
        cluster_radius_m=args.cluster_radius_m,
    )
    complete_universe = enriched_universe.loc[
        enriched_universe[list(NDVI_FEATURES)].notna().all(axis=1)
    ].copy().reset_index(drop=True)

    common = dict(
        exclusion_radius_km=args.known_point_exclusion_km,
        outer_radii_km=args.outer_radii_km,
        selection_fractions=args.selection_fractions,
        recovery_radii_km=args.recovery_radii_km,
    )
    spatial_folds, spatial_aggregate, spatial_summary = evaluate_anchor_spatial_balance(
        complete_universe, enriched_clusters, **common
    )
    ndvi_folds, ndvi_aggregate, ndvi_summary = evaluate_anchor_ndvi_filter(
        complete_universe, enriched_clusters, **common
    )
    coverage_folds, coverage_aggregate, coverage_summary = evaluate_anchor_coverage_habitat(
        complete_universe, enriched_clusters, **common
    )
    comparison, comparison_summary = compare_selector_aggregates(
        spatial_aggregate, ndvi_aggregate, coverage_aggregate
    )
    comparison_summary["complete_ndvi_candidate_universe_rows"] = int(len(complete_universe))
    comparison_summary["component_roles"] = {
        "spatial": spatial_summary["scientific_role"],
        "ndvi": ndvi_summary["scientific_role"],
        "coverage_habitat": coverage_summary["scientific_role"],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    spatial_folds.to_csv(args.out_dir / "spatial_folds.csv", index=False)
    spatial_aggregate.to_csv(args.out_dir / "spatial_aggregate.csv", index=False)
    ndvi_folds.to_csv(args.out_dir / "ndvi_folds.csv", index=False)
    ndvi_aggregate.to_csv(args.out_dir / "ndvi_aggregate.csv", index=False)
    coverage_folds.to_csv(args.out_dir / "coverage_habitat_folds.csv", index=False)
    coverage_aggregate.to_csv(args.out_dir / "coverage_habitat_aggregate.csv", index=False)
    comparison.to_csv(args.out_dir / "matched_selector_comparison.csv", index=False)
    (args.out_dir / "summary.json").write_text(
        json.dumps(comparison_summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(comparison_summary, indent=2, ensure_ascii=False))
    print(comparison.to_csv(index=False))


if __name__ == "__main__":
    main()
