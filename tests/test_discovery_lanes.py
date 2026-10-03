from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery.lanes import DiscoveryLane, DiscoveryLaneEvidence, plan_discovery_lanes


class DiscoveryLaneTests(unittest.TestCase):
    def test_local_and_detached_can_coexist_without_blending(self) -> None:
        plan = plan_discovery_lanes(
            DiscoveryLaneEvidence(
                exact_population_count=3,
                local_context_justified=True,
                declared_local_boundary_available=True,
                source_backed_component_ids_available=True,
                remote_same_component_candidates_available=True,
                other_component_candidates_available=True,
            )
        )
        self.assertEqual(
            plan.lanes,
            (
                DiscoveryLane.LOCAL_CONTINUATION,
                DiscoveryLane.DETACHED_SAME_COMPONENT,
                DiscoveryLane.DETACHED_OTHER_COMPONENT,
            ),
        )
        self.assertTrue(plan.local_and_detached_coexist)
        self.assertFalse(plan.budget_allocation_identified)
        self.assertFalse(plan.field_outcomes_used)

    def test_anchor_count_alone_does_not_create_a_lane(self) -> None:
        plan = plan_discovery_lanes(DiscoveryLaneEvidence(exact_population_count=20))
        self.assertEqual(plan.lanes, (DiscoveryLane.ABSTAIN,))

    def test_remote_same_component_requires_declared_local_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "declared LOCAL boundary"):
            plan_discovery_lanes(
                DiscoveryLaneEvidence(
                    exact_population_count=2,
                    source_backed_component_ids_available=True,
                    remote_same_component_candidates_available=True,
                )
            )

    def test_sentinel_can_exist_without_exact_population(self) -> None:
        plan = plan_discovery_lanes(
            DiscoveryLaneEvidence(
                sentinel_context_available=True,
                sentinel_subregime="UNCERTAINTY_FOOTPRINT",
            )
        )
        self.assertEqual(plan.lanes, (DiscoveryLane.SENTINEL,))
        self.assertEqual(plan.sentinel_subregime, "UNCERTAINTY_FOOTPRINT")


if __name__ == "__main__":
    unittest.main()
