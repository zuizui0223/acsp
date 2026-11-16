#!/usr/bin/env python3
"""Verify a post-hoc, coordinate-free three-run GSI replay ledger.

This checks internal coherence against the original frozen PR247 patch receipt.
With --logs-root it additionally compares each recorded digest to the supplied
original GitHub job logs. It never authenticates the provenance of supplied
logs or recovers private source DEM bytes. No biological outcomes are read.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "validation" / "cirsium_gsi_three_run_log_ledger_20261116.json"
FROZEN = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
RUNS = (37647225829, 37705751756, 37726204623)
STAGES = (
    "private_grid_sha256",
    "terrain_feature_digest_sha256",
    "private_gsi_frame_sha256",
    "source_state_digest_sha256",
    "private_structural_order_sha256",
    "private_patch_sha256",
)
EXPECTED_JOB_IDS = {
    "37647225829": {"CIR02": 112881046241, "CIR06": 112881046494, "CIR12": 112881046402, "CIR13": 112881046755},
    "37705751756": {"CIR02": 113079588230, "CIR06": 113079588295, "CIR12": 113079588079, "CIR13": 113079588247},
    "37726204623": {"CIR02": 113144829922, "CIR06": 113144830101, "CIR12": 113144830083, "CIR13": 113144830064},
}


def read_json(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _hex_sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def extract_logged_hashes(log: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in STAGES:
        pattern = r'"' + re.escape(field) + r'"\\s*:\\s*"([0-9a-f]{64})"'
        matches = re.findall(pattern, log)
        if not matches:
            raise ValueError("missing logged digest " + field)
        result[field] = matches[-1]
    return result


def verify(ledger: dict, frozen: dict, logs_root: Path | None = None) -> dict:
    if ledger.get("schema_version") != "cirsium-gsi-three-run-stage-replay-log-ledger-v1":
        raise ValueError("ledger schema mismatch")
    if ledger.get("status") != "POSTHOC_COORDINATE_FREE_HISTORICAL_LOG_DIAGNOSTIC":
        raise ValueError("ledger cannot claim preregistration")
    if ledger.get("frozen_source_run") != RUNS[0] or frozen.get("source_workflow_run") != RUNS[0]:
        raise ValueError("original frozen source run mismatch")
    if frozen.get("status") != "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED":
        raise ValueError("frozen patch result status mismatch")
    if ledger.get("units") != list(UNITS) or set(frozen.get("units", {})) != set(UNITS):
        raise ValueError("unit identity drift")
    if [r.get("run_id") for r in ledger.get("run_order", [])] != list(RUNS):
        raise ValueError("run order altered")
    jobs = ledger.get("logged_jobs", {})
    if set(jobs) != {str(r) for r in RUNS}:
        raise ValueError("run membership drift")
    claims = ledger.get("interpretation", {})
    for flag in (
        "raw_log_bytes_archived_in_this_receipt",
        "raw_candidate_ids_or_coordinates_in_receipt",
        "field_outcomes_opened",
        "patch_byte_identity_rescues_original_full_order_mismatch",
        "field_selector_promotion_authorized",
        "cpu_dispatch_causality_established",
        "source_world_causal_mechanism_identified",
    ):
        if claims.get(flag) is not False:
            raise ValueError("claim boundary violated: " + flag)
    if claims.get("independent_biological_cohorts_added") != 0:
        raise ValueError("replay runs cannot be independent biological cohorts")

    original = jobs[str(RUNS[0])]
    counters = {
        "total_unit_jobs": 0,
        "grid_sha_matches": 0,
        "source_state_sha_matches": 0,
        "patch_sha_matches": 0,
        "gsi_sha_matches_original": 0,
        "order_sha_matches_original": 0,
        "failed_closed_jobs": 0,
    }
    per_unit = {unit: {} for unit in UNITS}
    for i, run in enumerate(RUNS):
        run_jobs = jobs[str(run)]
        if set(run_jobs) != set(UNITS):
            raise ValueError("wrong run unit set")
        success = failure = 0
        for unit in UNITS:
            row = run_jobs[unit]
            base = original[unit]
            if row.get("job_id") != EXPECTED_JOB_IDS[str(run)][unit]:
                raise ValueError("wrong historical job ID")
            if any(not _hex_sha(row.get(field)) for field in STAGES):
                raise ValueError("missing or malformed SHA")
            expected_failure = run == RUNS[2] and unit in ("CIR02", "CIR12", "CIR13")
            status = "failure" if expected_failure else "success"
            if row.get("job_conclusion") != status:
                raise ValueError("historical job conclusion changed")
            if expected_failure:
                failure += 1
            else:
                success += 1
            if i == 0:
                if row["private_structural_order_sha256"] != frozen["units"][unit]["structural_order_sha256"]:
                    raise ValueError("original full-order SHA differs from frozen PR247")
            if row["private_patch_sha256"] != frozen["units"][unit]["private_patch_sha256"]:
                raise ValueError("patch SHA differs from original frozen PR247")
            flags = {
                "grid_match": row["private_grid_sha256"] == base["private_grid_sha256"],
                "source_state_match": row["source_state_digest_sha256"] == base["source_state_digest_sha256"],
                "gsi_match": row["terrain_feature_digest_sha256"] == base["terrain_feature_digest_sha256"],
                "order_match": row["private_structural_order_sha256"] == base["private_structural_order_sha256"],
                "patch_match": row["private_patch_sha256"] == base["private_patch_sha256"],
            }
            if flags["gsi_match"] != flags["order_match"]:
                raise ValueError("GSI/order replay pattern disagrees with recorded observation")
            for stage in ("grid", "source_state", "gsi", "order", "patch"):
                key = stage + "_sha_matches" + ("_original" if stage in ("gsi", "order") else "")
                counters[key] += int(flags[stage + "_match"])
            counters["total_unit_jobs"] += 1
            counters["failed_closed_jobs"] += int(expected_failure)
            per_unit[unit][("original", "replay_249", "replay_250")[i]] = flags

            if logs_root is not None:
                logfile = logs_root / str(run) / (unit + ".log")
                raw = logfile.read_text(encoding="utf-8-sig")
                for field in STAGES:
                    pattern = r'"' + re.escape(field) + r'"\\s*:\\s*"([0-9a-f]{64})"'
                    found = re.findall(pattern, raw)
                    if not found or found[-1] != row[field]:
                        raise ValueError("supplied log hash differs: " + field)
                got_failure = "fine structural order hash differs from frozen source" in raw
                if got_failure != expected_failure:
                    raise ValueError("supplied log failure marker mismatch")
        declared = ledger["run_order"][i]
        if declared.get("job_success_count") != success or declared.get("job_failed_count") != failure:
            raise ValueError("historical job status totals differ")

    summary = ledger.get("derived_summary", {})
    if any(summary.get(k) != v for k, v in counters.items()):
        raise ValueError("summary count drift")
    if summary.get("per_unit") != per_unit:
        raise ValueError("per-unit replay flags changed")
    if counters != {
        "total_unit_jobs": 12,
        "grid_sha_matches": 12,
        "source_state_sha_matches": 12,
        "patch_sha_matches": 12,
        "gsi_sha_matches_original": 7,
        "order_sha_matches_original": 7,
        "failed_closed_jobs": 3,
    }:
        raise ValueError("historical three-run result no longer matches")
    return {
        "status": "THREE_RUN_POSTHOC_LEDGER_INTERNALLY_CONSISTENT",
        "source_log_crosscheck_performed": logs_root is not None,
        "summary": counters,
        "causal_source_of_gsi_drift_established": False,
        "field_selector_validation": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--frozen", type=Path, default=FROZEN)
    ap.add_argument("--logs-root", type=Path)
    args = ap.parse_args()
    result = verify(read_json(args.ledger), read_json(args.frozen), args.logs_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
