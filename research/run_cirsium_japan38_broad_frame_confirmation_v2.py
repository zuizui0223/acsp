#!/usr/bin/env python3
"""Run the frozen Japan38 BROAD-vs-LOCAL candidate-frame confirmation v2.

Two-phase boundary:
1) verify the exact historical-only preflight artifact, provider-identity amendment,
   and reconstruct every canonical constructible candidate universe;
2) only after all phase-1 checks pass, fetch 2021-2025 outcomes once per unique
   GBIF provider identity and evaluate full-frame reachability.

Paper taxon concepts remain in the audit ledger, but concepts resolving to the
same GBIF usageKey are not counted as independent primary replicates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.taxon_patches import VALIDATED_JAPAN_REGIONS
from run_cirsium_disjoint_broad_frame_replication_v1 import (
    FrozenUnitState,
    fetch_and_score_recent_unit,
    reconstruct_frozen_unit,
)

CONTRACT_PATH = ROOT / "validation" / "cirsium_japan38_broad_frame_confirmation_v2.json"
ROSTER_PATH = ROOT / "validation" / "cirsium_japan38_disjoint_v2_roster.csv"
AMENDMENT_PATH = ROOT / "validation" / "cirsium_japan38_provider_identity_amendment_v2.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise RuntimeError(f"PREOUTCOME_FINGERPRINT_DRIFT:{message}: expected={expected!r} actual={actual!r}")


def _included_roster() -> pd.DataFrame:
    roster = pd.read_csv(ROSTER_PATH, dtype=str).fillna("")
    flag = roster["include_v2"].str.lower().eq("true")
    included = roster.loc[flag].copy().reset_index(drop=True)
    if len(included) != 31 or included["member_id"].nunique() != 31:
        raise RuntimeError("frozen Japan38 v2 roster must contain exactly 31 included paper concepts")
    return included


def verify_preoutcome_documents(preflight_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], pd.DataFrame]:
    contract = _load_json(CONTRACT_PATH)
    amendment = _load_json(AMENDMENT_PATH)
    preflight = _load_json(preflight_path)
    roster = _included_roster()

    _assert_equal(contract.get("status"), "FROZEN_BEFORE_2021_2025_OUTCOME_FETCH", "contract status")
    _assert_equal(amendment.get("status"), "FROZEN_AFTER_HISTORICAL_PREFLIGHT_BEFORE_2021_2025_OUTCOME_OPENING", "amendment status")
    _assert_equal(amendment.get("recent_outcomes_opened_before_amendment"), False, "amendment recent boundary")
    _assert_equal(preflight.get("recent_outcomes_fetched"), False, "preflight recent boundary")
    _assert_equal(preflight.get("declared_taxa"), 31, "preflight declared concepts")
    _assert_equal(preflight.get("units_frozen"), 13, "constructible concept rows")
    _assert_equal(preflight.get("units_no_historical_anchor"), 14, "no-anchor concept rows")
    _assert_equal(preflight.get("units_provider_failure"), 4, "provider-failure concept rows")
    _assert_equal(_sha256(preflight_path), amendment["source_preflight"]["preflight_result_sha256"], "preflight file SHA256")

    rows = {str(row["unit_id"]): row for row in preflight["units"]}
    _assert_equal(set(rows), set(roster["member_id"].astype(str)), "preflight/roster concept IDs")

    resolved_groups: dict[int, list[str]] = {}
    for member_id, row in rows.items():
        audit = row.get("gbif_historical_audit") or {}
        usage = audit.get("matched_usage_key")
        if usage is not None:
            resolved_groups.setdefault(int(usage), []).append(member_id)
    duplicate = {key: sorted(value) for key, value in resolved_groups.items() if len(value) > 1}
    _assert_equal(duplicate, {3113139: ["JPN_20", "JPN_21", "JPN_35"]}, "provider identity duplicate groups")

    constructible = [row for row in rows.values() if row.get("status") == "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN"]
    constructible_keys = {int((row.get("gbif_historical_audit") or {})["matched_usage_key"]) for row in constructible}
    _assert_equal(len(constructible_keys), 11, "unique constructible provider identities")

    declared = amendment["constructible_provider_identities"]
    declared_keys = {int(row["matched_usage_key"]) for row in declared}
    _assert_equal(constructible_keys, declared_keys, "amendment constructible provider identities")
    return contract, amendment, preflight, roster


def _all_region_ids() -> list[str]:
    return [str(row[0]) for row in VALIDATED_JAPAN_REGIONS]


def reconstruct_all_canonical_states(
    contract: dict[str, Any],
    amendment: dict[str, Any],
    preflight: dict[str, Any],
    roster: pd.DataFrame,
) -> tuple[dict[int, FrozenUnitState], dict[int, str], dict[str, dict[str, Any]]]:
    """Reconstruct all 11 canonical provider identities before any recent fetch."""
    preflight_rows = {str(row["unit_id"]): row for row in preflight["units"]}
    roster_rows = roster.set_index("member_id").to_dict(orient="index")
    states: dict[int, FrozenUnitState] = {}
    canonical_members: dict[int, str] = {}

    for declaration in amendment["constructible_provider_identities"]:
        usage_key = int(declaration["matched_usage_key"])
        member_id = str(declaration["canonical_member_id"])
        frozen = preflight_rows[member_id]
        species = str(roster_rows[member_id]["provider_query_name"])
        audit = frozen.get("gbif_historical_audit") or {}
        _assert_equal(int(audit.get("matched_usage_key")), usage_key, f"{member_id} provider usageKey")
        _assert_equal(frozen.get("status"), "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN", f"{member_id} constructible status")

        unit = {
            "unit_id": member_id,
            "species": species,
            "allowed_fixed_regions": _all_region_ids(),
        }
        gate_unit = {
            "recent_fetch_authorized": True,
            "species": species,
            "selected_region": str(frozen["selected_region"]["region_id"]),
            "historical_evidence_sha256": str(frozen["historical_evidence_sha256"]),
            "population_anchor_sha256": str(frozen["population_anchor_sha256"]),
            "worldcover_sample_sha256": str(frozen["worldcover_point_audit"]["sample_classification_sha256"]),
        }
        state = reconstruct_frozen_unit(
            unit,
            contract=contract,
            preflight_unit=frozen,
            gate_unit=gate_unit,
        )
        states[usage_key] = state
        canonical_members[usage_key] = member_id

    _assert_equal(len(states), 11, "reconstructed unique provider identities")
    return states, canonical_members, preflight_rows


def _primary_aggregate(identity_results: list[dict[str, Any]], metrics: pd.DataFrame, contract: dict[str, Any]) -> dict[str, Any]:
    endpoint = contract["primary_endpoint"]
    evaluable = [row for row in identity_results if row["status"] == "TEMPORALLY_EVALUABLE"]
    positives = [row for row in evaluable if bool(row.get("primary_positive"))]
    evaluable_n = len(evaluable)
    positive_fraction = float(len(positives) / evaluable_n) if evaluable_n else 0.0

    primary_radius = float(contract["outcome"]["primary_recovery_radius_km"])
    primary_metrics = metrics.loc[np.isclose(pd.to_numeric(metrics["recovery_radius_km"], errors="coerce"), primary_radius)].copy() if not metrics.empty else pd.DataFrame()
    broad = primary_metrics.loc[primary_metrics["lane_id"].eq("BROAD_LAND")]
    local5 = primary_metrics.loc[primary_metrics["lane_id"].eq("LOCAL_5KM_LAND")]
    broad_recovered = int(pd.to_numeric(broad["recovered_novel_populations"], errors="coerce").fillna(0).sum()) if not broad.empty else 0
    local5_recovered = int(pd.to_numeric(local5["recovered_novel_populations"], errors="coerce").fillna(0).sum()) if not local5.empty else 0
    novel_total = int(pd.to_numeric(broad["novel_population_count"], errors="coerce").fillna(0).sum()) if not broad.empty else 0
    cluster_weighted_added = float((broad_recovered - local5_recovered) / novel_total) if novel_total else 0.0

    gate_evaluable = evaluable_n >= int(endpoint["minimum_temporally_evaluable_taxa"])
    gate_positive = positive_fraction >= float(endpoint["minimum_fraction_evaluable_taxa_with_strictly_positive_difference"])
    gate_added = cluster_weighted_added >= float(endpoint["minimum_cluster_weighted_added_recall"])
    passed = bool(gate_evaluable and gate_positive and gate_added)
    return {
        "unique_constructible_provider_identities": 11,
        "temporally_evaluable_provider_identities": evaluable_n,
        "positive_provider_identities": int(len(positives)),
        "positive_fraction": positive_fraction,
        "novel_population_clusters_primary_denominator": novel_total,
        "broad_recovered_clusters_at_1km": broad_recovered,
        "local5_recovered_clusters_at_1km": local5_recovered,
        "cluster_weighted_broad_minus_local5_added_recall": cluster_weighted_added,
        "minimum_temporally_evaluable_provider_identities": int(endpoint["minimum_temporally_evaluable_taxa"]),
        "minimum_positive_fraction": float(endpoint["minimum_fraction_evaluable_taxa_with_strictly_positive_difference"]),
        "minimum_cluster_weighted_added_recall": float(endpoint["minimum_cluster_weighted_added_recall"]),
        "evaluable_gate_passed": gate_evaluable,
        "positive_fraction_gate_passed": gate_positive,
        "cluster_weighted_added_recall_gate_passed": gate_added,
        "all_preregistered_gates_passed": passed,
    }


def run(preflight_path: Path) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    contract, amendment, preflight, roster = verify_preoutcome_documents(preflight_path)

    # PHASE 1: live reconstruction and all hashes for every canonical identity.
    # No 2021-2025 provider call can occur before this function returns.
    states, canonical_members, preflight_rows = reconstruct_all_canonical_states(contract, amendment, preflight, roster)

    # PHASE 2: open heldout exactly once per unique provider identity.
    identity_results: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    for usage_key in sorted(states):
        state = states[usage_key]
        result, rows = fetch_and_score_recent_unit(state, contract=contract)
        result = dict(result)
        result["matched_usage_key"] = int(usage_key)
        result["canonical_member_id"] = canonical_members[usage_key]
        recent_audit = result.get("recent_provider_audit") or {}
        if recent_audit:
            _assert_equal(int(recent_audit.get("matched_usage_key")), int(usage_key), f"{canonical_members[usage_key]} recent provider usageKey")
        identity_results.append(result)
        for row in rows:
            metric_rows.append({"matched_usage_key": int(usage_key), "canonical_member_id": canonical_members[usage_key], **row})

    metrics = pd.DataFrame(metric_rows)
    primary = _primary_aggregate(identity_results, metrics, contract)

    # Secondary concept ledger: all 31 declared concepts remain visible, but aliases
    # never add an independent primary replicate.
    usage_to_result = {int(row["matched_usage_key"]): row for row in identity_results}
    canonical_for_usage = {int(row["matched_usage_key"]): str(row["canonical_member_id"]) for row in amendment["constructible_provider_identities"]}
    concept_rows: list[dict[str, Any]] = []
    for frozen in preflight["units"]:
        member_id = str(frozen["unit_id"])
        audit = frozen.get("gbif_historical_audit") or {}
        usage = audit.get("matched_usage_key")
        base = {
            "member_id": member_id,
            "requested_name": str(frozen["species"]),
            "preflight_status": str(frozen["status"]),
            "matched_usage_key": "" if usage is None else int(usage),
            "matched_scientific_name": str(audit.get("matched_scientific_name") or ""),
            "primary_provider_identity_unit": False,
            "canonical_member_id": "",
            "outcome_status": "NOT_FETCHED_NONCONSTRUCTIBLE",
        }
        if usage is not None and int(usage) in usage_to_result:
            canonical = canonical_for_usage[int(usage)]
            result = usage_to_result[int(usage)]
            base["canonical_member_id"] = canonical
            base["primary_provider_identity_unit"] = member_id == canonical
            base["outcome_status"] = str(result["status"]) if member_id == canonical else f"ALIAS_OF_{canonical}"
        concept_rows.append(base)
    concept_ledger = pd.DataFrame(concept_rows)

    summary = {
        "schema_version": "cirsium-japan38-broad-frame-confirmation-result-v2",
        "status": "JAPAN38_BROAD_FRAME_CONFIRMATION_COMPLETE",
        "source_contract": str(CONTRACT_PATH.relative_to(ROOT)),
        "provider_identity_amendment": str(AMENDMENT_PATH.relative_to(ROOT)),
        "source_preflight_result_sha256": _sha256(preflight_path),
        "validated_japan_product_changed": False,
        "automatic_global_adapter_changed": False,
        "selector_evaluated": False,
        "human_access_used": False,
        "declared_paper_concepts": 31,
        "preflight_constructible_concept_rows": 13,
        "preflight_no_historical_anchor_concept_rows": 14,
        "preflight_provider_failure_concept_rows": 4,
        "provider_identity_policy": "unique GBIF matched_usage_key; shared paper-concept aliases count once",
        "primary": primary,
        "decision": "BROAD_FRAME_HYPOTHESIS_CONFIRMED" if primary["all_preregistered_gates_passed"] else "PREREGISTERED_BROAD_FRAME_GATE_FAILED",
        "identity_results": identity_results,
        "claim_boundary": "Full-frame reachability tests candidate-universe adequacy only. It is not selector superiority, occupancy probability, field efficiency, or exact-site prediction. Any selector test requires a new disjoint cohort."
    }
    return summary, metrics, concept_ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    summary, metrics, concepts = run(args.preflight)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metrics.to_csv(args.out_dir / "ceiling_metrics.csv", index=False)
    concepts.to_csv(args.out_dir / "concept_ledger.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
