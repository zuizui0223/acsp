from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery import partition_candidate_components


class DiscoveryComponentTests(unittest.TestCase):
    def test_partition_separates_anchored_and_detached_without_distance(self) -> None:
        frame = pd.DataFrame(
            [
                {"candidate_cell_id": "a1", "ecological_component_id": "A", "latitude": 35.0, "longitude": 139.0},
                {"candidate_cell_id": "a2", "ecological_component_id": "A", "latitude": 35.1, "longitude": 139.1},
                {"candidate_cell_id": "b1", "ecological_component_id": "B", "latitude": 35.2, "longitude": 139.2},
                {"candidate_cell_id": "c1", "ecological_component_id": "C", "latitude": 35.3, "longitude": 139.3},
            ]
        )
        local, detached, audit = partition_candidate_components(frame, anchored_component_ids=["A"])
        self.assertEqual(local["candidate_cell_id"].tolist(), ["a1", "a2"])
        self.assertEqual(detached["candidate_cell_id"].tolist(), ["b1", "c1"])
        self.assertEqual(audit.component_count, 3)
        self.assertEqual(audit.detached_component_count, 2)
        self.assertFalse(audit.distance_threshold_used)
        self.assertFalse(audit.field_outcomes_used)

    def test_unknown_anchored_component_fails_closed(self) -> None:
        frame = pd.DataFrame(
            [{"candidate_cell_id": "a", "ecological_component_id": "A", "latitude": 35.0, "longitude": 139.0}]
        )
        with self.assertRaisesRegex(ValueError, "absent from candidate frame"):
            partition_candidate_components(frame, anchored_component_ids=["Z"])


if __name__ == "__main__":
    unittest.main()
