#!/usr/bin/env python3
"""Outcome-free proof that LOO support worlds can be execution-sharded exactly.

Preparatory only. This file does not fetch taxa, occurrences, surfaces, or outcomes.
It proves that computing the already-frozen leave-one-prototype-out support-rank
worlds in separate execution shards and reassembling them in the original removed-
prototype order returns the same consensus and uncertainty arrays as the frozen core.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.robust_patches import leave_one_out_consensus_support, robust_environment_geometry

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2_ru_robust_world_shard_prep_v1.json"
EXPECTED_FINGERPRINT = "6ed3cf68fe9eac282c78c901f9b1d4b70681cbaa2ba89db8dbfa3392013e2829"
FEATURES = ("elevation", "slope", "aspect_sin", "aspect_cos", "roughness", "tpi")


def load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("execution_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_FINGERPRINT or calculated != EXPECTED_FINGERPRINT:
        raise AssertionError("RU robust-world preparatory contract fingerprint mismatch")
    rule = payload["execution_rule"]
    required_false = (
        "scientific_method_changed", "cohort_changed", "declarations_changed", "country_changed",
        "country_geometry_changed", "complete_ru_surface_changed", "historical_training_scope_changed",
        "prototype_rule_changed", "leave_one_out_world_definition_changed", "support_world_dtype_changed",
        "consensus_reduction_changed", "uncertainty_reduction_changed", "support_threshold_changed",
        "patch_aggregation_changed", "random_baseline_changed", "heldout_outcome_opening_order_changed",
        "gates_changed", "outcome_driven_tuning_allowed",
    )
    for key in required_false:
        if rule[key] is not False:
            raise AssertionError(f"contract drift: {key}")
    if rule["world_partition_only"] is not True or int(rule["world_shard_count"]) != 8:
        raise AssertionError("world sharding contract drift")
    if rule["support_world_dtype"] != "float32" or int(rule["max_prototypes"]) != 32:
        raise AssertionError("frozen robust representation drift")
    payload["execution_fingerprint"] = stored
    return payload


def _complete(frame: pd.DataFrame) -> pd.DataFrame:
    values = frame.loc[:, FEATURES].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    return frame.loc[np.isfinite(values).all(axis=1)].copy().reset_index(drop=True)


def sharded_exact_consensus(universe: pd.DataFrame, prototypes: pd.DataFrame, *, shard_count: int = 8):
    complete = _complete(prototypes)
    if len(complete) < 2:
        raise ValueError("at least two complete prototypes are required")
    shards: dict[int, list[tuple[int, np.ndarray, float]]] = {i: [] for i in range(int(shard_count))}
    for removed in range(len(complete)):
        subset = complete.drop(index=complete.index[removed]).reset_index(drop=True)
        _, support_rank, _, kernel_scale = robust_environment_geometry(
            universe,
            subset,
            feature_columns=FEATURES,
        )
        world = np.asarray(support_rank).astype("float32", copy=False)
        shards[removed % int(shard_count)].append((removed, world, float(kernel_scale)))
    reassembled = sorted((item for values in shards.values() for item in values), key=lambda x: x[0])
    if [removed for removed, _, _ in reassembled] != list(range(len(complete))):
        raise AssertionError("removed-prototype world order was not exactly restored")
    stack = np.vstack([world for _, world, _ in reassembled])
    return np.median(stack, axis=0), np.std(stack, axis=0), np.asarray([k for _, _, k in reassembled])


def _synthetic_case(prototype_count: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    prototypes = pd.DataFrame(rng.normal(size=(prototype_count, len(FEATURES))), columns=FEATURES)
    universe = pd.DataFrame(rng.normal(size=(257, len(FEATURES))), columns=FEATURES)
    # Include valid-but-extreme rows so percentile ranking and float32 world casts are exercised.
    universe.loc[0, :] = 0.0
    universe.loc[1, :] = 25.0
    original_consensus, original_uncertainty, audit = leave_one_out_consensus_support(
        universe,
        prototypes,
        feature_columns=FEATURES,
        support_world_dtype="float32",
    )
    sharded_consensus, sharded_uncertainty, kernel_scales = sharded_exact_consensus(universe, prototypes)
    if not np.array_equal(original_consensus, sharded_consensus):
        raise AssertionError(f"consensus differs for prototype_count={prototype_count}")
    if not np.array_equal(original_uncertainty, sharded_uncertainty):
        raise AssertionError(f"uncertainty differs for prototype_count={prototype_count}")
    if audit.prototype_count != prototype_count or audit.leave_one_out_worlds != prototype_count:
        raise AssertionError("frozen audit world count drift")
    if audit.support_world_dtype != "float32":
        raise AssertionError("frozen support world dtype drift")
    if float(kernel_scales.min()) != float(audit.kernel_scale_min) or float(kernel_scales.max()) != float(audit.kernel_scale_max):
        raise AssertionError("kernel-scale audit differs after world reassembly")


def main() -> int:
    contract = load_contract()
    for i, n in enumerate((5, 7, 16, 32), start=1):
        _synthetic_case(n, 20260825 + i)
    print(json.dumps({
        "equivalence": "bitwise_passed",
        "prototype_counts_tested": [5, 7, 16, 32],
        "world_shard_count": 8,
        "support_world_dtype": "float32",
        "execution_fingerprint": contract["execution_fingerprint"],
        "scientific_method_changed": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
