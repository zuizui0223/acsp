#!/usr/bin/env python3
"""Build paper-ready outputs for the frozen pre-Campanula ACSP validation.

The original independent confirmation table remains frozen. Later predeclared
comparisons are reported separately as secondary evidence and never replace the
original confirmatory estimates. The 2026-08-08 fitted-SDM benchmark is treated
primarily as a matched-pool decision-object contrast; its held-out recovery
comparison is secondary, while the outcome-free set-difference table documents
whether the two methods make the same field decision.

Field GPS data, post-baseline allocation rules, ODSP exports, and production-only
integrated evidence are not read by this builder.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from acsp import StandardBaselineProtocol, ValidatedCorePolicy, claim_status_table
from audit_random_validation_stability import run as run_stability_audit

DEFAULT_OUTPUT = ROOT / "paper/generated"
COMPARATOR_DIR = ROOT / "validation/standard_baseline_results_20260724"
COMPARATOR_SUMMARY = COMPARATOR_DIR / "comparator_summary.csv"
COMPARATOR_MANIFEST = COMPARATOR_DIR / "run_manifest.json"
COMPARATOR_PROTOCOL = ROOT / "validation/standard_baseline_protocol.json"

SDM_DECISION_DIR = ROOT / "validation/sdm_decision_results_20260808"
SDM_METHOD_SUMMARY = SDM_DECISION_DIR / "method_summary.csv"
SDM_INFERENCE = SDM_DECISION_DIR / "pair_level_inference.csv"
SDM_PAIR_AUDIT = SDM_DECISION_DIR / "pair_artifact_audit.csv"
SDM_DECISION_SUMMARY = SDM_DECISION_DIR / "decision_difference_summary.csv"
SDM_DECISION_MANIFEST = SDM_DECISION_DIR / "run_manifest.json"

EXPECTED_SDM_PROTOCOL = "cea7ba04d53d6af7be5d642746539e46ff924435fd683aa43479ea5a38022652"
EXPECTED_SDM_CONTRACT = "1627009619716726e4af2e1ac7dc5ce47fa50dcfefa3bb042364c84b00884bd1"
EXPECTED_SDM_RECOVERY_ARTIFACT_SHA256 = "560b4e46b4c9b961bba21558ba897632ea1edf8f178625c086357a8fc478e461"
EXPECTED_SDM_DECISION_ARTIFACT_SHA256 = "98a927bc5a48f7c59300c955fa0ba464a560498bb3048c84b4f60470f5907eb6"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _retrospective_table(stability: dict[str, object]) -> pd.DataFrame:
    rows = []
    definitions = (
        ("animals", "animals_independent_mixed_cohort", "Independent mixed confirmation"),
        ("plants", "plants_pooled_independent_cohorts", "Pooled independent plant confirmations"),
    )
    for group, key, cohort in definitions:
        values = stability[key]
        rows.append(
            {
                "taxon_group": group,
                "cohort": cohort,
                "declared_taxon_region_pairs": values["declared_pairs"],
                "acsp_ite_recall_10km": values["mean_ite_default_recall"],
                "same_pool_random_ite_recall_10km": values["mean_ite_random_recall"],
                "lift_over_random": values["mean_lift"],
                "leave_one_pair_out_min_lift": values["leave_one_pair_out_min_lift"],
                "minimum_bootstrap_probability_lift_positive": values[
                    "minimum_bootstrap_probability_positive_across_seeds"
                ],
                "minimum_half_cohort_probability_lift_positive": values[
                    "minimum_half_sample_probability_positive_across_seeds"
                ],
                "maximum_sign_flip_p_across_seeds": values[
                    "maximum_sign_flip_p_across_seeds"
                ],
                "stability_verdict": values["stability_verdict"],
            }
        )
    return pd.DataFrame(rows)


def _seed_sensitivity_table(stability: dict[str, object]) -> pd.DataFrame:
    frames = []
    for group, key in (
        ("animals", "animals_independent_mixed_cohort"),
        ("plants", "plants_pooled_independent_cohorts"),
    ):
        frame = pd.DataFrame(stability[key]["seed_sensitivity"])
        frame.insert(0, "taxon_group", group)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _load_secondary_comparator() -> tuple[pd.DataFrame, dict[str, object]]:
    if not COMPARATOR_SUMMARY.exists() or not COMPARATOR_MANIFEST.exists():
        raise FileNotFoundError("Reviewed secondary comparator snapshot is incomplete.")
    summary = pd.read_csv(COMPARATOR_SUMMARY)
    manifest = json.loads(COMPARATOR_MANIFEST.read_text(encoding="utf-8"))
    protocol = StandardBaselineProtocol.from_json(COMPARATOR_PROTOCOL).manifest()
    if manifest.get("protocol_fingerprint") != protocol.get("fingerprint"):
        raise ValueError("Secondary comparator protocol fingerprint does not match the frozen protocol.")
    if not manifest.get("runs") or any(int(run.get("checksum_mismatches", -1)) != 0 for run in manifest["runs"]):
        raise ValueError("Secondary comparator artifacts have not passed checksum review.")
    required = {
        "taxon_group",
        "decision_method",
        "eligible_pairs",
        "mean_ite_recall",
        "vs_random_mean_difference",
        "vs_random_ci_low",
        "vs_random_ci_high",
        "vs_random_sign_flip_p",
        "vs_acsp_mean_difference",
        "vs_acsp_ci_low",
        "vs_acsp_ci_high",
        "vs_acsp_sign_flip_p",
    }
    missing = required - set(summary.columns)
    if missing:
        raise ValueError(f"Secondary comparator summary is missing: {', '.join(sorted(missing))}")
    return summary, manifest


def _load_sdm_decision_contrast() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    required_paths = (
        SDM_METHOD_SUMMARY,
        SDM_INFERENCE,
        SDM_PAIR_AUDIT,
        SDM_DECISION_SUMMARY,
        SDM_DECISION_MANIFEST,
    )
    if any(not path.exists() for path in required_paths):
        raise FileNotFoundError("Reviewed fitted-SDM decision-contrast snapshot is incomplete.")

    method_summary = pd.read_csv(SDM_METHOD_SUMMARY)
    inference = pd.read_csv(SDM_INFERENCE)
    audit = pd.read_csv(SDM_PAIR_AUDIT)
    decision_summary = pd.read_csv(SDM_DECISION_SUMMARY)
    manifest = json.loads(SDM_DECISION_MANIFEST.read_text(encoding="utf-8"))

    if manifest.get("protocol_fingerprint") != EXPECTED_SDM_PROTOCOL:
        raise ValueError("Fitted-SDM protocol fingerprint differs from the reviewed snapshot.")
    if manifest.get("execution_contract_fingerprint") != EXPECTED_SDM_CONTRACT:
        raise ValueError("Fitted-SDM execution-contract fingerprint differs from the reviewed snapshot.")
    if manifest.get("recovered_aggregate_artifact_sha256") != EXPECTED_SDM_RECOVERY_ARTIFACT_SHA256:
        raise ValueError("Recovered fitted-SDM aggregate digest differs from the reviewed artifact.")
    if manifest.get("decision_difference_artifact_sha256") != EXPECTED_SDM_DECISION_ARTIFACT_SHA256:
        raise ValueError("Decision-difference artifact digest differs from the reviewed artifact.")
    if int(manifest.get("verified_pair_artifacts", -1)) != 24:
        raise ValueError("Fitted-SDM contrast does not contain 24 verified pair artifacts.")
    if int(manifest.get("written_fold_method_rows", -1)) != 720:
        raise ValueError("Fitted-SDM contrast does not contain all 720 fold-method rows.")
    if int(audit["artifact_status"].eq("verified").sum()) != 24:
        raise ValueError("Fitted-SDM pair audit contains an unverified artifact.")

    comparison = inference[
        inference["numerator_method"].eq("frozen_acsp")
        & inference["denominator_method"].eq("fitted_sdm_top_k")
    ].copy()
    if len(comparison) != 6:
        raise ValueError("Expected six ACSP-versus-fitted-SDM contrast rows.")

    mean_lookup = method_summary.pivot(
        index="taxon_group", columns="decision_method", values="mean_pair_recall"
    )
    rows = []
    for row in comparison.itertuples(index=False):
        group = str(row.taxon_group)
        item = {
            "estimand": str(row.estimand),
            "taxon_group": group,
            "paired_taxon_region_pairs": int(row.paired_taxon_region_pairs),
            "acsp_minus_sdm_mean_difference": float(row.mean_pair_difference),
            "bootstrap_ci_low": float(row.bootstrap_ci_low),
            "bootstrap_ci_high": float(row.bootstrap_ci_high),
            "sign_flip_p": float(row.sign_flip_p),
        }
        if str(row.estimand) == "all_declared_intention_to_evaluate" and group in mean_lookup.index:
            item["acsp_mean_pair_recall"] = float(mean_lookup.loc[group, "frozen_acsp"])
            item["sdm_mean_pair_recall"] = float(mean_lookup.loc[group, "fitted_sdm_top_k"])
        else:
            item["acsp_mean_pair_recall"] = float("nan")
            item["sdm_mean_pair_recall"] = float("nan")
        rows.append(item)

    performance = pd.DataFrame(rows)
    required_decision = {
        "taxon_group",
        "evaluable_folds",
        "evaluable_pairs",
        "mean_shared_count",
        "mean_jaccard_overlap",
        "exact_set_match_fraction",
        "mean_local_sdm_rank_spearman",
        "mean_acsp_local_evidence",
        "mean_sdm_local_evidence",
        "mean_acsp_sdm_suitability",
        "mean_sdm_sdm_suitability",
        "mean_acsp_pairwise_distance_km",
        "mean_sdm_pairwise_distance_km",
    }
    missing = required_decision - set(decision_summary.columns)
    if missing:
        raise ValueError(f"Decision-difference summary is missing: {', '.join(sorted(missing))}")
    return performance, decision_summary, manifest


def build(args: argparse.Namespace) -> dict[str, object]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    stability = run_stability_audit()
    retrospective = _retrospective_table(stability)
    seed_sensitivity = _seed_sensitivity_table(stability)
    claims = claim_status_table()
    comparator, comparator_manifest = _load_secondary_comparator()
    sdm_performance, sdm_decisions, sdm_manifest = _load_sdm_decision_contrast()
    policies = {
        group: ValidatedCorePolicy.for_taxon_group(group).manifest()
        for group in ("plant", "animal")
    }

    retrospective.to_csv(output / "table_1_retrospective_validation.csv", index=False)
    seed_sensitivity.to_csv(output / "table_s1_seed_sensitivity.csv", index=False)
    claims.to_csv(output / "table_s2_claim_matrix.csv", index=False)
    comparator.to_csv(output / "table_s3_standard_baseline_comparison.csv", index=False)
    sdm_performance.to_csv(output / "table_s4_fitted_sdm_performance_contrast.csv", index=False)
    sdm_decisions.to_csv(output / "table_s5_sdm_decision_differences.csv", index=False)
    (output / "retrospective_stability.json").write_text(
        json.dumps(stability, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "validated_core_policies.json").write_text(
        json.dumps(policies, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "standard_baseline_results_manifest.json").write_text(
        json.dumps(comparator_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "sdm_decision_results_manifest.json").write_text(
        json.dumps(sdm_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    manifest: dict[str, object] = {
        "paper_scope": "pre_campanula_cross_taxon_retrospective",
        "retrospective_status": "complete",
        "retrospective_endpoint": stability["endpoint"],
        "retrospective_baseline": stability["baseline"],
        "validated_taxon_groups": ["animals", "plants"],
        "primary_recovery_radius_km": 10.0,
        "top_k": 5,
        "field_data_read": False,
        "post_baseline_algorithms_read": False,
        "method_comparator_status": "complete_secondary_predeclared_reconstruction",
        "method_comparator_protocol_fingerprint": comparator_manifest["protocol_fingerprint"],
        "method_comparator_boundary": comparator_manifest["provenance_boundary"],
        "sdm_decision_contrast_status": "complete_secondary_matched_pool",
        "sdm_decision_contrast_protocol_fingerprint": sdm_manifest["protocol_fingerprint"],
        "sdm_decision_contrast_interpretation": "decision differentiation first; held-out superiority is not a manuscript claim",
        "outputs": [
            "table_1_retrospective_validation.csv",
            "table_s1_seed_sensitivity.csv",
            "table_s2_claim_matrix.csv",
            "table_s3_standard_baseline_comparison.csv",
            "table_s4_fitted_sdm_performance_contrast.csv",
            "table_s5_sdm_decision_differences.csv",
            "retrospective_stability.json",
            "validated_core_policies.json",
            "standard_baseline_results_manifest.json",
            "sdm_decision_results_manifest.json",
        ],
    }
    (output / "paper_output_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def main() -> None:
    args = parse_args()
    print(json.dumps(build(args), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
