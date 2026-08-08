#!/usr/bin/env python3
"""Build paper-ready outputs for the frozen pre-Campanula ACSP validation.

The paper is restricted to cross-taxon retrospective evidence. The original
independent confirmation table remains frozen. A later predeclared standard-
baseline reconstruction is reported separately as secondary comparator evidence;
it does not replace the original confirmatory candidate pools or estimates.
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


def build(args: argparse.Namespace) -> dict[str, object]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    stability = run_stability_audit()
    retrospective = _retrospective_table(stability)
    seed_sensitivity = _seed_sensitivity_table(stability)
    claims = claim_status_table()
    comparator, comparator_manifest = _load_secondary_comparator()
    policies = {
        group: ValidatedCorePolicy.for_taxon_group(group).manifest()
        for group in ("plant", "animal")
    }

    retrospective.to_csv(output / "table_1_retrospective_validation.csv", index=False)
    seed_sensitivity.to_csv(output / "table_s1_seed_sensitivity.csv", index=False)
    claims.to_csv(output / "table_s2_claim_matrix.csv", index=False)
    comparator.to_csv(output / "table_s3_standard_baseline_comparison.csv", index=False)
    (output / "retrospective_stability.json").write_text(
        json.dumps(stability, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "validated_core_policies.json").write_text(
        json.dumps(policies, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "standard_baseline_results_manifest.json").write_text(
        json.dumps(comparator_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
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
        "outputs": [
            "table_1_retrospective_validation.csv",
            "table_s1_seed_sensitivity.csv",
            "table_s2_claim_matrix.csv",
            "table_s3_standard_baseline_comparison.csv",
            "retrospective_stability.json",
            "validated_core_policies.json",
            "standard_baseline_results_manifest.json",
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
