#!/usr/bin/env python3
"""Compare two SHA-verified original ACSP v2 runs across a seed-offset repair.

The runs reuse a frozen taxon-region cohort but refetch GBIF independently;
their exact original occurrence rows are NOT archived. Only source-confirmed
historical result ZIPs are accepted. This is not an independent confirmation,
a controlled fixed-input RNG sensitivity experiment, or a new field result.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import io
import json
import math
from pathlib import Path

try:
    from research.replay_original_robust_patch_v2_artifacts import (
        _members, read_receipt, check_primary_table,
    )
except ModuleNotFoundError:
    from replay_original_robust_patch_v2_artifacts import (
        _members, read_receipt, check_primary_table,
    )

SCHEMA = "acsp-v2-20260820-original-comparison-baseline-offset-v1"
PRIOR_RUN = 32336724090
PRIOR_ARTIFACT = 9395679418
PRIOR_HEAD_SHA = "df6277f4d9e8b3e36a5dad1730affb8db69da48a"
FINAL_RUN = 32337884576
FINAL_ARTIFACT = 9396133154
FINAL_HEAD_SHA = "39c9e6853f8d8aeffe42acd1258fe4f8f936f009"
PRIOR_ARCHIVE = {
    "archive_sha256": "7b7bc3dd069c948bb7c63254b3e50e2822d3a8bbe51bd3a4f245dd04aad297f3",
    "member_sha256": {
        "confirmation-folds/export_manifest.json": "b9e89cb8de1969ea0531c8106d3f82750aa4791bfbf7658429855b1dd1f637fd",
        "confirmation-folds/pair_export_status.csv": "55f66ba821cba0eafdcc149f04e082e0c66ecf4a51d9456c94319e158a81b7bf",
        "confirmation-results/confirmation_fold_results.csv": "0619ad1eebefb8cb499d383c6cde5521f464a5098dd83c1ff98ea47cce7437e1",
        "confirmation-results/confirmation_pair_results.csv": "55af3b622f470412888723f7481a2784d2557232912b010e42a2d3786910576b",
        "confirmation-results/confirmation_radius_summary.csv": "81ca44f5b077552676f1d51e1fb7d9f481a36e8d9a3dede4c63bf309173dd421",
        "confirmation-results/confirmation_summary.json": "666886b118741cc0effd096da48538eef54c3f0eaed1b4e358b167865f763efc",
    },
}
BASELINE_DIFF_FIELDS = {"random_mean_recall", "lift_over_random"}
PAIR_DIFF_FIELDS = {"mean_random_recall", "mean_lift"}
PRIMARY_RADIUS = 10.0


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _csv(content: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


def _aligned(before: list[dict[str, str]], after: list[dict[str, str]],
             keys: tuple[str, ...], allowed_changes: set[str]) -> list[
                 tuple[dict[str, str], dict[str, str]]
             ]:
    _require(len(before) == len(after), "original table row count changed")
    _require(bool(before) and bool(after), "empty original table")
    columns = set(before[0])
    _require(columns == set(after[0]), "original schema changed")
    _require(set(keys) <= columns and allowed_changes <= columns,
             "comparison key or baseline column missing")
    for row in [*before, *after]:
        _require(set(row) == columns, "ragged original source table")
    b = {tuple(row[k] for k in keys): row for row in before}
    a = {tuple(row[k] for k in keys): row for row in after}
    _require(len(b) == len(before) and len(a) == len(after)
             and b.keys() == a.keys(), "unmatched original row key")
    pairs = [(b[k], a[k]) for k in sorted(b)]
    for before_row, after_row in pairs:
        for col in columns - set(keys) - allowed_changes:
            _require(before_row[col] == after_row[col],
                     f"frozen non-random result changed: {col}")
    return pairs


def _changed(before: str, after: str) -> bool:
    b, a = float(before), float(after)
    _require(math.isfinite(b) and math.isfinite(a),
             "original comparison metric nonfinite")
    return not math.isclose(b, a, rel_tol=0.0, abs_tol=1e-14)


def _mean(values: list[float]) -> float:
    _require(bool(values) and all(math.isfinite(v) for v in values),
             "original comparison means missing/nonfinite")
    return math.fsum(values) / len(values)


def compare(prior_zip: Path, final_zip: Path) -> dict[str, object]:
    receipt = read_receipt()
    check_primary_table(receipt)
    _require(receipt["source_runs"]["confirmation"] == FINAL_RUN
             and receipt["artifacts"]["confirmation"]["id"] == FINAL_ARTIFACT,
             "original official run changed")
    before = _members(prior_zip, PRIOR_ARCHIVE)
    after = _members(final_zip, receipt["artifacts"]["confirmation"])
    _require(set(before) == set(after), "original result archive member set changed")
    fixed_exact_files = [
        "confirmation-folds/export_manifest.json",
        "confirmation-folds/pair_export_status.csv",
    ]
    for name in fixed_exact_files:
        _require(before[name] == after[name],
                 f"original export summary bytes changed: {name}")

    folds = _aligned(
        _csv(before["confirmation-results/confirmation_fold_results.csv"]),
        _csv(after["confirmation-results/confirmation_fold_results.csv"]),
        ("pair_id", "repeat", "radius_km"), BASELINE_DIFF_FIELDS,
    )
    pair_rows = _aligned(
        _csv(before["confirmation-results/confirmation_pair_results.csv"]),
        _csv(after["confirmation-results/confirmation_pair_results.csv"]),
        ("pair_id",), PAIR_DIFF_FIELDS,
    )
    _require(len(folds) == 1920 and len(pair_rows) == 96,
             "original 96-pair/480-fold four-radius denominator changed")
    _require({float(b["radius_km"]) for b, _ in folds} == {1.0, 2.0, 5.0, 10.0},
             "distance set changed")
    _require({(int(b["pair_id"]), int(b["repeat"]), float(b["radius_km"]))
             for b, _ in folds} ==
             {(p, repeat, r) for p in range(1, 97)
              for repeat in range(1, 6) for r in (1., 2., 5., 10.)},
             "original pair/fold/radius cells altered")

    by_radius: dict[str, dict[str, float | int]] = {}
    for radius in (1.0, 2.0, 5.0, PRIMARY_RADIUS):
        subset = [(b, a) for b, a in folds if float(b["radius_km"]) == radius]
        _require(len(subset) == 480, "incomplete regional fold metric")
        changed_random = sum(_changed(b["random_mean_recall"], a["random_mean_recall"])
                             for b, a in subset)
        changed_lift = sum(_changed(b["lift_over_random"], a["lift_over_random"])
                           for b, a in subset)
        _require(changed_random == changed_lift, "random-baseline-only delta violation")
        deltas = [float(a["lift_over_random"]) - float(b["lift_over_random"])
                  for b, a in subset]
        _require(all(math.isclose(delta,
                   -(float(a["random_mean_recall"])-float(b["random_mean_recall"])),
                   rel_tol=0.0, abs_tol=1e-13)
                   for delta, (b, a) in zip(deltas, subset)),
                 "observed recall shifted between old and corrected outputs")
        by_radius[str(int(radius))] = {
            "declared_folds": 480,
            "changed_random_baseline_folds": changed_random,
            "changed_lift_folds": changed_lift,
            "prior_mean_lift": _mean([float(b["lift_over_random"]) for b, _ in subset]),
            "final_mean_lift": _mean([float(a["lift_over_random"]) for _, a in subset]),
            "mean_lift_difference_final_minus_prior": _mean(deltas),
        }

    changed_pairs = sum(_changed(b["mean_lift"], a["mean_lift"])
                        for b, a in pair_rows)
    _require(changed_pairs == sum(_changed(b["mean_random_recall"], a["mean_random_recall"])
                                  for b, a in pair_rows),
             "pair mean changes are not confined to random baseline")

    p0 = json.loads(before["confirmation-results/confirmation_summary.json"])
    p1 = json.loads(after["confirmation-results/confirmation_summary.json"])
    _require(p0["execution_fingerprint"] == p1["execution_fingerprint"] ==
             "47afe0f78fdc253f395cb0eb6410ae846ab15e12da1b922c72edad357c722a45",
             "execution fingerprint changed")
    _require(p0["protocol_fingerprint"] == p1["protocol_fingerprint"] ==
             "68f94dbb5ad9cd6ec433653df83df323a7fc489b1ef8ded2422bd8520b0f71e6",
             "method protocol fingerprint changed")
    for x in (p0, p1):
        _require(x["frozen_pairs"] == 96 and x["declared_folds"] == 480,
                 "declared denominator drift")
        _require(x["primary_support_fraction"] == 0.025
                 and x["primary_radius_km"] == 10.0,
                 "original scientific rule drift")
        _require(x["overall_confirmation_passed"] is True
                 and x["primary_statistical_gate_passed"] is True
                 and x["cross_taxon_guardrail_passed"] is True,
                 "one of two original runs did not pass the frozen gates")
        _require(x["pairs_with_any_failed_fold"] == 23,
                 "failed-pair accounting changed")
        _require(x["pair_bootstrap_95_ci"][0] > 0
                 and x["one_sided_sign_flip_p"] < 0.05,
                 "one of two original results was not positive")
    prior_lift = float(p0["overall_pair_mean_lift"])
    final_lift = float(p1["overall_pair_mean_lift"])
    _require(math.isclose(prior_lift,
             _mean([float(b["mean_lift"]) for b, _ in pair_rows]),
             rel_tol=0, abs_tol=1e-14), "prior pair mean disagrees")
    _require(math.isclose(final_lift,
             _mean([float(a["mean_lift"]) for _, a in pair_rows]),
             rel_tol=0, abs_tol=1e-14), "final pair mean disagrees")
    _require(math.isclose(final_lift,
             receipt["independent_recomputation"]["mean_lift_10km"],
             rel_tol=0, abs_tol=1e-14), "changed official paper inference")

    return {
        "schema_version": SCHEMA,
        "status": "HISTORICAL_NONINDEPENDENT_SEED_IMPLEMENTATION_COMPARISON",
        "provenance": {
            "prior_successful_run": PRIOR_RUN,
            "prior_artifact_id": PRIOR_ARTIFACT,
            "prior_head_sha": PRIOR_HEAD_SHA,
            "prior_zip_sha256": PRIOR_ARCHIVE["archive_sha256"],
            "final_official_run": FINAL_RUN,
            "final_artifact_id": FINAL_ARTIFACT,
            "final_head_sha": FINAL_HEAD_SHA,
            "final_zip_sha256": receipt["artifacts"]["confirmation"]["archive_sha256"],
            "same_original_export_manifest_bytes": True,
            "same_original_pair_export_status_bytes": True,
            "same_protocol_and_execution_fingerprints": True,
        },
        "frozen_geometry_and_recovery_outputs": {
            "original_fold_by_radius_rows": len(folds),
            "unaltered_nonlinear_support_fields_and_recall_in_all_rows": True,
            "only_random_mean_recall_and_lift_differ": True,
            "changed_random_baseline_fold_by_radius_rows": sum(
                _changed(b["random_mean_recall"], a["random_mean_recall"])
                for b, a in folds),
            "changed_pair_mean_lift_rows": changed_pairs,
        },
        "primary_10km": {
            "prior_mean_lift": prior_lift,
            "final_mean_lift": final_lift,
            "mean_lift_difference_final_minus_prior": final_lift - prior_lift,
            "prior_ci95": p0["pair_bootstrap_95_ci"],
            "final_ci95": p1["pair_bootstrap_95_ci"],
            "prior_signflip_p": p0["one_sided_sign_flip_p"],
            "final_signflip_p": p1["one_sided_sign_flip_p"],
            "both_passed_frozen_gates": True,
            "official_final_result_unchanged": True,
        },
        "by_radius_descriptive_only": by_radius,
        "scientific_limits": {
            "independent_new_taxa_or_cohort": False,
            "historical_input_GBIF_rows_byte_verified_equal": False,
            "comparison_is_controlled_fixed_input_RNG_experiment": False,
            "causal_attribution_only_to_seed_proven": False,
            "original_source_occurence_rows_recovered": False,
            "new_biological_or_field_effect": False,
            "original_frozen_method_parameters_retuned": False,
            "new_confirmatory_statistical_test": False,
        },
    }



def verify_saved_receipt(actual: object, saved_path: Path) -> None:
    """Require the saved no-coordinate report to match source-authenticated ZIPs."""
    expected = json.loads(Path(saved_path).read_text(encoding="utf-8"))

    def equal(x: object, y: object, where: str = "root") -> None:
        if isinstance(x, dict) and isinstance(y, dict):
            _require(x.keys() == y.keys(), f"saved receipt keys changed at {where}")
            for key in x:
                equal(x[key], y[key], f"{where}.{key}")
        elif isinstance(x, list) and isinstance(y, list):
            _require(len(x) == len(y), f"saved receipt list length changed at {where}")
            for i, (left, right) in enumerate(zip(x, y)):
                equal(left, right, f"{where}[{i}]")
        elif (isinstance(x, (int, float)) and not isinstance(x, bool)
              and isinstance(y, (int, float)) and not isinstance(y, bool)):
            _require(math.isfinite(x) and math.isfinite(y)
                     and math.isclose(x, y, rel_tol=0.0, abs_tol=1e-12),
                     f"saved receipt numerical change at {where}")
        else:
            _require(type(x) is type(y) and x == y,
                     f"saved receipt value change at {where}")

    equal(actual, expected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-zip", type=Path, required=True)
    parser.add_argument("--final-zip", type=Path, required=True)
    parser.add_argument("--verify-saved", type=Path)
    args = parser.parse_args()
    report = compare(args.prior_zip, args.final_zip)
    if args.verify_saved is not None:
        verify_saved_receipt(report, args.verify_saved)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
