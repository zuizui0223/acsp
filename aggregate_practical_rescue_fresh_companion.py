#!/usr/bin/env python3
"""Evaluate predeclared fresh Rescue companion comparators from frozen pair artifacts.

The corrected-GRTS-v2 confirmation remains the separately frozen primary gate.
This companion implements the already-written issue-57 requirement to compare
Practical Rescue with frozen publication v1, local-only, geographic maximin,
and same-pool random on the exact same untouched 192-pair cohort.

For every complete fold, comparator selections are written to this command's
output directory before the held-out occurrence file is opened for scoring.
Primary pair artifacts are read-only and are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.decision_baselines import (
    DecisionBaselineConfig,
    random_same_pool_sets,
    select_geographic_farthest,
)
from acsp.practical_core import PracticalCorePolicy, select_practical_core
from acsp.validated_core import ValidatedCorePolicy, select_validated_core
from run_practical_core_confirmation_pair import _coverage_sets, _recall

EXPECTED_COMPANION_PROTOCOL = "ed8e1333cf9638f90aa0fa2eda11d0845b484c6316826a194e02eb1b3dc8847e"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(path: Path, *, expected: str | None = None) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not stored or stored != calculated:
        raise ValueError(
            f"protocol fingerprint mismatch: stored={stored!r}, calculated={calculated!r}"
        )
    if expected is not None and calculated != expected:
        raise ValueError(f"unexpected companion protocol fingerprint: {calculated}")
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _ids(frame: pd.DataFrame | None) -> list[str]:
    if frame is None or frame.empty or "candidate_id" not in frame.columns:
        return []
    return frame["candidate_id"].astype(str).tolist()


def _inference(values: np.ndarray, draws: int, seed: int) -> dict[str, object]:
    difference = np.asarray(values, dtype=float)
    if difference.ndim != 1 or len(difference) == 0 or not np.isfinite(difference).all():
        raise ValueError("companion differences must be a non-empty finite vector")
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


def _freeze_companion_decisions(
    candidates: pd.DataFrame,
    taxon_group: str,
    pair_id: int,
    repeat: int,
    protocol: dict[str, object],
    output_dir: Path,
) -> dict[str, object]:
    if "candidate_id" not in candidates.columns:
        raise RuntimeError("fresh candidate artifact lacks stable candidate_id")
    top_k = int(protocol["comparators"]["frozen_v1"]["top_k"])
    if len(candidates) < top_k:
        raise RuntimeError("complete fresh fold unexpectedly has fewer than Top-k candidates")

    v1 = select_validated_core(
        candidates,
        ValidatedCorePolicy.for_taxon_group(str(taxon_group)),
    )
    local = select_practical_core(candidates, PracticalCorePolicy(top_k=top_k))
    base_config = DecisionBaselineConfig(
        k=top_k,
        id_col="candidate_id",
        score_col="component_local_habitat_score",
        random_draws=int(protocol["comparators"]["same_pool_random"]["draws_per_fold"]),
        random_state=20260813 + int(pair_id) * 1000 + int(repeat),
    )
    geographic = select_geographic_farthest(candidates, base_config)
    random_draws = random_same_pool_sets(candidates, base_config)

    decisions = {
        "pair_id": int(pair_id),
        "repeat": int(repeat),
        "outcomes_available_to_selectors": False,
        "frozen_v1_ids": _ids(v1),
        "local_only_ids": _ids(local),
        "geographic_maximin_ids": _ids(geographic),
        "same_pool_random_ids": [_ids(draw) for draw in random_draws],
    }
    for key in ("frozen_v1_ids", "local_only_ids", "geographic_maximin_ids"):
        if len(decisions[key]) != top_k:
            raise RuntimeError(f"companion selector {key} did not return Top-k")
    if len(decisions["same_pool_random_ids"]) != int(
        protocol["comparators"]["same_pool_random"]["draws_per_fold"]
    ):
        raise RuntimeError("companion random selector wrote the wrong number of draws")
    if any(len(ids) != top_k for ids in decisions["same_pool_random_ids"]):
        raise RuntimeError("companion random selector produced a non-Top-k draw")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "decisions_pre_outcome.json").write_text(
        json.dumps(decisions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return decisions


def run(
    cohort: Path,
    pair_root: Path,
    fresh_protocol_path: Path,
    companion_protocol_path: Path,
    output: Path,
) -> dict[str, object]:
    companion, companion_fp = _canonical(
        companion_protocol_path, expected=EXPECTED_COMPANION_PROTOCOL
    )
    fresh, fresh_fp = _canonical(fresh_protocol_path)
    bound = companion["bound_fresh_confirmation"]
    if fresh_fp != str(bound["fresh_protocol_fingerprint"]):
        raise ValueError("companion protocol is not bound to this fresh protocol")
    if _sha256(cohort) != str(bound["cohort_sha256"]):
        raise ValueError("fresh cohort bytes differ from the pre-outcome companion freeze")
    if str(fresh["final_model"]["model_sha256"]) != str(bound["final_model_sha256"]):
        raise ValueError("fresh protocol model differs from companion freeze")

    declared = pd.read_csv(cohort)
    expected_pairs = int(bound["pair_count"])
    if len(declared) != expected_pairs:
        raise ValueError(f"fresh cohort contains {len(declared)} pairs, expected {expected_pairs}")
    if sorted(pd.to_numeric(declared["pair_id"], errors="raise").astype(int)) != list(
        range(1, expected_pairs + 1)
    ):
        raise ValueError("fresh cohort pair IDs are not exactly 1..192")

    summaries = list(pair_root.rglob("pair_summary.json"))
    if len(summaries) != expected_pairs:
        raise RuntimeError(
            f"companion invalid: expected {expected_pairs} verified pair summaries, found {len(summaries)}"
        )
    summary_by_id: dict[int, tuple[Path, dict[str, object]]] = {}
    for path in summaries:
        payload = json.loads(path.read_text(encoding="utf-8"))
        pair_id = int(payload["pair_id"])
        if pair_id in summary_by_id:
            raise RuntimeError(f"duplicate pair summary for {pair_id}")
        if payload.get("verified_scientific_artifact") is not True:
            raise RuntimeError(f"pair {pair_id} is not a verified scientific artifact")
        if str(payload.get("protocol_fingerprint")) != fresh_fp:
            raise RuntimeError(f"pair {pair_id} fresh protocol fingerprint mismatch")
        if str(payload.get("final_model_sha256")) != str(bound["final_model_sha256"]):
            raise RuntimeError(f"pair {pair_id} final model hash mismatch")
        summary_by_id[pair_id] = (path.parent, payload)
    if sorted(summary_by_id) != list(range(1, expected_pairs + 1)):
        raise RuntimeError("companion pair summaries are incomplete")

    fold_rows: list[dict[str, object]] = []
    pair_rows: list[dict[str, object]] = []
    radius = float(bound["recovery_radius_km"])
    expected_folds = int(bound["folds_per_pair"])
    for pair_id in range(1, expected_pairs + 1):
        pair_dir, summary = summary_by_id[pair_id]
        group = str(summary["taxon_group"])
        folds = pd.read_csv(pair_dir / "fold_comparison.csv")
        if len(folds) != expected_folds:
            raise RuntimeError(f"pair {pair_id} has {len(folds)} folds, expected {expected_folds}")
        pair_fold_rows: list[dict[str, object]] = []
        for fold in folds.itertuples(index=False):
            repeat = int(fold.repeat)
            status = str(fold.fold_status)
            rescue_recovery = float(fold.rescue_recovery_10km)
            row = {
                "pair_id": pair_id,
                "repeat": repeat,
                "taxon_group": group,
                "scientific_name": str(summary["scientific_name"]),
                "region_name": str(summary["region_name"]),
                "fold_status": status,
                "rescue_recovery_10km": rescue_recovery,
            }
            if status != "complete":
                if abs(rescue_recovery) > 1e-12:
                    raise RuntimeError(
                        f"pair {pair_id} repeat {repeat} non-complete fold is not the frozen zero estimand"
                    )
                row.update({
                    "frozen_v1_recovery_10km": 0.0,
                    "local_only_recovery_10km": 0.0,
                    "geographic_maximin_recovery_10km": 0.0,
                    "same_pool_random_mean_recovery_10km": 0.0,
                    "companion_decisions_frozen_before_heldout_open": True,
                })
                pair_fold_rows.append(row)
                fold_rows.append(row)
                continue

            fold_dir = pair_dir / f"fold_{repeat:03d}"
            candidate_path = fold_dir / "candidate_pool_pre_outcome.csv"
            heldout_path = fold_dir / "held_out_occurrences.csv"
            if not candidate_path.is_file() or not heldout_path.is_file():
                raise RuntimeError(
                    f"pair {pair_id} repeat {repeat} lacks complete frozen candidate/heldout artifacts"
                )
            candidates = pd.read_csv(candidate_path)
            decision_dir = output / "pre_outcome_decisions" / f"pair_{pair_id:03d}" / f"fold_{repeat:03d}"
            decisions = _freeze_companion_decisions(
                candidates, group, pair_id, repeat, companion, decision_dir
            )
            decision_path = decision_dir / "decisions_pre_outcome.json"
            if not decision_path.is_file():
                raise RuntimeError("companion pre-outcome decision artifact was not physically written")

            # Held-out scoring starts only after every companion choice above is frozen.
            heldout = pd.read_csv(heldout_path)
            coverage, all_ids = _coverage_sets(candidates, heldout, radius)
            random_recovery = [
                _recall(ids, coverage, all_ids)
                for ids in decisions["same_pool_random_ids"]
            ]
            row.update({
                "frozen_v1_recovery_10km": _recall(decisions["frozen_v1_ids"], coverage, all_ids),
                "local_only_recovery_10km": _recall(decisions["local_only_ids"], coverage, all_ids),
                "geographic_maximin_recovery_10km": _recall(decisions["geographic_maximin_ids"], coverage, all_ids),
                "same_pool_random_mean_recovery_10km": float(np.mean(random_recovery)),
                "companion_decisions_frozen_before_heldout_open": True,
            })
            pair_fold_rows.append(row)
            fold_rows.append(row)

        pair_frame = pd.DataFrame(pair_fold_rows)
        pair_rows.append({
            "pair_id": pair_id,
            "taxon_group": group,
            "scientific_name": str(summary["scientific_name"]),
            "region_name": str(summary["region_name"]),
            "rescue_mean_recovery_10km": float(pair_frame["rescue_recovery_10km"].mean()),
            "frozen_v1_mean_recovery_10km": float(pair_frame["frozen_v1_recovery_10km"].mean()),
            "local_only_mean_recovery_10km": float(pair_frame["local_only_recovery_10km"].mean()),
            "geographic_maximin_mean_recovery_10km": float(pair_frame["geographic_maximin_recovery_10km"].mean()),
            "same_pool_random_mean_recovery_10km": float(pair_frame["same_pool_random_mean_recovery_10km"].mean()),
        })

    pair_frame = pd.DataFrame(pair_rows).sort_values("pair_id", kind="mergesort").reset_index(drop=True)
    fold_frame = pd.DataFrame(fold_rows).sort_values(["pair_id", "repeat"], kind="mergesort").reset_index(drop=True)
    inference_cfg = companion["inference"]
    draws = int(inference_cfg["bootstrap_draws"])
    seed = int(inference_cfg["seed"])
    methods = {
        "frozen_v1": "frozen_v1_mean_recovery_10km",
        "local_only": "local_only_mean_recovery_10km",
        "geographic_maximin": "geographic_maximin_mean_recovery_10km",
        "same_pool_random": "same_pool_random_mean_recovery_10km",
    }
    inference: dict[str, object] = {}
    for offset, (method, column) in enumerate(methods.items()):
        diff = (
            pair_frame["rescue_mean_recovery_10km"].to_numpy(float)
            - pair_frame[column].to_numpy(float)
        )
        pair_frame[f"rescue_minus_{method}"] = diff
        inference[method] = _inference(diff, draws, seed + offset)

    threshold = float(inference_cfg["minimum_absolute_recall_gain"])
    v1 = inference["frozen_v1"]
    companion_gate_passed = bool(
        len(pair_frame) == expected_pairs
        and v1["mean_difference"] >= threshold
        and v1["bootstrap_95ci_low"] > 0
        and v1["sign_flip_p"] < 0.05
    )

    output.mkdir(parents=True, exist_ok=True)
    fold_frame.to_csv(output / "fold_level_companion.csv", index=False)
    pair_frame.to_csv(output / "pair_level_companion.csv", index=False)
    result = {
        "status": "fresh_practical_rescue_companion_evaluated",
        "protocol_fingerprint": companion_fp,
        "fresh_protocol_fingerprint": fresh_fp,
        "cohort_sha256": _sha256(cohort),
        "final_model_sha256": str(bound["final_model_sha256"]),
        "declared_pairs": expected_pairs,
        "verified_pair_artifacts": int(len(pair_frame)),
        "inference": inference,
        "minimum_absolute_recall_gain": threshold,
        "required_v2_minus_frozen_v1_gate_passed": companion_gate_passed,
        "primary_grts_gate_changed": False,
        "fresh_outcomes_used_for_retuning": False,
        "missing_pair_artifacts_scored_as_zero": False,
    }
    (output / "companion_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--cohort", type=Path, required=True)
    command.add_argument("--pair-root", type=Path, required=True)
    command.add_argument("--fresh-protocol", dest="fresh_protocol_path", type=Path, required=True)
    command.add_argument("--companion-protocol", dest="companion_protocol_path", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
