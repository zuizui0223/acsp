"""Frozen, publication-facing ACSP candidate-set policy.

The production application contains additional evidence, logistics, and learning
features. This module exposes only the narrow policy evaluated in the independent
cross-taxon retrospective cohorts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

import pandas as pd

from .planning import select_complementary_candidates


@dataclass(frozen=True)
class ValidatedCorePolicy:
    taxon_group: str
    top_k: int = 5
    score_col: str = "component_local_habitat_score"
    evidence_weight: float = 1.0
    separation_scale_m: float = 25_000.0
    recovery_radius_km: float = 10.0
    validation_block_degrees: float = 0.1
    repeats: int = 5

    def __post_init__(self) -> None:
        group = self.taxon_group.strip().lower()
        if group not in {"plant", "animal"}:
            raise ValueError("taxon_group must be 'plant' or 'animal'")
        if self.top_k < 1:
            raise ValueError("top_k must be at least one")
        if not 0.0 <= float(self.evidence_weight) <= 1.0:
            raise ValueError("evidence_weight must lie in [0, 1]")
        if self.separation_scale_m <= 0 or self.recovery_radius_km <= 0 or self.validation_block_degrees <= 0:
            raise ValueError("distance and block parameters must be positive")
        if self.repeats < 1:
            raise ValueError("repeats must be at least one")

    @classmethod
    def for_taxon_group(cls, taxon_group: str) -> "ValidatedCorePolicy":
        group = str(taxon_group).strip().lower()
        if group == "plant":
            return cls(taxon_group="plant", evidence_weight=1.0)
        if group == "animal":
            return cls(taxon_group="animal", evidence_weight=0.75)
        raise ValueError("taxon_group must be 'plant' or 'animal'")

    @property
    def geographic_complementarity_weight(self) -> float:
        return 1.0 - float(self.evidence_weight)

    def manifest(self) -> dict[str, object]:
        payload = {
            **asdict(self),
            "geographic_complementarity_weight": self.geographic_complementarity_weight,
            "known_candidate_filter": "occurrence-supported|known-location|known anchor",
            "excluded_confirmatory_evidence": [
                "direct occurrence support",
                "survey-gap distance",
                "environmental novelty",
                "distance to known occurrences",
                "production macro-model, access, logistics, and field-feedback weights",
            ],
            "supported_claim": "Top-5 regional held-out recovery within 10 km versus random Top-5 from the identical candidate pool",
            "unsupported_claims": [
                "exact-site occupancy",
                "5 km general precision",
                "accessibility",
                "detectability",
                "abundance",
                "discoveries per field day",
                "validation of the complete production integrated score",
            ],
        }
        payload["fingerprint"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return payload


def select_validated_core(
    candidates: pd.DataFrame,
    policy: ValidatedCorePolicy,
    *,
    candidate_type_col: str = "candidate_type",
) -> pd.DataFrame:
    """Apply the frozen plant or animal candidate-set policy.

    Candidate generation must already have used training occurrences only. This
    function removes known-location candidate types and never reads held-out
    outcomes.
    """
    if candidates is None:
        raise ValueError("candidates must be a DataFrame")
    required = {"latitude", "longitude", policy.score_col}
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError(f"candidates is missing: {', '.join(sorted(missing))}")
    work = candidates.copy().reset_index(drop=True)
    if candidate_type_col in work.columns:
        known = work[candidate_type_col].astype(str).str.contains(
            "occurrence-supported|known-location|known anchor", case=False, na=False
        )
        work = work.loc[~known].reset_index(drop=True)
    if work.empty:
        return work.assign(
            validated_core_rank=pd.Series(dtype="Int64"),
            validated_core_policy=pd.Series(dtype=str),
        )
    selected = select_complementary_candidates(
        work,
        min(policy.top_k, len(work)),
        score_col=policy.score_col,
        evidence_weight=policy.evidence_weight,
        separation_scale_m=policy.separation_scale_m,
    ).copy()
    selected["validated_core_rank"] = range(1, len(selected) + 1)
    selected["validated_core_policy"] = f"frozen_{policy.taxon_group}_10km_top5"
    selected["validated_core_fingerprint"] = policy.manifest()["fingerprint"]
    selected["validated_recovery_radius_km"] = policy.recovery_radius_km
    return selected
