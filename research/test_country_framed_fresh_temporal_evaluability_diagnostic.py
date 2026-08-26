from __future__ import annotations

import json

from diagnose_country_framed_fresh_temporal_evaluability import (
    DIAGNOSTIC_COLUMNS,
    FORBIDDEN_OUTCOME_COLUMNS,
    ROOT,
    diagnose,
)


def test_diagnostic_surface_excludes_scientific_outcomes() -> None:
    assert FORBIDDEN_OUTCOME_COLUMNS.isdisjoint(DIAGNOSTIC_COLUMNS)


def test_terminal_temporal_evaluability_decomposition_is_frozen() -> None:
    payload = diagnose()
    summary = payload["summary"]

    assert summary["row_count"] == 48
    assert summary["unique_species_keys"] == 48
    assert summary["declaration_layer"] == {
        "status_counts": {"declared": 46, "country_declaration_failed": 2},
        "declared": 46,
        "failed": 2,
    }
    assert summary["candidate_layer"]["status_counts"] == {
        "generated": 40,
        "candidate_generation_failed": 6,
        "not_attempted_declaration_failed": 2,
    }
    assert summary["candidate_layer"]["generated"] == 40
    assert summary["candidate_layer"]["generated_fraction"] == 40 / 48

    temporal = summary["temporal_observation_layer"]
    assert temporal["status_counts"] == {
        "evaluated": 34,
        "zero_recent_country_records": 12,
        "not_attempted_no_declared_country": 2,
    }
    assert temporal["evaluated"] == 34
    assert temporal["evaluated_fraction_of_all_frozen_taxa"] == 34 / 48
    assert temporal["zero_recent_country_records"] == 12
    assert temporal["recent_provider_failed"] == 0

    joint = summary["joint_layer"]
    assert joint["candidate_generated_and_temporally_evaluated"] == 32
    assert joint["fraction_of_all_frozen_taxa"] == 32 / 48
    assert joint["candidate_generated_but_zero_recent_country_records"] == 8
    assert joint["candidate_generation_failed_but_temporally_evaluated"] == 2

    assert summary["by_taxon_group"]["plant"]["temporally_evaluated"] == 16
    assert summary["by_taxon_group"]["plant"]["joint_candidate_generated_and_temporally_evaluated"] == 15
    assert summary["by_taxon_group"]["animal"]["temporally_evaluated"] == 18
    assert summary["by_taxon_group"]["animal"]["joint_candidate_generated_and_temporally_evaluated"] == 17

    assert {k: v["temporally_evaluated"] for k, v in summary["by_geographic_stratum"].items()} == {
        "north": 10,
        "east": 7,
        "west": 10,
        "south": 7,
    }

    zero = summary["zero_recent_declared_taxa"]
    assert zero["count"] == 12
    assert zero["country_counts"] == {"RU": 1, "KP": 1, "LV": 1, "JP": 3, "CN": 3, "TW": 1, "VN": 2}
    assert zero["historical_training_rows_min"] == 0
    assert zero["historical_training_rows_median"] == 15.5
    assert zero["historical_training_rows_mean"] == 431 / 12
    assert zero["historical_training_rows_max"] == 123
    assert zero["three_largest_historical_training_row_counts"] == [123, 96, 84]

    assert payload["interpretation"]["generated_but_temporally_unevaluable_taxa"] == 8
    assert payload["interpretation"]["candidate_failed_but_temporally_observable_taxa"] == 2
    assert payload["guards"]["descriptive_post_outcome_only"] is True
    assert payload["guards"]["primary_decision_changed"] is False
    assert payload["guards"]["scientific_thresholds_tuned"] is False
    assert payload["guards"]["lift_columns_read"] is False
    assert payload["guards"]["new_eligibility_rule_created"] is False


def test_frozen_json_is_exact_regeneration() -> None:
    frozen = json.loads(
        (ROOT / "validation" / "acsp_country_framed_fresh_temporal_evaluability_diagnostic_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert diagnose() == frozen
