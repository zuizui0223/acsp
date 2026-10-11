#!/usr/bin/env python3
"""Coordinate-free synthetic kernel test: locate the first non-reproduced slope stage.

The actual GSI attachment, terrain sampling, ranking and frozen patches are
completely untouched. Input raster data are generated from deterministic
integer arithmetic, not any candidate-site or provider data. Stage formulas
mirror the *existing* production terrain_surface implementation, with a
mandatory exact equality check against its slope100 output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import scipy
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from scipy.ndimage import uniform_filter

from research.campanula_microterrain_discovery import terrain_surface

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_synthetic_slope_kernel_two_run_v1.json"
STAGES = (
    "resampled_elevation", "local_mean100", "filled_elevation",
    "gradient_dx", "gradient_dy", "instantaneous_slope",
    "slope_valid_support", "slope_smoothing_numerator", "slope100",
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as src:
        for piece in iter(lambda: src.read(4 * 1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def _fingerprint(values: np.ndarray, *, decimals: int = 8) -> str:
    data = np.asarray(values, dtype=np.float64)
    if np.isinf(data).any():
        raise ValueError("nonfinite synthetic terrain stage inf values forbidden")
    # Canonical NaN payload and byte order; include mask and dimensions so
    # NaN-filled regions are not mistaken for valid physical data.
    mask = np.isfinite(data)
    safe = np.where(mask, data, 0.0)
    safe = np.round(safe, decimals=decimals).astype("<f8", copy=False)
    digest = hashlib.sha256()
    digest.update(str(data.shape).encode("ascii") + b"\n")
    digest.update(np.ascontiguousarray(mask, dtype=np.uint8).tobytes())
    digest.update(np.ascontiguousarray(safe).tobytes())
    return digest.hexdigest()


def validate_contract() -> None:
    c = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if c.get("status") != "FROZEN_BEFORE_TWO_INDEPENDENT_SYNTHETIC_RUNNER_JOBS":
        raise ValueError("synthetic slope diagnostic is not frozen")
    if c.get("stages") != list(STAGES):
        raise ValueError("synthetic slope stage identities changed")
    if c.get("precision_decimals") != 8 or c.get("run_count") != 2:
        raise ValueError("synthetic slope precision or number of jobs changed")
    if c.get("synthetic_input", {}).get("seed_or_randomness_used") is not False:
        raise ValueError("synthetic diagnostic may not use randomized source inputs")
    for key in (
        "no_private_dem_or_coords_exported",
        "no_field_outcomes_opened",
        "no_change_to_original_GSI_pipeline",
        "no_change_to_structural_selector",
        "no_2p5pct_or_1km_rule_changed",
    ):
        if c.get(key) is not True:
            raise ValueError(f"unsafe synthetic slope contract: {key}")


def synthesize_mosaic(path: Path) -> str:
    """Produce reproducible DEM tile with gradient, step terrain and nodata."""
    validate_contract()
    c = json.loads(CONTRACT.read_text(encoding="utf-8"))
    width = c["synthetic_input"]["width"]
    height = c["synthetic_input"]["height"]
    resolution = c["synthetic_input"]["resolution_m"]
    if (height, width, resolution) != (288, 288, 25):
        raise ValueError("synthetic terrain grid changed")
    y = np.arange(height, dtype=np.int64)[:, None]
    x = np.arange(width, dtype=np.int64)[None, :]
    numerators = 100_000 + 7 * x + 11 * y + 43 * ((x // 11) % 4) + 67 * ((y // 7) % 5)
    data = (numerators / 1000.0).astype(np.float32)
    # Keep nodata separated from sample field sites (synthetic grid only).
    data[24:39, 80:115] = np.float32(-9999)
    data[192:203, 190:230] = np.float32(-9999)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", width=width, height=height,
        count=1, dtype="float32", crs="EPSG:3857",
        transform=from_origin(15_500_000.0, 4_200_000.0, resolution, resolution),
        nodata=-9999.0, compress="deflate", tiled=True,
    ) as dst:
        dst.write(data, 1)
    return _sha(path)


def generate_stage_arrays(path: Path) -> tuple[dict[str, np.ndarray], str]:
    """Mirror *existing* terrain_surface math and compare final kernel output."""
    with rasterio.open(path) as src:
        factor = max(1, int(round(25.0 / abs(src.res[0]))))
        height = max(1, src.height // factor)
        width = max(1, src.width // factor)
        elevation = src.read(
            1, out_shape=(height, width), resampling=Resampling.average,
        ).astype("float32")
        transform = src.transform * src.transform.scale(
            src.width / width, src.height / height,
        )
        if src.nodata is not None:
            elevation[elevation == src.nodata] = np.nan
        elevation[elevation < -1000] = np.nan
        resolution = float(abs(transform.a))
        valid = np.isfinite(elevation).astype("float32")
        zero_filled = np.nan_to_num(elevation, nan=0.0)
        size100 = max(3, int(round(200 / resolution)) | 1)
        support = uniform_filter(valid, size=size100, mode="nearest")
        total = uniform_filter(zero_filled, size=size100, mode="nearest")
        with np.errstate(divide="ignore", invalid="ignore"):
            mean100 = np.where(support > 1e-6, total / support, np.nan)
        filled = np.where(np.isfinite(elevation), elevation, mean100)
        dy, dx = np.gradient(filled, resolution, resolution)
        slope = np.degrees(np.arctan(np.sqrt(dx * dx + dy * dy)))
        slope_valid = np.isfinite(slope).astype("float32")
        slope_zero = np.nan_to_num(slope, nan=0.0)
        slope_support = uniform_filter(slope_valid, size100)
        numerator = uniform_filter(slope_zero, size100)
        with np.errstate(divide="ignore", invalid="ignore"):
            slope100 = np.where(slope_support > 1e-6, numerator / slope_support, np.nan)
    production = terrain_surface(path, target_res=25.0)
    if not np.array_equal(production["slope100"], slope100, equal_nan=True):
        raise ValueError("mirror's synthetic slope result disagrees with production terrain_surface")
    if not np.array_equal(production["arr"], elevation, equal_nan=True):
        raise ValueError("mirror's synthetic elevation differs from production")
    stages = dict(zip(STAGES, (
        elevation, mean100, filled, dx, dy, slope,
        slope_support, numerator, slope100,
    )))
    return stages, _fingerprint(elevation)


def audit_synthetic_slope(path: Path) -> dict[str, Any]:
    validate_contract()
    tif_sha = synthesize_mosaic(path)
    stages, raster_fingerprint = generate_stage_arrays(path)
    first = {name: _fingerprint(array) for name, array in stages.items()}
    again, second_raster_fingerprint = generate_stage_arrays(path)
    second = {name: _fingerprint(array) for name, array in again.items()}
    after = _sha(path)
    if after != tif_sha or raster_fingerprint != second_raster_fingerprint:
        raise ValueError("synthetic source bytes or resampled elevation changed")
    if first != second:
        raise ValueError("slope stages differ in one process from same synthetic DEM")
    return {
        "schema_version": "cirsium-synthetic-slope-kernel-stage-replay-v1",
        "status": "SYNTHETIC_SLOPE_STAGE_DOUBLE_REPLAY_CONSISTENT",
        "source_dem_byte_sha256": tif_sha,
        "source_resampled_elevation_sha256": raster_fingerprint,
        "stage_sha256": first,
        "stage_count": len(first),
        "native_versions": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "rasterio": rasterio.__version__,
            "rasterio_gdal": rasterio.__gdal_version__,
            "runner_image": os.environ.get("ImageVersion", "local"),
            "openblas_num_threads": os.environ.get("OPENBLAS_NUM_THREADS", "unset"),
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS", "unset"),
        },
        "replay_same_process_exact": True,
        "synthetic_stage_source_compared_to_production": True,
        "private_dem_or_candidate_locations_opened": False,
        "prospective_field_outcomes_opened": False,
        "real_CIR02_root_cause_identified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--synthetic-dem", type=Path, required=True)
    args = parser.parse_args()
    if args.out_json.exists() or args.synthetic_dem.exists():
        raise SystemExit("refusing to overwrite synthetic DEM or public diagnostic")
    result = audit_synthetic_slope(args.synthetic_dem)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "stage_count": result["stage_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
