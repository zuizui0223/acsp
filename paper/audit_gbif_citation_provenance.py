#!/usr/bin/env python3
"""Offline, fail-closed audit of GBIF provenance for the frozen ACSP paper.

This never fetches GBIF, substitutes new records, opens field outcomes,
exposes private coordinates, or invents a dataset/Zenodo DOI. A passing
audit documents a known citation gap; it does NOT certify submission readiness.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FROZEN_BLOBS = {
    "research/benchmark_general_random_taxa_regions.py": "91cf10f1677d80b48758c232380d653c93070d93",
    "research/export_robust_patch_confirmation_folds_v2.py": "52ced202c7e23e708c5fb9f0e0c982c421664ae3",
    "gbif_fieldmap_builder_app.py": "a0aaf197c1697919c4b5f32f6e0955742c679cd3",
    ".github/workflows/robust-patch-untouched-confirmation-v2.yml": "377c05a971858de5328614d83f5fc4a14a34866c",
    "validation/acsp_robust_patch_untouched_confirmation_execution_v2.json": "f9ecfbe3cae46c34c956b021265abb85f7b7e440",
    "paper/generated/table_1_robust_patch_confirmation.csv": "87de7566c752351e185d1a5d3095005e9a7bf9e1",
    "CITATION.cff": "f97ab5a97811659e665b9f11c339989719ee96cb",
}
MANUSCRIPT = "paper/MANUSCRIPT_ROBUST_PATCH_DRAFT.md"
DOC = "paper/GBIF_CITATION_AND_INPUT_PROVENANCE.md"
SEARCH_ENDPOINT = "https://api.gbif.org/v1/occurrence/search"
RELEASE_BASELINE = "6f5628f05415d2308c040954e8f312ef2bf0a2bc"


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _source_git_blob(path: Path) -> str:
    value = path.read_bytes()
    return hashlib.sha1(f"blob {len(value)}\0".encode("ascii") + value).hexdigest()


def _read_bound_sources(root: Path) -> dict[str, str]:
    """Exact Git blob checks prevent incidental current/main source drift."""
    sources: dict[str, str] = {}
    for path, sha in FROZEN_BLOBS.items():
        p = root / path
        _require(p.is_file() and not p.is_symlink(), f"missing or symlinked frozen source: {path}")
        _require(_source_git_blob(p) == sha, f"source Git blob drift: {path}")
        sources[path] = p.read_text(encoding="utf-8")
    return sources


def _func_source(text: str, name: str) -> str:
    lines = text.splitlines()
    first = next((i for i, x in enumerate(lines) if x.startswith(f"def {name}(")), None)
    _require(first is not None, f"missing source function: {name}")
    after = next((i for i in range(first + 1, len(lines))
                  if lines[i].startswith(("def ", "class ", "@"))), len(lines))
    return "\n".join(lines[first:after])


def _declared_upload_paths(yaml_source: str) -> list[str]:
    marker = "name: acsp-robust-patch-untouched-confirmation-v2-results"
    _require(yaml_source.count(marker) == 1, "named original result archive changed")
    tail = yaml_source.split(marker, 1)[1]
    _require("path: |" in tail, "missing declared result upload block")
    after = tail.split("path: |", 1)[1]
    rows: list[str] = []
    for line in after.splitlines()[1:]:
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) < 12:
            break
        rows.append(line.strip())
    _require(rows == ["confirmation-folds/export_manifest.json",
                      "confirmation-folds/pair_export_status.csv",
                      "confirmation-results"], "declared upload paths changed")
    return rows


def audit(root: Path = ROOT) -> dict[str, object]:
    sources = _read_bound_sources(root)
    execution = json.loads(sources["validation/acsp_robust_patch_untouched_confirmation_execution_v2.json"])
    pair_count = execution["cohort_artifact"]["declared_pairs"]
    folds = execution["fold_generation"]["repeats"] * pair_count
    fetch_cap = execution["occurrence_fetch"]["records_per_pair"]
    _require((pair_count, folds, fetch_cap) == (96, 480, 150), "frozen cohort/fetch denominator drift")
    cohort = execution["cohort_artifact"]
    _require(cohort["workflow_run_id"] == 32335791948 and cohort["artifact_id"] == 9394691112,
             "frozen taxon-identity cohort provenance drift")
    _require(bool(re.fullmatch(r"[a-f0-9]{64}", cohort["sha256"])), "invalid frozen cohort checksum")

    benchmark = sources["research/benchmark_general_random_taxa_regions.py"]
    _require(f'GBIF_SEARCH = "{SEARCH_ENDPOINT}"' in benchmark, "GBIF search endpoint drift")
    fetch = _func_source(benchmark, "fetch_occurrences")
    _require('get_json(GBIF_SEARCH' in fetch and '"offset": 0' in fetch
             and '"taxonKey"' in fetch and '"geometry"' in fetch
             and 'gbif_record_to_species_row(record)' in fetch,
             "frozen live GBIF search and conversion semantics drift")
    _require('"limit": min(300, int(cap))' in fetch, "frozen occurrence cap drift")

    exporter = sources["research/export_robust_patch_confirmation_folds_v2.py"]
    _require("from benchmark_general_random_taxa_regions import fetch_occurrences" in exporter,
             "frozen export no longer uses GBIF search")
    _require('training.to_csv(fold_dir / "training_occurrences.csv"' in exporter
             and 'heldout.to_csv(fold_dir / "held_out_occurrences.csv"' in exporter,
             "historical per-fold input handling drift")
    _require('occurrences = fetch_occurrences(row, records_per_pair)' in exporter,
             "frozen input call drift")

    app = sources["gbif_fieldmap_builder_app.py"]
    converter = _func_source(app, "gbif_record_to_species_row")
    cleaner = _func_source(app, "clean_occurrences")
    _require('"gbifID": rec.get("gbifID") or rec.get("key")' in converter,
             "original GBIF record ID not transferred in source")
    _require('"datasetKey"' not in converter, "original datasetKey conversion contract changed")
    _require('out["_gbif_id"]' in cleaner, "cleaned GBIF ID convention changed")

    paths = _declared_upload_paths(
        sources[".github/workflows/robust-patch-untouched-confirmation-v2.yml"]
    )
    _require("confirmation-folds" not in paths
             and not any(x.startswith("confirmation-folds/pair_") for x in paths),
             "original raw fold input now appears in declared upload")
    with (root / "paper/generated/table_1_robust_patch_confirmation.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    _require(len(rows) == 1 and rows[0]["declared_taxon_region_pairs"] == "96"
             and rows[0]["declared_folds"] == "480"
             and rows[0]["confirmation_status"] == "untouched_confirmation_passed",
             "primary frozen paper result changed")

    cff = sources["CITATION.cff"]
    _require('name: "ACSP Developers"' in cff, "software citation authorship source drift")
    _require(re.search(r"(?m)^doi\s*:", cff) is None, "CITATION.cff now declares a DOI: re-audit")
    manuscript = (root / MANUSCRIPT).read_text(encoding="utf-8")
    _require("## Data and code availability" in manuscript, "missing source availability section")
    _require("GBIF Occurrence Search API" in manuscript, "missing corrected GBIF input disclosure")
    _require("not included in the declared GitHub Actions result upload" in manuscript,
             "original raw-input archive omission is no longer disclosed")
    _require("No GBIF download DOI has been verified for this exact frozen input" in manuscript,
             "unverified original GBIF citation silently changed")
    _require("## Author contributions" in manuscript, "original paper structure changed")
    _require((root / DOC).is_file(), "missing bounded audit note")

    return {
        "status": "ORIGINAL_INPUT_CITATION_NOT_YET_RECOVERED",
        "scope": "Japan 96 taxon-region pairs / 480 declared spatial folds",
        "original_input_method": "GBIF_OCCURRENCE_SEARCH_API",
        "original_api_url": SEARCH_ENDPOINT,
        "frozen_automatic_GBIF_download_DOI_generated": False,
        "frozen_GBIF_download_DOI_verified": False,
        "unique_exact_frozen_GBIF_record_ids_archived_in_declared_result_upload": False,
        "original_datasetKey_transferred_by_record_converter": False,
        "original_gbifID_transferred_to_temporary_fold_rows": True,
        "raw_fold_occurrence_csv_in_declared_upload": False,
        "raw_folds_could_exist_outside_checked_repository": True,
        "frozen_cohort_identity_artifact": {
            "workflow_run_id": cohort["workflow_run_id"],
            "artifact_id": cohort["artifact_id"],
            "sha256": cohort["sha256"],
        },
        "original_declared_result_upload_paths": paths,
        "counts": {
            "declared_taxon_region_pairs": pair_count,
            "declared_spatial_folds": folds,
            "maximum_search_records_per_pair": fetch_cap,
        },
        "frozen_source_git_blobs": dict(sorted(FROZEN_BLOBS.items())),
        "frozen_software_commit_before_audit": RELEASE_BASELINE,
        "zenodo_release_DOI_verified": False,
        "journal_submission_ready": False,
        "new_GBIF_download_replaces_historic_input": False,
        "retuned_historic_confirmation": False,
        "protected_occurrence_coordinates_exported": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
