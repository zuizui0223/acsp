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


def run(
    development_manifest: Path,
    training_rows: Path,
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
    if int(development.get("complete_training_rows", 0)) != 873:
        raise ValueError("router final fit requires exactly 873 complete fold rows")
    if development.get("candidate_frames_regenerated") is not False:
        raise ValueError("router development regenerated candidate frames")
    if development.get("outcomes_available_to_router_at_test_inference") is not False:
        raise ValueError("router development reports test-outcome access")

    frame = pd.read_csv(training_rows)
    if len(frame) != 873 or frame["pair_id"].astype(int).nunique() != 192:
        raise ValueError("router training table is not the frozen 873-row/192-pair development table")
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
        "development_complete_folds": 873,
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
    command.add_argument("--protocol", dest="protocol_path", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
