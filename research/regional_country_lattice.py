#!/usr/bin/env python3
"""Outcome-blind regional lattice mechanics for country-framed integration.

This module is research-only and contains no taxon or occurrence input. It
inherits a 2-degree regional scale from the independently validated Japanese
region design, intersects a globally anchored 2 x 2 degree lattice with a
frozen external country geometry, and creates 800 deterministic geometry-only
candidate points per intersecting tile.

The tile grid is a computational/search representation, not a biological or
movement boundary. All sampled points retain one country-level ``survey_area_id``
so later robust 1 km patch aggregation is not blocked at tile edges.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Iterator

import numpy as np
import pandas as pd
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box
from shapely.ops import unary_union

from acsp.taxon_patches import VALIDATED_JAPAN_REGIONS
from country_framed_robust_integration import CountryLandGeometry, _parse_land_geometry

LATTICE_STEP_DEG = 2.0
LATTICE_LON_ANCHOR = -180.0
LATTICE_LAT_ANCHOR = -90.0
POINTS_PER_REGIONAL_TILE = 800
_LON_TILE_COUNT = int(round(360.0 / LATTICE_STEP_DEG))
_LAT_TILE_COUNT = int(round(180.0 / LATTICE_STEP_DEG))
_MAX_COMPONENT_DRAW_FACTOR = 2000


@dataclass(frozen=True)
class RegionalTile:
    country_code: str
    tile_id: str
    lon_index: int
    lat_index: int
    west: float
    south: float
    east: float
    north: float
    land_geometry_wkt: str


@dataclass(frozen=True)
class RegionalLatticeAudit:
    country_code: str
    lattice_step_deg: float
    reference_region_width_median_deg: float
    reference_region_height_median_deg: float
    intersecting_tile_count: int
    points_per_tile: int
    total_geometry_points: int
    occurrence_selected_tiles: bool = False
    tile_is_scientific_barrier: bool = False
    country_geometry_is_outer_frame: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "country_code": self.country_code,
            "lattice_step_deg": self.lattice_step_deg,
            "reference_region_width_median_deg": self.reference_region_width_median_deg,
            "reference_region_height_median_deg": self.reference_region_height_median_deg,
            "intersecting_tile_count": self.intersecting_tile_count,
            "points_per_tile": self.points_per_tile,
            "total_geometry_points": self.total_geometry_points,
            "occurrence_selected_tiles": self.occurrence_selected_tiles,
            "tile_is_scientific_barrier": self.tile_is_scientific_barrier,
            "country_geometry_is_outer_frame": self.country_geometry_is_outer_frame,
        }


def validated_reference_region_scale() -> tuple[float, float]:
    """Return median width/height of the fixed 12-region Japan design."""
    widths = np.asarray([float(east) - float(west) for _, _, _, west, south, east, north in VALIDATED_JAPAN_REGIONS])
    heights = np.asarray([float(north) - float(south) for _, _, _, west, south, east, north in VALIDATED_JAPAN_REGIONS])
    return float(np.median(widths)), float(np.median(heights))


def _polygonal_part(geometry):
    if geometry.is_empty:
        return None
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return geometry
    if geometry.geom_type == "GeometryCollection":
        pieces = [g for g in geometry.geoms if g.geom_type in {"Polygon", "MultiPolygon"} and not g.is_empty]
        if not pieces:
            return None
        merged = unary_union(pieces)
        if merged.is_empty or merged.geom_type not in {"Polygon", "MultiPolygon"}:
            return None
        return merged
    return None


def _tile_id(lon_index: int, lat_index: int) -> str:
    return f"x{int(lon_index):03d}_y{int(lat_index):02d}"


def _index_range(minimum: float, maximum: float, *, anchor: float, count: int) -> range:
    eps = 1e-12
    start = int(math.floor((float(minimum) - anchor) / LATTICE_STEP_DEG))
    stop = int(math.floor((float(maximum) - anchor - eps) / LATTICE_STEP_DEG))
    start = max(0, min(count - 1, start))
    stop = max(0, min(count - 1, stop))
    return range(start, stop + 1)


def iter_country_regional_tiles(spec: CountryLandGeometry) -> Iterator[RegionalTile]:
    """Yield every 2-degree lattice tile with polygonal country intersection."""
    code, country = _parse_land_geometry(spec)
    minx, miny, maxx, maxy = map(float, country.bounds)
    lon_indices = _index_range(minx, maxx, anchor=LATTICE_LON_ANCHOR, count=_LON_TILE_COUNT)
    lat_indices = _index_range(miny, maxy, anchor=LATTICE_LAT_ANCHOR, count=_LAT_TILE_COUNT)

    for lat_index in lat_indices:
        south = LATTICE_LAT_ANCHOR + lat_index * LATTICE_STEP_DEG
        north = south + LATTICE_STEP_DEG
        for lon_index in lon_indices:
            west = LATTICE_LON_ANCHOR + lon_index * LATTICE_STEP_DEG
            east = west + LATTICE_STEP_DEG
            clipped = _polygonal_part(country.intersection(box(west, south, east, north)))
            if clipped is None or clipped.area <= 0.0:
                continue
            if not clipped.is_valid:
                raise ValueError(
                    f"invalid country/tile intersection for {code} {_tile_id(lon_index, lat_index)}; no repair fallback is allowed"
                )
            yield RegionalTile(
                country_code=code,
                tile_id=_tile_id(lon_index, lat_index),
                lon_index=int(lon_index),
                lat_index=int(lat_index),
                west=float(west),
                south=float(south),
                east=float(east),
                north=float(north),
                land_geometry_wkt=clipped.wkt,
            )


def _tile_seed(country_code: str, tile_id: str) -> int:
    token = f"regional-lattice-v1|{country_code}|{tile_id}".encode("utf-8")
    return int(hashlib.sha256(token).hexdigest()[:16], 16) % (2**32 - 1)


def _polygon_components(geometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return [part for part in geometry.geoms if not part.is_empty and part.area > 0.0]
    raise ValueError(f"regional tile geometry must be Polygon/MultiPolygon, got {geometry.geom_type}")


def _sample_component(component: Polygon, count: int, rng: np.random.Generator) -> list[tuple[float, float]]:
    """Rejection-sample inside one polygon component using its own tight bbox."""
    if count <= 0:
        return []
    west, south, east, north = map(float, component.bounds)
    if not (west < east and south < north):
        raise ValueError("polygon component has degenerate bounds")
    rows: list[tuple[float, float]] = []
    max_draws = max(10_000, int(count) * _MAX_COMPONENT_DRAW_FACTOR)
    draws = 0
    while len(rows) < count and draws < max_draws:
        needed = count - len(rows)
        batch = min(max(128, needed * 4), max_draws - draws)
        xs = rng.uniform(west, east, size=batch)
        ys = rng.uniform(south, north, size=batch)
        draws += batch
        # Deliberately use covers to retain boundary points if the RNG happens
        # to hit one; no geometry buffering/repair is performed.
        from shapely.geometry import Point
        for longitude, latitude in zip(xs, ys):
            if component.covers(Point(float(longitude), float(latitude))):
                rows.append((float(latitude), float(longitude)))
                if len(rows) == count:
                    break
    if len(rows) != count:
        raise ValueError(
            f"regional tile component sampling produced {len(rows)}/{count} points; no bbox/provider fallback is allowed"
        )
    return rows


def sample_regional_tile(tile: RegionalTile, *, n_points: int = POINTS_PER_REGIONAL_TILE) -> pd.DataFrame:
    """Generate deterministic geometry-only points inside one clipped tile."""
    from shapely import wkt

    n_points = int(n_points)
    if n_points <= 0:
        raise ValueError("n_points must be positive")
    geometry = wkt.loads(tile.land_geometry_wkt)
    if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"invalid regional tile geometry for {tile.tile_id}")
    components = _polygon_components(geometry)
    if not components:
        raise ValueError(f"regional tile {tile.tile_id} has no polygon components")
    areas = np.asarray([part.area for part in components], dtype=float)
    if not np.isfinite(areas).all() or float(areas.sum()) <= 0.0:
        raise ValueError(f"regional tile {tile.tile_id} has invalid component areas")

    rng = np.random.default_rng(_tile_seed(tile.country_code, tile.tile_id))
    allocation = rng.multinomial(n_points, areas / areas.sum())
    rows: list[tuple[float, float]] = []
    for component, count in zip(components, allocation):
        rows.extend(_sample_component(component, int(count), rng))
    if len(rows) != n_points:
        raise AssertionError("regional tile sampler returned an unexpected point count")

    frame = pd.DataFrame(rows, columns=["latitude", "longitude"])
    frame["survey_area_id"] = f"country-{tile.country_code}"
    frame["regional_tile_id"] = tile.tile_id
    frame["tile_west"] = tile.west
    frame["tile_south"] = tile.south
    frame["tile_east"] = tile.east
    frame["tile_north"] = tile.north
    return frame


def build_regional_country_surface(
    spec: CountryLandGeometry,
    *,
    points_per_tile: int = POINTS_PER_REGIONAL_TILE,
) -> tuple[pd.DataFrame, RegionalLatticeAudit]:
    """Build the complete geometry-only regional surface for one country."""
    code = spec.normalized_code()
    tiles = list(iter_country_regional_tiles(spec))
    if not tiles:
        raise ValueError(f"country {code} intersects no 2-degree regional tiles")
    frames = [sample_regional_tile(tile, n_points=points_per_tile) for tile in tiles]
    surface = pd.concat(frames, ignore_index=True)
    width_median, height_median = validated_reference_region_scale()
    audit = RegionalLatticeAudit(
        country_code=code,
        lattice_step_deg=LATTICE_STEP_DEG,
        reference_region_width_median_deg=width_median,
        reference_region_height_median_deg=height_median,
        intersecting_tile_count=len(tiles),
        points_per_tile=int(points_per_tile),
        total_geometry_points=int(len(surface)),
    )
    return surface, audit


__all__ = [
    "LATTICE_STEP_DEG",
    "LATTICE_LON_ANCHOR",
    "LATTICE_LAT_ANCHOR",
    "POINTS_PER_REGIONAL_TILE",
    "RegionalLatticeAudit",
    "RegionalTile",
    "build_regional_country_surface",
    "iter_country_regional_tiles",
    "sample_regional_tile",
    "validated_reference_region_scale",
]
