#!/usr/bin/env python3
"""Run one fully fresh confirmation pair for frozen Practical Rescue vs GRTS.

Operational selections use only training-fold candidate attributes plus the
already-frozen final rescue model. Held-out coordinates are scored only after
both the rescue Top-5 and all official GRTS draws have been written to disk.
Unexpected infrastructure failures are not converted to scientific zeroes: the
process exits without a verified pair summary so strict aggregation invalidates
the confirmation until the pair is rerun successfully.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess

import joblib
import numpy as np
import pandas as pd
import sklearn

from acsp.practical_rescue import (
    RESCUE_CATEGORICAL_FEATURES,
    RESCUE_NUMERIC_FEATURES,
    build_rescue_features,
    select_local_anchor_rescue,
)
from benchmark_general_random_taxa_regions import fetch_occurrences
from run_practical_core_confirmation_pair import (
    _coord_columns,
    _coverage_sets,
    _recall,
    _sha256,
    _split_ids,
    build_candidate_pool,
)


def _canonical_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not stored or stored != calculated:
        raise ValueError(
            f"fresh confirmation protocol mismatch: stored={stored!r}, calculated={calculated!r}"
        )
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _stable_ids(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "candidate_id" not in frame.columns:
        return []
    return frame["candidate_id"].astype(str).tolist()


def _model_contract(
    model_path: Path,
    model_manifest_path: Path,
    protocol: dict[str, object],
) -> tuple[object, dict[str, object]]:
    expected = protocol["final_model"]
    manifest_hash = _sha256(model_manifest_path)
    model_hash = _sha256(model_path)
    if manifest_hash != str(expected["model_manifest_sha256"]):
        raise ValueError("final model manifest hash differs from frozen confirmation protocol")
    if model_hash != str(expected["model_sha256"]):
        raise ValueError("final rescue model hash differs from frozen confirmation protocol")
    manifest = json.loads(model_manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("model_sha256")) != model_hash:
        raise ValueError("final model manifest does not self-report the frozen model hash")
    if int(manifest.get("development_pairs", 0)) != 72:
        raise ValueError("final model was not fitted to exactly 72 frozen development pairs")
    if manifest.get("grts_outcomes_used_as_model_features_or_targets") is not False:
        raise ValueError("final model manifest permits GRTS outcomes in training")
    if manifest.get("model_hyperparameters_changed_after_grts_gate") is not False:
        raise ValueError("final model manifest reports post-GRTS retuning")
    if str(manifest.get("rescue_protocol_fingerprint")) != str(expected["rescue_protocol_fingerprint"]):
        raise ValueError("final model rescue protocol fingerprint mismatch")
    if str(manifest.get("grts_development_protocol_fingerprint")) != str(expected["grts_development_protocol_fingerprint"]):
        raise ValueError("final model GRTS development fingerprint mismatch")
    runtime = protocol["software_contract"]
    actual = {
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "joblib": joblib.__version__,
    }
    for key in ("python", "scikit_learn", "pandas", "numpy"):
        if str(actual[key]) != str(runtime[key]):
            raise ValueError(f"fresh confirmation runtime mismatch for {key}: {actual[key]} != {runtime[key]}")
    return joblib.load(model_path), manifest


def _run_grts(
    candidate_path: Path,
    output_path: Path,
    pair_id: int,
    repeat: int,
    protocol: dict[str, object],
) -> pd.DataFrame:
    grts = protocol["official_grts"]
    command = [
        "Rscript",
        "benchmark_methods/grts_rescue_primary_batch.R",
        "--input", str(candidate_path),
        "--output", str(output_path),
        "--draws", str(int(grts["draws_per_fold"])),
        "--seed-base", str(int(grts["seed_base"])),
        "--global-pair-id", str(int(pair_id)),
        "--repeat", str(int(repeat)),
        "--k", str(int(grts["top_k"])),
        "--replacements", str(int(grts["replacement_sites"])),
        "--score-col", str(grts["score_col"]),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0 or not output_path.exists():
        raise RuntimeError(
            "official GRTS subprocess failed before a verified pre-outcome artifact was frozen: "
            + completed.stderr[-4000:]
        )
    draws = pd.read_csv(output_path)
    expected = int(grts["draws_per_fold"])
    if len(draws) != expected:
        raise RuntimeError(f"official GRTS wrote {len(draws)} draws, expected {expected}")
    if draws["outcomes_available_to_selector"].astype(str).str.lower().isin({"true", "1"}).any():
        raise RuntimeError("official GRTS artifact reports held-out outcome access")
    return draws


def _scientific_zero_fold(
    pair: pd.Series,
    repeat: int,
    reason: str,
    candidate_pool: int,
) -> dict[str, object]:
    return {
        "pair_id": int(pair.pair_id),
        "repeat": int(repeat),
        "taxon_group": str(pair.taxon_group),
        "scientific_name": str(pair.scientific_name),
        "region_name": str(pair.region_name),
        "fold_status": "explicit_scientific_zero",
        "scientific_zero_reason": reason,
        "candidate_pool": int(candidate_pool),
        "heldout_records": 0,
        "rescue_recovery_10km": 0.0,
        "grts_mean_recovery_10km": 0.0,
        "grts_valid_base_draws": 0,
        "grts_warning_draws": 0,
        "grts_error_draws": 0,
        "outcomes_available_to_rescue_selector": False,
        "outcomes_available_to_grts_selector": False,
    }


def _write_pair_summary(
    root: Path,
    pair: pd.Series,
    protocol_fp: str,
    model_hash: str,
    folds: pd.DataFrame,
    pair_status: str,
) -> dict[str, object]:
    folds.to_csv(root / "fold_comparison.csv", index=False)
    summary = {
        "pair_id": int(pair.pair_id),
        "scientific_name": str(pair.scientific_name),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "pair_status": pair_status,
        "protocol_fingerprint": protocol_fp,
        "final_model_sha256": model_hash,
        "verified_scientific_artifact": True,
        "expected_repeats": int(len(folds)),
        "explicit_scientific_zero_folds": int(folds["fold_status"].eq("explicit_scientific_zero").sum()),
        "rescue_mean_recovery_10km": float(pd.to_numeric(folds["rescue_recovery_10km"], errors="raise").mean()),
        "grts_mean_recovery_10km": float(pd.to_numeric(folds["grts_mean_recovery_10km"], errors="raise").mean()),
        "grts_valid_base_draws": int(pd.to_numeric(folds["grts_valid_base_draws"], errors="coerce").fillna(0).sum()),
        "grts_warning_draws": int(pd.to_numeric(folds["grts_warning_draws"], errors="coerce").fillna(0).sum()),
        "grts_error_draws": int(pd.to_numeric(folds["grts_error_draws"], errors="coerce").fillna(0).sum()),
        "outcomes_available_to_rescue_selector": False,
        "outcomes_available_to_grts_selector": False,
        "fold_comparison_sha256": _sha256(root / "fold_comparison.csv"),
    }
    (root / "pair_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def run(args: argparse.Namespace) -> dict[str, object]:
    protocol, protocol_fp = _canonical_protocol(args.protocol)
    estimator, model_manifest = _model_contract(
        args.model, args.model_manifest, protocol
    )
    model_hash = _sha256(args.model)

    cohort = pd.read_csv(args.cohort)
    chosen = cohort[pd.to_numeric(cohort["pair_id"], errors="coerce").eq(args.pair_id)]
    if len(chosen) != 1:
        raise ValueError(f"pair_id {args.pair_id} is not uniquely present in fresh cohort")
    pair = chosen.iloc[0]
    root = args.output / f"pair_{int(pair.pair_id):03d}"
    root.mkdir(parents=True, exist_ok=True)

    # Network/API failures remain infrastructure failures: do not catch them and
    # do not manufacture a zero-valued pair_summary.json.
    occurrences = fetch_occurrences(pair, int(protocol["cohort"]["records_per_pair"]))
    latitude_col, longitude_col = _coord_columns(occurrences)
    work = occurrences.copy().reset_index(drop=True)
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)

    repeats = int(protocol["outer_validation"]["repeats"])
    if len(work) < 4:
        folds = pd.DataFrame([
            _scientific_zero_fold(pair, repeat, "fewer_than_four_valid_occurrence_coordinates", 0)
            for repeat in range(1, repeats + 1)
        ])
        return _write_pair_summary(root, pair, protocol_fp, model_hash, folds, "scientific_ineligible")

    work["_outer_occurrence_id"] = [
        f"fresh-pair{int(pair.pair_id):03d}-occurrence{index + 1:05d}"
        for index in range(len(work))
    ]
    block = float(protocol["outer_validation"]["block_degrees"])
    work["_outer_block"] = (
        np.floor(work[latitude_col] / block).astype(int).astype(str)
        + ":"
        + np.floor(work[longitude_col] / block).astype(int).astype(str)
    )
    blocks = work["_outer_block"].drop_duplicates().to_numpy()
    if len(blocks) < 2:
        folds = pd.DataFrame([
            _scientific_zero_fold(pair, repeat, "fewer_than_two_outer_spatial_blocks", 0)
            for repeat in range(1, repeats + 1)
        ])
        return _write_pair_summary(root, pair, protocol_fp, model_hash, folds, "scientific_ineligible")

    rng = np.random.default_rng(
        int(protocol["outer_validation"]["fold_seed_base"]) + int(pair.pair_id)
    )
    n_holdout = min(
        len(blocks) - 1,
        max(1, int(round(len(blocks) * float(protocol["outer_validation"]["holdout_fraction"])))),
    )
    fold_rows: list[dict[str, object]] = []
    for repeat in range(1, repeats + 1):
        fold_dir = root / f"fold_{repeat:03d}"
        fold_dir.mkdir(parents=True, exist_ok=True)
        held_blocks = set(rng.choice(blocks, size=n_holdout, replace=False).tolist())
        heldout = work[work["_outer_block"].isin(held_blocks)].copy().reset_index(drop=True)
        training = (
            work[~work["_outer_block"].isin(held_blocks)]
            .drop(columns=["_outer_block", "_outer_occurrence_id"])
            .copy()
            .reset_index(drop=True)
        )
        candidates = build_candidate_pool(training, pair, repeat)
        candidate_path = fold_dir / "candidate_pool_pre_outcome.csv"
        candidates.to_csv(candidate_path, index=False)

        if len(candidates) < int(protocol["official_grts"]["top_k"]):
            fold_rows.append(
                _scientific_zero_fold(
                    pair, repeat, "training_only_candidate_pool_below_top_k", len(candidates)
                )
            )
            continue

        features = build_rescue_features(candidates, str(pair.taxon_group))
        if len(features) != len(candidates):
            raise RuntimeError("fresh rescue feature rows differ from eligible shared candidate rows")
        columns = [*RESCUE_NUMERIC_FEATURES, *RESCUE_CATEGORICAL_FEATURES]
        predictions = estimator.predict(features[columns])
        rescue_selected = select_local_anchor_rescue(candidates, predictions)
        rescue_ids = _stable_ids(rescue_selected)
        if len(rescue_ids) != int(protocol["official_grts"]["top_k"]):
            raise RuntimeError("frozen rescue selector did not return the declared Top-k")
        rescue_decision_path = fold_dir / "rescue_decision_pre_outcome.json"
        rescue_decision_path.write_text(
            json.dumps({
                "pair_id": int(pair.pair_id),
                "repeat": int(repeat),
                "selected_ids": rescue_ids,
                "model_sha256": model_hash,
                "protocol_fingerprint": protocol_fp,
                "outcomes_available_to_selector": False,
            }, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        grts_path = fold_dir / "grts_draws_pre_outcome.csv"
        grts_draws = _run_grts(candidate_path, grts_path, int(pair.pair_id), repeat, protocol)

        # Outcome attachment starts only after both pre-outcome artifacts above exist.
        if not rescue_decision_path.exists() or not grts_path.exists():
            raise RuntimeError("pre-outcome decisions were not physically frozen before scoring")
        coverage, all_ids = _coverage_sets(
            candidates, heldout, float(protocol["estimand"]["radius_km"])
        )
        rescue_recovery = _recall(rescue_ids, coverage, all_ids)
        grts_recoveries: list[float] = []
        valid_draws = 0
        warning_draws = 0
        error_draws = 0
        scored = grts_draws.copy()
        for row in grts_draws.itertuples(index=False):
            ids = _split_ids(row.base_ids)
            error = "" if pd.isna(row.error_message) else str(row.error_message)
            warning = "" if pd.isna(row.warning_message) else str(row.warning_message)
            value = _recall(ids, coverage, all_ids) if ids else 0.0
            grts_recoveries.append(value)
            if ids and not error:
                valid_draws += 1
            warning_draws += int(bool(warning))
            error_draws += int(bool(error))
        scored["heldout_recovery_10km"] = grts_recoveries
        scored["outcomes_attached_after_selection"] = True
        scored.to_csv(fold_dir / "grts_draws_scored.csv", index=False)
        heldout.to_csv(fold_dir / "held_out_occurrences.csv", index=False)

        fold_row = {
            "pair_id": int(pair.pair_id),
            "repeat": int(repeat),
            "taxon_group": str(pair.taxon_group),
            "scientific_name": str(pair.scientific_name),
            "region_name": str(pair.region_name),
            "fold_status": "complete",
            "scientific_zero_reason": "",
            "candidate_pool": int(len(candidates)),
            "heldout_records": int(len(all_ids)),
            "rescue_recovery_10km": float(rescue_recovery),
            "grts_mean_recovery_10km": float(np.mean(grts_recoveries)),
            "grts_valid_base_draws": int(valid_draws),
            "grts_warning_draws": int(warning_draws),
            "grts_error_draws": int(error_draws),
            "outcomes_available_to_rescue_selector": False,
            "outcomes_available_to_grts_selector": False,
            "candidate_pool_pre_outcome_sha256": _sha256(candidate_path),
            "rescue_decision_pre_outcome_sha256": _sha256(rescue_decision_path),
            "grts_draws_pre_outcome_sha256": _sha256(grts_path),
        }
        (fold_dir / "fold_summary.json").write_text(
            json.dumps(fold_row, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        fold_rows.append(fold_row)

    folds = pd.DataFrame(fold_rows)
    if len(folds) != repeats:
        raise RuntimeError(f"fresh pair wrote {len(folds)} fold rows, expected {repeats}")
    return _write_pair_summary(root, pair, protocol_fp, model_hash, folds, "complete")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-id", type=int, required=True)
    command.add_argument("--cohort", type=Path, required=True)
    command.add_argument("--model", type=Path, required=True)
    command.add_argument("--model-manifest", type=Path, required=True)
    command.add_argument("--protocol", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
