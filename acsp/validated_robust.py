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


def _empty_patch_table(area_col: str) -> pd.DataFrame:
    """Return a readable zero-row product table when the frozen tier is empty."""
    return pd.DataFrame(
        columns=[
            "zone_id",
            area_col,
            "zone_score",
            "zone_rank",
            "zone_member_count",
            "zone_radius_m",
            "zone_merge_threshold_m",
            "representative_site_id",
            "latitude",
            "longitude",
            "site_id",
            "ecological_support_threshold",
            "ecological_status",
            "validation_status",
            "validation_support_fraction",
            "validation_primary_radius_km",
            "validation_confirmation_pairs",
            "validation_confirmation_folds",
            "validation_mean_lift_over_random",
        ]
    )


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
    exact occupied sites, route plans, or budget-optimal itineraries.
    """
    consensus, _, audit = leave_one_out_consensus_support(
        universe,
        prototypes,
        feature_columns=feature_columns,
        support_world_dtype="float32",
    )
    _, patches = support_cells_to_patches(
        universe,
        consensus,
        threshold=VALIDATED_ROBUST_SUPPORT_FRACTION,
        merge_distance_m=VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
        area_col=area_col,
        ecological_status="validated_cross_taxon_robust_support_patch",
    )
    if patches.empty:
        patches = _empty_patch_table(area_col)
    else:
        patches = patches.copy()
        patches["validation_status"] = VALIDATED_ROBUST_STATUS
        patches["validation_support_fraction"] = VALIDATED_ROBUST_SUPPORT_FRACTION
        patches["validation_primary_radius_km"] = VALIDATED_ROBUST_PRIMARY_RADIUS_KM
        patches["validation_confirmation_pairs"] = VALIDATED_ROBUST_CONFIRMATION_PAIRS
        patches["validation_confirmation_folds"] = VALIDATED_ROBUST_CONFIRMATION_FOLDS
        patches["validation_mean_lift_over_random"] = VALIDATED_ROBUST_MEAN_LIFT_OVER_RANDOM
    return patches.reset_index(drop=True), audit
