"""Reusable structural-family catalog for experimental N4 discovery.

The catalog makes the ecological structure expected by each family explicit so
provider adapters can be exchanged without changing the discovery algorithm.
These are development contracts, not occupancy models.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StructuralFamilySpec:
    family_id: str
    label: str
    ecological_question: str
    required_raw_columns: tuple[str, ...]
    source_roles: tuple[str, ...]
    notes: str


STRUCTURAL_FAMILIES: dict[str, StructuralFamilySpec] = {
    "WETLAND_MOISTURE_STRUCTURE": StructuralFamilySpec(
        family_id="WETLAND_MOISTURE_STRUCTURE",
        label="Wetland / moisture continuity",
        ecological_question="Does a moist or wetland-associated structural component continue through the candidate frame?",
        required_raw_columns=(
            "wc_water_frac_250m",
            "wc_wetland_frac_250m",
            "slope100",
            "tpi300",
            "terrain_continuity_score_raw",
        ),
        source_roles=("landcover", "terrain", "ecological_graph"),
        notes="Uses public land-cover fractions plus low-slope/valley context and a separately constructed terrain-continuity graph.",
    ),
    "ALPINE_TOPOGRAPHIC_STRUCTURE": StructuralFamilySpec(
        family_id="ALPINE_TOPOGRAPHIC_STRUCTURE",
        label="Alpine topographic continuity",
        ecological_question="Does the same high-relief landform component continue beyond known populations?",
        required_raw_columns=(
            "elev",
            "landform_continuity_score_raw",
            "ridge_valley_continuity_score_raw",
        ),
        source_roles=("terrain", "ecological_graph"),
        notes="Relative elevation is frame-ranked; landform and ridge/valley continuity must come from an explicit ecological graph.",
    ),
    "OPEN_GRASSLAND_STRUCTURE": StructuralFamilySpec(
        family_id="OPEN_GRASSLAND_STRUCTURE",
        label="Open grassland / fragment continuity",
        ecological_question="Are open grassland fragments structurally connected or repeated across the justified frame?",
        required_raw_columns=(
            "wc_grass_frac_250m",
            "fragment_continuity_score_raw",
            "terrain_context_score_raw",
        ),
        source_roles=("landcover", "ecological_graph"),
        notes="Designed for open-land fragments; does not treat generic environmental similarity as a substitute for fragment structure.",
    ),
    "COASTAL_ISLAND_STRUCTURE": StructuralFamilySpec(
        family_id="COASTAL_ISLAND_STRUCTURE",
        label="Coastal / island structure",
        ecological_question="Does a shore-position and island-component structure justify looking beyond known coastal populations?",
        required_raw_columns=(
            "coast_distance_m",
            "shore_landform_continuity_score_raw",
            "island_component_score_raw",
        ),
        source_roles=("coastline", "terrain_or_landcover", "ecological_graph"),
        notes="Coast proximity is monotone but not sufficient alone; a source-backed shore landform and island/component graph is required.",
    ),
    "FOREST_EDGE_STRUCTURE": StructuralFamilySpec(
        family_id="FOREST_EDGE_STRUCTURE",
        label="Forest-edge structure",
        ecological_question="Do canopy transitions and terrain components repeat along forest edges?",
        required_raw_columns=(
            "wc_tree_frac_250m",
            "wc_edge_mix_250m",
            "terrain_component_score_raw",
        ),
        source_roles=("landcover", "ecological_graph"),
        notes="Uses a symmetric edge signal rather than rewarding either closed forest or open land by itself.",
    ),
}


def list_structural_families() -> tuple[StructuralFamilySpec, ...]:
    """Return all currently frozen development families in stable order."""
    return tuple(STRUCTURAL_FAMILIES[key] for key in sorted(STRUCTURAL_FAMILIES))


def get_structural_family_spec(family_id: str) -> StructuralFamilySpec:
    key = str(family_id).strip()
    try:
        return STRUCTURAL_FAMILIES[key]
    except KeyError as exc:
        raise ValueError(
            f"unknown structural family {key!r}; available: {', '.join(sorted(STRUCTURAL_FAMILIES))}"
        ) from exc
