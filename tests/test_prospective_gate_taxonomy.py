from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_prospective_gate_taxonomy_preserves_history_and_two_axes() -> None:
    payload = json.loads(
        (ROOT / "validation" / "acsp_prospective_gate_taxonomy_v1.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "prospective_only_not_authoritative_for_existing_runs"
    history = payload["historical_boundary"]
    assert history["rewrite_prior_terminal_decisions"] is False
    assert history["reclassify_prior_failures"] is False
    assert history["recompute_prior_evidence"] is False
    assert history["current_provider_eligible_v1_contract_changed"] is False
    assert payload["status_axes"]["no_single_all_gates_label"] is True
    assert len(payload["country_framed_candidate_patch_confirmation"]["supply_gates"]) == 3
    assert len(payload["country_framed_candidate_patch_confirmation"]["hypothesis_gates"]) == 4
    assert len(payload["provider_eligible_observability_successor"]["supply_gates"]) == 5
    assert len(payload["provider_eligible_observability_successor"]["hypothesis_gates"]) == 2
