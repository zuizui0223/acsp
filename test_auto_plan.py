import unittest

import pandas as pd

from acsp.auto_plan import plan_auto_effort


PROTOCOL = {
    "daily_field_hours": 8.0,
    "search_minutes_per_cell": 30,
    "access_buffer_minutes_per_cell": 0,
    "protocol_id": "test",
    "taxon_group": "plant",
}


class AutoPlanTests(unittest.TestCase):
    def test_unreachable_candidate_is_filtered_before_coverage_order(self):
        candidates = pd.DataFrame({
            "site_id": ["blocked", "a", "b"],
            "survey_area_id": ["x", "x", "x"],
            "latitude": [35.000, 35.010, 35.020],
            "longitude": [139.000, 139.010, 139.020],
        })
        # blocked has no path at all. a and b are connected through explicit walk edges.
        edges = pd.DataFrame({
            "from_id": ["hub", "a", "a", "b"],
            "to_id": ["a", "hub", "b", "a"],
            "travel_minutes": [10, 10, 10, 10],
            "mode": ["walk", "walk", "walk", "walk"],
        })
        selected, audit, frontier, reachability = plan_auto_effort(
            candidates,
            movement_edges=edges,
            hub_id="hub",
            allowed_modes=["walk"],
            survey_protocol=PROTOCOL,
            coverage_radius_km=0.5,
        )
        self.assertEqual(audit.input_candidates, 3)
        self.assertEqual(audit.reachable_candidates, 2)
        self.assertEqual(audit.unreachable_candidates, 1)
        blocked = reachability.loc[reachability["site_id"].eq("blocked")].iloc[0]
        self.assertFalse(bool(blocked["roundtrip_reachable"]))
        self.assertNotIn("blocked", selected["site_id"].tolist())
        self.assertTrue(frontier["reachable"].all())

    def test_shortest_path_can_use_intermediate_explicit_nodes(self):
        candidates = pd.DataFrame({
            "site_id": ["site"],
            "survey_area_id": ["x"],
            "latitude": [35.0],
            "longitude": [139.0],
        })
        edges = pd.DataFrame({
            "from_id": ["hub", "road-junction", "site", "road-junction"],
            "to_id": ["road-junction", "site", "road-junction", "hub"],
            "travel_minutes": [5, 7, 8, 6],
            "mode": ["road", "trail", "trail", "road"],
        })
        _, audit, _, reachability = plan_auto_effort(
            candidates,
            movement_edges=edges,
            hub_id="hub",
            allowed_modes=["road", "trail"],
            survey_protocol=PROTOCOL,
        )
        row = reachability.iloc[0]
        self.assertTrue(bool(row["roundtrip_reachable"]))
        self.assertEqual(float(row["outbound_minutes"]), 12.0)
        self.assertEqual(float(row["return_minutes"]), 14.0)
        self.assertEqual(audit.reachable_candidates, 1)

    def test_disallowed_flight_does_not_create_reachability(self):
        candidates = pd.DataFrame({
            "site_id": ["island"],
            "latitude": [35.0],
            "longitude": [139.0],
        })
        edges = pd.DataFrame({
            "from_id": ["hub", "island"],
            "to_id": ["island", "hub"],
            "travel_minutes": [1, 1],
            "mode": ["flight", "flight"],
        })
        with self.assertRaisesRegex(ValueError, "No movement edges remain"):
            plan_auto_effort(
                candidates,
                movement_edges=edges,
                hub_id="hub",
                allowed_modes=["walk"],
                survey_protocol=PROTOCOL,
            )


if __name__ == "__main__":
    unittest.main()
