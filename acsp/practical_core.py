"""Parsimonious ACSP practical finite-decision policy.

This module is separate from :mod:`acsp.validated_core`.  The historical
publication-facing v1 policy remains frozen.  Development after v1 found no
reproducible gain from learned candidate utilities, policy routers, or added
geographic/environmental complementarity over the focal local-habitat signal.

The practical core therefore uses the same transparent local evidence for
plants and animals and returns a finite Top-k survey decision.  It is frozen for
an untouched comparison against established survey-design methods; it is not yet
validated as superior to them.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import pandas as pd


PRACTICAL_CORE_PROTOCOL_ID = "acsp-practical-local-core-v1"
PRACTICAL_CORE_FINGERPRINT = "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905"
KNOWN_CANDIDATE_PATTERN = "occurrence-supported|known-location|known anchor"


@dataclass(frozen=True)
class PracticalCorePolicy:
    """Frozen development configuration for the parsimonious practical core."""

    top_k: int = 5
    score_col: str = "component_local_habitat_score"
    recovery_radius_km: float = 10.0
    validation_block_degrees: float = 0.1
    repeats: int = 5
    protocol_id: str = PRACTICAL_CORE_PROTOCOL_ID
    protocol_fingerprint: str = PRACTICAL_CORE_FINGERPRINT

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError("top_k must be at least one")
        if self.recovery_radius_km <= 0 or self.validation_block_degrees <= 0:
            raise ValueError("distance and block parameters must be positive")
        if self.repeats < 1:
            raise ValueError("repeats must be at least one")

    @property
    def geographic_complementarity_weight(self) -> float:
        return 0.0


def _stable_candidate_id(frame: pd.DataFrame) -> pd.Series:
    for column in ("candidate_id", "site_id"):
        if column in frame.columns:
            return frame[column].astype(str)
    return pd.Series(
        [f"candidate-{index + 1:06d}" for index in range(len(frame))],
        index=frame.index,
        dtype=str,
    )


def select_practical_core(
    candidates: pd.DataFrame,
    policy: PracticalCorePolicy | None = None,
    *,
    candidate_type_col: str = "candidate_type",
) -> pd.DataFrame:
    """Return the deterministic local-evidence Top-k practical survey set.

    Candidate generation must already have used training occurrences only.
    Known-location rows are filtered before ranking.  No scientific name,
    held-out coordinate, held-out recovery, SDM prediction, survey-gap score,
    access score, or geographic complementarity term is read by the selector.
    """
    cfg = policy or PracticalCorePolicy()
    if candidates is None:
        raise ValueError("candidates must be a DataFrame")
    required = {"latitude", "longitude", cfg.score_col}
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError(f"candidates is missing: {', '.join(sorted(missing))}")

    work = candidates.copy().reset_index(drop=True)
    if candidate_type_col in work.columns:
        known = work[candidate_type_col].astype(str).str.contains(
            KNOWN_CANDIDATE_PATTERN, case=False, na=False
        )
        work = work.loc[~known].reset_index(drop=True)
    if work.empty:
        return work.assign(
            practical_core_rank=pd.Series(dtype="Int64"),
            practical_core_policy=pd.Series(dtype=str),
            practical_core_fingerprint=pd.Series(dtype=str),
        )

    work["_practical_score"] = pd.to_numeric(
        work[cfg.score_col], errors="coerce"
    ).fillna(float("-inf"))
    work["_practical_stable_id"] = _stable_candidate_id(work)
    selected = work.sort_values(
        ["_practical_score", "_practical_stable_id"],
        ascending=[False, True],
        kind="mergesort",
    ).head(min(cfg.top_k, len(work))).copy()
    selected = selected.drop(
        columns=["_practical_score", "_practical_stable_id"], errors="ignore"
    ).reset_index(drop=True)
    selected["practical_core_rank"] = range(1, len(selected) + 1)
    selected["practical_core_policy"] = cfg.protocol_id
    selected["practical_core_fingerprint"] = cfg.protocol_fingerprint
    selected["practical_core_score_interpretation"] = (
        "occurrence-conditioned local environmental support; not occupancy probability"
    )
    selected["practical_core_recovery_radius_km"] = cfg.recovery_radius_km
    return selected


def protocol_fingerprint(payload: dict[str, object]) -> str:
    """Return the canonical SHA-256 for the external practical-core protocol."""
    cleaned = dict(payload)
    cleaned.pop("fingerprint", None)
    encoded = json.dumps(cleaned, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
