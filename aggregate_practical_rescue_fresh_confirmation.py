#!/usr/bin/env python3
"""Aggregate a fully fresh Practical Rescue versus official GRTS confirmation.

Unlike the invalidated earlier confirmation path, missing pair artifacts are
never converted to scientific zeroes. Every declared pair must write a
verified pair_summary.json. Explicit scientific failures may contribute the
predeclared zero estimand only when that failure is recorded inside the pair
artifact itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _canonical_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not stored or stored != calculated:
        raise ValueError(
            f"fresh confirmation protocol fingerprint mismatch: stored={stored!r}, calculated={calculated!r}"
        )
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _inference(difference: np.ndarray, draws: int, seed: int) -> dict[str, object]:
    difference = np.asarray(difference, dtype=float)
    if difference.ndim != 1 or len(difference) == 0 or not np.isfinite(difference).all():
        raise ValueError("primary pair differences must be a non-empty finite vector")
    rng = np.random.default_rng(int(seed))
    bootstrap = rng.choice(difference, size=(int(draws), len(difference)), replace=True).mean(axis=1)
    null = (
        rng.choice(np.array([-1.0, 1.0]), size=(int(draws), len(difference)))
        * difference
    ).mean(axis=1)
    observed = abs(float(difference.mean()))
    return {
        "pairs": int(len(difference)),
        "mean_difference": float(difference.mean()),
        "bootstrap_95ci_low": float(np.quantile(bootstrap, 0.025)),
        "bootstrap_95ci_high": float(np.quantile(bootstrap, 0.975)),
        "sign_flip_p": float((1 + np.sum(np.abs(null) >= observed)) / (int(draws) + 1)),
        "positive_pairs": int(np.sum(difference > 1e-12)),
        "negative_pairs": int(np.sum(difference < -1e-12)),
        "tied_pairs": int(np.sum(np.abs(difference) <= 1e-12)),
        "difference_sd": float(np.std(difference, ddof=1)),
    }


def run(cohort: Path, pair_root: Path, protocol_path: Path, output: Path) -> dict[str, object]:
    protocol, fingerprint = _canonical_protocol(protocol_path)
    declared = pd.read_csv(cohort)
    expected_pairs = int(protocol["cohort"]["pair_count"])
    if len(declared) != expected_pairs:
        raise ValueError(f"cohort has {len(declared)} rows, expected {expected_pairs}")
    pair_ids = sorted(pd.to_numeric(declared["pair_id"], errors="raise").astype(int).tolist())
    if pair_ids != list(range(1, expected_pairs + 1)):
        raise ValueError("fresh confirmation pair IDs are not exactly 1..N")
    if declared["scientific_name"].astype(str).nunique() != expected_pairs:
        raise ValueError("fresh confirmation cohort contains repeated taxa")

    summary_paths = list(pair_root.rglob("pair_summary.json"))
    if len(summary_paths) != expected_pairs:
        raise RuntimeError(
            "confirmation invalid: missing or duplicate verified pair artifacts; "
            f"expected {expected_pairs}, found {len(summary_paths)}"
        )
    summaries = [json.loads(path.read_text(encoding="utf-8")) for path in summary_paths]
    pair = pd.DataFrame(summaries)
    if len(pair) != expected_pairs or pair["pair_id"].astype(int).nunique() != expected_pairs:
        raise RuntimeError("confirmation invalid: pair summaries are not one-to-one with declared pairs")
    pair = pair.sort_values("pair_id", kind="mergesort").reset_index(drop=True)
    if pair["pair_id"].astype(int).tolist() != list(range(1, expected_pairs + 1)):
        raise RuntimeError("confirmation invalid: pair summary IDs are incomplete")
    if pair["protocol_fingerprint"].astype(str).nunique() != 1 or str(pair["protocol_fingerprint"].iloc[0]) != fingerprint:
        raise RuntimeError("confirmation invalid: pair artifacts disagree on protocol fingerprint")
    if not pair["verified_scientific_artifact"].astype(bool).all():
        raise RuntimeError("confirmation invalid: an infrastructure marker was supplied in place of a scientific artifact")
    if pair["outcomes_available_to_rescue_selector"].astype(bool).any():
        raise RuntimeError("confirmation invalid: rescue selector had held-out outcome access")
    if pair["outcomes_available_to_grts_selector"].astype(bool).any():
        raise RuntimeError("confirmation invalid: GRTS selector had held-out outcome access")

    model_hashes = set(pair["final_model_sha256"].astype(str))
    expected_model_hash = str(protocol["final_model"]["model_sha256"])
    if model_hashes != {expected_model_hash}:
        raise RuntimeError(f"confirmation invalid: pair model hashes differ from frozen model {expected_model_hash}")

    rescue = pd.to_numeric(pair["rescue_mean_recovery_10km"], errors="raise").to_numpy(float)
    grts = pd.to_numeric(pair["grts_mean_recovery_10km"], errors="raise").to_numpy(float)
    if not np.isfinite(rescue).all() or not np.isfinite(grts).all():
        raise RuntimeError("confirmation invalid: non-finite primary pair estimands")
    pair["rescue_minus_grts"] = rescue - grts

    inference_cfg = protocol["inference"]
    primary = _inference(
        pair["rescue_minus_grts"].to_numpy(float),
        int(inference_cfg["bootstrap_draws"]),
        int(inference_cfg["seed"]),
    )
    threshold = float(inference_cfg["minimum_absolute_recall_gain"])
    passed = bool(
        len(pair) == expected_pairs
        and primary["mean_difference"] >= threshold
        and primary["bootstrap_95ci_low"] > 0
        and primary["sign_flip_p"] < 0.05
    )

    source_results: dict[str, object] = {}
    for group, subset in pair.groupby("taxon_group"):
        source_results[str(group)] = _inference(
            subset["rescue_minus_grts"].to_numpy(float),
            int(inference_cfg["bootstrap_draws"]),
            int(inference_cfg["seed"]) + (1 if str(group) == "plant" else 2),
        )

    output.mkdir(parents=True, exist_ok=True)
    pair.to_csv(output / "pair_level_comparison.csv", index=False)
    result = {
        "status": "fresh_practical_rescue_confirmation_evaluated",
        "protocol_fingerprint": fingerprint,
        "declared_pairs": expected_pairs,
        "verified_pair_artifacts": int(len(pair)),
        "missing_pair_artifacts_scored_as_zero": False,
        "primary_contrast": str(inference_cfg["primary_contrast"]),
        "primary_inference": primary,
        "taxon_group_inference": source_results,
        "minimum_absolute_recall_gain": threshold,
        "promotion_gate_passed": passed,
        "final_model_sha256": expected_model_hash,
        "outcomes_available_to_rescue_selector": False,
        "outcomes_available_to_grts_selector": False,
        "no_retuning_after_confirmation_outcome": True,
    }
    (output / "confirmation_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--cohort", type=Path, required=True)
    command.add_argument("--pair-root", type=Path, required=True)
    command.add_argument("--protocol", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
