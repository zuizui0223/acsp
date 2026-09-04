"""Outcome-blind structural candidate selection for prospective local discovery.

This module deliberately does not decide which ecological variables belong to a
taxon. That decision is frozen upstream in the Cirsium structural-family contract.
The selector consumes one precomputed, provenance-bearing structural support score
and returns an exact matched-count candidate set. It never reads field outcomes,
access, permission, route cost, or tissue acquisition.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

OUTCOME_LIKE_TOKENS = (
    "field_outcome",
    "field_success",
    "detected",
    "detection_state",
    "current_occurrence_field_state",
    "tissue_acquired",
    "identity_verification_status",
)


@dataclass(frozen=True)
class StructuralSelectorAudit:
    feature_family: str
    support_provenance_id: str
    input_candidate_count: int
    requested_count: int
    selected_count: int
    support_column: str
    candidate_id_column: str
    field_outcomes_used: bool = False
    post_outcome_feature_switch_allowed: bool = False


def _forbidden_outcome_columns(columns: Iterable[str]) -> list[str]:
    found: list[str] = []
    for column in columns:
        lowered = str(column).strip().lower()
        if any(token in lowered for token in OUTCOME_LIKE_TOKENS):
            found.append(str(column))
    return sorted(set(found))


def select_structural_support(
    candidates: pd.DataFrame,
    *,
    count: int,
    feature_family: str,
    support_provenance_id: str,
    support_column: str = "structural_support",
    candidate_id_column: str = "candidate_cell_id",
) -> tuple[pd.DataFrame, StructuralSelectorAudit]:
    """Select the highest precomputed structural support at an exact matched count.

    The function has no ecological feature weights and no field-result inputs. Ties
    are broken only by the stable candidate ID. Callers must freeze the feature
    family and support-generation provenance before field outcomes are opened.
    """
    requested = int(count)
    if requested < 0:
        raise ValueError("count must be non-negative")
    if not str(feature_family).strip():
        raise ValueError("feature_family is required")
    if not str(support_provenance_id).strip():
        raise ValueError("support_provenance_id is required")

    forbidden = _forbidden_outcome_columns(candidates.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in structural selection: {forbidden}")
    for required in (support_column, candidate_id_column):
        if required not in candidates.columns:
            raise ValueError(f"missing required column: {required}")

    frame = candidates.copy()
    support = pd.to_numeric(frame[support_column], errors="coerce").to_numpy(float)
    if not np.isfinite(support).all():
        raise ValueError("structural support must be complete and finite")
    if ((support < 0.0) | (support > 1.0)).any():
        raise ValueError("structural support must lie in [0, 1]")

    ids = frame[candidate_id_column]
    if ids.isna().any() or ids.astype(str).duplicated().any():
        raise ValueError("candidate IDs must be complete and unique")

    if requested == 0 or frame.empty:
        selected = frame.iloc[0:0].copy().reset_index(drop=True)
    else:
        target = min(requested, len(frame))
        frame = frame.assign(_structural_support_numeric=support)
        frame = frame.sort_values(
            ["_structural_support_numeric", candidate_id_column],
            ascending=[False, True],
            kind="mergesort",
        )
        selected = frame.iloc[:target].drop(columns=["_structural_support_numeric"]).reset_index(drop=True)

    audit = StructuralSelectorAudit(
        feature_family=str(feature_family),
        support_provenance_id=str(support_provenance_id),
        input_candidate_count=int(len(candidates)),
        requested_count=requested,
        selected_count=int(len(selected)),
        support_column=support_column,
        candidate_id_column=candidate_id_column,
    )
    return selected, audit
