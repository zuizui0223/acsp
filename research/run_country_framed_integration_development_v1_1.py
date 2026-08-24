#!/usr/bin/env python3
"""Run preregistered country-framed integration development v1.1.

V1.1 uses a taxon cohort disjoint from rejected v1 and changes exactly one
integration-specific condition: after drawing 800 external country-geometry
points, incomplete terrain rows are dropped and the remaining non-empty complete
surface is passed to the unchanged robust core. There is no exact post-terrain
800-row requirement and no replacement threshold is introduced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from acsp.taxon_patches import ROBUST_TERRAIN_FEATURES
from acsp.validated_robust import (
    VALIDATED_ROBUST_PRIMARY_RADIUS_KM,
    VALIDATED_ROBUST_SUPPORT_FRACTION,
    validated_robust_candidate_patches,
)
from country_framed_robust_integration import country_terrain_inputs, fetch_country_occurrences
from geoboundaries_v6_provider import fetch_geoboundaries_country_geometry
from run_country_framed_integration_development_v1 import (
    _finite_mean,
    _geometry_digest_from_source_version,
    _random_seed,
    fetch_recent_country_occurrences,
    recovery_fraction,
    same_size_random_recovery,
    taxon_bootstrap_mean_ci,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v1_1.json"
V1_IDENTITIES_PATH = ROOT / "validation" / "country_framed_robust_integration_development_v1" / "predeclared_taxon_country_pairs_compact.csv"
CONFIRMATION_TAXA_PATH = ROOT / "validation" / "geographic_framing_confirmation_v1" / "confirmation_taxa.csv"
EXPECTED_PROTOCOL_FINGERPRINT = "b61ab7f2625112c459559d28129db89c74ddc32808ebd5cfc6cf43009824d555"


def _protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_PROTOCOL_FINGERPRINT or calculated != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError(
            f"v1.1 protocol fingerprint mismatch: file={stored}, calculated={calculated}, expected={EXPECTED_PROTOCOL_FINGERPRINT}"
        )
    payload["protocol_fingerprint"] = stored
    return payload


def _audit_disjoint_declarations(declarations: pd.DataFrame) -> None:
    if len(declarations) != 24 or declarations["speciesKey"].nunique() != 24:
        raise ValueError("v1.1 stage-1 artifact must contain exactly 24 unique taxa")
    v1 = pd.read_csv(V1_IDENTITIES_PATH)
    overlap_v1 = set(pd.to_numeric(declarations["speciesKey"], errors="raise").astype(int)) & set(
        pd.to_numeric(v1["speciesKey"], errors="raise").astype(int)
    )
    if overlap_v1:
        raise ValueError(f"v1.1 artifact reuses rejected v1 taxa: {sorted(overlap_v1)}")
    if CONFIRMATION_TAXA_PATH.is_file():
        confirmation = pd.read_csv(CONFIRMATION_TAXA_PATH)
        overlap_confirmation = set(declarations["scientific_name"].astype(str)) & set(
            confirmation["scientific_name"].astype(str)
        )
        if overlap_confirmation:
            raise ValueError(f"v1.1 artifact overlaps fresh framing-confirmation taxa: {sorted(overlap_confirmation)[:5]}")


def evaluate_frozen_declarations_v1_1(
    declarations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    protocol = _protocol()
    _audit_disjoint_declarations(declarations)
    outcome_cfg = protocol["outcome_evaluation"]
    radius_km = float(outcome_cfg["primary_recovery_radius_km"])
    if radius_km != float(VALIDATED_ROBUST_PRIMARY_RADIUS_KM) or radius_km != 10.0:
        raise ValueError("v1.1 primary radius drifted from the frozen 10 km endpoint")
    repetitions = int(outcome_cfg["random_baseline_repetitions"])
    recent_years = tuple(int(x) for x in outcome_cfg["heldout_year_range"])
    recent_cap = int(outcome_cfg["heldout_max_coordinate_records_per_taxon_country"])
    random_seed_base = int(outcome_cfg["random_seed"])

    result_rows: list[dict[str, object]] = []
    patch_frames: list[pd.DataFrame] = []

    for row in declarations.itertuples(index=False):
        base = row._asdict()
        species_key = int(base["speciesKey"])
        country_code = str(base.get("selected_country_code") or "").upper()
        declaration_status = str(base.get("declaration_status") or "")
        candidate_status = "not_attempted_declaration_failed"
        candidate_failure_reason = ""
        temporal_status = "not_attempted_no_declared_country"
        temporal_failure_reason = ""
        historical_rows = recent_rows = complete_surface_rows = prototype_rows = candidate_patch_count = 0
        support_audit_json = "{}"
        verified_geometry_sha = ""
        robust_recall = random_mean = random_q025 = random_q975 = lift = float("nan")
        surface = pd.DataFrame()
        patches = pd.DataFrame()
        recent = pd.DataFrame(columns=["latitude", "longitude"])

        if declaration_status == "declared" and country_code:
            # Same candidate-first ordering as v1. Recent held-out outcomes are
            # fetched only after candidate generation has completed or failed.
            try:
                geometry = fetch_geoboundaries_country_geometry(country_code)
                verified_geometry_sha = _geometry_digest_from_source_version(geometry.source_version)
                expected_geometry_sha = str(base.get("geometry_canonical_sha256") or "").lower()
                if verified_geometry_sha != expected_geometry_sha:
                    raise ValueError(
                        f"country geometry digest mismatch: declared={expected_geometry_sha}, refetched={verified_geometry_sha}"
                    )
                occurrences = fetch_country_occurrences(species_key, country_code)
                historical_rows = int(len(occurrences))
                surface, prototypes, _surface_seed = country_terrain_inputs(occurrences, geometry)
                complete_surface_rows = int(len(surface))
                prototype_rows = int(len(prototypes))
                # Deliberate sole change from rejected v1: do NOT require
                # complete_surface_rows == 800. country_terrain_inputs already
                # rejects an empty complete surface; no new minimum is added.
                if complete_surface_rows <= 0 or complete_surface_rows > 800:
                    raise ValueError(
                        f"unexpected complete-surface size after 800 geometry draws: {complete_surface_rows}"
                    )
                patches, support_audit = validated_robust_candidate_patches(
                    surface,
                    prototypes,
                    feature_columns=ROBUST_TERRAIN_FEATURES,
                    area_col="survey_area_id",
                )
                candidate_patch_count = int(len(patches))
                support_audit_json = json.dumps(
                    support_audit.as_dict(), sort_keys=True, separators=(",", ":")
                )
                if candidate_patch_count <= 0:
                    raise ValueError("frozen robust core returned zero candidate patches")
                candidate_status = "generated"
                patches = patches.copy()
                patches["integration_pair_id"] = int(base["integration_pair_id"])
                patches["speciesKey"] = species_key
                patches["scientific_name"] = str(base["scientific_name"])
                patches["taxon_group"] = str(base["taxon_group"])
                patches["framing_country_code"] = country_code
                patch_frames.append(patches)
            except Exception as exc:
                candidate_status = "candidate_generation_failed"
                candidate_failure_reason = f"{type(exc).__name__}: {exc}"

            try:
                recent = fetch_recent_country_occurrences(
                    species_key,
                    country_code,
                    years=recent_years,
                    cap=recent_cap,
                )
                recent_rows = int(len(recent))
                temporal_status = "evaluated" if recent_rows > 0 else "zero_recent_country_records"
            except Exception as exc:
                temporal_status = "recent_provider_failed"
                temporal_failure_reason = f"{type(exc).__name__}: {exc}"

            if candidate_status == "generated" and temporal_status == "evaluated":
                robust_recall = recovery_fraction(recent, patches, radius_km)
                random_mean, random_q025, random_q975 = same_size_random_recovery(
                    recent,
                    surface,
                    selected_count=candidate_patch_count,
                    radius_km=radius_km,
                    repetitions=repetitions,
                    seed=_random_seed(random_seed_base, species_key, country_code),
                )
                lift = float(robust_recall - random_mean)

        result_rows.append(
            {
                **base,
                "candidate_generation_status": candidate_status,
                "candidate_generation_failure_reason": candidate_failure_reason,
                "temporal_status": temporal_status,
                "temporal_failure_reason": temporal_failure_reason,
                "historical_training_occurrence_rows": historical_rows,
                "recent_heldout_occurrence_rows": recent_rows,
                "complete_post_terrain_surface_rows": complete_surface_rows,
                "complete_surface_fraction_of_800_draws": float(complete_surface_rows / 800.0),
                "prototype_rows": prototype_rows,
                "candidate_patch_count": candidate_patch_count,
                "verified_geometry_canonical_sha256": verified_geometry_sha,
                "primary_radius_km": radius_km,
                "robust_recall": robust_recall,
                "random_recall_mean": random_mean,
                "random_recall_q025": random_q025,
                "random_recall_q975": random_q975,
                "robust_minus_random_recall": lift,
                "support_audit_json": support_audit_json,
            }
        )

    results = pd.DataFrame(result_rows)
    all_patches = pd.concat(patch_frames, ignore_index=True) if patch_frames else pd.DataFrame()
    candidate_success = results["candidate_generation_status"].eq("generated")
    temporal_evaluable = results["temporal_status"].eq("evaluated")
    integrated = candidate_success & temporal_evaluable & pd.to_numeric(
        results["robust_minus_random_recall"], errors="coerce"
    ).notna()
    gate_cfg = protocol["development_gate"]
    lifts = pd.to_numeric(results.loc[integrated, "robust_minus_random_recall"], errors="coerce").to_numpy(float)
    mean_lift, ci_low, ci_high = taxon_bootstrap_mean_ci(
        lifts,
        repetitions=int(gate_cfg["bootstrap_repetitions"]),
        seed=int(gate_cfg["bootstrap_seed"]),
    )
    plant_mean = _finite_mean(
        results.loc[integrated & results["taxon_group"].eq("plant"), "robust_minus_random_recall"]
    )
    animal_mean = _finite_mean(
        results.loc[integrated & results["taxon_group"].eq("animal"), "robust_minus_random_recall"]
    )
    candidate_rate = float(candidate_success.mean())
    temporal_rate = float(temporal_evaluable.mean())
    gate_checks = {
        "declared_taxa": int(len(results)) == int(gate_cfg["required_declared_taxa"]),
        "candidate_generation_success_rate": candidate_rate >= float(gate_cfg["candidate_generation_success_rate_min"]),
        "temporal_evaluability_rate": temporal_rate >= float(gate_cfg["temporal_evaluability_rate_min"]),
        "mean_lift_positive": bool(np.isfinite(mean_lift) and mean_lift > 0.0),
        "bootstrap_lower_positive": bool(np.isfinite(ci_low) and ci_low > 0.0),
        "plant_mean_nonnegative": bool(np.isfinite(plant_mean) and plant_mean >= float(gate_cfg["plant_mean_lift_min"])),
        "animal_mean_nonnegative": bool(np.isfinite(animal_mean) and animal_mean >= float(gate_cfg["animal_mean_lift_min"])),
    }
    successful_surface = pd.to_numeric(
        results.loc[candidate_success, "complete_post_terrain_surface_rows"], errors="coerce"
    )
    summary: dict[str, object] = {
        "status": "country_framed_robust_integration_development_v1_1_complete",
        "protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "parent_rejected_v1_run": 32685558754,
        "declared_taxa": int(len(results)),
        "candidate_generation_success_taxa": int(candidate_success.sum()),
        "candidate_generation_success_rate": candidate_rate,
        "temporally_evaluable_taxa": int(temporal_evaluable.sum()),
        "temporal_evaluability_rate": temporal_rate,
        "integrated_evaluable_taxa": int(integrated.sum()),
        "primary_support_fraction": float(VALIDATED_ROBUST_SUPPORT_FRACTION),
        "primary_radius_km": radius_km,
        "random_baseline_repetitions": repetitions,
        "mean_robust_minus_random_recall": mean_lift,
        "taxon_bootstrap_95pct_ci": [ci_low, ci_high],
        "plant_mean_robust_minus_random_recall": plant_mean,
        "animal_mean_robust_minus_random_recall": animal_mean,
        "successful_candidate_surface_rows_median": (
            float(successful_surface.median()) if len(successful_surface) else float("nan")
        ),
        "successful_candidate_surface_rows_min": (
            int(successful_surface.min()) if len(successful_surface) else None
        ),
        "gate_checks": gate_checks,
        "development_gate_passed": bool(all(gate_checks.values())),
        "only_method_change_from_v1": "remove_exact_800_complete_post_terrain_surface_requirement",
        "terrain_complete_rows_required_exactly_800": False,
        "new_minimum_complete_surface_rows_added": False,
        "candidate_generation_preceded_recent_outcome_fetch": True,
        "retuned_after_outcome_opening": False,
        "country_representation_changed": False,
        "country_geometry_provider_changed": False,
        "robust_core_changed": False,
        "v1_taxa_reused": False,
        "confirmation_v1_taxa_consumed": False,
        "development_only": True,
        "global_candidate_generation_validated": False,
    }
    return results, all_patches, summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--declarations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    declarations = pd.read_csv(args.declarations)
    results, patches, summary = evaluate_frozen_declarations_v1_1(declarations)
    results.to_csv(args.output / "taxon_country_results.csv", index=False)
    patches.to_csv(args.output / "integrated_candidate_patches.csv", index=False)
    (args.output / "development_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
