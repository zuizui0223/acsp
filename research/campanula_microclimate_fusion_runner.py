#!/usr/bin/env python3
"""Run the Campanula microclimate experiment with baseline terrain fields attached.

This compatibility runner keeps the scientific experiment in
`campanula_microclimate_fusion.py` while making its terrain input contract
explicit: the microterrain universe CSV contains only `env_nn`, so TPI and
roughness are sampled from the same GSI-derived 25 m `terrain_surface()` used by
the baseline rather than assumed to be serialized in the CSV.
"""
from __future__ import annotations

import campanula_microclimate_fusion as fusion
from campanula_microterrain_discovery import terrain_surface


_original_dem_physics = fusion.dem_physics


def dem_physics_with_baseline_fields(path):
    transform, crs, surfaces = _original_dem_physics(path)
    baseline = terrain_surface(path)
    surfaces = dict(surfaces)
    for field in ("tpi100", "tpi300", "rough100", "rough300"):
        surfaces[field] = baseline[field]
    return transform, crs, surfaces


if __name__ == "__main__":
    fusion.dem_physics = dem_physics_with_baseline_fields
    fusion.main()
