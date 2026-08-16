#!/usr/bin/env python3
"""Prepare outcome-free public layers for one operational-budget development island."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

from prepare_acsp_cross_island_public_layers import (
    build_ndvi_mosaic,
    required_ndvi_keys,
    sha256_file,
)

EXPECTED_DEVELOPMENT = "877cc5f4240ce5ab19c45bf16bde42eb9a32405df55c03dcf74267503d470450"
EXPECTED_COHORT = "00916d8eb5755c4bea19a415615c9b46fdb69804b22e97146f03565692d73b79"


def canonical(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated:
        raise ValueError(f"fingerprint mismatch: {path}")
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-protocol", type=Path, required=True)
    parser.add_argument("--cohort-protocol", type=Path, required=True)
    parser.add_argument("--island", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    development, development_fp = canonical(args.development_protocol)
    cohort, cohort_fp = canonical(args.cohort_protocol)
    if development_fp != EXPECTED_DEVELOPMENT:
        raise ValueError(f"unexpected development protocol {development_fp}")
    if cohort_fp != EXPECTED_COHORT:
        raise ValueError(f"unexpected cohort protocol {cohort_fp}")
    cells = {str(row["island_id"]): row for row in cohort["scope"]["island_cells"]}
    if args.island not in cells:
        raise KeyError(args.island)
    cell = cells[args.island]
    bounds = tuple(float(cell[key]) for key in ("west", "south", "east", "north"))

    args.out.mkdir(parents=True, exist_ok=True)
    os.environ["GBIF_FIELDMAP_CACHE"] = str(args.out / "gsi-cache")
    from gbif_fieldmap_builder_app import build_gsi_dem_for_bounds

    reference = (((bounds[1] + bounds[3]) / 2.0, (bounds[0] + bounds[2]) / 2.0),)
    dem_path, attribution = build_gsi_dem_for_bounds(
        bounds,
        reference_coordinates=reference,
        max_tiles=int(development["public_layers"]["gsi_max_tiles_per_island"]),
    )
    if not dem_path:
        raise RuntimeError(f"no GSI DEM for {args.island}")
    dem_out = args.out / "dem.tif"
    shutil.copy2(dem_path, dem_out)

    keys = required_ndvi_keys(bounds)
    ndvi_out = args.out / "ndvi.tif"
    sources = build_ndvi_mosaic(keys, args.out / "ndvi-source", bounds, ndvi_out)
    manifest = {
        "island_id": args.island,
        "bounds": list(bounds),
        "development_protocol_fingerprint": development_fp,
        "cohort_protocol_fingerprint": cohort_fp,
        "gsi": {"attribution": attribution, "sha256": sha256_file(dem_out), "bytes": dem_out.stat().st_size},
        "esa_ndvi": {"sources": sources, "mosaic_sha256": sha256_file(ndvi_out), "mosaic_bytes": ndvi_out.stat().st_size},
        "selected_taxon_occurrences_read": False,
        "heldout_outcomes_read": False,
    }
    (args.out / "layer_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
