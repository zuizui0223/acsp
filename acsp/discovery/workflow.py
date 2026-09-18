"""High-level, fail-closed workflow for experimental N4 discovery.

This module encodes the common structure that survived repeated development
failures: population-level occurrence evidence, explicit regime gates, a frozen
candidate frame before ranking, structural/process information separated from
access, and strong same-frame comparators. It never fits a distance-environment
blend and never invents a local search radius when none is declared.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import pandas as pd

from .comparators import rank_morton_dyadic_spatial_balance, rank_nearest_anchor
from .evidence import cluster_medoid_table, complete_link_clusters
from .families import get_structural_family_spec
from .regimes import DiscoveryEvidenceProfile, DiscoveryRegime, resolve_discovery_regime
from .schemas import (
    CandidateFrameSchemaAudit,
    SourceManifestAudit,
    normalize_occurrence_evidence,
    validate_candidate_frame_schema,
    validate_source_manifest,
)
from .structural import StructuralOrderAudit, build_structural_support_order


_ECOLOGY_FORBIDDEN_COLUMN_TOKENS = (
    "field_outcome",
    "field_success",
    "detected",
    "detection_state",
    "tissue_acquired",
    "distance_to_road",
    "road_distance",
    "distance_to_trail",
    "trail_distance",
    "access_score",
    "permission",
    "route_",
    "travel_",
    "budget",
    "field_cost",
    "search_minutes",
    "survey_time",
)
_ECOLOGY_FORBIDDEN_SOURCE_TOKENS = (
    "road",
    "trail",
    "access",
    "permission",
    "route",
    "travel",
    "budget",
    "field_cost",
)


def _forbidden_ecology_columns(columns: Iterable[str]) -> list[str]:
    found: list[str] = []
    for column in columns:
        lowered = str(column).strip().lower()
        if any(token in lowered for token in _ECOLOGY_FORBIDDEN_COLUMN_TOKENS):
            found.append(str(column))
    return sorted(set(found))


def _forbidden_ecology_source_roles(roles: Iterable[str]) -> list[str]:
    found: list[str] = []
    for role in roles:
        lowered = str(role).strip().lower()
        if any(token in lowered for token in _ECOLOGY_FORBIDDEN_SOURCE_TOKENS):
            found.append(str(role))
    return sorted(set(found))


@dataclass(frozen=True)
class EvidencePolicy:
    """Transparent occurrence-to-population evidence policy.

    The defaults are conservative development defaults carried forward from the
    current public fine-scale diagnostics. They are not universal biological
    constants and are reported in every assessment.
    """

    exact_anchor_max_uncertainty_m: float = 1000.0
    population_cluster_radius_km: float = 0.5
    require_declared_uncertainty_for_exact_anchor: bool = True

    def validate(self) -> None:
        if float(self.exact_anchor_max_uncertainty_m) < 0:
            raise ValueError("exact_anchor_max_uncertainty_m cannot be negative")
        if float(self.population_cluster_radius_km) <= 0:
            raise ValueError("population_cluster_radius_km must be positive")


@dataclass(frozen=True)
class DiscoveryContext:
    """Source-backed ecological context supplied to the regime gate.

    No field outcome may be used to set these flags. In particular,
    ``local_component_justified`` is not inferred from anchor count alone.
    """

    local_component_justified: bool = False
    detached_component_available: bool = False
    sentinel_context_available: bool = False
    sentinel_subregime: str = ""

    def validate(self) -> None:
        active = sum(
            int(value)
            for value in (
                self.local_component_justified,
                self.detached_component_available,
                self.sentinel_context_available,
            )
        )
        if active > 1:
            raise ValueError("LOCAL, DETACHED and SENTINEL contexts are mutually exclusive for one discovery run")
        if self.sentinel_subregime and not self.sentinel_context_available:
            raise ValueError("sentinel_subregime requires SENTINEL context")


@dataclass(frozen=True)
class DiscoveryAssessment:
    status: str
    regime: str
    reason: str
    next_step: str
    occurrence_rows: int
    exact_anchor_rows: int
    population_anchor_count: int
    rows_missing_declared_uncertainty: int
    rows_above_exact_uncertainty_limit: int
    policy: dict[str, Any]
    occurrence_audit: dict[str, Any]
    warnings: tuple[str, ...]
    validated_product_changed: bool = False
    independent_confirmation_claim: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveryRankingAudit:
    status: str
    regime: str
    feature_family: str
    methods: tuple[str, ...]
    candidate_audit: dict[str, Any]
    source_audit: dict[str, Any]
    structural_audit: dict[str, Any] | None
    no_fitted_blend: bool = True
    same_candidate_frame_for_all_methods: bool = True
    field_outcomes_used: bool = False
    human_access_used: bool = False
    validated_product_changed: bool = False
    independent_confirmation_claim: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_occurrence_evidence(
    occurrence_frame: pd.DataFrame,
    *,
    context: DiscoveryContext | None = None,
    policy: EvidencePolicy | None = None,
) -> tuple[DiscoveryAssessment, pd.DataFrame]:
    """Convert occurrence rows to population evidence and resolve a safe regime.

    Returns a human-readable assessment plus deterministic population medoids.
    When evidence is insufficient the function returns an ABSTAIN assessment
    rather than manufacturing a wider local frame.
    """
    cfg = policy or EvidencePolicy()
    cfg.validate()
    ctx = context or DiscoveryContext()
    ctx.validate()
    normalized, occurrence_audit = normalize_occurrence_evidence(occurrence_frame)

    uncertainty = pd.to_numeric(normalized["coordinate_uncertainty_m"], errors="coerce")
    declared = uncertainty.notna()
    exact = uncertainty.le(float(cfg.exact_anchor_max_uncertainty_m))
    if cfg.require_declared_uncertainty_for_exact_anchor:
        exact &= declared
    exact_rows = normalized.loc[exact].copy().reset_index(drop=True)

    clusters = complete_link_clusters(
        exact_rows,
        radius_km=float(cfg.population_cluster_radius_km),
        latitude_col="latitude",
        longitude_col="longitude",
        id_col="occurrence_id",
    )
    medoids = cluster_medoid_table(clusters, prefix="P")
    decision = resolve_discovery_regime(
        DiscoveryEvidenceProfile(
            exact_anchor_count=int(len(medoids)),
            local_component_justified=bool(ctx.local_component_justified),
            detached_component_available=bool(ctx.detached_component_available),
            sentinel_context_available=bool(ctx.sentinel_context_available),
            sentinel_subregime=str(ctx.sentinel_subregime),
        )
    )

    missing_uncertainty = int((~declared).sum())
    above_limit = int((declared & ~uncertainty.le(float(cfg.exact_anchor_max_uncertainty_m))).sum())
    warnings: list[str] = []
    if missing_uncertainty:
        warnings.append(
            f"{missing_uncertainty} occurrence rows lack declared coordinate uncertainty and were not treated as exact anchors"
        )
    if above_limit:
        warnings.append(
            f"{above_limit} occurrence rows exceed the exact-anchor uncertainty limit and remain contextual rather than exact evidence"
        )
    if len(medoids) == 0:
        warnings.append("no bounded population anchor could be reconstructed from exact-enough occurrence evidence")
    if len(exact_rows) and len(medoids) < len(exact_rows):
        warnings.append(
            "repeated occurrence rows were collapsed to bounded population clusters so record density does not masquerade as independent populations"
        )

    if decision.regime == DiscoveryRegime.LOCAL_CONTINUATION:
        status = "READY_FOR_DECLARED_LOCAL_FRAME"
        next_step = "Provide or freeze a candidate frame/sector; do not infer a universal local radius from distance alone."
    elif decision.regime == DiscoveryRegime.DETACHED_COMPONENT:
        status = "READY_FOR_DETACHED_COMPONENT_FRAME"
        next_step = "Provide the source-backed detached candidate component and structural layers."
    elif decision.regime == DiscoveryRegime.SENTINEL:
        status = "READY_FOR_SENTINEL_FRAME"
        next_step = "Provide the declared sentinel/context frame and source provenance; exact local interpolation is not justified."
    elif len(medoids) > 0:
        status = "CONTEXT_REQUIRED"
        next_step = (
            "Exact population evidence exists, but no ecological component is justified. "
            "Declare source-backed LOCAL/DETACHED/SENTINEL context or keep ABSTAIN."
        )
    else:
        status = "ABSTAIN_INSUFFICIENT_EXACT_EVIDENCE"
        next_step = (
            "Do not relax coordinate precision or widen the search after seeing outcomes. "
            "Use a justified SENTINEL/DETACHED context, a better provider, or collect better occurrence evidence."
        )

    assessment = DiscoveryAssessment(
        status=status,
        regime=decision.regime.value,
        reason=decision.reason,
        next_step=next_step,
        occurrence_rows=int(len(normalized)),
        exact_anchor_rows=int(len(exact_rows)),
        population_anchor_count=int(len(medoids)),
        rows_missing_declared_uncertainty=missing_uncertainty,
        rows_above_exact_uncertainty_limit=above_limit,
        policy=asdict(cfg),
        occurrence_audit=asdict(occurrence_audit),
        warnings=tuple(warnings),
    )
    return assessment, medoids


def rank_discovery_frame(
    candidate_frame: pd.DataFrame,
    *,
    assessment: DiscoveryAssessment,
    source_manifest: dict[str, Any],
    feature_family: str | None = None,
    source_provenance: dict[str, Any] | None = None,
    target_component_id: str | None = None,
    graph_radius_cells: int = 1,
) -> tuple[dict[str, pd.DataFrame], DiscoveryRankingAudit]:
    """Rank one frozen candidate frame with separate non-blended methods.

    Structural support is optional. Spatial balance is always produced. The
    nearest-known comparator is produced only for LOCAL_CONTINUATION when the
    candidate frame carries a complete ``nearest_anchor_km`` column.

    Field outcomes and human movement/access variables are forbidden here. They
    belong downstream of ecological candidate generation.
    """
    if assessment.regime == DiscoveryRegime.ABSTAIN_LOCAL_PATCH.value:
        raise ValueError("cannot rank a local discovery frame while the assessment is ABSTAIN")

    forbidden_columns = _forbidden_ecology_columns(candidate_frame.columns)
    if forbidden_columns:
        raise ValueError(
            "ecological discovery frame contains field-outcome or human-feasibility columns that belong downstream in G_F: "
            + ", ".join(forbidden_columns)
        )

    candidate_audit: CandidateFrameSchemaAudit = validate_candidate_frame_schema(candidate_frame)
    source_audit: SourceManifestAudit = validate_source_manifest(source_manifest)
    forbidden_roles = _forbidden_ecology_source_roles(source_audit.roles)
    if forbidden_roles:
        raise ValueError(
            "source manifest contains human-feasibility roles that cannot create ecological support: "
            + ", ".join(forbidden_roles)
        )

    rankings: dict[str, pd.DataFrame] = {}
    structural_audit: StructuralOrderAudit | None = None

    spatial, _ = rank_morton_dyadic_spatial_balance(candidate_frame)
    rankings["DETERMINISTIC_SPATIAL_BALANCE"] = spatial

    if (
        assessment.regime == DiscoveryRegime.LOCAL_CONTINUATION.value
        and candidate_audit.nearest_anchor_distance_available
    ):
        rankings["ANNULAR_NEAREST_KNOWN"] = rank_nearest_anchor(candidate_frame)

    family_id = str(feature_family or "").strip()
    if family_id:
        family = get_structural_family_spec(family_id)
        missing = sorted(set(family.required_raw_columns).difference(candidate_frame.columns))
        if missing:
            raise ValueError(
                f"candidate frame lacks pre-graph raw columns required by {family.family_id}: {missing}. "
                f"Required source roles: {', '.join(family.source_roles)}"
            )
        if family.family_id == "COASTAL_ISLAND_STRUCTURE" and not str(target_component_id or "").strip():
            raise ValueError("COASTAL_ISLAND_STRUCTURE requires a predeclared target_component_id")
        provenance = source_provenance or {
            "source_manifest": source_manifest,
            "family_id": family.family_id,
        }
        structural, structural_audit = build_structural_support_order(
            candidate_frame,
            feature_family=family.family_id,
            source_provenance=provenance,
            target_component_id=target_component_id,
            graph_radius_cells=int(graph_radius_cells),
        )
        rankings["STRUCTURAL_SUPPORT"] = structural

    audit = DiscoveryRankingAudit(
        status="RANKINGS_READY_DEVELOPMENT_ONLY",
        regime=assessment.regime,
        feature_family=family_id,
        methods=tuple(rankings.keys()),
        candidate_audit=asdict(candidate_audit),
        source_audit=asdict(source_audit),
        structural_audit=None if structural_audit is None else asdict(structural_audit),
    )
    return rankings, audit


def summarize_rankings(rankings: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return a coordinate-free summary suitable for logs and public artifacts."""
    rows: list[dict[str, Any]] = []
    for method, frame in rankings.items():
        if frame.empty:
            rows.append({"method": method, "candidate_count": 0, "first_candidate_id": ""})
            continue
        first_id = str(frame.iloc[0].get("candidate_cell_id", ""))
        rows.append(
            {
                "method": str(method),
                "candidate_count": int(len(frame)),
                "first_candidate_id": first_id,
                "decision_rank_complete": bool(
                    "decision_rank" in frame.columns
                    and frame["decision_rank"].tolist() == list(range(1, len(frame) + 1))
                ),
            }
        )
    return pd.DataFrame(rows)
