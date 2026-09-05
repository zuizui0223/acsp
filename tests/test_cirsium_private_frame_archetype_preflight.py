import unittest

import pandas as pd

from research.preflight_cirsium_private_frame_archetypes_v1 import build_preflight


def _requirements():
    return pd.DataFrame([
        {"cohort_unit_id": "CIR03", "species_binomial": "Cirsium ugoense", "occurrence_problem_class": "LOCAL_CONTINUATION", "structural_feature_family": "ALPINE_TOPOGRAPHIC_STRUCTURE", "requires_primary_anchor_geometry": True, "requires_gsi_dem": True, "requires_esa_worldcover_2021": False, "requires_gsi_coastline": False, "requires_broad_sentinel_support": False, "requires_target_component_id": False, "private_source_manifest_status": "NOT_BUILT", "private_frame_status": "NOT_BUILT", "public_full_ranking_status": "NOT_FROZEN"},
        {"cohort_unit_id": "CIR08", "species_binomial": "Cirsium brevicaule", "occurrence_problem_class": "LOCAL_CONTINUATION", "structural_feature_family": "COASTAL_ISLAND_STRUCTURE", "requires_primary_anchor_geometry": True, "requires_gsi_dem": False, "requires_esa_worldcover_2021": True, "requires_gsi_coastline": True, "requires_broad_sentinel_support": False, "requires_target_component_id": True, "private_source_manifest_status": "NOT_BUILT", "private_frame_status": "NOT_BUILT", "public_full_ranking_status": "NOT_FROZEN"},
        {"cohort_unit_id": "CIR02", "species_binomial": "Cirsium inundatum", "occurrence_problem_class": "SENTINEL", "structural_feature_family": "WETLAND_MOISTURE_STRUCTURE", "requires_primary_anchor_geometry": False, "requires_gsi_dem": True, "requires_esa_worldcover_2021": True, "requires_gsi_coastline": False, "requires_broad_sentinel_support": True, "requires_target_component_id": False, "private_source_manifest_status": "NOT_BUILT", "private_frame_status": "NOT_BUILT", "public_full_ranking_status": "NOT_FROZEN"},
    ])


def _cohort(opened=False):
    return pd.DataFrame([
        {"cohort_unit_id": "CIR03", "outcome_opened": opened},
        {"cohort_unit_id": "CIR08", "outcome_opened": False},
        {"cohort_unit_id": "CIR02", "outcome_opened": False},
    ])


class PrivateFrameArchetypePreflightTests(unittest.TestCase):
    def test_archetype_preflight_reports_exact_private_source_blockers(self):
        table, summary = build_preflight(_requirements(), _cohort())
        self.assertEqual(list(table.cohort_unit_id), ["CIR03", "CIR08", "CIR02"])
        self.assertEqual(summary["ready_units"], 0)
        self.assertEqual(summary["blocked_units"], 3)
        cir03 = table.set_index("cohort_unit_id").loc["CIR03"]
        self.assertEqual(cir03.required_private_inputs, "primary_anchor_geometry|gsi_dem_snapshot")
        cir08 = table.set_index("cohort_unit_id").loc["CIR08"]
        self.assertIn("gsi_coastline_snapshot", cir08.required_private_inputs)
        self.assertIn("target_ecological_component", cir08.required_private_inputs)
        cir02 = table.set_index("cohort_unit_id").loc["CIR02"]
        self.assertIn("sentinel_support_input", cir02.required_private_inputs)

    def test_preflight_fails_closed_after_outcome_opening(self):
        with self.assertRaisesRegex(ValueError, "field outcome already opened"):
            build_preflight(_requirements(), _cohort(opened=True))


if __name__ == "__main__":
    unittest.main()
