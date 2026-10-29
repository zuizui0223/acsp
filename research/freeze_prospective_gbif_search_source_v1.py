#!/usr/bin/env python3
"""Freeze caller-supplied GBIF Search API pages for a NEW ACSP cohort only.

Offline, read-only ingestion of raw GBIF JSON responses with request metadata.
Captures exact bytes, GBIF record IDs, datasetKey attribution and optional
pre-outcome analysis-used IDs in a PRIVATE ZIP. A PUBLIC JSON receipt contains
only aggregate counts/hashes. Does not authenticate the time/provider of
caller-supplied data, mint a GBIF DOI, or restore August 2026 original inputs.
Never change the validated 2.5% / float32 / 1 km ACSP method here.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "acsp-new-prospective-gbif-search-capture-v1"
PURPOSE = "new-independent-cohort-only-not-2026-08-20"
RECEIPT_SCHEMA = "acsp-new-prospective-gbif-source-receipt-v1"
DATASET_KEY = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
POSITIVE_ID = re.compile(r"^[1-9][0-9]*$")
MAX_MANIFEST_BYTES = 2_000_000
MAX_PAGE_BYTES = 4_000_000
MAX_PAGES = 512


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read(path: Path, max_bytes: int) -> bytes:
    _require(path.is_file() and not path.is_symlink(),
             "source must be an existing, non-symlinked file")
    _require(0 < path.stat().st_size <= max_bytes, "source byte size is outside the cap")
    return path.read_bytes()


def _record_id(value: object) -> str:
    _require((isinstance(value, (str, int)) and not isinstance(value, bool)),
             "GBIF record ID must be an exact integer or decimal string")
    result = str(value)
    _require(bool(POSITIVE_ID.fullmatch(result)),
             "GBIF record ID missing or not an exact positive integer")
    return result


def _validate_query(query: dict[str, object]) -> None:
    _require(isinstance(query, dict), "missing original GBIF request parameters")
    k = query.get("taxonKey")
    _require(type(k) is int and k > 0, "taxonKey must be an integer")
    limit, offset = query.get("limit"), query.get("offset")
    _require(type(limit) is int and 1 <= limit <= 300, "request limit must be 1-300")
    _require(type(offset) is int and offset == 0,
             "only explicit first-page, capped prospective search is supported")
    _require(str(query.get("hasCoordinate")).lower() == "true"
             and str(query.get("hasGeospatialIssue")).lower() == "false"
             and query.get("occurrenceStatus") == "PRESENT",
             "mandatory original GBIF coordinate/quality/presence filters missing")
    has_geometry = isinstance(query.get("geometry"), str) and bool(query["geometry"].strip())
    has_country = isinstance(query.get("country"), str) and bool(
        re.fullmatch(r"[A-Z]{2}", str(query["country"])))
    _require(has_geometry != has_country, "require exactly one geographic frame")
    _require(all(isinstance(key, str) and key.strip()
                 and isinstance(value, (str, int, bool)) for key, value in query.items()),
             "original GBIF search query contains an unsupported parameter")


def _validate_manifest(payload: object) -> dict[str, object]:
    _require(isinstance(payload, dict), "capture manifest must be JSON object")
    _require(payload.get("schema_version") == SCHEMA, "wrong prospective capture schema")
    _require(payload.get("purpose") == PURPOSE,
             "historical 2026-08-20 original confirmation must never be relabeled")
    fingerprint = payload.get("frozen_protocol_sha256")
    _require(isinstance(fingerprint, str) and bool(SHA256.fullmatch(fingerprint)),
             "new-cohort protocol SHA-256 is missing")
    stamp = payload.get("capture_time_declared_utc")
    _require(isinstance(stamp, str) and stamp.endswith("Z"),
             "capture time must be declared UTC ISO-8601")
    try:
        dt = datetime.fromisoformat(stamp[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid declared UTC capture time") from exc
    _require(dt.tzinfo == timezone.utc
             and dt >= datetime(2026, 9, 1, tzinfo=timezone.utc),
             "declared capture time cannot represent historical August 2026 inputs")
    pages = payload.get("pages")
    _require(isinstance(pages, list) and 1 <= len(pages) <= MAX_PAGES,
             "capture must provide a finite set of source pages")
    labels: set[str] = set()
    queries: set[str] = set()
    for page in pages:
        _require(isinstance(page, dict) and set(page) == {"path", "query"},
                 "each page must contain exact path and request query")
        name = page["path"]
        _require(isinstance(name, str) and name.endswith(".json")
                 and PurePosixPath(name).as_posix() == name
                 and not name.startswith("/") and "\\" not in name
                 and len(PurePosixPath(name).parts) == 1
                 and name not in (".", ".."),
                 "page path must be a safe flat JSON basename")
        _require(name not in labels, "duplicate response page file")
        labels.add(name)
        _validate_query(page["query"])
        query_code = _sha(_canonical(page["query"]))
        _require(query_code not in queries,
                 "duplicate GBIF search request (first-page cap); no refetch substitution")
        queries.add(query_code)
    return payload


def _response_records(content: bytes, query: dict[str, object]) -> list[dict[str, object]]:
    try:
        data = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("raw GBIF response is not JSON") from exc
    _require(isinstance(data, dict) and isinstance(data.get("results"), list),
             "GBIF response must contain results array")
    _require(type(data.get("offset")) is int and data["offset"] == query["offset"]
             and type(data.get("limit")) is int and data["limit"] == query["limit"],
             "response offset or limit does not match immutable request")
    _require(type(data.get("count")) is int and data["count"] >= len(data["results"])
             and type(data.get("endOfRecords")) is bool,
             "GBIF response count/endOfRecords invalid")
    _require(len(data["results"]) <= query["limit"], "more GBIF records than requested")
    _require(data["results"] or data["count"] == 0,
             "nonempty GBIF result count with empty capped first page")
    for record in data["results"]:
        _require(isinstance(record, dict), "raw GBIF record must be an object")
    return data["results"]


def _used_ids(path: Path | None, available: set[str]) -> tuple[set[str], bytes | None]:
    if path is None:
        return set(), None
    raw = _read(Path(path), 4_000_000)
    try:
        ids = [line.strip() for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    except UnicodeDecodeError as exc:
        raise ValueError("analysis-used IDs file must be UTF-8") from exc
    _require(bool(ids) and len(ids) == len(set(ids)),
             "analysis-used ID file is empty or duplicates record IDs")
    ids_set = {_record_id(x) for x in ids}
    _require(ids_set <= available, "analysis-used IDs include records not in frozen raw source")
    return ids_set, raw


def _zip_add(z: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    z.writestr(info, content)


def freeze(
    manifest_path: Path,
    private_archive_path: Path,
    public_receipt_path: Path,
    used_ids_path: Path | None = None,
) -> dict[str, object]:
    """Freeze caller-supplied bytes; do not run GBIF live Search or infer original dates."""
    manifest_path = Path(manifest_path)
    raw_manifest = _read(manifest_path, MAX_MANIFEST_BYTES)
    manifest = _validate_manifest(json.loads(raw_manifest))
    private_archive_path = Path(private_archive_path).resolve()
    public_receipt_path = Path(public_receipt_path).resolve()
    root = ROOT.resolve()
    _require(root != private_archive_path and root not in private_archive_path.parents,
             "private source archive must be OUTSIDE the public Git checkout")
    _require(private_archive_path.suffix == ".zip"
             and public_receipt_path.suffix == ".json"
             and private_archive_path != public_receipt_path,
             "distinct private ZIP and public JSON receipt paths required")
    _require(private_archive_path.parent.is_dir() and public_receipt_path.parent.is_dir(),
             "output parent directories must already exist")
    _require(not private_archive_path.exists() and not public_receipt_path.exists(),
             "outputs must be new; never overwrite a frozen source snapshot")

    all_ids: set[str] = set()
    per_dataset: Counter[str] = Counter()
    per_license: Counter[str] = Counter()
    id_dataset: dict[str, str] = {}
    raw_pages: dict[str, bytes] = {}
    record_count = 0
    digester = hashlib.sha256(b"acsp-new-gbif-source-pages-v1\n")
    for page in manifest["pages"]:
        name = page["path"]
        query = page["query"]
        raw = _read(manifest_path.parent / name, MAX_PAGE_BYTES)
        records = _response_records(raw, query)
        digester.update(len(name.encode("utf-8")).to_bytes(4, "big"))
        digester.update(name.encode("utf-8"))
        digester.update(len(raw).to_bytes(8, "big"))
        digester.update(raw)
        raw_pages[name] = raw
        for record in records:
            rid = _record_id(record.get("gbifID", record.get("key")))
            _require(rid not in all_ids, "repeated GBIF ID across fresh raw pages")
            all_ids.add(rid)
            dataset = record.get("datasetKey")
            _require(isinstance(dataset, str) and DATASET_KEY.fullmatch(dataset),
                     "datasetKey UUID missing from a fresh raw GBIF record")
            lic = record.get("license")
            _require(isinstance(lic, str) and bool(lic.strip()),
                     "source record license missing (citation/redistribution audit incomplete)")
            lat, lon = record.get("decimalLatitude"), record.get("decimalLongitude")
            try:
                latitude, longitude = float(lat), float(lon)
            except (ValueError, TypeError) as exc:
                raise ValueError("GBIF record coordinate is absent") from exc
            _require(math.isfinite(latitude) and -90 <= latitude <= 90
                     and math.isfinite(longitude) and -180 <= longitude <= 180,
                     "GBIF record coordinate invalid")
            id_dataset[rid] = dataset.lower()
            per_dataset[dataset.lower()] += 1
            per_license[lic] += 1
            record_count += 1
    selected_ids, used_raw = _used_ids(used_ids_path, all_ids)
    used_datasets = Counter(id_dataset[rid] for rid in selected_ids)
    private_attribution = {
        "schema_version": SCHEMA,
        "status": "CALLER_SUPPLIED_PAGES_NOT_PROVIDER_ATTESTED",
        "original_raw_record_count": record_count,
        "gbif_record_ids_unique_count": len(all_ids),
        "dataset_key_counts_fetched_not_necessarily_used": dict(sorted(per_dataset.items())),
        "license_counts_fetched": dict(sorted(per_license.items())),
        "analysis_used_record_ids_provided": used_raw is not None,
        "analysis_used_record_count": len(selected_ids),
        "dataset_key_counts_analysis_used_if_supplied": dict(sorted(used_datasets.items())),
        "historical_2026_08_20_input_authenticated": False,
        "GBIF_derived_dataset_DOI_registered": False,
    }
    source_members = {
        "capture_manifest.json": raw_manifest,
        **{"raw_pages/" + key: value for key, value in raw_pages.items()},
        "private_attribution.json": _canonical(private_attribution),
    }
    if used_raw is not None:
        source_members["analysis_used_gbif_ids.txt"] = used_raw
    source_members["private_source_digests.json"] = _canonical({
        name: _sha(content) for name, content in sorted(source_members.items())
    })
    with zipfile.ZipFile(private_archive_path, mode="x") as z:
        for name, content in sorted(source_members.items()):
            _zip_add(z, name, content)
    archive_hash = _sha(private_archive_path.read_bytes())
    public = {
        "schema_version": RECEIPT_SCHEMA,
        "purpose": PURPOSE,
        "status": "NEW_COHORT_RAW_SOURCE_SNAPSHOTTED_NOT_ORIGIN_ATTESTED",
        "declared_capture_time_utc_not_provider_verified": manifest["capture_time_declared_utc"],
        "frozen_new_cohort_protocol_sha256": manifest["frozen_protocol_sha256"],
        "private_archive_sha256": archive_hash,
        "original_manifest_sha256": _sha(raw_manifest),
        "all_original_page_bytes_sequence_sha256": digester.hexdigest(),
        "pages_captured": len(raw_pages),
        "source_records_fetched": record_count,
        "unique_gbif_ids_fetched": len(all_ids),
        "source_dataset_keys_count": len(per_dataset),
        "source_license_categories_count": len(per_license),
        "explicit_analysis_used_id_set_archived_privately": used_raw is not None,
        "analysis_used_id_count_if_supplied": len(selected_ids),
        "source_dataset_keys_for_used_ids_count_if_supplied": len(used_datasets),
        "exact_analysis_used_record_set_not_confirmed_without_ids": used_raw is None,
        "original_2026_august_96pair_source_recovered": False,
        "provider_response_origin_independently_authenticated": False,
        "gbif_derived_dataset_doi_issued": False,
        "persistent_private_or_public_data_url_verified": False,
        "archive_contains_sensitive_coordinates_and_ids_DO_NOT_UPLOAD": True,
        "public_receipt_contains_row_ids_locations_or_dataset_key_list": False,
        "new_biological_validation_performed": False,
    }
    with public_receipt_path.open("x", encoding="utf-8") as handle:
        handle.write(_canonical(public).decode("utf-8"))
    return public


def verify_archive(private_archive_path: Path, public_receipt_path: Path) -> dict:
    receipt = json.loads(_read(Path(public_receipt_path), 2_000_000))
    _require(receipt["schema_version"] == RECEIPT_SCHEMA, "wrong public receipt schema")
    _require(_sha(_read(Path(private_archive_path), 2_000_000_000)) ==
             receipt["private_archive_sha256"], "private ZIP hash mismatch")
    with zipfile.ZipFile(private_archive_path) as z:
        names = z.namelist()
        _require(len(names) == len(set(names)) and "private_source_digests.json" in names,
                 "private archive member collision/missing digests")
        hashes = json.loads(z.read("private_source_digests.json"))
        _require(set(hashes) == set(names) - {"private_source_digests.json"},
                 "private archive members do not match frozen digest inventory")
        for name, expected in hashes.items():
            _require(_sha(z.read(name)) == expected, "private raw-page source changed")
        _require(_sha(z.read("capture_manifest.json")) ==
                 receipt["original_manifest_sha256"], "original capture manifest changed")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Caller-supplied manifest beside private GBIF raw JSON pages")
    parser.add_argument("--private-archive", type=Path, required=True,
                        help="Private .zip OUTSIDE the public repository")
    parser.add_argument("--public-receipt", type=Path, required=True,
                        help="Coordinate-free source receipt JSON")
    parser.add_argument("--used-gbif-ids", type=Path,
                        help="Optional PRIVATE exact analysis-used GBIF ID list")
    args = parser.parse_args()
    result = freeze(args.manifest, args.private_archive, args.public_receipt,
                    args.used_gbif_ids)
    verify_archive(args.private_archive, args.public_receipt)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
