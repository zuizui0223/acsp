#!/usr/bin/env python3
"""Build paper-ready outputs for the frozen pre-Campanula ACSP validation.

The paper is intentionally restricted to the independent retrospective
cross-taxon program. Field GPS data, post-baseline allocation rules, ODSP
exports, and production-only integrated evidence are not read by this builder.
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

from acsp import ValidatedCorePolicy, claim_status_table
from audit_random_validation_stability import run as run_stability_audit

DEFAULT_OUTPUT = ROOT / "paper/generated"


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


def build(args: argparse.Namespace) -> dict[str, object]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    stability = run_stability_audit()
    retrospective = _retrospective_table(stability)
    seed_sensitivity = _seed_sensitivity_table(stability)
    claims = claim_status_table()
    policies = {
        group: ValidatedCorePolicy.for_taxon_group(group).manifest()
        for group in ("plant", "animal")
    }

    retrospective.to_csv(output / "table_1_retrospective_validation.csv", index=False)
    seed_sensitivity.to_csv(output / "table_s1_seed_sensitivity.csv", index=False)
    claims.to_csv(output / "table_s2_claim_matrix.csv", index=False)
    (output / "retrospective_stability.json").write_text(
        json.dumps(stability, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "validated_core_policies.json").write_text(
        json.dumps(policies, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    manifest: dict[str, object] = {
        "paper_scope": "pre_campanula_retrospective_only",
        "retrospective_status": "complete",
        "retrospective_endpoint": stability["endpoint"],
        "retrospective_baseline": stability["baseline"],
        "validated_taxon_groups": ["animals", "plants"],
        "primary_recovery_radius_km": 10.0,
        "top_k": 5,
        "field_data_read": False,
        "post_baseline_algorithms_read": False,
        "method_comparator_status": (
            "implementation_ready; requires frozen candidate-level fold exports "
            "before environmental/geographic/dual-space results enter the paper"
        ),
        "outputs": [
            "table_1_retrospective_validation.csv",
            "table_s1_seed_sensitivity.csv",
            "table_s2_claim_matrix.csv",
            "retrospective_stability.json",
            "validated_core_policies.json",
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
