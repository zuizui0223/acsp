"""Reusable ACSP survey-planning methods."""

from .automatic_sdm import (
    AUTO_SDM_VARIABLES,
    AutomaticSdmCoreConfig,
    derive_power_bioclim,
    fit_automatic_sdm_core,
    interpolate_power_bioclim,
    score_automatic_sdm_candidates,
    select_sdm_top_k,
)
from .claims import CLAIM_MATRIX, claim_status_table
from .comparator_benchmark import (
    ALL_METHODS,
    ENVIRONMENTAL_METHODS,
    UNIVERSAL_METHODS,
    StandardBaselineProtocol,
    comparator_inference,
    evaluate_candidate_fold,
    pair_level_intention_to_evaluate,
    select_heldout_greedy_oracle,
)
from .comparator_export import ComparatorFold, iter_comparator_folds, write_comparator_pair_export
from .coverage import CoverageSelectionAudit, select_maximum_coverage_sites
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
from .practical_core import (
    PRACTICAL_CORE_FINGERPRINT,
    PRACTICAL_CORE_PROTOCOL_ID,
    PracticalCorePolicy,
    select_practical_core,
)
from .robust_patches import (
    RobustSupportAudit,
    leave_one_out_consensus_support,
    robust_environment_geometry,
    support_cells_to_patches,
)
from .taxon_patches import discover_validated_candidate_patches
from .validated_robust import validated_robust_candidate_patches
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
    "ALL_METHODS", "AUTO_SDM_VARIABLES", "AutomaticSdmCoreConfig", "CLAIM_MATRIX",
    "ComparatorFold", "CoverageSelectionAudit", "DecisionBaselineConfig", "ENVIRONMENTAL_METHODS",
    "PRACTICAL_CORE_FINGERPRINT", "PRACTICAL_CORE_PROTOCOL_ID", "PracticalCorePolicy",
    "RobustSupportAudit", "StandardBaselineProtocol", "UNIVERSAL_METHODS", "ValidatedCorePolicy",
    "choose_spatial_partition", "claim_status_table", "comparator_inference",
    "compare_decision_baselines", "DEFAULT_INTEGRATED_WEIGHTS", "DEFAULT_ENSEMBLE_ALGORITHMS",
    "DEFAULT_RECOVERY_RADII_KM", "derive_power_bioclim", "discover_validated_candidate_patches",
    "evaluate_candidate_fold", "fit_automatic_sdm_core", "interpolate_power_bioclim",
    "iter_comparator_folds", "make_classifier", "model_performance_table", "filter_candidates_to_extent",
    "integrated_candidate_scores", "aggregate_candidates_to_zones", "compare_zone_rankings", "normalize_extent",
    "pair_level_intention_to_evaluate", "random_same_pool_sets", "recommend_candidates",
    "recommend_survey_zones", "recovered_fraction", "robust_environment_geometry",
    "leave_one_out_consensus_support", "support_cells_to_patches", "score_automatic_sdm_candidates",
    "select_complementary_candidates", "select_dual_space_farthest", "select_environmental_farthest",
    "select_geographic_farthest", "select_heldout_greedy_oracle", "select_maximum_coverage_sites",
    "select_practical_core", "select_score_top_k", "select_sdm_top_k", "select_validated_core",
    "validated_robust_candidate_patches", "write_comparator_pair_export", "predict_equal_weight_ensemble",
    "sdm_method_record", "calibrate_candidate_weights", "clustered_recovery_inference",
    "calibrate_model_ensemble_weights", "multi_taxon_weight_benchmark", "spatial_block_candidate_benchmark",
    "spatial_block_recovery_validation", "spatial_model_accuracy_benchmark", "stratified_random_taxa",
    "zone_agreement_summary", "haversine_distance_m", "normalize_field_locations", "cluster_field_detections",
    "detection_recovery_table", "recovery_summary", "stratified_random_recovery_benchmark",
]

__version__ = "0.1.0"
