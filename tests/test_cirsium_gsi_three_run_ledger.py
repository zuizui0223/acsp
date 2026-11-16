"""Offline regressions for source-locked, three-run historical GSI diagnostic."""
from __future__ import annotations

import copy
import json

import pytest

from research.audit_cirsium_gsi_three_run_ledger import (
    FROZEN, LEDGER, RUNS, STAGES, UNITS, extract_logged_hashes, read_json, verify,
)


@pytest.fixture
def source():
    return read_json(LEDGER), read_json(FROZEN)


def test_saved_three_run_ledger_matches_original_frozen_patch_source(source):
    ledger, frozen = source
    result = verify(ledger, frozen)
    assert result["status"] == "THREE_RUN_POSTHOC_LEDGER_INTERNALLY_CONSISTENT"
    assert result["summary"]["grid_sha_matches"] == 12
    assert result["summary"]["source_state_sha_matches"] == 12
    assert result["summary"]["patch_sha_matches"] == 12
    assert result["summary"]["gsi_sha_matches_original"] == 7
    assert result["summary"]["order_sha_matches_original"] == 7
    assert result["summary"]["failed_closed_jobs"] == 3
    assert result["causal_source_of_gsi_drift_established"] is False
    assert result["source_log_crosscheck_performed"] is False


@pytest.mark.parametrize("badfield", [
    "private_grid_sha256",
    "source_state_digest_sha256",
    "private_patch_sha256",
    "terrain_feature_digest_sha256",
])
def test_detects_modified_historical_stage_sha(source, badfield):
    original, frozen = source
    ledger = copy.deepcopy(original)
    ledger["logged_jobs"][str(RUNS[-1])]["CIR02"][badfield] = "0" * 64
    with pytest.raises(ValueError):
        verify(ledger, frozen)


def test_detects_original_identity_or_denominator_source_drift(source):
    original, frozen = source
    ledger = copy.deepcopy(original)
    ledger["logged_jobs"][str(RUNS[0])]["CIR12"]["private_structural_order_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="original full-order SHA"):
        verify(ledger, frozen)


def test_rejects_mislabelled_confirmatory_biology_or_cpu_causality(source):
    original, frozen = source
    for field, value in [
        ("field_selector_promotion_authorized", True),
        ("cpu_dispatch_causality_established", True),
        ("raw_candidate_ids_or_coordinates_in_receipt", True),
        ("independent_biological_cohorts_added", 1),
    ]:
        ledger = copy.deepcopy(original)
        ledger["interpretation"][field] = value
        with pytest.raises(ValueError):
            verify(ledger, frozen)


def test_rejects_silently_reclassifying_a_failed_job(source):
    original, frozen = source
    ledger = copy.deepcopy(original)
    ledger["logged_jobs"][str(RUNS[-1])]["CIR13"]["job_conclusion"] = "success"
    with pytest.raises(ValueError, match="historical job conclusion"):
        verify(ledger, frozen)


def test_independent_log_crosscheck_works_for_all_twelve_jobs(tmp_path, source):
    ledger, frozen = source
    for run in RUNS:
        (tmp_path / str(run)).mkdir()
        for unit in UNITS:
            row = ledger["logged_jobs"][str(run)][unit]
            log = "\n".join(f'"{field}": "{row[field]}"' for field in STAGES)
            if row["job_conclusion"] == "failure":
                log += "\nfine structural order hash differs from frozen source"
            (tmp_path / str(run) / (unit + ".log")).write_text(log + "\n", encoding="utf-8")
    result = verify(ledger, frozen, tmp_path)
    assert result["source_log_crosscheck_performed"] is True
    logfile = tmp_path / str(RUNS[-1]) / "CIR06.log"
    logfile.write_text(logfile.read_text().replace('"private_patch_sha256": "', '"private_patch_sha256": "0'), encoding="utf-8")
    with pytest.raises(ValueError, match="supplied log hash differs"):
        verify(ledger, frozen, tmp_path)


def test_extractor_fails_closed_without_all_fields(source):
    ledger, _ = source
    row = ledger["logged_jobs"][str(RUNS[0])]["CIR02"]
    log = "\n".join(f'"{field}": "{row[field]}"' for field in STAGES)
    assert extract_logged_hashes(log) == {field: row[field] for field in STAGES}
    with pytest.raises(ValueError, match="missing logged digest"):
        extract_logged_hashes('"private_grid_sha256": "' + "f" * 64 + '"')
