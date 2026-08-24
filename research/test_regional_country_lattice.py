import hashlib
import inspect
import json
from pathlib import Path
import unittest

from shapely import wkt
from shapely.geometry import Point

from country_framed_robust_integration import CountryLandGeometry
from regional_country_lattice import (
    LATTICE_LAT_ANCHOR,
    LATTICE_LON_ANCHOR,
    LATTICE_STEP_DEG,
    POINTS_PER_REGIONAL_TILE,
    build_regional_country_surface,
    iter_country_regional_tiles,
    sample_regional_tile,
    validated_reference_region_scale,
)

ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = ROOT / "validation" / "acsp_country_regional_lattice_2deg_freeze_v1.json"
EXPECTED_FREEZE_FINGERPRINT = "6d5c0ca8cc699eda7856d37e72007cadcc208a9312765f1162ed963ae0de0ba1"


class RegionalCountryLatticeTests(unittest.TestCase):
    def test_freeze_fingerprint_and_reference_scale_are_inherited(self):
        payload = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
        stored = payload.pop("freeze_fingerprint")
        calculated = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        self.assertEqual(stored, EXPECTED_FREEZE_FINGERPRINT)
        self.assertEqual(calculated, EXPECTED_FREEZE_FINGERPRINT)
        width, height = validated_reference_region_scale()
        self.assertEqual(width, 2.0)
        self.assertEqual(height, 1.9)
        self.assertEqual(LATTICE_STEP_DEG, 2.0)
        self.assertEqual(LATTICE_LON_ANCHOR, -180.0)
        self.assertEqual(LATTICE_LAT_ANCHOR, -90.0)
        self.assertEqual(POINTS_PER_REGIONAL_TILE, 800)
        self.assertFalse(payload["lattice"]["historical_occurrence_tile_selection"])
        self.assertFalse(payload["lattice"]["tile_is_scientific_barrier"])
        self.assertFalse(payload["future_v2_boundary"]["ecological_outcomes_opened"])

    def test_four_aligned_tiles_are_all_included_and_share_country_area(self):
        spec = CountryLandGeometry(
            country_code="ZZ",
            land_geometry_wkt="POLYGON((0 0,4 0,4 4,0 4,0 0))",
            source_id="fixture",
            source_version="fixture-v1",
        )
        tiles = list(iter_country_regional_tiles(spec))
        self.assertEqual(len(tiles), 4)
        self.assertEqual(len({tile.tile_id for tile in tiles}), 4)
        surface, audit = build_regional_country_surface(spec)
        self.assertEqual(len(surface), 4 * 800)
        self.assertEqual(surface["regional_tile_id"].nunique(), 4)
        self.assertEqual(surface["survey_area_id"].unique().tolist(), ["country-ZZ"])
        self.assertTrue((surface.groupby("regional_tile_id").size() == 800).all())
        polygon = wkt.loads(spec.land_geometry_wkt)
        self.assertTrue(
            all(
                polygon.covers(Point(float(lon), float(lat)))
                for lat, lon in surface[["latitude", "longitude"]].itertuples(index=False, name=None)
            )
        )
        self.assertEqual(audit.intersecting_tile_count, 4)
        self.assertEqual(audit.total_geometry_points, 3200)
        self.assertFalse(audit.occurrence_selected_tiles)
        self.assertFalse(audit.tile_is_scientific_barrier)

    def test_partial_country_intersections_are_included_without_occurrence_filtering(self):
        spec = CountryLandGeometry(
            country_code="ZZ",
            land_geometry_wkt="POLYGON((0.5 0.5,2.5 0.5,2.5 2.5,0.5 2.5,0.5 0.5))",
            source_id="fixture",
            source_version="fixture-v1",
        )
        tiles = list(iter_country_regional_tiles(spec))
        self.assertEqual(len(tiles), 4)
        bounds = {(tile.west, tile.south, tile.east, tile.north) for tile in tiles}
        self.assertEqual(
            bounds,
            {
                (0.0, 0.0, 2.0, 2.0),
                (2.0, 0.0, 4.0, 2.0),
                (0.0, 2.0, 2.0, 4.0),
                (2.0, 2.0, 4.0, 4.0),
            },
        )

    def test_component_weighted_sampling_handles_fragmented_islands_deterministically(self):
        spec = CountryLandGeometry(
            country_code="ZZ",
            land_geometry_wkt=(
                "MULTIPOLYGON(((0.1 0.1,0.2 0.1,0.2 0.2,0.1 0.2,0.1 0.1)),"
                "((1.8 1.8,1.9 1.8,1.9 1.9,1.8 1.9,1.8 1.8)))"
            ),
            source_id="fixture",
            source_version="fixture-v1",
        )
        tile = list(iter_country_regional_tiles(spec))[0]
        first = sample_regional_tile(tile)
        second = sample_regional_tile(tile)
        self.assertTrue(first.equals(second))
        self.assertEqual(len(first), 800)
        geometry = wkt.loads(tile.land_geometry_wkt)
        self.assertTrue(
            all(
                geometry.covers(Point(float(lon), float(lat)))
                for lat, lon in first[["latitude", "longitude"]].itertuples(index=False, name=None)
            )
        )

    def test_public_mechanics_take_geometry_not_taxon_or_occurrence(self):
        signature = inspect.signature(build_regional_country_surface)
        self.assertEqual(list(signature.parameters), ["spec", "points_per_tile"])
        self.assertNotIn("taxon", signature.parameters)
        self.assertNotIn("occurrences", signature.parameters)
        freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
        self.assertTrue(freeze["future_v2_boundary"]["country_wide_historical_prototype_scope_unchanged_from_v1_v1_1"])
        self.assertFalse(freeze["future_v2_boundary"]["candidate_ranking_or_topk"])
        self.assertFalse(freeze["future_v2_boundary"]["confirmation_taxa_allowed"])


if __name__ == "__main__":
    unittest.main()
