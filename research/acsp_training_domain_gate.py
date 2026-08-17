#!/usr/bin/env python3
"""Training-only domain gate for ACSP survey-policy applicability.

This module is research infrastructure.  It prevents a terrestrial land-grid
survey policy from being applied blindly to marine/coastal training data.  The
gate uses taxonomy only as a conservative prior; the observed fraction of
training occurrences supported by the candidate land surface can override a
plant/animal prior.  Held-out outcomes are never an input.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import numpy as np


AQUATIC_VERTEBRATE_CLASSES = {
    "actinopterygii",
    "chondrichthyes",
    "myxini",
    "cephalaspidomorphi",
}


@dataclass(frozen=True)
class DomainDecision:
    domain: str
    terrestrial_policy_applicable: bool
    evidence: str
    confidence: str

    def as_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "terrestrial_policy_applicable": self.terrestrial_policy_applicable,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


def infer_training_domain(
    taxon_metadata: Optional[Mapping[str, object]] = None,
    *,
    training_land_fraction: Optional[float] = None,
) -> DomainDecision:
    """Infer the survey-surface domain without reading held-out outcomes.

    `training_land_fraction` is the fraction of cleaned training occurrences
    supported by the declared land candidate surface (for example valid GSI DEM
    land).  It has precedence over broad kingdom labels so marine vascular
    plants are not automatically treated as terrestrial.
    """
    metadata = {
        str(key).lower(): str(value or "").strip().lower()
        for key, value in (taxon_metadata or {}).items()
    }
    kingdom = metadata.get("kingdom", "")
    phylum = metadata.get("phylum", "")
    clazz = metadata.get("class", "")

    fraction = None
    if training_land_fraction is not None and np.isfinite(float(training_land_fraction)):
        fraction = float(np.clip(float(training_land_fraction), 0.0, 1.0))

    # Observed training support overrides coarse taxonomy. This is the key
    # correction relative to the historical kingdom-first surface inference.
    if fraction is not None:
        if fraction <= 0.20:
            return DomainDecision(
                "marine",
                False,
                f"only {fraction:.1%} of training occurrences are supported by the land candidate surface",
                "high" if fraction <= 0.05 else "medium",
            )
        if fraction <= 0.65:
            return DomainDecision(
                "coastal_or_amphibious",
                False,
                f"training occurrences straddle land and non-land support ({fraction:.1%} land)",
                "medium",
            )

    if clazz in AQUATIC_VERTEBRATE_CLASSES:
        return DomainDecision(
            "inland_or_aquatic",
            False,
            f"taxonomy class {clazz or 'unknown'} is aquatic and no terrestrial override is justified",
            "medium",
        )

    if kingdom in {"plantae", "viridiplantae"}:
        if phylum and phylum not in {"tracheophyta", "streptophyta"}:
            return DomainDecision(
                "non_vascular_or_algal_plant",
                False,
                f"plant phylum {phylum} is outside the current terrestrial vascular-plant policy",
                "high",
            )
        if fraction is None:
            return DomainDecision(
                "terrestrial_candidate_unverified",
                False,
                "vascular-plant taxonomy suggests terrestrial use, but training land support was not measured",
                "low",
            )
        return DomainDecision(
            "terrestrial",
            True,
            f"vascular-plant prior plus {fraction:.1%} land-supported training occurrences",
            "high" if fraction >= 0.90 else "medium",
        )

    if fraction is not None and fraction >= 0.80:
        return DomainDecision(
            "terrestrial",
            True,
            f"{fraction:.1%} of training occurrences are supported by the land candidate surface",
            "medium",
        )

    return DomainDecision(
        "unknown",
        False,
        "training data do not establish applicability of the terrestrial survey policy",
        "low",
    )
