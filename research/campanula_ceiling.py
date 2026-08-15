"""Upper bound on detection-cluster recovery, per pool and radius.

Answers the question a ranking experiment cannot: how many of the field
detection clusters could *any* selection reach, and with what budget. If the
maximum at a radius is below the target, no ranking rule can close the gap —
the candidate generator has to change.

    python research/campanula_ceiling.py
    python research/campanula_ceiling.py --pool dense --radii 0.5 1 2

Columns:
    max          clusters within the radius of at least one candidate; exact
    k_for_max    greedy budget that reaches `max`
    oracle_k=N   greedy coverage at budget N; a lower bound on the true optimum,
                 since max-cover is NP-hard and greedy is the (1-1/e) standard

Development data only. See campanula_development_loop for why that matters.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.field_validation import haversine_distance_m

import campanula_development_loop as loop

POOL_FILES = {
    "validation": "candidate_pool.csv",
    "survey": "candidate_pool_survey.csv",
    "dense": "candidate_pool_dense.csv",
}
DEFAULT_RADII = (0.5, 1.0, 2.0, 3.0, 5.0, 10.0)


def distance_km(pool: pd.DataFrame, clusters: pd.DataFrame) -> np.ndarray:
    lats = pool["latitude"].to_numpy(dtype=float)
    lons = pool["longitude"].to_numpy(dtype=float)
    return (
        np.vstack(
            [
                haversine_distance_m(float(row.latitude), float(row.longitude), lats, lons)
                for row in clusters.itertuples()
            ]
        )
        / 1000.0
    )


def greedy_cover(reachable: np.ndarray, budget: int | None = None) -> tuple[int, int]:
    """Return (covered, budget_used) for greedy max-cover."""
    covered = np.zeros(reachable.shape[0], dtype=bool)
    used = 0
    while budget is None or used < budget:
        gain = (reachable & ~covered[:, None]).sum(axis=0)
        best = int(gain.argmax())
        if gain[best] == 0:
            break
        covered |= reachable[:, best]
        used += 1
    return int(covered.sum()), used


def smallest_full_radius(distances: np.ndarray, limit_km: float = 50.0) -> float | None:
    """Smallest radius at which every cluster has at least one candidate."""
    n = distances.shape[0]
    if (distances <= limit_km).any(axis=1).sum() < n:
        return None
    low, high = 0.0, limit_km
    for _ in range(60):
        mid = (low + high) / 2.0
        if (distances <= mid).any(axis=1).sum() == n:
            high = mid
        else:
            low = mid
    return high


def report(pool_name: str, pool: pd.DataFrame, clusters: pd.DataFrame, radii, budgets) -> None:
    distances = distance_km(pool, clusters)
    n = len(clusters)
    print(f"\n=== pool: {pool_name} ({len(pool)} candidates, {n} clusters) ===")
    header = f"{'radius':>8} {'max':>8} {'k_for_max':>10}" + "".join(
        f"{'oracle_k=' + str(b):>13}" for b in budgets
    )
    print(header)
    for radius in radii:
        reachable = distances <= float(radius)
        maximum = int(reachable.any(axis=1).sum())
        _, k_needed = greedy_cover(reachable)
        row = f"{float(radius):7.2f}k {maximum:>4d}/{n:<3d} {k_needed:>10d}"
        for budget in budgets:
            covered, _ = greedy_cover(reachable, budget)
            row += f"{str(covered) + '/' + str(n):>13}"
        print(row)
    full = smallest_full_radius(distances)
    if full is None:
        print("  full coverage: not reached within 50 km")
    else:
        _, k_needed = greedy_cover(distances <= full)
        print(f"  full {n}/{n} coverage first possible at {full:.2f} km, budget k={k_needed}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pool", choices=sorted(POOL_FILES) + ["all"], default="all")
    parser.add_argument("--radii", type=float, nargs="+", default=list(DEFAULT_RADII))
    parser.add_argument("--budgets", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--cache-dir", type=Path, default=loop.CACHE_DIR)
    parser.add_argument("--locations", type=Path, default=loop.LOCATIONS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    clusters = loop.load_detection_clusters(args.locations)
    names = sorted(POOL_FILES) if args.pool == "all" else [args.pool]
    seen = False
    for name in names:
        path = args.cache_dir / POOL_FILES[name]
        if not path.exists():
            print(f"\n=== pool: {name} — absent ({path.name} not cached yet) ===")
            continue
        seen = True
        report(name, loop.load_pool(args.cache_dir, POOL_FILES[name]), clusters, args.radii, args.budgets)
    if not seen:
        raise SystemExit(
            "No cached pools found. Build them with the campanula-development-data workflow."
        )


if __name__ == "__main__":
    main()
