from __future__ import annotations

from pathlib import Path
import sys

import pytest

RESEARCH = Path(__file__).resolve().parents[1] / "research"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import preflight_cirsium_aza3_gbif_anchor_availability_v1 as mod


def test_taxon_match_provider_failure_is_indeterminate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mod,
        "gbif_taxon_match",
        lambda species: (_ for _ in ()).throw(RuntimeError("HTTP Error 429")),
    )
    result = mod.one_species("Cirsium example")
    assert result["preflight_regime"] == mod.PROVIDER_FAILURE_REGIME
    assert result["provider_status"] == "unavailable"
    assert result["primary_anchor_available"] == "indeterminate"
    assert result["legacy_precise_anchor_available"] == "indeterminate"
    assert result["gbif_taxon_match_classification"] == "PROVIDER_UNAVAILABLE"


def test_occurrence_provider_failure_never_becomes_anchor_absence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mod,
        "gbif_taxon_match",
        lambda species: {
            "classification": "AUTO_EXACT_ACCEPTED",
            "usage_key": "123",
        },
    )
    monkeypatch.setattr(
        mod,
        "has_eligible_precise_record",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP Error 429")),
    )
    result = mod.one_species("Cirsium example")
    assert result["preflight_regime"] == mod.PROVIDER_FAILURE_REGIME
    assert result["provider_status"] == "unavailable"
    assert result["primary_anchor_available"] == "indeterminate"
    assert result["legacy_precise_anchor_available"] == "indeterminate"
    assert result["recent_georeferenced_provider_count"] == 0


def test_successful_primary_anchor_remains_local_continuation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mod,
        "gbif_taxon_match",
        lambda species: {
            "classification": "AUTO_EXACT_ACCEPTED",
            "usage_key": "123",
        },
    )
    monkeypatch.setattr(
        mod,
        "has_eligible_precise_record",
        lambda *a, **k: (True, 3, 1, 8),
    )
    result = mod.one_species("Cirsium example")
    assert result["preflight_regime"] == "LOCAL_CONTINUATION_INPUT_AVAILABLE"
    assert result["provider_status"] == "ok"
    assert result["primary_anchor_available"] == "true"
