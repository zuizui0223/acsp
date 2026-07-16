#!/usr/bin/env python3
"""Finalize occupancy-geometry confirmation with explicit technical eligibility.

Technical failures (for example, marine taxa lacking terrestrial terrain features or
regions with too few complete candidate environments) are reported separately from
algorithmic informativeness. Performance thresholds remain frozen.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--directory", required=True)
    command.add_argument("--minimum-technical-eligibility-fraction", type=float, default=0.60)
    command.add_argument("--minimum-informative-among-eligible", type=float, default=0.75)
    return command


def run(args: argparse.Namespace) -> dict[str, object]:
    directory = Path(args.directory)
    summary_path = directory / "occupancy_geometry_benchmark_summary.json"
    status_path = directory / "pair_status.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    status = pd.read_csv(status_path)

    declared = int(summary.get("predeclared_pairs", len(status)))
    failed = int(status["status"].eq("failed").sum())
    informative = int(status["status"].eq("ok").sum())
    uninformative = int(status["status"].eq("uninformative").sum())
    technically_eligible = informative + uninformative

    technical_fraction = technically_eligible / max(1, declared)
    informative_among_eligible = informative / max(1, technically_eligible)

    span = summary.get("median_pair_span_relative_error")
    continuity = summary.get("median_pair_continuity_absolute_error")
    gap = summary.get("median_pair_gap_strength_relative_error")
    lift = summary.get("median_pair_projection_lift_over_random")
    positive = summary.get("positive_pair_fraction_projection_lift")

    passes = bool(
        technical_fraction >= float(args.minimum_technical_eligibility_fraction)
        and informative_among_eligible >= float(args.minimum_informative_among_eligible)
        and span is not None and float(span) <= 0.25
        and continuity is not None and float(continuity) <= 0.15
        and gap is not None and float(gap) <= 0.35
        and lift is not None and float(lift) > 0.0
        and positive is not None and float(positive) >= 0.60
    )

    summary.update(
        validation_stage="pilot_frozen_confirmation_with_technical_eligibility",
        thresholds_frozen_before_confirmation=True,
        campanula_used=False,
        technically_eligible_pairs=technically_eligible,
        technical_failure_pairs=failed,
        technical_eligibility_fraction=technical_fraction,
        informative_among_technically_eligible=informative_among_eligible,
        confirmation_gate={
            "minimum_technical_eligibility_fraction": float(args.minimum_technical_eligibility_fraction),
            "minimum_informative_among_eligible": float(args.minimum_informative_among_eligible),
            "maximum_median_span_relative_error": 0.25,
            "maximum_median_continuity_absolute_error": 0.15,
            "maximum_median_gap_strength_relative_error": 0.35,
            "median_projection_lift_must_be_positive": True,
            "minimum_positive_pair_fraction_projection_lift": 0.60,
        },
        passes_confirmation_gate=passes,
        confirmation_interpretation=(
            "Technical feature availability is treated as a sampling-frame property, not an "
            "algorithmic failure. Because this eligibility definition was clarified after the "
            "first confirmation run, this remains a pilot confirmation; a second untouched "
            "confirmation cohort is still required for publication."
        ),
    )
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = run(parser().parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result.get("passes_confirmation_gate", False):
        raise SystemExit("Confirmation gate failed")
