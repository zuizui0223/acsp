import unittest

import pandas as pd

from acsp.reachable_patches import PatchSettings, discover_persistent_patches


class ReachablePatchTests(unittest.TestCase):
    def setUp(self):
        rows = []
        site_id = 1
        for area_index, area in enumerate(("a", "b")):
            base_lat = 34.0 + area_index
            for offset, support in ((0.0, 0.95), (0.008, 0.90), (0.016, 0.85), (0.08, 0.30)):
                rows.append(
                    {
                        "site_id": site_id,
                        "survey_area_id": area,
                        "latitude": base_lat + offset,
                        "longitude": 139.0,
                        "analogue_score": support,
                        "elevation": offset * 1000,
                        "slope": offset * 100,
                        "roughness": offset * 50,
                        "tpi": offset,
                        "distance_to_coast_m": 100 + offset * 1000,
                    }
                )
                site_id += 1
        self.candidates = pd.DataFrame(rows)

    def test_returns_one_route_constrained_patch_per_area(self):
        stations, patches = discover_persistent_patches(
            self.candidates,
            settings=PatchSettings(maximum_stations=2, maximum_patch_diameter_km=3.0),
        )
        self.assertEqual(set(patches["survey_area_id"]), {"a", "b"})
        self.assertTrue((patches["patch_station_count"] <= 2).all())
        self.assertTrue((patches["patch_diameter_km"] <= 3.0 + 1e-9).all())
        self.assertEqual(stations.groupby("survey_area_id").size().to_dict(), {"a": 2, "b": 2})

    def test_distant_low_support_point_does_not_form_selected_chain(self):
        stations, _ = discover_persistent_patches(
            self.candidates,
            settings=PatchSettings(maximum_stations=3, maximum_patch_diameter_km=2.5),
        )
        self.assertTrue((stations["analogue_score"] >= 0.85).all())


if __name__ == "__main__":
    unittest.main()
