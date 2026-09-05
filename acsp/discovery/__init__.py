"""Experimental N4 discovery primitives and high-level workflow.

This subpackage generalizes the current occurrence-to-next-observation development
line without broadening the independently validated robust candidate-patch claim.
It is intentionally not imported from :mod:`acsp` at package import time.

Scientific boundary
-------------------
``acsp.discovery`` is DEVELOPMENT-ONLY until separately confirmed. It provides
reusable mechanics for evidence typing, regime resolution, candidate-frame
construction, structural support, and strong same-frame comparators. It does not
claim occupancy, field efficiency, optimal budgets, routes, or stopping rules.
"""

from .comparators import (
    ComparatorAudit,
    rank_morton_dyadic_spatial_balance,
    rank_nearest_anchor,
    select_stable_start_maximin,
)
from .evidence import (
    OccurrenceCluster,
    cluster_medoid,
    cluster_medoid_table,
    cluster_min_distance_km,
    complete_link_clusters,
    haversine_km,
)
from .families import StructuralFamilySpec, get_structural_family_spec, list_structural_families
from .frames import AnnularFrameAudit, AnnularFrameSpec, build_annular_candidate_frame
from .regimes import DiscoveryEvidenceProfile, DiscoveryRegime, RegimeDecision, resolve_discovery_regime
from .schemas import (
    CandidateFrameSchemaAudit,
    OccurrenceEvidenceAudit,
    SourceManifestAudit,
    normalize_occurrence_evidence,
    validate_candidate_frame_schema,
    validate_source_manifest,
)
from .structural import StructuralOrderAudit, build_structural_support_order
from .workflow import (
    DiscoveryAssessment,
    DiscoveryContext,
    DiscoveryRankingAudit,
    EvidencePolicy,
    assess_occurrence_evidence,
    rank_discovery_frame,
    summarize_rankings,
)

DISCOVERY_API_VERSION = "0.2.0-development"
DISCOVERY_VALIDATION_STATUS = "experimental_not_independently_validated"

__all__ = [
    "DISCOVERY_API_VERSION",
    "DISCOVERY_VALIDATION_STATUS",
    "OccurrenceCluster",
    "haversine_km",
    "cluster_min_distance_km",
    "complete_link_clusters",
    "cluster_medoid",
    "cluster_medoid_table",
    "AnnularFrameSpec",
    "AnnularFrameAudit",
    "build_annular_candidate_frame",
    "DiscoveryRegime",
    "DiscoveryEvidenceProfile",
    "RegimeDecision",
    "resolve_discovery_regime",
    "StructuralOrderAudit",
    "build_structural_support_order",
    "StructuralFamilySpec",
    "get_structural_family_spec",
    "list_structural_families",
    "ComparatorAudit",
    "rank_nearest_anchor",
    "select_stable_start_maximin",
    "rank_morton_dyadic_spatial_balance",
    "OccurrenceEvidenceAudit",
    "CandidateFrameSchemaAudit",
    "SourceManifestAudit",
    "normalize_occurrence_evidence",
    "validate_candidate_frame_schema",
    "validate_source_manifest",
    "EvidencePolicy",
    "DiscoveryContext",
    "DiscoveryAssessment",
    "DiscoveryRankingAudit",
    "assess_occurrence_evidence",
    "rank_discovery_frame",
    "summarize_rankings",
]
