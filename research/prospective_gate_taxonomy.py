#!/usr/bin/env python3
"""Prospective-only ACSP gate taxonomy.

This module does not alter any existing frozen protocol or terminal decision.
It provides a small pure classifier for successor contracts that choose to
adopt the separately frozen supply/evaluability and hypothesis/effect axes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = ROOT / "validation" / "acsp_prospective_gate_taxonomy_v1.json"


def load_taxonomy() -> dict[str, object]:
    payload = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_id") != "acsp_prospective_gate_taxonomy_v1":
        raise ValueError("prospective gate taxonomy schema drifted")
    if payload.get("status") != "prospective_only_not_authoritative_for_existing_runs":
        raise ValueError("prospective gate taxonomy status drifted")
    history = payload["historical_boundary"]
    for key in (
        "rewrite_prior_terminal_decisions",
        "reclassify_prior_failures",
        "recompute_prior_evidence",
        "current_provider_eligible_v1_contract_changed",
        "current_or_prior_cohort_rescue_allowed",
    ):
        if history[key] is not False:
            raise ValueError(f"historical-boundary protection drifted: {key}")
    axes = payload["status_axes"]
    if axes["no_single_all_gates_label"] is not True:
        raise ValueError("successor contracts must preserve separate status axes")
    return payload


def _all_true(checks: Mapping[str, bool], required: list[str]) -> bool:
    missing = [name for name in required if name not in checks]
    if missing:
        raise ValueError(f"missing gate checks: {missing}")
    return all(bool(checks[name]) for name in required)


def classify_successor(
    *,
    family: str,
    gate_checks: Mapping[str, bool],
    protocol_abort: bool = False,
) -> dict[str, object]:
    """Classify a *future* contract that has explicitly adopted this schema."""
    taxonomy = load_taxonomy()
    if family not in (
        "country_framed_candidate_patch_confirmation",
        "provider_eligible_observability_successor",
    ):
        raise ValueError(f"unknown prospective gate family: {family}")

    cfg = taxonomy[family]
    supply_required = list(cfg["supply_gates"])
    hypothesis_required = list(cfg["hypothesis_gates"])

    if protocol_abort:
        return {
            "supply_status": "protocol_abort",
            "hypothesis_status": "unavailable",
            "promotion_status": "not_promoted",
        }

    supply_supported = _all_true(gate_checks, supply_required)
    if not supply_supported:
        return {
            "supply_status": "insufficient",
            "hypothesis_status": "unavailable",
            "promotion_status": "not_promoted",
        }

    hypothesis_supported = _all_true(gate_checks, hypothesis_required)
    return {
        "supply_status": "sufficient",
        "hypothesis_status": "supported" if hypothesis_supported else "not_supported",
        "promotion_status": "promoted" if hypothesis_supported else "not_promoted",
    }
