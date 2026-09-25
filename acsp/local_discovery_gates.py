"""Evidence-adequacy gates for occurrence-anchored local discovery.

This module classifies *which survey problem is currently identifiable* before
any candidate-patch score is interpreted. It is prospective development code;
it does not modify the frozen validated robust-patch product.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProblemClass = Literal[
    "TAXON_REVIEW",
    "LOCAL_CONTINUATION",
    "DETACHED_COMPONENT",
    "SENTINEL",
    "ABSTAIN_LOCAL_PATCH",
]
AnchorReplicationClass = Literal[
    "ZERO_PRIMARY_ANCHOR",
    "SINGLE_PRIMARY_ANCHOR",
    "MULTIPLE_PRIMARY_ANCHORS",
]

AUTO_EXACT_TAXON = "AUTO_EXACT_ACCEPTED"


def classify_anchor_replication(primary_anchor_count: int) -> AnchorReplicationClass:
    """Return the exact 0 / 1 / >=2 replication class without tuning a cutoff."""
    if primary_anchor_count < 0:
        raise ValueError("primary_anchor_count must be non-negative")
    if primary_anchor_count == 0:
        return "ZERO_PRIMARY_ANCHOR"
    if primary_anchor_count == 1:
        return "SINGLE_PRIMARY_ANCHOR"
    return "MULTIPLE_PRIMARY_ANCHORS"


@dataclass(frozen=True)
class LocalDiscoveryEvidence:
    """Outcome-blind evidence available before patch generation."""

    taxon_match_classification: str
    primary_anchor_count: int = 0
    legacy_precise_count: int = 0
    nonprimary_context_count: int = 0
    broad_support_available: bool = False
    detached_component_supported: bool = False
    structural_family: str = "GENERAL_SPATIAL_BASELINE_ONLY"

    def __post_init__(self) -> None:
        for name in ("primary_anchor_count", "legacy_precise_count", "nonprimary_context_count"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.detached_component_supported and self.primary_anchor_count <= 0:
            raise ValueError("detached-component mode requires at least one eligible primary anchor")


@dataclass(frozen=True)
class LocalDiscoveryGateResult:
    problem_class: ProblemClass
    anchor_replication_class: AnchorReplicationClass
    patch_generation_allowed: bool
    anchor_kernel_allowed: bool
    structural_selector_allowed: bool
    evidence_context: str
    reason: str


def classify_local_discovery_problem(evidence: LocalDiscoveryEvidence) -> LocalDiscoveryGateResult:
    """Classify the next legitimate ACSP problem before candidate scoring.

    Ordering is deliberate:

    taxonomy -> anchor adequacy -> local/detached/sentinel/abstain.

    A region-only or historical record can inform context but cannot be promoted
    into a local anchor. Sentinel requires an independently available broad
    support frame; otherwise ACSP must abstain rather than manufacture locality.

    Anchor availability is not treated as binary evidence strength. A local
    problem with one eligible coordinate is explicitly distinguished from a
    local problem supported by two or more eligible coordinates. This is a
    reporting/evidence-adequacy distinction, not an outcome-tuned threshold.
    """

    replication = classify_anchor_replication(evidence.primary_anchor_count)

    if evidence.taxon_match_classification != AUTO_EXACT_TAXON:
        return LocalDiscoveryGateResult(
            problem_class="TAXON_REVIEW",
            anchor_replication_class=replication,
            patch_generation_allowed=False,
            anchor_kernel_allowed=False,
            structural_selector_allowed=False,
            evidence_context="taxon_concept_unresolved",
            reason="Resolve the taxon/concept crosswalk before occurrence geometry is interpreted.",
        )

    if evidence.primary_anchor_count > 0:
        if evidence.detached_component_supported:
            problem: ProblemClass = "DETACHED_COMPONENT"
            reason = "Eligible primary anchor exists and a predeclared disconnected structural component is available."
        else:
            problem = "LOCAL_CONTINUATION"
            reason = "Eligible recent precise anchor evidence supports an anchor-conditioned search."
        context = (
            "single_primary_anchor"
            if replication == "SINGLE_PRIMARY_ANCHOR"
            else "multiple_primary_anchors"
        )
        return LocalDiscoveryGateResult(
            problem_class=problem,
            anchor_replication_class=replication,
            patch_generation_allowed=True,
            anchor_kernel_allowed=True,
            structural_selector_allowed=True,
            evidence_context=context,
            reason=reason,
        )

    context = (
        "legacy_precise_context"
        if evidence.legacy_precise_count > 0
        else "nonprimary_context"
        if evidence.nonprimary_context_count > 0
        else "no_local_occurrence_context"
    )

    if evidence.broad_support_available:
        return LocalDiscoveryGateResult(
            problem_class="SENTINEL",
            anchor_replication_class=replication,
            patch_generation_allowed=True,
            anchor_kernel_allowed=False,
            structural_selector_allowed=True,
            evidence_context=context,
            reason="No eligible local anchor exists; use broad support plus spatially balanced sentinel exploration.",
        )

    return LocalDiscoveryGateResult(
        problem_class="ABSTAIN_LOCAL_PATCH",
        anchor_replication_class=replication,
        patch_generation_allowed=False,
        anchor_kernel_allowed=False,
        structural_selector_allowed=False,
        evidence_context=context,
        reason="Current evidence cannot justify a bounded local patch without false precision.",
    )
