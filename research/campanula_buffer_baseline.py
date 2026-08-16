"""The dumbest control for a coverage claim: circles around known records.

A rule that declares part of an island "supported" and then recovers every field
cluster inside it has to beat the laziest possible rule that does the same
thing — draw a disc of radius r around every training occurrence and declare
that. Without this control, a large enough envelope recovers everything by
construction.

Reports, per radius: how many detection clusters fall within the gate radius of
the buffer, split into novel and already-known, against the union area of the
buffer in square kilometres. Area is the comparable currency, because a declared
cell count times its cell area is an area too.

    python research/campanula_buffer_baseline.py
    python research/campanula_buffer_baseline.py --compare-km2 23.67

Union area is Monte Carlo over the survey rectangles and does not subtract sea,
so the buffer's area is if anything understated as a *land* cost — which makes
this control conservative in the buffer's favour.

Development data only. See campanula_development_loop for why that matters.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.field_validation import haversine_distance_m

import campanula_development_loop as loop

DEFAULT_RADII = (0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 5.5)


def island_bounds() -> dict:
    import os
    import sys

    os.environ.setdefault("GBIF_FIELDMAP_CACHE", "/tmp/campanula_buffer_cache")
    sys.path.insert(0, str(loop.DATA_DIR))
    import run_temporal_external_validation as pipeline

    return pipeline.ISLAND_BOUNDS


def records_inside(occurrences: pd.DataFrame, bounds: dict) -> pd.DataFrame:
    lat = pd.to_numeric(occurrences["_latitude"], errors="coerce")
    lon = pd.to_numeric(occurrences["_longitude"], errors="coerce")
    inside = pd.Series(False, index=occurrences.index)
    for _name, (west, south, east, north) in bounds.items():
        inside |= lat.between(south, north) & lon.between(west, east)
    return occurrences[inside]


def union_area_km2(records: pd.DataFrame, radius_km: float, bounds: dict, *, samples: int, seed: int) -> float:
    if radius_km <= 0:
        return 0.0
    rng = np.random.default_rng(seed)
    lats = records["_latitude"].to_numpy(dtype=float)
    lons = records["_longitude"].to_numpy(dtype=float)
    total = 0.0
    for _name, (west, south, east, north) in bounds.items():
        sample_lat = rng.uniform(south, north, samples)
        sample_lon = rng.uniform(west, east, samples)
        middle = (south + north) / 2.0
        rect_km2 = (north - south) * 111.32 * (east - west) * 111.32 * math.cos(math.radians(middle))
        covered = np.zeros(samples, dtype=bool)
        for lat, lon in zip(lats, lons):
            covered |= haversine_distance_m(lat, lon, sample_lat, sample_lon) <= radius_km * 1000.0
        total += rect_km2 * covered.mean()
    return float(total)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--gate-km", type=float, default=1.0, help="Recovery radius being claimed.")
    parser.add_argument("--novelty-km", type=float, default=1.0)
    parser.add_argument("--radii", type=float, nargs="+", default=list(DEFAULT_RADII))
    parser.add_argument("--samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--compare-km2",
        type=float,
        default=None,
        help="Area of the envelope being checked, e.g. declared cells times cell area.",
    )
    parser.add_argument("--cache-dir", type=Path, default=loop.CACHE_DIR)
    parser.add_argument("--locations", type=Path, default=loop.LOCATIONS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bounds = island_bounds()
    occurrences = loop.load_training_occurrences(args.cache_dir)
    clusters = loop.split_clusters_by_novelty(
        loop.load_detection_clusters(args.locations), occurrences, novelty_km=args.novelty_km
    )
    inside = records_inside(occurrences, bounds)

    lats = occurrences["_latitude"].to_numpy(dtype=float)
    lons = occurrences["_longitude"].to_numpy(dtype=float)
    to_record = np.array(
        [
            haversine_distance_m(float(row.latitude), float(row.longitude), lats, lons).min() / 1000.0
            for row in clusters.itertuples()
        ]
    )
    novel = clusters["novel"].to_numpy(dtype=bool)
    n_all, n_novel = len(clusters), int(novel.sum())

    print(f"training records {len(occurrences)} ({len(inside)} inside the survey rectangles)")
    print(f"clusters {n_all}, of which novel {n_novel} at {args.novelty_km:g} km")
    print(f"gate radius {args.gate_km:g} km\n")
    print(f"{'buffer r':>9} {'area km2':>10} {'recovered':>12} {'novel':>12}")
    rows = []
    for radius in args.radii:
        area = union_area_km2(inside, radius, bounds, samples=args.samples, seed=args.seed)
        reached = to_record <= radius + args.gate_km
        rows.append((radius, area, int(reached.sum()), int((reached & novel).sum())))
        print(
            f"{radius:9.1f} {area:10.2f} {rows[-1][2]:>8d}/{n_all:<3d} {rows[-1][3]:>8d}/{n_novel:<3d}"
        )

    if args.compare_km2 is not None:
        target = args.compare_km2
        complete = [r for r in rows if r[2] == n_all]
        print(f"\nenvelope under test: {target:.2f} km2")
        below = [r for r in rows if r[1] <= target]
        above = [r for r in rows if r[1] > target]
        if below and above:
            lo, hi = below[-1], above[0]
            print(
                f"  at the same area the buffer sits between r={lo[0]:g} "
                f"({lo[2]}/{n_all}, {lo[3]}/{n_novel} novel) and r={hi[0]:g} "
                f"({hi[2]}/{n_all}, {hi[3]}/{n_novel} novel)"
            )
        if complete:
            need = complete[0][1]
            print(f"  buffer needs {need:.2f} km2 for {n_all}/{n_all}, i.e. {need / target:.1f}x the area")
        else:
            print(f"  buffer never reaches {n_all}/{n_all} within the tested radii")


if __name__ == "__main__":
    main()
