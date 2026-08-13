#!/usr/bin/env python3
"""Run one untouched vNext2 confirmation pair with fully frozen pre-outcome decisions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn

from acsp.decision_baselines import (
    DecisionBaselineConfig,
    random_same_pool_sets,
    select_geographic_farthest,
)
from acsp.practical_core import PracticalCorePolicy, select_practical_core
from acsp.practical_rescue import (
    RESCUE_CATEGORICAL_FEATURES,
    RESCUE_NUMERIC_FEATURES,
    build_rescue_features,
    select_local_anchor_rescue,
)
from acsp.practical_rescue_router import (
    ROUTER_PROTOCOL_FINGERPRINT,
    build_router_features,
    frozen_v1_ids,
    predict_linear_router_artifact,
    select_routed_candidates,
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
from run_practical_rescue_fresh_confirmation_pair_v2 import _run_grts_v2


EXPECTED_RESCUE_MODEL_SHA = "e5fde07f4aaad1ae5dcadb989169fd17ef428ac2be7577f5fd382c4f12fb45a3"
EXPECTED_ROUTER_PROTOCOL = "988243d9acbb20b16fcf7ec307db8c3a5325c3abd7ba71835da5e9911bc0cad6"


def _canonical_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not stored or stored != calculated:
        raise ValueError(
            f"vNext2 confirmation protocol mismatch: stored={stored!r}, calculated={calculated!r}"
        )
    if payload.get("protocol_id") != "acsp-practical-rescue-vnext2-untouched-confirmation-v1":
        raise ValueError("unexpected vNext2 confirmation protocol ID")
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _stable_ids(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "candidate_id" not in frame.columns:
        return []
    return frame["candidate_id"].astype(str).tolist()


def _load_rescue_model(
    model_path: Path,
    manifest_path: Path,
    protocol: dict[str, object],
) -> object:
    expected = protocol["final_rescue_v2"]
    model_hash = _sha256(model_path)
    manifest_hash = _sha256(manifest_path)
    if model_hash != str(expected["model_sha256"]) or model_hash != EXPECTED_RESCUE_MODEL_SHA:
        raise ValueError("frozen Rescue-v2 model hash differs from vNext2 protocol")
    if manifest_hash != str(expected["model_manifest_sha256"]):
        raise ValueError("frozen Rescue-v2 manifest hash differs from vNext2 protocol")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("model_sha256")) != model_hash:
        raise ValueError("Rescue-v2 manifest does not self-report the frozen model hash")
    if manifest.get("grts_outcomes_used_as_model_features_or_targets") is not False:
        raise ValueError("Rescue-v2 model reports GRTS outcomes in training")
    if manifest.get("model_hyperparameters_changed_after_grts_gate") is not False:
        raise ValueError("Rescue-v2 model reports post-GRTS retuning")
    if str(manifest.get("rescue_protocol_fingerprint")) != str(expected["rescue_protocol_fingerprint"]):
        raise ValueError("Rescue-v2 protocol fingerprint mismatch")
    if str(manifest.get("grts_development_protocol_fingerprint")) != str(expected["grts_development_protocol_fingerprint"]):
        raise ValueError("Rescue-v2 corrected-GRTS development fingerprint mismatch")
    return joblib.load(model_path)


def _load_router(
    router_path: Path,
    manifest_path: Path,
    protocol: dict[str, object],
) -> tuple[dict[str, object], str]:
    expected = protocol["final_router"]
    router_hash = _sha256(router_path)
    manifest_hash = _sha256(manifest_path)
    if router_hash != str(expected["model_sha256"]):
        raise ValueError("vNext2 router bytes differ from frozen protocol")
    if manifest_hash != str(expected["model_manifest_sha256"]):
        raise ValueError("vNext2 router manifest bytes differ from frozen protocol")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    router = json.loads(router_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "final_vnext2_router_fitted_after_complete_development_gate":
        raise ValueError("vNext2 router manifest is not a final passed development fit")
    if str(manifest.get("model_sha256")) != router_hash:
        raise ValueError("vNext2 router manifest hash disagrees with router bytes")
    if str(manifest.get("model_fingerprint")) != str(expected["model_fingerprint"]):
        raise ValueError("vNext2 router model fingerprint differs from frozen protocol")
    if str(router.get("model_fingerprint")) != str(expected["model_fingerprint"]):
        raise ValueError("vNext2 router JSON model fingerprint differs from frozen protocol")
    if str(manifest.get("protocol_fingerprint")) != EXPECTED_ROUTER_PROTOCOL:
        raise ValueError("vNext2 router manifest protocol mismatch")
    if str(router.get("protocol_fingerprint")) != EXPECTED_ROUTER_PROTOCOL:
        raise ValueError("vNext2 router JSON protocol mismatch")
    if manifest.get("confirmation_outcomes_used_for_fit") is not False:
        raise ValueError("vNext2 router reports confirmation outcomes in fit")
    if manifest.get("hyperparameters_changed_after_development_gate") is not False:
        raise ValueError("vNext2 router reports post-development retuning")
    if float(manifest.get("decision_threshold_absolute_recall", -1)) != 0.015:
        raise ValueError("vNext2 router threshold differs from frozen 0.015")
    if float(manifest.get("ridge_alpha", -1)) != 10.0:
        raise ValueError("vNext2 router alpha differs from frozen 10")
    return router, router_hash


def _assert_runtime(protocol: dict[str, object]) -> None:
    expected = protocol["software_contract"]
    actual = {
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }
    for key, value in actual.items():
        if str(value) != str(expected[key]):
            raise ValueError(f"vNext2 runtime mismatch for {key}: {value} != {expected[key]}")


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
        "router_recovery_10km": 0.0,
        "frozen_v1_recovery_10km": 0.0,
        "rescue_v2_recovery_10km": 0.0,
        "grts_mean_recovery_10km": 0.0,
        "local_only_recovery_10km": 0.0,
        "geographic_recovery_10km": 0.0,
        "random_mean_recovery_10km": 0.0,
        "router_predicted_rescue_minus_v1": 0.0,
        "router_chosen_policy": "explicit_scientific_zero",
        "grts_valid_base_draws": 0,
        "grts_warning_draws": 0,
        "grts_error_draws": 0,
        "outcomes_available_to_router": False,
        "outcomes_available_to_v1_selector": False,
        "outcomes_available_to_rescue_selector": False,
        "outcomes_available_to_grts_selector": False,
        "outcomes_available_to_secondary_selectors": False,
    }


def _write_pair_summary(
    root: Path,
    pair: pd.Series,
    protocol_fp: str,
    rescue_model_hash: str,
    router_hash: str,
    router_model_fingerprint: str,
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
        "rescue_v2_model_sha256": rescue_model_hash,
        "router_model_sha256": router_hash,
        "router_model_fingerprint": router_model_fingerprint,
        "verified_scientific_artifact": True,
        "expected_repeats": int(len(folds)),
        "explicit_scientific_zero_folds": int(folds["fold_status"].eq("explicit_scientific_zero").sum()),
        "router_mean_recovery_10km": float(pd.to_numeric(folds["router_recovery_10km"], errors="raise").mean()),
        "frozen_v1_mean_recovery_10km": float(pd.to_numeric(folds["frozen_v1_recovery_10km"], errors="raise").mean()),
        "rescue_v2_mean_recovery_10km": float(pd.to_numeric(folds["rescue_v2_recovery_10km"], errors="raise").mean()),
        "grts_mean_recovery_10km": float(pd.to_numeric(folds["grts_mean_recovery_10km"], errors="raise").mean()),
        "local_only_mean_recovery_10km": float(pd.to_numeric(folds["local_only_recovery_10km"], errors="raise").mean()),
        "geographic_mean_recovery_10km": float(pd.to_numeric(folds["geographic_recovery_10km"], errors="raise").mean()),
        "random_mean_recovery_10km": float(pd.to_numeric(folds["random_mean_recovery_10km"], errors="raise").mean()),
        "router_rescue_selected_folds": int(folds["router_chosen_policy"].eq("frozen_rescue_v2").sum()),
        "router_v1_selected_folds": int(folds["router_chosen_policy"].eq("frozen_v1").sum()),
        "grts_valid_base_draws": int(pd.to_numeric(folds["grts_valid_base_draws"], errors="coerce").fillna(0).sum()),
        "grts_warning_draws": int(pd.to_numeric(folds["grts_warning_draws"], errors="coerce").fillna(0).sum()),
        "grts_error_draws": int(pd.to_numeric(folds["grts_error_draws"], errors="coerce").fillna(0).sum()),
        "outcomes_available_to_router": False,
        "outcomes_available_to_v1_selector": False,
        "outcomes_available_to_rescue_selector": False,
        "outcomes_available_to_grts_selector": False,
        "outcomes_available_to_secondary_selectors": False,
        "fold_comparison_sha256": _sha256(root / "fold_comparison.csv"),
    }
    (root / "pair_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def run(args: argparse.Namespace) -> dict[str, object]:
    protocol, protocol_fp = _canonical_protocol(args.protocol)
    _assert_runtime(protocol)
    rescue_estimator = _load_rescue_model(args.rescue_model, args.rescue_model_manifest, protocol)
    rescue_model_hash = _sha256(args.rescue_model)
    router, router_hash = _load_router(args.router_model, args.router_model_manifest, protocol)
    router_model_fingerprint = str(router["model_fingerprint"])

    cohort = pd.read_csv(args.cohort)
    chosen = cohort[pd.to_numeric(cohort["pair_id"], errors="coerce").eq(args.pair_id)]
    if len(chosen) != 1:
        raise ValueError(f"pair_id {args.pair_id} is not uniquely present in vNext2 cohort")
    pair = chosen.iloc[0]
    root = args.output / f"pair_{int(pair.pair_id):03d}"
    root.mkdir(parents=True, exist_ok=True)

    # API/network failures remain infrastructure failures and are never converted
    # to scientific zeroes or replacement taxa.
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
        return _write_pair_summary(
            root, pair, protocol_fp, rescue_model_hash, router_hash,
            router_model_fingerprint, folds, "scientific_ineligible"
        )

    work["_outer_occurrence_id"] = [
        f"vnext2-pair{int(pair.pair_id):03d}-occurrence{index + 1:05d}"
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
        return _write_pair_summary(
            root, pair, protocol_fp, rescue_model_hash, router_hash,
            router_model_fingerprint, folds, "scientific_ineligible"
        )

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
        top_k = int(protocol["official_grts"]["top_k"])
        if len(candidates) < top_k:
            fold_rows.append(
                _scientific_zero_fold(
                    pair, repeat, "training_only_candidate_pool_below_top_k", len(candidates)
                )
            )
            continue

        # Frozen Rescue-v2 decision.
        rescue_features = build_rescue_features(candidates, str(pair.taxon_group))
        rescue_columns = [*RESCUE_NUMERIC_FEATURES, *RESCUE_CATEGORICAL_FEATURES]
        rescue_predictions = rescue_estimator.predict(rescue_features[rescue_columns])
        rescue_selected = select_local_anchor_rescue(candidates, rescue_predictions)
        rescue_ids = _stable_ids(rescue_selected)
        if len(rescue_ids) != top_k:
            raise RuntimeError("frozen Rescue-v2 did not return Top-5")
        rescue_path = fold_dir / "rescue_v2_decision_pre_outcome.json"
        rescue_path.write_text(
            json.dumps({
                "pair_id": int(pair.pair_id),
                "repeat": repeat,
                "selected_ids": rescue_ids,
                "model_sha256": rescue_model_hash,
                "outcomes_available_to_selector": False,
            }, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Frozen v1 decision and safe-router decision.
        v1_ids = frozen_v1_ids(candidates, str(pair.taxon_group))
        if len(v1_ids) != top_k:
            raise RuntimeError("frozen v1 did not return Top-5")
        v1_path = fold_dir / "frozen_v1_decision_pre_outcome.json"
        v1_path.write_text(
            json.dumps({
                "pair_id": int(pair.pair_id),
                "repeat": repeat,
                "selected_ids": v1_ids,
                "outcomes_available_to_selector": False,
            }, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        router_features = build_router_features(
            candidates, str(pair.taxon_group), v1_ids, rescue_ids
        )
        router_prediction = float(predict_linear_router_artifact(router_features, router)[0])
        routed = select_routed_candidates(
            candidates, v1_ids, rescue_ids, router_prediction
        )
        router_ids = _stable_ids(routed)
        chosen_policy = str(routed["router_chosen_policy"].iloc[0])
        if router_ids not in (v1_ids, rescue_ids):
            raise RuntimeError("router altered a frozen policy set instead of selecting one unchanged")
        router_path = fold_dir / "router_decision_pre_outcome.json"
        router_path.write_text(
            json.dumps({
                "pair_id": int(pair.pair_id),
                "repeat": repeat,
                "selected_ids": router_ids,
                "chosen_policy": chosen_policy,
                "predicted_rescue_minus_v1": router_prediction,
                "decision_threshold_absolute_recall": 0.015,
                "router_model_sha256": router_hash,
                "router_model_fingerprint": router_model_fingerprint,
                "router_protocol_fingerprint": ROUTER_PROTOCOL_FINGERPRINT,
                "outcomes_available_to_selector": False,
            }, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Secondary same-pool decisions are descriptive only but frozen before scoring.
        local_selected = select_practical_core(candidates, PracticalCorePolicy(top_k=top_k))
        local_ids = _stable_ids(local_selected)
        baseline_cfg = DecisionBaselineConfig(
            k=top_k,
            id_col="candidate_id",
            score_col="component_local_habitat_score",
            random_draws=50,
            random_state=int(protocol["inference"]["seed"]) + int(pair.pair_id) * 1000 + repeat,
        )
        geographic_ids = _stable_ids(select_geographic_farthest(candidates, baseline_cfg))
        random_ids = [_stable_ids(draw) for draw in random_same_pool_sets(candidates, baseline_cfg)]
        secondary_path = fold_dir / "secondary_decisions_pre_outcome.json"
        secondary_path.write_text(
            json.dumps({
                "pair_id": int(pair.pair_id),
                "repeat": repeat,
                "local_only_ids": local_ids,
                "geographic_ids": geographic_ids,
                "random_ids": random_ids,
                "random_draws": 50,
                "random_seed": baseline_cfg.random_state,
                "outcomes_available_to_selectors": False,
            }, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Corrected official GRTS is also frozen before scoring.
        grts_path = fold_dir / "grts_draws_pre_outcome.csv"
        grts_draws = _run_grts_v2(
            candidate_path, grts_path, int(pair.pair_id), repeat, protocol
        )

        pre_outcome_paths = [
            candidate_path, rescue_path, v1_path, router_path, secondary_path, grts_path
        ]
        if not all(path.exists() for path in pre_outcome_paths):
            raise RuntimeError("not all vNext2 pre-outcome decisions were physically frozen before scoring")

        # Held-out scoring starts only here.
        coverage, all_ids = _coverage_sets(
            candidates, heldout, float(protocol["estimand"]["radius_km"])
        )
        router_recovery = float(_recall(router_ids, coverage, all_ids))
        v1_recovery = float(_recall(v1_ids, coverage, all_ids))
        rescue_recovery = float(_recall(rescue_ids, coverage, all_ids))
        local_recovery = float(_recall(local_ids, coverage, all_ids))
        geographic_recovery = float(_recall(geographic_ids, coverage, all_ids))
        random_recoveries = [float(_recall(ids, coverage, all_ids)) for ids in random_ids]

        grts_recoveries: list[float] = []
        valid_draws = 0
        warning_draws = 0
        error_draws = 0
        scored_grts = grts_draws.copy()
        for row in grts_draws.itertuples(index=False):
            ids = _split_ids(row.base_ids)
            error = "" if pd.isna(row.error_message) else str(row.error_message)
            warning = "" if pd.isna(row.warning_message) else str(row.warning_message)
            grts_recoveries.append(float(_recall(ids, coverage, all_ids)) if ids else 0.0)
            if ids and not error:
                valid_draws += 1
            warning_draws += int(bool(warning))
            error_draws += int(bool(error))
        if error_draws:
            raise RuntimeError("non-empty-frame GRTS errors survived corrected-v2 fail-closed adapter")
        scored_grts["heldout_recovery_10km"] = grts_recoveries
        scored_grts["outcomes_attached_after_selection"] = True
        scored_grts.to_csv(fold_dir / "grts_draws_scored.csv", index=False)
        heldout.to_csv(fold_dir / "held_out_occurrences.csv", index=False)

        fold_row = {
            "pair_id": int(pair.pair_id),
            "repeat": repeat,
            "taxon_group": str(pair.taxon_group),
            "scientific_name": str(pair.scientific_name),
            "region_name": str(pair.region_name),
            "fold_status": "complete",
            "scientific_zero_reason": "",
            "candidate_pool": int(len(candidates)),
            "heldout_records": int(len(all_ids)),
            "router_recovery_10km": router_recovery,
            "frozen_v1_recovery_10km": v1_recovery,
            "rescue_v2_recovery_10km": rescue_recovery,
            "grts_mean_recovery_10km": float(np.mean(grts_recoveries)),
            "local_only_recovery_10km": local_recovery,
            "geographic_recovery_10km": geographic_recovery,
            "random_mean_recovery_10km": float(np.mean(random_recoveries)),
            "router_predicted_rescue_minus_v1": router_prediction,
            "router_chosen_policy": chosen_policy,
            "grts_valid_base_draws": valid_draws,
            "grts_warning_draws": warning_draws,
            "grts_error_draws": error_draws,
            "outcomes_available_to_router": False,
            "outcomes_available_to_v1_selector": False,
            "outcomes_available_to_rescue_selector": False,
            "outcomes_available_to_grts_selector": False,
            "outcomes_available_to_secondary_selectors": False,
            "candidate_pool_pre_outcome_sha256": _sha256(candidate_path),
            "rescue_v2_decision_pre_outcome_sha256": _sha256(rescue_path),
            "frozen_v1_decision_pre_outcome_sha256": _sha256(v1_path),
            "router_decision_pre_outcome_sha256": _sha256(router_path),
            "secondary_decisions_pre_outcome_sha256": _sha256(secondary_path),
            "grts_draws_pre_outcome_sha256": _sha256(grts_path),
        }
        (fold_dir / "fold_summary.json").write_text(
            json.dumps(fold_row, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        fold_rows.append(fold_row)

    folds = pd.DataFrame(fold_rows)
    if len(folds) != repeats:
        raise RuntimeError(f"vNext2 pair wrote {len(folds)} folds, expected {repeats}")
    return _write_pair_summary(
        root, pair, protocol_fp, rescue_model_hash, router_hash,
        router_model_fingerprint, folds, "complete"
    )


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-id", type=int, required=True)
    command.add_argument("--cohort", type=Path, required=True)
    command.add_argument("--rescue-model", type=Path, required=True)
    command.add_argument("--rescue-model-manifest", type=Path, required=True)
    command.add_argument("--router-model", type=Path, required=True)
    command.add_argument("--router-model-manifest", type=Path, required=True)
    command.add_argument("--protocol", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
