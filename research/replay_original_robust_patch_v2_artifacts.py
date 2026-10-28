#!/usr/bin/env python3
"""Replay ACSP v2 statistics from SHA-pinned ORIGINAL GitHub result ZIPs.

This checks the authentic 2026-08-20 cohort and 96-pair/480-fold result
archives; it is NOT a refit from historical GBIF occurrence records. Only
the exact original ZIPs, with byte-for-byte SHA matches, may satisfy replay.
No network, prospective data, private site coordinates or current GBIF fetch.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "validation/acsp_original_v2_archival_reconciliation_20261028.json"
PRIMARY_TABLE = ROOT / "paper/generated/table_1_robust_patch_confirmation.csv"
FINGERPRINT = "47afe0f78fdc253f395cb0eb6410ae846ab15e12da1b922c72edad357c722a45"
ARCHIVE_SIZE_LIMIT = 20_000_000


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_receipt(receipt_path: Path = RECEIPT) -> dict:
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    _check(receipt["schema_version"] == "acsp-original-v2-results-byte-recovery-2026-10-28",
           "unexpected archival receipt schema")
    _check(receipt["status"] ==
           "ORIGINAL_RESULTS_RECOVERED_AND_STATISTICS_REPRODUCED_INPUT_ROWS_STILL_MISSING",
           "archival result/input boundary altered")
    _check(receipt["source_runs"] == {"cohort": 32335791948, "confirmation": 32337884576},
           "original run IDs altered")
    for name, artifact_id in (("cohort", 9394691112), ("confirmation", 9396133154)):
        artifact = receipt["artifacts"][name]
        _check(artifact["id"] == artifact_id, "original artifact id altered")
        _check(len(artifact["archive_sha256"]) == 64, "missing ZIP digest")
        _check(all(len(s) == 64 for s in artifact["member_sha256"].values()),
               "missing internal member digest")
        _check(not any("training_occurrences" in p or "held_out_occurrences" in p
                       for p in artifact["member_sha256"]),
               "original raw input incorrectly claimed as an archived ZIP member")
    _check(receipt["archive_contents"]["declared_folds_per_radius"] == 480
           and receipt["archive_contents"]["pair_results"] == 96
           and receipt["archive_contents"]["fold_rows_all_radii"] == 1920,
           "declared confirmation denominator altered")
    _check(receipt["scientific_claims"]["original_occurrence_inputs_recovered"] is False,
           "raw GBIF input cannot be claimed recovered")
    _check(receipt["scientific_claims"]["original_GBIF_download_DOI_verified"] is False,
           "original GBIF download DOI unverified")
    _check(receipt["scientific_claims"]["new_biological_validation"] is False,
           "historical result replay is not new biology")
    return receipt


def check_primary_table(receipt: dict, table_path: Path = PRIMARY_TABLE) -> None:
    with Path(table_path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    _check(len(rows) == 1, "primary table must have exactly one row")
    row = rows[0]
    _check(row["confirmation_status"] == "untouched_confirmation_passed",
           "frozen primary confirmation status changed")
    _check(row["analysis_scope"] == "validated_japan_12_region_frame",
           "validated geographic scope changed")
    _check(row["comparator"] == "same-size random candidate-patch sets",
           "original comparator changed")
    expected = receipt["independent_recomputation"]
    for column, value in (
        ("mean_lift_over_comparator", expected["mean_lift_10km"]),
        ("bootstrap_ci95_lower", expected["pair_bootstrap_95_ci"][0]),
        ("bootstrap_ci95_upper", expected["pair_bootstrap_95_ci"][1]),
        ("sign_flip_p", expected["one_sided_signflip_p"]),
        ("plant_mean_lift", expected["plant_mean_lift"]),
        ("animal_mean_lift", expected["animal_mean_lift"]),
    ):
        _check(np.isclose(float(row[column]), float(value), rtol=0, atol=1e-14),
               f"primary table changed: {column}")
    _check(int(row["declared_taxon_region_pairs"]) == 96
           and int(row["declared_folds"]) == 480, "primary declared cohort changed")


def _members(path: Path, source: dict) -> dict[str, bytes]:
    archive = Path(path)
    _check(archive.is_file() and not archive.is_symlink(), "original ZIP missing")
    _check(0 < archive.stat().st_size < ARCHIVE_SIZE_LIMIT, "original ZIP size invalid")
    data = archive.read_bytes()
    _check(hashlib.sha256(data).hexdigest() == source["archive_sha256"],
           "original archive SHA256 differs; no reinterpretation allowed")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            _check(len(infos) == len(set(x.filename for x in infos)), "duplicate ZIP member")
            _check({x.filename for x in infos} == set(source["member_sha256"]),
                   "original ZIP member paths changed")
            _check(all(not x.is_dir() and x.file_size < ARCHIVE_SIZE_LIMIT for x in infos),
                   "unexpected directory or oversized ZIP member")
            contents = {name: z.read(name) for name in source["member_sha256"]}
    except (zipfile.BadZipFile, OSError) as err:
        raise ValueError("cannot read original ZIP") from err
    for name, payload in contents.items():
        _check(hashlib.sha256(payload).hexdigest() == source["member_sha256"][name],
               f"original ZIP internal SHA256 differs: {name}")
    return contents


def _csv(contents: dict[str, bytes], name: str) -> list[dict[str, str]]:
    with io.StringIO(contents[name].decode("utf-8-sig")) as s:
        return list(csv.DictReader(s))


def _mean(rows: list[dict[str, str]], key: str) -> float:
    return float(np.mean([float(x[key]) for x in rows]))


def replay(cohort_zip: Path, results_zip: Path,
           receipt_path: Path = RECEIPT, primary_table: Path = PRIMARY_TABLE) -> dict:
    receipt = read_receipt(receipt_path)
    check_primary_table(receipt, primary_table)
    cohort = _members(cohort_zip, receipt["artifacts"]["cohort"])
    original = _members(results_zip, receipt["artifacts"]["confirmation"])
    identities = _csv(cohort, "predeclared_taxon_region_pairs.csv")
    pairs = _csv(original, "confirmation-results/confirmation_pair_results.csv")
    folds = _csv(original, "confirmation-results/confirmation_fold_results.csv")
    exports = _csv(original, "confirmation-folds/pair_export_status.csv")
    radius_summary = _csv(original, "confirmation-results/confirmation_radius_summary.csv")
    original_summary = json.loads(original["confirmation-results/confirmation_summary.json"])
    export_manifest = json.loads(original["confirmation-folds/export_manifest.json"])
    cohort_manifest = json.loads(cohort["cohort_manifest.json"])

    _check(len(identities) == len(pairs) == len(exports) == 96
           and len(folds) == 1920, "wrong original cohort or fold rows")
    _check({int(x["pair_id"]) for x in pairs} == set(range(1, 97)),
           "original pair identifiers not exhaustive")
    _check({x["pair_id"] for x in identities} == {x["pair_id"] for x in pairs},
           "cohort taxon pair mismatch")
    _check({x["scientific_name"] for x in identities} ==
           {x["scientific_name"] for x in pairs},
           "cohort taxon identity mismatch")
    _check({(int(x["pair_id"]), int(x["repeat"]), float(x["radius_km"]))
            for x in folds} ==
           {(p, fold, radius) for p in range(1, 97)
            for fold in range(1, 6) for radius in (1.0, 2.0, 5.0, 10.0)},
           "original declared 96 x 5 x 4 fold grid incomplete")
    _check(export_manifest["written_fold_manifests"] == 480
           and cohort_manifest["unique_declared_taxa"] == 96,
           "source manifests changed")
    _check(original_summary["execution_fingerprint"] == FINGERPRINT,
           "original frozen execution fingerprint changed")
    statuses = Counter(x["status"] for x in exports)
    _check(statuses == {"complete": 94, "failed_retained_as_zero": 2},
           "original export status counts changed")
    _check(sum(int(x["failed_folds"]) > 0 for x in pairs) == 23,
           "original folded failure count changed")

    values = np.asarray([float(x["mean_lift"]) for x in
                         sorted(pairs, key=lambda x: int(x["pair_id"]))])
    observed = float(values.mean())
    expected = receipt["independent_recomputation"]
    boot_rng = np.random.default_rng(expected["bootstrap_seed"])
    means = np.asarray([float(boot_rng.choice(values, size=96, replace=True).mean())
                        for _ in range(expected["bootstrap_draws"])])
    ci = np.quantile(means, [0.025, 0.975]).tolist()
    flip_rng = np.random.default_rng(expected["signflip_seed"])
    extreme = sum(float((values * flip_rng.choice((-1.0, 1.0), size=96)).mean()) >= observed
                  for _ in range(expected["signflip_draws"]))
    p = float((1 + extreme) / (expected["signflip_draws"] + 1))
    groups = {group: _mean([x for x in pairs if x["taxon_group"] == group], "mean_lift")
              for group in ("plant", "animal")}
    for actual, declared, name in (
        (observed, expected["mean_lift_10km"], "mean lift"),
        (p, expected["one_sided_signflip_p"], "sign-flip p"),
        (groups["plant"], expected["plant_mean_lift"], "plant mean"),
        (groups["animal"], expected["animal_mean_lift"], "animal mean"),
        (ci[0], expected["pair_bootstrap_95_ci"][0], "CI lower"),
        (ci[1], expected["pair_bootstrap_95_ci"][1], "CI upper"),
        (observed, original_summary["overall_pair_mean_lift"], "original mean"),
        (p, original_summary["one_sided_sign_flip_p"], "original p"),
    ):
        _check(np.isclose(actual, declared, rtol=0, atol=1e-14), f"replay mismatch: {name}")

    radii = []
    for r in (1.0, 2.0, 5.0, 10.0):
        subset = [x for x in folds if float(x["radius_km"]) == r]
        _check(len(subset) == 480, "incorrect fold count at recovery radius")
        comp = {"radius_km": int(r), "recall": _mean(subset, "recall"),
                "random_mean_recall": _mean(subset, "random_mean_recall"),
                "lift_over_random": _mean(subset, "lift_over_random")}
        original_row = next(x for x in radius_summary if float(x["radius_km"]) == r)
        for field, source_col in (("recall", "mean_recall"),
                                  ("random_mean_recall", "mean_random_recall"),
                                  ("lift_over_random", "mean_lift")):
            _check(np.isclose(comp[field], float(original_row[source_col]), rtol=0, atol=1e-14),
                   f"original radius table mismatch at {r} km")
        radii.append(comp)

    return {
        "status": "BYTE_VERIFIED_HISTORICAL_RESULTS_STATISTICS_REPRODUCED",
        "primary_pairs": 96,
        "declared_folds": 480,
        "fold_rows_at_four_scales": 1920,
        "original_export_pair_status": dict(statuses),
        "pairs_with_any_failed_fold": 23,
        "primary_mean_lift": observed,
        "primary_ci95": ci,
        "sign_flip_p": p,
        "plant_mean_lift": groups["plant"],
        "animal_mean_lift": groups["animal"],
        "secondary_descriptive_radius_results": radii,
        "original_occurrence_input_rows_present": False,
        "original_gbif_input_doi_verified": False,
        "new_biological_validation_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-zip", type=Path, required=True)
    parser.add_argument("--results-zip", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    args = parser.parse_args()
    print(json.dumps(replay(args.cohort_zip, args.results_zip, args.receipt),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
