#!/usr/bin/env python3
"""Freeze vNext2 untouched confirmation after both Rescue-v2 and router are fitted."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

RESCUE_PROTOCOL_FINGERPRINT = "8f4f0a85ca636bf70b445ed1bb70b93a2df7de6a5b687b91d42c436b7e258c48"
GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT = "74fec14b44035e897072b022d82ea30c00b27ce1bb95c16a0e9a5578a3d3da7a"
ROUTER_PROTOCOL_FINGERPRINT = "988243d9acbb20b16fcf7ec307db8c3a5325c3abd7ba71835da5e9911bc0cad6"
SPSURVEY_COMMIT = "0914fcd071713fdab19f43d8d9a66436830bd917"
EXPECTED_RESCUE_MODEL_SHA = "e5fde07f4aaad1ae5dcadb989169fd17ef428ac2be7577f5fd382c4f12fb45a3"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(
    rescue_model: Path,
    rescue_model_manifest: Path,
    router_model: Path,
    router_model_manifest: Path,
    excluded_taxa: Path,
    exclusion_manifest: Path,
    output: Path,
) -> dict[str, object]:
    rescue_info = json.loads(rescue_model_manifest.read_text(encoding="utf-8"))
    if _sha256(rescue_model) != EXPECTED_RESCUE_MODEL_SHA or str(rescue_info.get("model_sha256")) != EXPECTED_RESCUE_MODEL_SHA:
        raise ValueError("unexpected frozen Rescue-v2 model bytes")
    if str(rescue_info.get("rescue_protocol_fingerprint")) != RESCUE_PROTOCOL_FINGERPRINT:
        raise ValueError("unexpected Rescue-v2 development protocol")
    if str(rescue_info.get("grts_development_protocol_fingerprint")) != GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT:
        raise ValueError("unexpected corrected-GRTS development protocol in Rescue-v2 model")
    if rescue_info.get("grts_outcomes_used_as_model_features_or_targets") is not False:
        raise ValueError("Rescue-v2 model reports GRTS outcome leakage")
    if rescue_info.get("model_hyperparameters_changed_after_grts_gate") is not False:
        raise ValueError("Rescue-v2 model reports post-GRTS retuning")

    router_info = json.loads(router_model_manifest.read_text(encoding="utf-8"))
    router = json.loads(router_model.read_text(encoding="utf-8"))
    if router_info.get("status") != "final_vnext2_router_fitted_after_complete_development_gate":
        raise ValueError("vNext2 router has not passed the frozen development fit stage")
    if str(router_info.get("protocol_fingerprint")) != ROUTER_PROTOCOL_FINGERPRINT:
        raise ValueError("unexpected router protocol fingerprint")
    if str(router.get("protocol_fingerprint")) != ROUTER_PROTOCOL_FINGERPRINT:
        raise ValueError("router JSON protocol fingerprint mismatch")
    if str(router_info.get("model_fingerprint")) != str(router.get("model_fingerprint")):
        raise ValueError("router model fingerprint differs from its manifest")
    if str(router_info.get("model_sha256")) != _sha256(router_model):
        raise ValueError("router model bytes differ from its manifest")
    if router_info.get("confirmation_outcomes_used_for_fit") is not False:
        raise ValueError("router manifest reports confirmation outcomes in fit")
    if router_info.get("hyperparameters_changed_after_development_gate") is not False:
        raise ValueError("router manifest reports post-gate hyperparameter changes")
    if int(router_info.get("development_pairs", 0)) != 192 or int(router_info.get("training_rows", 0)) != 873:
        raise ValueError("router was not fitted to the complete frozen development set")

    exclusion_info = json.loads(exclusion_manifest.read_text(encoding="utf-8"))
    excluded = pd.read_csv(excluded_taxa)
    if int(exclusion_info.get("excluded_unique_taxa", 0)) != 456:
        raise ValueError("vNext2 exclusion manifest does not contain exactly 456 taxa")
    if len(excluded) != 456 or excluded["scientific_name"].astype(str).nunique() != 456:
        raise ValueError("vNext2 excluded_taxa.csv is not exactly 456 unique taxa")
    if str(exclusion_info.get("excluded_taxa_sha256")) != _sha256(excluded_taxa):
        raise ValueError("vNext2 exclusion bytes differ from manifest")
    if exclusion_info.get("new_confirmation_taxa_sampled") is not False:
        raise ValueError("new confirmation taxa were sampled before protocol freeze")
    if exclusion_info.get("new_confirmation_occurrence_outcomes_inspected") is not False:
        raise ValueError("new confirmation outcomes were inspected before protocol freeze")

    seed = 20260815
    payload: dict[str, object] = {
        "protocol_id": "acsp-practical-rescue-vnext2-untouched-confirmation-v1",
        "status": "frozen_after_final_router_before_new_cohort_sampling_or_outcome_inspection",
        "final_rescue_v2": {
            "model_sha256": EXPECTED_RESCUE_MODEL_SHA,
            "model_manifest_sha256": _sha256(rescue_model_manifest),
            "rescue_protocol_fingerprint": RESCUE_PROTOCOL_FINGERPRINT,
            "grts_development_protocol_fingerprint": GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT,
            "post_grts_retuning": False,
        },
        "final_router": {
            "model_sha256": _sha256(router_model),
            "model_manifest_sha256": _sha256(router_model_manifest),
            "model_fingerprint": str(router_info["model_fingerprint"]),
            "router_protocol_fingerprint": ROUTER_PROTOCOL_FINGERPRINT,
            "ridge_alpha": 10.0,
            "decision_threshold_absolute_recall": 0.015,
            "development_pairs": 192,
            "development_complete_folds": 873,
            "post_development_retuning": False,
        },
        "exclusion": {
            "excluded_unique_taxa": 456,
            "excluded_taxa_path": str(excluded_taxa),
            "excluded_taxa_sha256": _sha256(excluded_taxa),
            "exclusion_manifest_sha256": _sha256(exclusion_manifest),
            "rule": "exclude prior old192+Rescue72 union and all 192 inspected fresh-v2 taxa before new sampling",
        },
        "exclusion_files": [str(excluded_taxa)],
        "explicit_exclusion_prefixes": ["Campanula microdonta"],
        "cohort": {
            "pair_count": 192,
            "taxon_groups": ["plant", "animal"],
            "region_cell_count": 12,
            "record_count_strata": 4,
            "taxa_per_region_group_record_stratum": 2,
            "seed": seed,
            "minimum_records": 20,
            "facet_limit": 400,
            "records_per_pair": 150,
            "sampling_rule": "12 fixed Japanese region cells x plant/animal x within-frame record-count quartile x two globally unused taxa; exact 456-taxon exclusion; no replacement after declaration",
        },
        "outer_validation": {
            "block_degrees": 0.1,
            "holdout_fraction": 0.2,
            "repeats": 5,
            "fold_seed_base": seed,
            "candidate_generation": "unchanged training-only build_candidate_pool contract from the prior fully fresh confirmation",
            "known_candidate_filter": "occurrence-supported|known-location|known anchor",
            "scientific_zero_rule": "fewer than four valid coordinates, fewer than two spatial blocks, or training-only eligible candidate pool below Top-5 yields the same explicit zero fold for router, v1, Rescue-v2, and GRTS",
            "infrastructure_failure_rule": "missing/unverified pair artifact invalidates confirmation and is never converted to scientific zero",
        },
        "software_contract": {
            "python": "3.13.5",
            "scikit_learn": "1.8.0",
            "pandas": "2.2.3",
            "numpy": "2.3.5",
        },
        "official_grts": {
            "implementation": "USEPA/spsurvey::grts",
            "spsurvey_version": "5.6.1",
            "spsurvey_tag_commit": SPSURVEY_COMMIT,
            "variant": "official_grts_proportional_local_mindis10km",
            "frame": "identical finite training-only candidate rows used by v1, Rescue-v2, and router",
            "draws_per_fold": 50,
            "seed_base": seed,
            "seed_formula": "seed_base + pair_id*100000 + repeat*1000 + draw_index",
            "top_k": 5,
            "replacement_sites_requested": 3,
            "replacement_sites_effective_rule": "min(replacement_sites_requested, max(candidate_frame_rows - n_base, 0))",
            "score_col": "component_local_habitat_score",
            "aux_rule": "nonfinite local evidence to zero then pmax(score,1e-6)",
            "mindis_km": 10.0,
            "maxtry": 20,
            "nonempty_frame_implementation_error_rule": "hard fail; never score implementation failure as zero",
        },
        "estimand": {
            "radius_km": 10.0,
            "primary": "taxon-region-pair mean across five frozen spatial folds of safe-router Top-5 held-out recovery",
            "comparisons": ["safe_router_minus_corrected_grts_v2", "safe_router_minus_frozen_v1"],
        },
        "inference": {
            "unit": "taxon-region pair",
            "bootstrap_draws": 30000,
            "sign_flip_draws": 30000,
            "seed": seed,
            "minimum_absolute_recall_gain": 0.015,
            "overall_gate_each_primary_comparison": "mean >=0.015 AND pair-bootstrap 95% CI lower >0 AND sign-flip p<0.05",
            "taxon_group_gate_each_primary_comparison": "within plant96 and animal96 separately, mean >=0.015 AND pair-bootstrap 95% CI lower >0 AND sign-flip p<0.05",
            "promotion_gate": "192/192 verified pair artifacts AND both primary comparisons pass overall AND both primary comparisons pass the full plant and animal subgroup gates",
        },
        "secondary_comparators": ["local-only", "geographic maximin", "same-pool random mean"],
        "leakage_guardrail": "v1, Rescue-v2, router decision, secondary comparator decisions, and GRTS draws are physically frozen before held-out coordinates are scored",
        "new_confirmation_taxa_sampled_at_protocol_freeze": False,
        "new_confirmation_occurrence_outcomes_inspected_at_protocol_freeze": False,
        "missing_pair_artifacts_scored_as_zero": False,
        "taxon_replacement_after_declaration_allowed": False,
        "no_retuning_after_confirmation_outcome": True,
        "retrospective_promotion_does_not_imply_production_field_efficiency": True,
        "native_biosurvey_gate_still_required_for_broad_existing_tool_superiority": True,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["protocol_fingerprint"] = fingerprint
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "status": payload["status"],
        "protocol_fingerprint": fingerprint,
        "router_model_fingerprint": str(router_info["model_fingerprint"]),
        "excluded_taxa_sha256": _sha256(excluded_taxa),
        "new_confirmation_taxa_sampled": False,
        "new_confirmation_occurrence_outcomes_inspected": False,
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--rescue-model", type=Path, required=True)
    command.add_argument("--rescue-model-manifest", type=Path, required=True)
    command.add_argument("--router-model", type=Path, required=True)
    command.add_argument("--router-model-manifest", type=Path, required=True)
    command.add_argument("--excluded-taxa", type=Path, required=True)
    command.add_argument("--exclusion-manifest", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
