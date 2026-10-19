#!/usr/bin/env python3
"""Summarize availability/evaluability failure modes separately from prediction signal.

This is a post-opened diagnostic helper. It does not alter the frozen country-framed
scientific method or rescue/exclude taxa. It accepts the already-produced aggregate
``taxon_country_results.csv`` and reports counts only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def summarize(frame: pd.DataFrame) -> dict[str, object]:
    required = {
        "candidate_generation_status",
        "candidate_generation_failure_reason",
        "temporal_status",
        "declaration_status",
        "robust_minus_random_recall",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    n = int(len(frame))
    declared = frame["declaration_status"].astype(str).eq("declared")
    generated = frame["candidate_generation_status"].astype(str).eq("generated")
    temporal = frame["temporal_status"].astype(str).eq("evaluated")
    lift = pd.to_numeric(frame["robust_minus_random_recall"], errors="coerce")
    integrated = generated & temporal & lift.notna()

    failures = frame.loc[~generated].copy()
    failure_reason = failures["candidate_generation_failure_reason"].fillna("").astype(str)
    evidence_sparse = failure_reason.str.contains(
        "fewer than five usable historical occurrence rows|fewer than five unique complete historical terrain prototypes",
        regex=True,
    )
    zero_patch = failure_reason.str.contains("returned zero candidate patches", regex=False)
    declaration_failed = failures["candidate_generation_status"].astype(str).eq("not_attempted_declaration_failed")
    other_candidate_failure = ~(evidence_sparse | zero_patch | declaration_failed)

    temporal_status = frame["temporal_status"].astype(str)
    result = {
        "declared_units": n,
        "country_declaration_success": int(declared.sum()),
        "country_declaration_failure": int((~declared).sum()),
        "candidate_generation_success": int(generated.sum()),
        "candidate_generation_failure": int((~generated).sum()),
        "candidate_failure_modes": {
            "country_declaration_failed": int(declaration_failed.sum()),
            "insufficient_historical_evidence_or_complete_prototypes": int(evidence_sparse.sum()),
            "robust_core_returned_zero_candidate_patches": int(zero_patch.sum()),
            "other": int(other_candidate_failure.sum()),
        },
        "temporally_evaluable": int(temporal.sum()),
        "temporal_not_evaluable": int((~temporal).sum()),
        "temporal_failure_modes": {
            "zero_recent_country_records": int(temporal_status.eq("zero_recent_country_records").sum()),
            "no_declared_country": int(temporal_status.eq("not_attempted_no_declared_country").sum()),
            "other": int((~temporal & ~temporal_status.isin(["zero_recent_country_records", "not_attempted_no_declared_country"])).sum()),
        },
        "integrated_evaluable": int(integrated.sum()),
        "rates": {
            "country_declaration_success": float(declared.mean()) if n else 0.0,
            "candidate_generation_success": float(generated.mean()) if n else 0.0,
            "candidate_generation_success_given_declaration": float(generated[declared].mean()) if int(declared.sum()) else 0.0,
            "temporal_evaluability": float(temporal.mean()) if n else 0.0,
            "temporal_evaluability_given_declaration": float(temporal[declared].mean()) if int(declared.sum()) else 0.0,
            "integrated_evaluability": float(integrated.mean()) if n else 0.0,
            "temporal_evaluability_given_generated": float(temporal[generated].mean()) if int(generated.sum()) else 0.0,
        },
        "scientific_method_changed": False,
        "subset_rescue_used": False,
        "interpretation": "This separates availability/evaluability loss from predictive lift; it is descriptive and cannot promote the global adapter.",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    summary = summarize(pd.read_csv(args.input_csv))
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
