from __future__ import annotations

import research.diagnose_cirsium_fresh_sentinel_v2_worldcover_required_cogs as mod


def _probe_factory(mapping):
    def probe(url, *, timeout_seconds, max_attempts):
        cog = url.split("_v200_")[1].split("_Map.tif")[0]
        status = mapping[cog]
        return {
            "http_status": status,
            "classification": mod._classify_http_status(status),
            "attempts": 1,
            "error_class": "",
            "error_message": "",
        }
    return probe


def test_http_status_classification() -> None:
    assert mod._classify_http_status(200) == "OBJECT_ACCESSIBLE"
    assert mod._classify_http_status(206) == "OBJECT_ACCESSIBLE"
    assert mod._classify_http_status(404) == "OBJECT_NOT_PUBLISHED_AT_FROZEN_URL"
    assert mod._classify_http_status(403) == "OBJECT_ACCESS_DENIED_OR_UNAVAILABLE"
    assert mod._classify_http_status(429) == "TRANSIENT_PROVIDER_FAILURE"
    assert mod._classify_http_status(503) == "TRANSIENT_PROVIDER_FAILURE"
    assert mod._classify_http_status(418) == "OTHER_PROVIDER_HTTP_ERROR"


def test_diagnostic_uses_exact_frozen_four_cogs(monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "_load_contracts",
        lambda: (
            {
                "diagnostic_request": {
                    "timeout_seconds": 30,
                    "max_attempts": 3,
                }
            },
            {},
        ),
    )
    result = mod.diagnose_required_cogs(
        probe=_probe_factory({
            "N24E141": 206,
            "N24E153": 404,
            "N27E138": 206,
            "N27E141": 404,
        })
    )
    assert result["required_cog_ids"] == ["N24E141", "N24E153", "N27E138", "N27E141"]
    assert result["classification_counts"] == {
        "OBJECT_ACCESSIBLE": 2,
        "OBJECT_NOT_PUBLISHED_AT_FROZEN_URL": 2,
    }
    assert result["full_cog_downloaded"] is False
    assert result["worldcover_class_read"] is False
    assert result["candidate_membership_changed"] is False
    assert result["alternate_provider_used"] is False
    assert result["prospective_field_outcomes_opened"] is False
    assert result["diagnostic_can_authorize_ecological_screening"] is False
    assert "source-indeterminate" in result["next_gate"]


def test_transient_failure_stops_source_decision(monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "_load_contracts",
        lambda: (
            {
                "diagnostic_request": {
                    "timeout_seconds": 30,
                    "max_attempts": 3,
                }
            },
            {},
        ),
    )
    result = mod.diagnose_required_cogs(
        probe=_probe_factory({
            "N24E141": 206,
            "N24E153": 503,
            "N27E138": 206,
            "N27E141": 206,
        })
    )
    assert result["classification_counts"]["TRANSIENT_PROVIDER_FAILURE"] == 1
    assert "repeat only the same frozen source diagnostic" in result["next_gate"]
