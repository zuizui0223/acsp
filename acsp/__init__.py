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
from .occupancy_geometry import (
    OccupancyGeometry,
    infer_occupancy_geometry,
    minimum_spanning_tree,
    pairwise_distances,
    project_states,
    robust_scale,
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
    "OccupancyGeometry",
    "robust_scale",
    "pairwise_distances",
    "minimum_spanning_tree",
    "infer_occupancy_geometry",
    "project_states",
]

__version__ = "0.1.0"
