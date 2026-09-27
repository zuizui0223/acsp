#!/usr/bin/env python3
"""Build full coarse evidence orders for fresh-SENTINEL v2 source-ready candidates.

The four orders are response-independent and deliberately partial. They use only
coarse evidence directions already justified by the frozen Cirsium structural
families. SOURCE_INDETERMINATE_RETAIN candidates receive no ecological rank and
remain a separate retained lane.

No threshold, Top-k, field outcome, access layer, private exact site or P02 result
is used. These orders are not the final 100 m regular-grid structural orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.compose_cirsium_fresh_sentinel_v2_source_availability import (
    INDETERMINATE,
    READY,
    compose_source_availability,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_coarse_evidence_order_v1.json"
SOURCE_CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_source_indeterminate_retention_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
EXPECTED_CANDIDATES = 39200


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _rank01(values: pd.Series, *, high: bool) -> pd.Series:
    ranked = pd.to_numeric(values, errors="coerce").rank(method="average", pct=True).astype(float)
    if not high:
        ranked = 1.0 - ranked + 1.0 / max(len(ranked), 1)
    return ranked.clip(0.0, 1.0)


def _contracts() -> tuple[dict[str, Any], dict[str, Any]]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source = json.loads(SOURCE_CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_COARSE_EVIDENCE_ORDER_EXECUTION":
        raise ValueError("coarse evidence order contract is not frozen")
    if source.get("status") != "FROZEN_BEFORE_SOURCE_AVAILABILITY_COMPOSITION":
        raise ValueError("source-indeterminate retention contract is not frozen")
    if int(contract.get("candidate_count", -1)) != EXPECTED_CANDIDATES:
        raise ValueError("coarse evidence order denominator drifted")
    return contract, source


def _base_inputs(
    terrain: pd.DataFrame,
    worldcover: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if len(terrain) != EXPECTED_CANDIDATES or len(worldcover) != EXPECTED_CANDIDATES:
        raise ValueError("coarse evidence inputs must each contain 39,200 rows")
    source_ledger, _ = compose_source_availability(terrain, worldcover)
    t = terrain.reset_index(drop=True)
    w = worldcover.reset_index(drop=True)
    if source_ledger["candidate_cell_id"].astype(str).tolist() != t["candidate_cell_id"].astype(str).tolist():
        raise AssertionError("source ledger candidate order drifted")
    return t, w, source_ledger


def _finalize_unit_order(
    source_ledger: pd.DataFrame,
    unit: str,
    ready_frame: pd.DataFrame,
    *,
    component_columns: list[str],
    sort_columns: list[str],
    ascending: list[bool],
) -> pd.DataFrame:
    state_col = f"{unit}_source_state"
    ids = source_ledger["candidate_cell_id"].astype(str)
    ready_ids = set(source_ledger.loc[source_ledger[state_col].eq(READY), "candidate_cell_id"].astype(str))
    if set(ready_frame["candidate_cell_id"].astype(str)) != ready_ids:
        raise ValueError(f"{unit} ready candidate set changed during coarse evidence construction")

    work = ready_frame.copy()
    work["_stable_hash"] = work["candidate_cell_id"].map(_stable_hash)
    ordered = work.sort_values(
        [*sort_columns, "_stable_hash"],
        ascending=[*ascending, True],
        kind="mergesort",
    ).reset_index(drop=True)
    ordered["coarse_evidence_rank"] = range(1, len(ordered) + 1)
    rank_map = dict(zip(ordered["candidate_cell_id"].astype(str), ordered["coarse_evidence_rank"].astype(int)))

    output = pd.DataFrame({
        "candidate_cell_id": ids,
        "regional_tile_id": source_ledger["regional_tile_id"].astype(str),
        "source_state": source_ledger[state_col].astype(str),
    })
    output["coarse_evidence_rank"] = output["candidate_cell_id"].map(rank_map).astype("Int64")
    for column in component_columns:
        value_map = dict(zip(ready_frame["candidate_cell_id"].astype(str), ready_frame[column]))
        output[column] = output["candidate_cell_id"].map(value_map)
    output["ecological_rank_defined"] = output["source_state"].eq(READY)
    if output.loc[output["source_state"].eq(INDETERMINATE), "coarse_evidence_rank"].notna().any():
        raise AssertionError(f"{unit} source-indeterminate candidates received an ecological rank")
    if output["candidate_cell_id"].astype(str).tolist() != ids.tolist():
        raise AssertionError(f"{unit} output candidate order drifted")
    return output


def build_coarse_evidence_orders(
    terrain: pd.DataFrame,
    worldcover: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    contract, _ = _contracts()
    t, w, source = _base_inputs(terrain, worldcover)
    ids = source["candidate_cell_id"].astype(str)
    wc_codes = pd.to_numeric(w["worldcover_class_code"], errors="coerce")

    orders: dict[str, pd.DataFrame] = {}

    # CIR02: direct wetland point class first; then low-slope/low-TPI coarse context.
    mask = source["CIR02_source_state"].eq(READY).to_numpy()
    cir02 = pd.DataFrame({
        "candidate_cell_id": ids[mask].to_numpy(),
        "direct_wetland_signal": (wc_codes[mask].to_numpy(float) == 90.0).astype(int),
        "coarse_slope": pd.to_numeric(t.loc[mask, "slope"], errors="coerce").to_numpy(float),
        "coarse_tpi": pd.to_numeric(t.loc[mask, "tpi"], errors="coerce").to_numpy(float),
    })
    if not np.isfinite(cir02[["coarse_slope", "coarse_tpi"]].to_numpy(float)).all():
        raise ValueError("CIR02 source-ready terrain contains non-finite slope/tpi")
    cir02["coarse_low_slope_rank"] = _rank01(cir02["coarse_slope"], high=False)
    cir02["coarse_low_tpi_rank"] = _rank01(cir02["coarse_tpi"], high=False)
    cir02["coarse_topographic_moisture_context"] = np.minimum(
        cir02["coarse_low_slope_rank"], cir02["coarse_low_tpi_rank"]
    )
    orders["CIR02"] = _finalize_unit_order(
        source,
        "CIR02",
        cir02,
        component_columns=["direct_wetland_signal", "coarse_topographic_moisture_context"],
        sort_columns=["direct_wetland_signal", "coarse_topographic_moisture_context"],
        ascending=[False, False],
    )

    # CIR06: only the source-justified high relative-elevation direction is available coarsely.
    mask = source["CIR06_source_state"].eq(READY).to_numpy()
    cir06 = pd.DataFrame({
        "candidate_cell_id": ids[mask].to_numpy(),
        "coarse_elevation": pd.to_numeric(t.loc[mask, "elevation"], errors="coerce").to_numpy(float),
    })
    if not np.isfinite(cir06["coarse_elevation"].to_numpy(float)).all():
        raise ValueError("CIR06 source-ready elevation contains non-finite values")
    cir06["coarse_relative_elevation_rank"] = _rank01(cir06["coarse_elevation"], high=True)
    orders["CIR06"] = _finalize_unit_order(
        source,
        "CIR06",
        cir06,
        component_columns=["coarse_relative_elevation_rank"],
        sort_columns=["coarse_relative_elevation_rank"],
        ascending=[False],
    )

    # CIR12/CIR13: direct grass point class only. Local terrain continuity is deferred.
    for unit in ("CIR12", "CIR13"):
        mask = source[f"{unit}_source_state"].eq(READY).to_numpy()
        ready = pd.DataFrame({
            "candidate_cell_id": ids[mask].to_numpy(),
            "direct_grass_signal": (wc_codes[mask].to_numpy(float) == 30.0).astype(int),
        })
        orders[unit] = _finalize_unit_order(
            source,
            unit,
            ready,
            component_columns=["direct_grass_signal"],
            sort_columns=["direct_grass_signal"],
            ascending=[False],
        )

    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-coarse-evidence-order-result-v1",
        "status": "FULL_COARSE_EVIDENCE_ORDERS_BUILT_PRE_OUTCOME",
        "outer_frame_identity": "JP_PUBLIC_COUNTRY_BROAD_FRAME_V1",
        "candidate_count": EXPECTED_CANDIDATES,
        "orders": {
            unit: {
                "source_ready_candidate_count": int((orders[unit]["source_state"] == READY).sum()),
                "source_indeterminate_retain_candidate_count": int((orders[unit]["source_state"] == INDETERMINATE).sum()),
                "ecological_rank_defined_count": int(orders[unit]["ecological_rank_defined"].sum()),
                "max_coarse_evidence_rank": int(orders[unit]["coarse_evidence_rank"].max()),
                "candidate_rows_dropped": 0,
            }
            for unit in UNITS
        },
        "CIR02_direct_wetland_signal_count": int(
            pd.to_numeric(orders["CIR02"]["direct_wetland_signal"], errors="coerce").fillna(0).sum()
        ),
        "CIR12_direct_grass_signal_count": int(
            pd.to_numeric(orders["CIR12"]["direct_grass_signal"], errors="coerce").fillna(0).sum()
        ),
        "CIR13_direct_grass_signal_count": int(
            pd.to_numeric(orders["CIR13"]["direct_grass_signal"], errors="coerce").fillna(0).sum()
        ),
        "source_indeterminate_candidates_receive_ecological_rank": False,
        "source_indeterminate_candidates_ranked_below_source_ready": False,
        "candidate_selection_added": False,
        "top_k_or_threshold_applied": False,
        "fitted_weight_used": False,
        "coarse_order_is_final_100m_structural_order": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "private_exact_site_geometry_used": False,
        "p02_result_used": False,
        "human_access_used": False,
        "budget_used": False,
        "next_gate": (
            "Freeze the hash-only coarse-order receipt, then define outcome-blind coarse-to-fine expansion. "
            "Source-indeterminate candidates remain a separate retained lane."
        ),
    }
    expected_signals = contract["expected_direct_signal_counts_on_frozen_source_ready_denominator"]
    if summary["CIR02_direct_wetland_signal_count"] != int(expected_signals["CIR02_wetland_class_90"]):
        raise ValueError("CIR02 direct wetland signal count drifted")
    if summary["CIR12_direct_grass_signal_count"] != int(expected_signals["CIR12_grass_class_30"]):
        raise ValueError("CIR12 direct grass signal count drifted")
    if summary["CIR13_direct_grass_signal_count"] != int(expected_signals["CIR13_grass_class_30"]):
        raise ValueError("CIR13 direct grass signal count drifted")
    return orders, summary


def run(
    terrain_csv_gz: Path,
    worldcover_csv_gz: Path,
    out_dir: Path,
) -> dict[str, Any]:
    contract, source_contract = _contracts()
    terrain_csv_gz = Path(terrain_csv_gz).resolve()
    worldcover_csv_gz = Path(worldcover_csv_gz).resolve()
    out_dir = Path(out_dir).resolve()
    if out_dir.exists():
        raise ValueError("refusing to overwrite coarse-evidence output directory")

    expected_terrain = source_contract["source_inputs"]["terrain"]["full_csv_gz_sha256"]
    expected_wc = source_contract["source_inputs"]["worldcover"]["full_csv_gz_sha256"]
    if _sha256(terrain_csv_gz) != expected_terrain:
        raise ValueError("terrain artifact SHA256 mismatch")
    if _sha256(worldcover_csv_gz) != expected_wc:
        raise ValueError("WorldCover artifact SHA256 mismatch")

    terrain = pd.read_csv(terrain_csv_gz, low_memory=False)
    worldcover = pd.read_csv(worldcover_csv_gz, low_memory=False)
    orders, summary = build_coarse_evidence_orders(terrain, worldcover)
    out_dir.mkdir(parents=True)
    hashes = {}
    for unit, frame in orders.items():
        path = out_dir / f"{unit}_coarse_evidence_order.csv.gz"
        frame.to_csv(path, index=False, compression="gzip")
        hashes[unit] = _sha256(path)
    summary["private_order_sha256_by_unit"] = hashes
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["summary_sha256"] = _sha256(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terrain-csv-gz", type=Path, required=True)
    parser.add_argument("--worldcover-csv-gz", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.terrain_csv_gz, args.worldcover_csv_gz, args.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
