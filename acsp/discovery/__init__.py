"""Experimental N4 discovery primitives.

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

from .evidence import (
    OccurrenceCluster,
    cluster_medoid,
    cluster_medoid_table,
    cluster_min_distance_km,
    complete_link_clusters,
    haversine_km,
)
from .frames import AnnularFrameAudit, AnnularFrameSpec, build_annular_candidate_frame
from .regimes import DiscoveryEvidenceProfile, DiscoveryRegime, RegimeDecision, resolve_discovery_regime
from .structural import StructuralOrderAudit, build_structural_support_order

DISCOVERY_API_VERSION = "0.1.0-development"
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
]
