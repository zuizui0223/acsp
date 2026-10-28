#!/usr/bin/env python3
"""Offline structural inspection of a CLAIMED 2026 ACSP v2 occurrence-fold backup.

Purpose: If a private folder later appears, test whether its 480 paired folds
match the frozen taxon identities, original export counts, metadata, and exact
seeded spatial block partitions. This is NOT proof the underlying GBIF records
were those actually served in 2026: no contemporaneous per-fold raw-data hash
survives the checked Actions result archives.

Never fetch current GBIF, serialize private occurrence IDs, print coordinates,
write the original fold CSVs to GitHub, or promote mere structural agreement
into original-input authentication. Source archives are SHA-256-pinned.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re

import numpy as np

try:
    from research.replay_original_robust_patch_v2_artifacts import (
        _members, read_receipt,
    )
except ModuleNotFoundError:
    from replay_original_robust_patch_v2_artifacts import (
        _members, read_receipt,
    )

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT = "47afe0f78fdc253f395cb0eb6410ae846ab15e12da1b922c72edad357c722a45"
N_PAIRS = 96
REPEATS = 5
SEED_BASE = 20260823
BLOCK_DEGREES = 0.1
MAX_RECORDS = 150
PAIR_PATTERN = re.compile(r"pair_\d{3}\Z")
FOLD_PATTERN = re.compile(r"fold_\d{3}\Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _safe_file(path: Path, max_bytes: int = 2_000_000) -> bytes:
    _require(path.is_file() and not path.is_symlink(), "required backup file absent/symlink")
    _require(0 <= path.stat().st_size <= max_bytes, "candidate file too large")
    return path.read_bytes()


def _csv_bytes(content: bytes) -> list[dict[str, str]]:
    with io.StringIO(content.decode("utf-8-sig")) as stream:
        reader = csv.DictReader(stream)
        _require(reader.fieldnames is not None and
                 len(reader.fieldnames) == len(set(reader.fieldnames)),
                 "candidate CSV missing/duplicate headers")
        data = list(reader)
    _require(all(None not in row and None not in row.values() for row in data),
             "ragged candidate CSV")
    return data


def _read_rows(path: Path) -> list[dict[str, str]]:
    return _csv_bytes(_safe_file(path))


def _float_coordinate(row: dict[str, str], direction: str) -> float:
    fields = {"latitude": ("latitude", "_latitude", "decimalLatitude"),
              "longitude": ("longitude", "_longitude", "decimalLongitude")}[direction]
    used = next((row[f] for f in fields if f in row), None)
    _require(used is not None, "candidate coordinate column absent")
    try:
        value = float(used)
    except ValueError as exc:
        raise ValueError("candidate coordinate invalid") from exc
    _require(math.isfinite(value) and
             (abs(value) <= 90 if direction == "latitude" else abs(value) <= 180),
             "candidate coordinate outside valid range")
    return value


def _block(row: dict[str, str]) -> str:
    return f"{math.floor(_float_coordinate(row, 'latitude') / BLOCK_DEGREES)}:" \
           f"{math.floor(_float_coordinate(row, 'longitude') / BLOCK_DEGREES)}"


def _ids(rows: list[dict[str, str]]) -> dict[int, dict[str, str]]:
    output: dict[int, dict[str, str]] = {}
    for row in rows:
        _require("_row_id" in row and re.fullmatch(r"\d+", row["_row_id"] or "") is not None,
                 "frozen cleaned row ordinal not present")
        k = int(row["_row_id"])
        _require(k not in output, "duplicate cleaned row ordinal in fold")
        output[k] = row
    return output


def _status_pair(cohort: dict[str, str], status: dict[str, str]) -> None:
    for key in ("pair_id", "scientific_name", "taxon_group"):
        _require(cohort[key] == status[key], "candidate identity/status mismatch")
    _require(status["status"] in ("complete", "failed_retained_as_zero"),
             "unrecognized frozen pair-export state")
    _require(int(status["written_folds"]) == REPEATS,
             "original exported-fold count differs")


def inspect_candidate_root(
    root: Path, identities: list[dict[str, str]], statuses: list[dict[str, str]],
    *, expected_pairs: int = N_PAIRS,
) -> dict[str, object]:
    """Do not use this output to assert historical GBIF record authenticity."""
    root = Path(root)
    _require(root.is_dir() and not root.is_symlink(), "candidate root missing/symlink")
    _require(len(identities) == len(statuses) == expected_pairs,
             "frozen identity/status denominator mismatch")
    declared = {int(x["pair_id"]): x for x in identities}
    recorded = {int(x["pair_id"]): x for x in statuses}
    _require(len(declared) == len(recorded) == expected_pairs and
             set(declared) == set(recorded) == set(range(1, expected_pairs + 1)),
             "frozen pair IDs incomplete/duplicated")
    _require({p.name for p in root.iterdir() if PAIR_PATTERN.fullmatch(p.name)} ==
             {f"pair_{i:03d}" for i in range(1, expected_pairs + 1)},
             "candidate root pair directories incomplete")
    totals = {"complete_pairs": 0, "failed_retained_pairs": 0,
              "fold_manifests_checked": 0, "structurally_consistent_complete_pairs": 0,
              "distinct_cleaned_rows_across_complete_pairs": 0,
              "cleaned_rows_with_nonblank_gbif_id": 0,
              "cleaned_rows_with_nonblank_dataset_key": 0,
              "cleaned_rows_missing_gbif_id": 0}
    for pair_id in sorted(declared):
        identity = declared[pair_id]
        status = recorded[pair_id]
        _status_pair(identity, status)
        pair_dir = root / f"pair_{pair_id:03d}"
        _require(pair_dir.is_dir() and not pair_dir.is_symlink(), "candidate pair folder absent")
        _require({p.name for p in pair_dir.iterdir() if FOLD_PATTERN.fullmatch(p.name)} ==
                 {f"fold_{j:03d}" for j in range(1, REPEATS + 1)},
                 "candidate pair fold folders incomplete")
        known_pool = None
        split_maps: list[tuple[set[int], set[int]]] = []
        for repeat in range(1, REPEATS + 1):
            d = pair_dir / f"fold_{repeat:03d}"
            _require(d.is_dir() and not d.is_symlink(), "candidate fold folder absent/symlink")
            record = json.loads(_safe_file(d / "fold_manifest.json").decode("utf-8"))
            meta = record["provenance"]
            _require(int(record["pair_id"]) == int(record["provenance"]["pair_id"]) ==
                     pair_id and int(record["repeat"]) == repeat,
                     "frozen pair/fold provenance mismatch")
            _require(record["execution_fingerprint"] == FINGERPRINT,
                     "frozen execution fingerprint mismatch")
            _require(str(meta["scientific_name"]) == identity["scientific_name"] and
                     str(meta["taxon_group"]) == identity["taxon_group"] and
                     str(meta["region_name"]) == identity["region_name"] and
                     int(meta["species_key"]) == int(identity["speciesKey"]),
                     "frozen taxon/region identity mismatch")
            train = _read_rows(d / "training_occurrences.csv")
            held = _read_rows(d / "held_out_occurrences.csv")
            totals["fold_manifests_checked"] += 1
            _require(int(record["training_records"]) == len(train) and
                     int(record["heldout_records"]) == len(held),
                     "per-fold CSV counts disagree with frozen fold manifest")
            if status["status"] == "failed_retained_as_zero":
                _require(record["status"] == "failed_placeholder" and
                         len(train) == len(held) == 0 and
                         record["failure_reason"] == status["failure_reason"],
                         "failed pair placeholder no longer zero")
                continue
            _require(record["status"] == "ready" and not record["failure_reason"],
                     "completed pair fold is not ready")
            _require(train and held and len(train) + len(held) <= MAX_RECORDS and
                     len(train) + len(held) == int(status["occurrence_rows"]),
                     "completed pair record counts differ from frozen original")
            tr, ho = _ids(train), _ids(held)
            _require(not (set(tr) & set(ho)), "same cleaned record in train and heldout")
            pool = {**tr, **ho}
            _require(set(pool) == set(range(len(pool))),
                     "cleaned original row ordinals incomplete")
            if known_pool is None:
                known_pool = pool
            else:
                _require(pool == known_pool, "candidate input pool differs across five folds")
            split_maps.append((set(tr), set(ho)))
        if status["status"] == "failed_retained_as_zero":
            totals["failed_retained_pairs"] += 1
            continue
        totals["complete_pairs"] += 1
        _require(known_pool is not None and len(split_maps) == REPEATS,
                 "completed pair missing source rows")
        # Original exporter splits a single deterministic ordered occurrence pool.
        ordered = [known_pool[i] for i in range(len(known_pool))]
        ordered_blocks = list(dict.fromkeys(_block(r) for r in ordered))
        _require(len(ordered_blocks) == int(status["spatial_blocks"]) >= 2,
                 "original spatial block count differs")
        holdout_count = min(len(ordered_blocks) - 1,
                            max(1, int(round(len(ordered_blocks) * 0.2))))
        rng = np.random.default_rng(SEED_BASE + pair_id)
        blocks = np.array(ordered_blocks, dtype=object)
        for train_ids, heldout_ids in split_maps:
            selected = set(rng.choice(blocks, size=holdout_count,
                                      replace=False).tolist())
            expected_held = {i for i, row in enumerate(ordered) if _block(row) in selected}
            _require(heldout_ids == expected_held and
                     train_ids == set(range(len(ordered))) - expected_held,
                     "candidate split does not match original frozen RNG rule")
        totals["structurally_consistent_complete_pairs"] += 1
        totals["distinct_cleaned_rows_across_complete_pairs"] += len(ordered)
        for row in ordered:
            fid = row.get("_gbif_id") or row.get("gbifID") or ""
            if fid.strip():
                totals["cleaned_rows_with_nonblank_gbif_id"] += 1
            else:
                totals["cleaned_rows_missing_gbif_id"] += 1
            if (row.get("datasetKey") or "").strip():
                totals["cleaned_rows_with_nonblank_dataset_key"] += 1
    _require(totals["complete_pairs"] + totals["failed_retained_pairs"] == expected_pairs,
             "declared failed-pair denominator changed")
    _require(totals["fold_manifests_checked"] == expected_pairs * REPEATS,
             "declared fold denominator changed")
    return {
        "status": "STRUCTURALLY_CONSISTENT_CANDIDATE_BACKUP_PROVENANCE_UNAUTHENTICATED",
        "denominator": {"pairs": expected_pairs, "folds": expected_pairs * REPEATS},
        "checks": totals,
        "original_historical_record_id_set_proven": False,
        "historical_gbif_dataset_key_attribution_proven": False,
        "retrospective_2026_original_source_proven": False,
        "untrusted_candidate_can_prove_authenticity_by_structural_checks_alone": False,
        "new_gbif_requests_made": False,
        "new_confirmation_performed": False,
        "raw_record_ids_or_coordinates_in_report": False,
    }


def audit_with_verified_historical_archives(root: Path, cohort_zip: Path,
                                            results_zip: Path) -> dict[str, object]:
    receipt = read_receipt()
    cohort = _members(cohort_zip, receipt["artifacts"]["cohort"])
    results = _members(results_zip, receipt["artifacts"]["confirmation"])
    identities = _csv_bytes(cohort["predeclared_taxon_region_pairs.csv"])
    status = _csv_bytes(results["confirmation-folds/pair_export_status.csv"])
    report = inspect_candidate_root(root, identities, status)
    _require(report["checks"]["complete_pairs"] == 94 and
             report["checks"]["failed_retained_pairs"] == 2,
             "original pair export-state denominator changed")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--cohort-zip", type=Path, required=True)
    parser.add_argument("--results-zip", type=Path, required=True)
    args = parser.parse_args()
    # Print only safe counts; no file paths, taxon names, record IDs or coordinates.
    result = audit_with_verified_historical_archives(args.candidate_root,
                                                      args.cohort_zip,
                                                      args.results_zip)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
