from __future__ import annotations

import json

from develop_country_frame_observability_score import (
    FORBIDDEN_OUTCOME_COLUMNS,
    PREDECLARED_COLUMNS,
    RESULT_COLUMNS,
    ROOT,
    develop,
)


def test_score_surface_is_preheldout_and_outcome_blind() -> None:
    assert FORBIDDEN_OUTCOME_COLUMNS.isdisjoint(PREDECLARED_COLUMNS)
    assert FORBIDDEN_OUTCOME_COLUMNS.isdisjoint(RESULT_COLUMNS)
    payload = develop()
    assert payload["score_definition"]["formula"] == "log1p(historical_selected_country_count)"
    assert payload["score_definition"]["threshold_selected"] is False
    assert payload["source"]["fresh_terminal_audit_used_for_score_development"] is False
    assert payload["guards"]["fresh_48_used_to_fit_or_select_score"] is False
    assert payload["guards"]["candidate_generation_outcomes_read"] is False
    assert payload["guards"]["lift_outcomes_read"] is False
    assert payload["guards"]["scientific_threshold_selected"] is False


def test_development_result_is_frozen() -> None:
    payload = develop()
    endpoint = payload["temporal_endpoint"]
    primary = payload["primary_development_result"]
    comparator = payload["negative_comparator"]

    assert payload["source"]["development_taxa"] == 48
    assert payload["source"]["unique_development_taxa"] == 48
    assert endpoint["temporally_evaluated"] == 37
    assert endpoint["zero_recent_country_records"] == 11
    assert endpoint["temporally_evaluable_fraction"] == 37 / 48

    assert primary["observability_score_auc"] == 0.7923832923832924
    assert primary["bootstrap"] == {
        "requested_replicates": 10000,
        "valid_replicates": 10000,
        "seed": 20260827,
        "mean_auc": 0.7905048482811496,
        "median_auc": 0.7960687960687961,
        "ci95_lower": 0.6241697191697192,
        "ci95_upper": 0.925,
        "fraction_auc_le_0_5": 0.0012,
    }
    assert primary["evaluated_historical_country_count"]["median"] == 102.0
    assert primary["zero_recent_historical_country_count"]["median"] == 14.0

    assert comparator["auc"] == 0.5442260442260443
    assert comparator["observability_score_minus_comparator_auc"] == 0.24815724815724816

    assert payload["secondary"]["by_development_cohort"]["v1"]["observability_score_auc"] == 0.7894736842105263
    assert payload["secondary"]["by_development_cohort"]["v1_1"]["observability_score_auc"] == 0.8101851851851852
    assert payload["secondary"]["by_taxon_group"]["plant"]["observability_score_auc"] == 0.7947368421052632
    assert payload["secondary"]["by_taxon_group"]["animal"]["observability_score_auc"] == 0.7638888888888888

    assert payload["guards"]["completed_seven_gate_decision_changed"] is False
    assert payload["guards"]["development_result_is_confirmation"] is False
    assert payload["guards"]["future_confirmation_requires_genuinely_fresh_identities"] is True


def test_frozen_json_is_exact_regeneration() -> None:
    frozen = json.loads(
        (ROOT / "validation" / "acsp_country_frame_observability_score_development_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert develop() == frozen
