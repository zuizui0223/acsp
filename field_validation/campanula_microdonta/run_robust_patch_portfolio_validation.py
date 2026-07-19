#!/usr/bin/env python3
"""Evaluate cumulative robust near-disconnected patch portfolios.

The portfolio order is fixed without using 2026 field detections. Field clusters
are used only to evaluate cumulative recovery of the top-k patches. The robust
ranking is compared with support-only, stability-only, and random patch orders
at the same patch count.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from acsp import cluster_patch_recovery_table

RADII_KM = (1.0, 2.0, 5.0, 10.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    parser.add_argument("--random-draws", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260719)
    return parser.parse_args()


def evaluate_order(
    order: list[str],
    members: pd.DataFrame,
    clusters: pd.DataFrame,
    method: str,
    draw: int | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for k in range(1, len(order) + 1):
        selected_ids = order[:k]
        selected = members[members["gap_patch_id"].astype(str).isin(selected_ids)]
        recovery = cluster_patch_recovery_table(
            selected,
            clusters,
            cluster_col="cluster_id",
            radii_km=RADII_KM,
        )
        row: dict[str, object] = {
            "method": method,
            "draw": draw,
            "top_k": k,
            "selected_patch_ids": "|".join(selected_ids),
            "selected_patch_count": len(selected_ids),
            "selected_member_count": int(len(selected)),
        }
        for radius in RADII_KM:
            column = f"recovered_within_{radius:g}km"
            row[f"cluster_recall_{radius:g}km"] = (
                float(recovery[column].mean()) if column in recovery else 0.0
            )
        rows.append(row)
    return rows


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    ranked = pd.read_csv(results / "robust_near_disconnected_patch_ranking.csv")
    members = pd.read_csv(results / "candidate_patch_occurrence_connectivity.csv")
    clusters = pd.read_csv(results / "independent_detection_clusters.csv")

    ranked = ranked.sort_values("robust_near_disconnected_rank").reset_index(drop=True)
    patch_ids = ranked["gap_patch_id"].astype(str).tolist()
    orders = {
        "robust_near_disconnected": patch_ids,
        "support_only": ranked.sort_values(
            ["gap_patch_score", "gap_patch_id"], ascending=[False, True]
        )["gap_patch_id"].astype(str).tolist(),
        "stability_only": ranked.sort_values(
            ["near_disconnected_frequency", "gap_patch_id"], ascending=[False, True]
        )["gap_patch_id"].astype(str).tolist(),
    }

    rows: list[dict[str, object]] = []
    for method, order in orders.items():
        rows.extend(evaluate_order(order, members, clusters, method))

    rng = np.random.default_rng(args.seed)
    for draw in range(args.random_draws):
        order = rng.permutation(patch_ids).tolist()
        rows.extend(evaluate_order(order, members, clusters, "random", draw=draw + 1))

    draws = pd.DataFrame(rows)
    draws.to_csv(results / "robust_patch_portfolio_draws.csv", index=False)

    deterministic = draws[draws["method"].ne("random")].copy()
    random = draws[draws["method"].eq("random")]
    random_summary = (
        random.groupby("top_k", as_index=False)
        .agg(
            random_recall_1km_mean=("cluster_recall_1km", "mean"),
            random_recall_1km_q025=("cluster_recall_1km", lambda s: s.quantile(0.025)),
            random_recall_1km_q975=("cluster_recall_1km", lambda s: s.quantile(0.975)),
            random_recall_2km_mean=("cluster_recall_2km", "mean"),
            random_recall_2km_q025=("cluster_recall_2km", lambda s: s.quantile(0.025)),
            random_recall_2km_q975=("cluster_recall_2km", lambda s: s.quantile(0.975)),
            random_recall_5km_mean=("cluster_recall_5km", "mean"),
            random_recall_5km_q025=("cluster_recall_5km", lambda s: s.quantile(0.025)),
            random_recall_5km_q975=("cluster_recall_5km", lambda s: s.quantile(0.975)),
        )
    )
    comparison = deterministic.merge(random_summary, on="top_k", how="left")
    for radius in (1, 2, 5):
        comparison[f"above_random_975_{radius}km"] = (
            comparison[f"cluster_recall_{radius}km"]
            > comparison[f"random_recall_{radius}km_q975"]
        )
    comparison["field_data_used_in_order"] = False
    comparison["field_data_used_only_for_evaluation"] = True
    comparison.to_csv(results / "robust_patch_portfolio_comparison.csv", index=False)

    print(
        comparison[
            [
                "method",
                "top_k",
                "cluster_recall_1km",
                "cluster_recall_2km",
                "cluster_recall_5km",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
