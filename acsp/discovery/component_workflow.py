"""High-level provider workflow for source-backed component preparation.

This module keeps provider interaction outside the scientific selector. It takes
an already declared broad candidate frame plus population anchors, creates one
pinned ESA WorldCover crop, attaches physical land-component IDs, and writes the
anchored-versus-other component partition without using field outcomes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .components import partition_candidate_components
from .providers import attach_worldcover_component_ids, build_worldcover_2021_map_crop
from .schemas import validate_candidate_frame_schema


@dataclass(frozen=True)
class WorldCoverComponentPreparationAudit:
    status: str
    input_candidate_count: int
    land_candidate_count: int
    anchored_candidate_count: int
    other_component_candidate_count: int
    anchored_component_ids: tuple[str, ...]
    worldcover_crop_sha256: str
    provider_release: str
    source_manifest: dict[str, Any]
    field_outcomes_used: bool = False
    human_access_used: bool = False
    component_selection_fitted_to_outcomes: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _frame_bounds(frame: pd.DataFrame) -> tuple[float, float, float, float]:
    return (
        float(frame["longitude"].min()),
        float(frame["latitude"].min()),
        float(frame["longitude"].max()),
        float(frame["latitude"].max()),
    )


def prepare_worldcover_component_partition(
    candidate_frame: pd.DataFrame,
    population_anchors: pd.DataFrame,
    *,
    snapshot_path: Path,
    crop_margin_m: float = 3000.0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, WorldCoverComponentPreparationAudit]:
    """Prepare a broad frame for source-backed LOCAL/DETACHED component work.

    Returns ``(all_land, anchored_components, other_components, audit)``.
    All historical anchor components are retained. No component-size threshold or
    distance threshold is fitted here.
    """
    validate_candidate_frame_schema(candidate_frame)
    if population_anchors is None or population_anchors.empty:
        raise ValueError("population_anchors cannot be empty")
    for column in ("latitude", "longitude"):
        if column not in population_anchors.columns:
            raise ValueError(f"population anchors missing {column}")

    snapshot_path = Path(snapshot_path)
    wc_audit = build_worldcover_2021_map_crop(
        _frame_bounds(candidate_frame),
        snapshot_path,
        margin_m=float(crop_margin_m),
    )
    all_land, component_audit = attach_worldcover_component_ids(
        candidate_frame,
        population_anchors,
        snapshot_path,
    )
    anchored, other, partition_audit = partition_candidate_components(
        all_land,
        anchored_component_ids=component_audit.anchored_component_ids,
    )
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {
        "schema_version": "acsp-discovery-worldcover-component-source-v1",
        "sources": [
            {
                "provider_id": "ESA_WORLDCOVER",
                "layer_role": "component_geometry",
                "release_id": wc_audit.release_id,
                "retrieved_at": retrieved_at,
                "source_uri": ";".join(wc_audit.source_urls),
                "sha256": wc_audit.output_sha256,
            },
            {
                "provider_id": "ESA_WORLDCOVER",
                "layer_role": "landcover",
                "release_id": wc_audit.release_id,
                "retrieved_at": retrieved_at,
                "source_uri": ";".join(wc_audit.source_urls),
                "sha256": wc_audit.output_sha256,
            },
        ],
    }
    audit = WorldCoverComponentPreparationAudit(
        status="WORLDCOVER_COMPONENT_PARTITION_READY_DEVELOPMENT_ONLY",
        input_candidate_count=int(len(candidate_frame)),
        land_candidate_count=int(len(all_land)),
        anchored_candidate_count=int(len(anchored)),
        other_component_candidate_count=int(len(other)),
        anchored_component_ids=tuple(component_audit.anchored_component_ids),
        worldcover_crop_sha256=str(wc_audit.output_sha256),
        provider_release=str(wc_audit.release_id),
        source_manifest=manifest,
    )
    # Explicit cross-check so a future provider refactor cannot silently alter
    # the partition semantics while returning a plausible audit object.
    if audit.anchored_candidate_count != partition_audit.anchored_candidate_count:
        raise AssertionError("anchored component count drifted during WorldCover preparation")
    if audit.other_component_candidate_count != partition_audit.detached_candidate_count:
        raise AssertionError("other component count drifted during WorldCover preparation")
    return all_land, anchored, other, audit
