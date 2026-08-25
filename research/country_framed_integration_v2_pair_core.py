#!/usr/bin/env python3
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from acsp.taxon_patches import ROBUST_TERRAIN_FEATURES
from acsp.validated_robust import VALIDATED_ROBUST_PRIMARY_RADIUS_KM, validated_robust_candidate_patches
from country_framed_robust_integration import fetch_country_occurrences
from geoboundaries_v6_provider import fetch_geoboundaries_country_geometry
from run_country_framed_integration_development_v1_1 import (
    _geometry_digest_from_source_version,
    fetch_recent_country_occurrences,
    recovery_fraction,
    same_size_random_recovery,
)
from run_country_framed_integration_development_v2 import _protocol, regional_terrain_inputs


def evaluate_one_v2_core(declaration: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate one frozen declaration with the authoritative v2 scientific method."""
    protocol = _protocol()
    evalcfg = protocol["evaluation"]
    radius = float(evalcfg["primary_recovery_radius_km"])
    reps = int(evalcfg["random_baseline_repetitions"])
    seedbase = int(evalcfg["random_seed"])
    if radius != 10.0 or radius != float(VALIDATED_ROBUST_PRIMARY_RADIUS_KM):
        raise ValueError("v2 radius drift")

    base = declaration.to_dict()
    pair_id = int(base["integration_pair_id"])
    key = int(base["speciesKey"])
    code = str(base.get("selected_country_code") or "").upper()
    declaration_status = str(base.get("declaration_status") or "")

    cstatus = "not_attempted_declaration_failed"
    creason = ""
    tstatus = "not_attempted_no_declared_country"
    treason = ""
    hist_n = recent_n = tiles = geom_n = complete_n = proto_n = patch_n = 0
    robust = random_mean = random_q025 = random_q975 = lift = float("nan")
    verified = ""
    patches = pd.DataFrame()
    surface = pd.DataFrame()

    if declaration_status == "declared" and code:
        try:
            geom = fetch_geoboundaries_country_geometry(code)
            verified = _geometry_digest_from_source_version(geom.source_version)
            if verified != str(base.get("geometry_canonical_sha256") or "").lower():
                raise ValueError("frozen country geometry digest mismatch")
            historical = fetch_country_occurrences(key, code)
            hist_n = len(historical)
            surface, prototypes, audit = regional_terrain_inputs(historical, geom)
            tiles = int(audit.intersecting_tile_count)
            geom_n = int(audit.total_geometry_points)
            complete_n = len(surface)
            proto_n = len(prototypes)
            patches, _ = validated_robust_candidate_patches(
                surface,
                prototypes,
                feature_columns=ROBUST_TERRAIN_FEATURES,
                area_col="survey_area_id",
            )
            patch_n = len(patches)
            if patch_n <= 0:
                raise ValueError("frozen robust core returned zero candidate patches")
            cstatus = "generated"
            patches = patches.copy()
            patches["integration_pair_id"] = pair_id
            patches["speciesKey"] = key
            patches["scientific_name"] = str(base["scientific_name"])
            patches["taxon_group"] = str(base["taxon_group"])
            patches["framing_country_code"] = code
        except Exception as exc:
            cstatus = "candidate_generation_failed"
            creason = f"{type(exc).__name__}: {exc}"

        # This call must stay after candidate generation. It opens the heldout endpoint.
        try:
            recent = fetch_recent_country_occurrences(key, code, years=(2021, 2025), cap=300)
            recent_n = len(recent)
            tstatus = "evaluated" if recent_n > 0 else "zero_recent_country_records"
        except Exception as exc:
            recent = pd.DataFrame(columns=["latitude", "longitude"])
            tstatus = "recent_provider_failed"
            treason = f"{type(exc).__name__}: {exc}"

        if cstatus == "generated" and tstatus == "evaluated":
            robust = recovery_fraction(recent, patches, radius)
            token = f"{seedbase}|{key}|{code}".encode()
            rs = int(hashlib.sha256(token).hexdigest()[:16], 16) % (2**32 - 1)
            random_mean, random_q025, random_q975 = same_size_random_recovery(
                recent,
                surface,
                selected_count=patch_n,
                radius_km=radius,
                repetitions=reps,
                seed=rs,
            )
            lift = float(robust - random_mean)

    row = {
        **base,
        "candidate_generation_status": cstatus,
        "candidate_generation_failure_reason": creason,
        "temporal_status": tstatus,
        "temporal_failure_reason": treason,
        "historical_training_occurrence_rows": hist_n,
        "recent_heldout_occurrence_rows": recent_n,
        "regional_tile_count": tiles,
        "geometry_surface_points": geom_n,
        "complete_terrain_surface_points": complete_n,
        "prototype_rows": proto_n,
        "candidate_patch_count": patch_n,
        "verified_geometry_canonical_sha256": verified,
        "primary_radius_km": radius,
        "robust_recall": robust,
        "random_recall_mean": random_mean,
        "random_recall_q025": random_q025,
        "random_recall_q975": random_q975,
        "robust_minus_random_recall": lift,
    }
    return pd.DataFrame([row]), patches
