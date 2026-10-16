#!/usr/bin/env python3
"""Diagnose opened global country-frame selection using historical evidence only.

This script is deliberately post-outcome descriptive. It never reruns robust
support and never claims counterfactual recovery. For each already-consumed fresh
pair it compares the frozen selected country with the country that the new
provider-supported, historical-evidence-first automatic planner would have chosen
*using only the already-frozen historical country counts and provider coverage*.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from acsp.discovery.country_frames import CountryFrameState, plan_automatic_global_country
from geoboundaries_v6_coverage_contract import alpha2_to_alpha3_if_supported, load_iso_mapping


def _supported_alpha2_codes() -> set[str]:
    mapping = load_iso_mapping()
    return {code for code in mapping if alpha2_to_alpha3_if_supported(code) is not None}


def diagnose(frame: pd.DataFrame, *, historical_min_count: int = 5) -> tuple[pd.DataFrame, dict[str, object]]:
    required = {
        "fresh_pair_id",
        "scientific_name",
        "selected_country_code",
        "historical_selected_country_count",
        "historical_country_counts_json",
        "candidate_generation_status",
        "candidate_generation_failure_reason",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    supported = _supported_alpha2_codes()
    rows: list[dict[str, object]] = []
    for row in frame.itertuples(index=False):
        raw_counts = json.loads(str(row.historical_country_counts_json))
        counts = {str(code).upper(): int(count) for code, count in raw_counts.items()}
        plan = plan_automatic_global_country(
            counts,
            provider_supported_country_codes=supported,
            historical_min_count=int(historical_min_count),
            tie_break_seed=2026090601,
        )
        selected = str(row.selected_country_code or "").strip().upper()
        selected_count = int(row.historical_selected_country_count or 0)
        selected_supported = bool(selected and selected in supported)
        automatic = str(plan.selected_country_code or "")
        automatic_count = 0
        if automatic:
            automatic_count = int(counts.get(automatic, 0))
        rows.append(
            {
                "fresh_pair_id": int(row.fresh_pair_id),
                "scientific_name": str(row.scientific_name),
                "frozen_selected_country_code": selected,
                "frozen_selected_historical_count": selected_count,
                "frozen_selected_provider_supported": selected_supported,
                "evidence_first_country_code": automatic,
                "evidence_first_historical_count": automatic_count,
                "evidence_first_state": plan.state.value,
                "selection_changed": bool(automatic and automatic != selected),
                "historical_count_gain": int(automatic_count - selected_count),
                "candidate_generation_status": str(row.candidate_generation_status),
                "candidate_generation_failure_reason": str(row.candidate_generation_failure_reason or ""),
            }
        )

    detail = pd.DataFrame(rows).sort_values("fresh_pair_id", kind="mergesort").reset_index(drop=True)
    candidate_failed = ~detail["candidate_generation_status"].eq("generated")
    higher_alternative = detail["historical_count_gain"].gt(0) & detail["evidence_first_state"].eq(CountryFrameState.READY.value)
    summary: dict[str, object] = {
        "schema_version": "global-country-frame-selection-diagnosis-v1",
        "status": "POST_OPENED_HISTORICAL_ONLY_DIAGNOSIS",
        "consumed_pair_count": int(len(detail)),
        "frozen_selected_provider_unsupported_count": int((~detail["frozen_selected_provider_supported"]).sum()),
        "evidence_first_ready_count": int(detail["evidence_first_state"].eq(CountryFrameState.READY.value).sum()),
        "selection_changed_count": int(detail["selection_changed"].sum()),
        "candidate_generation_failure_count": int(candidate_failed.sum()),
        "candidate_failures_with_higher_supported_historical_alternative": int((candidate_failed & higher_alternative).sum()),
        "candidate_failure_pair_ids_with_higher_supported_historical_alternative": detail.loc[candidate_failed & higher_alternative, "fresh_pair_id"].astype(int).tolist(),
        "candidate_failure_examples": detail.loc[candidate_failed, [
            "fresh_pair_id",
            "scientific_name",
            "frozen_selected_country_code",
            "frozen_selected_historical_count",
            "evidence_first_country_code",
            "evidence_first_historical_count",
            "candidate_generation_failure_reason",
        ]].to_dict(orient="records"),
        "heldout_used_to_choose_country": False,
        "robust_support_rerun": False,
        "counterfactual_candidate_generation_success_claimed": False,
        "counterfactual_predictive_lift_claimed": False,
        "validated_japan_core_changed": False,
        "interpretation": "Historical-only diagnosis of country-frame availability. A richer provider-supported alternative is a hypothesis for a new fresh confirmation, not evidence that the consumed pair would have succeeded.",
    }
    return detail, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--detail-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()
    detail, summary = diagnose(pd.read_csv(args.input_csv))
    if args.detail_output:
        args.detail_output.parent.mkdir(parents=True, exist_ok=True)
        detail.to_csv(args.detail_output, index=False)
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not args.detail_output and not args.summary_output:
        print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
