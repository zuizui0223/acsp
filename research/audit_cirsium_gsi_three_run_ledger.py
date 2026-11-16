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


# Exact SHA triples copied from the named, original GitHub job logs. This
# independent code-side freeze detects a changed digest even if "different
# from source" stays true in the derived summary. It is not proof that these
# GitHub logs or private DEMs have been archived as a complete raw dataset.
EXPECTED_STAGE_SHA_TRIPLES = {
    "37647225829": {
        "CIR02": ("931300eae97dc777f3391f28345493d9209110b8c3e9ca257bf65b8c66dc0127", "27eebb7c4cdf4a2826cbc1b750388f5846bf2376516df67cd21828d163f17a94", "8d5693e2fdc39b7474e76b39fb94a1758c49768d77c013fbe8536f88cc7118f4"),
        "CIR06": ("6a85cc71206bade4e819bb7a66cdc1d50953d2cd98a1744ef099dcca73619a42", "06920f34f4cc6e7ee22e7b6d61be88db992cb57099e35feeedf5bb7725bbb23d", "1d974681d6586fbe3b99cd26ecddf98bd53fe734c0c26d31c461b7cfdd25bd26"),
        "CIR12": ("b7cf4328af2ad10da1c591ca6d9cdd94dd8ebe13d68cc4f65b89a3c442ded907", "77121ef910780434b6a9a04d642f170a707721025c40ea6a6ef9c973cc7c2818", "47273b8f0261726f61b4d7e3a1b110c961195645db5ce1531515c0976f0b62d7"),
        "CIR13": ("105e3c7164d20d346488bdd2cd34f6d7fdcb8eb1b293358f1094b00148e6290c", "4696647fd4066e66cefe8991b91c0d8960cb8a991ed8452fe1a1834e2fabc2e2", "394b36742dc2b7cf5078ffa8244eae799fefeb89f5b0ef3df73586d89275d38b"),
    },
    "37705751756": {
        "CIR02": ("931300eae97dc777f3391f28345493d9209110b8c3e9ca257bf65b8c66dc0127", "27eebb7c4cdf4a2826cbc1b750388f5846bf2376516df67cd21828d163f17a94", "8d5693e2fdc39b7474e76b39fb94a1758c49768d77c013fbe8536f88cc7118f4"),
        "CIR06": ("876b877c5784d8d6f1707b4ae5546505d222d4990c147cbb0b84c1b8cd815870", "194208d1f921d212d450c11575a54a068322ee1ab646099e22da701a956aacfb", "94438a45c4ca25a9d6a136b88b3f9a9dd4dadd90c37f2cd7b25c32f8522400f9"),
        "CIR12": ("b7cf4328af2ad10da1c591ca6d9cdd94dd8ebe13d68cc4f65b89a3c442ded907", "77121ef910780434b6a9a04d642f170a707721025c40ea6a6ef9c973cc7c2818", "47273b8f0261726f61b4d7e3a1b110c961195645db5ce1531515c0976f0b62d7"),
        "CIR13": ("3e305121983267ba3265750ad2c06d29bb2a0c370c2f2025cd20320acf3198bc", "99070dd322d7421d85410a8a9c361b232a7cbcf8bbc17929c5ea18580ea6f75c", "c29bf7e40182afda68df73719a509d26fa7bfd7bd25707771880b1ba4b0f796d"),
    },
    "37726204623": {
        "CIR02": ("e2ae43320f586323ebded54955b8cec1e43a35e3e0cd70313334b6e99848aa49", "46fe181d7cd182b83b139b85cf676df947bf960399074d578ea259e1f98ef8e3", "2d1bd9554b7aea9a7bd54bdb7e91ead5e40f813b9100f71aa061546777cd9b2b"),
        "CIR06": ("6a85cc71206bade4e819bb7a66cdc1d50953d2cd98a1744ef099dcca73619a42", "06920f34f4cc6e7ee22e7b6d61be88db992cb57099e35feeedf5bb7725bbb23d", "1d974681d6586fbe3b99cd26ecddf98bd53fe734c0c26d31c461b7cfdd25bd26"),
        "CIR12": ("14190d958f738beddecfd6ac545c61ab8e2360da24c7509e1216882a2bbb63a9", "0f64d5a742ede1bea530872c40d4a7772fbd85d89e8c363576f7120a3e6a62cb", "20ac1ea9aee35bb34b88a467423f7f72d575558186c44e4e03dbfe2532eb9f6b"),
        "CIR13": ("3e305121983267ba3265750ad2c06d29bb2a0c370c2f2025cd20320acf3198bc", "99070dd322d7421d85410a8a9c361b232a7cbcf8bbc17929c5ea18580ea6f75c", "c29bf7e40182afda68df73719a509d26fa7bfd7bd25707771880b1ba4b0f796d"),
    },
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
        pattern = r'"' + re.escape(field) + r'"\s*:\s*"([0-9a-f]{64})"'
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
            expected_stages = EXPECTED_STAGE_SHA_TRIPLES[str(run)][unit]
            actual_stages = (
                row["terrain_feature_digest_sha256"],
                row["private_gsi_frame_sha256"],
                row["private_structural_order_sha256"],
            )
            if i == 0:
                if row["private_structural_order_sha256"] != frozen["units"][unit]["structural_order_sha256"]:
                    raise ValueError("original full-order SHA differs from frozen PR247")
            if actual_stages != expected_stages:
                raise ValueError("historical stage SHA does not match original job-log record")
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
                    pattern = r'"' + re.escape(field) + r'"\s*:\s*"([0-9a-f]{64})"'
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
