#!/usr/bin/env python3
"""Cross-fit the v1-anchored fifth-slot Practical Rescue vNext on 192 inspected pairs.

The 192-pair fresh-v2 confirmation failed the predeclared frozen-v1 companion
gate and is explicitly development data from this point forward.  This script
never treats its result as confirmation.  Candidate frames and spatial holdouts
are reused byte-for-byte; only the finite Top-5 policy is redesigned.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.practical_rescue_vnext import (
    VNEXT_CATEGORICAL_FEATURES,
    VNEXT_NUMERIC_FEATURES,
    VNEXT_PROTOCOL_FINGERPRINT,
    build_vnext_features,
    frozen_v1_order,
    make_vnext_estimator,
    select_vnext_anchored_fifth,
)
from run_practical_core_confirmation_pair import _coverage_sets, _recall


EXPECTED_FRESH_PROTOCOL = "c7d84a3160e9d9b0b05b932c44444be5dfd750200e72749fb413592499bcf8bd"
EXPECTED_PAIRS = 192
EXPECTED_FOLDS_PER_PAIR = 5
RADIUS_KM = 10.0


def _canonical_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not stored or stored != calculated or stored != VNEXT_PROTOCOL_FINGERPRINT:
        raise ValueError(
            f"vNext protocol mismatch: stored={stored!r}, calculated={calculated!r}, "
            f"expected={VNEXT_PROTOCOL_FINGERPRINT!r}"
        )
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _ids(frame: pd.DataFrame) -> list[str]:
    for column in ("candidate_id", "site_id"):
        if column in frame.columns:
            return frame[column].astype(str).tolist()
    raise ValueError("candidate frame has no candidate_id/site_id")


def _inference(values: np.ndarray, draws: int, seed: int) -> dict[str, object]:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("pair differences must be finite")
    rng = np.random.default_rng(int(seed))
    bootstrap = rng.choice(values, size=(int(draws), len(values)), replace=True).mean(axis=1)
    null = rng.choice(np.array([-1.0, 1.0]), size=(int(draws), len(values))) * values
    null = null.mean(axis=1)
    observed = abs(float(values.mean()))
    return {
        "pairs": int(len(values)),
        "mean_difference": float(values.mean()),
        "bootstrap_95ci_low": float(np.quantile(bootstrap, 0.025)),
        "bootstrap_95ci_high": float(np.quantile(bootstrap, 0.975)),
        "sign_flip_p": float((1 + np.sum(np.abs(null) >= observed)) / (int(draws) + 1)),
        "positive_pairs": int(np.sum(values > 1e-12)),
        "negative_pairs": int(np.sum(values < -1e-12)),
        "tied_pairs": int(np.sum(np.abs(values) <= 1e-12)),
        "difference_sd": float(np.std(values, ddof=1)),
    }


def _pair_directories(pair_root: Path) -> dict[int, Path]:
    result: dict[int, Path] = {}
    failures = list(pair_root.rglob("infrastructure_failure.json"))
    if failures:
        raise RuntimeError(f"development source contains infrastructure markers: {len(failures)}")
    for summary_path in pair_root.rglob("pair_summary.json"):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        pair_id = int(summary["pair_id"])
        if pair_id in result:
            raise RuntimeError(f"duplicate pair artifact for pair {pair_id}")
        if summary.get("verified_scientific_artifact") is not True:
            raise RuntimeError(f"pair {pair_id} is not a verified scientific artifact")
        if str(summary.get("protocol_fingerprint")) != EXPECTED_FRESH_PROTOCOL:
            raise RuntimeError(f"pair {pair_id} came from an unexpected fresh protocol")
        result[pair_id] = summary_path.parent
    if sorted(result) != list(range(1, EXPECTED_PAIRS + 1)):
        raise RuntimeError(f"expected complete pair IDs 1..{EXPECTED_PAIRS}, found {len(result)}")
    return result


def _fold_statuses(pair_dir: Path) -> pd.DataFrame:
    fold_path = pair_dir / "fold_comparison.csv"
    frame = pd.read_csv(fold_path)
    if len(frame) != EXPECTED_FOLDS_PER_PAIR:
        raise RuntimeError(f"{pair_dir} has {len(frame)} folds, expected {EXPECTED_FOLDS_PER_PAIR}")
    return frame.sort_values("repeat", kind="mergesort").reset_index(drop=True)


def _development_fold(
    pair_id: int,
    pair_dir: Path,
    repeat: int,
    taxon_group: str,
) -> tuple[pd.DataFrame | None, dict[str, object]]:
    statuses = _fold_statuses(pair_dir)
    row = statuses.loc[pd.to_numeric(statuses["repeat"], errors="raise").eq(repeat)]
    if len(row) != 1:
        raise RuntimeError(f"pair {pair_id} repeat {repeat} is not unique")
    status = str(row["fold_status"].iloc[0])
    if status == "explicit_scientific_zero":
        return None, {
            "pair_id": pair_id,
            "repeat": repeat,
            "taxon_group": taxon_group,
            "fold_status": status,
            "v1_recovery_10km": 0.0,
            "rescue_v2_recovery_10km": float(row["rescue_recovery_10km"].iloc[0]),
        }
    if status != "complete":
        raise RuntimeError(f"pair {pair_id} repeat {repeat} has unexpected status {status!r}")

    fold_dir = pair_dir / f"fold_{repeat:03d}"
    candidate_path = fold_dir / "candidate_pool_pre_outcome.csv"
    heldout_path = fold_dir / "held_out_occurrences.csv"
    if not candidate_path.exists() or not heldout_path.exists():
        raise RuntimeError(f"pair {pair_id} repeat {repeat} lacks frozen candidate/heldout artifacts")
    candidates = pd.read_csv(candidate_path)
    heldout = pd.read_csv(heldout_path)
    features = build_vnext_features(candidates, taxon_group)
    v1_ids = frozen_v1_order(candidates, taxon_group)
    if len(v1_ids) < 5:
        raise RuntimeError(
            f"complete fold pair {pair_id} repeat {repeat} returned only {len(v1_ids)} frozen-v1 sites"
        )
    coverage, all_ids = _coverage_sets(candidates, heldout, RADIUS_KM)
    if not all_ids:
        raise RuntimeError(f"pair {pair_id} repeat {repeat} complete fold has no held-out IDs")
    anchors = v1_ids[:4]
    anchor_recovered: set[str] = set()
    for candidate_id in anchors:
        anchor_recovered |= coverage.get(candidate_id, set())

    training = features.loc[~features["_v1_anchor"].astype(bool)].copy()
    training["target_anchor4_marginal_recall"] = [
        len(coverage.get(str(candidate_id), set()) - anchor_recovered) / len(all_ids)
        for candidate_id in training["_stable_id"].astype(str)
    ]
    training["pair_id"] = pair_id
    training["repeat"] = repeat
    training["taxon_group_meta"] = taxon_group

    audit = {
        "pair_id": pair_id,
        "repeat": repeat,
        "taxon_group": taxon_group,
        "fold_status": status,
        "candidate_pool": int(len(candidates)),
        "heldout_records": int(len(all_ids)),
        "v1_recovery_10km": float(_recall(v1_ids, coverage, all_ids)),
        "rescue_v2_recovery_10km": float(row["rescue_recovery_10km"].iloc[0]),
    }
    return training, audit


def _load_source(pair_root: Path) -> tuple[dict[int, dict[str, object]], pd.DataFrame]:
    pair_dirs = _pair_directories(pair_root)
    pair_cache: dict[int, dict[str, object]] = {}
    all_training: list[pd.DataFrame] = []
    for pair_id, pair_dir in pair_dirs.items():
        summary = json.loads((pair_dir / "pair_summary.json").read_text(encoding="utf-8"))
        taxon_group = str(summary["taxon_group"])
        fold_items: list[dict[str, object]] = []
        for repeat in range(1, EXPECTED_FOLDS_PER_PAIR + 1):
            training, audit = _development_fold(pair_id, pair_dir, repeat, taxon_group)
            fold_items.append({"training": training, "audit": audit})
            if training is not None:
                all_training.append(training)
        pair_cache[pair_id] = {
            "pair_dir": pair_dir,
            "taxon_group": taxon_group,
            "scientific_name": str(summary["scientific_name"]),
            "region_name": str(summary["region_name"]),
            "rescue_v2_mean_recovery_10km": float(summary["rescue_mean_recovery_10km"]),
            "folds": fold_items,
        }
    combined = pd.concat(all_training, ignore_index=True) if all_training else pd.DataFrame()
    return pair_cache, combined


def _outer_assignment(pair_ids: list[int], folds: int, seed: int) -> dict[int, int]:
    rng = np.random.default_rng(int(seed))
    shuffled = np.asarray(sorted(pair_ids), dtype=int)
    shuffled = rng.permutation(shuffled)
    mapping: dict[int, int] = {}
    for position, pair_id in enumerate(shuffled.tolist()):
        mapping[int(pair_id)] = int(position % folds) + 1
    counts = pd.Series(mapping).value_counts().sort_index()
    if counts.max() - counts.min() > 1:
        raise AssertionError("outer pair folds are unexpectedly imbalanced")
    return mapping


def _score_pair(pair_id: int, info: dict[str, object], estimator: object, outer_fold: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    fold_rows: list[dict[str, object]] = []
    replacements = 0
    for item in info["folds"]:
        audit = dict(item["audit"])
        repeat = int(audit["repeat"])
        if audit["fold_status"] == "explicit_scientific_zero":
            vnext_recovery = 0.0
            replaced = False
        else:
            pair_dir = Path(info["pair_dir"])
            candidates = pd.read_csv(pair_dir / f"fold_{repeat:03d}" / "candidate_pool_pre_outcome.csv")
            heldout = pd.read_csv(pair_dir / f"fold_{repeat:03d}" / "held_out_occurrences.csv")
            selected = select_vnext_anchored_fifth(candidates, str(info["taxon_group"]), estimator)
            selected_ids = _ids(selected)
            coverage, all_ids = _coverage_sets(candidates, heldout, RADIUS_KM)
            vnext_recovery = float(_recall(selected_ids, coverage, all_ids))
            replaced = bool(selected["vnext_replaced_frozen_v1_fifth"].iloc[0]) if not selected.empty else False
            replacements += int(replaced)
        fold_rows.append({
            **audit,
            "outer_fold": outer_fold,
            "vnext_recovery_10km": vnext_recovery,
            "vnext_minus_v1": vnext_recovery - float(audit["v1_recovery_10km"]),
            "vnext_replaced_frozen_v1_fifth": replaced,
        })
    fold_frame = pd.DataFrame(fold_rows)
    pair_row = {
        "pair_id": pair_id,
        "outer_fold": outer_fold,
        "taxon_group": str(info["taxon_group"]),
        "scientific_name": str(info["scientific_name"]),
        "region_name": str(info["region_name"]),
        "vnext_mean_recovery_10km": float(fold_frame["vnext_recovery_10km"].mean()),
        "frozen_v1_mean_recovery_10km": float(fold_frame["v1_recovery_10km"].mean()),
        "rescue_v2_mean_recovery_10km": float(info["rescue_v2_mean_recovery_10km"]),
        "vnext_minus_frozen_v1": float(fold_frame["vnext_minus_v1"].mean()),
        "replacement_folds": int(replacements),
        "complete_folds": int(fold_frame["fold_status"].eq("complete").sum()),
        "scientific_zero_folds": int(fold_frame["fold_status"].eq("explicit_scientific_zero").sum()),
    }
    return fold_rows, pair_row


def run(pair_root: Path, protocol_path: Path, output: Path) -> dict[str, object]:
    protocol, fingerprint = _canonical_protocol(protocol_path)
    pair_cache, all_training = _load_source(pair_root)
    assignment = _outer_assignment(
        list(pair_cache),
        int(protocol["development_evaluation"]["outer_pair_folds"]),
        int(protocol["development_evaluation"]["pair_assignment_seed"]),
    )
    columns = [*VNEXT_NUMERIC_FEATURES, *VNEXT_CATEGORICAL_FEATURES]
    if not set(columns).issubset(all_training.columns):
        missing = sorted(set(columns) - set(all_training.columns))
        raise RuntimeError(f"training source lacks vNext features: {missing}")
    forbidden_tokens = ("heldout", "held_out", "scientific_name", "region_name", "grts")
    bad = [column for column in columns if any(token in column.lower() for token in forbidden_tokens)]
    if bad:
        raise RuntimeError(f"forbidden inference feature names: {bad}")

    fold_results: list[dict[str, object]] = []
    pair_results: list[dict[str, object]] = []
    outer_folds = sorted(set(assignment.values()))
    for outer_fold in outer_folds:
        train_pairs = {pair_id for pair_id, fold in assignment.items() if fold != outer_fold}
        test_pairs = sorted(pair_id for pair_id, fold in assignment.items() if fold == outer_fold)
        train = all_training[all_training["pair_id"].astype(int).isin(train_pairs)].copy()
        if train.empty:
            raise RuntimeError(f"outer fold {outer_fold} has no training rows")
        estimator = make_vnext_estimator()
        estimator.fit(train[columns], pd.to_numeric(train["target_anchor4_marginal_recall"], errors="raise"))
        for pair_id in test_pairs:
            folds, pair = _score_pair(pair_id, pair_cache[pair_id], estimator, outer_fold)
            fold_results.extend(folds)
            pair_results.append(pair)

    pair = pd.DataFrame(pair_results).sort_values("pair_id", kind="mergesort").reset_index(drop=True)
    fold = pd.DataFrame(fold_results).sort_values(["pair_id", "repeat"], kind="mergesort").reset_index(drop=True)
    if len(pair) != EXPECTED_PAIRS or pair["pair_id"].nunique() != EXPECTED_PAIRS:
        raise RuntimeError("vNext cross-fit did not evaluate exactly 192 pairs")
    if len(fold) != EXPECTED_PAIRS * EXPECTED_FOLDS_PER_PAIR:
        raise RuntimeError("vNext cross-fit did not evaluate exactly 960 folds")

    inference_cfg = protocol["development_evaluation"]
    primary = _inference(
        pair["vnext_minus_frozen_v1"].to_numpy(float),
        int(inference_cfg["bootstrap_draws"]),
        int(inference_cfg["inference_seed"]),
    )
    threshold = float(protocol["learned_fifth_slot"]["replacement_margin_absolute_recall"])
    passed = bool(
        primary["mean_difference"] >= threshold
        and primary["bootstrap_95ci_low"] > 0
        and primary["sign_flip_p"] < 0.05
    )
    by_group = {
        str(group): _inference(
            subset["vnext_minus_frozen_v1"].to_numpy(float),
            int(inference_cfg["bootstrap_draws"]),
            int(inference_cfg["inference_seed"]) + (1 if str(group) == "plant" else 2),
        )
        for group, subset in pair.groupby("taxon_group")
    }

    output.mkdir(parents=True, exist_ok=True)
    pair.to_csv(output / "pair_level_comparison.csv", index=False)
    fold.to_csv(output / "fold_level_comparison.csv", index=False)
    pd.DataFrame([
        {"pair_id": pair_id, "outer_fold": outer_fold}
        for pair_id, outer_fold in sorted(assignment.items())
    ]).to_csv(output / "outer_pair_assignment.csv", index=False)
    manifest = {
        "status": "vnext_anchored_fifth_development_crossfit_evaluated",
        "protocol_fingerprint": fingerprint,
        "source_fresh_run_id": int(protocol["redesign_basis"]["failed_confirmation_run_id"]),
        "source_fresh_confirmation_reclassified_as_development": True,
        "declared_pairs": EXPECTED_PAIRS,
        "evaluated_pairs": int(len(pair)),
        "evaluated_folds": int(len(fold)),
        "training_rows": int(len(all_training)),
        "outer_pair_folds": int(len(outer_folds)),
        "primary_contrast": "vnext_minus_frozen_v1",
        "primary_inference": primary,
        "taxon_group_inference": by_group,
        "replacement_margin_absolute_recall": threshold,
        "replacement_folds": int(fold["vnext_replaced_frozen_v1_fifth"].astype(bool).sum()),
        "complete_folds": int(fold["fold_status"].eq("complete").sum()),
        "scientific_zero_folds": int(fold["fold_status"].eq("explicit_scientific_zero").sum()),
        "development_gate_passed": passed,
        "new_untouched_confirmation_required": True,
        "source_outcomes_available_to_vnext_training": True,
        "outcomes_available_to_selector_at_test_inference": False,
        "candidate_frames_regenerated": False,
    }
    (output / "development_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-root", type=Path, required=True)
    command.add_argument("--protocol", dest="protocol_path", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
