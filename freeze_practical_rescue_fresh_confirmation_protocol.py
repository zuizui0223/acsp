#!/usr/bin/env python3
"""Freeze the fresh Practical Rescue confirmation protocol after final model fit.

The scientific confirmation design is fixed here. The only late-bound values
are cryptographic identities of the already-frozen final model and the already-
frozen 264-taxon exclusion set. No confirmation taxa are sampled by this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

RESCUE_PROTOCOL_FINGERPRINT = "8f4f0a85ca636bf70b445ed1bb70b93a2df7de6a5b687b91d42c436b7e258c48"
GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT = "950f7d9de90da2f2bd2561a18b7cc1eb74a60568ccc801875b96119db53bddf2"
SPSURVEY_COMMIT = "0914fcd071713fdab19f43d8d9a66436830bd917"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    model: Path,
    model_manifest: Path,
    excluded_taxa: Path,
    exclusion_manifest: Path,
    output: Path,
) -> dict[str, object]:
    model_info = json.loads(model_manifest.read_text(encoding="utf-8"))
    if model_info.get("status") != "final_rescue_model_fitted_after_official_grts_development_gate":
        raise ValueError("final rescue model manifest has not passed the frozen GRTS development stage")
    if int(model_info.get("development_pairs", 0)) != 72 or int(model_info.get("development_folds", 0)) != 360:
        raise ValueError("final rescue model was not frozen from the complete 72-pair development set")
    if model_info.get("grts_outcomes_used_as_model_features_or_targets") is not False:
        raise ValueError("final rescue model used GRTS outcomes as training inputs")
    if model_info.get("model_hyperparameters_changed_after_grts_gate") is not False:
        raise ValueError("final rescue model reports post-GRTS retuning")
    if str(model_info.get("rescue_protocol_fingerprint")) != RESCUE_PROTOCOL_FINGERPRINT:
        raise ValueError("unexpected rescue development protocol fingerprint")
    if str(model_info.get("grts_development_protocol_fingerprint")) != GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT:
        raise ValueError("unexpected GRTS development protocol fingerprint")

    model_hash = _sha256(model)
    if str(model_info.get("model_sha256")) != model_hash:
        raise ValueError("final model bytes do not match model manifest")

    exclusion_info = json.loads(exclusion_manifest.read_text(encoding="utf-8"))
    exclusions = pd.read_csv(excluded_taxa)
    if int(exclusion_info.get("excluded_unique_taxa", 0)) != 264:
        raise ValueError("fresh exclusion manifest does not freeze exactly 264 taxa")
    if len(exclusions) != 264 or exclusions["scientific_name"].astype(str).nunique() != 264:
        raise ValueError("fresh excluded_taxa.csv does not contain exactly 264 unique taxa")
    exclusion_hash = _sha256(excluded_taxa)
    if str(exclusion_info.get("excluded_taxa_sha256")) != exclusion_hash:
        raise ValueError("fresh exclusion bytes do not match exclusion manifest")
    if exclusion_info.get("new_confirmation_taxa_sampled") is not False:
        raise ValueError("exclusion stage reports that confirmation taxa were already sampled")
    if exclusion_info.get("occurrence_outcomes_inspected") is not False:
        raise ValueError("exclusion stage reports occurrence outcome inspection")

    payload: dict[str, object] = {
        "protocol_id": "acsp-practical-rescue-fresh-confirmation-v1",
        "status": "frozen_after_final_72_model_before_fresh_cohort_sampling_or_outcome_inspection",
        "final_model": {
            "model_sha256": model_hash,
            "model_manifest_sha256": _sha256(model_manifest),
            "rescue_protocol_fingerprint": RESCUE_PROTOCOL_FINGERPRINT,
            "grts_development_protocol_fingerprint": GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT,
            "development_pairs": 72,
            "development_folds": 360,
            "post_grts_retuning": False,
        },
        "exclusion": {
            "excluded_unique_taxa": 264,
            "excluded_taxa_path": str(excluded_taxa),
            "excluded_taxa_sha256": exclusion_hash,
            "exclusion_manifest_sha256": _sha256(exclusion_manifest),
            "rule": "exclude every taxon in the invalidated old 192 confirmation cohort and every taxon in the 72-pair rescue development cohort before fresh sampling",
        },
        "exclusion_files": [str(excluded_taxa)],
        "explicit_exclusion_prefixes": ["Campanula microdonta"],
        "cohort": {
            "pair_count": 192,
            "taxon_groups": ["plant", "animal"],
            "region_cell_count": 12,
            "record_count_strata": 4,
            "taxa_per_region_group_record_stratum": 2,
            "seed": 20260813,
            "minimum_records": 20,
            "facet_limit": 400,
            "records_per_pair": 150,
            "sampling_rule": "12 fixed Japanese region cells x plant/animal x within-frame record-count quartile x two globally unused taxa; exact 264-taxon exclusion before strata; no replacement after declaration",
        },
        "outer_validation": {
            "block_degrees": 0.1,
            "holdout_fraction": 0.2,
            "repeats": 5,
            "fold_seed_base": 20260813,
            "candidate_generation": "unchanged training-only build_candidate_pool contract reused from untouched Practical Core confirmation",
            "known_candidate_filter": "occurrence-supported|known-location|known anchor",
            "scientific_zero_rule": "only explicit in-run scientific ineligibility such as fewer than two spatial blocks or training-only candidate pool below Top-5 may score the declared zero estimand",
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
            "frame": "identical finite training-only ACSP candidate rows used by frozen Practical Rescue",
            "draws_per_fold": 50,
            "seed_base": 20260813,
            "seed_formula": "seed_base + pair_id*100000 + repeat*1000 + draw_index",
            "top_k": 5,
            "replacement_sites": 3,
            "score_col": "component_local_habitat_score",
            "aux_rule": "nonfinite local evidence to zero then pmax(score,1e-6)",
            "mindis_km": 10.0,
            "maxtry": 20,
        },
        "estimand": {
            "radius_km": 10.0,
            "primary": "taxon-region-pair mean over five spatial outer folds of frozen Practical Rescue Top-5 held-out recovery minus the mean of 50 pre-outcome official GRTS Top-5 draws",
        },
        "inference": {
            "unit": "taxon-region pair",
            "bootstrap_draws": 30000,
            "sign_flip_draws": 30000,
            "seed": 20260813,
            "minimum_absolute_recall_gain": 0.015,
            "primary_contrast": "practical_rescue_final_72 - official_grts_proportional_local_mindis10km",
            "promotion_gate": "192/192 verified pair artifacts AND mean difference >= 0.015 AND pair-bootstrap 95% CI lower bound > 0 AND sign-flip p < 0.05",
        },
        "leakage_guardrail": "held-out coordinates are not passed to either operational selector; rescue and all GRTS pre-outcome artifacts are physically written before held-out scoring",
        "confirmation_taxa_sampled_at_protocol_freeze": False,
        "confirmation_occurrence_outcomes_inspected_at_protocol_freeze": False,
        "missing_pair_artifacts_scored_as_zero": False,
        "no_retuning_after_confirmation_outcome": True,
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
        "final_model_sha256": model_hash,
        "excluded_taxa_sha256": exclusion_hash,
        "confirmation_taxa_sampled": False,
        "confirmation_occurrence_outcomes_inspected": False,
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--model", type=Path, required=True)
    command.add_argument("--model-manifest", type=Path, required=True)
    command.add_argument("--excluded-taxa", type=Path, required=True)
    command.add_argument("--exclusion-manifest", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
