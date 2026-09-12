from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery.broad_frames import (
    attach_nearest_anchor_distance,
    build_rectangular_candidate_frame,
    partition_local_and_detached,
)


class BroadFrameTests(unittest.TestCase):
    def test_rectangular_frame_is_deterministic(self) -> None:
        a, audit_a = build_rectangular_candidate_frame(
            (139.0, 35.0, 139.02, 35.02), grid_spacing_m=500.0, candidate_id_prefix="x"
        )
        b, audit_b = build_rectangular_candidate_frame(
            (139.0, 35.0, 139.02, 35.02), grid_spacing_m=500.0, candidate_id_prefix="x"
        )
        self.assertGreater(len(a), 0)
        self.assertEqual(a.to_dict("records"), b.to_dict("records"))
        self.assertEqual(audit_a, audit_b)
        self.assertFalse(audit_a.field_outcomes_used)
        self.assertFalse(audit_a.human_access_used)

    def test_distance_and_detached_partition_preserve_declared_boundary(self) -> None:
        frame = pd.DataFrame(
            [
                {"candidate_cell_id": "a", "latitude": 35.0, "longitude": 139.01, "grid_row": 0, "grid_col": 0, "ecological_component_id": "C1"},
                {"candidate_cell_id": "b", "latitude": 35.0, "longitude": 139.07, "grid_row": 0, "grid_col": 1, "ecological_component_id": "C1"},
                {"candidate_cell_id": "c", "latitude": 35.0, "longitude": 139.08, "grid_row": 0, "grid_col": 2, "ecological_component_id": "C2"},
            ]
        )
        anchors = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
        with_distance = attach_nearest_anchor_distance(frame, anchors)
        labeled, audit = partition_local_and_detached(
            with_distance, local_boundary_km=5.0, target_component_id="C1"
        )
        lane = dict(zip(labeled["candidate_cell_id"], labeled["discovery_lane"]))
        self.assertEqual(lane["a"], "LOCAL")
        self.assertEqual(lane["b"], "DETACHED_SAME_COMPONENT")
        self.assertEqual(lane["c"], "DETACHED_OTHER_COMPONENT")
        self.assertEqual(audit.local_boundary_km, 5.0)
        self.assertEqual(audit.local_count, 1)
        self.assertEqual(audit.detached_count, 2)
        self.assertFalse(audit.fitted_thresholds)

    def test_partition_requires_predeclared_distance(self) -> None:
        frame = pd.DataFrame(
            [{"candidate_cell_id": "x", "latitude": 35.0, "longitude": 139.0, "grid_row": 0, "grid_col": 0}]
        )
        with self.assertRaisesRegex(ValueError, "nearest_anchor_km"):
            partition_local_and_detached(frame, local_boundary_km=5.0)


if __name__ == "__main__":
    unittest.main()
