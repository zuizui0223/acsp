from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery.evaluation import audit_candidate_frame_reachability
from acsp.discovery.evidence import OccurrenceCluster


class DiscoveryEvaluationTests(unittest.TestCase):
    def test_full_frame_ceiling_is_selector_free(self) -> None:
        frame = pd.DataFrame(
            {
                "latitude": [35.0, 35.01],
                "longitude": [139.0, 139.01],
            }
        )
        populations = [
            OccurrenceCluster(((35.0005, 139.0005, "near"),)),
            OccurrenceCluster(((36.0, 140.0, "far"),)),
        ]
        audit = audit_candidate_frame_reachability(frame, populations, recovery_radii_km=(0.25, 1.0))
        self.assertEqual(audit.heldout_population_count, 2)
        self.assertEqual(audit.recovered_counts, (1, 1))
        self.assertEqual(audit.recalls, (0.5, 0.5))
        self.assertTrue(audit.field_outcomes_used)
        self.assertFalse(audit.selector_used)
        self.assertFalse(audit.candidate_generation_modified)


if __name__ == "__main__":
    unittest.main()
