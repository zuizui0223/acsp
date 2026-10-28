#!/usr/bin/env python3
"""Audit original ACSP Actions ZIPs for *actual* historical GBIF fold inputs.

Only SHA-256-authenticated, preidentified 2026 archives are admissible.
This read-only scanner NEVER fetches current GBIF data or publishes GBIF
record IDs, taxon-level rows, or coordinate-bearing CSV contents.
A negative audit is bounded to the six listed artifacts; it does not
establish that no private backup or unexamined artifact exists.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

ARTIFACTS = {
    "cohort": (32335791948, 9394691112, "cc0f949649491439f91e1b90d01d48acbd3f7fffc6833a75105a3bc175a5faf3", 4),
    "prior_confirmation": (32336724090, 9395679418, "7b7bc3dd069c948bb7c63254b3e50e2822d3a8bbe51bd3a4f245dd04aad297f3", 6),
    "official_confirmation": (32337884576, 9396133154, "f23c23afe4863f816f2b3a0780d9a39d6eddb383512188a0bf572dcdf055936f", 6),
    "geographic_v1": (32574305976, 9476173948, "54ed1ccaaebc22c768fb3eb06af2cf647ac8174f07638c582e2577a58676d972", 7),
    "geographic_v2": (32613853356, 9486388476, "907b9c83e49b84e9681fa9e7561345929ba655adabd6dfce58204102edbc9313", 7),
    "geographic_v3": (32615062909, 9486693473, "92f48e8a91388d98acc152b13fe3d4ed5cb74d6454b6aa1f4f6735f7ee412ec3", 2),
}
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "acsp-original-gbif-input-artifact-inventory-20261028"
STATUSES = {
    "prior_confirmation": "confirmation-folds/pair_export_status.csv",
    "official_confirmation": "confirmation-folds/pair_export_status.csv",
    "geographic_v1": "framing-development-folds/pair_export_status.csv",
    "geographic_v2": "framing-development-v2-folds/pair_export_status.csv",
}
MANIFESTS = {key: path.replace("pair_export_status.csv", "export_manifest.json")
             for key, path in STATUSES.items()}


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _read_original_archive(path: Path, expected_sha: str, members: int):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), "original ZIP absent or symlink")
    _require(0 < path.stat().st_size < 1_000_000, "original ZIP size not expected")
    archive_bytes = path.read_bytes()
    _require(hashlib.sha256(archive_bytes).hexdigest() == expected_sha,
             "original artifact SHA256 mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
            files = z.infolist()
            names = [item.filename for item in files]
            _require(len(names) == members and len(set(names)) == members,
                     "original artifact member count/identity drift")
            _require(all(not item.is_dir() and 0 < item.file_size < 2_000_000
                         for item in files), "unexpected ZIP directory/size")
            _require(all(not name.startswith("/") and ".." not in name.split("/")
                         for name in names), "unsafe ZIP path")
            return {name: z.read(name) for name in names}
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("invalid authenticated ZIP container") from exc


def _table(payload: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))


def audit(paths: dict[str, Path]) -> dict[str, object]:
    _require(set(paths) == set(ARTIFACTS), "six original archives required, no additions")
    sources = {}
    members = {}
    for label, (run_id, artifact_id, digest, count) in ARTIFACTS.items():
        data = _read_original_archive(paths[label], digest, count)
        sources[label] = data
        members[label] = {
            "run_id": run_id,
            "artifact_id": artifact_id,
            "zip_sha256": digest,
            "member_count": len(data),
            "actual_original_training_or_heldout_csv_present": any(
                name.endswith("/training_occurrences.csv") or
                name.endswith("/held_out_occurrences.csv")
                for name in data
            ),
        }
    _require(not any(x["actual_original_training_or_heldout_csv_present"]
                     for x in members.values()),
             "an authenticated original occurrence input file was found: reclassify audit")

    # Pair export CSV bytes repeat, but raw record identity does NOT follow.
    status_sha = {
        label: hashlib.sha256(sources[label][path]).hexdigest()
        for label, path in STATUSES.items()
    }
    manifest_sha = {
        label: hashlib.sha256(sources[label][path]).hexdigest()
        for label, path in MANIFESTS.items()
    }
    _require(len(set(status_sha.values())) == len(set(manifest_sha.values())) == 1,
             "frozen export summary bytes not identical across four executions")
    _require(next(iter(status_sha.values())) ==
             "55f66ba821cba0eafdcc149f04e082e0c66ecf4a51d9456c94319e158a81b7bf",
             "frozen pair-status hash differs from original result receipt")
    _require(next(iter(manifest_sha.values())) ==
             "b9e89cb8de1969ea0531c8106d3f82750aa4791bfbf7658429855b1dd1f637fd",
             "frozen fold manifest hash differs")

    pair_statuses = _table(sources["official_confirmation"][STATUSES["official_confirmation"]])
    _require(len(pair_statuses) == 96, "original taxon-region pairs incomplete")
    status_counts = {
        "complete": sum(x["status"] == "complete" for x in pair_statuses),
        "failed_retained_as_zero": sum(x["status"] == "failed_retained_as_zero"
                                       for x in pair_statuses),
    }
    _require(status_counts == {"complete": 94, "failed_retained_as_zero": 2},
             "original 94/2 pair statuses changed")
    _require(len(_table(sources["official_confirmation"][
        "confirmation-results/confirmation_pair_results.csv"])) == 96,
        "official source pair outputs missing")
    _require(len(_table(sources["official_confirmation"][
        "confirmation-results/confirmation_fold_results.csv"])) == 1920,
        "official fold by radius outputs missing")

    # Geographic v2 has 7,895 *nonfocal genus/family reference* points.
    # Never disclose their coordinates or confuse them with original focal inputs.
    prior_points = sources["geographic_v2"][
        "framing-development-v2-results/higher_taxon_prior_points.csv"]
    with io.StringIO(prior_points.decode("utf-8-sig")) as f:
        reader = csv.DictReader(f)
        prior_fields = reader.fieldnames or []
        points_count = sum(1 for _ in reader)
    _require(prior_fields == [
        "pair_id", "_latitude", "_longitude", "scientific_name",
        "prior_rank_used", "prior_taxon_key_used",
    ] and points_count == 7895, "nonfocal prior point archive changed")
    prior_audit = _table(sources["geographic_v2"][
        "framing-development-v2-results/higher_taxon_prior_pair_audit.csv"])
    _require(len(prior_audit) == 96, "nonfocal prior audit pair count changed")
    _require(sum(x["focal_training_coordinates_used"] == "False" and
                 x["focal_heldout_coordinates_used"] == "False"
                 for x in prior_audit) == 94,
             "geographic v2 prior did not exclude focal coordinates")
    _require(all(x["focal_training_coordinates_used"] in ("", "False") and
                 x["focal_heldout_coordinates_used"] in ("", "False")
                 for x in prior_audit), "focal coordinates leaked into higher-taxon prior")

    # Geographic v3 is registry counts, not a frozen occurrence record archive.
    countries = _table(sources["geographic_v3"][
        "country_registry_v3_taxon_diagnostics.csv"])
    _require(len(countries) > 0 and
             "historical_record_count" in countries[0] and
             "historical_countries" in countries[0], "unexpected v3 registry output")
    _require("gbifID" not in countries[0] and "datasetKey" not in countries[0],
             "source record attribution unexpectedly available in v3")

    cohort = _table(sources["cohort"]["predeclared_taxon_region_pairs.csv"])
    _require(len(cohort) == 96 and
             len(sources["cohort"]) == 4, "original cohort manifest changed")

    return {
        "schema_version": SCHEMA,
        "status": "EXACT_ORIGINAL_GBIF_INPUT_RECORDS_NOT_IN_SIX_CHECKED_ARCHIVES",
        "checked_artifacts": members,
        "checked_artifact_count": len(members),
        "cross_execution_pair_export_status_sha256": next(iter(status_sha.values())),
        "cross_execution_fold_manifest_sha256": next(iter(manifest_sha.values())),
        "pair_status_summary": status_counts,
        "four_execution_status_files_byte_identical": True,
        "four_execution_fold_manifests_byte_identical": True,
        "original_confirmatory_pair_rows": 96,
        "original_confirmatory_fold_by_radius_rows": 1920,
        "geographic_v2_nonfocal_reference_point_rows": points_count,
        "geographic_v2_prior_excludes_focal_coordinates": True,
        "geographic_v3_only_countries_and_counts": True,
        "scientific_boundaries": {
            "original_GBIF_input_rows_recovered": False,
            "original_GBIF_ID_inventory_recovered": False,
            "original_datasetKey_mapping_recovered": False,
            "original_GBIF_citation_DOI_verified": False,
            "byte_identical_pair_status_proves_byte_identical_GBIF_inputs": False,
            "new_GBIF_queries_executed": False,
            "all_other_backup_locations_exhaustively_searched": False,
            "new_ecological_confirmation_or_adjustment": False,
            "protected_coordinates_in_output": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ARTIFACTS:
        parser.add_argument("--" + label.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--verify-saved", type=Path)
    args = parser.parse_args()
    files = {name: getattr(args, name) for name in ARTIFACTS}
    result = audit(files)
    if args.verify_saved is not None:
        reference = json.loads(args.verify_saved.read_text(encoding="utf-8"))
        _require(result == reference, "source-backed report differs from saved public receipt")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
