"""Connect historical country planning to the frozen global patch machinery.

This is a product adapter, not a fresh scientific confirmation. It preserves
the complete regional lattice and never selects tiles from focal occurrences.
"""
from __future__ import annotations

import pandas as pd

from .discovery.country_entry import plan_country_for_species
from .global_geometry import fetch_geoboundaries_country_geometry
from .global_inputs import fetch_country_occurrences
from .global_lattice import POINTS_PER_REGIONAL_TILE, build_regional_country_surface
from .taxon_patches import RAW_TERRAIN_FEATURES, ROBUST_TERRAIN_FEATURES, _prototype_coordinates, _with_robust_features
from .validated_robust import validated_patch_columns, validated_robust_candidate_patches

METHOD_FINGERPRINT = "7535e749d3cc04c8d49db13957da53685a5050eec7d1e9e2d6624348332a56f9"
EVIDENCE_FAILURE_PREFIXES = (
    "GBIF returned no usable historical occurrence rows in ",
    "fewer than five usable historical occurrence rows in ",
    "regional lattice has no complete terrain surface points",
    "fewer than five unique complete historical terrain prototypes:",
)


def _empty_patches() -> pd.DataFrame:
    return pd.DataFrame(columns=[*validated_patch_columns(), "speciesKey", "scientific_name", "framing_country_code"])


def regional_terrain_inputs(occurrences: pd.DataFrame, geometry):
    from gbif_fieldmap_builder_app import extract_environment
    geometry_surface,lattice_audit=build_regional_country_surface(geometry,points_per_tile=POINTS_PER_REGIONAL_TILE)
    enriched=extract_environment(geometry_surface,list(RAW_TERRAIN_FEATURES),"latitude","longitude","2.5m")
    surface=_with_robust_features(enriched)
    surface=surface.loc[surface[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)].copy().reset_index(drop=True)
    if surface.empty: raise ValueError("regional lattice has no complete terrain surface points")
    proto_points=_prototype_coordinates(occurrences)
    prototypes=extract_environment(proto_points,list(RAW_TERRAIN_FEATURES),"latitude","longitude","2.5m")
    prototypes=_with_robust_features(prototypes)
    prototypes=prototypes.loc[prototypes[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)].copy().drop_duplicates(list(ROBUST_TERRAIN_FEATURES)).reset_index(drop=True)
    if len(prototypes)<5: raise ValueError(f"fewer than five unique complete historical terrain prototypes: {len(prototypes)}")
    return surface,prototypes,lattice_audit


def discover_global_candidate_patches(scientific_name: str, *, country: str = "", progress=None):
    """Return non-ranked patches and an audit, or an explicit unavailable state.

    Provider/computation exceptions propagate; no country, geometry, threshold,
    surface density, or species is substituted to rescue a failed execution.
    Large country lattices may be expensive: all tiles are retained.
    """
    def report(phase, details):
        if progress is not None:
            progress(phase, details)

    report("PLANNING_COUNTRY", {})
    plan = plan_country_for_species(scientific_name, country=country)
    audit = {
        "schema_version": "acsp-global-candidate-patches-v1",
        "method_fingerprint": METHOD_FINGERPRINT,
        "country_plan": plan,
        "candidate_generation_run": False,
        "heldout_2021_2025_opened": False,
        "field_outcomes_used": False,
        "new_scientific_confirmation": False,
        "warning": "Non-ranked candidate patches, not occupancy or field efficiency. The automatic adapter has a bounded tested cohort; arbitrary explicit-country searches are not independently confirmed.",
    }
    report("COUNTRY_PLANNED", {"country_plan": plan})
    if plan["status"] != "READY":
        return _empty_patches(), {**audit, "status": plan["status"], "candidate_patch_count": 0}
    code = plan["country_plan"]["selected_country_code"]
    key = int(plan["matched_usage_key"])
    geometry = fetch_geoboundaries_country_geometry(code)
    if geometry.normalized_code() != code:
        raise ValueError("geometry country differs from selected country; no substitution allowed")
    audit["country_geometry_source_id"] = geometry.source_id
    audit["country_geometry_source_version"] = geometry.source_version
    report("GEOMETRY_RECEIVED", {"selected_country": code, "source_version": geometry.source_version})
    try:
        historical = fetch_country_occurrences(key, code)
        audit["historical_training_occurrence_rows"] = len(historical)
        report("BUILDING_TERRAIN", {"historical_training_occurrence_rows": len(historical)})
        surface, prototypes, lattice_audit = regional_terrain_inputs(historical, geometry)
    except ValueError as exc:
        if not any(str(exc).startswith(prefix) for prefix in EVIDENCE_FAILURE_PREFIXES):
            raise
        return _empty_patches(), {**audit, "status": "SENTINEL_OR_ABSTAIN", "evidence_failure_reason": str(exc), "candidate_patch_count": 0}
    if len(prototypes) > 32:
        raise ValueError("prototype rule drift: expected <=32")
    audit.update({"lattice_audit": lattice_audit.as_dict(), "complete_terrain_surface_points": len(surface), "prototype_rows": len(prototypes)})
    report("GENERATING_PATCHES", {"complete_terrain_surface_points": len(surface), "prototype_rows": len(prototypes)})
    patches, support = validated_robust_candidate_patches(surface, prototypes, feature_columns=ROBUST_TERRAIN_FEATURES, area_col="survey_area_id")
    patches = patches.copy()
    # Do not attach the Japanese confirmation label to a global application.
    patches["validation_status"] = "explicit_country_application_not_independently_confirmed" if country else "automatic_global_adapter_application"
    patches["speciesKey"] = key
    patches["scientific_name"] = plan["matched_scientific_name"]
    patches["framing_country_code"] = code
    audit.update({"status": "ROBUST_READY" if len(patches) else "ROBUST_EMPTY", "candidate_generation_run": True, "candidate_patch_count": len(patches), "support_audit": support.as_dict()})
    return patches, audit
