#!/usr/bin/env python3
"""Compare patch portfolios at equal candidate-member survey budgets."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from acsp import cluster_patch_recovery_table

RADII_KM = (1.0, 2.0, 5.0, 10.0)
DEFAULT_BUDGETS = (7, 10, 15, 20, 30, 50)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    parser.add_argument("--random-draws", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260719)
    return parser.parse_args()


def select_under_budget(order: list[str], sizes: dict[str, int], budget: int) -> list[str]:
    """Greedily retain whole patches while respecting a member-count budget."""
    selected: list[str] = []
    used = 0
    for patch_id in order:
        size = int(sizes[patch_id])
        if used + size <= budget:
            selected.append(patch_id)
            used += size
    return selected


def evaluate(
    method: str,
    budget: int,
    selected_ids: list[str],
    members: pd.DataFrame,
    clusters: pd.DataFrame,
    draw: int | None = None,
) -> dict[str, object]:
    selected = members[members["gap_patch_id"].isin(selected_ids)]
    row: dict[str, object] = {
        "method": method,
        "draw": draw,
        "member_budget": budget,
        "selected_patch_ids": "|".join(selected_ids),
        "selected_patch_count": len(selected_ids),
        "selected_member_count": int(len(selected)),
    }
    if selected.empty:
        for radius in RADII_KM:
            row[f"cluster_recall_{radius:g}km"] = 0.0
        return row
    recovery = cluster_patch_recovery_table(
        selected,
        clusters,
        cluster_col="cluster_id",
        radii_km=RADII_KM,
    )
    for radius in RADII_KM:
        row[f"cluster_recall_{radius:g}km"] = float(
            recovery[f"recovered_within_{radius:g}km"].mean()
        )
    return row


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    ranking = pd.read_csv(results / "robust_near_disconnected_patch_ranking.csv")
    members = pd.read_csv(results / "candidate_patch_occurrence_connectivity.csv")
    clusters = pd.read_csv(results / "independent_detection_clusters.csv")

    eligible = ranking["gap_patch_id"].astype(str).tolist()
    members = members[members["gap_patch_id"].isin(eligible)].copy()
    sizes = members.groupby("gap_patch_id").size().astype(int).to_dict()

    orders = {
        "robust_near_disconnected": ranking.sort_values(
            "robust_near_disconnected_rank"
        )["gap_patch_id"].astype(str).tolist(),
        "support_only": ranking.sort_values(
            ["gap_patch_score", "gap_patch_id"], ascending=[False, True]
        )["gap_patch_id"].astype(str).tolist(),
        "stability_only": ranking.sort_values(
            ["near_disconnected_frequency", "gap_patch_score", "gap_patch_id"],
            ascending=[False, False, True],
        )["gap_patch_id"].astype(str).tolist(),
    }

    max_members = int(sum(sizes.values()))
    budgets = sorted({min(int(value), max_members) for value in DEFAULT_BUDGETS if value > 0})
    deterministic: list[dict[str, object]] = []
    for method, order in orders.items():
        for budget in budgets:
            chosen = select_under_budget(order, sizes, budget)
            deterministic.append(evaluate(method, budget, chosen, members, clusters))

    rng = np.random.default_rng(args.seed)
    random_rows: list[dict[str, object]] = []
    for draw in range(args.random_draws):
        order = list(rng.permutation(eligible))
        for budget in budgets:
            chosen = select_under_budget(order, sizes, budget)
            random_rows.append(
                evaluate("random", budget, chosen, members, clusters, draw=draw + 1)
            )

    random_df = pd.DataFrame(random_rows)
    random_df.to_csv(results / "member_budget_portfolio_draws.csv", index=False)
    deterministic_df = pd.DataFrame(deterministic)

    summaries: list[dict[str, object]] = []
    for budget, group in random_df.groupby("member_budget"):
        item: dict[str, object] = {"member_budget": int(budget)}
        for radius in RADII_KM:
            column = f"cluster_recall_{radius:g}km"
            item[f"random_recall_{radius:g}km_mean"] = float(group[column].mean())
            item[f"random_recall_{radius:g}km_q025"] = float(group[column].quantile(0.025))
            item[f"random_recall_{radius:g}km_q975"] = float(group[column].quantile(0.975))
        summaries.append(item)
    comparison = deterministic_df.merge(pd.DataFrame(summaries), on="member_budget")
    for radius in RADII_KM:
        comparison[f"above_random_975_{radius:g}km"] = (
            comparison[f"cluster_recall_{radius:g}km"]
            > comparison[f"random_recall_{radius:g}km_q975"]
        )
    comparison["field_data_used_in_order"] = False
    comparison["field_data_used_only_for_evaluation"] = True
    comparison.to_csv(results / "member_budget_portfolio_comparison.csv", index=False)

    print(
        comparison[
            [
                "method",
                "member_budget",
                "selected_member_count",
                "cluster_recall_1km",
                "cluster_recall_2km",
                "cluster_recall_5km",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
