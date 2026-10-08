#!/usr/bin/env python3
"""Hash private GSI PNG tiles and constructed DEM mosaics without opening outcomes.

This audit is read-only: no source/provider retry, source override, new habitat
prediction, selection cutoff or field coordinates. The public receipt exposes
only whole-inventory hashes and counts, never tile XYZ identifiers or paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "validation" /
    "coverage_then_fine_structure_fresh_sentinel_v2_gsi_cache_provenance_v1.json"
)
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inventory(cache_dir: Path, glob_pattern: str) -> tuple[int, int, str]:
    paths = sorted(cache_dir.glob(glob_pattern), key=lambda p: p.relative_to(cache_dir).as_posix())
    if not paths:
        raise ValueError("missing required GSI source-cache object category")
    count = 0
    byte_count = 0
    digest = hashlib.sha256()
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("source cache contains a nonregular or symlinked object")
        relative = path.relative_to(cache_dir).as_posix()
        file_size = path.stat().st_size
        if file_size <= 0:
            raise ValueError("GSI cache contains empty source object")
        # Paths are used only inside the SHA256 calculation. They are never
        # published, even though official GSI tile paths contain XYZ indices.
        digest.update(
            (relative + "\t" + _hash_file(path) + "\n").encode("utf-8")
        )
        count += 1
        byte_count += int(file_size)
    return count, byte_count, digest.hexdigest()


def audit_gsi_cache_provenance(cache_dir: Path, *, unit_id: str) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_READ_ONLY_GSI_CACHE_CONTENT_AUDIT":
        raise ValueError("GSI cache content audit contract is not frozen")
    if tuple(contract.get("cohort_unit_ids") or ()) != UNITS:
        raise ValueError("GSI cache audit cohort changed")
    if contract.get("read_only") is not True or contract.get("promotion_authorized") is not False:
        raise ValueError("GSI cache audit cannot change source or promote a selector")
    if contract.get("scan_categories") != {
        "gsi_png_tiles": "gsi_dem_tiles/**/*.png",
        "constructed_gsi_mosaics": "app_layers/gsi_*.tif",
    }:
        raise ValueError("GSI cache provenance inventory scope drifted")
    if unit_id not in UNITS:
        raise ValueError("unknown GSI cohort unit")
    cache_dir = Path(cache_dir).resolve()
    if _inside_repo(cache_dir) or not cache_dir.is_dir():
        raise ValueError("private GSI cache directory must exist outside the repository")

    tiles = _inventory(cache_dir, contract["scan_categories"]["gsi_png_tiles"])
    mosaics = _inventory(cache_dir, contract["scan_categories"]["constructed_gsi_mosaics"])
    return {
        "schema_version": "cirsium-fresh-sentinel-v2-gsi-cache-content-fingerprint-v1",
        "status": "GSI_RAW_CACHE_CONTENT_INVENTORY_AUDITED_PRE_OUTCOME",
        "cohort_unit_id": unit_id,
        "tile_file_count": tiles[0],
        "tile_total_bytes": tiles[1],
        "tile_inventory_sha256": tiles[2],
        "mosaic_file_count": mosaics[0],
        "mosaic_total_bytes": mosaics[1],
        "mosaic_inventory_sha256": mosaics[2],
        "files_read_only": True,
        "coordinate_bearing_filenames_exported": False,
        "source_png_bytes_pinned_to_release_version": False,
        "field_outcomes_opened": False,
        "terrain_values_changed_by_audit": False,
        "field_selector_validation": False,
        "interpretation": (
            "Inventory-level fingerprints of the exact private GSI cache in "
            "this execution; comparison with another identically scoped run "
            "may identify byte changes upstream of the terrain sampler."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", required=True, choices=UNITS)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--public-safe-summary-json", required=True, type=Path)
    args = parser.parse_args()
    if args.public_safe_summary_json.exists():
        raise SystemExit("refusing to overwrite existing GSI cache audit receipt")
    result = audit_gsi_cache_provenance(args.cache_dir, unit_id=args.unit_id)
    args.public_safe_summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.public_safe_summary_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "unit_id": args.unit_id,
        "tile_file_count": result["tile_file_count"],
        "mosaic_file_count": result["mosaic_file_count"],
        "field_outcomes_opened": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
