"""Provider-neutral component partitioning for LOCAL versus DETACHED discovery.

A provider or upstream ecological graph may assign each candidate cell an
``ecological_component_id``. This module does not decide what a component means;
it only separates components already represented by known populations from
source-backed components that are not represented by those populations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class ComponentPartitionAudit:
    component_column: str
    candidate_count: int
    component_count: int
    anchored_component_ids: tuple[str, ...]
    local_candidate_count: int
    detached_candidate_count: int
    detached_component_count: int
    field_outcomes_used: bool = False
    human_access_used: bool = False
    distance_threshold_used: bool = False


def partition_candidate_components(
    candidate_frame: pd.DataFrame,
    *,
    anchored_component_ids: Iterable[str],
    component_column: str = "ecological_component_id",
) -> tuple[pd.DataFrame, pd.DataFrame, ComponentPartitionAudit]:
    """Return `(local, detached, audit)` from an already frozen component map.

    LOCAL contains candidate cells in components represented by historical
    populations. DETACHED contains every other declared component in the same
    frozen outer candidate frame. No distance threshold, outcome, or access layer
    is used to decide the partition.
    """
    if candidate_frame is None or candidate_frame.empty:
        raise ValueError("candidate_frame cannot be empty")
    if component_column not in candidate_frame.columns:
        raise ValueError(f"candidate frame missing component column: {component_column}")
    values = candidate_frame[component_column]
    if values.isna().any() or values.astype(str).str.strip().eq("").any():
        raise ValueError("ecological component IDs must be complete and non-empty")
    anchors = tuple(sorted({str(value).strip() for value in anchored_component_ids if str(value).strip()}))
    if not anchors:
        raise ValueError("at least one anchored component ID is required")
    components = set(values.astype(str))
    unknown = sorted(set(anchors).difference(components))
    if unknown:
        raise ValueError(f"anchored component IDs are absent from candidate frame: {unknown}")

    local_mask = values.astype(str).isin(set(anchors))
    local = candidate_frame.loc[local_mask].copy().reset_index(drop=True)
    detached = candidate_frame.loc[~local_mask].copy().reset_index(drop=True)
    detached_components = sorted(set(detached[component_column].astype(str))) if not detached.empty else []
    audit = ComponentPartitionAudit(
        component_column=str(component_column),
        candidate_count=int(len(candidate_frame)),
        component_count=int(len(components)),
        anchored_component_ids=anchors,
        local_candidate_count=int(len(local)),
        detached_candidate_count=int(len(detached)),
        detached_component_count=int(len(detached_components)),
    )
    return local, detached, audit
