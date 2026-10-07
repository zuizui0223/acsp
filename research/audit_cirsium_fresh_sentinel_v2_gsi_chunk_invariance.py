#!/usr/bin/env python3
"""Audit whether GSI fine-terrain chunking behaves as pure source transport.

The audit fixes candidate points before terrain access, samples the exact same
points under two 40-km chunk-lattice phases, and compares both the selected GSI
source attribution and frozen terrain vectors. It does not rank candidates or
use field outcomes.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from acsp.global_geometry import fetch_geoboundaries_country_geometry
from research.audit_cirsium_fresh_sentinel_v2_local_refinement_size import (
    GRID_M,
    PROJ_STRING,
    READY,
    SUPPORT_FRACTION,
)
from research.build_cirsium_fresh_sentinel_public_broad_frame_v2 import (
    build_fresh_sentinel_v2_outer_frame,
)
from research.build_cirsium_private_alpine_local_grid_v1 import _sample_terrain
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_gsi_chunk_invariance_audit_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
EXPECTED_CANDIDATES = 39200
CHUNK_CELLS = 400
PHASES = ((0, 0), (200, 200))
TERRAIN_COLUMNS = ("elev", "slope100", "tpi300", "rough300")


def _load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_GSI_CHUNK_INVARIANCE_AUDIT":
        raise ValueError("GSI chunk-invariance contract is not frozen")
    if tuple(value.get("cohort_unit_ids") or ()) != UNITS:
        raise ValueError("GSI audit unit set drifted")
    fine = value["fine_grid_candidate_transport"]
    if int(fine["grid_spacing_m"]) != 100 or int(fine["physical_chunk_width_m"]) != 40000:
        raise ValueError("GSI fine transport physical scale drifted")
    if int(fine["equivalent_chunk_grid_cells"]) != CHUNK_CELLS:
        raise ValueError("GSI fine transport chunk-cell count drifted")
    if tuple(tuple(map(int, x)) for x in fine["chunk_phase_offsets_cells"]) != PHASES:
        raise ValueError("GSI phase offsets drifted")
    return value


def _select_indices(n: int, maximum: int) -> list[int]:
    if n <= 0:
        return []
    if n <= maximum:
        return list(range(n))
    values = np.linspace(0, n - 1, num=maximum)
    return sorted(set(int(round(x)) for x in values))


def build_audit_points(order: pd.DataFrame, outer: pd.DataFrame, unit: str) -> pd.DataFrame:
    contract = _load_contract()
    ready = order.loc[order["source_state"].astype(str).eq(READY)].copy()
    ready["coarse_evidence_rank"] = pd.to_numeric(
        ready["coarse_evidence_rank"], errors="raise"
    ).astype(int)
    ready = ready.sort_values("coarse_evidence_rank", kind="mergesort").reset_index(drop=True)
    retain_n = int(math.ceil(SUPPORT_FRACTION * len(ready)))
    centers = ready.iloc[:retain_n].copy()
    coords = outer.set_index(outer["candidate_cell_id"].astype(str))[["latitude", "longitude"]]
    centers.index = centers["candidate_cell_id"].astype(str)
    centers = centers.join(coords, how="left").reset_index(drop=True)
    if centers[["latitude", "longitude"]].isna().any().any():
        raise ValueError(f"{unit} failed to restore coarse-center coordinates")

    selected = centers.iloc[
        _select_indices(len(centers), int(contract["audit_sample"]["max_centers_per_unit"]))
    ].copy()
    forward = Transformer.from_crs("EPSG:4326", CRS.from_proj4(PROJ_STRING), always_xy=True)
    inverse = Transformer.from_crs(CRS.from_proj4(PROJ_STRING), "EPSG:4326", always_xy=True)
    xs, ys = forward.transform(
        selected["longitude"].to_numpy(float), selected["latitude"].to_numpy(float)
    )
    rows: dict[tuple[int, int], dict[str, Any]] = {}
    offsets = [tuple(map(int, x)) for x in contract["audit_sample"]["fine_point_offsets_grid_cells"]]
    for center_rank, x, y in zip(selected["coarse_evidence_rank"].astype(int), xs, ys):
        center_col = math.floor(float(x) / GRID_M)
        center_row = math.floor(float(y) / GRID_M)
        for drow, dcol in offsets:
            row = center_row + drow
            col = center_col + dcol
            key = (row, col)
            cx = (col + 0.5) * GRID_M
            cy = (row + 0.5) * GRID_M
            lon, lat = inverse.transform(cx, cy)
            rows.setdefault(
                key,
                {
                    "cohort_unit_id": unit,
                    "candidate_cell_id": f"{unit}_gsi_audit_r{row}_c{col}",
                    "grid_row": row,
                    "grid_col": col,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "source_center_rank": int(center_rank),
                },
            )
    return pd.DataFrame(list(rows.values())).sort_values(
        ["grid_row", "grid_col"], kind="mergesort"
    ).reset_index(drop=True)


def _chunk_groups(frame: pd.DataFrame, phase_row: int, phase_col: int) -> list[pd.DataFrame]:
    work = frame.copy()
    work["_chunk_row"] = (work["grid_row"].astype(int) - int(phase_row)) // CHUNK_CELLS
    work["_chunk_col"] = (work["grid_col"].astype(int) - int(phase_col)) // CHUNK_CELLS
    return [
        group.drop(columns=["_chunk_row", "_chunk_col"]).copy().reset_index(drop=True)
        for _, group in work.groupby(["_chunk_row", "_chunk_col"], sort=True)
    ]


def attach_gsi_for_phase(
    frame: pd.DataFrame,
    *,
    phase_row: int,
    phase_col: int,
    work_dir: Path,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    cache = work_dir / "gsi-cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("GBIF_FIELDMAP_CACHE", str(cache))
    from gbif_fieldmap_builder_app import build_gsi_dem_for_bounds

    pieces: list[pd.DataFrame] = []
    audits: list[dict[str, Any]] = []
    for index, component in enumerate(_chunk_groups(frame, phase_row, phase_col)):
        west = float(component["longitude"].min()) - 0.02
        east = float(component["longitude"].max()) + 0.02
        south = float(component["latitude"].min()) - 0.02
        north = float(component["latitude"].max()) + 0.02
        references = tuple(
            (float(row.latitude), float(row.longitude))
            for row in component.iloc[:: max(1, len(component) // 8)].head(8).itertuples(index=False)
        )
        dem_path, attribution = build_gsi_dem_for_bounds(
            (west, south, east, north),
            references,
            max_tiles=900,
        )
        if not dem_path:
            audits.append(
                {
                    "chunk_index": int(index),
                    "candidate_rows_input": int(len(component)),
                    "status": "INDETERMINATE_GSI_PROVIDER_UNAVAILABLE",
                    "gsi_attribution": "",
                }
            )
            unavailable = component.copy()
            for column in TERRAIN_COLUMNS:
                unavailable[column] = np.nan
            unavailable["gsi_source_state"] = "INDETERMINATE_GSI_PROVIDER_UNAVAILABLE"
            unavailable["gsi_attribution"] = ""
            pieces.append(unavailable)
            continue
        try:
            sampled = _sample_terrain(component, Path(dem_path))
        except ValueError as exc:
            if "no annular candidate cell has complete terrain support" not in str(exc):
                raise
            audits.append(
                {
                    "chunk_index": int(index),
                    "candidate_rows_input": int(len(component)),
                    "status": "INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE",
                    "gsi_attribution": str(attribution),
                }
            )
            unavailable = component.copy()
            for column in TERRAIN_COLUMNS:
                unavailable[column] = np.nan
            unavailable["gsi_source_state"] = "INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE"
            unavailable["gsi_attribution"] = str(attribution)
            pieces.append(unavailable)
            continue
        complete_ids = set(sampled["candidate_cell_id"].astype(str))
        out = component.copy()
        out["gsi_source_state"] = np.where(
            out["candidate_cell_id"].astype(str).isin(complete_ids),
            "SOURCE_COMPLETE",
            "INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE",
        )
        out["gsi_attribution"] = str(attribution)
        sampled_by_id = sampled.set_index(sampled["candidate_cell_id"].astype(str))
        for column in TERRAIN_COLUMNS:
            out[column] = np.nan
            mask = out["candidate_cell_id"].astype(str).isin(complete_ids)
            ids = out.loc[mask, "candidate_cell_id"].astype(str)
            out.loc[mask, column] = sampled_by_id.loc[ids, column].to_numpy(float)
        pieces.append(out)
        audits.append(
            {
                "chunk_index": int(index),
                "candidate_rows_input": int(len(component)),
                "source_complete_rows": int(len(sampled)),
                "status": "SOURCE_ACQUIRED",
                "gsi_attribution": str(attribution),
            }
        )
    merged = pd.concat(pieces, ignore_index=True).sort_values(
        "candidate_cell_id", kind="mergesort"
    ).reset_index(drop=True)
    if merged["candidate_cell_id"].duplicated().any():
        raise AssertionError("GSI phase assembly duplicated candidate IDs")
    return merged, audits


def compare_phases(a: pd.DataFrame, b: pd.DataFrame) -> dict[str, Any]:
    left = a.set_index("candidate_cell_id").sort_index()
    right = b.set_index("candidate_cell_id").sort_index()
    if left.index.tolist() != right.index.tolist():
        raise AssertionError("GSI phase comparison candidate identities drifted")
    state_match = left["gsi_source_state"].astype(str).eq(right["gsi_source_state"].astype(str))
    attribution_match = left["gsi_attribution"].astype(str).eq(right["gsi_attribution"].astype(str))
    numeric_match = np.ones(len(left), dtype=bool)
    max_abs_diff = 0.0
    for column in TERRAIN_COLUMNS:
        x = pd.to_numeric(left[column], errors="coerce").to_numpy(float)
        y = pd.to_numeric(right[column], errors="coerce").to_numpy(float)
        same_missing = np.isnan(x) == np.isnan(y)
        finite = np.isfinite(x) & np.isfinite(y)
        diffs = np.zeros(len(x), dtype=float)
        diffs[finite] = np.abs(x[finite] - y[finite])
        if finite.any():
            max_abs_diff = max(max_abs_diff, float(diffs[finite].max()))
        numeric_match &= same_missing & ((~finite) | (diffs <= 1e-9))
    all_match = state_match.to_numpy() & attribution_match.to_numpy() & numeric_match
    return {
        "candidate_rows": int(len(left)),
        "source_state_match_rows": int(state_match.sum()),
        "attribution_match_rows": int(attribution_match.sum()),
        "terrain_vector_match_rows": int(numeric_match.sum()),
        "all_match_rows": int(all_match.sum()),
        "all_match_fraction": float(all_match.mean()),
        "max_abs_terrain_difference": float(max_abs_diff),
        "chunk_transport_invariant_on_audit_sample": bool(all_match.all()),
    }


def run_unit(order: pd.DataFrame, outer: pd.DataFrame, unit: str, work_dir: Path) -> dict[str, Any]:
    points = build_audit_points(order, outer, unit)
    phase_results = {}
    frames = {}
    for phase in PHASES:
        key = f"r{phase[0]}_c{phase[1]}"
        frame, chunks = attach_gsi_for_phase(
            points,
            phase_row=phase[0],
            phase_col=phase[1],
            work_dir=work_dir / unit / key,
        )
        frames[key] = frame
        phase_results[key] = {
            "chunk_count": int(len(chunks)),
            "source_complete_rows": int(frame["gsi_source_state"].eq("SOURCE_COMPLETE").sum()),
            "provider_unavailable_rows": int(
                frame["gsi_source_state"].eq("INDETERMINATE_GSI_PROVIDER_UNAVAILABLE").sum()
            ),
            "terrain_vector_unavailable_rows": int(
                frame["gsi_source_state"].eq("INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE").sum()
            ),
            "attributions": sorted(set(frame["gsi_attribution"].astype(str))),
            "chunks": chunks,
        }
    comparison = compare_phases(frames["r0_c0"], frames["r200_c200"])
    return {
        "cohort_unit_id": unit,
        "audit_candidate_rows": int(len(points)),
        "phase_results": phase_results,
        "phase_comparison": comparison,
        "field_outcomes_opened": False,
        "candidate_ranking_computed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", action="append", required=True, help="UNIT=path.csv.gz")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    orders = {}
    for spec in args.order:
        unit, path = spec.split("=", 1)
        orders[unit] = pd.read_csv(path, low_memory=False)
    if set(orders) != set(UNITS):
        raise ValueError("GSI audit requires exactly CIR02/CIR06/CIR12/CIR13")
    geometry = fetch_geoboundaries_country_geometry("JP")
    outer, summary = build_fresh_sentinel_v2_outer_frame(geometry)
    if int(summary["candidate_count"]) != EXPECTED_CANDIDATES:
        raise ValueError("frozen Japan outer frame candidate count drifted")
    result = {
        "schema_version": "cirsium-fresh-sentinel-v2-gsi-chunk-invariance-audit-result-v1",
        "status": "GSI_CHUNK_INVARIANCE_AUDIT_COMPLETE_PRE_OUTCOME",
        "chunk_width_m": 40000,
        "fine_grid_spacing_m": 100,
        "phase_offsets_cells": [list(x) for x in PHASES],
        "units": {
            unit: run_unit(orders[unit], outer, unit, args.work_dir)
            for unit in UNITS
        },
        "field_outcomes_opened": False,
        "candidate_ranking_computed": False,
        "promotion_gate": False,
    }
    result["all_units_invariant"] = all(
        row["phase_comparison"]["chunk_transport_invariant_on_audit_sample"]
        for row in result["units"].values()
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
