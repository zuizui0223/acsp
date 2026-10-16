#!/usr/bin/env python3
"""Compose lossless source-availability states for fresh-SENTINEL v2.

This stage joins the already-frozen full terrain and repaired WorldCover source
artifacts on the exact 39,200 candidate identities. It computes no ecological
score. A candidate is either source-ready for a declared family or retained as
SOURCE_INDETERMINATE_RETAIN. Missing source evidence can never remove a candidate,
become unsuitable habitat, or act as a negative score.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_source_indeterminate_retention_v1.json"
READY = "SOURCE_READY_FOR_FAMILY_COARSE_STAGE"
INDETERMINATE = "SOURCE_INDETERMINATE_RETAIN"
EXPECTED_CANDIDATES = 39200
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
TERRAIN_ONLY_UNITS = {"CIR06"}
TERRAIN_WORLDCOVER_UNITS = {"CIR02", "CIR12", "CIR13"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside_repo(path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_SOURCE_AVAILABILITY_COMPOSITION":
        raise ValueError("source-indeterminate retention contract is not frozen")
    if int(value.get("outer_frame", {}).get("candidate_count", -1)) != EXPECTED_CANDIDATES:
        raise ValueError("source-retention candidate denominator drifted")
    if tuple(value.get("unit_source_requirements", {}).keys()) != UNITS:
        raise ValueError("source-retention unit identity/order drifted")
    return value


def _validate_hash(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != str(expected):
        raise ValueError(f"{label} SHA256 mismatch: expected={expected} actual={actual}")


def compose_source_availability(
    terrain: pd.DataFrame,
    worldcover: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return one lossless source-state row per frozen candidate."""
    contract = _contract()
    if len(terrain) != EXPECTED_CANDIDATES or len(worldcover) != EXPECTED_CANDIDATES:
        raise ValueError("terrain and WorldCover must both contain exactly 39,200 rows")

    terrain_required = {"candidate_cell_id", "regional_tile_id", "latitude", "longitude", "coarse_terrain_status"}
    worldcover_required = {"candidate_cell_id", "regional_tile_id", "latitude", "longitude", "worldcover_point_status"}
    missing_t = sorted(terrain_required.difference(terrain.columns))
    missing_w = sorted(worldcover_required.difference(worldcover.columns))
    if missing_t:
        raise ValueError(f"terrain artifact missing columns: {missing_t}")
    if missing_w:
        raise ValueError(f"WorldCover artifact missing columns: {missing_w}")

    t = terrain.reset_index(drop=True).copy()
    w = worldcover.reset_index(drop=True).copy()
    t_ids = t["candidate_cell_id"].astype(str).tolist()
    w_ids = w["candidate_cell_id"].astype(str).tolist()
    if t_ids != w_ids:
        raise ValueError("terrain and WorldCover candidate identity/order differ")
    if len(set(t_ids)) != EXPECTED_CANDIDATES:
        raise ValueError("candidate IDs must be unique across the frozen denominator")
    if not t["regional_tile_id"].astype(str).equals(w["regional_tile_id"].astype(str)):
        raise ValueError("terrain and WorldCover regional_tile_id differ")
    for column in ("latitude", "longitude"):
        left = pd.to_numeric(t[column], errors="coerce").to_numpy(float)
        right = pd.to_numeric(w[column], errors="coerce").to_numpy(float)
        if not np.isfinite(left).all() or not np.isfinite(right).all():
            raise ValueError(f"{column} must be finite in both source artifacts")
        if not np.allclose(left, right, rtol=0.0, atol=1e-12):
            raise ValueError(f"terrain and WorldCover {column} differ")

    terrain_complete = t["coarse_terrain_status"].astype(str).eq("COMPLETE").to_numpy()
    worldcover_complete = w["worldcover_point_status"].astype(str).eq("COMPLETE").to_numpy()
    both_complete = terrain_complete & worldcover_complete

    ledger = pd.DataFrame({
        "candidate_cell_id": t_ids,
        "regional_tile_id": t["regional_tile_id"].astype(str).to_numpy(),
        "terrain_source_status": t["coarse_terrain_status"].astype(str).to_numpy(),
        "worldcover_source_status": w["worldcover_point_status"].astype(str).to_numpy(),
    })
    for unit in UNITS:
        ready = terrain_complete if unit in TERRAIN_ONLY_UNITS else both_complete
        ledger[f"{unit}_source_state"] = np.where(ready, READY, INDETERMINATE)

    expected = contract["expected_source_coverage_from_frozen_inputs"]
    terrain_n = int(terrain_complete.sum())
    worldcover_n = int(worldcover_complete.sum())
    both_n = int(both_complete.sum())
    terrain_missing_wc_complete = int((~terrain_complete & worldcover_complete).sum())
    terrain_complete_wc_missing = int((terrain_complete & ~worldcover_complete).sum())
    both_missing = int((~terrain_complete & ~worldcover_complete).sum())

    observed = {
        "terrain_complete_candidates": terrain_n,
        "worldcover_complete_candidates": worldcover_n,
        "both_terrain_and_worldcover_complete_candidates": both_n,
        "terrain_incomplete_worldcover_complete": terrain_missing_wc_complete,
        "terrain_complete_worldcover_incomplete": terrain_complete_wc_missing,
        "both_incomplete": both_missing,
        "CIR06_source_ready_candidates": int((ledger["CIR06_source_state"] == READY).sum()),
        "CIR06_source_indeterminate_retain_candidates": int((ledger["CIR06_source_state"] == INDETERMINATE).sum()),
        "CIR02_CIR12_CIR13_source_ready_candidates_each": int((ledger["CIR02_source_state"] == READY).sum()),
        "CIR02_CIR12_CIR13_source_indeterminate_retain_candidates_each": int((ledger["CIR02_source_state"] == INDETERMINATE).sum()),
    }
    if observed != expected:
        raise ValueError(f"frozen source-coverage composition drift: expected={expected} observed={observed}")

    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-source-availability-composition-v1",
        "status": "SOURCE_AVAILABILITY_LEDGER_COMPOSED_PRE_OUTCOME",
        "outer_frame_identity": "JP_PUBLIC_COUNTRY_BROAD_FRAME_V1",
        "candidate_count": EXPECTED_CANDIDATES,
        "candidate_rows_dropped": 0,
        "candidate_identity_order_preserved": True,
        "terrain_complete_candidates": terrain_n,
        "worldcover_complete_candidates": worldcover_n,
        "both_terrain_and_worldcover_complete_candidates": both_n,
        "terrain_incomplete_worldcover_complete": terrain_missing_wc_complete,
        "terrain_complete_worldcover_incomplete": terrain_complete_wc_missing,
        "both_incomplete": both_missing,
        "unit_source_state_counts": {
            unit: {
                READY: int((ledger[f"{unit}_source_state"] == READY).sum()),
                INDETERMINATE: int((ledger[f"{unit}_source_state"] == INDETERMINATE).sum()),
            }
            for unit in UNITS
        },
        "source_indeterminate_candidates_retained": True,
        "source_indeterminate_is_biological_negative": False,
        "source_indeterminate_may_be_recoded_as_unsuitable": False,
        "source_indeterminate_may_be_dropped": False,
        "source_indeterminate_may_receive_worst_ecological_score": False,
        "ecological_score_computed": False,
        "habitat_threshold_applied": False,
        "candidate_rank_added": False,
        "candidate_selection_added": False,
        "coarse_to_fine_expansion_applied": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "private_exact_site_geometry_used": False,
        "p02_result_used": False,
        "human_access_used": False,
        "next_gate": (
            "Freeze family-specific coarse ecological evidence formulas. "
            "SOURCE_INDETERMINATE_RETAIN remains a parallel retained lane and cannot be excluded by source missingness."
        ),
    }
    return ledger, summary


def run(
    terrain_csv_gz: Path,
    worldcover_csv_gz: Path,
    ledger_out_csv_gz: Path,
    summary_out_json: Path,
) -> dict[str, Any]:
    contract = _contract()
    terrain_csv_gz = Path(terrain_csv_gz).resolve()
    worldcover_csv_gz = Path(worldcover_csv_gz).resolve()
    ledger_out_csv_gz = Path(ledger_out_csv_gz).resolve()
    summary_out_json = Path(summary_out_json).resolve()
    for path in (terrain_csv_gz, worldcover_csv_gz):
        if not path.is_file():
            raise ValueError(f"missing frozen source artifact: {path}")
    if _inside_repo(ledger_out_csv_gz):
        raise ValueError("candidate-level source ledger must remain outside the public repository")
    if ledger_out_csv_gz.exists() or summary_out_json.exists():
        raise ValueError("refusing to overwrite source-availability outputs")

    _validate_hash(
        terrain_csv_gz,
        contract["source_inputs"]["terrain"]["full_csv_gz_sha256"],
        "terrain artifact",
    )
    _validate_hash(
        worldcover_csv_gz,
        contract["source_inputs"]["worldcover"]["full_csv_gz_sha256"],
        "WorldCover repair artifact",
    )

    terrain = pd.read_csv(terrain_csv_gz, low_memory=False)
    worldcover = pd.read_csv(worldcover_csv_gz, low_memory=False)
    ledger, summary = compose_source_availability(terrain, worldcover)
    ledger_out_csv_gz.parent.mkdir(parents=True, exist_ok=True)
    summary_out_json.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(ledger_out_csv_gz, index=False, compression="gzip")
    summary_out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        **summary,
        "terrain_artifact_sha256": _sha256(terrain_csv_gz),
        "worldcover_artifact_sha256": _sha256(worldcover_csv_gz),
        "source_ledger_sha256": _sha256(ledger_out_csv_gz),
        "public_safe_summary_sha256": _sha256(summary_out_json),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terrain-csv-gz", type=Path, required=True)
    parser.add_argument("--worldcover-csv-gz", type=Path, required=True)
    parser.add_argument("--ledger-out-csv-gz", type=Path, required=True)
    parser.add_argument("--summary-out-json", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        args.terrain_csv_gz,
        args.worldcover_csv_gz,
        args.ledger_out_csv_gz,
        args.summary_out_json,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
