"""Experimental N4 discovery primitives and high-level workflow.

This subpackage generalizes the current occurrence-to-next-observation development
line without broadening the independently validated robust candidate-patch claim.
It is intentionally not imported from :mod:`acsp` at package import time.

Scientific boundary
-------------------
``acsp.discovery`` is DEVELOPMENT-ONLY until separately confirmed. It provides
reusable mechanics for evidence typing, availability/evaluability separation,
provider-aware country framing, regime resolution, candidate-frame construction,
structural support, scale-separated coverage/localization, and strong same-frame
comparators. It does not claim occupancy, field efficiency, optimal budgets,
routes, or stopping rules.
"""


DISCOVERY_API_VERSION = "0.8.0-development"
DISCOVERY_VALIDATION_STATUS = "experimental_not_independently_validated"

from importlib import import_module

# Preserve the public interface without loading unrelated experimental modules.
_EXPORT_MODULES = {
    "availability": "AvailabilityDecision AvailabilityState resolve_availability_state".split(),
    "broad_frames": "DetachedPartitionAudit RectangularFrameAudit attach_nearest_anchor_distance build_rectangular_candidate_frame partition_local_and_detached".split(),
    "comparators": "ComparatorAudit rank_morton_dyadic_spatial_balance rank_nearest_anchor select_stable_start_maximin".split(),
    "component_workflow": "WorldCoverComponentPreparationAudit prepare_worldcover_component_partition".split(),
    "components": "ComponentPartitionAudit partition_candidate_components".split(),
    "country_frames": "CountryFrameCandidate CountryFramePlan CountryFrameState plan_automatic_global_country plan_explicit_target_country rank_historical_country_frames".split(),
    "evidence": "OccurrenceCluster cluster_medoid cluster_medoid_table cluster_min_distance_km complete_link_clusters haversine_km".split(),
    "families": "StructuralFamilySpec get_structural_family_spec list_structural_families".split(),
    "frames": "AnnularFrameAudit AnnularFrameSpec build_annular_candidate_frame".split(),
    "lanes": "DiscoveryLane DiscoveryLaneEvidence DiscoveryLanePlan plan_discovery_lanes".split(),
    "recipes": "StructuralRecipe StructuralRecipeAudit evaluate_structural_recipe get_structural_recipe rank_structural_recipe".split(),
    "regimes": "DiscoveryEvidenceProfile DiscoveryRegime RegimeDecision resolve_discovery_regime".split(),
    "scale_separated": "CoverageThenStructureAudit rank_coverage_then_fine_structure".split(),
    "schemas": "CandidateFrameSchemaAudit OccurrenceEvidenceAudit SourceManifestAudit normalize_occurrence_evidence validate_candidate_frame_schema validate_source_manifest".split(),
    "structural": "StructuralOrderAudit build_structural_support_order".split(),
    "workflow": "DiscoveryAssessment DiscoveryContext DiscoveryRankingAudit EvidencePolicy assess_occurrence_evidence rank_discovery_frame summarize_rankings".split(),
}
_LAZY_EXPORTS = {name: module for module, names in _EXPORT_MODULES.items() for name in names}


def __getattr__(name):
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "DISCOVERY_API_VERSION", "DISCOVERY_VALIDATION_STATUS",
    "AvailabilityState", "AvailabilityDecision", "resolve_availability_state",
    "CountryFrameState", "CountryFrameCandidate", "CountryFramePlan", "rank_historical_country_frames", "plan_automatic_global_country", "plan_explicit_target_country",
    "OccurrenceCluster", "haversine_km", "cluster_min_distance_km", "complete_link_clusters", "cluster_medoid", "cluster_medoid_table",
    "AnnularFrameSpec", "AnnularFrameAudit", "build_annular_candidate_frame",
    "RectangularFrameAudit", "DetachedPartitionAudit", "build_rectangular_candidate_frame", "attach_nearest_anchor_distance", "partition_local_and_detached",
    "ComponentPartitionAudit", "partition_candidate_components",
    "WorldCoverComponentPreparationAudit", "prepare_worldcover_component_partition",
    "DiscoveryRegime", "DiscoveryEvidenceProfile", "RegimeDecision", "resolve_discovery_regime",
    "DiscoveryLane", "DiscoveryLaneEvidence", "DiscoveryLanePlan", "plan_discovery_lanes",
    "StructuralOrderAudit", "build_structural_support_order",
    "CoverageThenStructureAudit", "rank_coverage_then_fine_structure",
    "StructuralFamilySpec", "get_structural_family_spec", "list_structural_families",
    "StructuralRecipe", "StructuralRecipeAudit", "get_structural_recipe", "evaluate_structural_recipe", "rank_structural_recipe",
    "ComparatorAudit", "rank_nearest_anchor", "select_stable_start_maximin", "rank_morton_dyadic_spatial_balance",
    "OccurrenceEvidenceAudit", "CandidateFrameSchemaAudit", "SourceManifestAudit", "normalize_occurrence_evidence", "validate_candidate_frame_schema", "validate_source_manifest",
    "EvidencePolicy", "DiscoveryContext", "DiscoveryAssessment", "DiscoveryRankingAudit", "assess_occurrence_evidence", "rank_discovery_frame", "summarize_rankings",
]
