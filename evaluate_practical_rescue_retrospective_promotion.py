#!/usr/bin/env python3
"""Combine independently frozen fresh gates into the Practical Rescue promotion state.

This command does not re-score any biological outcome. It only checks the two
pre-outcome promotion requirements that can be satisfied retrospectively:
(1) the corrected official GRTS v2 fresh primary gate, and
(2) the issue-57 frozen-v1 fresh companion gate.

Prospective field validation and broad native-biosurvey superiority remain
separate, explicitly unresolved gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PRIMARY_PROTOCOL = "c7d84a3160e9d9b0b05b932c44444be5dfd750200e72749fb413592499bcf8bd"
COMPANION_PROTOCOL = "ed8e1333cf9638f90aa0fa2eda11d0845b484c6316826a194e02eb1b3dc8847e"
MODEL_SHA = "e5fde07f4aaad1ae5dcadb989169fd17ef428ac2be7577f5fd382c4f12fb45a3"


def run(primary_manifest: Path, companion_manifest: Path, output: Path) -> dict[str, object]:
    primary = json.loads(primary_manifest.read_text(encoding="utf-8"))
    companion = json.loads(companion_manifest.read_text(encoding="utf-8"))

    if primary.get("status") != "fresh_practical_rescue_confirmation_evaluated":
        raise ValueError("primary fresh confirmation is not a completed scientific aggregate")
    if companion.get("status") != "fresh_practical_rescue_companion_evaluated":
        raise ValueError("fresh companion comparison is not a completed scientific aggregate")
    if str(primary.get("protocol_fingerprint")) != PRIMARY_PROTOCOL:
        raise ValueError("unexpected fresh primary protocol fingerprint")
    if str(companion.get("protocol_fingerprint")) != COMPANION_PROTOCOL:
        raise ValueError("unexpected fresh companion protocol fingerprint")
    if str(companion.get("fresh_protocol_fingerprint")) != PRIMARY_PROTOCOL:
        raise ValueError("companion is not bound to the frozen fresh primary protocol")
    if int(primary.get("declared_pairs", 0)) != 192 or int(primary.get("verified_pair_artifacts", 0)) != 192:
        raise ValueError("fresh primary does not contain 192 verified pair artifacts")
    if int(companion.get("declared_pairs", 0)) != 192 or int(companion.get("verified_pair_artifacts", 0)) != 192:
        raise ValueError("fresh companion does not contain 192 verified pair artifacts")
    if str(primary.get("final_model_sha256")) != MODEL_SHA:
        raise ValueError("fresh primary used an unexpected final Rescue model")
    if str(companion.get("final_model_sha256")) != MODEL_SHA:
        raise ValueError("fresh companion used an unexpected final Rescue model")
    if primary.get("missing_pair_artifacts_scored_as_zero") is not False:
        raise ValueError("fresh primary permits missing artifacts to become zero")
    if companion.get("missing_pair_artifacts_scored_as_zero") is not False:
        raise ValueError("fresh companion permits missing artifacts to become zero")
    if primary.get("no_retuning_after_confirmation_outcome") is not True:
        raise ValueError("fresh primary does not preserve the no-retuning contract")
    if companion.get("fresh_outcomes_used_for_retuning") is not False:
        raise ValueError("fresh companion reports post-outcome retuning")

    grts_pass = bool(primary.get("promotion_gate_passed") is True)
    v1_pass = bool(companion.get("required_v2_minus_frozen_v1_gate_passed") is True)
    retrospective_pass = bool(grts_pass and v1_pass)
    result = {
        "status": (
            "retrospective_ecological_promotion_passed"
            if retrospective_pass
            else "retrospective_ecological_promotion_not_passed"
        ),
        "fresh_primary_protocol_fingerprint": PRIMARY_PROTOCOL,
        "fresh_companion_protocol_fingerprint": COMPANION_PROTOCOL,
        "final_model_sha256": MODEL_SHA,
        "verified_fresh_pairs": 192,
        "corrected_grts_v2_fresh_gate_passed": grts_pass,
        "frozen_v1_fresh_companion_gate_passed": v1_pass,
        "retrospective_ecological_promotion_passed": retrospective_pass,
        "retrospective_claim_if_passed": (
            "On the frozen untouched Japanese taxon-region confirmation cohort, Practical Rescue improved the predeclared 10-km Top-5 regional held-out recovery endpoint over both corrected official GRTS v2 and frozen publication-facing ACSP v1."
            if retrospective_pass
            else None
        ),
        "claim_boundary": "regional 10-km finite survey-decision recovery; not exact-site occupancy, access, detectability, abundance, phenology, or discoveries per field day",
        "production_promotion_status": "blocked_pending_prospective_field_attempt_non_detection_effort_and_access_records",
        "broad_existing_tool_superiority_status": "pending_native_biosurvey_end_to_end_gate_for_the_promoted_rescue_policy",
        "sdm_relationship_status": "separate_existing_fitted_sdm_decision_contrast_only; no universal SDM superiority claim",
        "post_confirmation_retuning_allowed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--primary-manifest", type=Path, required=True)
    command.add_argument("--companion-manifest", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
