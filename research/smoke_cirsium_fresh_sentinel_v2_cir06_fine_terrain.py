#!/usr/bin/env python3
"""Run a deterministic CIR06 fine-terrain source-mechanics smoke.

The smoke consumes the frozen CIR06 coarse order and frozen coarse-terrain artifact,
uses the pre-frozen 5-km / 100-m local-refinement geometry around rank 1, retrieves
GSI DEM through the production provider path, and samples the existing frozen
terrain primitives. It never computes a structural graph or opens any field outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer

from research.audit_cirsium_fresh_sentinel_v2_local_refinement_geometry import (
    GRID_M,
    PROJ_STRING,
    RADIUS_M,
    _forward_transformer,
    _select_centers,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_cir06_fine_terrain_smoke_v1.json"
UNIT = "CIR06"
EXPECTED_CENTER_ID = "JP_x158_y63_p0142"
EXPECTED_CORE_CELLS = 7860
TERRAIN_TARGET_RES_M = 25.0
LARGEST_NEIGHBOURHOOD_M = 300.0
REQUIRED = ("elev", "slope100", "tpi300", "rough300")


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_CIR06_FINE_TERRAIN_SMOKE":
        raise ValueError("CIR06 fine-terrain smoke contract is not frozen")
    if value["center_rule"]["expected_candidate_cell_id"] != EXPECTED_CENTER_ID:
        raise ValueError("CIR06 smoke center identity drifted")
    if int(value["fine_geometry"]["expected_core_cell_count"]) != EXPECTED_CORE_CELLS:
        raise ValueError("CIR06 smoke core cell count drifted")
    if float(value["fine_geometry"]["grid_spacing_m"]) != GRID_M:
        raise ValueError("CIR06 smoke grid spacing drifted")
    if float(value["fine_geometry"]["window_radius_km"]) * 1000.0 != RADIUS_M:
        raise ValueError("CIR06 smoke radius drifted")
    return value


def derived_retrieval_margin_m() -> float:
    size300 = max(3, int(round(LARGEST_NEIGHBOURHOOD_M / TERRAIN_TARGET_RES_M)) | 1)
    half_width = ((size300 - 1) // 2) * TERRAIN_TARGET_RES_M
    gradient_cell = TERRAIN_TARGET_RES_M
    return float(half_width + gradient_cell)


def build_core_grid(latitude: float, longitude: float) -> pd.DataFrame:
    forward = _forward_transformer()
    inverse = Transformer.from_crs(
        CRS.from_proj4(PROJ_STRING),
        "EPSG:4326",
        always_xy=True,
    )
    x0, y0 = forward.transform(float(longitude), float(latitude))
    min_col = math.floor((x0 - RADIUS_M) / GRID_M)
    max_col = math.floor((x0 + RADIUS_M) / GRID_M)
    min_row = math.floor((y0 - RADIUS_M) / GRID_M)
    max_row = math.floor((y0 + RADIUS_M) / GRID_M)

    rows = np.arange(min_row, max_row + 1, dtype=np.int64)
    cols = np.arange(min_col, max_col + 1, dtype=np.int64)
    yy = (rows.astype(float) + 0.5) * GRID_M
    xx = (cols.astype(float) + 0.5) * GRID_M
    mask = (yy[:, None] - y0) ** 2 + (xx[None, :] - x0) ** 2 <= RADIUS_M * RADIUS_M + 1e-9
    rr, cc = np.nonzero(mask)
    grid_rows = rows[rr]
    grid_cols = cols[cc]
    center_x = (grid_cols.astype(float) + 0.5) * GRID_M
    center_y = (grid_rows.astype(float) + 0.5) * GRID_M
    lon, lat = inverse.transform(center_x, center_y)
    out = pd.DataFrame({
        "candidate_cell_id": [
            f"{UNIT}_fine_r{int(r)}_c{int(c)}"
            for r, c in zip(grid_rows, grid_cols)
        ],
        "grid_row": grid_rows,
        "grid_col": grid_cols,
        "latitude": np.asarray(lat, dtype=float),
        "longitude": np.asarray(lon, dtype=float),
    })
    if len(out) != EXPECTED_CORE_CELLS:
        raise ValueError(
            f"CIR06 smoke core geometry drifted: expected {EXPECTED_CORE_CELLS}, got {len(out)}"
        )
    if out[["grid_row", "grid_col"]].duplicated().any():
        raise AssertionError("CIR06 smoke fine grid contains duplicate row/col pairs")
    return out


def padded_retrieval_bounds(latitude: float, longitude: float) -> tuple[float, float, float, float]:
    margin = derived_retrieval_margin_m()
    forward = _forward_transformer()
    inverse = Transformer.from_crs(
        CRS.from_proj4(PROJ_STRING),
        "EPSG:4326",
        always_xy=True,
    )
    x0, y0 = forward.transform(float(longitude), float(latitude))
    radius = RADIUS_M + margin
    corners = [
        (x0 - radius, y0 - radius),
        (x0 - radius, y0 + radius),
        (x0 + radius, y0 - radius),
        (x0 + radius, y0 + radius),
    ]
    lon, lat = inverse.transform(
        np.asarray([x for x, _ in corners], dtype=float),
        np.asarray([y for _, y in corners], dtype=float),
    )
    return (
        float(np.min(lon)),
        float(np.min(lat)),
        float(np.max(lon)),
        float(np.max(lat)),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(
    order_csv_gz: Path,
    terrain_csv_gz: Path,
    *,
    cache_root: Path,
) -> dict[str, Any]:
    contract = _contract()
    order = pd.read_csv(order_csv_gz, low_memory=False)
    terrain = pd.read_csv(terrain_csv_gz, low_memory=False)
    centers = _select_centers(order, terrain, UNIT, production=True)
    center = centers.iloc[0]
    center_id = str(center["candidate_cell_id"])
    if center_id != EXPECTED_CENTER_ID:
        raise ValueError(f"CIR06 rank-1 center drifted: {center_id}")

    lat = float(center["latitude"])
    lon = float(center["longitude"])
    core = build_core_grid(lat, lon)
    bounds = padded_retrieval_bounds(lat, lon)

    cache_root = Path(cache_root).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ["GBIF_FIELDMAP_CACHE"] = str(cache_root)

    try:
        from gbif_fieldmap_builder_app import build_gsi_dem_for_bounds
        dem_path, attribution = build_gsi_dem_for_bounds(
            bounds,
            reference_coordinates=((lat, lon),),
        )
    except Exception as exc:
        return {
            "schema_version": "cirsium-fresh-sentinel-v2-cir06-fine-terrain-smoke-result-v1",
            "status": "INDETERMINATE_GSI_PROVIDER_FAILURE",
            "cohort_unit_id": UNIT,
            "center_candidate_cell_id": center_id,
            "core_cell_count": int(len(core)),
            "retrieval_margin_m": derived_retrieval_margin_m(),
            "provider_error_class": type(exc).__name__,
            "provider_error_message": str(exc)[:500],
            "provider_failure_is_biological_negative": False,
            "alternate_provider_used": False,
            "structural_graph_computed": False,
            "field_outcomes_opened": False,
        }

    if not dem_path:
        return {
            "schema_version": "cirsium-fresh-sentinel-v2-cir06-fine-terrain-smoke-result-v1",
            "status": "INDETERMINATE_GSI_PROVIDER_FAILURE",
            "cohort_unit_id": UNIT,
            "center_candidate_cell_id": center_id,
            "core_cell_count": int(len(core)),
            "retrieval_margin_m": derived_retrieval_margin_m(),
            "provider_error_class": "NO_GSI_DEM_RETURNED",
            "provider_error_message": "",
            "provider_failure_is_biological_negative": False,
            "alternate_provider_used": False,
            "structural_graph_computed": False,
            "field_outcomes_opened": False,
        }

    dem = Path(dem_path)
    try:
        from research.build_cirsium_private_alpine_local_grid_v1 import _sample_terrain
        sampled = _sample_terrain(core, dem)
    except Exception as exc:
        return {
            "schema_version": "cirsium-fresh-sentinel-v2-cir06-fine-terrain-smoke-result-v1",
            "status": "INDETERMINATE_TERRAIN_SAMPLING_FAILURE",
            "cohort_unit_id": UNIT,
            "center_candidate_cell_id": center_id,
            "core_cell_count": int(len(core)),
            "retrieval_margin_m": derived_retrieval_margin_m(),
            "gsi_attribution": str(attribution),
            "dem_sha256": _sha256(dem),
            "sampling_error_class": type(exc).__name__,
            "sampling_error_message": str(exc)[:500],
            "sampling_failure_is_biological_negative": False,
            "alternate_provider_used": False,
            "structural_graph_computed": False,
            "field_outcomes_opened": False,
        }

    missing = sorted(set(REQUIRED).difference(sampled.columns))
    if missing:
        raise AssertionError(f"fine terrain smoke missing required columns: {missing}")
    required_values = sampled.loc[:, REQUIRED].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    if not np.isfinite(required_values).all():
        raise AssertionError("terrain-complete smoke rows contain non-finite required values")

    complete = int(len(sampled))
    return {
        "schema_version": "cirsium-fresh-sentinel-v2-cir06-fine-terrain-smoke-result-v1",
        "status": "CIR06_FINE_TERRAIN_SMOKE_COMPLETE",
        "cohort_unit_id": UNIT,
        "center_candidate_cell_id": center_id,
        "core_cell_count": int(len(core)),
        "terrain_complete_cell_count": complete,
        "terrain_incomplete_cell_count": int(len(core) - complete),
        "terrain_complete_fraction": float(complete / len(core)),
        "retrieval_margin_m": derived_retrieval_margin_m(),
        "retrieval_bounds_wgs84": [float(x) for x in bounds],
        "gsi_attribution": str(attribution),
        "dem_sha256": _sha256(dem),
        "required_terrain_columns": list(REQUIRED),
        "production_default_max_tiles": int(contract["terrain_source"]["production_default_max_tiles"]),
        "provider_failure_is_biological_negative": False,
        "alternate_provider_used": False,
        "ecological_ranking_computed": False,
        "structural_graph_computed": False,
        "field_outcomes_opened": False,
        "private_exact_site_used": False,
        "p02_result_used": False,
        "access_or_budget_used": False,
        "next_gate": "If source mechanics are usable, freeze blockwise full-CIR06 fine-terrain attachment before any structural graph.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-csv-gz", type=Path, required=True)
    parser.add_argument("--terrain-csv-gz", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.order_csv_gz, args.terrain_csv_gz, cache_root=args.cache_root)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
