#!/usr/bin/env python3
"""Consolidate a cross-taxon ecological-support gate from development results.

The input is the already-inspected 16-taxon strong support sweep.  For each
held-out development taxon, q is chosen using the other taxa only.  This is a
development jackknife, not independent confirmation.  Its purpose is to test
whether the surviving low-budget q10 policy depends on any one taxon before a
new external cohort is sampled.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def bootstrap_ci(values: np.ndarray, draws: int, seed: int) -> list[float]:
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(int(draws), len(values)))
    means = values[indices].mean(axis=1)
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def exact_sign_flip_p(values: np.ndarray) -> float:
    """Exact one-sided sign-flip p for the small taxon panels used here."""
    values = np.asarray(values, dtype=float)
    observed = float(values.mean())
    if observed <= 0:
        return 1.0
    n = len(values)
    if n > 20:
        raise ValueError("exact sign-flip enumeration is limited to <=20 values")
    patterns = np.arange(1 << n, dtype=np.uint32)[:, None]
    bits = (patterns >> np.arange(n, dtype=np.uint32)) & 1
    signs = bits.astype(np.int8) * 2 - 1
    null_means = (signs * values).mean(axis=1)
    return float(np.mean(null_means >= observed - 1e-15))


def paired_stats(values: np.ndarray, *, seed: int, bootstrap_draws: int = 10000) -> dict:
    values = np.asarray(values, dtype=float)
    return {
        "mean_difference": float(values.mean()),
        "bootstrap_95ci": bootstrap_ci(values, bootstrap_draws, seed),
        "exact_sign_flip_p": exact_sign_flip_p(values),
        "positive_taxa": int((values > 0).sum()),
        "negative_taxa": int((values < 0).sum()),
        "ties": int((values == 0).sum()),
    }


def choose_q(
    wide: pd.DataFrame,
    quantiles: list[float],
    *,
    seed: int,
    bootstrap_draws: int,
) -> tuple[float, list[dict]]:
    control = wide[1.0].to_numpy(float)
    stable: list[tuple[float, float]] = []
    diagnostics: list[dict] = []
    for i, q in enumerate(sorted(q for q in quantiles if q < 1.0)):
        diff = wide[q].to_numpy(float) - control
        stats = paired_stats(diff, seed=seed + i * 100, bootstrap_draws=bootstrap_draws)
        passes = bool(
            stats["mean_difference"] > 0
            and stats["bootstrap_95ci"][0] > 0
            and stats["exact_sign_flip_p"] < 0.05
        )
        diagnostics.append({"support_quantile": float(q), "passes": passes, **stats})
        if passes:
            stable.append((float(stats["mean_difference"]), float(q)))
    if not stable:
        return 1.0, diagnostics
    # Largest stable mean lift; exact ties prefer broader support.
    stable.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return float(stable[0][1]), diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--taxon-results", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text())
    frame = pd.read_csv(args.taxon_results)
    quantiles = [float(q) for q in protocol["support_quantiles"]]
    primary_budget = int(protocol["primary_budget"])
    budgets = [primary_budget] + [
        int(x) for x in protocol["diagnostic_budgets"] if int(x) != primary_budget
    ]
    bootstrap_draws = 10000

    required = {"sample_id", "scientific_name", "support_quantile", "budget", "recall"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

    jackknife_rows: list[dict] = []
    q_diagnostic_rows: list[dict] = []
    final_fit_rows: list[dict] = []
    budget_summaries: list[dict] = []

    for budget in budgets:
        subset = frame[frame["budget"].eq(budget)].copy()
        wide = subset.pivot(index="sample_id", columns="support_quantile", values="recall")
        names = subset[["sample_id", "scientific_name"]].drop_duplicates().set_index("sample_id")
        if not set(quantiles).issubset(set(float(x) for x in wide.columns)):
            raise RuntimeError(f"budget {budget} lacks declared q values")

        for held_id in wide.index:
            training = wide.drop(index=held_id)
            selected_q, diagnostics = choose_q(
                training,
                quantiles,
                seed=20261400 + int(budget) * 100 + int(held_id),
                bootstrap_draws=bootstrap_draws,
            )
            for row in diagnostics:
                q_diagnostic_rows.append(
                    {
                        "budget": int(budget),
                        "heldout_sample_id": int(held_id),
                        "training_taxa": int(len(training)),
                        **row,
                    }
                )
            selected_recall = float(wide.loc[held_id, selected_q])
            global_recall = float(wide.loc[held_id, 1.0])
            q10_recall = float(wide.loc[held_id, 0.10])
            jackknife_rows.append(
                {
                    "budget": int(budget),
                    "sample_id": int(held_id),
                    "scientific_name": str(names.loc[held_id, "scientific_name"]),
                    "selected_q_from_other_taxa": selected_q,
                    "selected_recall": selected_recall,
                    "global_recall": global_recall,
                    "fixed_q10_recall": q10_recall,
                    "selected_minus_global": selected_recall - global_recall,
                    "selected_minus_q10": selected_recall - q10_recall,
                }
            )

        final_q, final_diagnostics = choose_q(
            wide,
            quantiles,
            seed=20261500 + int(budget) * 100,
            bootstrap_draws=bootstrap_draws,
        )
        for row in final_diagnostics:
            final_fit_rows.append({"budget": int(budget), "final_selected_q": final_q, **row})

        jack = pd.DataFrame([r for r in jackknife_rows if r["budget"] == budget])
        selected_stats = paired_stats(
            jack["selected_minus_global"].to_numpy(float),
            seed=20261600 + int(budget),
            bootstrap_draws=bootstrap_draws,
        )
        selected_qs = sorted(jack["selected_q_from_other_taxa"].unique().tolist())
        consistency = len(selected_qs) == 1 and float(selected_qs[0]) < 1.0
        primary_gate = bool(
            budget == primary_budget
            and consistency
            and selected_stats["mean_difference"]
            >= float(protocol["primary_gate"]["minimum_mean_lift"])
            and selected_stats["bootstrap_95ci"][0]
            > float(protocol["primary_gate"]["bootstrap_lower95_gt"])
            and selected_stats["exact_sign_flip_p"]
            < float(protocol["primary_gate"]["exact_sign_flip_p_lt"])
            and float(final_q) == float(selected_qs[0])
        )
        budget_summaries.append(
            {
                "budget": int(budget),
                "jackknife_selected_qs": [float(x) for x in selected_qs],
                "jackknife_same_non1_q": consistency,
                "final_all_taxa_selected_q": float(final_q),
                "leave_one_taxon_out_vs_global": selected_stats,
                "primary_gate": primary_gate,
            }
        )

    summary = {
        "status": "development_only",
        "protocol_id": protocol["protocol_id"],
        "taxa": int(frame["sample_id"].nunique()),
        "budgets": budget_summaries,
        "primary_budget": primary_budget,
        "promotion_candidate": next(
            (row for row in budget_summaries if row["budget"] == primary_budget), None
        ),
        "confirmation_claim": False,
        "campanula_field_coordinates_used": False,
        "frozen_192_consumed": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(jackknife_rows).to_csv(args.out / "taxon_jackknife_results.csv", index=False)
    pd.DataFrame(q_diagnostic_rows).to_csv(args.out / "taxon_jackknife_q_diagnostics.csv", index=False)
    pd.DataFrame(final_fit_rows).to_csv(args.out / "all_taxa_q_fit_diagnostics.csv", index=False)
    (args.out / "cross_taxon_support_gate_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
