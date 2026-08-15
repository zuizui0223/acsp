"""Campanula microdonta development loop.

*Campanula microdonta* is a **development** dataset, not independent
confirmation. The 2026 field GPS outcomes have already been inspected, and the
`select_area_balanced_candidates` update was made because those outcomes exposed
a failure. Nothing measured here can support a validation claim about ACSP. Any
rule that comes out of this loop has to be frozen and then tested on taxa that
have never been touched.

Why the target radius is 1 km
-----------------------------
The national retrospective claim uses a 10 km endpoint. That endpoint is
saturated on this system: the Izu islands are smaller than the radius, so five
candidates placed anywhere recover ~86% of detection clusters, and same-pool
random scores essentially the same. Within-island nearest-cluster separation has
a median near 0.9-1.9 km, so 1 km is the coarsest radius at which a ranking can
still be distinguished from chance here.

Usage
-----
Cache the dataset first (needs network, so run it on CI):

    python research/cache_campanula_development_data.py

Then iterate offline:

    python research/campanula_development_loop.py --strategy local_topk
    python research/campanula_development_loop.py --strategy area_balanced --top-k 10

Add a strategy by writing a function that takes the scored candidate pool, a
budget, and an evidence weight, returns the selected rows, and registering it in
STRATEGIES.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from acsp.area_selection import select_area_balanced_candidates
from acsp.field_validation import (
    cluster_field_detections,
    detection_recovery_table,
    recovery_summary,
    stratified_random_recovery_benchmark,
)
from acsp.planning import select_complementary_candidates

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "field_validation" / "campanula_microdonta"
CACHE_DIR = DATA_DIR / "development_data"
LOCATIONS = DATA_DIR / "locations_2026.csv"

SCORE_COL = "component_local_habitat_score"
CLUSTER_RADIUS_M = 500.0
PRIMARY_RADIUS_KM = 1.0
REPORT_RADII_KM = (0.5, 1.0, 2.0, 5.0, 10.0)

Strategy = Callable[[pd.DataFrame, int, float], pd.DataFrame]


def strategy_local_topk(pool: pd.DataFrame, top_k: int, evidence_weight: float) -> pd.DataFrame:
    """Frozen Practical Core: rank by local habitat evidence, take the top k.

    With the plant evidence weight of 1.0 this is also the historical v1 plant
    policy, because no weight is left for the geographic-complementarity term.
    """
    ordered = pool.sort_values([SCORE_COL, "site_id"], ascending=[False, True], kind="mergesort")
    return ordered.head(top_k).copy()


def strategy_local_complementary(pool: pd.DataFrame, top_k: int, evidence_weight: float) -> pd.DataFrame:
    """Local evidence traded against geographic complementarity.

    `evidence_weight` below 1.0 leaves the remainder for spatial spread; the
    historical v1 animal policy used 0.75.
    """
    return select_complementary_candidates(
        pool, min(top_k, len(pool)), score_col=SCORE_COL, evidence_weight=evidence_weight
    ).copy()


def strategy_area_balanced(pool: pd.DataFrame, top_k: int, evidence_weight: float) -> pd.DataFrame:
    """Post-baseline update: represent every island before repeating one."""
    return select_area_balanced_candidates(
        pool, min(top_k, len(pool)), score_col=SCORE_COL, evidence_weight=evidence_weight
    ).copy()


STRATEGIES: dict[str, Strategy] = {
    "local_topk": strategy_local_topk,
    "local_complementary": strategy_local_complementary,
    "area_balanced": strategy_area_balanced,
}


def load_pool(cache_dir: Path, filename: str = "candidate_pool.csv") -> pd.DataFrame:
    path = cache_dir / filename
    if not path.exists():
        raise SystemExit(
            f"Missing {path}.\n"
            "Cache the development dataset first — it needs GBIF and GSI network access:\n"
            "  python research/cache_campanula_development_data.py\n"
            "or run the campanula-development-data workflow, which does it on a runner."
        )
    pool = pd.read_csv(path)
    if SCORE_COL not in pool.columns:
        raise SystemExit(f"{path} has no {SCORE_COL} column.")
    pool["site_id"] = pool["site_id"].astype(str)
    return pool


def load_detection_clusters_from_frame(rows: pd.DataFrame) -> pd.DataFrame:
    # cluster_field_detections returns (per-row assignments, cluster table).
    _assignments, clusters = cluster_field_detections(rows, cluster_radius_m=CLUSTER_RADIUS_M)
    return clusters


def load_detection_clusters(locations: Path) -> pd.DataFrame:
    return load_detection_clusters_from_frame(pd.read_csv(locations))


def evaluate(
    pool: pd.DataFrame,
    selected: pd.DataFrame,
    clusters: pd.DataFrame,
    *,
    iterations: int,
    seed: int,
) -> dict[str, object]:
    recovery = detection_recovery_table(selected, clusters, radii_km=REPORT_RADII_KM)
    summary = recovery_summary(recovery, radii_km=REPORT_RADII_KM)
    # Returns (per-radius benchmark, per-iteration random draws).
    benchmark, draws = stratified_random_recovery_benchmark(
        pool,
        selected["site_id"].tolist(),
        clusters,
        radii_km=REPORT_RADII_KM,
        iterations=iterations,
        seed=seed,
    )
    return {
        "recovery": recovery,
        "summary": summary,
        "benchmark": benchmark,
        "random_draws": draws,
    }


def per_area_misses(recovery: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    column = f"recovered_{float(radius_km):g}km"
    area_col = "survey_area_id" if "survey_area_id" in recovery.columns else "island"
    if area_col not in recovery.columns:
        return pd.DataFrame()
    grouped = recovery.groupby(area_col)[column]
    out = pd.DataFrame(
        {
            "n_clusters": grouped.size().astype(int),
            "n_recovered": grouped.sum().astype(int),
        }
    )
    out["recall"] = out["n_recovered"] / out["n_clusters"]
    return out.reset_index()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strategy", default="local_topk", choices=sorted(STRATEGIES))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--evidence-weight",
        type=float,
        default=1.0,
        help="Weight on local evidence; the remainder goes to geographic spread. "
        "1.0 is the plant policy, 0.75 the historical v1 animal policy.",
    )
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument(
        "--pool",
        choices=("validation", "survey"),
        default="validation",
        help="validation = leakage-controlled pool (known-location candidates stripped, "
        "occurrence-derived evidence excluded). survey = the pool a surveyor would "
        "actually be handed. Only the validation pool can support a validation claim.",
    )
    parser.add_argument("--locations", type=Path, default=LOCATIONS)
    parser.add_argument("--json-out", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pool = load_pool(
        args.cache_dir,
        "candidate_pool.csv" if args.pool == "validation" else "candidate_pool_survey.csv",
    )
    clusters = load_detection_clusters(args.locations)
    selected = STRATEGIES[args.strategy](pool, args.top_k, args.evidence_weight)

    result = evaluate(pool, selected, clusters, iterations=args.iterations, seed=args.seed)
    summary = result["summary"]
    benchmark = result["benchmark"]

    print(f"pool                : {args.pool}")
    print(f"strategy            : {args.strategy}")
    print(f"budget              : {args.top_k}")
    print(f"evidence weight     : {args.evidence_weight}")
    print(f"candidate pool      : {len(pool)} rows")
    print(f"detection clusters  : {len(clusters)} at {CLUSTER_RADIUS_M:.0f} m")
    print(f"primary target      : {PRIMARY_RADIUS_KM:g} km recall\n")

    merged = summary.merge(benchmark, on="radius_km", how="left")
    for _, row in merged.iterrows():
        marker = "  <-- primary" if float(row["radius_km"]) == PRIMARY_RADIUS_KM else ""
        print(
            f"  {row['radius_km']:5.1f} km  "
            f"recall {row['detection_recall']:.4f} "
            f"({int(row['n_recovered'])}/{int(row['n_detection_clusters'])})  "
            f"random {row['random_mean_recall']:.4f}  "
            f"lift {row['lift_over_random']:+.4f}  "
            f"p {row['randomization_p_one_sided']:.4f}{marker}"
        )

    misses = per_area_misses(result["recovery"], PRIMARY_RADIUS_KM)
    if not misses.empty:
        print(f"\nper-island recall at {PRIMARY_RADIUS_KM:g} km:")
        for _, row in misses.iterrows():
            area = row.iloc[0]
            print(
                f"  {str(area):14s} {int(row['n_recovered'])}/{int(row['n_clusters'])}"
                f"  ({row['recall']:.2f})"
            )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {
                    "pool": args.pool,
                    "strategy": args.strategy,
                    "top_k": args.top_k,
                    "evidence_weight": args.evidence_weight,
                    "pool_size": int(len(pool)),
                    "n_detection_clusters": int(len(clusters)),
                    "primary_radius_km": PRIMARY_RADIUS_KM,
                    "summary": merged.to_dict(orient="records"),
                    "per_area": misses.to_dict(orient="records"),
                    "development_only": True,
                },
                indent=2,
            )
        )
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
