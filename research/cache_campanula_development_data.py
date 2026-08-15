"""Cache the Campanula microdonta development dataset.

This needs live GBIF and GSI access, so it is meant to run on a GitHub Actions
runner rather than in a network-restricted environment. Run it through the
`campanula-development-data` workflow.

It reuses the existing temporal-external-validation pipeline rather than
reimplementing candidate generation, and writes small artifacts that let
`research/campanula_development_loop.py` iterate completely offline:

    field_validation/campanula_microdonta/development_data/
        gbif_training_occurrences_through_2025.csv
        candidate_pool.csv
        detection_clusters.csv
        manifest.json

The DEM mosaics are deliberately **not** committed. Across the five islands they
are roughly 215 MB of float32 raster, which does not belong in git. Pass
`--dem-out DIR` to copy them somewhere for upload as a workflow artifact when an
experiment needs to regenerate candidates rather than re-rank the cached pool.

Scientific status: development data. The 2026 field outcomes have already been
inspected, so nothing built from this cache can serve as independent
confirmation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIELD_DIR = REPO_ROOT / "field_validation" / "campanula_microdonta"
DEFAULT_OUT = FIELD_DIR / "development_data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--gbif-cap", type=int, default=2000)
    parser.add_argument(
        "--dem-out",
        type=Path,
        default=None,
        help="Optional directory to copy the GSI DEM mosaics into, for artifact upload.",
    )
    parser.add_argument(
        "--raster-cache",
        type=Path,
        default=Path("/tmp/campanula_dev_cache"),
        help="Where the app should cache GSI tiles while building candidates.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()

    # The app reads its cache location at import time, so set it before importing.
    args.raster_cache.mkdir(parents=True, exist_ok=True)
    os.environ["GBIF_FIELDMAP_CACHE"] = str(args.raster_cache)
    sys.path.insert(0, str(FIELD_DIR))

    import pandas as pd  # noqa: E402  (import after the cache env var is set)

    from acsp.field_validation import cluster_field_detections  # noqa: E402
    import run_temporal_external_validation as pipeline  # noqa: E402

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    print(f"fetching GBIF records for {pipeline.SCIENTIFIC_NAME} through {pipeline.TRAINING_YEAR_MAX} ...")
    occurrences, provenance = pipeline.fetch_historical_gbif(args.gbif_cap)
    occ_path = out / "gbif_training_occurrences_through_2025.csv"
    occurrences.to_csv(occ_path, index=False)
    print(f"  {len(occurrences)} training occurrences -> {occ_path.name}")

    print("building the candidate pool (this downloads GSI terrain per island) ...")
    pool, selected = pipeline.build_frozen_candidates(occurrences, provenance)
    pool_path = out / "candidate_pool.csv"
    pool.to_csv(pool_path, index=False)
    print(f"  {len(pool)} candidates -> {pool_path.name}")

    locations = pd.read_csv(FIELD_DIR / "locations_2026.csv")
    _assignments, clusters = cluster_field_detections(locations, cluster_radius_m=500.0)
    clusters_path = out / "detection_clusters.csv"
    clusters.to_csv(clusters_path, index=False)
    print(f"  {len(clusters)} detection clusters -> {clusters_path.name}")

    dem_files: list[str] = []
    if args.dem_out is not None:
        args.dem_out.mkdir(parents=True, exist_ok=True)
        for tif in sorted((args.raster_cache / "app_layers").glob("*.tif")):
            shutil.copy2(tif, args.dem_out / tif.name)
            dem_files.append(tif.name)
        print(f"  copied {len(dem_files)} DEM mosaics -> {args.dem_out}")

    manifest = {
        "dataset_role": "development_only",
        "why": (
            "The 2026 Campanula microdonta field outcomes were already inspected and "
            "motivated the select_area_balanced_candidates update, so this taxon can no "
            "longer serve as independent confirmation."
        ),
        "scientific_name": pipeline.SCIENTIFIC_NAME,
        "training_year_max": pipeline.TRAINING_YEAR_MAX,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gbif_provenance": provenance,
        "island_bounds": {k: list(v) for k, v in pipeline.ISLAND_BOUNDS.items()},
        "counts": {
            "training_occurrences": int(len(occurrences)),
            "candidate_pool": int(len(pool)),
            "baseline_selected": int(len(selected)),
            "detection_clusters": int(len(clusters)),
        },
        "files": {
            path.name: {"sha256": sha256(path), "bytes": path.stat().st_size}
            for path in (occ_path, pool_path, clusters_path)
        },
        "dem_files_not_committed": dem_files,
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"  manifest -> {manifest_path.name}")
    print("\ndone. iterate with:")
    print("  python research/campanula_development_loop.py --strategy local_topk")


if __name__ == "__main__":
    main()
