"""Multi-lane evidence planning for experimental N4 discovery.

The original single-regime resolver remains available for frozen experiments.
This module adds a higher-level, non-exclusive lane plan because repeated
retrospective diagnostics show that LOCAL and DETACHED evidence can be
complementary rather than mutually exclusive.

The planner does not allocate budget between lanes and does not rank candidates.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DiscoveryLane(str, Enum):
    LOCAL_CONTINUATION = "LOCAL_CONTINUATION"
    DETACHED_SAME_COMPONENT = "DETACHED_SAME_COMPONENT"
    DETACHED_OTHER_COMPONENT = "DETACHED_OTHER_COMPONENT"
    SENTINEL = "SENTINEL"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class DiscoveryLaneEvidence:
    exact_population_count: int = 0
    local_context_justified: bool = False
    declared_local_boundary_available: bool = False
    source_backed_component_ids_available: bool = False
    remote_same_component_candidates_available: bool = False
    other_component_candidates_available: bool = False
    sentinel_context_available: bool = False
    sentinel_subregime: str = ""

    def validate(self) -> None:
        if int(self.exact_population_count) < 0:
            raise ValueError("exact_population_count cannot be negative")
        if self.local_context_justified and int(self.exact_population_count) < 1:
            raise ValueError("LOCAL_CONTINUATION requires at least one exact population")
        if self.remote_same_component_candidates_available:
            if not self.source_backed_component_ids_available:
                raise ValueError("remote same-component candidates require source-backed component identities")
            if not self.declared_local_boundary_available:
                raise ValueError("remote same-component candidates require a declared LOCAL boundary")
            if int(self.exact_population_count) < 1:
                raise ValueError("remote same-component candidates require at least one exact population")
        if self.other_component_candidates_available and not self.source_backed_component_ids_available:
            raise ValueError("other-component candidates require source-backed component identities")
        if self.sentinel_subregime and not self.sentinel_context_available:
            raise ValueError("sentinel_subregime requires sentinel_context_available")


@dataclass(frozen=True)
class DiscoveryLanePlan:
    lanes: tuple[DiscoveryLane, ...]
    exact_population_count: int
    local_and_detached_coexist: bool
    budget_allocation_identified: bool
    reason: str
    sentinel_subregime: str = ""
    field_outcomes_used: bool = False
    human_access_used: bool = False


def plan_discovery_lanes(evidence: DiscoveryLaneEvidence) -> DiscoveryLanePlan:
    """Return all independently justified search lanes without blending them."""
    evidence.validate()
    lanes: list[DiscoveryLane] = []
    if evidence.local_context_justified:
        lanes.append(DiscoveryLane.LOCAL_CONTINUATION)
    if evidence.remote_same_component_candidates_available:
        lanes.append(DiscoveryLane.DETACHED_SAME_COMPONENT)
    if evidence.other_component_candidates_available:
        lanes.append(DiscoveryLane.DETACHED_OTHER_COMPONENT)
    if evidence.sentinel_context_available:
        lanes.append(DiscoveryLane.SENTINEL)
    if not lanes:
        lanes = [DiscoveryLane.ABSTAIN]

    local_and_detached = (
        DiscoveryLane.LOCAL_CONTINUATION in lanes
        and any(lane in lanes for lane in (DiscoveryLane.DETACHED_SAME_COMPONENT, DiscoveryLane.DETACHED_OTHER_COMPONENT))
    )
    if lanes == [DiscoveryLane.ABSTAIN]:
        reason = "available evidence does not justify a LOCAL, DETACHED, or SENTINEL lane"
    elif local_and_detached:
        reason = "LOCAL evidence is retained while independently source-backed non-local components are preserved as separate DETACHED lanes"
    elif any(lane in lanes for lane in (DiscoveryLane.DETACHED_SAME_COMPONENT, DiscoveryLane.DETACHED_OTHER_COMPONENT)):
        reason = "source-backed non-local candidate structure is available without requiring a nearest-known-only search"
    elif DiscoveryLane.LOCAL_CONTINUATION in lanes:
        reason = "only the separately justified local continuation lane is currently available"
    else:
        reason = "only sentinel/context evidence is currently available"

    return DiscoveryLanePlan(
        lanes=tuple(lanes),
        exact_population_count=int(evidence.exact_population_count),
        local_and_detached_coexist=bool(local_and_detached),
        budget_allocation_identified=False,
        reason=reason,
        sentinel_subregime=str(evidence.sentinel_subregime),
    )
