"""Validated cross-taxon robust candidate-patch product.

This is the promoted ACSP product boundary after untouched confirmation.
It converts an environmental candidate universe plus training-occurrence
prototypes into bounded candidate patches. It does not rank a user-specified
number of sites and does not optimize routes, budgets, days, or movement modes.
"""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from .robust_patches import RobustSupportAudit, leave_one_out_consensus_support, support_cells_to_patches

VALIDATED_ROBUST_SUPPORT_FRACTION = 0.025
VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M = 1000.0
VALIDATED_ROBUST_PRIMARY_RADIUS_KM = 10.0
VALIDATED_ROBUST_CONFIRMATION_PAIRS = 96
VALIDATED_ROBUST_CONFIRMATION_FOLDS = 480
VALIDATED_ROBUST_MEAN_LIFT_OVER_RANDOM = 0.08558708102617191
VALIDATED_ROBUST_BOOTSTRAP_CI = (0.051186296271122624, 0.12165096941745603)
VALIDATED_ROBUST_SIGN_FLIP_P = 3.333222225925803e-05
VALIDATED_ROBUST_ANIMAL_MEAN_LIFT = 0.11415032280591153
VALIDATED_ROBUST_PLANT_MEAN_LIFT = 0.057023839246432256
VALIDATED_ROBUST_STATUS = "untouched_confirmation_passed"


def validated_patch_columns(area_col: str = "survey_area_id") -> tuple[str, ...]:
    """Return the stable user-facing validated candidate-patch schema."""
    return (
        "candidate_patch_id",
        str(area_col),
        "latitude",
        "longitude",
        "support_cell_count",
        "candidate_patch_radius_m",
        "patch_merge_distance_m",
        "support_fraction",
        "validation_status",
    )


def _empty_patch_table(area_col: str) -> pd.DataFrame:
    """Return a readable zero-row product table when the frozen tier is empty."""
    return pd.DataFrame(columns=list(validated_patch_columns(area_col)))


def _project_validated_patch_table(patches: pd.DataFrame, *, area_col: str) -> pd.DataFrame:
    """Expose only candidate-patch fields in a neutral, non-priority row order."""
    if patches.empty:
        return _empty_patch_table(area_col)

    required = {
        "zone_id",
        area_col,
        "latitude",
        "longitude",
        "zone_member_count",
        "zone_radius_m",
    }
    missing = sorted(required.difference(patches.columns))
    if missing:
        raise ValueError(f"candidate-patch aggregation is missing required columns: {missing}")

    out = pd.DataFrame(
        {
            "candidate_patch_id": patches["zone_id"].astype(str),
            area_col: patches[area_col],
            "latitude": pd.to_numeric(patches["latitude"], errors="coerce"),
            "longitude": pd.to_numeric(patches["longitude"], errors="coerce"),
            "support_cell_count": pd.to_numeric(patches["zone_member_count"], errors="coerce").astype("Int64"),
            "candidate_patch_radius_m": pd.to_numeric(patches["zone_radius_m"], errors="coerce"),
            "patch_merge_distance_m": float(VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M),
            "support_fraction": float(VALIDATED_ROBUST_SUPPORT_FRACTION),
            "validation_status": VALIDATED_ROBUST_STATUS,
        }
    )
    # The legacy aggregation helper sorts its diagnostic table by a score. The
    # validated product has no patch ranking, so deliberately discard that row
    # order and use a stable identifier order instead. Zone numbering itself is
    # created before score sorting from deterministic candidate/universe order.
    out["_neutral_area_sort"] = out[area_col].astype(str)
    out = out.sort_values(
        ["_neutral_area_sort", "candidate_patch_id"],
        kind="mergesort",
    ).drop(columns="_neutral_area_sort").reset_index(drop=True)
    return out.loc[:, list(validated_patch_columns(area_col))]


def validated_robust_candidate_patches(
    universe: pd.DataFrame,
    prototypes: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    area_col: str = "survey_area_id",
) -> tuple[pd.DataFrame, RobustSupportAudit]:
    """Return the validated ACSP robust candidate-patch set.

    Scientific parameters are deliberately not user-tunable here. The function
    uses the independently confirmed 2.5% leave-one-prototype-out support tier,
    float32 support worlds, and 1 km same-area patch aggregation.

    The returned rows are candidate patches, not occupancy probabilities,
    exact occupied sites, route plans, priority rankings, or budget-optimal
    itineraries. Legacy planner scores/ranks and their row ordering are
    deliberately removed from the validated output.
    """
    consensus, _, audit = leave_one_out_consensus_support(
        universe,
        prototypes,
        feature_columns=feature_columns,
        support_world_dtype="float32",
    )
    _, raw_patches = support_cells_to_patches(
        universe,
        consensus,
        threshold=VALIDATED_ROBUST_SUPPORT_FRACTION,
        merge_distance_m=VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
        area_col=area_col,
        ecological_status="validated_cross_taxon_robust_support_patch",
    )
    patches = _project_validated_patch_table(raw_patches, area_col=area_col)
    return patches, audit
