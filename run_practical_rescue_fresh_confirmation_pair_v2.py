#!/usr/bin/env python3
"""Run a fresh frozen Practical Rescue pair against corrected official GRTS v2.

This wrapper reuses the full fresh-pair leakage separation, rescue scoring,
scientific-zero rules, and artifact contract unchanged. It substitutes only the
corrected feasible diagnostic-replacement GRTS adapter.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

import run_practical_rescue_fresh_confirmation_pair as base


def _run_grts_v2(
    candidate_path: Path,
    output_path: Path,
    pair_id: int,
    repeat: int,
    protocol: dict[str, object],
) -> pd.DataFrame:
    grts = protocol["official_grts"]
    command = [
        "Rscript",
        "benchmark_methods/grts_rescue_primary_batch_v2.R",
        "--input", str(candidate_path),
        "--output", str(output_path),
        "--draws", str(int(grts["draws_per_fold"])),
        "--seed-base", str(int(grts["seed_base"])),
        "--global-pair-id", str(int(pair_id)),
        "--repeat", str(int(repeat)),
        "--k", str(int(grts["top_k"])),
        "--replacements", str(int(grts["replacement_sites_requested"])),
        "--score-col", str(grts["score_col"]),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0 or not output_path.exists():
        raise RuntimeError(
            "corrected official GRTS subprocess failed before a verified pre-outcome artifact was frozen: "
            + completed.stderr[-4000:]
        )
    draws = pd.read_csv(output_path)
    expected_draws = int(grts["draws_per_fold"])
    if len(draws) != expected_draws:
        raise RuntimeError(
            f"corrected official GRTS wrote {len(draws)} draws, expected {expected_draws}"
        )
    if draws["outcomes_available_to_selector"].astype(str).str.lower().isin({"true", "1"}).any():
        raise RuntimeError("corrected official GRTS artifact reports held-out outcome access")
    required = {"effective_replacements", "candidate_frame_rows"}
    if not required.issubset(draws.columns):
        raise RuntimeError("corrected GRTS artifact lacks feasible-replacement diagnostics")
    requested = int(grts["replacement_sites_requested"])
    effective = pd.to_numeric(draws["effective_replacements"], errors="raise").astype(int).to_numpy()
    frame_rows = pd.to_numeric(draws["candidate_frame_rows"], errors="raise").astype(int).to_numpy()
    n_base = np.minimum(int(grts["top_k"]), frame_rows)
    expected_effective = np.minimum(requested, np.maximum(frame_rows - n_base, 0))
    if not np.array_equal(effective, expected_effective):
        raise RuntimeError("corrected GRTS artifact violates feasible diagnostic replacement rule")
    return draws


base._run_grts = _run_grts_v2
parser = base.parser
run = base.run


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
