#!/usr/bin/env python3
"""Static verifier and pure selection semantics for issue #169.

Importing this module performs no network access and opens no fresh identity,
focal-species historical facet, or heldout outcome. Live providers belong only
to a later explicit first-activation workflow.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from geoboundaries_v6_coverage_contract import (
    alpha2_to_alpha3_if_supported,
    load_contract as load_coverage_contract,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_frame_observability_confirmation_provider_eligible_v1.json"
EXECUTION_PATH = ROOT / "validation" / "acsp_country_frame_observability_confirmation_provider_eligible_execution_v1.json"
EXCLUSION_PATH = ROOT / "validation" / "acsp_provider_eligible_observability_exclusion_provenance_v1.json"
EXPECTED_PROTOCOL_FINGERPRINT = "4afd35c96178934f33f1e1336871df59972ffc6f487c6f11b9abedd690ea442d"
EXPECTED_EXECUTION_FINGERPRINT = "541c97a81030905533bd7e8f7f8429494bd7f65dd25f96f538f29fcf21bc2c40"
EXPECTED_EXCLUSION_FINGERPRINT = "b4dba265e33ec716e5451de8bb18eaf4e3647e66ccb29aa089644fca2e74d52b"
EXPECTED_COVERAGE_FINGERPRINT = "377f6374e077cc38ea7fc026de6dc289abc2716aca8c83d66ddcd42826139520"


def _canonical_sha256(payload: object) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("utf-8") + data).hexdigest()


def _load_fingerprinted(path: Path, key: str, expected: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    stored = str(payload.pop(key, ""))
    calculated = _canonical_sha256(payload)
    if stored != expected or calculated != expected:
        raise ValueError(
            f"{path.name} fingerprint mismatch: stored={stored}, calculated={calculated}, expected={expected}"
        )
    payload[key] = stored
    return payload


def protocol() -> dict[str, Any]:
    payload = _load_fingerprinted(PROTOCOL_PATH, "protocol_fingerprint", EXPECTED_PROTOCOL_FINGERPRINT)
    if payload["status"] != "predeclared_before_new_candidate_identity_or_focal_species_query":
        raise ValueError("provider-eligible protocol status drifted")
    if payload["parent_issue"] != 169:
        raise ValueError("provider-eligible parent issue drifted")
    if payload["trigger"]["coverage_contract_fingerprint"] != EXPECTED_COVERAGE_FINGERPRINT:
        raise ValueError("coverage contract fingerprint drifted in protocol")
    if payload["trigger"]["exclusion_provenance_fingerprint"] != EXPECTED_EXCLUSION_FINGERPRINT:
        raise ValueError("exclusion provenance fingerprint drifted in protocol")
    if any(
        payload["trigger"][key] is not False
        for key in (
            "new_candidate_identities_opened_before_protocol",
            "new_focal_species_historical_facets_opened_before_protocol",
            "new_heldout_outcomes_opened_before_protocol",
        )
    ):
        raise ValueError("new data were opened before preregistration")
    if payload["cohort"]["target_frames"] != 96:
        raise ValueError("target-frame count drifted")
    if payload["country_declaration"]["score_formula"] != "log1p(historical_selected_country_count)":
        raise ValueError("observability score drifted")
    if payload["country_declaration"]["score_cutoff_selected"] is not False:
        raise ValueError("score cutoff may not be selected")
    if payload["execution"]["pr_or_merge_may_open_heldout"] is not False:
        raise ValueError("preregistration PR may not open heldout outcomes")
    return payload


def execution_contract() -> dict[str, Any]:
    payload = _load_fingerprinted(
        EXECUTION_PATH, "execution_contract_fingerprint", EXPECTED_EXECUTION_FINGERPRINT
    )
    if payload["protocol_fingerprint"] != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("execution contract protocol fingerprint drifted")
    if payload["coverage_contract_fingerprint"] != EXPECTED_COVERAGE_FINGERPRINT:
        raise ValueError("execution contract coverage fingerprint drifted")
    if payload["exclusion_provenance_fingerprint"] != EXPECTED_EXCLUSION_FINGERPRINT:
        raise ValueError("execution contract exclusion fingerprint drifted")
    static = payload["static_preregistration"]
    if static["network_provider_calls_allowed"] is not False:
        raise ValueError("static preregistration may not call providers")
    if static["activation_marker_allowed"] is not False:
        raise ValueError("activation marker is forbidden in preregistration")
    first = payload["first_activation_workflow_contract"]
    if first["workflow_must_not_have_pull_request_trigger"] is not True:
        raise ValueError("first activation workflow must not consume run numbers on PR")
    if first["workflow_must_not_have_schedule_trigger"] is not True or first["no_cron_fallback"] is not True:
        raise ValueError("first activation workflow must not have scheduled fallback")
    if first["workflow_dispatch_allowed"] is not False:
        raise ValueError("first activation workflow_dispatch is forbidden")
    second = payload["second_activation_workflow_contract"]
    if second["workflow_must_not_have_pull_request_trigger"] is not True:
        raise ValueError("second activation workflow must not consume run numbers on PR")
    if second["workflow_must_not_have_schedule_trigger"] is not True:
        raise ValueError("second activation workflow must not be scheduled")
    return payload


def exclusion_provenance() -> dict[str, Any]:
    payload = _load_fingerprinted(
        EXCLUSION_PATH, "exclusion_provenance_fingerprint", EXPECTED_EXCLUSION_FINGERPRINT
    )
    if payload["source_file_count"] != 12 or len(payload["files"]) != 12:
        raise ValueError("exclusion source-file count drifted")
    if payload["network_access"] is not False:
        raise ValueError("exclusion inventory unexpectedly used network access")
    for forbidden_flag in (
        "fresh_candidate_identity_opened",
        "focal_species_historical_facet_opened",
        "heldout_2021_2025_opened",
        "aborted_163_partial_audit_replayed",
    ):
        if payload[forbidden_flag] is not False:
            raise ValueError(f"forbidden exclusion provenance flag: {forbidden_flag}")
    for item in payload["files"]:
        path = ROOT / str(item["path"])
        data = path.read_bytes()
        if len(data) != int(item["byte_count"]):
            raise ValueError(f"exclusion byte count drifted: {item['path']}")
        if hashlib.sha256(data).hexdigest() != str(item["sha256"]):
            raise ValueError(f"exclusion SHA256 drifted: {item['path']}")
        if _git_blob_sha(data) != str(item["git_blob_sha"]):
            raise ValueError(f"exclusion git-blob SHA drifted: {item['path']}")
    return payload


def validate_static_preregistration() -> dict[str, str]:
    cfg = protocol()
    execution = execution_contract()
    exclusions = exclusion_provenance()
    coverage = load_coverage_contract()
    if coverage["coverage_contract_fingerprint"] != EXPECTED_COVERAGE_FINGERPRINT:
        raise ValueError("frozen provider coverage fingerprint drifted")
    return {
        "protocol_fingerprint": cfg["protocol_fingerprint"],
        "execution_contract_fingerprint": execution["execution_contract_fingerprint"],
        "coverage_contract_fingerprint": coverage["coverage_contract_fingerprint"],
        "exclusion_provenance_fingerprint": exclusions["exclusion_provenance_fingerprint"],
    }


def identity_hash(seed: int, region: int, group: str, stratum: int, species_key: int) -> str:
    token = f"{int(seed)}|{int(region)}|{group}|{int(stratum)}|{int(species_key)}".encode("utf-8")
    return hashlib.sha256(token).hexdigest()


def observability_score(historical_selected_country_count: int) -> float:
    count = int(historical_selected_country_count)
    if count < 0:
        raise ValueError("historical selected-country count must be nonnegative")
    return float(math.log1p(count))


def provider_eligibility(selected_country_alpha2: str | None) -> tuple[bool, str | None, str]:
    if selected_country_alpha2 is None or not str(selected_country_alpha2).strip():
        return False, None, "preselection_ineligible_no_historical_country"
    alpha2 = str(selected_country_alpha2).strip().upper()
    alpha3 = alpha2_to_alpha3_if_supported(alpha2)
    if alpha3 is None:
        return False, None, "preselection_ineligible_provider_coverage"
    return True, alpha3, "provider_eligible_before_final_selection"


def select_final_eligible(
    candidates: Iterable[dict[str, Any]], *, region: int, group: str, stratum: int
) -> dict[str, Any]:
    """Pure offline final selection from a complete frozen eligibility snapshot."""
    cfg = protocol()
    eligible: list[dict[str, Any]] = []
    for raw in candidates:
        row = dict(raw)
        if int(row["region_cell_index"]) != int(region):
            continue
        if str(row["taxon_group"]) != str(group):
            continue
        if int(row["record_count_stratum"]) != int(stratum):
            continue
        if row.get("eligibility_status") != "provider_eligible_before_final_selection":
            continue
        if row.get("provider_eligible") is not True:
            continue
        key = int(row["speciesKey"])
        row["identity_selection_hash"] = identity_hash(
            int(cfg["cohort"]["selection_seed"]), int(region), str(group), int(stratum), key
        )
        eligible.append(row)
    if not eligible:
        raise ValueError(
            f"no provider-eligible candidate for region={region}, group={group}, stratum={stratum}"
        )
    eligible.sort(
        key=lambda row: (
            str(row["identity_selection_hash"]),
            int(row["speciesKey"]),
            str(row["scientific_name"]),
        )
    )
    return eligible[0]
