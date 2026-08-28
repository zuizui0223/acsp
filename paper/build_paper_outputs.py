#!/usr/bin/env python3
"""Build paper-ready outputs for the frozen pre-Campanula ACSP validation.

The original independent confirmation table remains frozen. Later predeclared
comparisons are reported separately as secondary evidence and never replace the
original confirmatory estimates. The 2026-08-08 fitted-SDM benchmark is treated
primarily as a matched-pool decision-object contrast; its held-out recovery
comparison is secondary, while the outcome-free set-difference table documents
whether the two methods make the same field decision. The later one-shot global
observability attempt is exported only as a provider-supply/evaluability boundary,
not as a held-out effect estimate.

Field GPS data, post-baseline allocation rules, ODSP exports, and production-only
integrated evidence are not read by this builder.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from acsp import StandardBaselineProtocol, ValidatedCorePolicy, claim_status_table
from research.audit_random_validation_stability import run as run_stability_audit

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
OBSERVABILITY_TERMINAL = (
    ROOT / "validation/acsp_provider_eligible_observability_first_activation_terminal_v1.json"
)
COUNTRY_FRESH_RESULT = (
    ROOT / "validation/acsp_country_framed_fresh_heterogeneity_confirmation_result_v1.json"
)
LEGACY_EXCLUDED_OUTPUTS = (
    "table_3_campanula_baseline_validation.csv",
    "table_4_campanula_area_balanced_update.csv",
    "table_5_campanula_area_balanced_top5.csv",
)


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


def _load_global_observability_boundary() -> tuple[pd.DataFrame, dict[str, object]]:
    terminal = json.loads(OBSERVABILITY_TERMINAL.read_text(encoding="utf-8"))
    if terminal.get("schema_id") != "acsp_provider_eligible_observability_first_activation_terminal_v1":
        raise ValueError("Global observability terminal schema changed.")
    run = terminal["authoritative_run"]
    observed = terminal["observed_execution"]
    original = terminal["original_terminal_status"]
    axes = terminal["two_axis_description"]
    boundary = terminal["claim_boundary"]
    if int(run.get("workflow_run_id", -1)) != 33031292325 or int(run.get("workflow_run_number", -1)) != 1:
        raise ValueError("Global observability authoritative one-shot run changed.")
    if original.get("status") != "abort_not_evaluable":
        raise ValueError("Global observability original terminal status changed.")
    if axes.get("supply_status") != "protocol_abort" or axes.get("hypothesis_status") != "unavailable":
        raise ValueError("Global observability two-axis status changed.")
    for key in (
        "heldout_2021_2025_opened",
        "candidate_generation_run",
        "robust_support_run",
        "random_baseline_run",
        "recall_or_lift_read",
        "outcome_driven_tuning",
    ):
        if observed.get(key) is not False:
            raise ValueError(f"Global observability boundary crossed: {key}")
    if boundary.get("observability_hypothesis_tested") is not False:
        raise ValueError("Global observability abort was reclassified as a hypothesis test.")
    if boundary.get("validated_japan_product_changed") is not False:
        raise ValueError("Global observability abort changed the validated Japan product.")
    row = {
        "scope": "country_framed_global_extension",
        "workflow_run_id": int(run["workflow_run_id"]),
        "workflow_run_number": int(run["workflow_run_number"]),
        "terminal_stage": int(run["terminal_stage"]),
        "candidate_rows": int(observed["candidate_rows"]),
        "historical_unique_species_queries": int(observed["historical_unique_species_queries"]),
        "historical_provider_success_count": int(observed["historical_provider_success_count"]),
        "historical_provider_error_count": int(observed["historical_provider_error_count"]),
        "provider_error_type": observed["provider_error_type"],
        "supply_status": axes["supply_status"],
        "hypothesis_status": axes["hypothesis_status"],
        "promotion_status": axes["promotion_status"],
        "heldout_2021_2025_opened": observed["heldout_2021_2025_opened"],
        "complete_authoritative_96_frame_artifact_created": observed[
            "complete_authoritative_96_frame_artifact_created"
        ],
        "observability_hypothesis_tested": boundary["observability_hypothesis_tested"],
        "validated_japan_product_changed": boundary["validated_japan_product_changed"],
        "interpretation": boundary["allowed_role"],
    }
    return pd.DataFrame([row]), terminal


def _evidence_availability_table(
    retrospective: pd.DataFrame,
    observability_terminal: dict[str, object],
) -> pd.DataFrame:
    country = json.loads(COUNTRY_FRESH_RESULT.read_text(encoding="utf-8"))
    if country.get("fresh_confirmation_gate_passed") is not False:
        raise ValueError("Country-framed fresh result no longer records a failed promotion gate.")
    if country.get("global_candidate_generation_validated") is not False:
        raise ValueError("Country-framed fresh result unexpectedly promotes a global product.")
    if country.get("validated_japan_core_changed") is not False:
        raise ValueError("Country-framed fresh result changed the validated Japan core.")

    observed = observability_terminal["observed_execution"]
    axes = observability_terminal["two_axis_description"]
    return pd.DataFrame(
        [
            {
                "scope": "validated_japan_12_region_core",
                "declared_denominator": int(retrospective["declared_taxon_region_pairs"].sum()),
                "evaluable_or_completed": int(retrospective["declared_taxon_region_pairs"].sum()),
                "heldout_or_response_status": "opened_under_frozen_spatial_holdout",
                "terminal_status": "validated_supported_at_10km",
                "promotion_status": "validated_product",
                "paper_role": "primary_confirmatory_anchor",
                "development_stop": "close_manuscript_without_global_rescue",
            },
            {
                "scope": "country_framed_fresh_extension",
                "declared_denominator": int(country["declared_taxa"]),
                "evaluable_or_completed": int(country["temporally_evaluable_taxa"]),
                "heldout_or_response_status": "opened_once_under_frozen_contract",
                "terminal_status": "failed_6_of_7_preregistered_gates",
                "promotion_status": "not_promoted",
                "paper_role": "failed_or_conditional_generalization_boundary",
                "development_stop": "no_consumed_cohort_rescue_or_same_method_promotion_attempt",
            },
            {
                "scope": "provider_eligible_observability_first_activation",
                "declared_denominator": int(observed["historical_unique_species_queries"]),
                "evaluable_or_completed": int(observed["historical_provider_success_count"]),
                "heldout_or_response_status": "2021_2025_heldout_unopened",
                "terminal_status": f"{axes['supply_status']}__hypothesis_{axes['hypothesis_status']}",
                "promotion_status": axes["promotion_status"],
                "paper_role": "provider_supply_and_evaluability_boundary_only",
                "development_stop": "no_aborted_cohort_rescue; successor_requires_new_contract",
            },
        ]
    )


def _write_recovery_figure(retrospective: pd.DataFrame, path: Path) -> None:
    """Write a dependency-free, journal-ready paired comparison as SVG."""
    width, height = 1200, 650
    left, right = 255, 1090
    x_max = 0.12
    rows = [("Animals", retrospective.iloc[0], 280), ("Plants", retrospective.iloc[1], 455)]

    def sx(value: float) -> float:
        return left + (right - left) * value / x_max

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="1200" height="650" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#222831}.title{font-size:30px;font-weight:700}.sub{font-size:17px;fill:#59636e}.axis{font-size:15px;fill:#59636e}.group{font-size:23px;font-weight:700}.value{font-size:16px;font-weight:700}.note{font-size:14px;fill:#59636e}</style>',
        '<text x="70" y="62" class="title">Held-out recovery within 10 km</text>',
        '<text x="70" y="94" class="sub">Frozen ACSP Top-5 versus same-pool random Top-5; intention-to-evaluate pair means</text>',
    ]
    for tick in (0.00, 0.03, 0.06, 0.09, 0.12):
        x = sx(tick)
        svg.extend(
            [
                f'<line x1="{x:.1f}" y1="150" x2="{x:.1f}" y2="525" stroke="#d9dee4" stroke-width="1"/>',
                f'<text x="{x:.1f}" y="552" text-anchor="middle" class="axis">{tick:.2f}</text>',
            ]
        )
    svg.append(f'<line x1="{left}" y1="525" x2="{right}" y2="525" stroke="#59636e" stroke-width="1.5"/>')
    for label, row, y in rows:
        random_value = float(row["same_pool_random_ite_recall_10km"])
        acsp_value = float(row["acsp_ite_recall_10km"])
        n_pairs = int(row["declared_taxon_region_pairs"])
        x_random, x_acsp = sx(random_value), sx(acsp_value)
        svg.extend(
            [
                f'<text x="70" y="{y + 8}" class="group">{escape(label)}</text>',
                f'<text x="70" y="{y + 34}" class="note">n = {n_pairs} taxon-region pairs</text>',
                f'<line x1="{x_random:.1f}" y1="{y}" x2="{x_acsp:.1f}" y2="{y}" stroke="#59636e" stroke-width="4"/>',
                f'<circle cx="{x_random:.1f}" cy="{y}" r="11" fill="#ffffff" stroke="#c28a18" stroke-width="4"/>',
                f'<circle cx="{x_acsp:.1f}" cy="{y}" r="12" fill="#2f6da5" stroke="#1f4d75" stroke-width="2"/>',
                f'<text x="{x_random:.1f}" y="{y - 23}" text-anchor="middle" class="value">{random_value:.3f}</text>',
                f'<text x="{x_acsp:.1f}" y="{y + 35}" text-anchor="middle" class="value">{acsp_value:.3f}</text>',
                f'<text x="{(x_random + x_acsp) / 2:.1f}" y="{y - 23}" text-anchor="middle" class="note">lift +{acsp_value-random_value:.3f}</text>',
            ]
        )
    svg.extend(
        [
            '<circle cx="760" cy="600" r="8" fill="#2f6da5" stroke="#1f4d75" stroke-width="2"/><text x="778" y="606" class="axis">Frozen ACSP</text>',
            '<circle cx="930" cy="600" r="8" fill="#ffffff" stroke="#c28a18" stroke-width="3"/><text x="948" y="606" class="axis">Same-pool random</text>',
            '</svg>',
        ]
    )
    path.write_text("\n".join(svg), encoding="utf-8")


def _write_evidence_boundary_figure(table: pd.DataFrame, path: Path) -> None:
    width, height = 1400, 650
    cards = [
        (75, "Validated Japan core", "SUPPORTED", "48 taxon-region pairs", "Frozen 10-km heldout endpoint", "#2f6da5", "#eaf2f8"),
        (500, "Country-framed extension", "NOT PROMOTED", "34 / 48 temporally evaluable", "Fresh run failed 1 of 7 gates", "#9a6b12", "#fff6df"),
        (925, "Provider first activation", "UNAVAILABLE", "3,132 / 3,161 queries succeeded", "29 HTTP 429; heldout unopened", "#6b7280", "#f1f3f5"),
    ]
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="1400" height="650" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#222831}.title{font-size:30px;font-weight:700}.sub{font-size:17px;fill:#59636e}.cardtitle{font-size:22px;font-weight:700}.status{font-size:17px;font-weight:700}.line{font-size:16px}.note{font-size:15px;fill:#59636e}</style>',
        '<text x="70" y="62" class="title">Evidence and generalization boundary</text>',
        '<text x="70" y="94" class="sub">Each extension keeps its frozen denominator and terminal semantics; later technical failure does not revise the validated core</text>',
    ]
    for index, (x, title, status, denominator, detail, color, fill) in enumerate(cards):
        svg.extend(
            [
                f'<rect x="{x}" y="175" width="350" height="280" rx="18" fill="{fill}" stroke="{color}" stroke-width="3"/>',
                f'<text x="{x+28}" y="222" class="cardtitle">{escape(title)}</text>',
                f'<text x="{x+28}" y="264" class="status" fill="{color}" style="fill:{color}">{escape(status)}</text>',
                f'<text x="{x+28}" y="318" class="line">{escape(denominator)}</text>',
                f'<text x="{x+28}" y="352" class="line">{escape(detail)}</text>',
            ]
        )
        if index == 0:
            svg.append(f'<text x="{x+28}" y="407" class="note">Primary paper anchor</text>')
        elif index == 1:
            svg.append(f'<text x="{x+28}" y="407" class="note">Generality/evaluability boundary</text>')
        else:
            svg.append(f'<text x="{x+28}" y="397" class="note">Supply protocol abort</text><text x="{x+28}" y="422" class="note">Not a null/adverse hypothesis result</text>')
    for x1, x2 in ((425, 500), (850, 925)):
        svg.extend(
            [
                f'<line x1="{x1}" y1="315" x2="{x2-14}" y2="315" stroke="#59636e" stroke-width="3"/>',
                f'<path d="M {x2-14} 306 L {x2} 315 L {x2-14} 324 Z" fill="#59636e"/>',
            ]
        )
    svg.extend(
        [
            '<line x1="75" y1="530" x2="1275" y2="530" stroke="#222831" stroke-width="2"/>',
            '<text x="75" y="568" class="status">MANUSCRIPT HARD STOP</text>',
            '<text x="300" y="568" class="line">Close at the validated Japan + failed/conditional extension + explicit abstention boundary.</text>',
            '<text x="300" y="598" class="note">No global-positive rescue; any successor observability test requires a prospectively new contract and cohort.</text>',
            '</svg>',
        ]
    )
    path.write_text("\n".join(svg), encoding="utf-8")


def build(args: argparse.Namespace) -> dict[str, object]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    stability = run_stability_audit()
    retrospective = _retrospective_table(stability)
    seed_sensitivity = _seed_sensitivity_table(stability)
    claims = claim_status_table()
    comparator, comparator_manifest = _load_secondary_comparator()
    sdm_performance, sdm_decisions, sdm_manifest = _load_sdm_decision_contrast()
    observability, observability_terminal = _load_global_observability_boundary()
    availability = _evidence_availability_table(retrospective, observability_terminal)
    policies = {
        group: ValidatedCorePolicy.for_taxon_group(group).manifest()
        for group in ("plant", "animal")
    }

    retrospective.to_csv(output / "table_1_retrospective_validation.csv", index=False)
    availability.to_csv(output / "table_2_evidence_availability.csv", index=False)
    seed_sensitivity.to_csv(output / "table_s1_seed_sensitivity.csv", index=False)
    claims.to_csv(output / "table_s2_claim_matrix.csv", index=False)
    comparator.to_csv(output / "table_s3_standard_baseline_comparison.csv", index=False)
    sdm_performance.to_csv(output / "table_s4_fitted_sdm_performance_contrast.csv", index=False)
    sdm_decisions.to_csv(output / "table_s5_sdm_decision_differences.csv", index=False)
    observability.to_csv(output / "table_s6_global_observability_boundary.csv", index=False)
    _write_recovery_figure(retrospective, output / "figure_1_primary_recovery.svg")
    _write_evidence_boundary_figure(availability, output / "figure_2_evidence_boundary.svg")
    for legacy_name in LEGACY_EXCLUDED_OUTPUTS:
        (output / legacy_name).unlink(missing_ok=True)
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
        "global_observability_status": observability_terminal["original_terminal_status"]["status"],
        "global_observability_supply_status": observability_terminal["two_axis_description"]["supply_status"],
        "global_observability_hypothesis_status": observability_terminal["two_axis_description"]["hypothesis_status"],
        "global_observability_heldout_opened": observability_terminal["observed_execution"]["heldout_2021_2025_opened"],
        "global_product_promoted": observability_terminal["claim_boundary"]["country_framed_or_global_product_promoted"],
        "validated_japan_product_changed_by_global_abort": observability_terminal["claim_boundary"]["validated_japan_product_changed"],
        "outputs": [
            "table_1_retrospective_validation.csv",
            "table_2_evidence_availability.csv",
            "figure_1_primary_recovery.svg",
            "figure_2_evidence_boundary.svg",
            "table_s1_seed_sensitivity.csv",
            "table_s2_claim_matrix.csv",
            "table_s3_standard_baseline_comparison.csv",
            "table_s4_fitted_sdm_performance_contrast.csv",
            "table_s5_sdm_decision_differences.csv",
            "table_s6_global_observability_boundary.csv",
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
