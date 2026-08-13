#!/usr/bin/env python3
"""Strictly aggregate the untouched vNext2 router confirmation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


EXPECTED_PAIRS = 192
EXPECTED_GROUP_PAIRS = 96


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


def _inference(values: np.ndarray, draws: int, seed: int) -> dict[str, object]:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("vNext2 pair differences must be a finite non-empty vector")
    rng = np.random.default_rng(int(seed))
    bootstrap = rng.choice(values, size=(int(draws), len(values)), replace=True).mean(axis=1)
    null = (
        rng.choice(np.array([-1.0, 1.0]), size=(int(draws), len(values))) * values
    ).mean(axis=1)
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


def _passes(result: dict[str, object], threshold: float) -> bool:
    return bool(
        float(result["mean_difference"]) >= float(threshold)
        and float(result["bootstrap_95ci_low"]) > 0
        and float(result["sign_flip_p"]) < 0.05
    )


def run(
    cohort: Path,
    pair_root: Path,
    protocol_path: Path,
    output: Path,
) -> dict[str, object]:
    protocol, fingerprint = _canonical_protocol(protocol_path)
    declared = pd.read_csv(cohort)
    if len(declared) != EXPECTED_PAIRS:
        raise ValueError(f"vNext2 cohort has {len(declared)} rows, expected {EXPECTED_PAIRS}")
    declared_ids = pd.to_numeric(declared["pair_id"], errors="raise").astype(int).tolist()
    if sorted(declared_ids) != list(range(1, EXPECTED_PAIRS + 1)):
        raise ValueError("vNext2 cohort pair IDs are not exactly 1..192")
    if declared["scientific_name"].astype(str).nunique() != EXPECTED_PAIRS:
        raise ValueError("vNext2 cohort contains repeated taxa")
    declared_group_counts = declared["taxon_group"].astype(str).value_counts().to_dict()
    if declared_group_counts != {"plant": EXPECTED_GROUP_PAIRS, "animal": EXPECTED_GROUP_PAIRS}:
        raise ValueError(f"vNext2 cohort is not plant96/animal96: {declared_group_counts}")

    infrastructure_failures = list(pair_root.rglob("infrastructure_failure.json"))
    if infrastructure_failures:
        raise RuntimeError(
            "vNext2 confirmation invalid: infrastructure failures are present and may not become zero; "
            f"count={len(infrastructure_failures)}"
        )
    summary_paths = list(pair_root.rglob("pair_summary.json"))
    if len(summary_paths) != EXPECTED_PAIRS:
        raise RuntimeError(
            "vNext2 confirmation invalid: expected 192 verified pair summaries, "
            f"found {len(summary_paths)}"
        )
    summaries = [json.loads(path.read_text(encoding="utf-8")) for path in summary_paths]
    pair = pd.DataFrame(summaries).sort_values("pair_id", kind="mergesort").reset_index(drop=True)
    if pair["pair_id"].astype(int).tolist() != list(range(1, EXPECTED_PAIRS + 1)):
        raise RuntimeError("vNext2 pair summaries are incomplete or duplicated")
    if pair["verified_scientific_artifact"].astype(bool).ne(True).any():
        raise RuntimeError("vNext2 pair summaries include an unverified scientific artifact")
    if pair["protocol_fingerprint"].astype(str).nunique() != 1 or str(pair["protocol_fingerprint"].iloc[0]) != fingerprint:
        raise RuntimeError("vNext2 pair artifacts disagree on frozen protocol fingerprint")

    expected_rescue_hash = str(protocol["final_rescue_v2"]["model_sha256"])
    expected_router_hash = str(protocol["final_router"]["model_sha256"])
    expected_router_fp = str(protocol["final_router"]["model_fingerprint"])
    if set(pair["rescue_v2_model_sha256"].astype(str)) != {expected_rescue_hash}:
        raise RuntimeError("vNext2 pair artifacts disagree on frozen Rescue-v2 model")
    if set(pair["router_model_sha256"].astype(str)) != {expected_router_hash}:
        raise RuntimeError("vNext2 pair artifacts disagree on frozen router bytes")
    if set(pair["router_model_fingerprint"].astype(str)) != {expected_router_fp}:
        raise RuntimeError("vNext2 pair artifacts disagree on frozen router model fingerprint")

    for column in (
        "outcomes_available_to_router",
        "outcomes_available_to_v1_selector",
        "outcomes_available_to_rescue_selector",
        "outcomes_available_to_grts_selector",
        "outcomes_available_to_secondary_selectors",
    ):
        if pair[column].astype(bool).any():
            raise RuntimeError(f"vNext2 confirmation invalid: {column} reports held-out outcome access")
    if pd.to_numeric(pair["grts_error_draws"], errors="raise").sum() != 0:
        raise RuntimeError("vNext2 confirmation invalid: non-empty-frame GRTS errors survived pair-level fail-closed checks")

    numeric_columns = [
        "router_mean_recovery_10km",
        "frozen_v1_mean_recovery_10km",
        "rescue_v2_mean_recovery_10km",
        "grts_mean_recovery_10km",
        "local_only_mean_recovery_10km",
        "geographic_mean_recovery_10km",
        "random_mean_recovery_10km",
    ]
    for column in numeric_columns:
        pair[column] = pd.to_numeric(pair[column], errors="raise")
        if not np.isfinite(pair[column].to_numpy(float)).all():
            raise RuntimeError(f"vNext2 confirmation contains non-finite {column}")

    pair["router_minus_corrected_grts_v2"] = (
        pair["router_mean_recovery_10km"] - pair["grts_mean_recovery_10km"]
    )
    pair["router_minus_frozen_v1"] = (
        pair["router_mean_recovery_10km"] - pair["frozen_v1_mean_recovery_10km"]
    )
    pair["router_minus_local_only"] = (
        pair["router_mean_recovery_10km"] - pair["local_only_mean_recovery_10km"]
    )
    pair["router_minus_geographic"] = (
        pair["router_mean_recovery_10km"] - pair["geographic_mean_recovery_10km"]
    )
    pair["router_minus_random"] = (
        pair["router_mean_recovery_10km"] - pair["random_mean_recovery_10km"]
    )

    inference_cfg = protocol["inference"]
    draws = int(inference_cfg["bootstrap_draws"])
    seed = int(inference_cfg["seed"])
    threshold = float(inference_cfg["minimum_absolute_recall_gain"])
    primary_columns = {
        "router_minus_corrected_grts_v2": "router_minus_corrected_grts_v2",
        "router_minus_frozen_v1": "router_minus_frozen_v1",
    }
    overall: dict[str, object] = {}
    groups: dict[str, dict[str, object]] = {"plant": {}, "animal": {}}
    gates: dict[str, object] = {}
    for offset, (name, column) in enumerate(primary_columns.items()):
        overall_result = _inference(pair[column].to_numpy(float), draws, seed + offset * 100)
        overall[name] = overall_result
        gates[f"overall_{name}"] = _passes(overall_result, threshold)
        for group_offset, group in enumerate(("plant", "animal"), start=1):
            subset = pair.loc[pair["taxon_group"].astype(str).eq(group)]
            if len(subset) != EXPECTED_GROUP_PAIRS:
                raise RuntimeError(f"vNext2 confirmation does not contain {group}96")
            result = _inference(
                subset[column].to_numpy(float),
                draws,
                seed + offset * 100 + group_offset,
            )
            groups[group][name] = result
            gates[f"{group}_{name}"] = _passes(result, threshold)

    secondary = {
        "router_minus_local_only": _inference(
            pair["router_minus_local_only"].to_numpy(float), draws, seed + 501
        ),
        "router_minus_geographic": _inference(
            pair["router_minus_geographic"].to_numpy(float), draws, seed + 502
        ),
        "router_minus_random": _inference(
            pair["router_minus_random"].to_numpy(float), draws, seed + 503
        ),
    }
    strict_gate = bool(all(bool(value) for value in gates.values()))

    output.mkdir(parents=True, exist_ok=True)
    pair.to_csv(output / "pair_level_comparison.csv", index=False)
    result = {
        "status": "vnext2_untouched_confirmation_evaluated",
        "protocol_fingerprint": fingerprint,
        "declared_pairs": EXPECTED_PAIRS,
        "verified_pair_artifacts": int(len(pair)),
        "taxon_group_counts": {str(k): int(v) for k, v in pair["taxon_group"].astype(str).value_counts().items()},
        "missing_pair_artifacts_scored_as_zero": False,
        "minimum_absolute_recall_gain": threshold,
        "primary_overall_inference": overall,
        "primary_taxon_group_inference": groups,
        "primary_gate_components": gates,
        "secondary_inference": secondary,
        "router_rescue_selected_folds": int(pd.to_numeric(pair["router_rescue_selected_folds"], errors="raise").sum()),
        "router_v1_selected_folds": int(pd.to_numeric(pair["router_v1_selected_folds"], errors="raise").sum()),
        "grts_error_draws": int(pd.to_numeric(pair["grts_error_draws"], errors="raise").sum()),
        "retrospective_ecological_promotion_passed": strict_gate,
        "production_field_efficiency_promotion_passed": False,
        "production_field_efficiency_blocker": "prospective attempted-site/non-detection/effort/access-failure evidence remains required",
        "broad_existing_tool_superiority_passed": False,
        "broad_existing_tool_superiority_blocker": "native biosurvey end-to-end comparison remains required",
        "outcomes_available_to_router": False,
        "outcomes_available_to_v1_selector": False,
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
    command.add_argument("--protocol", dest="protocol_path", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
