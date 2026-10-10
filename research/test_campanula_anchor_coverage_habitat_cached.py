from __future__ import annotations

import unittest

import pandas as pd

from evaluate_campanula_anchor_coverage_habitat import coverage_constrained_habitat_sample
from run_campanula_anchor_coverage_habitat_cached import (
    cached_coverage_constrained_habitat_sample,
)


class CachedCoverageHabitatTests(unittest.TestCase):
    def test_cached_selector_matches_frozen_reference_for_multiple_counts(self):
        frame = pd.DataFrame(
            [
                {
                    "island": "alpha",
                    "latitude": (i % 5) * 0.01,
                    "longitude": (i // 5) * 0.01,
                    "candidate_cell_id": i,
                    "environment_distance": float((13 * i) % 17) / 17.0,
                }
                for i in range(30)
            ]
        )
        for count in (1, 2, 3, 5, 9, 15, 29, 30):
            expected = coverage_constrained_habitat_sample(frame.copy(), count)
            actual_frame = frame.copy()
            actual = cached_coverage_constrained_habitat_sample(actual_frame, count)
            self.assertEqual(
                expected["candidate_cell_id"].astype(int).tolist(),
                actual["candidate_cell_id"].astype(int).tolist(),
            )
            # A second call on the same object exercises the cache path.
            repeated = cached_coverage_constrained_habitat_sample(actual_frame, count)
            self.assertEqual(
                actual["candidate_cell_id"].astype(int).tolist(),
                repeated["candidate_cell_id"].astype(int).tolist(),
            )


if __name__ == "__main__":
    unittest.main()
