#!/usr/bin/env python3
"""Evaluate one frozen rescue-development pair against corrected official GRTS v2.

This wrapper intentionally reuses the frozen v1 pair evaluator. The only
scientific change is the official GRTS adapter's feasible diagnostic-replacement
rule, which strengthens the comparator without changing the rescue policy.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pandas as pd

import benchmark_practical_rescue_grts_pair as base

EXPECTED_PROTOCOL = "74fec14b44035e897072b022d82ea30c00b27ce1bb95c16a0e9a5578a3d3da7a"


def _assert_nonempty_grts_draws_error_free(result: pd.DataFrame) -> None:
    """Reject implementation failures on non-empty candidate frames.

    Empty candidate frames are handled before R is called and retain the frozen
    protocol's explicit zero-recovery artifact. Once a non-empty frame reaches
    official GRTS, however, an implementation error must not silently become a
    zero comparator score because that would bias the promotion contrast toward
    Rescue.
    """
    if "error_message" not in result.columns:
        raise RuntimeError("corrected GRTS artifact lacks error_message")
    errors = result["error_message"].fillna("").astype(str).str.strip()
    bad = errors.ne("")
    if bad.any():
        examples = sorted(set(errors.loc[bad].tolist()))[:3]
        raise RuntimeError(
            "corrected official GRTS produced draw errors on a non-empty candidate frame; "
            f"refusing failure-as-zero promotion scoring (draws={int(bad.sum())}, examples={examples})"
        )


def _run_grts_v2(
    input_path: Path,
    output_path: Path,
    global_pair_id: int,
    repeat: int,
    protocol: dict[str, object],
) -> pd.DataFrame:
    grts = protocol["official_grts"]
    frame = pd.read_csv(input_path)
    draws = int(grts["draws_per_fold"])
    if frame.empty:
        result = base._empty_draws(
            global_pair_id,
            repeat,
            draws,
            str(grts["spsurvey_version"]),
            str(grts["spsurvey_tag_commit"]),
        )
        result["effective_replacements"] = 0
        result["candidate_frame_rows"] = 0
        result["replacement_feasibility_rule"] = (
            "min(requested,max(candidate_frame_rows-n_base,0))"
        )
        result.to_csv(output_path, index=False)
        return result

    command = [
        "Rscript",
        "benchmark_methods/grts_rescue_primary_batch_v2.R",
        "--input", str(input_path),
        "--output", str(output_path),
        "--draws", str(draws),
        "--seed-base", str(grts["seed_base"]),
        "--global-pair-id", str(global_pair_id),
        "--repeat", str(repeat),
        "--k", str(grts["top_k"]),
        "--replacements", str(grts["replacement_sites_requested"]),
        "--score-col", str(grts["score_col"]),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "corrected official GRTS subprocess failed before a scientific draw artifact was frozen: "
            + completed.stderr[-4000:]
        )
    result = pd.read_csv(output_path)
    if len(result) != draws:
        raise RuntimeError(f"expected {draws} corrected GRTS draws, found {len(result)}")
    if result["outcomes_available_to_selector"].astype(str).str.lower().isin({"true", "1"}).any():
        raise RuntimeError("corrected GRTS pre-outcome artifact reports outcome access")
    requested = int(grts["replacement_sites_requested"])
    effective = pd.to_numeric(result["effective_replacements"], errors="raise")
    frame_rows = pd.to_numeric(result["candidate_frame_rows"], errors="raise")
    base_requested = frame_rows.clip(upper=int(grts["top_k"]))
    expected_effective = (frame_rows - base_requested).clip(lower=0, upper=requested)
    if not effective.equals(expected_effective.astype(effective.dtype)):
        raise RuntimeError("corrected GRTS artifact violates the frozen feasible-replacement rule")
    _assert_nonempty_grts_draws_error_free(result)
    return result


def parser():
    command = base.parser()
    for action in command._actions:
        if action.dest == "protocol":
            action.default = Path(
                "validation/acsp_practical_rescue_grts_development_protocol_v2.json"
            )
    return command


def run(args):
    # Scope v2 bindings to this invocation. Importing this audit wrapper must not
    # mutate the retained v1 protocol or GRTS runner used by repository tests and
    # historical reproduction.
    original_protocol = base.EXPECTED_PROTOCOL
    original_runner = base._run_grts
    try:
        base.EXPECTED_PROTOCOL = EXPECTED_PROTOCOL
        base._run_grts = _run_grts_v2
        return base.run(args)
    finally:
        base.EXPECTED_PROTOCOL = original_protocol
        base._run_grts = original_runner


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2))
