#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from acsp.validated_robust import VALIDATED_ROBUST_PRIMARY_RADIUS_KM, VALIDATED_ROBUST_SUPPORT_FRACTION
from country_framed_integration_v2_replication_execution_contract import (
    EXPECTED_EXECUTION_FINGERPRINT,
    execution_contract,
)
from predeclare_country_framed_integration_development_v2 import EXPECTED_PROTOCOL_FINGERPRINT, _protocol
from predeclare_country_framed_integration_development_v2_replication import (
    EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
    replication_protocol,
)
from regional_country_lattice import LATTICE_STEP_DEG, POINTS_PER_REGIONAL_TILE
from run_country_framed_integration_development_v1_1 import _finite_mean, taxon_bootstrap_mean_ci

PAIR_ARTIFACT_GLOB = "replication-pair-*"


def aggregate_replication(input_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    authoritative = _protocol()
    replication = replication_protocol()
    execution_contract()
    gate = replication["replication_gate"]
    evalcfg = authoritative["evaluation"]

    result_files = sorted(input_root.glob(f"{PAIR_ARTIFACT_GLOB}/taxon_country_results.csv"))
    manifest_files = sorted(input_root.glob(f"{PAIR_ARTIFACT_GLOB}/pair_manifest.json"))
    if len(result_files) != 24 or len(manifest_files) != 24:
        raise ValueError(f"expected 24 replication pair artifacts, found results={len(result_files)} manifests={len(manifest_files)}")

    results = pd.concat([pd.read_csv(path) for path in result_files], ignore_index=True)
    if len(results) != 24:
        raise ValueError("aggregated replication must contain exactly 24 result rows")
    pair_ids = pd.to_numeric(results["integration_pair_id"], errors="raise").astype(int)
    if sorted(pair_ids.tolist()) != list(range(1, 25)):
        raise ValueError("replication pair ids must be exactly 1..24")
    if results["speciesKey"].nunique() != 24:
        raise ValueError("replication must preserve 24 unique frozen taxa")
    if not results["replication_protocol_fingerprint"].astype(str).eq(EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT).all():
        raise ValueError("replication protocol fingerprint drift across pair results")
    if not results["replication_execution_fingerprint"].astype(str).eq(EXPECTED_EXECUTION_FINGERPRINT).all():
        raise ValueError("replication execution fingerprint drift across pair results")

    for path in manifest_files:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest["replication_protocol_fingerprint"] != EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT:
            raise ValueError("pair manifest replication fingerprint drift")
        if manifest["replication_execution_fingerprint"] != EXPECTED_EXECUTION_FINGERPRINT:
            raise ValueError("pair manifest execution fingerprint drift")
        if manifest["authoritative_v2_protocol_fingerprint"] != EXPECTED_PROTOCOL_FINGERPRINT:
            raise ValueError("pair manifest authoritative v2 fingerprint drift")
        if manifest["scientific_method_changed"] is not False:
            raise ValueError("replication pair changed scientific method")
        if manifest["cohort_reselected"] is not False or manifest["declaration_reselected"] is not False:
            raise ValueError("replication pair reselected frozen identities")
        if manifest["candidate_generation_preceded_recent_outcome_fetch"] is not True:
            raise ValueError("replication pair opened recent outcome before candidate generation")

    patch_frames: list[pd.DataFrame] = []
    for path in sorted(input_root.glob(f"{PAIR_ARTIFACT_GLOB}/integrated_candidate_patches.csv")):
        try:
            frame = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            continue
        if not frame.empty:
            patch_frames.append(frame)
    patches = pd.concat(patch_frames, ignore_index=True) if patch_frames else pd.DataFrame()

    cs = results["candidate_generation_status"].eq("generated")
    te = results["temporal_status"].eq("evaluated")
    integrated = cs & te & pd.to_numeric(results["robust_minus_random_recall"], errors="coerce").notna()
    lifts = pd.to_numeric(results.loc[integrated, "robust_minus_random_recall"], errors="coerce").to_numpy(float)
    mean, low, high = taxon_bootstrap_mean_ci(
        lifts,
        repetitions=int(gate["bootstrap_repetitions"]),
        seed=int(gate["bootstrap_seed"]),
    )
    plant = _finite_mean(results.loc[integrated & results["taxon_group"].eq("plant"), "robust_minus_random_recall"])
    animal = _finite_mean(results.loc[integrated & results["taxon_group"].eq("animal"), "robust_minus_random_recall"])
    cr = float(cs.mean())
    tr = float(te.mean())
    checks = {
        "declared_taxa": len(results) == int(gate["required_declared_taxa"]),
        "candidate_generation_success_rate": cr >= float(gate["candidate_generation_success_rate_min"]),
        "temporal_evaluability_rate": tr >= float(gate["temporal_evaluability_rate_min"]),
        "mean_lift_positive": bool(np.isfinite(mean) and mean > 0),
        "bootstrap_lower_positive": bool(np.isfinite(low) and low > 0),
        "plant_mean_nonnegative": bool(np.isfinite(plant) and plant >= float(gate["plant_mean_lift_min"])),
        "animal_mean_nonnegative": bool(np.isfinite(animal) and animal >= float(gate["animal_mean_lift_min"])),
    }

    radius = float(evalcfg["primary_recovery_radius_km"])
    reps = int(evalcfg["random_baseline_repetitions"])
    if radius != 10.0 or radius != float(VALIDATED_ROBUST_PRIMARY_RADIUS_KM):
        raise ValueError("replication radius drift")

    summary = {
        "status": "country_framed_robust_integration_development_v2_replication_complete",
        "replication_protocol_fingerprint": EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
        "replication_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "authoritative_v2_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "declared_taxa": 24,
        "candidate_generation_success_taxa": int(cs.sum()),
        "candidate_generation_success_rate": cr,
        "temporally_evaluable_taxa": int(te.sum()),
        "temporal_evaluability_rate": tr,
        "integrated_evaluable_taxa": int(integrated.sum()),
        "lattice_step_deg": LATTICE_STEP_DEG,
        "points_per_regional_tile": POINTS_PER_REGIONAL_TILE,
        "primary_support_fraction": float(VALIDATED_ROBUST_SUPPORT_FRACTION),
        "primary_radius_km": radius,
        "random_baseline_repetitions": reps,
        "mean_robust_minus_random_recall": mean,
        "taxon_bootstrap_95pct_ci": [low, high],
        "plant_mean_robust_minus_random_recall": plant,
        "animal_mean_robust_minus_random_recall": animal,
        "gate_checks": checks,
        "replication_gate_passed": all(checks.values()),
        "change_from_authoritative_v2": "cohort_identity_rule_only",
        "candidate_generation_preceded_recent_outcome_fetch": True,
        "retuned_after_outcome_opening": False,
        "country_representation_changed": False,
        "country_geometry_provider_changed": False,
        "robust_core_changed": False,
        "endpoint_changed": False,
        "random_baseline_changed": False,
        "gate_changed": False,
        "seed_changed": False,
        "v1_or_v1_1_taxa_reused": False,
        "v2_taxa_reused": False,
        "confirmation_v1_taxa_consumed": False,
        "development_replication": True,
        "global_candidate_generation_validated": False,
        "technical_pair_sharding_only": True,
        "scientific_method_changed_in_execution": False,
        "retuning_on_replication_taxa_allowed": False,
    }
    return results.sort_values("integration_pair_id").reset_index(drop=True), patches, summary


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    a.output.mkdir(parents=True, exist_ok=True)
    results, patches, summary = aggregate_replication(a.input_root)
    results.to_csv(a.output / "taxon_country_results.csv", index=False)
    patches.to_csv(a.output / "integrated_candidate_patches.csv", index=False)
    (a.output / "replication_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
