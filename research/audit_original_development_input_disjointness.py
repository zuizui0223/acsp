#!/usr/bin/env python3
"""Source-byte audit: real DEVELOPMENT GBIF fold inputs vs untouched 96-pair cohort.

Input archives come from *different historical GitHub Actions runs*:
- 2026-08-19 robust-patch cross-taxon DEVELOPMENT (has real fold CSVs)
- 2026-08-20 predeclared 96-pair untouched CONFIRMATION (identities only)
This is NOT recovery of the frozen 96-pair confirmation's input records.
No network requests, data replacement, geographic coordinates or
record-level names/GBIF IDs are written to stdout or the public report.
"""
from __future__ import annotations

from collections import Counter
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

DEVELOPMENT_RUN = 32258117404
DEVELOPMENT_ARTIFACT = 9367472075
DEVELOPMENT_SHA256 = "46ca48bfa6be30e7302f1671b824e4a4f73da5040fb738fe44512b58806ba76a"
CONFIRMATION_RUN = 32335791948
CONFIRMATION_ARTIFACT = 9394691112
CONFIRMATION_SHA256 = "cc0f949649491439f91e1b90d01d48acbd3f7fffc6833a75105a3bc175a5faf3"
SCHEMA = "acsp-original-development-input-vs-confirmation-cohort-20261029"
MAX_ZIP_SIZE = 4_000_000
MAX_MEMBER_SIZE = 500_000


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read_archive(path: Path, sha: str, *, expected_count: int) -> dict[str, bytes]:
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), "missing source ZIP or symlink")
    _require(0 < path.stat().st_size < MAX_ZIP_SIZE, "unexpected original ZIP size")
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == sha, "original GitHub ZIP SHA256 mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            _require(len(infos) == expected_count, "original ZIP member count changed")
            paths = [x.filename for x in infos]
            _require(len(set(paths)) == len(paths), "duplicate ZIP member")
            _require(all(not x.is_dir() and 0 < x.file_size <= MAX_MEMBER_SIZE for x in infos),
                     "unsafe ZIP member size/type")
            _require(all(not PurePosixPath(x).is_absolute()
                         and ".." not in PurePosixPath(x).parts for x in paths),
                     "invalid ZIP member path")
            return {x.filename: z.read(x.filename) for x in infos}
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("could not read original GitHub ZIP") from exc


def _rows(source: dict[str, bytes], path: str) -> list[dict[str, str]]:
    _require(path in source, "required frozen source file missing")
    with io.StringIO(source[path].decode("utf-8-sig")) as f:
        reader = csv.DictReader(f)
        _require(bool(reader.fieldnames), "original source CSV lacks schema")
        return list(reader)


def _frozen_id(value: str) -> str:
    v = str(value).strip()
    _require(v.isdigit() and int(v) > 0, "missing/invalid source record identity")
    return str(int(v))


def audit(development_zip: Path, confirmation_cohort_zip: Path) -> dict[str, object]:
    development = _read_archive(development_zip, DEVELOPMENT_SHA256, expected_count=368)
    official = _read_archive(confirmation_cohort_zip, CONFIRMATION_SHA256, expected_count=4)
    original_cohort = _rows(official, "predeclared_taxon_region_pairs.csv")
    _require(len(original_cohort) == 96, "frozen independent cohort not 96")
    _require(all(x["status"] == "predeclared" for x in original_cohort),
             "independent cohort declaration status changed")
    independent_keys = {_frozen_id(x["speciesKey"]) for x in original_cohort}
    independent_names = {str(x["scientific_name"]).strip().casefold() for x in original_cohort}
    _require(len(independent_keys) == len(independent_names) == 96,
             "original confirmation taxon uniqueness changed")

    dev_keys: set[str] = set()
    dev_names: set[str] = set()
    group_counts: Counter[str] = Counter()
    source_fold_count = train_rows = heldout_rows = 0
    per_unique_pair_source_rows = 0
    per_fold_duplicate_ids = 0
    per_fold_train_heldout_overlap = 0
    fold_source_hashes_checked = 0
    fold_pools_stable_across_repeats = 0
    all_expected_paths: set[str] = {
        "combined_manifest.json", "combined_summary.csv",
        "samples/mixed.csv", "samples/plants.csv",
    }

    for scope in ("mixed", "plants"):
        root = f"exports/{scope}"
        declared_name = f"{root}/declared_pairs.csv"
        manifest_name = f"{root}/export_manifest.json"
        status_name = f"{root}/pair_export_status.csv"
        all_expected_paths |= {declared_name, manifest_name, status_name}
        declarations = _rows(development, declared_name)
        _require(len(declarations) == 8 and
                 all(x["status"] == "predeclared" for x in declarations),
                 "development stratum identities/status changed")
        manifest = json.loads(development[manifest_name])
        _require(manifest["declared_pairs"] == 8 and
                 manifest["status_counts"] == {"complete": 8},
                 "development export manifest/status changed")
        status = _rows(development, status_name)
        _require(len(status) == 8 and
                 all(row["status"] == "complete" for row in status),
                 "development status CSV changed")
        all_expected_paths |= {
            f"results/{scope}/robust_patch_development_manifest.json",
            f"results/{scope}/robust_patch_development_summary.csv",
        }

        for pair in declarations:
            taxon_key = _frozen_id(pair["speciesKey"])
            name = str(pair["scientific_name"]).strip().casefold()
            _require(name and taxon_key not in dev_keys and name not in dev_names,
                     "development taxa not unique")
            dev_keys.add(taxon_key)
            dev_names.add(name)
            group = pair["taxon_group"]
            _require(group in {"plant", "animal"}, "unexpected source taxon group")
            group_counts[group] += 1
            source_pair_id = int(pair["pair_id"])
            _require(source_pair_id >= 1, "invalid declared pair ID")
            pools: list[frozenset[str]] = []
            for repeat in range(1, 6):
                directory = f"{root}/pair_{source_pair_id:03d}/fold_{repeat:03d}"
                meta_path = f"{directory}/fold_manifest.json"
                _require(meta_path in development, "development fold manifest missing")
                meta = json.loads(development[meta_path])
                _require(meta["pair_id"] == source_pair_id and meta["repeat"] == repeat
                         and meta["status"] == "ready", "development fold identity/status drift")
                _require(_frozen_id(meta["provenance"]["species_key"]) == taxon_key
                         and meta["provenance"]["scientific_name"].strip().casefold() == name,
                         "source taxon/fold provenance disagrees")
                all_expected_paths.add(meta_path)
                fold_pool: set[str] = set()
                pair_sets = []
                for kind in ("training_occurrences", "held_out_occurrences"):
                    file_name = f"{kind}.csv"
                    path = f"{directory}/{file_name}"
                    rows = _rows(development, path)
                    entry = meta["files"][kind]
                    _require(entry["path"] == file_name
                             and entry["rows"] == len(rows)
                             and hashlib.sha256(development[path]).hexdigest() == entry["sha256"],
                             "source-baked original per-fold CSV hash/count drift")
                    _require(len(rows) > 0, "original development fold has empty source rows")
                    _require({"gbifID", "_gbif_id", "_row_id", "latitude", "longitude"} <= rows[0].keys(),
                             "development GBIF provenance columns missing")
                    ids = [_frozen_id(row["gbifID"]) for row in rows]
                    aliases = [_frozen_id(row["_gbif_id"]) for row in rows]
                    _require(ids == aliases, "GBIF ID alias changed in source fold")
                    _require(all(x["latitude"] and x["longitude"] for x in rows),
                             "source coordinate field missing")
                    _require(all(str(x["_row_id"]).isdigit() for x in rows),
                             "source occurrence ordinal missing")
                    _require(len(set(ids)) == len(ids), "development fold duplicate source ID")
                    _require(all("datasetKey" not in r for r in rows),
                             "source unexpectedly has datasetKey; recategorize provenance")
                    pair_sets.append(set(ids))
                    fold_pool.update(ids)
                    all_expected_paths.add(path)
                    fold_source_hashes_checked += 1
                    if kind == "training_occurrences":
                        train_rows += len(rows)
                        _require(meta["training_records"] == len(rows),
                                 "training count mismatch against source manifest")
                    else:
                        heldout_rows += len(rows)
                        _require(meta["heldout_records"] == len(rows),
                                 "heldout count mismatch against source manifest")
                _require(not pair_sets[0] & pair_sets[1],
                         "development train-heldout source IDs overlap")
                pools.append(frozenset(fold_pool))
                source_fold_count += 1
                all_expected_paths.add(f"{directory}/candidates.csv")
                candidate = meta["files"]["candidates"]
                _require(hashlib.sha256(development[f"{directory}/candidates.csv"]).hexdigest()
                         == candidate["sha256"], "original development candidate file changed")
                fold_source_hashes_checked += 1
            _require(all(p == pools[0] for p in pools), "source record pool changed across folds")
            fold_pools_stable_across_repeats += 1
            per_unique_pair_source_rows += len(pools[0])

    _require(set(development) == all_expected_paths, "unexpected source ZIP members")
    _require(source_fold_count == 80 and len(dev_keys) == len(dev_names) == 16,
             "development 16×5 fold contract drift")
    _require(group_counts == {"plant": 12, "animal": 4},
             "development source cohort taxonomic mix changed")
    _require(dev_keys.isdisjoint(independent_keys) and
             dev_names.isdisjoint(independent_names),
             "DEVELOPMENT taxon reused in independently confirmed 96-pair cohort")
    _require((train_rows, heldout_rows, per_unique_pair_source_rows) ==
             (9660, 1965, 2325),
             "source development record counters changed")
    _require(fold_source_hashes_checked == 240
             and fold_pools_stable_across_repeats == 16,
             "incomplete original source hash/identity checks")

    return {
        "schema_version": SCHEMA,
        "status": "DEVELOPMENT_INPUTS_RECOVERED_TAXON_DISJOINT_FROM_96_CONFIRMATION",
        "original_development_source": {
            "run_id": DEVELOPMENT_RUN,
            "artifact_id": DEVELOPMENT_ARTIFACT,
            "whole_zip_sha256": DEVELOPMENT_SHA256,
            "original_archive_member_count": len(development),
        },
        "independent_confirmation_source": {
            "run_id": CONFIRMATION_RUN,
            "artifact_id": CONFIRMATION_ARTIFACT,
            "whole_zip_sha256": CONFIRMATION_SHA256,
            "independent_taxa": len(independent_keys),
        },
        "development_taxa": len(dev_keys),
        "development_taxon_groups": dict(sorted(group_counts.items())),
        "development_folds": source_fold_count,
        "source_fold_csv_hashes_and_candidate_hashes_verified": fold_source_hashes_checked,
        "stable_source_record_pools_across_folds": fold_pools_stable_across_repeats,
        "training_row_instances_across_all_folds": train_rows,
        "heldout_row_instances_across_all_folds": heldout_rows,
        "development_distinct_pair_pool_rows_summed": per_unique_pair_source_rows,
        "development_and_independent_confirmation_taxon_name_overlap": 0,
        "development_and_independent_confirmation_species_key_overlap": 0,
        "used_gbif_id_aliases_present_in_development_fold_CSVs": True,
        "source_datasetKeys_in_original_development_CSVs": False,
        "boundaries": {
            "confirms_original_2026_08_20_independent_confirmation_inputs_recovered": False,
            "taxon_disjointness_proves_outcome_independence_in_all_other_senses": False,
            "contemporaneous_GBIF_datasetKeys_restored": False,
            "original_confirmation_GBIF_data_DOI_verified": False,
            "new_GBIF_queries_or_biological_tests_run": False,
            "raw_record_IDs_or_coordinates_disclosed": False,
            "historical_confirmation_or_algorithm_modified": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-zip", type=Path, required=True)
    parser.add_argument("--confirmation-cohort-zip", type=Path, required=True)
    parser.add_argument("--verify-saved", type=Path)
    args = parser.parse_args()
    report = audit(args.development_zip, args.confirmation_cohort_zip)
    if args.verify_saved:
        reference = json.loads(args.verify_saved.read_text(encoding="utf-8"))
        _require(report == reference, "saved source provenance receipt differs from original ZIPs")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
