#!/usr/bin/env python3
"""Read-only stage fingerprints from selected *real* CIR02 GSI mosaics.

At three prospectively fixed 40-km chunks, select up to 24 originally
source-complete candidates by sorted IDs. The real existing production
terrain_surface is run again only for diagnosis. Hash selected cells'
intermediate slope arrays, never locations, cell identities or raw features.
"""
from __future__ import annotations

import hashlib
import json
import platform
import struct
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.transform import rowcol

from research.audit_cirsium_slope_kernel_synthetic_two_run import (
    STAGES, generate_stage_arrays,
)
from research.audit_cirsium_fresh_sentinel_v2_same_mosaic_numerical_replay import (
    _selected_chunks, _source_complete_candidates, _sha256,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_cir02_real_dem_slope_stage_probe_v1.json"
DECIMALS = (2, 8)


def _contract() -> dict[str, Any]:
    record = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if record.get("status") != "FROZEN_BEFORE_NEW_CIR02_REAL_DEM_STAGE_RUN":
        raise ValueError("CIR02 real DEM diagnostic contract is not frozen")
    if record.get("cohort_unit_id") != "CIR02":
        raise ValueError("CIR02 stage diagnosis may not retarget another taxon")
    if tuple(record.get("stage_order", ())) != STAGES:
        raise ValueError("slope stages differ from production numerical mirror")
    sample = record.get("sample_policy", {})
    if (sample.get("expected_source_chunk_count") != 177 or
        sample.get("max_source_complete_candidates_per_chunk") != 24 or
        sample.get("no_outcome_based_selection") is not True):
        raise ValueError("predeclared CIR02 3x24 sample changed")
    if tuple(record.get("digest_protocol", {}).get("rounded_precision_decimals", ())) != DECIMALS:
        raise ValueError("selected stage precision changed")
    for k in ("never_change_original_dem_sampler_or_candidate_order",
              "assert_mirrored_kernel_equals_original_production_slope100",
              "assert_first_pass_sampled_slope_equals_staged_surface_for_probed_cells"):
        if record.get("execution", {}).get(k) is not True:
            raise ValueError("real source read-only policy violated")
    for k in ("no_full_structural_order_replay_claim","no_field_selector_or_habitat_claim",
              "no_private_sites_or_field_outcomes","no_posthoc_support_fraction_or_patch_distance_change"):
        if record.get("interpretation", {}).get(k) is not True:
            raise ValueError("scientific claim boundary changed")
    return record


def _surface_coordinates(
    selected: pd.DataFrame, dem_path: Path, shape: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray]:
    if not {"longitude", "latitude", "candidate_cell_id"}.issubset(selected):
        raise ValueError("selected original CIR02 candidates have no source coordinates")
    with rasterio.open(dem_path) as src:
        if src.crs is None:
            raise ValueError("source GSI DEM lacks CRS")
        factor = max(1, int(round(25.0 / abs(src.res[0]))))
        height, width = max(1, src.height // factor), max(1, src.width // factor)
        transform = src.transform * src.transform.scale(
            src.width / width, src.height / height,
        )
        if (height, width) != shape:
            raise ValueError("staged DEM raster dimensions drifted")
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        xs, ys = transformer.transform(
            selected["longitude"].to_numpy(float),
            selected["latitude"].to_numpy(float),
        )
        rr, cc = rowcol(transform, xs, ys)
    rows = np.asarray(rr, dtype=np.int64)
    cols = np.asarray(cc, dtype=np.int64)
    if not np.all((rows >= 0) & (rows < shape[0]) & (cols >= 0) & (cols < shape[1])):
        raise ValueError("original source-complete selected candidate fell outside the DEM")
    return rows, cols


class CIR02RealDEMSlopeStageCollector:
    def __init__(self) -> None:
        _contract()
        self._source_chunk_count: int | None = None
        self._seen: set[int] = set()
        self._sha_exact = {
            stage: hashlib.sha256(("CIR02_REAL_SLOPE_STAGE_" + stage + "_EXACT_V1\n").encode())
            for stage in STAGES
        }
        self._sha_rounded = {
            stage: {
                p: hashlib.sha256(
                    (f"CIR02_REAL_SLOPE_STAGE_{stage}_DECIMAL_{p}_V1\n").encode()
                ) for p in DECIMALS
            } for stage in STAGES
        }
        self._selected_source = hashlib.sha256(b"CIR02_SELECTED_3_CHUNKS_SOURCE_CONTENT_V1\n")
        self._source_complete_tested = 0

    def __call__(
        self, chunk_index: int, total_chunks: int,
        component: pd.DataFrame, sampled: pd.DataFrame, mosaic_path: Path,
    ) -> None:
        _contract()
        if total_chunks != 177 or (
            self._source_chunk_count is not None and self._source_chunk_count != total_chunks
        ):
            raise ValueError("CIR02 real source chunk denominator changed")
        self._source_chunk_count = total_chunks
        if chunk_index not in _selected_chunks(total_chunks):
            return
        if chunk_index in self._seen:
            raise ValueError("duplicate original selected source chunk")
        self._seen.add(chunk_index)
        path = Path(mosaic_path)
        if path.is_symlink() or not path.is_file():
            raise ValueError("original read-only source DEM missing or a symlink")
        original_sha = _sha256(path)
        stages, _ = generate_stage_arrays(path)
        if _sha256(path) != original_sha:
            raise ValueError("CIR02 real source DEM bytes changed during stage audit")
        ids = _source_complete_candidates(sampled)
        if not ids:
            raise ValueError("selected original source-complete candidate group is empty")
        original = sampled.set_index(sampled["candidate_cell_id"].astype(str))
        cells = component.set_index(component["candidate_cell_id"].astype(str))
        if not original.index.is_unique or not cells.index.is_unique:
            raise ValueError("private real source IDs duplicated")
        if not set(ids).issubset(cells.index):
            raise ValueError("predeclared source candidates missing from actual chunk")
        locations = cells.loc[ids].reset_index(drop=False)
        rows, cols = _surface_coordinates(locations, path, stages[STAGES[0]].shape)
        original_slope = original.loc[ids, "slope100"].to_numpy(dtype=np.float64)
        staged_slope = np.asarray(stages["slope100"][rows, cols], dtype=np.float64)
        if not np.array_equal(original_slope, staged_slope, equal_nan=True):
            raise ValueError("real original CIR02 sampled slope disagrees with diagnostic mirror")
        if not np.isfinite(original_slope).all():
            raise ValueError("original source-complete CIR02 slope contains nonfinite values")
        # Hash each sampled stage value in the original source IDs' stable
        # sorted order. No per-chunk hashes or IDs enter the public result.
        self._selected_source.update(
            (f"chunk={chunk_index}\t{original_sha}\n").encode("ascii")
        )
        for stage in STAGES:
            values = np.asarray(stages[stage][rows, cols], dtype=np.float64)
            if not np.isfinite(values).all():
                raise ValueError(f"nonfinite source-complete CIR02 slope stage: {stage}")
            for ident, numeric in zip(ids, values):
                prefix = ident.encode("utf-8") + b"\t"
                self._sha_exact[stage].update(prefix + struct.pack("<d", float(numeric)) + b"\n")
                for precision in DECIMALS:
                    self._sha_rounded[stage][precision].update(
                        prefix + format(float(numeric), f".{precision}f").encode("ascii") + b"\n"
                    )
        self._source_complete_tested += len(ids)

    def summary(self, *, unit_id: str, source_chunk_count: int) -> dict[str, Any]:
        _contract()
        if unit_id != "CIR02" or source_chunk_count != 177:
            raise ValueError("CIR02 diagnostic must use its original fixed chunk policy")
        expected = _selected_chunks(source_chunk_count)
        if not self._seen.issubset(expected):
            raise ValueError("source chunk selection deviated from frozen rule")
        complete = set(expected) == self._seen
        return {
            "schema_version": "cirsium-fresh-sentinel-v2-real-dem-slope-stages-v1",
            "status": (
                "ORIGINAL_REAL_DEM_CIR02_THREE_CHUNK_STAGE_AUDIT_COMPLETE"
                if complete else "ORIGINAL_REAL_DEM_STAGE_SAMPLING_INCOMPLETE"
            ),
            "cohort_unit_id": unit_id,
            "source_chunk_count": source_chunk_count,
            "predeclared_selected_chunk_count": len(expected),
            "probed_chunk_count": len(self._seen),
            "source_complete_cells_probed": self._source_complete_tested,
            "all_predeclared_chunks_eligible": complete,
            "sampled_mosaics_content_order_sha256": (
                self._selected_source.hexdigest() if self._seen else None
            ),
            "stages_exact_float64_sha256": {
                name: obj.hexdigest() for name, obj in self._sha_exact.items()
            } if complete else {},
            "stages_decimal_sha256": {
                name: {str(p): h.hexdigest() for p, h in hashes.items()}
                for name, hashes in self._sha_rounded.items()
            } if complete else {},
            "stage_sampled_individual_coordinates_or_ids_public": False,
            "individual_slope_values_public": False,
            "per_chunk_stage_hashes_public": False,
            "primary_source_selection_or_sampled_vectors_changed": False,
            "field_outcomes_opened": False,
            "all_177_chunks_or_actual_historical_CIR02_cause_reproduced": False,
            "native_python_patch_version": platform.python_version(),
        }
