from __future__ import annotations

import pytest

from acsp.local_discovery_gates import LocalDiscoveryEvidence, classify_local_discovery_problem


def test_taxonomy_gate_precedes_geometry() -> None:
    result = classify_local_discovery_problem(
        LocalDiscoveryEvidence(
            taxon_match_classification="NO_GBIF_MATCH",
            primary_anchor_count=99,
            broad_support_available=True,
        )
    )
    assert result.problem_class == "TAXON_REVIEW"
    assert result.patch_generation_allowed is False
    assert result.anchor_kernel_allowed is False


def test_recent_precise_anchor_opens_local_continuation() -> None:
    result = classify_local_discovery_problem(
        LocalDiscoveryEvidence(
            taxon_match_classification="AUTO_EXACT_ACCEPTED",
            primary_anchor_count=1,
            broad_support_available=True,
            structural_family="WETLAND_MOISTURE_STRUCTURE",
        )
    )
    assert result.problem_class == "LOCAL_CONTINUATION"
    assert result.patch_generation_allowed is True
    assert result.anchor_kernel_allowed is True


def test_detached_component_requires_anchor_and_explicit_structure() -> None:
    result = classify_local_discovery_problem(
        LocalDiscoveryEvidence(
            taxon_match_classification="AUTO_EXACT_ACCEPTED",
            primary_anchor_count=2,
            detached_component_supported=True,
        )
    )
    assert result.problem_class == "DETACHED_COMPONENT"
    with pytest.raises(ValueError):
        LocalDiscoveryEvidence(
            taxon_match_classification="AUTO_EXACT_ACCEPTED",
            primary_anchor_count=0,
            detached_component_supported=True,
        )


def test_legacy_record_never_becomes_local_anchor() -> None:
    result = classify_local_discovery_problem(
        LocalDiscoveryEvidence(
            taxon_match_classification="AUTO_EXACT_ACCEPTED",
            legacy_precise_count=5,
            broad_support_available=True,
        )
    )
    assert result.problem_class == "SENTINEL"
    assert result.anchor_kernel_allowed is False
    assert result.evidence_context == "legacy_precise_context"


def test_no_anchor_without_broad_support_abstains() -> None:
    result = classify_local_discovery_problem(
        LocalDiscoveryEvidence(
            taxon_match_classification="AUTO_EXACT_ACCEPTED",
            nonprimary_context_count=12,
            broad_support_available=False,
        )
    )
    assert result.problem_class == "ABSTAIN_LOCAL_PATCH"
    assert result.patch_generation_allowed is False


def test_counts_must_be_nonnegative() -> None:
    with pytest.raises(ValueError):
        LocalDiscoveryEvidence(
            taxon_match_classification="AUTO_EXACT_ACCEPTED",
            primary_anchor_count=-1,
        )
