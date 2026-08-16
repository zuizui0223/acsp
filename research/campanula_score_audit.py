"""Audit whether the local-habitat score points at the real sites.

A recall number says the ranking failed. It does not say why. This asks four
questions of the score itself, per island:

1. Is the score comparable across islands? A global Top-k concentrates wherever
   the scale is inflated, regardless of within-island signal.
2. Does the score rank real sites above the rest, within one island? Spearman
   against distance-to-nearest-detection-cluster; negative is useful, positive
   means the score points away from the plant.
3. If it is inverted, which terrain variable carries the error?
4. How much of the pool is unrankable, i.e. has no score at all?
5. How many training records fitted each island's profile? Where that count is
   tiny the profile has no spread, every candidate matches, and the scores
   saturate — so a global Top-k follows the islands with the least evidence.

    python research/campanula_score_audit.py --pool dense

Development data only. See campanula_development_loop for why that matters.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.field_validation import haversine_distance_m

import campanula_development_loop as loop
from campanula_ceiling import POOL_FILES

TERRAIN = ("elevation", "slope", "aspect", "roughness", "tpi")


def annotate(pool: pd.DataFrame, clusters: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    lats = clusters["latitude"].to_numpy(dtype=float)
    lons = clusters["longitude"].to_numpy(dtype=float)
    nearest = np.array(
        [
            haversine_distance_m(float(row.latitude), float(row.longitude), lats, lons).min() / 1000.0
            for row in pool.itertuples()
        ]
    )
    out = pool.copy()
    out["distance_km"] = nearest
    out["near_real_site"] = nearest <= radius_km
    return out


def report(pool: pd.DataFrame, radius_km: float) -> None:
    score = loop.SCORE_COL

    print("1. score scale per island — a global Top-k follows the inflated scale")
    scale = pool.groupby("survey_area_id")[score].agg(["count", "median", "max"])
    scale["unscored"] = pool.groupby("survey_area_id")[score].apply(lambda s: int(s.isna().sum()))
    print(scale.round(4).to_string(), "\n")

    ranked = pool.sort_values(score, ascending=False).reset_index(drop=True)
    print("   global top-10:")
    for i, row in ranked.head(10).iterrows():
        mark = "HIT" if row["near_real_site"] else ""
        print(
            f"     {i + 1:2d}. {str(row['survey_area_id']):12s} "
            f"{row[score]:.4f}  {row['distance_km']:6.2f} km {mark}"
        )
    for island in sorted(pool["survey_area_id"].dropna().unique()):
        island_rows = ranked.index[ranked["survey_area_id"] == island]
        hit_rows = ranked.index[(ranked["survey_area_id"] == island) & ranked["near_real_site"]]
        best = f"{int(island_rows.min()) + 1}" if len(island_rows) else "-"
        best_hit = f"{int(hit_rows.min()) + 1}" if len(hit_rows) else "none"
        print(f"     {island:12s} best global rank {best:>4}, best hit {best_hit:>4} of {len(ranked)}")

    print(f"\n2. within-island rank quality — spearman(score, distance); negative is useful")
    for island, sub in pool.groupby("survey_area_id"):
        usable = sub.dropna(subset=[score])
        if len(usable) < 4 or usable["distance_km"].nunique() < 2:
            print(f"   {island:12s} too few scored candidates")
            continue
        rho = usable[score].corr(usable["distance_km"], method="spearman")
        verdict = "useful" if rho < -0.1 else ("INVERTED" if rho > 0.1 else "no signal")
        print(f"   {island:12s} {rho:+.3f}   {verdict}")

    print(f"\n3. terrain of real sites vs the rest (median, within {radius_km:g} km)")
    columns = [c for c in TERRAIN if c in pool.columns]
    if not columns:
        print("   no terrain columns in this pool")
    else:
        for island, sub in pool.groupby("survey_area_id"):
            hits = sub[sub["near_real_site"]]
            misses = sub[~sub["near_real_site"]]
            if hits.empty or misses.empty:
                continue
            print(f"   {island}:")
            for column in columns:
                near = pd.to_numeric(hits[column], errors="coerce").median()
                far = pd.to_numeric(misses[column], errors="coerce").median()
                if pd.isna(near) or pd.isna(far):
                    continue
                print(f"     {column:12s} real {near:9.2f}   rest {far:9.2f}   diff {near - far:+9.2f}")

    unscored = int(pool[score].isna().sum())
    print(
        f"\n4. unrankable: {unscored}/{len(pool)} candidates "
        f"({unscored / max(1, len(pool)):.0%}) have no {score}"
    )


def profile_support(pool: pd.DataFrame, occurrences: pd.DataFrame, island_bounds: dict) -> None:
    """Relate each island's score scale to how many records built its profile.

    The local analogue is fitted per survey area from the training records that
    fall inside it. Where that count is tiny the fitted profile has almost no
    spread, so every candidate matches it and the scores saturate near 1. Where
    it is large the profile has real variance and scores spread down. A global
    Top-k then follows the islands with the *least* evidence.
    """
    score = loop.SCORE_COL
    lat = pd.to_numeric(occurrences.get("_latitude", occurrences.get("latitude")), errors="coerce")
    lon = pd.to_numeric(occurrences.get("_longitude", occurrences.get("longitude")), errors="coerce")
    rows = []
    inside_any = pd.Series(False, index=occurrences.index)
    for name, (west, south, east, north) in island_bounds.items():
        within = lat.between(south, north) & lon.between(west, east)
        inside_any |= within
        sub = pool[pool["survey_area_id"] == name]
        if sub.empty:
            continue
        rows.append(
            {
                "island": name,
                "training_records": int(within.sum()),
                "candidates": int(len(sub)),
                "median_score": round(float(sub[score].median()), 4),
                "score_iqr": round(float(sub[score].quantile(0.75) - sub[score].quantile(0.25)), 4),
            }
        )
    table = pd.DataFrame(rows).sort_values("training_records")
    print("\n5. profile support — how many records fitted each island's analogue")
    print(table.to_string(index=False))
    outside = int((~inside_any).sum())
    print(
        f"   {outside}/{len(occurrences)} training records fall outside every survey area "
        f"and fit no profile at all"
    )
    if len(table) > 2:
        rho = table["training_records"].corr(table["median_score"], method="spearman")
        print(f"   spearman(training_records, median_score) = {rho:+.3f}; -1.0 would mean")
        print("   the score ranks profile tightness rather than habitat")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pool", choices=sorted(POOL_FILES), default="dense")
    parser.add_argument("--radius-km", type=float, default=1.0)
    parser.add_argument("--cache-dir", type=Path, default=loop.CACHE_DIR)
    parser.add_argument("--locations", type=Path, default=loop.LOCATIONS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pool = loop.load_pool(args.cache_dir, POOL_FILES[args.pool])
    clusters = loop.load_detection_clusters(args.locations)
    print(f"pool: {args.pool} ({len(pool)} candidates, {len(clusters)} detection clusters)\n")
    report(annotate(pool, clusters, args.radius_km), args.radius_km)

    import os
    import sys as _sys

    os.environ.setdefault("GBIF_FIELDMAP_CACHE", "/tmp/campanula_audit_cache")
    _sys.path.insert(0, str(loop.DATA_DIR))
    try:
        import run_temporal_external_validation as pipeline
    except Exception as exc:  # pragma: no cover - depends on the app import
        print(f"\n5. profile support unavailable: {exc}")
        return
    profile_support(pool, loop.load_training_occurrences(args.cache_dir), pipeline.ISLAND_BOUNDS)


if __name__ == "__main__":
    main()
