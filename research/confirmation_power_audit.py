"""Can a confirmation design detect an effect at all, given its own results?

A confirmation reports mean lift, an interval, and a sign-flip p. None of those
say how many pairs actually carried information. A pair where both the method
and the control recover nothing is a tie, and a pair where both recover
everything is also a tie; neither can move a sign test. When ties dominate, the
design fails for a reason that has nothing to do with the method under test.

Run it on a confirmation's pair-level results:

    python research/confirmation_power_audit.py \
      validation/acsp_adaptive_cross_island_confirmation_20260816/pair_results.csv

Reports the split into dropped, floor-saturated, ceiling-saturated, tied, and
informative pairs, then the best one-sided sign-flip p reachable at that
informative count and how many informative pairs the gate actually needs.

Use it before spending an untouched cohort, not only after.
"""
from __future__ import annotations

import argparse
import csv
from math import comb
from pathlib import Path

GATE_P = 0.05


def one_sided_sign_p(positive: int, informative: int) -> float:
    if informative <= 0:
        return 1.0
    return sum(comb(informative, k) for k in range(positive, informative + 1)) / 2**informative


def informative_needed(gate_p: float, discordant: int, limit: int = 60) -> int | None:
    """Smallest informative count where `discordant` negatives still clears the gate."""
    for n in range(discordant + 1, limit):
        if one_sided_sign_p(n - discordant, n) < gate_p:
            return n
    return None


def audit(rows: list[dict], *, status_col: str, ok_value: str) -> dict:
    scored = [r for r in rows if r.get(status_col) == ok_value]
    lift = lambda r: float(r["mean_lift"])
    support = lambda r: float(r["mean_support_recall"])
    control = lambda r: float(r["mean_control_recall"])

    floor = [r for r in scored if support(r) == 0.0 and control(r) == 0.0]
    ceiling = [r for r in scored if support(r) == 1.0 and control(r) == 1.0]
    other_tie = [
        r
        for r in scored
        if abs(lift(r)) < 1e-12 and r not in floor and r not in ceiling
    ]
    informative = [r for r in scored if abs(lift(r)) >= 1e-12]
    positive = [r for r in informative if lift(r) > 0]
    return {
        "declared": len(rows),
        "dropped": len(rows) - len(scored),
        "scored": len(scored),
        "floor": len(floor),
        "ceiling": len(ceiling),
        "other_tie": len(other_tie),
        "informative": len(informative),
        "positive": len(positive),
    }


def report(a: dict, gate_p: float) -> None:
    n, pos = a["informative"], a["positive"]
    print(f"declared pairs                {a['declared']}")
    print(f"  dropped before scoring      {a['dropped']}")
    print(f"  scored                      {a['scored']}")
    print(f"    both recovered nothing    {a['floor']:>3d}   floor-saturated, no information")
    print(f"    both recovered everything {a['ceiling']:>3d}   ceiling-saturated, no information")
    print(f"    tied in between           {a['other_tie']:>3d}")
    print(f"    informative               {n:>3d}   ({pos} positive, {n - pos} negative)")

    best = 1 / 2**n if n else 1.0
    print(f"\nthe sign-flip test sees only the {n} informative pairs")
    print(f"  best reachable one-sided p   {best:.5f}" + ("" if n else "  (no informative pairs)"))
    if best >= gate_p:
        print(f"  gate p < {gate_p} is UNREACHABLE at any outcome")
    else:
        print(f"  gate p < {gate_p} is reachable, but only on a clean sweep"
              if one_sided_sign_p(n - 1, n) >= gate_p
              else f"  gate p < {gate_p} is reachable and survives a discordant pair")
    print(f"  observed {pos}/{n} positive     p = {one_sided_sign_p(pos, n):.5f}")

    print("\ninformative pairs the gate requires")
    for discordant in (0, 1, 2):
        need = informative_needed(gate_p, discordant)
        label = "clean sweep" if discordant == 0 else f"{discordant} discordant"
        print(f"  {label:>14}: {need}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pair_results", type=Path)
    parser.add_argument("--status-col", default="status")
    parser.add_argument("--ok-value", default="ok")
    parser.add_argument("--gate-p", type=float, default=GATE_P)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.pair_results.open() as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"{args.pair_results} has no rows")
    report(audit(rows, status_col=args.status_col, ok_value=args.ok_value), args.gate_p)


if __name__ == "__main__":
    main()
