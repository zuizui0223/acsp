from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import prepare_cirsium_japan38_broad_frame_confirmation_v2 as v2


class Japan38BroadFrameConfirmationV2Tests(unittest.TestCase):
    def test_frozen_roster_expands_exactly_31_taxa(self):
        units = v2.load_frozen_units()
        self.assertEqual(len(units), 31)
        self.assertEqual(len({row["unit_id"] for row in units}), 31)
        self.assertEqual(len({row["species"] for row in units}), 31)
        self.assertTrue(all(len(row["allowed_fixed_regions"]) == 12 for row in units))

    def test_contract_primary_gates_are_frozen_before_outcome(self):
        contract = json.loads(v2.CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["status"], "FROZEN_BEFORE_2021_2025_OUTCOME_FETCH")
        primary = contract["primary_endpoint"]
        self.assertEqual(primary["minimum_temporally_evaluable_taxa"], 8)
        self.assertEqual(primary["minimum_fraction_evaluable_taxa_with_strictly_positive_difference"], 0.5)
        self.assertEqual(primary["minimum_cluster_weighted_added_recall"], 0.1)
        self.assertTrue(primary["all_three_conditions_required"])
        self.assertFalse(contract["candidate_universes"]["structural_selector_used"])
        self.assertFalse(contract["candidate_universes"]["spatial_selector_used"])
        self.assertFalse(contract["candidate_universes"]["human_access_used"])

    def test_run_keeps_all_declared_taxa_without_recent_fetch(self):
        observed = []

        def fake_prepare(unit, contract):
            observed.append((unit["unit_id"], tuple(unit["allowed_fixed_regions"])))
            return {
                "unit_id": unit["unit_id"],
                "species": unit["species"],
                "status": "NO_HISTORICAL_ANCHOR",
                "recent_outcomes_fetched": False,
            }

        with mock.patch.object(v2, "_prepare_unit", side_effect=fake_prepare):
            result = v2.run()
        self.assertEqual(result["declared_taxa"], 31)
        self.assertEqual(result["units_no_historical_anchor"], 31)
        self.assertEqual(len(observed), 31)
        self.assertTrue(all(len(regions) == 12 for _, regions in observed))
        self.assertFalse(result["recent_outcomes_fetched"])

    def test_runner_has_no_recent_provider_dependency(self):
        source = (RESEARCH / "prepare_cirsium_japan38_broad_frame_confirmation_v2.py").read_text(encoding="utf-8")
        self.assertNotIn("fetch_recent_country_occurrences", source)
        self.assertNotIn("year_from=2021", source)
        self.assertNotIn("year_to=2025", source)


if __name__ == "__main__":
    unittest.main()
