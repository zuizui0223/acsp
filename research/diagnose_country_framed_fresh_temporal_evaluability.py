#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_taxon_audit_v1.csv"
EXPECTED_FRESH_PROTOCOL_FINGERPRINT = "65ba06f174f4bdc9a49c24e54e8f7c67958757ab527fc23e4ccf427bf2d91a01"
EXPECTED_FRESH_EXECUTION_FINGERPRINT = "c8d8009ff692f71b1c076e1ee0e3c957527ea789c5c984011574ddd41f91095b"

# Deliberately exclude recall/lift columns. This diagnosis addresses observation
# availability and execution status only; it cannot be used to rescue the
# terminal scientific decision.
DIAGNOSTIC_COLUMNS = (
    "fresh_pair_id",
    "taxon_group",
    "geographic_stratum",
    "region_name",
    "speciesKey",
    "scientific_name",
    "declaration_status",
    "selected_country_code",
    "candidate_generation_status",
    "temporal_status",
    "historical_training_occurrence_rows",
    "recent_heldout_occurrence_rows",
    "candidate_patch_count",
    "fresh_protocol_fingerprint",
    "fresh_execution_fingerprint",
)
FORBIDDEN_OUTCOME_COLUMNS = {
    "robust_recall",
    "random_recall_mean",
    "robust_minus_random_recall",
}


def _counts(values: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in Counter(values.astype(str)).items()}


def _layer_summary(frame: pd.DataFrame) -> dict[str, object]:
    declared = frame["declaration_status"].eq("declared")
    generated = frame["candidate_generation_status"].eq("generated")
    evaluated = frame["temporal_status"].eq("evaluated")
    zero_recent = frame["temporal_status"].eq("zero_recent_country_records")
    declaration_failed = ~declared

    by_group: dict[str, object] = {}
    for group in ("plant", "animal"):
        g = frame["taxon_group"].eq(group)
        total = int(g.sum())
        by_group[group] = {
            "total": total,
            "declared": int((g & declared).sum()),
            "candidate_generated": int((g & generated).sum()),
            "temporally_evaluated": int((g & evaluated).sum()),
            "temporally_evaluable_fraction": float((g & evaluated).sum() / total),
            "zero_recent_country_records": int((g & zero_recent).sum()),
            "country_declaration_failed": int((g & declaration_failed).sum()),
            "joint_candidate_generated_and_temporally_evaluated": int((g & generated & evaluated).sum()),
        }

    by_stratum: dict[str, object] = {}
    for stratum in ("north", "east", "west", "south"):
        g = frame["geographic_stratum"].eq(stratum)
        total = int(g.sum())
        by_stratum[stratum] = {
            "total": total,
            "temporally_evaluated": int((g & evaluated).sum()),
            "zero_recent_country_records": int((g & zero_recent).sum()),
            "country_declaration_failed": int((g & declaration_failed).sum()),
        }

    zero_declared = frame.loc[declared & zero_recent].copy()
    hist = pd.to_numeric(zero_declared["historical_training_occurrence_rows"], errors="raise")
    largest_hist = sorted((int(x) for x in hist.tolist()), reverse=True)[:3]

    return {
        "row_count": int(len(frame)),
        "unique_species_keys": int(frame["speciesKey"].nunique()),
        "declaration_layer": {
            "status_counts": _counts(frame["declaration_status"]),
            "declared": int(declared.sum()),
            "failed": int(declaration_failed.sum()),
        },
        "candidate_layer": {
            "status_counts": _counts(frame["candidate_generation_status"]),
            "generated": int(generated.sum()),
            "generated_fraction": float(generated.mean()),
        },
        "temporal_observation_layer": {
            "status_counts": _counts(frame["temporal_status"]),
            "evaluated": int(evaluated.sum()),
            "evaluated_fraction_of_all_frozen_taxa": float(evaluated.mean()),
            "zero_recent_country_records": int(zero_recent.sum()),
            "recent_provider_failed": int(frame["temporal_status"].eq("recent_provider_failed").sum()),
        },
        "joint_layer": {
            "candidate_generated_and_temporally_evaluated": int((generated & evaluated).sum()),
            "fraction_of_all_frozen_taxa": float((generated & evaluated).mean()),
            "candidate_generated_but_zero_recent_country_records": int((generated & zero_recent).sum()),
            "candidate_generation_failed_but_temporally_evaluated": int((frame["candidate_generation_status"].eq("candidate_generation_failed") & evaluated).sum()),
        },
        "by_taxon_group": by_group,
        "by_geographic_stratum": by_stratum,
        "zero_recent_declared_taxa": {
            "count": int(len(zero_declared)),
            "country_counts": _counts(zero_declared["selected_country_code"]),
            "historical_training_rows_min": int(hist.min()),
            "historical_training_rows_median": float(hist.median()),
            "historical_training_rows_mean": float(hist.mean()),
            "historical_training_rows_max": int(hist.max()),
            "three_largest_historical_training_row_counts": largest_hist,
        },
    }


def diagnose(audit_path: Path = DEFAULT_AUDIT) -> dict[str, object]:
    if FORBIDDEN_OUTCOME_COLUMNS.intersection(DIAGNOSTIC_COLUMNS):
        raise AssertionError("scientific outcome columns entered diagnostic surface")
    frame = pd.read_csv(audit_path, usecols=list(DIAGNOSTIC_COLUMNS))
    if len(frame) != 48 or frame["speciesKey"].nunique() != 48 or frame["scientific_name"].nunique() != 48:
        raise ValueError("fresh terminal audit is not exactly 48 unique taxa")
    if set(frame["fresh_protocol_fingerprint"].astype(str)) != {EXPECTED_FRESH_PROTOCOL_FINGERPRINT}:
        raise ValueError("fresh protocol fingerprint drift")
    if set(frame["fresh_execution_fingerprint"].astype(str)) != {EXPECTED_FRESH_EXECUTION_FINGERPRINT}:
        raise ValueError("fresh execution fingerprint drift")

    summary = _layer_summary(frame)
    return {
        "diagnostic_name": "country-framed fresh temporal evaluability observation-layer diagnosis",
        "source": {
            "authoritative_run_id": 32932865041,
            "fresh_protocol_fingerprint": EXPECTED_FRESH_PROTOCOL_FINGERPRINT,
            "fresh_execution_fingerprint": EXPECTED_FRESH_EXECUTION_FINGERPRINT,
            "terminal_primary_decision": "FAIL",
            "terminal_failed_primary_gate": "temporal_evaluability_fraction_ge_0_75",
        },
        "summary": summary,
        "interpretation": {
            "candidate_generation_failure_is_not_the_temporal_gate": True,
            "generated_candidate_patches_without_recent_country_records_exist": summary["joint_layer"]["candidate_generated_but_zero_recent_country_records"] > 0,
            "zero_recent_records_are_not_confined_to_negligible_historical_counts": summary["zero_recent_declared_taxa"]["three_largest_historical_training_row_counts"],
            "working_hypothesis": "an outcome-independent historical country frame can be computationally valid yet fail to remain observable in a later heldout window",
        },
        "guards": {
            "descriptive_post_outcome_only": True,
            "primary_decision_changed": False,
            "taxa_or_countries_replaced": False,
            "scientific_constants_changed": False,
            "scientific_thresholds_tuned": False,
            "lift_columns_read": False,
            "new_eligibility_rule_created": False,
            "consumed_confirmation_rerun_allowed": False,
            "future_observability_rule_requires_separate_preregistration_and_fresh_identities": True,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = diagnose(args.audit)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
