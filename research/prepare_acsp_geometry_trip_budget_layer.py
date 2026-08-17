#!/usr/bin/env python3
"""Prepare outcome-free GSI land geometry for ACSP trip-budget validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

EXPECTED_PROTOCOL = "6bd7c35e2e3de369088691ebe8861d0578f5933374895fe06cb390bfe9a4383f"


def canonical(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"protocol fingerprint mismatch: file={expected} calculated={calculated} expected={EXPECTED_PROTOCOL}"
        )
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--island", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol, fingerprint = canonical(args.protocol)
    cells = {str(row["island_id"]): row for row in protocol["island_cells"]}
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
        max_tiles=int(protocol["candidate_surface"]["gsi_max_tiles_per_island"]),
    )
    if not dem_path:
        raise RuntimeError(f"no GSI DEM for {args.island}")
    dem_out = args.out / "dem.tif"
    shutil.copy2(dem_path, dem_out)

    manifest = {
        "status": "public_geometry_ready",
        "island_id": args.island,
        "bounds": list(bounds),
        "protocol_fingerprint": fingerprint,
        "gsi": {
            "attribution": attribution,
            "sha256": sha256_file(dem_out),
            "bytes": dem_out.stat().st_size,
        },
        "taxon_occurrences_read": False,
        "taxon_outcomes_read": False,
        "environmental_support_modifier_read": False,
    }
    (args.out / "layer_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
