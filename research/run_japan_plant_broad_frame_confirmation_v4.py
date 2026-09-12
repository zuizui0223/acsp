#!/usr/bin/env python3
"""Evaluate issue #203 only after the exact v4 pre-heldout object is frozen.

Execution is deliberately two phase:
1. verify the complete historical-only 24-taxon preflight and reconstruct every
   BROAD/LOCAL candidate universe byte-semantically from 2000-2020 evidence;
2. only after all 24 reconstructions pass, open 2021-2025 once per frozen taxon
   and evaluate candidate-universe reachability.

This tests candidate-universe adequacy, not selector superiority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable

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

PROTOCOL_PATH = ROOT / "validation" / "japan_plant_broad_frame_confirmation_v4.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise RuntimeError(
            f"PREOUTCOME_FINGERPRINT_DRIFT:{message}: expected={expected!r} actual={actual!r}"
        )


def _all_region_ids() -> list[str]:
    return [str(row[0]) for row in VALIDATED_JAPAN_REGIONS]


def _adapt_contract(protocol: dict[str, Any]) -> dict[str, Any]:
    """Expose the frozen v4 protocol through the generic reconstruction interface."""
    stage = protocol["stage2_historical_qualification"]
    return {
        "historical_evidence": {
            "country": str(stage["country"]),
            "period": [int(stage["period"][0]), int(stage["period"][1])],
            "coordinate_uncertainty_m_max": float(stage["coordinate_uncertainty_m_max"]),
        },
        "candidate_universes": dict(protocol["candidate_universes"]),
        "outcome": dict(protocol["outcome"]),
        "primary_endpoint": dict(protocol["primary_endpoint"]),
    }


def verify_preoutcome_preflight(preflight_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    protocol = _load_json(PROTOCOL_PATH)
    preflight = _load_json(preflight_path)

    _assert_equal(protocol.get("protocol_id"), "japan_plant_broad_frame_confirmation_v4", "protocol id")
    _assert_equal(
        protocol.get("status"),
        "FROZEN_BEFORE_IDENTITY_CANDIDATE_SELECTION_OR_FOCAL_HISTORICAL_QUERY",
        "protocol freeze status",
    )
    _assert_equal(
        preflight.get("status"),
        "PREOUTCOME_24_TAXA_AND_CANDIDATE_UNIVERSES_FROZEN",
        "preflight status",
    )
    _assert_equal(preflight.get("candidate_identity_count"), 96, "candidate identity count")
    _assert_equal(preflight.get("final_taxa"), 24, "final taxon count")
    _assert_equal(preflight.get("heldout_2021_2025_opened"), False, "heldout boundary")
    _assert_equal(preflight.get("selector_evaluated"), False, "selector boundary")
    _assert_equal(preflight.get("validated_japan_product_changed"), False, "Japan core boundary")
    _assert_equal(preflight.get("automatic_global_adapter_changed"), False, "global adapter boundary")

    selected = list(preflight.get("selected_taxa") or [])
    _assert_equal(len(selected), 24, "selected rows")
    keys = [int(row["speciesKey"]) for row in selected]
    names = [str(row["scientific_name"]) for row in selected]
    _assert_equal(len(set(keys)), 24, "unique speciesKey")
    _assert_equal(len(set(names)), 24, "unique scientific names")

    required_lanes = {"BROAD_LAND", "LOCAL_2KM_LAND", "LOCAL_5KM_LAND", "LOCAL_10KM_LAND"}
    minimum = int(protocol["stage2_historical_qualification"]["minimum_historical_population_clusters_in_selected_region"])
    for row in selected:
        if int(row["historical_population_count"]) < minimum:
            raise RuntimeError("PREOUTCOME_FINGERPRINT_DRIFT:historical qualification")
        _assert_equal(set(row["candidate_universes"]), required_lanes, f"{row['speciesKey']} lanes")

    canonical = [
        {
            "speciesKey": int(row["speciesKey"]),
            "scientific_name": str(row["scientific_name"]),
            "selected_region": str(row["selected_region"]["region_id"]),
            "historical_evidence_sha256": str(row["historical_evidence_sha256"]),
            "population_anchor_sha256": str(row["population_anchor_sha256"]),
            "candidate_universes": row["candidate_universes"],
        }
        for row in selected
    ]
    _assert_equal(_canonical_sha(canonical), str(preflight["final_selection_sha256"]), "final selection hash")
    return protocol, preflight


def reconstruct_all_states(
    protocol: dict[str, Any],
    preflight: dict[str, Any],
    *,
    reconstructor: Callable[..., FrozenUnitState] = reconstruct_frozen_unit,
) -> tuple[dict[int, FrozenUnitState], dict[int, dict[str, Any]]]:
    """Reconstruct and verify every frozen taxon before any recent fetch."""
    contract = _adapt_contract(protocol)
    states: dict[int, FrozenUnitState] = {}
    frozen_rows: dict[int, dict[str, Any]] = {}

    for row in preflight["selected_taxa"]:
        key = int(row["speciesKey"])
        unit_id = f"JPB4_{key}"
        preflight_unit = {
            "status": "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN",
            "selected_region": row["selected_region"],
            "historical_evidence_sha256": str(row["historical_evidence_sha256"]),
            "population_anchor_sha256": str(row["population_anchor_sha256"]),
            "worldcover_point_audit": row["worldcover_point_audit"],
            "candidate_universes": row["candidate_universes"],
        }
        gate_unit = {
            "recent_fetch_authorized": True,
            "species": str(row["scientific_name"]),
            "selected_region": str(row["selected_region"]["region_id"]),
            "historical_evidence_sha256": str(row["historical_evidence_sha256"]),
            "population_anchor_sha256": str(row["population_anchor_sha256"]),
            "worldcover_sample_sha256": str(row["worldcover_point_audit"]["sample_classification_sha256"]),
        }
        unit = {
            "unit_id": unit_id,
            "species": str(row["scientific_name"]),
            "allowed_fixed_regions": _all_region_ids(),
        }
        states[key] = reconstructor(
            unit,
            contract=contract,
            preflight_unit=preflight_unit,
            gate_unit=gate_unit,
        )
        frozen_rows[key] = row

    _assert_equal(len(states), 24, "fully reconstructed taxon count")
    return states, frozen_rows


def _aggregate(
    identity_results: list[dict[str, Any]],
    metrics: pd.DataFrame,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    endpoint = protocol["primary_endpoint"]
    evaluable_keys = {
        int(row["speciesKey"])
        for row in identity_results
        if row["status"] == "TEMPORALLY_EVALUABLE"
    }
    primary_radius = float(protocol["outcome"]["primary_recovery_radius_km"])
    primary = metrics.loc[
        np.isclose(pd.to_numeric(metrics.get("recovery_radius_km"), errors="coerce"), primary_radius)
    ].copy() if not metrics.empty else pd.DataFrame()

    positive = 0
    broad_recovered = 0
    local5_recovered = 0
    novel_total = 0
    taxon_contrasts: list[dict[str, Any]] = []
    for key in sorted(evaluable_keys):
        sub = primary.loc[pd.to_numeric(primary["speciesKey"], errors="coerce").eq(key)]
        by_lane = sub.set_index("lane_id")
        if "BROAD_LAND" not in by_lane.index or "LOCAL_5KM_LAND" not in by_lane.index:
            raise RuntimeError(f"missing primary lane metrics for speciesKey={key}")
        b_recall = float(by_lane.loc["BROAD_LAND", "recall"])
        l_recall = float(by_lane.loc["LOCAL_5KM_LAND", "recall"])
        contrast = b_recall - l_recall
        if contrast > 0.0:
            positive += 1
        b_rec = int(by_lane.loc["BROAD_LAND", "recovered_novel_populations"])
        l_rec = int(by_lane.loc["LOCAL_5KM_LAND", "recovered_novel_populations"])
        n = int(by_lane.loc["BROAD_LAND", "novel_population_count"])
        broad_recovered += b_rec
        local5_recovered += l_rec
        novel_total += n
        taxon_contrasts.append({
            "speciesKey": key,
            "broad_recall": b_recall,
            "local5_recall": l_recall,
            "broad_minus_local5": contrast,
            "novel_population_count": n,
        })

    evaluable_n = len(evaluable_keys)
    positive_fraction = float(positive / evaluable_n) if evaluable_n else 0.0
    added = float((broad_recovered - local5_recovered) / novel_total) if novel_total else 0.0
    gate_evaluable = evaluable_n >= int(endpoint["minimum_temporally_evaluable_taxa"])
    gate_positive = positive_fraction >= float(endpoint["minimum_fraction_evaluable_taxa_with_strictly_positive_difference"])
    gate_added = added >= float(endpoint["minimum_cluster_weighted_added_recall"])
    passed = bool(gate_evaluable and gate_positive and gate_added)
    return {
        "frozen_taxa": 24,
        "temporally_evaluable_taxa": evaluable_n,
        "positive_taxa": int(positive),
        "positive_fraction": positive_fraction,
        "novel_population_clusters_primary_denominator": int(novel_total),
        "broad_recovered_clusters_at_1km": int(broad_recovered),
        "local5_recovered_clusters_at_1km": int(local5_recovered),
        "cluster_weighted_broad_minus_local5_added_recall": added,
        "minimum_temporally_evaluable_taxa": int(endpoint["minimum_temporally_evaluable_taxa"]),
        "minimum_positive_fraction": float(endpoint["minimum_fraction_evaluable_taxa_with_strictly_positive_difference"]),
        "minimum_cluster_weighted_added_recall": float(endpoint["minimum_cluster_weighted_added_recall"]),
        "evaluable_gate_passed": gate_evaluable,
        "positive_fraction_gate_passed": gate_positive,
        "cluster_weighted_added_recall_gate_passed": gate_added,
        "all_preregistered_gates_passed": passed,
        "taxon_contrasts": taxon_contrasts,
    }


def run(
    preflight_path: Path,
    *,
    reconstructor: Callable[..., FrozenUnitState] = reconstruct_frozen_unit,
    scorer: Callable[..., tuple[dict[str, Any], list[dict[str, Any]]]] = fetch_and_score_recent_unit,
) -> tuple[dict[str, Any], pd.DataFrame]:
    protocol, preflight = verify_preoutcome_preflight(preflight_path)

    # Phase 1 must finish for all 24 taxa before the first scorer/provider call.
    states, frozen_rows = reconstruct_all_states(
        protocol, preflight, reconstructor=reconstructor
    )
    contract = _adapt_contract(protocol)

    # Phase 2: only now may 2021-2025 be opened.
    identity_results: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    for key in sorted(states):
        result, rows = scorer(states[key], contract=contract)
        result = dict(result)
        result["speciesKey"] = int(key)
        result["scientific_name"] = str(frozen_rows[key]["scientific_name"])
        recent_audit = result.get("recent_provider_audit") or {}
        if recent_audit:
            _assert_equal(
                int(recent_audit["matched_usage_key"]), int(key), f"{key} heldout provider identity"
            )
        identity_results.append(result)
        for row in rows:
            metric_rows.append({
                "speciesKey": int(key),
                "scientific_name": str(frozen_rows[key]["scientific_name"]),
                **row,
            })

    metrics = pd.DataFrame(metric_rows)
    primary = _aggregate(identity_results, metrics, protocol)
    summary = {
        "schema_version": "japan-plant-broad-frame-confirmation-result-v4",
        "status": "JAPAN_PLANT_BROAD_FRAME_CONFIRMATION_COMPLETE",
        "source_preflight_sha256": _sha256(preflight_path),
        "protocol_sha256": _sha256(PROTOCOL_PATH),
        "validated_japan_product_changed": False,
        "automatic_global_adapter_changed": False,
        "selector_evaluated": False,
        "human_access_used": False,
        "primary": primary,
        "decision": (
            "BROAD_FRAME_HYPOTHESIS_CONFIRMED"
            if primary["all_preregistered_gates_passed"]
            else "PREREGISTERED_BROAD_FRAME_GATE_FAILED"
        ),
        "identity_results": identity_results,
        "claim_boundary": (
            "Candidate-universe adequacy among historically qualified Japanese plants only; "
            "BROAD is a superset of LOCAL, so this is not selector superiority, occupancy "
            "probability, exact-site prediction, or field-efficiency validation."
        ),
    }
    return summary, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    summary, metrics = run(args.preflight)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metrics.to_csv(args.out_dir / "ceiling_metrics.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
