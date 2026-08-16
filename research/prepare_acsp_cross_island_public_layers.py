#!/usr/bin/env python3
"""Prepare public GSI land and ESA NDVI layers for one frozen island cell.

This script is outcome-free. It reads only the frozen execution/cohort protocols
and public raster sources. It does not read selected-taxon occurrence rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

import rasterio
from rasterio.merge import merge

EXPECTED_EXECUTION = "24a5cc0d21bcfd4fdfce5dc9b8ccbb2cd8dc1fc717928d8ed6775c79ef8591e1"
EXPECTED_COHORT = "7bc745ffbcaa23146c56f61e9cf3a1c2ba22bd28cc4ad37468b9b6b726520a65"


def canonical_fingerprint(path: Path, field: str = "protocol_fingerprint") -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop(field, ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated:
        raise ValueError(f"fingerprint mismatch for {path}: file={expected} calculated={calculated}")
    payload[field] = expected
    return payload, calculated


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ndvi_key(lat_degree: int, lon_degree: int) -> str:
    if lat_degree < 0 or lon_degree < 0:
        raise ValueError("Japan confirmation protocol expects N/E ESA tiles")
    stem = f"N{lat_degree:02d}E{lon_degree:03d}"
    return f"ndvi/2021/N{lat_degree:02d}/ESA_WorldCover_10m_2021_v200_{stem}_NDVI.tif"


def required_ndvi_keys(bounds: tuple[float, float, float, float], margin: float = 0.02) -> list[str]:
    west, south, east, north = bounds
    lat0 = math.floor(south - margin)
    lat1 = math.floor(north + margin)
    lon0 = math.floor(west - margin)
    lon1 = math.floor(east + margin)
    return [
        ndvi_key(lat, lon)
        for lat in range(lat0, lat1 + 1)
        for lon in range(lon0, lon1 + 1)
    ]


def aws_copy(key: str, target: Path, attempts: int = 4) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return
    last = None
    for attempt in range(attempts):
        proc = subprocess.run(
            [
                "aws", "s3", "cp",
                f"s3://esa-worldcover-s2/{key}",
                str(target),
                "--no-sign-request",
            ],
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0 and target.exists() and target.stat().st_size > 0:
            return
        last = (proc.returncode, proc.stdout[-1000:], proc.stderr[-1000:])
        if target.exists():
            target.unlink()
        if attempt + 1 < attempts:
            time.sleep(min(20.0, 2.0 * (2 ** attempt)))
    raise RuntimeError(f"ESA NDVI download failed for {key}: {last}")


def build_ndvi_mosaic(keys: list[str], tile_dir: Path, bounds, output: Path) -> list[dict]:
    paths = []
    sources = []
    for key in keys:
        local = tile_dir / Path(key).name
        aws_copy(key, local)
        paths.append(local)
        sources.append({"s3_key": key, "sha256": sha256_file(local), "bytes": local.stat().st_size})

    west, south, east, north = map(float, bounds)
    crop_bounds = (west - 0.02, south - 0.02, east + 0.02, north + 0.02)
    datasets = [rasterio.open(path) for path in paths]
    try:
        mosaic, transform = merge(datasets, bounds=crop_bounds)
        if mosaic.shape[0] < 3:
            raise RuntimeError(f"ESA NDVI mosaic has {mosaic.shape[0]} bands; expected >=3")
        profile = datasets[0].profile.copy()
        profile.update(
            driver="GTiff",
            height=mosaic.shape[1],
            width=mosaic.shape[2],
            transform=transform,
            count=mosaic.shape[0],
            compress="deflate",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output, "w", **profile) as dst:
            dst.write(mosaic)
    finally:
        for src in datasets:
            src.close()
    return sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-protocol", type=Path, required=True)
    parser.add_argument("--cohort-protocol", type=Path, required=True)
    parser.add_argument("--island", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    execution, execution_fp = canonical_fingerprint(args.execution_protocol)
    cohort, cohort_fp = canonical_fingerprint(args.cohort_protocol)
    if execution_fp != EXPECTED_EXECUTION:
        raise ValueError(f"unexpected execution protocol: {execution_fp}")
    if cohort_fp != EXPECTED_COHORT:
        raise ValueError(f"unexpected cohort protocol: {cohort_fp}")

    cells = {str(row["island_id"]): row for row in cohort["scope"]["island_cells"]}
    if args.island not in cells:
        raise KeyError(f"unknown island cell {args.island!r}")
    cell = cells[args.island]
    bounds = tuple(float(cell[key]) for key in ("west", "south", "east", "north"))

    args.out.mkdir(parents=True, exist_ok=True)
    cache = args.out / "gsi-cache"
    os.environ["GBIF_FIELDMAP_CACHE"] = str(cache)
    # Import only after setting the cache root; the production module resolves
    # CACHE_DIR at import time.
    from gbif_fieldmap_builder_app import build_gsi_dem_for_bounds

    reference = (((bounds[1] + bounds[3]) / 2.0, (bounds[0] + bounds[2]) / 2.0),)
    dem_path, attribution = build_gsi_dem_for_bounds(
        bounds,
        reference_coordinates=reference,
        max_tiles=int(execution["public_layers"]["gsi_max_tiles_per_island"]),
    )
    if not dem_path:
        raise RuntimeError(f"no GSI DEM could be built for {args.island}")
    dem_output = args.out / "dem.tif"
    shutil.copy2(dem_path, dem_output)

    keys = required_ndvi_keys(bounds)
    ndvi_output = args.out / "ndvi.tif"
    ndvi_sources = build_ndvi_mosaic(keys, args.out / "ndvi-source", bounds, ndvi_output)

    manifest = {
        "island_id": args.island,
        "bounds": list(bounds),
        "execution_protocol_fingerprint": execution_fp,
        "cohort_protocol_fingerprint": cohort_fp,
        "gsi": {
            "attribution": attribution,
            "sha256": sha256_file(dem_output),
            "bytes": dem_output.stat().st_size,
        },
        "esa_ndvi": {
            "sources": ndvi_sources,
            "mosaic_sha256": sha256_file(ndvi_output),
            "mosaic_bytes": ndvi_output.stat().st_size,
        },
        "selected_taxon_occurrences_read": False,
        "heldout_outcomes_read": False,
    }
    (args.out / "layer_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
