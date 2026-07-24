"""Reusable ACSP survey-planning methods."""

from .claims import CLAIM_MATRIX, claim_status_table
from .decision_baselines import (
    DecisionBaselineConfig,
    compare_decision_baselines,
    random_same_pool_sets,
    recovered_fraction,
    select_dual_space_farthest,
    select_environmental_farthest,
    select_geographic_farthest,
    select_score_top_k,
)
from .field_validation import (
    DEFAULT_RECOVERY_RADII_KM,
    cluster_field_detections,
    detection_recovery_table,
    haversine_distance_m,
    normalize_field_locations,
    recovery_summary,
    stratified_random_recovery_benchmark,
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
from .validated_core import ValidatedCorePolicy, select_validated_core
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
    "CLAIM_MATRIX",
    "DecisionBaselineConfig",
    "ValidatedCorePolicy",
    "choose_spatial_partition",
    "claim_status_table",
    "compare_decision_baselines",
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
    "random_same_pool_sets",
    "recommend_candidates",
    "recommend_survey_zones",
    "recovered_fraction",
    "select_complementary_candidates",
    "select_dual_space_farthest",
    "select_environmental_farthest",
    "select_geographic_farthest",
    "select_score_top_k",
    "select_validated_core",
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

__version__ = "0.1.0"
