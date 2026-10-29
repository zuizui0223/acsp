#!/usr/bin/env python3
"""Join private cleaned ACSP rows to a frozen NEW-cohort GBIF raw-source ZIP.

Run entirely offline, against the private ZIP and receipt created by
freeze_prospective_gbif_search_source_v1.py.  A bridge is only accepted
if the source ZIP already contains its explicit, exact analysis-used
GBIF ID list; merely fetching matching records is insufficient.

The public result contains hashes/counts only: no coordinates, taxon
names, row IDs, or datasetKey UUIDs. Source provenance, capture time,
scientific independence and GBIF DOI are NOT attested by this check.
Never substitute a new source for the unrecovered August 2026 inputs.
"""
from __future__ import annotations

from collections import Counter
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

try:
    from research import freeze_prospective_gbif_search_source_v1 as source
except ModuleNotFoundError:
    import freeze_prospective_gbif_search_source_v1 as source

SCHEMA = "acsp-new-prospective-gbif-used-row-bridge-v1"
STATUS = "NEW_COHORT_CLEANED_INPUT_MATCHES_FROZEN_RAW_IDS_NOT_ORIGIN_ATTESTED"
COORDINATE_PAIRS = (
    ("_latitude", "_longitude"),
    ("latitude", "longitude"),
    ("decimalLatitude", "decimalLongitude"),
)
AUDIT_MAX_BYTES = 12_000_000


def _check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _safe_original_bytes(path: Path, max_bytes: int = AUDIT_MAX_BYTES) -> bytes:
    _check(path.is_file() and not path.is_symlink(),
           "private source file missing or symlinked")
    _check(0 < path.stat().st_size <= max_bytes,
           "private source size exceeds bounded audit limit")
    return path.read_bytes()


def _record_coordinates(record: dict) -> tuple[float, float]:
    try:
        lat = float(record["decimalLatitude"])
        lon = float(record["decimalLongitude"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("original source coordinate missing or malformed") from exc
    _check(math.isfinite(lat) and math.isfinite(lon)
           and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0,
           "original source coordinate outside valid bounds")
    return lat, lon


def _clean_coordinates(row: dict[str, str], original: tuple[float, float]) -> None:
    complete = 0
    for lat_key, lon_key in COORDINATE_PAIRS:
        has_lat, has_lon = lat_key in row, lon_key in row
        _check(has_lat == has_lon, "partial cleaned coordinate column pair")
        if not has_lat:
            continue
        complete += 1
        try:
            lat = float(row[lat_key])
            lon = float(row[lon_key])
        except (TypeError, ValueError) as exc:
            raise ValueError("cleaned coordinate malformed") from exc
        _check(math.isfinite(lat) and math.isfinite(lon),
               "nonfinite cleaned coordinate")
        _check(math.isclose(lat, original[0], rel_tol=0, abs_tol=1e-9)
               and math.isclose(lon, original[1], rel_tol=0, abs_tol=1e-9),
               "cleaned coordinate does not match raw GBIF source")
    _check(complete > 0, "cleaned rows lack a complete coordinate pair")


def _used_ids(payload: bytes) -> list[str]:
    try:
        values = [line.strip() for line in payload.decode("utf-8-sig").splitlines()
                  if line.strip()]
    except UnicodeDecodeError as exc:
        raise ValueError("source used-ID inventory is not UTF-8") from exc
    _check(bool(values), "private frozen analysis-used ID inventory is empty")
    result = [source._record_id(value) for value in values]
    _check(len(result) == len(set(result)),
           "duplicate used GBIF IDs in source-private inventory")
    return result


def bridge(private_zip: Path, source_receipt_path: Path,
           cleaned_csv_path: Path, public_receipt_path: Path) -> dict:
    # SHA, manifest member hashes and source protocol label are checked
    # before any cleaned rows can be accepted.
    source_report = source.verify_archive(private_zip, source_receipt_path)
    _check(source_report["purpose"] == source.PURPOSE
           and source_report["status"] ==
           "NEW_COHORT_RAW_SOURCE_SNAPSHOTTED_NOT_ORIGIN_ATTESTED",
           "input snapshot is not a prospective capture")
    _check(source_report["explicit_analysis_used_id_set_archived_privately"] is True,
           "analysis-used ID list was not frozen in source-private ZIP")
    _check(source_report["original_2026_august_96pair_source_recovered"] is False,
           "historical August 2026 original cannot be promoted")
    _check(source_report["provider_response_origin_independently_authenticated"] is False,
           "unattested source must remain explicitly unauthenticated")

    with zipfile.ZipFile(private_zip) as archive:
        names = set(archive.namelist())
        _check("analysis_used_gbif_ids.txt" in names
               and "private_attribution.json" in names
               and "capture_manifest.json" in names,
               "source ZIP lacks frozen exact used-ID inventory/metadata")
        manifest = source._validate_manifest(
            json.loads(archive.read("capture_manifest.json"))
        )
        attribution = json.loads(archive.read("private_attribution.json"))
        used = _used_ids(archive.read("analysis_used_gbif_ids.txt"))
        used_set = set(used)
        _check(attribution.get("analysis_used_record_ids_provided") is True
               and attribution.get("analysis_used_record_count") == len(used)
               and source_report["analysis_used_id_count_if_supplied"] == len(used),
               "frozen used-ID count differs from source attribution")

        observed: dict[str, dict] = {}
        for page in manifest["pages"]:
            records = source._response_records(
                archive.read("raw_pages/" + page["path"]), page["query"]
            )
            for record in records:
                rid = source._record_id(record.get("gbifID", record.get("key")))
                _check(rid not in observed, "source ZIP repeats an original GBIF ID")
                observed[rid] = record
        _check(len(observed) == source_report["unique_gbif_ids_fetched"],
               "source receipt record totals changed")
        _check(used_set <= set(observed),
               "source used-ID inventory contains GBIF IDs absent from raw pages")

        raw_cleaned = _safe_original_bytes(Path(cleaned_csv_path))
        with io.StringIO(raw_cleaned.decode("utf-8-sig")) as stream:
            reader = csv.DictReader(stream)
            _check(reader.fieldnames is not None, "cleaned GBIF CSV header missing")
            headers = set(reader.fieldnames)
            _check("_row_id" in headers, "cleaned row ordinal required")
            _check(bool({"_gbif_id", "gbifID"} & headers),
                   "cleaned GBIF ID column required")
            _check(any(a in headers and b in headers
                       for a, b in COORDINATE_PAIRS),
                   "cleaned record coordinate columns missing")
            rows = list(reader)
        _check(bool(rows) and len(rows) <= len(observed)
               and len(rows) <= len(used), "cleaned row count outside frozen source")
        _check(all(None not in row and None not in row.values()
                   for row in rows), "malformed cleaned row CSV")

        cleaned_ids: list[str] = []
        cleaned_ordinals: list[int] = []
        touched_datasets = Counter()
        touched_licenses = Counter()
        optional_dataset_column_present = "datasetKey" in headers
        optional_license_column_present = "license" in headers
        for row in rows:
            candidate_fields = [
                source._record_id(row[col])
                for col in ("_gbif_id", "gbifID") if col in row
            ]
            _check(len(set(candidate_fields)) == 1,
                   "cleaned GBIF identifier aliases disagree")
            rid = candidate_fields[0]
            _check(rid in observed,
                   "cleaned GBIF record not found in frozen source pages")
            cleaned_ids.append(rid)
            raw = observed[rid]
            _clean_coordinates(row, _record_coordinates(raw))
            try:
                ordinal = int(row["_row_id"])
            except (TypeError, ValueError) as exc:
                raise ValueError("cleaned row ordinal is invalid") from exc
            _check(ordinal >= 0 and str(ordinal) == row["_row_id"],
                   "cleaned row ordinal must be exact nonnegative integer")
            cleaned_ordinals.append(ordinal)

            if optional_dataset_column_present:
                _check(row["datasetKey"].lower() == raw["datasetKey"].lower(),
                       "cleaned datasetKey differs from original GBIF record")
            if optional_license_column_present:
                _check(row["license"] == raw["license"],
                       "cleaned source license differs from original GBIF record")
            for field in ("scientificName", "eventDate", "basisOfRecord", "countryCode"):
                if field in headers:
                    _check(row[field] == str(raw.get(field) or ""),
                           "cleaned source identity metadata differs from raw GBIF")
            touched_datasets[raw["datasetKey"].lower()] += 1
            touched_licenses[raw["license"]] += 1

        _check(len(set(cleaned_ids)) == len(cleaned_ids),
               "duplicate GBIF record in cleaned used-row CSV")
        _check(len(set(cleaned_ordinals)) == len(cleaned_ordinals),
               "duplicate cleaned source row ordinal")
        _check(set(cleaned_ids) == used_set and len(cleaned_ids) == len(used),
               "cleaned used-row IDs do not exactly match frozen private used-ID list")
        original_used_datasets = attribution.get(
            "dataset_key_counts_analysis_used_if_supplied"
        )
        _check(original_used_datasets == dict(sorted(touched_datasets.items())),
               "source contributor attribution differs from cleaned used rows")

    output = {
        "schema_version": SCHEMA,
        "status": STATUS,
        "purpose": source.PURPOSE,
        "source_private_zip_sha256": source_report["private_archive_sha256"],
        "source_public_receipt_sha256": hashlib.sha256(
            _safe_original_bytes(Path(source_receipt_path), 2_000_000)
        ).hexdigest(),
        "cleaned_used_row_csv_sha256": hashlib.sha256(raw_cleaned).hexdigest(),
        "source_records_fetched": source_report["source_records_fetched"],
        "source_unique_gbif_ids_fetched": source_report["unique_gbif_ids_fetched"],
        "cleaned_and_frozen_used_record_count": len(cleaned_ids),
        "unique_source_datasets_for_used_records": len(touched_datasets),
        "unique_source_license_categories_for_used_records": len(touched_licenses),
        "all_cleaned_gbif_ids_match_frozen_used_id_set": True,
        "all_cleaned_coordinates_match_frozen_raw_records": True,
        "cleaned_dataset_keys_checked_if_present": optional_dataset_column_present,
        "cleaned_license_fields_checked_if_present": optional_license_column_present,
        "raw_source_zip_and_member_sha_verified": True,
        "public_receipt_contains_gbif_ids_taxa_or_locations": False,
        "private_used_id_list_required_for_bridge": True,
        "provider_response_origin_independently_authenticated": False,
        "frozen_used_ids_independently_attested_pre_outcome": False,
        "historical_2026_august_original_gbif_input_recovered": False,
        "gbif_derived_dataset_doi_registered": False,
        "new_biological_confirmation_performed": False,
        "immutable_survey_input_history_authenticated": False,
    }
    output_path = Path(public_receipt_path)
    _check(output_path.suffix == ".json" and output_path.parent.is_dir()
           and not output_path.exists(),
           "public coordinate-free receipt must use a new JSON path")
    with output_path.open("x", encoding="utf-8") as handle:
        handle.write(source._canonical(output).decode("utf-8"))
    return output


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-private-zip", type=Path, required=True)
    p.add_argument("--source-receipt", type=Path, required=True)
    p.add_argument("--cleaned-used-csv", type=Path, required=True)
    p.add_argument("--public-receipt", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(
        bridge(args.source_private_zip, args.source_receipt,
               args.cleaned_used_csv, args.public_receipt),
        sort_keys=True, indent=2,
    ))


if __name__ == "__main__":
    main()
