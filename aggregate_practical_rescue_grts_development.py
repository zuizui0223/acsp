#!/usr/bin/env python3
"""Aggregate the frozen 72-pair rescue versus official GRTS development gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_PROTOCOL = "47afc2acf0807998ca13b04cce72e71cea2baffff7df7b33fb9b66a82559885b"
INFERENCE_SEED = 20260812


def _protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if stored != calculated or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"GRTS development protocol mismatch: stored={stored}, calculated={calculated}"
        )
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _expected_groups() -> set[str]:
    return {
        f"{prefix}_{index}"
        for prefix in ("mixed", "plants", "sdm")
        for index in range(1, 25)
    }


def _inference(difference: np.ndarray, draws: int) -> dict[str, object]:
    difference = np.asarray(difference, dtype=float)
    rng = np.random.default_rng(INFERENCE_SEED)
    bootstrap = rng.choice(
        difference, size=(int(draws), len(difference)), replace=True
    ).mean(axis=1)
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
        "sign_flip_p": float(
            (1 + np.sum(np.abs(null) >= observed)) / (int(draws) + 1)
        ),
        "positive_pairs": int(np.sum(difference > 1e-12)),
        "negative_pairs": int(np.sum(difference < -1e-12)),
        "tied_pairs": int(np.sum(np.abs(difference) <= 1e-12)),
        "difference_sd": float(np.std(difference, ddof=1)),
    }


def run(pair_root: Path, protocol_path: Path, output: Path) -> dict[str, object]:
    protocol, fingerprint = _protocol(protocol_path)
    summaries = []
    fold_tables = []
    for summary_path in pair_root.rglob("pair_summary.json"):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summaries.append(summary)
        fold_path = summary_path.parent / "fold_comparison.csv"
        if not fold_path.exists():
            raise FileNotFoundError(f"missing fold comparison for {summary['group_id']}")
        fold_tables.append(pd.read_csv(fold_path))
    if len(summaries) != 72:
        raise ValueError(f"expected 72 pair summaries, found {len(summaries)}")

    pair = pd.DataFrame(summaries).sort_values("global_pair_id").reset_index(drop=True)
    if set(pair["group_id"].astype(str)) != _expected_groups():
        missing = sorted(_expected_groups() - set(pair["group_id"].astype(str)))
        extra = sorted(set(pair["group_id"].astype(str)) - _expected_groups())
        raise ValueError(f"pair group mismatch: missing={missing}, extra={extra}")
    if pair["global_pair_id"].astype(int).tolist() != list(range(1, 73)):
        raise ValueError("global pair IDs are not exactly 1..72")
    if pair["protocol_fingerprint"].astype(str).nunique() != 1 or str(pair["protocol_fingerprint"].iloc[0]) != fingerprint:
        raise ValueError("pair artifacts disagree on GRTS protocol fingerprint")
    if not pair["all_grts_draws_frozen_before_heldout_loading"].astype(bool).all():
        raise ValueError("a pair did not freeze all GRTS draws before heldout loading")
    if pair["outcomes_available_to_grts_selector"].astype(bool).any():
        raise ValueError("GRTS selector had outcome access")

    folds = pd.concat(fold_tables, ignore_index=True)
    if len(folds) != 72 * 5:
        raise ValueError(f"expected 360 fold rows, found {len(folds)}")
    pair["rescue_minus_grts"] = (
        pd.to_numeric(pair["rescue_mean_recovery_10km"], errors="raise")
        - pd.to_numeric(pair["grts_mean_recovery_10km"], errors="raise")
    )
    pair["rescue_minus_local"] = (
        pd.to_numeric(pair["rescue_mean_recovery_10km"], errors="raise")
        - pd.to_numeric(pair["local_mean_recovery_10km"], errors="raise")
    )

    expected_rescue_local = float(
        protocol["rescue_72_development_result"]["combined_72_mean_gain_vs_local"]
    )
    observed_rescue_local = float(pair["rescue_minus_local"].mean())
    if not np.isclose(observed_rescue_local, expected_rescue_local, atol=1e-10, rtol=0):
        raise ValueError(
            "72-pair rescue/local snapshot changed before GRTS inference: "
            f"observed={observed_rescue_local}, expected={expected_rescue_local}"
        )

    inference_cfg = protocol["inference"]
    primary = _inference(
        pair["rescue_minus_grts"].to_numpy(float),
        int(inference_cfg["bootstrap_draws"]),
    )
    threshold = float(inference_cfg["minimum_absolute_recall_gain"])
    passed = bool(
        len(pair) == 72
        and primary["mean_difference"] >= threshold
        and primary["bootstrap_95ci_low"] > 0
        and primary["sign_flip_p"] < 0.05
    )

    source_results = {}
    for source, subset in pair.groupby("source"):
        source_results[str(source)] = _inference(
            subset["rescue_minus_grts"].to_numpy(float),
            int(inference_cfg["bootstrap_draws"]),
        )

    output.mkdir(parents=True, exist_ok=True)
    pair.to_csv(output / "pair_level_comparison.csv", index=False)
    folds.to_csv(output / "fold_level_comparison.csv", index=False)
    result = {
        "status": "official_grts_72_pair_development_gate_evaluated",
        "protocol_fingerprint": fingerprint,
        "rescue_protocol_fingerprint": protocol["rescue_policy"]["protocol_fingerprint"],
        "declared_pairs": 72,
        "complete_pairs": int(len(pair)),
        "folds": int(len(folds)),
        "inference_seed": INFERENCE_SEED,
        "primary_contrast": str(inference_cfg["primary_contrast"]),
        "primary_inference": primary,
        "source_inference": source_results,
        "minimum_absolute_recall_gain": threshold,
        "development_grts_gate_passed": passed,
        "rescue_minus_local_snapshot": observed_rescue_local,
        "grts_warning_draws": int(pd.to_numeric(folds["grts_warning_draws"], errors="coerce").fillna(0).sum()),
        "grts_error_draws": int(pd.to_numeric(folds["grts_error_draws"], errors="coerce").fillna(0).sum()),
        "grts_valid_base_draws": int(pd.to_numeric(folds["grts_valid_base_draws"], errors="coerce").fillna(0).sum()),
        "total_grts_draws": int(72 * 5 * protocol["official_grts"]["draws_per_fold"]),
        "spsurvey_version": protocol["official_grts"]["spsurvey_version"],
        "spsurvey_tag_commit": protocol["official_grts"]["spsurvey_tag_commit"],
        "outcomes_available_to_grts_selector": False,
        "no_retuning_after_grts_outcome": True,
        "fresh_confirmation_required_for_promotion": True,
    }
    (output / "development_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-root", type=Path, required=True)
    command.add_argument(
        "--protocol",
        type=Path,
        default=Path("validation/acsp_practical_rescue_grts_development_protocol.json"),
    )
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
