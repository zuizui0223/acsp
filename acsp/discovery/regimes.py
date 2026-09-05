"""Fail-closed regime resolution for experimental N4 discovery."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DiscoveryRegime(str, Enum):
    LOCAL_CONTINUATION = "LOCAL_CONTINUATION"
    DETACHED_COMPONENT = "DETACHED_COMPONENT"
    SENTINEL = "SENTINEL"
    ABSTAIN_LOCAL_PATCH = "ABSTAIN_LOCAL_PATCH"


@dataclass(frozen=True)
class DiscoveryEvidenceProfile:
    """Typed evidence supplied to the regime gate.

    ``local_component_justified`` is intentionally explicit. This package does
    not infer it from a post-hoc anchor-count threshold. A separate frozen
    evidence-adequacy rule must justify that statement for a real experiment.
    """

    exact_anchor_count: int = 0
    local_component_justified: bool = False
    detached_component_available: bool = False
    sentinel_context_available: bool = False
    sentinel_subregime: str = ""

    def validate(self) -> None:
        if int(self.exact_anchor_count) < 0:
            raise ValueError("exact_anchor_count cannot be negative")
        if self.local_component_justified and int(self.exact_anchor_count) < 1:
            raise ValueError("LOCAL_CONTINUATION cannot be justified without an exact anchor")
        if self.sentinel_subregime and not self.sentinel_context_available:
            raise ValueError("sentinel_subregime requires sentinel_context_available")


@dataclass(frozen=True)
class RegimeDecision:
    regime: DiscoveryRegime
    reason: str
    exact_anchor_count: int
    sentinel_subregime: str = ""
    inferred_from_anchor_count_threshold: bool = False


def resolve_discovery_regime(profile: DiscoveryEvidenceProfile) -> RegimeDecision:
    """Resolve LOCAL/DETACHED/SENTINEL/ABSTAIN without fitted thresholds."""
    profile.validate()
    if profile.local_component_justified:
        return RegimeDecision(
            regime=DiscoveryRegime.LOCAL_CONTINUATION,
            reason="a separately justified local component has at least one exact anchor",
            exact_anchor_count=int(profile.exact_anchor_count),
        )
    if profile.detached_component_available:
        return RegimeDecision(
            regime=DiscoveryRegime.DETACHED_COMPONENT,
            reason="a separated ecological component is justified but local interpolation is not",
            exact_anchor_count=int(profile.exact_anchor_count),
        )
    if profile.sentinel_context_available:
        return RegimeDecision(
            regime=DiscoveryRegime.SENTINEL,
            reason="only broad/uncertainty/context evidence supports search",
            exact_anchor_count=int(profile.exact_anchor_count),
            sentinel_subregime=str(profile.sentinel_subregime),
        )
    return RegimeDecision(
        regime=DiscoveryRegime.ABSTAIN_LOCAL_PATCH,
        reason="available evidence does not justify a fine local or detached search frame",
        exact_anchor_count=int(profile.exact_anchor_count),
    )
