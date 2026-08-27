#!/usr/bin/env python3
"""Offline validator for the issue #169 provider-eligible freeze execution contract."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "validation"
    / "acsp_country_frame_observability_provider_eligible_confirmation_execution_v1.json"
)
EXPECTED_EXECUTION_FINGERPRINT = "0bdc69f05fb1d8030c13f9ccea01676d2915a544846bda8c216362e9890adc34"
EXPECTED_PROTOCOL_FINGERPRINT = "91b8143f38abb173c3cdabc198bfcc5f113632f33b3c674b99374aac1efdd644"
EXPECTED_COVERAGE_FINGERPRINT = "377f6374e077cc38ea7fc026de6dc289abc2716aca8c83d66ddcd42826139520"
WORKFLOW_PATH = ".github/workflows/country-frame-observability-provider-eligible-confirmation-freeze.yml"
ACTIVATION_MARKER_PATH = "validation/activate_country_frame_observability_provider_eligible_confirmation_v1.marker"
AUTHORITATIVE_ARTIFACT_NAME = "country-frame-observability-provider-eligible-confirmation-cohort"
ABORT_ARTIFACT_NAME = "country-frame-observability-provider-eligible-confirmation-abort-audit"


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def validate_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("contract_id") != "acsp_country_frame_observability_provider_eligible_confirmation_execution_v1":
        raise ValueError("unexpected provider-eligible execution contract id")
    if payload.get("status") != "predeclared_before_any_new_candidate_identity_historical_facet_or_heldout_outcome":
        raise ValueError("provider-eligible execution contract status drift")
    if payload.get("parent_issue") != 169:
        raise ValueError("provider-eligible execution parent issue drift")

    stored = str(payload.get("execution_fingerprint", ""))
    material = copy.deepcopy(payload)
    material.pop("execution_fingerprint", None)
    calculated = _canonical_sha256(material)
    if stored != EXPECTED_EXECUTION_FINGERPRINT or calculated != EXPECTED_EXECUTION_FINGERPRINT:
        raise ValueError(
            "provider-eligible execution fingerprint mismatch: "
            f"file={stored}, calculated={calculated}, expected={EXPECTED_EXECUTION_FINGERPRINT}"
        )
    if payload.get("protocol_fingerprint") != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("provider-eligible scientific protocol binding drift")
    if payload.get("coverage_contract_fingerprint") != EXPECTED_COVERAGE_FINGERPRINT:
        raise ValueError("provider-eligible coverage binding drift")

    workflow = payload.get("workflow")
    if not isinstance(workflow, dict):
        raise ValueError("provider-eligible workflow contract is malformed")
    expected_workflow = {
        "path": WORKFLOW_PATH,
        "name": "Country-frame observability provider-eligible confirmation freeze",
        "event": "push",
        "branch": "main",
        "activation_marker_path": ACTIVATION_MARKER_PATH,
        "schedule_present": False,
        "pull_request_trigger_present": False,
        "workflow_dispatch_present": False,
        "required_run_number": 1,
    }
    if workflow != expected_workflow:
        raise ValueError("provider-eligible workflow trigger contract drift")

    scientific = payload.get("scientific_object")
    if not isinstance(scientific, dict):
        raise ValueError("provider-eligible scientific object contract is malformed")
    if scientific.get("target_frames") != 96:
        raise ValueError("provider-eligible target frame count drift")
    if scientific.get("plant") != 48 or scientific.get("animal") != 48:
        raise ValueError("provider-eligible plant/animal balance drift")
    if scientific.get("identity_selection_seed") != 664395665:
        raise ValueError("provider-eligible identity seed drift")
    if scientific.get("score_formula") != "log1p(historical_selected_country_count)":
        raise ValueError("provider-eligible score formula drift")
    if scientific.get("freeze_opens_heldout") is not False:
        raise ValueError("provider-eligible freeze workflow may not open heldout")
    if scientific.get("replacement_after_freeze_allowed") is not False:
        raise ValueError("provider-eligible post-freeze replacement became allowed")

    eligibility = payload.get("eligibility_semantics")
    if not isinstance(eligibility, dict):
        raise ValueError("provider-eligible eligibility semantics are malformed")
    if eligibility.get("country_declaration_precedes_provider_coverage_check") is not True:
        raise ValueError("country declaration/coverage order drift")
    if eligibility.get("unsupported_declared_country_is_pre_freeze_candidate_ineligibility") is not True:
        raise ValueError("unsupported-country eligibility semantics drift")
    if eligibility.get("unsupported_declared_country_may_be_substituted") is not False:
        raise ValueError("country substitution became allowed")
    if eligibility.get("candidate_is_scientifically_frozen_before_provider_eligibility") is not False:
        raise ValueError("candidate would be scientifically frozen before provider eligibility")
    if eligibility.get("continuing_to_next_hash_ordered_candidate_after_pre_freeze_ineligibility_is_post_selection_replacement") is not False:
        raise ValueError("pre-freeze eligibility traversal was reclassified as post-selection replacement")
    if eligibility.get("supported_geometry_provider_error_aborts") is not True:
        raise ValueError("supported geometry provider errors must abort")
    if eligibility.get("historical_or_discovery_provider_error_aborts") is not True:
        raise ValueError("historical/discovery provider errors must abort")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("provider-eligible artifact contract is malformed")
    if artifacts.get("authoritative_name") != AUTHORITATIVE_ARTIFACT_NAME:
        raise ValueError("provider-eligible authoritative artifact name drift")
    if artifacts.get("abort_audit_name") != ABORT_ARTIFACT_NAME:
        raise ValueError("provider-eligible abort artifact name drift")

    heldout = payload.get("heldout_stage")
    if not isinstance(heldout, dict):
        raise ValueError("provider-eligible heldout-stage contract is malformed")
    if heldout.get("separate_explicit_one_shot_activation_required") is not True:
        raise ValueError("provider-eligible heldout stage lost separate activation")
    if heldout.get("heldout_execution_may_start_in_this_workflow") is not False:
        raise ValueError("provider-eligible freeze workflow may not start heldout execution")
    if heldout.get("authoritative_freeze_artifact_must_be_byte_pinned_before_heldout") is not True:
        raise ValueError("provider-eligible heldout lost byte-pinned freeze prerequisite")
    return payload


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provider-eligible execution contract must be a JSON object")
    return validate_contract(payload)


__all__ = [
    "ABORT_ARTIFACT_NAME",
    "ACTIVATION_MARKER_PATH",
    "AUTHORITATIVE_ARTIFACT_NAME",
    "CONTRACT_PATH",
    "EXPECTED_COVERAGE_FINGERPRINT",
    "EXPECTED_EXECUTION_FINGERPRINT",
    "EXPECTED_PROTOCOL_FINGERPRINT",
    "WORKFLOW_PATH",
    "load_contract",
    "validate_contract",
]
