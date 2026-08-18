import unittest

import pandas as pd

from acsp.trip_proxy import estimate_operational_trip
from acsp_discover import infer_survey_protocol
from gbif_fieldmap_builder_app import estimate_default_short_trip


class TripProxyEquivalenceTests(unittest.TestCase):
    def test_single_area_plant_proxy_matches_production(self):
        plan = pd.DataFrame({
            "site_id": [11, 12, 13, 14],
            "survey_area_id": [1, 1, 1, 1],
            "latitude": [35.000, 35.015, 35.030, 35.045],
            "longitude": [139.000, 139.015, 139.030, 139.045],
        })
        protocol = infer_survey_protocol({"kingdom": "Plantae"}).as_dict()
        protocol["surface_domain"] = "terrestrial"
        expected = estimate_default_short_trip(
            plan, 35.0, 139.0, survey_protocol=protocol, target_days=2
        )
        actual = estimate_operational_trip(
            plan, 35.0, 139.0, survey_protocol=protocol, target_days=2
        )
        self.assertEqual(actual, expected)

    def test_two_area_proxy_matches_production_with_explicit_area_hubs(self):
        plan = pd.DataFrame({
            "site_id": [1, 2, 3, 4],
            "survey_area_id": ["north", "north", "south", "south"],
            "latitude": [35.0, 35.02, 34.0, 34.02],
            "longitude": [139.0, 139.02, 138.0, 138.02],
        })
        protocol = infer_survey_protocol({"kingdom": "Plantae"}).as_dict()
        protocol["surface_domain"] = "terrestrial"
        hubs = {"north": (35.0, 139.0), "south": (34.0, 138.0)}
        expected = estimate_default_short_trip(
            plan,
            35.0,
            139.0,
            survey_protocol=protocol,
            target_days=4,
            area_hubs_override=hubs,
        )
        actual = estimate_operational_trip(
            plan,
            35.0,
            139.0,
            survey_protocol=protocol,
            target_days=4,
            area_hubs_override=hubs,
        )
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
