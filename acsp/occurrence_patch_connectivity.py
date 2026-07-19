"""Classify supported candidate patches relative to known occurrence patches.

The target is not a low-support corridor.  Known occurrences are first grouped
into spatial patches.  Candidate patches are then classified by their minimum
edge-to-edge distance to the nearest known occurrence patch.  A candidate patch
can therefore be close to the known distribution while remaining a distinct
spatial component.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .gap_patches import _connected_components, _validate_locations, haversine_distance_m


@dataclass(frozen=True)
class OccurrencePatchConnectivityConfig:
    """Spatial rules for occurrence-patch-relative classification."""

    occurrence_link_distance_m: float = 500.0
    candidate_occurrence_link_distance_m: float = 750.0
    near_disconnected_max_distance_m: float = 5_000.0

    def validate(self) -> None:
        if self.occurrence_link_distance_m <= 0:
            raise ValueError("occurrence_link_distance_m must be positive")
        if self.candidate_occurrence_link_distance_m < 0:
            raise ValueError("candidate_occurrence_link_distance_m must be non-negative")
        if self.near_disconnected_max_distance_m < self.candidate_occurrence_link_distance_m:
            raise ValueError(
                "near_disconnected_max_distance_m must be at least "
                "candidate_occurrence_link_distance_m"
            )


def build_occurrence_patches(
    known_occurrences: pd.DataFrame,
    *,
    link_distance_m: float = 500.0,
) -> pd.DataFrame:
    """Assign each known occurrence to a radius-graph occurrence patch."""

    if link_distance_m <= 0:
        raise ValueError("link_distance_m must be positive")
    known = _validate_locations(known_occurrences, "known_occurrences")
    if known.empty:
        return known.assign(occurrence_patch_id=pd.Series(dtype=str))

    components = _connected_components(
        known["latitude"].to_numpy(float),
        known["longitude"].to_numpy(float),
        float(link_distance_m),
    )
    patch_ids: dict[int, str] = {}
    for ordinal, component in enumerate(components, start=1):
        patch_id = f"occurrence-patch-{ordinal:03d}"
        for position in component:
            patch_ids[int(position)] = patch_id
    out = known.copy()
    out["occurrence_patch_id"] = out.index.map(patch_ids)
    return out


def _nearest_occurrence_patch(
    candidate_patch: pd.DataFrame,
    occurrence_members: pd.DataFrame,
) -> tuple[str | None, float]:
    if occurrence_members.empty:
        return None, math.inf

    occurrence_lats = occurrence_members["latitude"].to_numpy(float)
    occurrence_lons = occurrence_members["longitude"].to_numpy(float)
    best_distance = math.inf
    best_patch_id: str | None = None
    for row in candidate_patch[["latitude", "longitude"]].itertuples(index=False):
        distances = haversine_distance_m(
            row.latitude,
            row.longitude,
            occurrence_lats,
            occurrence_lons,
        )
        position = int(np.argmin(distances))
        distance = float(distances[position])
        patch_id = str(occurrence_members.iloc[position]["occurrence_patch_id"])
        if distance < best_distance:
            best_distance = distance
            best_patch_id = patch_id
    return best_patch_id, best_distance


def annotate_occurrence_patch_connectivity(
    candidate_patch_members: pd.DataFrame,
    known_occurrences: pd.DataFrame,
    *,
    config: OccurrencePatchConnectivityConfig | None = None,
) -> pd.DataFrame:
    """Annotate candidate patches as extensions, near-disconnected, or remote.

    ``occurrence_patch_extension`` means that at least one candidate member lies
    within the candidate-to-occurrence graph-link distance of a known occurrence
    patch. ``near_disconnected_occurrence_patch`` means the candidate patch is
    outside that connection distance but remains within the predeclared nearby
    search distance. More distant patches are ``remote_candidate_patch``.
    """

    cfg = config or OccurrencePatchConnectivityConfig()
    cfg.validate()
    if candidate_patch_members is None or candidate_patch_members.empty:
        return pd.DataFrame()
    if "gap_patch_id" not in candidate_patch_members.columns:
        raise ValueError("candidate_patch_members is missing gap_patch_id")

    candidates = _validate_locations(candidate_patch_members, "candidate_patch_members")
    occurrences = build_occurrence_patches(
        known_occurrences,
        link_distance_m=cfg.occurrence_link_distance_m,
    )

    rows: list[pd.DataFrame] = []
    for patch_id, patch in candidates.groupby("gap_patch_id", sort=True):
        nearest_patch_id, edge_distance_m = _nearest_occurrence_patch(patch, occurrences)
        if edge_distance_m <= cfg.candidate_occurrence_link_distance_m:
            connectivity_class = "occurrence_patch_extension"
        elif edge_distance_m <= cfg.near_disconnected_max_distance_m:
            connectivity_class = "near_disconnected_occurrence_patch"
        else:
            connectivity_class = "remote_candidate_patch"

        annotated = patch.copy()
        annotated["nearest_occurrence_patch_id"] = nearest_patch_id
        annotated["candidate_occurrence_edge_distance_m"] = edge_distance_m
        annotated["candidate_occurrence_gap_width_m"] = max(
            0.0,
            edge_distance_m - cfg.candidate_occurrence_link_distance_m,
        )
        annotated["occurrence_patch_connectivity_class"] = connectivity_class
        annotated["occurrence_patch_link_distance_m"] = cfg.occurrence_link_distance_m
        annotated["candidate_occurrence_link_distance_m"] = (
            cfg.candidate_occurrence_link_distance_m
        )
        annotated["near_disconnected_max_distance_m"] = (
            cfg.near_disconnected_max_distance_m
        )
        rows.append(annotated)

    return pd.concat(rows, ignore_index=True)
