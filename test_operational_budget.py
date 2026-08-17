import math
import unittest

import pandas as pd

from acsp.operational_budget import select_largest_feasible_prefix


def two_sites_per_day_estimator(plan, hub_latitude, hub_longitude, survey_protocol=None, target_days=1):
    k = len(plan)
    capacity = int(target_days) * 2
    return {
        "fits_target_days": k <= capacity,
        "estimated_days": int(math.ceil(k / 2.0)) if k else 0,
        "total_hours": float(k * 3.0),
        "hub_latitude": float(hub_latitude),
        "hub_longitude": float(hub_longitude),
    }


class OperationalBudgetTests(unittest.TestCase):
    def setUp(self):
        self.ordered = pd.DataFrame(
            {
                "site_id": [91, 14, 77, 3, 42, 8, 65],
                "latitude": [35.0, 35.1, 35.2, 35.3, 35.4, 35.5, 35.6],
                "longitude": [139.0, 139.1, 139.2, 139.3, 139.4, 139.5, 139.6],
                "coverage_rank": list(range(1, 8)),
            },
            index=[10, 20, 30, 40, 50, 60, 70],
        )

    def test_selects_longest_feasible_prefix_without_reordering(self):
        selected, audit, prefixes = select_largest_feasible_prefix(
            self.ordered,
            hub_latitude=35.25,
            hub_longitude=139.25,
            target_days=2,
            trip_estimator=two_sites_per_day_estimator,
        )
        self.assertEqual(selected["site_id"].tolist(), [91, 14, 77, 3])
        self.assertEqual(selected.index.tolist(), [10, 20, 30, 40])
        self.assertEqual(audit.selected_count, 4)
        self.assertTrue(audit.fits_target_days)
        self.assertEqual(audit.candidate_prefixes_evaluated, 7)
        self.assertEqual(prefixes["k"].tolist(), list(range(1, 8)))
        self.assertEqual(prefixes["fits_target_days"].tolist(), [True, True, True, True, False, False, False])

    def test_no_prefix_fits_returns_empty(self):
        def none_fit(plan, hub_latitude, hub_longitude, survey_protocol=None, target_days=1):
            return {"fits_target_days": False, "estimated_days": 99}

        selected, audit, prefixes = select_largest_feasible_prefix(
            self.ordered,
            hub_latitude=35.0,
            hub_longitude=139.0,
            target_days=1,
            trip_estimator=none_fit,
        )
        self.assertTrue(selected.empty)
        self.assertEqual(audit.selected_count, 0)
        self.assertFalse(audit.fits_target_days)
        self.assertEqual(len(prefixes), 7)

    def test_max_sites_caps_prefix_evaluation(self):
        selected, audit, prefixes = select_largest_feasible_prefix(
            self.ordered,
            hub_latitude=35.0,
            hub_longitude=139.0,
            target_days=5,
            trip_estimator=two_sites_per_day_estimator,
            max_sites=3,
        )
        self.assertEqual(selected["site_id"].tolist(), [91, 14, 77])
        self.assertEqual(audit.selected_count, 3)
        self.assertEqual(audit.candidate_prefixes_evaluated, 3)
        self.assertEqual(prefixes["k"].tolist(), [1, 2, 3])

    def test_non_monotone_estimator_uses_largest_feasible_prefix(self):
        def non_monotone(plan, hub_latitude, hub_longitude, survey_protocol=None, target_days=1):
            k = len(plan)
            return {"fits_target_days": k in {1, 3, 5}, "estimated_days": 1}

        selected, audit, _ = select_largest_feasible_prefix(
            self.ordered,
            hub_latitude=35.0,
            hub_longitude=139.0,
            target_days=1,
            trip_estimator=non_monotone,
        )
        self.assertEqual(selected["site_id"].tolist(), [91, 14, 77, 3, 42])
        self.assertEqual(audit.selected_count, 5)

    def test_invalid_budget_rejected(self):
        with self.assertRaises(ValueError):
            select_largest_feasible_prefix(
                self.ordered,
                hub_latitude=35.0,
                hub_longitude=139.0,
                target_days=0,
                trip_estimator=two_sites_per_day_estimator,
            )
        with self.assertRaises(ValueError):
            select_largest_feasible_prefix(
                self.ordered,
                hub_latitude=35.0,
                hub_longitude=139.0,
                target_days=1,
                trip_estimator=two_sites_per_day_estimator,
                max_sites=-1,
            )


if __name__ == "__main__":
    unittest.main()
