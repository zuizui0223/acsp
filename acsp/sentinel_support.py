"""Outcome-blind broad support for uncertainty-aware sentinel discovery.

Only records with a declared coordinate uncertainty > the frozen 1 km local-anchor
ceiling are eligible. The support does not shrink them to pseudo-exact points.
Each unique (coordinate, uncertainty-radius) footprint contributes equally; support
is the normalized number of declared uncertainty discs covering a candidate cell.

Unknown-uncertainty, obscured, region-only and legacy records are intentionally not
converted into coordinate kernels by this module.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from acsp.structural_selector import _forbidden_outcome_columns

EARTH_RADIUS_KM = 6371.0088
LOCAL_ANCHOR_CEILING_M = 1000.0


@dataclass(frozen=True)
class UncertaintyFootprintAudit:
    input_record_count: int
    unique_footprint_count: int
    candidate_count: int
    candidates_inside_union: int
    local_anchor_ceiling_m: float = LOCAL_ANCHOR_CEILING_M
    field_outcomes_used: bool = False
    distance_preference_inside_footprint: bool = False
    unknown_uncertainty_used_as_kernel: bool = False


def _haversine_matrix_km(candidates: pd.DataFrame, evidence: pd.DataFrame) -> np.ndarray:
    lat1 = np.radians(pd.to_numeric(candidates["latitude"], errors="raise").to_numpy(float))[:, None]
    lon1 = np.radians(pd.to_numeric(candidates["longitude"], errors="raise").to_numpy(float))[:, None]
    lat2 = np.radians(pd.to_numeric(evidence["latitude"], errors="raise").to_numpy(float))[None, :]
    lon2 = np.radians(pd.to_numeric(evidence["longitude"], errors="raise").to_numpy(float))[None, :]
    dlat = lat1 - lat2
    dlon = lon1 - lon2
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _validate_no_outcomes(frame: pd.DataFrame, label: str) -> None:
    forbidden = _forbidden_outcome_columns(frame.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in {label}: {forbidden}")


def uncertainty_footprint_support(
    candidates: pd.DataFrame,
    evidence: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, UncertaintyFootprintAudit]:
    """Return normalized overlap support and union membership for declared footprints."""
    _validate_no_outcomes(candidates, "sentinel candidate frame")
    _validate_no_outcomes(evidence, "sentinel uncertainty evidence")
    for column in ("latitude", "longitude"):
        if column not in candidates.columns or column not in evidence.columns:
            raise ValueError(f"both candidates and evidence require {column}")
    if "coordinate_uncertainty_m" not in evidence.columns:
        raise ValueError("evidence requires coordinate_uncertainty_m")
    if candidates.empty:
        raise ValueError("candidate frame cannot be empty")
    if evidence.empty:
        raise ValueError("uncertainty-footprint evidence cannot be empty")

    uncertainty = pd.to_numeric(evidence["coordinate_uncertainty_m"], errors="coerce")
    if uncertainty.isna().any() or not np.isfinite(uncertainty.to_numpy(float)).all():
        raise ValueError("uncertainty-kernel evidence requires complete finite declared uncertainty")
    if (uncertainty <= LOCAL_ANCHOR_CEILING_M).any():
        raise ValueError("uncertainty-kernel records must lie above the frozen 1 km local-anchor ceiling")

    work = evidence.copy()
    work["_unc_m"] = uncertainty.astype(float)
    # Exact duplicate declared footprints do not gain extra weight from repeated downloads/duplicates.
    work = work.drop_duplicates(subset=["latitude", "longitude", "_unc_m"], keep="first").reset_index(drop=True)

    distances = _haversine_matrix_km(candidates, work)
    radii_km = work["_unc_m"].to_numpy(float)[None, :] / 1000.0
    inside = distances <= radii_km + 1e-12
    overlap = inside.sum(axis=1).astype(float)
    union = overlap > 0
    maximum = float(overlap.max()) if overlap.size else 0.0
    support = overlap / maximum if maximum > 0 else np.zeros(len(candidates), dtype=float)

    return (
        pd.Series(support, index=candidates.index, name="uncertainty_footprint_support"),
        pd.Series(union, index=candidates.index, name="inside_uncertainty_footprint_union"),
        UncertaintyFootprintAudit(
            input_record_count=int(len(evidence)),
            unique_footprint_count=int(len(work)),
            candidate_count=int(len(candidates)),
            candidates_inside_union=int(union.sum()),
        ),
    )


def clip_to_uncertainty_footprint_union(
    candidates: pd.DataFrame,
    evidence: pd.DataFrame,
) -> tuple[pd.DataFrame, UncertaintyFootprintAudit]:
    """Clip a predeclared range-sector grid to the union of broad uncertainty discs."""
    support, union, audit = uncertainty_footprint_support(candidates, evidence)
    out = candidates.loc[union].copy()
    out["broad_sentinel_support"] = support.loc[union].to_numpy(float)
    if out.empty:
        raise ValueError("declared uncertainty footprints do not intersect the candidate range sector")
    return out.reset_index(drop=True), audit
