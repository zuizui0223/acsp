"""Reusable ACSP survey-planning methods."""

from .field_validation import (
    DEFAULT_RECOVERY_RADII_KM,
    cluster_field_detections,
    detection_recovery_table,
    haversine_distance_m,
    normalize_field_locations,
    recovery_summary,
    stratified_random_recovery_benchmark,
)
from .gap_connectivity import (
    CorridorBarrierConfig,
    annotate_gap_patch_barriers,
    corridor_support_profile,
    summarize_corridor_barrier,
)
from .gap_patches import (
    GapPatchConfig,
    discover_gap_patches,
    patch_recovery_table,
    summarize_gap_patches,
)
from .gap_validation import (
    cluster_patch_recovery_table,
    select_gap_patches_within_travel_distance,
)
from .occurrence_patch_connectivity import (
    OccurrencePatchConnectivityConfig,
    annotate_occurrence_patch_connectivity,
    build_occurrence_patches,
)
from .planning import (
    DEFAULT_INTEGRATED_WEIGHTS,
    aggregate_candidates_to_zones,
    compare_zone_rankings,
    filter_candidates_to_extent,
    integrated_candidate_scores,
    normalize_extent,
    recommend_candidates,
    recommend_survey_zones,
    select_complementary_candidates,
    zone_agreement_summary,
)
from .modeling import DEFAULT_ENSEMBLE_ALGORITHMS, make_classifier, predict_equal_weight_ensemble
from .sdm import choose_spatial_partition, model_performance_table, sdm_method_record
from .validation import (
    calibrate_candidate_weights,
    clustered_recovery_inference,
    calibrate_model_ensemble_weights,
    multi_taxon_weight_benchmark,
    spatial_block_candidate_benchmark,
    spatial_block_recovery_validation,
    spatial_model_accuracy_benchmark,
    stratified_random_taxa,
)

__all__ = [
    "choose_spatial_partition",
    "DEFAULT_INTEGRATED_WEIGHTS",
    "DEFAULT_ENSEMBLE_ALGORITHMS",
    "DEFAULT_RECOVERY_RADII_KM",
    "GapPatchConfig",
    "CorridorBarrierConfig",
    "OccurrencePatchConnectivityConfig",
    "make_classifier",
    "model_performance_table",
    "filter_candidates_to_extent",
    "integrated_candidate_scores",
    "aggregate_candidates_to_zones",
    "compare_zone_rankings",
    "normalize_extent",
    "recommend_candidates",
    "recommend_survey_zones",
    "select_complementary_candidates",
    "discover_gap_patches",
    "summarize_gap_patches",
    "patch_recovery_table",
    "select_gap_patches_within_travel_distance",
    "cluster_patch_recovery_table",
    "corridor_support_profile",
    "summarize_corridor_barrier",
    "annotate_gap_patch_barriers",
    "build_occurrence_patches",
    "annotate_occurrence_patch_connectivity",
    "predict_equal_weight_ensemble",
    "sdm_method_record",
    "calibrate_candidate_weights",
    "clustered_recovery_inference",
    "calibrate_model_ensemble_weights",
    "multi_taxon_weight_benchmark",
    "spatial_block_candidate_benchmark",
    "spatial_block_recovery_validation",
    "spatial_model_accuracy_benchmark",
    "stratified_random_taxa",
    "zone_agreement_summary",
    "haversine_distance_m",
    "normalize_field_locations",
    "cluster_field_detections",
    "detection_recovery_table",
    "recovery_summary",
    "stratified_random_recovery_benchmark",
]

__version__ = "0.2.0-dev"
