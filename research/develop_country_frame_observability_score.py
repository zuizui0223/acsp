#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_COHORTS = (
    {
        "name": "v1",
        "predeclared": ROOT / "validation" / "country_framed_robust_integration_development_v1" / "predeclared_taxon_country_pairs_compact.csv",
        "results": ROOT / "validation" / "country_framed_robust_integration_development_v1" / "taxon_results_compact.csv",
        "predeclared_blob_sha": "3219514af7087aa6524dc6c31c32af5f3438cdce",
        "results_blob_sha": "254ba1bcad3689a11b6f08a9c665a0addd1376a4",
    },
    {
        "name": "v1_1",
        "predeclared": ROOT / "validation" / "country_framed_robust_integration_development_v1_1" / "predeclared_taxon_country_pairs_compact.csv",
        "results": ROOT / "validation" / "country_framed_robust_integration_development_v1_1" / "taxon_results_compact.csv",
        "predeclared_blob_sha": "1f8f3c880b6ad9195c06fdc92359fa7286d4c9ce",
        "results_blob_sha": "868e2c27e61f0ef9bf28b05cab39d862938fa78e",
    },
)
FRESH_TERMINAL_AUDIT = ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_taxon_audit_v1.csv"
FRESH_TERMINAL_AUDIT_BLOB_SHA = "1584a0a8efdd9adc10c8fcb9ca8dd8bdd63cb1b1"
BOOTSTRAP_SEED = 20260827
BOOTSTRAP_REPLICATES = 10_000

PREDECLARED_COLUMNS = (
    "integration_pair_id",
    "taxon_group",
    "record_count_stratum",
    "speciesKey",
    "scientific_name",
    "selected_country_code",
    "historical_selected_country_count",
    "declaration_status",
)
RESULT_COLUMNS = (
    "integration_pair_id",
    "speciesKey",
    "scientific_name",
    "temporal_status",
)
FORBIDDEN_OUTCOME_COLUMNS = {
    "candidate_generation_status",
    "candidate_patch_count",
    "robust_recall",
    "random_recall_mean",
    "robust_minus_random_recall",
    "recent_heldout_occurrence_rows",
}


def rank_auc(scores: np.ndarray, labels: np.ndarray) -> float:
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    positive = scores[labels == 1]
    negative = scores[labels == 0]
    if positive.size == 0 or negative.size == 0:
        raise ValueError("AUC requires both temporal outcome classes")
    concordance = 0.0
    for value in positive:
        concordance += float(np.sum(value > negative))
        concordance += 0.5 * float(np.sum(value == negative))
    return concordance / float(positive.size * negative.size)


def load_development_rows() -> pd.DataFrame:
    if FORBIDDEN_OUTCOME_COLUMNS.intersection(PREDECLARED_COLUMNS):
        raise AssertionError("post-declaration outcome entered pre-heldout score surface")
    if FORBIDDEN_OUTCOME_COLUMNS.intersection(RESULT_COLUMNS):
        raise AssertionError("scientific/candidate outcome entered temporal label surface")

    frames: list[pd.DataFrame] = []
    for cohort in DEVELOPMENT_COHORTS:
        declared = pd.read_csv(cohort["predeclared"], usecols=list(PREDECLARED_COLUMNS))
        temporal = pd.read_csv(cohort["results"], usecols=list(RESULT_COLUMNS))
        merged = declared.merge(
            temporal,
            on=["integration_pair_id", "speciesKey", "scientific_name"],
            how="inner",
            validate="one_to_one",
        )
        if len(merged) != 24:
            raise ValueError(f"{cohort['name']} is not exactly 24 development taxa")
        if not merged["declaration_status"].eq("declared").all():
            raise ValueError(f"{cohort['name']} contains undeclared development rows")
        if not merged["temporal_status"].isin({"evaluated", "zero_recent_country_records"}).all():
            raise ValueError(f"{cohort['name']} has an unsupported temporal status")
        merged.insert(0, "development_cohort", cohort["name"])
        frames.append(merged)

    frame = pd.concat(frames, ignore_index=True)
    if len(frame) != 48 or frame["speciesKey"].nunique() != 48:
        raise ValueError("development surface is not exactly 48 unique pre-fresh taxa")
    return frame


def _bootstrap_auc(scores: np.ndarray, labels: np.ndarray) -> dict[str, float | int]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    values: list[float] = []
    n = len(labels)
    for _ in range(BOOTSTRAP_REPLICATES):
        idx = rng.integers(0, n, n)
        sampled_labels = labels[idx]
        if np.unique(sampled_labels).size != 2:
            continue
        values.append(rank_auc(scores[idx], sampled_labels))
    arr = np.asarray(values, dtype=float)
    q025, q50, q975 = np.quantile(arr, [0.025, 0.5, 0.975])
    return {
        "requested_replicates": BOOTSTRAP_REPLICATES,
        "valid_replicates": int(arr.size),
        "seed": BOOTSTRAP_SEED,
        "mean_auc": float(arr.mean()),
        "median_auc": float(q50),
        "ci95_lower": float(q025),
        "ci95_upper": float(q975),
        "fraction_auc_le_0_5": float(np.mean(arr <= 0.5)),
    }


def _count_summary(values: pd.Series) -> dict[str, float | int]:
    numeric = pd.to_numeric(values, errors="raise")
    return {
        "min": int(numeric.min()),
        "median": float(numeric.median()),
        "mean": float(numeric.mean()),
        "max": int(numeric.max()),
    }


def develop() -> dict[str, object]:
    frame = load_development_rows()
    historical_count = pd.to_numeric(frame["historical_selected_country_count"], errors="raise").to_numpy(dtype=float)
    score = np.log1p(historical_count)
    generic_stratum = pd.to_numeric(frame["record_count_stratum"], errors="raise").to_numpy(dtype=float)
    evaluated = frame["temporal_status"].eq("evaluated").to_numpy(dtype=int)

    score_auc = rank_auc(score, evaluated)
    comparator_auc = rank_auc(generic_stratum, evaluated)

    by_cohort: dict[str, object] = {}
    for cohort in ("v1", "v1_1"):
        mask = frame["development_cohort"].eq(cohort).to_numpy()
        by_cohort[cohort] = {
            "taxa": int(mask.sum()),
            "temporally_evaluated": int(evaluated[mask].sum()),
            "temporally_evaluable_fraction": float(evaluated[mask].mean()),
            "observability_score_auc": rank_auc(score[mask], evaluated[mask]),
            "generic_record_count_stratum_auc": rank_auc(generic_stratum[mask], evaluated[mask]),
        }

    by_group: dict[str, object] = {}
    for group in ("plant", "animal"):
        mask = frame["taxon_group"].eq(group).to_numpy()
        by_group[group] = {
            "taxa": int(mask.sum()),
            "temporally_evaluated": int(evaluated[mask].sum()),
            "temporally_evaluable_fraction": float(evaluated[mask].mean()),
            "observability_score_auc": rank_auc(score[mask], evaluated[mask]),
            "generic_record_count_stratum_auc": rank_auc(generic_stratum[mask], evaluated[mask]),
        }

    evaluated_mask = evaluated == 1
    zero_mask = evaluated == 0
    return {
        "development_name": "pre-heldout country-frame observability score",
        "status": "exploratory development on consumed pre-fresh cohorts",
        "score_definition": {
            "formula": "log1p(historical_selected_country_count)",
            "continuous": True,
            "threshold_selected": False,
            "historical_selected_country_count_known_before_heldout": True,
        },
        "source": {
            "development_cohorts": [
                {
                    "name": cohort["name"],
                    "predeclared_blob_sha": cohort["predeclared_blob_sha"],
                    "results_blob_sha": cohort["results_blob_sha"],
                }
                for cohort in DEVELOPMENT_COHORTS
            ],
            "development_taxa": 48,
            "unique_development_taxa": int(frame["speciesKey"].nunique()),
            "fresh_terminal_audit_blob_sha": FRESH_TERMINAL_AUDIT_BLOB_SHA,
            "fresh_terminal_audit_used_for_score_development": False,
        },
        "temporal_endpoint": {
            "positive": "temporal_status == evaluated",
            "negative": "temporal_status == zero_recent_country_records",
            "temporally_evaluated": int(evaluated.sum()),
            "zero_recent_country_records": int((1 - evaluated).sum()),
            "temporally_evaluable_fraction": float(evaluated.mean()),
        },
        "primary_development_result": {
            "observability_score_auc": score_auc,
            "bootstrap": _bootstrap_auc(score, evaluated),
            "evaluated_historical_country_count": _count_summary(frame.loc[evaluated_mask, "historical_selected_country_count"]),
            "zero_recent_historical_country_count": _count_summary(frame.loc[zero_mask, "historical_selected_country_count"]),
        },
        "negative_comparator": {
            "name": "generic preregistered record_count_stratum",
            "auc": comparator_auc,
            "observability_score_minus_comparator_auc": score_auc - comparator_auc,
        },
        "secondary": {
            "by_development_cohort": by_cohort,
            "by_taxon_group": by_group,
        },
        "interpretation": {
            "country_specific_historical_evidence_discriminates_later_observability": score_auc > 0.5,
            "country_specific_score_outperforms_generic_record_stratum_in_this_development_set": score_auc > comparator_auc,
            "candidate_or_lift_outcomes_needed_for_score": False,
            "working_product_role": "evidence-adequacy axis reported alongside, not used to filter or retune candidate patches",
        },
        "guards": {
            "fresh_48_used_to_fit_or_select_score": False,
            "candidate_generation_outcomes_read": False,
            "lift_outcomes_read": False,
            "taxa_or_countries_replaced": False,
            "candidate_generation_method_changed": False,
            "scientific_threshold_selected": False,
            "completed_seven_gate_decision_changed": False,
            "development_result_is_confirmation": False,
            "future_confirmation_requires_genuinely_fresh_identities": True,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = develop()
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
