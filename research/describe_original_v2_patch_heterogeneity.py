#!/usr/bin/env python3
"""Descriptive heterogeneity in the ORIGINAL 2026 ACSP robust-patch results.

Only accepts the SHA-256-pinned historical result ZIP. Reports aggregate
predeclared pair units, all declared failed folds and spatial radii.
NOT a new inferential test, region-specific effect, mechanism, treatment
effect, original GBIF input restoration, or global product validation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import io
import json
from pathlib import Path

import numpy as np

try:
    from research.replay_original_robust_patch_v2_artifacts import (
        _members, read_receipt, check_primary_table,
    )
except ModuleNotFoundError:
    from replay_original_robust_patch_v2_artifacts import (
        _members, read_receipt, check_primary_table,
    )

SCHEMA = "acsp-original-v2-descriptive-heterogeneity-20261028"
RADII = (1, 2, 5, 10)
EXPECTED_REGIONS = {
    "Chubu mountains", "Chugoku", "Hokkaido east", "Hokkaido west",
    "Izu", "Kanto", "Kinki", "Northern Kyushu", "Ryukyu", "Shikoku",
    "Southern Kyushu", "Tohoku",
}
KNOWN_FAILURES = {
    "": "no_failure",
    "empty_support_tier": "empty_robust_support",
    "ValueError: fewer than five unique complete training environment prototypes":
        "insufficient_environment_prototypes",
    "ValueError: occurrences occupy fewer than two spatial blocks":
        "insufficient_spatial_blocks",
    "ValueError: fewer than five training coordinates":
        "insufficient_training_coordinates",
}


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _read_csv(payload: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))


def _signs(values: list[float]) -> dict[str, int]:
    _check(all(np.isfinite(v) for v in values), "nonfinite frozen values")
    result = {"positive": sum(v > 0 for v in values),
              "zero": sum(v == 0 for v in values),
              "negative": sum(v < 0 for v in values)}
    _check(sum(result.values()) == len(values), "sign-count loss")
    return result


def _summary(rows: list[dict], key: str = "mean_lift") -> dict:
    values = [float(row[key]) for row in rows]
    _check(len(values) > 0, "empty descriptive stratum")
    return {
        "n_pairs": len(rows),
        "mean_lift": float(np.mean(values)),
        "median_lift": float(np.median(values)),
        "sign_counts": _signs(values),
    }


def build_report(result_zip: Path) -> dict:
    receipt = read_receipt()
    check_primary_table(receipt)
    files = _members(result_zip, receipt["artifacts"]["confirmation"])
    pairs = _read_csv(files["confirmation-results/confirmation_pair_results.csv"])
    folds = _read_csv(files["confirmation-results/confirmation_fold_results.csv"])
    export = _read_csv(files["confirmation-folds/pair_export_status.csv"])
    _check(len(pairs) == 96 and len(folds) == 1920 and len(export) == 96,
           "original 96×5×4 output shape drift")
    _check({int(x["pair_id"]) for x in pairs} == set(range(1, 97)),
           "original pair identifiers differ")
    _check(Counter(x["taxon_group"] for x in pairs) == {"plant": 48, "animal": 48},
           "frozen taxon group balance altered")
    _check(Counter(x["region_name"] for x in pairs) ==
           {region: 8 for region in EXPECTED_REGIONS},
           "frozen regional eight-pair balance altered")
    _check(all(int(x["fold_count"]) == 5 for x in pairs),
           "frozen fivefold denominator drift")
    _check({(int(x["pair_id"]), int(x["repeat"]), int(float(x["radius_km"])))
            for x in folds} ==
           {(p, f, radius) for p in range(1, 97) for f in range(1, 6) for radius in RADII},
           "original 96×5×4 fold grid no longer exact")
    _check(Counter(x["status"] for x in export) ==
           {"complete": 94, "failed_retained_as_zero": 2},
           "original fold-export status drift")

    overall = _summary(pairs)
    expected = receipt["independent_recomputation"]["mean_lift_10km"]
    _check(np.isclose(overall["mean_lift"], expected, rtol=0, atol=1e-14),
           "original primary mean differs from frozen confirmation")
    values = [float(x["mean_lift"]) for x in pairs]
    quartiles = [float(np.quantile(values, q)) for q in (0.25, 0.5, 0.75)]

    groups = {}
    for group in ("animal", "plant"):
        groups[group] = _summary([x for x in pairs if x["taxon_group"] == group])
        original_group = receipt["independent_recomputation"][f"{group}_mean_lift"]
        _check(np.isclose(groups[group]["mean_lift"], original_group, rtol=0, atol=1e-14),
               "original plant/animal mean drift")

    with_fails = [x for x in pairs if int(x["failed_folds"]) > 0]
    without_fails = [x for x in pairs if int(x["failed_folds"]) == 0]
    _check(len(with_fails) == 23 and len(without_fails) == 73,
           "failure-inclusive denominator drift")
    all_five_failed = sum(int(x["failed_folds"]) == 5 for x in pairs)
    _check(all_five_failed == 17, "original all-five-fail count drift")

    regions = {}
    leave_one_region_out = {}
    for name in sorted(EXPECTED_REGIONS):
        inside = [x for x in pairs if x["region_name"] == name]
        regions[name] = {
            **_summary(inside),
            "pairs_with_failed_folds": sum(int(x["failed_folds"]) > 0 for x in inside),
        }
        leave_one_region_out[name] = float(
            np.mean([float(x["mean_lift"]) for x in pairs if x["region_name"] != name])
        )
    regions_positive = sum(s["mean_lift"] > 0 for s in regions.values())
    regions_negative = sum(s["mean_lift"] < 0 for s in regions.values())
    _check(regions_positive == 10 and regions_negative == 2,
           "original descriptive regional sign counts drift")

    scales = []
    failure_counts = Counter()
    for radius in RADII:
        subset = [x for x in folds if float(x["radius_km"]) == radius]
        _check(len(subset) == 480, "missing original folds for radius")
        scale = {
            "radius_km": radius,
            "declared_folds": len(subset),
            "mean_heldout_recall": float(np.mean([float(x["recall"]) for x in subset])),
            "mean_same_size_random_recall": float(
                np.mean([float(x["random_mean_recall"]) for x in subset])),
            "mean_lift": float(np.mean([float(x["lift_over_random"]) for x in subset])),
        }
        _check(np.isclose(scale["mean_lift"],
                          next(x["mean_lift"] for x in
                               receipt["independent_recomputation"]["radius_means_descriptive"]
                               if int(x["radius_km"]) == radius),
                          rtol=0, atol=1e-14), "descriptive radius lift drift")
        scales.append(scale)
        if radius == 10:
            for row in subset:
                failure = row["failure_reason"]
                _check(failure in KNOWN_FAILURES, "unknown original failure reason")
                failure_counts[KNOWN_FAILURES[failure]] += 1
    _check(sum(failure_counts.values()) == 480, "primary fold failures not preserved")
    _check(failure_counts["no_failure"] == 375, "primary evaluable folds changed")

    return {
        "schema_version": SCHEMA,
        "status": "POSTHOC_DESCRIPTION_OF_FROZEN_VALIDATION_NOT_INDEPENDENT_CONFIRMATION",
        "original_source_run": receipt["source_runs"]["confirmation"],
        "original_artifact_id": receipt["artifacts"]["confirmation"]["id"],
        "original_zip_sha256": receipt["artifacts"]["confirmation"]["archive_sha256"],
        "unit": "taxon_region_pair_with_all_five_folds_retained",
        "declared_pair_count": 96,
        "all_declared_fold_by_radius_rows": 1920,
        "primary_10km": {
            **overall,
            "pair_lift_q1_median_q3": quartiles,
            "zero_is_not_biological_nondetection": True,
            "failure_inclusive_primary_confirmatory_mean_unchanged": True,
        },
        "taxon_groups": groups,
        "pair_failure_strata_descriptive_only": {
            "no_failed_fold": _summary(without_fails),
            "one_or_more_failed_folds": _summary(with_fails),
            "five_failed_folds_count": all_five_failed,
            "not_for_complete_case_reestimation": True,
        },
        "regions_descriptive_only": regions,
        "regional_means_positive": regions_positive,
        "regional_means_negative": regions_negative,
        "leave_one_region_out_descriptive_range": [
            min(leave_one_region_out.values()),
            max(leave_one_region_out.values()),
        ],
        "distance_scales_descriptive_only": scales,
        "primary_10km_failure_reasons": dict(sorted(failure_counts.items())),
        "science_boundary": {
            "only_original_2026_08_20_historical_result_rows_used": True,
            "new_gbif_queries_or_field_outcomes_used": False,
            "raw_original_gbif_occurrence_inputs_recovered": False,
            "regional_differences_causal_or_confirmatory": False,
            "secondary_radii_new_confirmatory_endpoints": False,
            "taxon_group_posthoc_sign_counts_new_tests": False,
            "primary_frozen_inference_or_denominator_changed": False,
            "geographic_global_product_validated_by_this": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-zip", type=Path, required=True)
    parser.add_argument("--verify-saved", type=Path)
    args = parser.parse_args()
    report = build_report(args.results_zip)
    if args.verify_saved is not None:
        saved = json.loads(args.verify_saved.read_text(encoding="utf-8"))
        _check(report == saved, "saved descriptive receipt differs from original ZIP")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
