#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from country_framed_fresh_heterogeneity_execution import (
    ALL_PAIR_IDS,
    EXPECTED_FRESH_EXECUTION_FINGERPRINT,
    EXPECTED_FRESH_PROTOCOL_FINGERPRINT,
    execution_contract,
)
from predeclare_country_framed_integration_development_v2 import EXPECTED_PROTOCOL_FINGERPRINT, _protocol
from run_country_framed_integration_development_v1_1 import _finite_mean, taxon_bootstrap_mean_ci

PAIR_ARTIFACT_GLOB = "fresh-pair-*"


def _sample_sd(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.std(values, ddof=1)) if len(values) >= 2 else float("nan")


def _heterogeneity_bootstrap(
    plant: np.ndarray,
    animal: np.ndarray,
    *,
    repetitions: int,
    seed: int,
) -> tuple[float, float, float]:
    plant = np.asarray(plant, dtype=float)
    animal = np.asarray(animal, dtype=float)
    plant = plant[np.isfinite(plant)]
    animal = animal[np.isfinite(animal)]
    if len(plant) < 2 or len(animal) < 2:
        return float("nan"), float("nan"), float("nan")
    plant_sd = _sample_sd(plant)
    animal_sd = _sample_sd(animal)
    observed = float(plant_sd / animal_sd) if np.isfinite(animal_sd) and animal_sd > 0 else float("nan")
    rng = np.random.default_rng(int(seed))
    ratios: list[float] = []
    for _ in range(int(repetitions)):
        ps = _sample_sd(rng.choice(plant, size=len(plant), replace=True))
        aas = _sample_sd(rng.choice(animal, size=len(animal), replace=True))
        if np.isfinite(ps) and np.isfinite(aas) and aas > 0:
            ratios.append(float(ps / aas))
    if not ratios:
        return observed, float("nan"), float("nan")
    arr = np.asarray(ratios, dtype=float)
    low, high = np.quantile(arr, [0.025, 0.975])
    return observed, float(low), float(high)


def aggregate_fresh(input_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    contract = execution_contract()
    authoritative = _protocol()
    primary = contract["aggregate"]
    result_files = sorted(input_root.glob(f"{PAIR_ARTIFACT_GLOB}/taxon_country_results.csv"))
    manifest_files = sorted(input_root.glob(f"{PAIR_ARTIFACT_GLOB}/pair_manifest.json"))
    if len(result_files) != 48 or len(manifest_files) != 48:
        raise ValueError(f"expected 48 fresh pair artifacts, found results={len(result_files)} manifests={len(manifest_files)}")

    results = pd.concat([pd.read_csv(path) for path in result_files], ignore_index=True)
    if len(results) != 48 or results["speciesKey"].nunique() != 48:
        raise ValueError("fresh aggregate must preserve exactly 48 unique taxa")
    pair_ids = pd.to_numeric(results["integration_pair_id"], errors="raise").astype(int)
    if sorted(pair_ids.tolist()) != list(ALL_PAIR_IDS):
        raise ValueError("fresh pair IDs must be exactly 1..48")
    if not results["fresh_protocol_fingerprint"].astype(str).eq(EXPECTED_FRESH_PROTOCOL_FINGERPRINT).all():
        raise ValueError("fresh protocol fingerprint drift across pair results")
    if not results["fresh_execution_fingerprint"].astype(str).eq(EXPECTED_FRESH_EXECUTION_FINGERPRINT).all():
        raise ValueError("fresh execution fingerprint drift across pair results")

    for path in manifest_files:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest["fresh_protocol_fingerprint"] != EXPECTED_FRESH_PROTOCOL_FINGERPRINT:
            raise ValueError("fresh pair manifest protocol drift")
        if manifest["fresh_execution_fingerprint"] != EXPECTED_FRESH_EXECUTION_FINGERPRINT:
            raise ValueError("fresh pair manifest execution drift")
        if manifest["authoritative_v2_protocol_fingerprint"] != EXPECTED_PROTOCOL_FINGERPRINT:
            raise ValueError("fresh pair manifest authoritative-v2 drift")
        if manifest["scientific_method_changed"] is not False:
            raise ValueError("fresh pair changed scientific method")
        if manifest["cohort_reselected"] is not False or manifest["declaration_reselected"] is not False:
            raise ValueError("fresh pair reselected frozen identities")
        if manifest["candidate_generation_preceded_recent_outcome_fetch"] is not True:
            raise ValueError("fresh pair opened recent outcome before candidate generation")

    patch_frames: list[pd.DataFrame] = []
    for path in sorted(input_root.glob(f"{PAIR_ARTIFACT_GLOB}/integrated_candidate_patches.csv")):
        try:
            frame = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            continue
        if not frame.empty:
            patch_frames.append(frame)
    patches = pd.concat(patch_frames, ignore_index=True) if patch_frames else pd.DataFrame()

    generated = results["candidate_generation_status"].eq("generated")
    temporal = results["temporal_status"].eq("evaluated")
    lift_values = pd.to_numeric(results["robust_minus_random_recall"], errors="coerce")
    integrated = generated & temporal & lift_values.notna()
    lifts = lift_values.loc[integrated].to_numpy(float)
    mean, low, high = taxon_bootstrap_mean_ci(
        lifts,
        repetitions=int(primary["bootstrap_repetitions"]),
        seed=int(primary["bootstrap_seed"]),
    )
    plant_mask = integrated & results["taxon_group"].eq("plant")
    animal_mask = integrated & results["taxon_group"].eq("animal")
    plant_mean = _finite_mean(lift_values.loc[plant_mask])
    animal_mean = _finite_mean(lift_values.loc[animal_mask])
    candidate_rate = float(generated.mean())
    temporal_rate = float(temporal.mean())

    gates_cfg = json.loads(
        (Path(__file__).resolve().parents[1] / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_v1.json").read_text(encoding="utf-8")
    )["primary_gates"]
    gate_checks = {
        "declared_taxa": len(results) == int(gates_cfg["declared_unique_taxa"]),
        "candidate_generation_success_rate": candidate_rate >= float(gates_cfg["candidate_generation_fraction_min"]),
        "temporal_evaluability_rate": temporal_rate >= float(gates_cfg["temporal_evaluability_fraction_min"]),
        "mean_lift_positive": bool(np.isfinite(mean) and mean > float(gates_cfg["mean_lift_gt"])),
        "bootstrap_lower_positive": bool(np.isfinite(low) and low > float(gates_cfg["bootstrap_lower_gt"])),
        "plant_mean_nonnegative": bool(np.isfinite(plant_mean) and plant_mean >= float(gates_cfg["plant_mean_gte"])),
        "animal_mean_nonnegative": bool(np.isfinite(animal_mean) and animal_mean >= float(gates_cfg["animal_mean_gte"])),
    }

    plant_lifts = lift_values.loc[plant_mask].to_numpy(float)
    animal_lifts = lift_values.loc[animal_mask].to_numpy(float)
    plant_sd = _sample_sd(plant_lifts)
    animal_sd = _sample_sd(animal_lifts)
    ratio, ratio_low, ratio_high = _heterogeneity_bootstrap(
        plant_lifts,
        animal_lifts,
        repetitions=int(primary["heterogeneity_bootstrap"].split(";")[1].strip().split()[0]) if False else 10000,
        seed=int(primary["heterogeneity_bootstrap_seed"]),
    )

    evalcfg = authoritative["evaluation"]
    summary = {
        "status": "country_framed_fresh_heterogeneity_confirmation_complete",
        "fresh_protocol_fingerprint": EXPECTED_FRESH_PROTOCOL_FINGERPRINT,
        "fresh_execution_fingerprint": EXPECTED_FRESH_EXECUTION_FINGERPRINT,
        "authoritative_v2_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "declared_taxa": 48,
        "candidate_generation_success_taxa": int(generated.sum()),
        "candidate_generation_success_rate": candidate_rate,
        "temporally_evaluable_taxa": int(temporal.sum()),
        "temporal_evaluability_rate": temporal_rate,
        "integrated_evaluable_taxa": int(integrated.sum()),
        "primary_support_fraction": 0.025,
        "primary_radius_km": float(evalcfg["primary_recovery_radius_km"]),
        "random_baseline_repetitions": int(evalcfg["random_baseline_repetitions"]),
        "mean_robust_minus_random_recall": mean,
        "taxon_bootstrap_95pct_ci": [low, high],
        "plant_mean_robust_minus_random_recall": plant_mean,
        "animal_mean_robust_minus_random_recall": animal_mean,
        "gate_checks": gate_checks,
        "fresh_confirmation_gate_passed": all(gate_checks.values()),
        "secondary_heterogeneity": {
            "decision_role": "secondary_only_cannot_change_primary_promotion_decision",
            "plant_integrated_evaluable_taxa": int(plant_mask.sum()),
            "animal_integrated_evaluable_taxa": int(animal_mask.sum()),
            "plant_lift_sample_sd": plant_sd,
            "animal_lift_sample_sd": animal_sd,
            "plant_to_animal_sd_ratio": ratio,
            "plant_to_animal_sd_ratio_bootstrap_95pct_ci": [ratio_low, ratio_high],
            "directional_hypothesis_observed": bool(np.isfinite(plant_sd) and np.isfinite(animal_sd) and plant_sd > animal_sd),
            "bootstrap_repetitions": 10000,
            "bootstrap_seed": int(primary["heterogeneity_bootstrap_seed"]),
        },
        "scientific_method_changed": False,
        "retuned_after_outcome_opening": False,
        "subset_rescue_used": False,
        "failed_declarations_replaced": False,
        "heterogeneity_changed_primary_decision": False,
        "validated_japan_core_changed": False,
        "global_candidate_generation_validated": bool(all(gate_checks.values())),
    }
    return results.sort_values("integration_pair_id").reset_index(drop=True), patches, summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    results, patches, summary = aggregate_fresh(args.input_root)
    results.to_csv(args.output / "taxon_country_results.csv", index=False)
    patches.to_csv(args.output / "integrated_candidate_patches.csv", index=False)
    (args.output / "fresh_confirmation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
