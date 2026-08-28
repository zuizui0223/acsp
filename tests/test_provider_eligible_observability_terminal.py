from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TERMINAL = ROOT / "validation" / "acsp_provider_eligible_observability_first_activation_terminal_v1.json"


def test_provider_eligible_first_activation_is_supply_abort_not_hypothesis_negative() -> None:
    record = json.loads(TERMINAL.read_text(encoding="utf-8"))
    run = record["authoritative_run"]
    observed = record["observed_execution"]
    original = record["original_terminal_status"]
    axes = record["two_axis_description"]
    claim = record["claim_boundary"]

    assert run["workflow_run_id"] == 33031292325
    assert run["workflow_run_number"] == 1
    assert run["terminal_stage"] == 2
    assert observed["historical_unique_species_queries"] == 3161
    assert observed["historical_provider_success_count"] + observed["historical_provider_error_count"] == 3161
    assert observed["historical_provider_error_count"] == 29
    assert observed["complete_authoritative_96_frame_artifact_created"] is False
    assert observed["heldout_2021_2025_opened"] is False
    assert observed["recall_or_lift_read"] is False

    assert original["status"] == "abort_not_evaluable"
    assert original["second_activation_after_abort_allowed"] is False
    assert original["new_seed_or_replacement_after_abort_allowed"] is False
    assert axes["historical_status_reclassified"] is False
    assert axes["supply_status"] == "protocol_abort"
    assert axes["hypothesis_status"] == "unavailable"
    assert axes["promotion_status"] == "not_promoted"
    assert claim["technical_abort_is_scientific_negative"] is False
    assert claim["validated_japan_product_changed"] is False
    assert claim["country_framed_or_global_product_promoted"] is False
    assert claim["current_publication_route"] == "Ecological Informatics"
