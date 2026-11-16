#!/usr/bin/env python3
"""Read-only, coordinate-free forensic comparison of three historical GSI runs.

This is a post-observation source-integrity audit, NOT an independent
ecological confirmation, a numerical-causality test or a field selector.
Input GitHub Actions logs are private/local and are never republished.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_PATCH_RECEIPT = ROOT / "validation" / (
    "coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
)
RUNS = {
    "original_247": (37647225829, {
        "CIR02": 112881046241, "CIR06": 112881046494,
        "CIR12": 112881046402, "CIR13": 112881046755,
    }),
    "replay_249": (37705751756, {
        "CIR02": 113079588230, "CIR06": 113079588295,
        "CIR12": 113079588079, "CIR13": 113079588247,
    }),
    "strict_audit_250": (37726204623, {
        "CIR02": 113144829922, "CIR06": 113144830101,
        "CIR12": 113144830083, "CIR13": 113144830064,
    }),
}
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
SCHEMAS = {
    "grid": "cirsium-fresh-sentinel-v2-primary-fine-grid-unit-v1",
    "gsi": "cirsium-fresh-sentinel-v2-fixed-gsi-terrain-result-v1",
    "structural": "cirsium-fresh-sentinel-v2-fine-structural-order-result-v1",
    "patch": "cirsium-fresh-sentinel-v2-fine-patch-transfer-result-v1",
}
EXPECTED_STATUSES = {
    "grid": "PRIMARY_2KM_100M_FINE_GRID_MATERIALIZED_PRE_OUTCOME",
    "gsi": "FIXED_GSI_TERRAIN_ATTACHED_PRE_OUTCOME",
    "structural": "FINE_STRUCTURAL_FULL_ORDER_BUILT_PRE_OUTCOME",
    "patch": "FINE_PATCH_TRANSFER_REPRESENTATION_FEASIBILITY_COMPLETE",
}
TIMESTAMP = re.compile(r"^\ufeff?\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d:\d\d\.\d+Z ?", re.M)
BLOCK_START = re.compile(r'\{\s*"schema_version"\s*:')
HEX64 = re.compile(r"^[a-f0-9]{64}$")
FAIL_TEXT = "fine structural order hash differs from frozen source"


def _objects(log_text: str) -> dict[str, dict[str, Any]]:
    # GitHub prefixes each stdout line with its own timestamp. Only parse
    # complete JSON objects with a known schema; never retain raw log text.
    cleaned = TIMESTAMP.sub("", log_text.lstrip("\ufeff"))
    decoder = json.JSONDecoder()
    objects: dict[str, dict[str, Any]] = {}
    for match in BLOCK_START.finditer(cleaned):
        try:
            value, _ = decoder.raw_decode(cleaned, match.start())
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        for section, schema in SCHEMAS.items():
            if value.get("schema_version") != schema:
                continue
            if section in objects:
                raise ValueError("duplicate source JSON object: " + section)
            if value.get("status") != EXPECTED_STATUSES[section]:
                raise ValueError("unexpected source status: " + section)
            if value.get("field_outcomes_opened") is not False:
                raise ValueError("field-outcome gate not confirmed: " + section)
            objects[section] = value
    if set(objects) != set(SCHEMAS):
        raise ValueError("missing complete source stage: " + str(sorted(set(SCHEMAS) - set(objects))))
    return objects


def _sha(value: Any, what: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise ValueError("missing or invalid SHA256: " + what)
    return value


def _integer(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid count: " + what)
    return value


def _signature(stage: dict[str, dict[str, Any]], unit: str, frozen: Mapping[str, Any]) -> dict[str, Any]:
    grid, gsi, structural, patch = (stage[s] for s in SCHEMAS)
    if any(obj.get("cohort_unit_id") != unit for obj in stage.values()):
        raise ValueError("unit identity drift " + unit)
    candidates = _integer(grid.get("fine_grid_cell_count"), "grid cells")
    complete = _integer(gsi.get("source_complete_rows"), "GSI complete")
    not_found = _integer(gsi.get("provider_unavailable_rows"), "GSI provider unavailable")
    not_vector = _integer(gsi.get("terrain_vector_unavailable_rows"), "GSI vector unavailable")
    if candidates != complete + not_found + not_vector:
        raise ValueError("GSI denominator not preserved " + unit)
    if candidates != gsi.get("candidate_rows") or candidates != structural.get("candidate_rows"):
        raise ValueError("candidate count changed " + unit)
    if any((
        candidates != frozen["fine_grid_candidate_count"],
        complete != frozen["gsi_source_complete_count"],
        structural.get("source_complete_rows") != frozen["structural_source_complete_count"],
        patch.get("source_complete_structural_order_rows") != frozen["structural_source_complete_count"],
        patch.get("retained_support_cell_count") != frozen["transferred_2p5pct_retained_cell_count"],
        patch.get("patch_count") != frozen["complete_link_patch_count"],
    )):
        raise ValueError("frozen source or patch denominator drift " + unit)
    if patch.get("support_fraction") != 0.025 or patch.get("patch_merge_distance_m") != 1000.0:
        raise ValueError("frozen 2.5%/1-km rule drift " + unit)
    chunk_count = _integer(gsi.get("chunk_count"), "chunk count")
    chunks = gsi.get("chunk_audits")
    if not isinstance(chunks, list) or len(chunks) != chunk_count:
        raise ValueError("incomplete GSI chunk audit " + unit)
    if any(not isinstance(x, dict) for x in chunks):
        raise ValueError("malformed chunk audit " + unit)
    return {
        "candidate_rows": candidates,
        "gsi_source_complete_rows": complete,
        "gsi_provider_unavailable_rows": not_found,
        "gsi_terrain_vector_unavailable_rows": not_vector,
        "gsi_chunk_count": chunk_count,
        "grid_sha256": _sha(grid.get("private_grid_sha256"), "grid"),
        "gsi_terrain_feature_sha256": _sha(gsi.get("terrain_feature_digest_sha256"), "GSI terrain"),
        "gsi_frame_sha256": _sha(gsi.get("private_gsi_frame_sha256"), "GSI CSV"),
        "source_state_sha256": _sha(structural.get("source_state_digest_sha256"), "source-state"),
        "structural_order_sha256": _sha(structural.get("private_structural_order_sha256"), "structural CSV"),
        "final_patch_sha256": _sha(patch.get("private_patch_sha256"), "patch CSV"),
        # Private internal comparison only. Never include the chunk objects
        # themselves in the public output.
        "_chunk_audits": chunks,
    }


def audit_three_runs(logs: Mapping[tuple[str, str], str], frozen: Mapping[str, Any]) -> dict[str, Any]:
    if frozen.get("status") != "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED":
        raise ValueError("wrong frozen historical patch source")
    if frozen.get("source_workflow_run") != 37647225829 or set(frozen.get("units", {})) != set(UNITS):
        raise ValueError("original PR247 source identity/units changed")
    results = {}
    for unit in UNITS:
        rows = {}
        for label, (run_id, job_ids) in RUNS.items():
            raw = logs.get((label, unit))
            if not isinstance(raw, str) or not raw:
                raise ValueError("missing original job log: " + label + "/" + unit)
            stages = _objects(raw)
            row = _signature(stages, unit, frozen["units"][unit])
            row["run_id"] = run_id
            row["job_id"] = job_ids[unit]
            row["strict_full_order_gate_failed"] = FAIL_TEXT in raw
            rows[label] = row

        source = rows["original_247"]
        if source["structural_order_sha256"] != frozen["units"][unit]["structural_order_sha256"]:
            raise ValueError("original rank SHA not bound to PR247 frozen receipt " + unit)
        if source["final_patch_sha256"] != frozen["units"][unit]["private_patch_sha256"]:
            raise ValueError("original patch SHA not bound to PR247 frozen receipt " + unit)
        compare_fields = (
            "candidate_rows", "gsi_source_complete_rows", "gsi_provider_unavailable_rows",
            "gsi_terrain_vector_unavailable_rows", "gsi_chunk_count", "grid_sha256",
            "source_state_sha256", "final_patch_sha256",
        )
        for label in ("replay_249", "strict_audit_250"):
            if any(rows[label][f] != source[f] for f in compare_fields):
                raise ValueError("fixed metadata or final patch drift: " + unit + "/" + label)
            if rows[label]["_chunk_audits"] != source["_chunk_audits"]:
                raise ValueError("GSI per-chunk audit drift: " + unit + "/" + label)
        if rows["original_247"]["strict_full_order_gate_failed"] or rows["replay_249"]["strict_full_order_gate_failed"]:
            raise ValueError("historical successful source job has failed full-order gate")
        if rows["strict_audit_250"]["strict_full_order_gate_failed"] != (
            rows["strict_audit_250"]["structural_order_sha256"] != source["structural_order_sha256"]
        ):
            raise ValueError("PR250 fail-closed status inconsistent with SHA " + unit)
        sig = [rows[label]["gsi_terrain_feature_sha256"] for label in RUNS]
        classes = [list(dict.fromkeys(sig)).index(v) for v in sig]
        unit_result = {
            "cohort_unit_id": unit,
            "original_frozen_patch_sha256": source["final_patch_sha256"],
            "candidate_rows": source["candidate_rows"],
            "gsi_source_complete_rows": source["gsi_source_complete_rows"],
            "gsi_chunk_count": source["gsi_chunk_count"],
            "gsi_chunk_metadata_identical_all_three": True,
            "grid_and_source_state_identical_all_three": True,
            "final_patch_bytes_identical_all_three": True,
            "distinct_gsi_feature_signatures": len(set(sig)),
            "gsi_feature_pattern_in_run_order": classes,
            "runs": {},
        }
        for label in RUNS:
            row = rows[label]
            unit_result["runs"][label] = {k: v for k, v in row.items() if k != "_chunk_audits"}
        results[unit] = unit_result
    return {
        "schema_version": "cirsium-three-run-gsi-fingerprint-integrity-v1",
        "status": "THREE_HISTORICAL_LOG_RUNS_AUDITED_PATCHES_STABLE_SOURCE_DRIFT",
        "run_order": list(RUNS),
        "workflow_run_ids": {label: v[0] for label, v in RUNS.items()},
        "source_receipt": str(ORIGINAL_PATCH_RECEIPT.relative_to(ROOT)),
        "units": results,
        "summary": {
            "historical_workflow_runs": 3,
            "historical_unit_jobs": 12,
            "unit_count": 4,
            "distinct_gsi_feature_signatures_per_unit": {unit: v["distinct_gsi_feature_signatures"] for unit, v in results.items()},
            "all_twelve_final_patch_files_match_original": True,
            "all_twelve_grid_and_source_state_digests_match": True,
            "all_twelve_chunk_metadata_reproduce": True,
            "all_twelve_full_orders_match_original": False,
        },
        "boundaries": {
            "post_observation_forensic_audit_only": True,
            "source_provider_tile_bytes_recovered_or_authenticated": False,
            "numerical_cpu_causality_proven": False,
            "full_100m_source_reproducibility_proven": False,
            "independent_field_confirmation": False,
            "same_patch_hash_cannot_waive_strict_PR250_full_order_gate": True,
            "original_2p5pct_1km_selection_and_main_changed": False,
            "private_coordinates_or_cell_ids_published": False,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--logs-root", type=Path, required=True, help="PRIVATE root: RUN_ID/JOB_ID.log")
    p.add_argument("--verify-saved", type=Path)
    p.add_argument("--out-json", type=Path)
    args = p.parse_args()
    if bool(args.verify_saved) == bool(args.out_json):
        p.error("select exactly one of --verify-saved and --out-json")
    if args.logs_root.resolve().is_relative_to(ROOT.resolve()):
        p.error("raw logs must remain outside public repository")
    frozen = json.loads(ORIGINAL_PATCH_RECEIPT.read_text(encoding="utf-8"))
    logs = {
        (label, unit): (args.logs_root / str(run_id) / f"{job}.log").read_text(encoding="utf-8-sig")
        for label, (run_id, jobs) in RUNS.items() for unit, job in jobs.items()
    }
    result = audit_three_runs(logs, frozen)
    if args.verify_saved:
        expected = json.loads(args.verify_saved.read_text(encoding="utf-8"))
        if result != expected:
            raise ValueError("saved three-run fingerprint receipt differs from source logs")
    else:
        if args.out_json.exists():
            raise FileExistsError("refusing to overwrite a public-safe receipt")
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
