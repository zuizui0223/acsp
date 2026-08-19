import unittest

import pandas as pd

from acsp.auto_budget import infer_recommended_effort


PROTOCOL = {
    "daily_field_hours": 8.0,
    "search_minutes_per_cell": 60,
    "access_buffer_minutes_per_cell": 0,
    "protocol_id": "test",
    "taxon_group": "plant",
}


def synthetic_trip(plan, hub_latitude, hub_longitude, survey_protocol=None, target_days=1):
    # One additional site costs two hours. This estimator is deliberately
    # independent of a user day budget; target_days only satisfies the common
    # estimator contract.
    hours = float(len(plan) * 2)
    return {
        "total_hours": hours,
        "estimated_days": max(1, (len(plan) + 3) // 4),
        "fits_target_days": True,
        "unreachable_site_ids": [],
    }


class AutoBudgetTests(unittest.TestCase):
    def test_selects_diminishing_returns_knee_without_user_days(self):
        ordered = pd.DataFrame({
            "site_id": ["a", "b", "c", "d", "e"],
            "latitude": [35.0] * 5,
            "longitude": [139.0] * 5,
            "cumulative_coverage_fraction": [0.50, 0.78, 0.90, 0.94, 0.96],
        })
        selected, audit, frontier = infer_recommended_effort(
            ordered,
            hub_latitude=35.0,
            hub_longitude=139.0,
            trip_estimator=synthetic_trip,
            survey_protocol=PROTOCOL,
        )
        self.assertEqual(audit.selected_count, 2)
        self.assertEqual(selected["site_id"].tolist(), ["a", "b"])
        self.assertEqual(int(frontier["recommended"].sum()), 1)

    def test_unreachable_prefix_cannot_be_recommended(self):
        def reachability_limited(plan, *args, **kwargs):
            unreachable = ["b"] if len(plan) >= 2 else []
            return {
                "total_hours": float(len(plan)),
                "estimated_days": 1,
                "fits_target_days": not unreachable,
                "unreachable_site_ids": unreachable,
            }

        ordered = pd.DataFrame({
            "site_id": ["a", "b"],
            "latitude": [35.0, 35.1],
            "longitude": [139.0, 139.1],
            "cumulative_coverage_fraction": [0.6, 1.0],
        })
        selected, audit, frontier = infer_recommended_effort(
            ordered,
            hub_latitude=35.0,
            hub_longitude=139.0,
            trip_estimator=reachability_limited,
            survey_protocol=PROTOCOL,
        )
        self.assertEqual(selected["site_id"].tolist(), ["a"])
        self.assertEqual(audit.unreachable_prefixes, 1)
        self.assertFalse(bool(frontier.loc[1, "reachable"]))


if __name__ == "__main__":
    unittest.main()
