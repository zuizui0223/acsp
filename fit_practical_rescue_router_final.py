#!/usr/bin/env python3
"""Fit the final transparent vNext2 router after its complete development gate passes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.practical_rescue_router import (
    ROUTER_CATEGORICAL_FEATURES,
    ROUTER_NUMERIC_FEATURES,
    ROUTER_PROTOCOL_FINGERPRINT,
    SafeRescueRouterPolicy,
    export_linear_router_artifact,
    make_router_estimator,
    predict_linear_router_artifact,
    router_training_weights,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not stored or stored != calculated or stored != ROUTER_PROTOCOL_FINGERPRINT:
        raise ValueError("final router fit received an unexpected protocol")
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _audit_training_rows_against_all_folds(
    frame: pd.DataFrame,
    folds: pd.DataFrame,
) -> tuple[int, list[int]]:
    """Prove that training rows are exactly the scientifically complete folds.

    Pairs whose five folds are all explicit scientific zeroes legitimately have
    no router-training row because neither frozen policy can differ there. They
    remain in the 192-pair development estimand and must be identifiable from
    the complete fold audit rather than silently disappearing.
    """
    required_fold = {"pair_id", "repeat", "fold_status"}
    missing_fold = required_fold - set(folds.columns)
    if missing_fold:
        raise ValueError(f"router fold audit lacks: {sorted(missing_fold)}")
    if len(folds) != 960:
        raise ValueError(f"router fold audit has {len(folds)} rows, expected 960")
    fold_pair = pd.to_numeric(folds["pair_id"], errors="raise").astype(int)
    fold_repeat = pd.to_numeric(folds["repeat"], errors="raise").astype(int)
    if sorted(fold_pair.unique().tolist()) != list(range(1, 193)):
        raise ValueError("router fold audit does not contain pair IDs 1..192")
    if not fold_repeat.between(1, 5).all():
        raise ValueError("router fold audit repeat values are outside 1..5")
    fold_keys = pd.DataFrame({"pair_id": fold_pair, "repeat": fold_repeat})
    if fold_keys.duplicated().any():
        raise ValueError("router fold audit contains duplicate pair/repeat rows")
    statuses = folds["fold_status"].astype(str)
    allowed = {"complete", "explicit_scientific_zero"}
    unexpected = sorted(set(statuses) - allowed)
    if unexpected:
        raise ValueError(f"router fold audit contains unexpected statuses: {unexpected}")
    complete_mask = statuses.eq("complete")
    if int(complete_mask.sum()) != 873 or int((~complete_mask).sum()) != 87:
        raise ValueError("router fold audit no longer has frozen 873 complete / 87 zero folds")

    required_train = {"pair_id", "repeat"}
    missing_train = required_train - set(frame.columns)
    if missing_train:
        raise ValueError(f"router training table lacks: {sorted(missing_train)}")
    train_pair = pd.to_numeric(frame["pair_id"], errors="raise").astype(int)
    train_repeat = pd.to_numeric(frame["repeat"], errors="raise").astype(int)
    if len(frame) != 873:
        raise ValueError(f"router training table has {len(frame)} rows, expected 873")
    if not train_pair.between(1, 192).all() or not train_repeat.between(1, 5).all():
        raise ValueError("router training table contains out-of-contract pair/repeat IDs")
    train_keys = pd.DataFrame({"pair_id": train_pair, "repeat": train_repeat})
    if train_keys.duplicated().any():
        raise ValueError("router training table contains duplicate pair/repeat rows")

    complete_keys = set(
        zip(
            fold_pair.loc[complete_mask].tolist(),
            fold_repeat.loc[complete_mask].tolist(),
        )
    )
    actual_keys = set(zip(train_pair.tolist(), train_repeat.tolist()))
    if actual_keys != complete_keys:
        missing = sorted(complete_keys - actual_keys)[:10]
        extra = sorted(actual_keys - complete_keys)[:10]
        raise ValueError(
            "router training rows are not exactly the complete scientific folds: "
            f"missing={missing}, extra={extra}"
        )

    complete_counts = (
        pd.DataFrame({"pair_id": fold_pair, "complete": complete_mask.astype(int)})
        .groupby("pair_id", sort=True)["complete"]
        .sum()
    )
    all_zero_pairs = complete_counts.index[complete_counts.eq(0)].astype(int).tolist()
    training_pairs = int(train_pair.nunique())
    if training_pairs + len(all_zero_pairs) != 192:
        raise ValueError("complete-fold contributors plus all-zero pairs do not reconstruct 192 pairs")
    if set(train_pair.unique().tolist()) & set(all_zero_pairs):
        raise ValueError("an all-zero pair unexpectedly appears in router training rows")
    return training_pairs, all_zero_pairs


def run(
    development_manifest: Path,
    training_rows: Path,
    fold_level: Path,
    protocol_path: Path,
    output: Path,
) -> dict[str, object]:
    protocol, fingerprint = _canonical_protocol(protocol_path)
    development = json.loads(development_manifest.read_text(encoding="utf-8"))
    if str(development.get("protocol_fingerprint")) != fingerprint:
        raise ValueError("router development manifest protocol mismatch")
    if development.get("development_gate_passed") is not True:
        raise ValueError("router final fit is blocked until the complete development gate passes")
    if development.get("primary_gate_passed") is not True:
        raise ValueError("router final fit is blocked by the overall development gate")
    if development.get("taxon_group_guardrail_passed") is not True:
        raise ValueError("router final fit is blocked by the plant/animal guardrail")
    if int(development.get("declared_pairs", 0)) != 192 or int(development.get("evaluated_pairs", 0)) != 192:
        raise ValueError("router final fit requires the complete 192-pair development set")
    if int(development.get("evaluated_folds", 0)) != 960:
        raise ValueError("router final fit requires the complete 960-fold development audit")
    if int(development.get("complete_training_rows", 0)) != 873:
        raise ValueError("router final fit requires exactly 873 complete fold rows")
    if int(development.get("scientific_zero_folds", 0)) != 87:
        raise ValueError("router final fit requires exactly 87 explicit scientific-zero folds")
    if development.get("candidate_frames_regenerated") is not False:
        raise ValueError("router development regenerated candidate frames")
    if development.get("outcomes_available_to_router_at_test_inference") is not False:
        raise ValueError("router development reports test-outcome access")

    frame = pd.read_csv(training_rows)
    folds = pd.read_csv(fold_level)
    training_pairs, all_zero_pairs = _audit_training_rows_against_all_folds(frame, folds)
    columns = [*ROUTER_NUMERIC_FEATURES, *ROUTER_CATEGORICAL_FEATURES]
    missing = set(columns + ["target_rescue_minus_v1", "pair_id"]) - set(frame.columns)
    if missing:
        raise ValueError(f"router final training table lacks: {sorted(missing)}")

    policy = SafeRescueRouterPolicy()
    estimator = make_router_estimator(policy)
    weights = router_training_weights(frame["pair_id"])
    target = pd.to_numeric(frame["target_rescue_minus_v1"], errors="raise").to_numpy(float)
    estimator.fit(frame[columns], target, model__sample_weight=weights)
    predictions = estimator.predict(frame[columns])
    artifact = export_linear_router_artifact(
        estimator,
        training_rows=len(frame),
        development_pairs=192,
        source_fingerprint=fingerprint,
        policy=policy,
    )
    artifact.update({
        "development_manifest_sha256": _sha256(development_manifest),
        "training_rows_sha256": _sha256(training_rows),
        "fold_level_sha256": _sha256(fold_level),
        "development_pairs_with_complete_folds": training_pairs,
        "development_all_zero_pairs": all_zero_pairs,
        "development_all_zero_pair_count": len(all_zero_pairs),
        "fit_target": "development-only fold Rescue-v2 minus frozen-v1 10-km recovery",
        "development_outcomes_used_for_final_router_fit": True,
        "confirmation_outcomes_used_for_router_fit": False,
        "router_hyperparameters_changed_after_development_gate": False,
        "new_untouched_confirmation_required": True,
    })
    reproduced = predict_linear_router_artifact(frame[columns], artifact)
    if not np.allclose(reproduced, predictions, atol=1e-12, rtol=1e-12):
        raise RuntimeError("exported transparent router artifact does not reproduce sklearn predictions")
    artifact_without_fp = dict(artifact)
    model_fingerprint = hashlib.sha256(
        json.dumps(artifact_without_fp, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    artifact["model_fingerprint"] = model_fingerprint

    output.mkdir(parents=True, exist_ok=True)
    model_path = output / "practical_rescue_vnext2_router.json"
    model_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {
        "status": "final_vnext2_router_fitted_after_complete_development_gate",
        "protocol_fingerprint": fingerprint,
        "model_fingerprint": model_fingerprint,
        "model_sha256": _sha256(model_path),
        "development_pairs": 192,
        "development_pairs_with_complete_folds": training_pairs,
        "development_all_zero_pair_count": len(all_zero_pairs),
        "development_all_zero_pairs": all_zero_pairs,
        "development_complete_folds": 873,
        "development_scientific_zero_folds": 87,
        "training_rows": len(frame),
        "decision_threshold_absolute_recall": policy.decision_threshold_absolute_recall,
        "ridge_alpha": policy.alpha,
        "development_outcomes_used_for_fit": True,
        "confirmation_outcomes_used_for_fit": False,
        "hyperparameters_changed_after_development_gate": False,
        "new_untouched_confirmation_required": True,
    }
    (output / "model_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--development-manifest", type=Path, required=True)
    command.add_argument("--training-rows", type=Path, required=True)
    command.add_argument("--fold-level", type=Path, required=True)
    command.add_argument("--protocol", dest="protocol_path", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
