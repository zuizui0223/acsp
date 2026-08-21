"""Public ACSP API with lazy compatibility imports.

The validated candidate-patch path is intentionally independent from the
historical ranked-planner stack.  Public compatibility names remain available
at the package root, but their implementation modules are imported only when a
caller actually asks for those names.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS: dict[str, tuple[str, str]] = {
    # Automatic SDM compatibility API.
    "AUTO_SDM_VARIABLES": ("automatic_sdm", "AUTO_SDM_VARIABLES"),
    "AutomaticSdmCoreConfig": ("automatic_sdm", "AutomaticSdmCoreConfig"),
    "derive_power_bioclim": ("automatic_sdm", "derive_power_bioclim"),
    "fit_automatic_sdm_core": ("automatic_sdm", "fit_automatic_sdm_core"),
    "interpolate_power_bioclim": ("automatic_sdm", "interpolate_power_bioclim"),
    "score_automatic_sdm_candidates": ("automatic_sdm", "score_automatic_sdm_candidates"),
    "select_sdm_top_k": ("automatic_sdm", "select_sdm_top_k"),
    # Claim/status helpers.
    "CLAIM_MATRIX": ("claims", "CLAIM_MATRIX"),
    "claim_status_table": ("claims", "claim_status_table"),
    # Comparator and benchmark helpers.
    "ALL_METHODS": ("comparator_benchmark", "ALL_METHODS"),
    "ENVIRONMENTAL_METHODS": ("comparator_benchmark", "ENVIRONMENTAL_METHODS"),
    "UNIVERSAL_METHODS": ("comparator_benchmark", "UNIVERSAL_METHODS"),
    "StandardBaselineProtocol": ("comparator_benchmark", "StandardBaselineProtocol"),
    "comparator_inference": ("comparator_benchmark", "comparator_inference"),
    "evaluate_candidate_fold": ("comparator_benchmark", "evaluate_candidate_fold"),
    "pair_level_intention_to_evaluate": ("comparator_benchmark", "pair_level_intention_to_evaluate"),
    "select_heldout_greedy_oracle": ("comparator_benchmark", "select_heldout_greedy_oracle"),
    "ComparatorFold": ("comparator_export", "ComparatorFold"),
    "iter_comparator_folds": ("comparator_export", "iter_comparator_folds"),
    "write_comparator_pair_export": ("comparator_export", "write_comparator_pair_export"),
    "CoverageSelectionAudit": ("coverage", "CoverageSelectionAudit"),
    "select_maximum_coverage_sites": ("coverage", "select_maximum_coverage_sites"),
    "DecisionBaselineConfig": ("decision_baselines", "DecisionBaselineConfig"),
    "compare_decision_baselines": ("decision_baselines", "compare_decision_baselines"),
    "random_same_pool_sets": ("decision_baselines", "random_same_pool_sets"),
    "recovered_fraction": ("decision_baselines", "recovered_fraction"),
    "select_dual_space_farthest": ("decision_baselines", "select_dual_space_farthest"),
    "select_environmental_farthest": ("decision_baselines", "select_environmental_farthest"),
    "select_geographic_farthest": ("decision_baselines", "select_geographic_farthest"),
    "select_score_top_k": ("decision_baselines", "select_score_top_k"),
    # Field-validation helpers.
    "DEFAULT_RECOVERY_RADII_KM": ("field_validation", "DEFAULT_RECOVERY_RADII_KM"),
    "cluster_field_detections": ("field_validation", "cluster_field_detections"),
    "detection_recovery_table": ("field_validation", "detection_recovery_table"),
    "haversine_distance_m": ("field_validation", "haversine_distance_m"),
    "normalize_field_locations": ("field_validation", "normalize_field_locations"),
    "recovery_summary": ("field_validation", "recovery_summary"),
    "stratified_random_recovery_benchmark": ("field_validation", "stratified_random_recovery_benchmark"),
    # Historical planner compatibility API. Import only on explicit use.
    "DEFAULT_INTEGRATED_WEIGHTS": ("planning", "DEFAULT_INTEGRATED_WEIGHTS"),
    "aggregate_candidates_to_zones": ("planning", "aggregate_candidates_to_zones"),
    "compare_zone_rankings": ("planning", "compare_zone_rankings"),
    "filter_candidates_to_extent": ("planning", "filter_candidates_to_extent"),
    "integrated_candidate_scores": ("planning", "integrated_candidate_scores"),
    "normalize_extent": ("planning", "normalize_extent"),
    "recommend_candidates": ("planning", "recommend_candidates"),
    "recommend_survey_zones": ("planning", "recommend_survey_zones"),
    "select_complementary_candidates": ("planning", "select_complementary_candidates"),
    "zone_agreement_summary": ("planning", "zone_agreement_summary"),
    # Modeling compatibility API.
    "DEFAULT_ENSEMBLE_ALGORITHMS": ("modeling", "DEFAULT_ENSEMBLE_ALGORITHMS"),
    "make_classifier": ("modeling", "make_classifier"),
    "predict_equal_weight_ensemble": ("modeling", "predict_equal_weight_ensemble"),
    # Earlier frozen decision cores retained for historical/research use.
    "PRACTICAL_CORE_FINGERPRINT": ("practical_core", "PRACTICAL_CORE_FINGERPRINT"),
    "PRACTICAL_CORE_PROTOCOL_ID": ("practical_core", "PRACTICAL_CORE_PROTOCOL_ID"),
    "PracticalCorePolicy": ("practical_core", "PracticalCorePolicy"),
    "select_practical_core": ("practical_core", "select_practical_core"),
    "ValidatedCorePolicy": ("validated_core", "ValidatedCorePolicy"),
    "select_validated_core": ("validated_core", "select_validated_core"),
    # Current robust candidate-patch core.
    "RobustSupportAudit": ("robust_patches", "RobustSupportAudit"),
    "leave_one_out_consensus_support": ("robust_patches", "leave_one_out_consensus_support"),
    "robust_environment_geometry": ("robust_patches", "robust_environment_geometry"),
    "support_cells_to_patches": ("robust_patches", "support_cells_to_patches"),
    "VALIDATED_JAPAN_REGIONS": ("taxon_patches", "VALIDATED_JAPAN_REGIONS"),
    "discover_validated_candidate_patches": ("taxon_patches", "discover_validated_candidate_patches"),
    "discover_validated_candidate_patches_japan": ("taxon_patches", "discover_validated_candidate_patches_japan"),
    "validated_patch_columns": ("validated_robust", "validated_patch_columns"),
    "validated_robust_candidate_patches": ("validated_robust", "validated_robust_candidate_patches"),
    # SDM and retrospective validation helpers.
    "choose_spatial_partition": ("sdm", "choose_spatial_partition"),
    "model_performance_table": ("sdm", "model_performance_table"),
    "sdm_method_record": ("sdm", "sdm_method_record"),
    "calibrate_candidate_weights": ("validation", "calibrate_candidate_weights"),
    "clustered_recovery_inference": ("validation", "clustered_recovery_inference"),
    "calibrate_model_ensemble_weights": ("validation", "calibrate_model_ensemble_weights"),
    "multi_taxon_weight_benchmark": ("validation", "multi_taxon_weight_benchmark"),
    "spatial_block_candidate_benchmark": ("validation", "spatial_block_candidate_benchmark"),
    "spatial_block_recovery_validation": ("validation", "spatial_block_recovery_validation"),
    "spatial_model_accuracy_benchmark": ("validation", "spatial_model_accuracy_benchmark"),
    "stratified_random_taxa": ("validation", "stratified_random_taxa"),
}

__all__ = list(_EXPORTS)
__version__ = "0.1.0"


def __getattr__(name: str):
    """Resolve package-root compatibility exports on first use."""
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy public names to interactive discovery tools."""
    return sorted(set(globals()) | set(__all__))
