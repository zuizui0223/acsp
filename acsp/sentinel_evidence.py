"""Classify coarse occurrence evidence after the local-anchor gate fails.

Cirsium shows that raw record abundance can coexist with zero usable <=1 km
primary anchors. This module preserves that coarse evidence without converting it
into false local precision. It decides whether a sentinel problem has an explicit
uncertainty-kernel input, only coarse sector context, legacy context, or no usable
occurrence support at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SentinelEvidenceClass = Literal[
    "LOCAL_PRIMARY_ANCHOR_PRESENT",
    "SENTINEL_UNCERTAINTY_KERNEL_ELIGIBLE",
    "SENTINEL_COARSE_CONTEXT_ONLY",
    "SENTINEL_LEGACY_CONTEXT_ONLY",
    "ABSTAIN_NO_OCCURRENCE_SUPPORT",
]


@dataclass(frozen=True)
class SentinelEvidenceCounts:
    primary_anchor_count: int = 0
    recent_declared_uncertainty_coordinate_count: int = 0
    recent_unknown_uncertainty_coordinate_count: int = 0
    recent_obscured_coordinate_count: int = 0
    recent_region_only_count: int = 0
    legacy_or_historical_spatial_count: int = 0

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if int(value) < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class SentinelEvidenceResult:
    evidence_class: SentinelEvidenceClass
    local_kernel_allowed: bool
    uncertainty_kernel_allowed: bool
    broad_sector_context_available: bool
    reason: str


def classify_sentinel_evidence(counts: SentinelEvidenceCounts) -> SentinelEvidenceResult:
    if counts.primary_anchor_count > 0:
        return SentinelEvidenceResult(
            evidence_class="LOCAL_PRIMARY_ANCHOR_PRESENT",
            local_kernel_allowed=True,
            uncertainty_kernel_allowed=False,
            broad_sector_context_available=True,
            reason="At least one frozen-rule primary anchor exists; use the local-continuation gate instead of sentinel fallback.",
        )
    if counts.recent_declared_uncertainty_coordinate_count > 0:
        return SentinelEvidenceResult(
            evidence_class="SENTINEL_UNCERTAINTY_KERNEL_ELIGIBLE",
            local_kernel_allowed=False,
            uncertainty_kernel_allowed=True,
            broad_sector_context_available=True,
            reason="Recent coordinate-bearing records have declared uncertainty >1 km; preserve their uncertainty scale for broad support without treating them as local anchors.",
        )
    if (
        counts.recent_unknown_uncertainty_coordinate_count
        + counts.recent_obscured_coordinate_count
        + counts.recent_region_only_count
        > 0
    ):
        return SentinelEvidenceResult(
            evidence_class="SENTINEL_COARSE_CONTEXT_ONLY",
            local_kernel_allowed=False,
            uncertainty_kernel_allowed=False,
            broad_sector_context_available=True,
            reason="Recent evidence exists but its spatial precision cannot justify a coordinate kernel; use only sector/structural context.",
        )
    if counts.legacy_or_historical_spatial_count > 0:
        return SentinelEvidenceResult(
            evidence_class="SENTINEL_LEGACY_CONTEXT_ONLY",
            local_kernel_allowed=False,
            uncertainty_kernel_allowed=False,
            broad_sector_context_available=True,
            reason="Only legacy/historical spatial evidence remains; retain it as context but do not imply current occupancy.",
        )
    return SentinelEvidenceResult(
        evidence_class="ABSTAIN_NO_OCCURRENCE_SUPPORT",
        local_kernel_allowed=False,
        uncertainty_kernel_allowed=False,
        broad_sector_context_available=False,
        reason="No occurrence evidence can justify local or broad occurrence-conditioned support; abstain or use an independently declared range-sector survey.",
    )
