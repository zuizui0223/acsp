import inspect
import unittest

import pandas as pd

from acsp.reachability import select_reachability_constrained_patches


def _patches() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_patch_id": ["a", "b", "c"],
            "survey_area_id": ["island-a", "island-a", "island-b"],
            "latitude": [35.0, 35.0, 40.0],
            "longitude": [139.0, 139.01, 145.0],
            "candidate_patch_radius_m": [100.0, 100.0, 100.0],
            "patch_merge_distance_m": [1000.0, 1000.0, 1000.0],
        }
    )


class ExplicitReachabilitySelectorTests(unittest.TestCase):
    def test_explicit_cross_area_edge_can_connect_distant_patches(self):
        patches = _patches().iloc[[0, 2]].reset_index(drop=True)
        edges = pd.DataFrame(
            {"from_patch_id": ["a"], "to_patch_id": ["c"]}
        )
        selected, audit = select_reachability_constrained_patches(patches, edges)
        self.assertEqual(audit.movement_component_count, 1)
        self.assertEqual(audit.reachability_edge_count, 1)
        self.assertEqual(audit.movement_constraint_mode, "explicit_reachability_graph")
        self.assertFalse(audit.straight_line_movement_assumption)
        self.assertEqual(audit.coverage_scale_km, 1.0)
        self.assertEqual(
            audit.coverage_scale_source,
            "candidate_patch_artifact.patch_merge_distance_m",
        )
        self.assertTrue(
            (selected["operational_coverage_scale_source"]
             == "candidate_patch_artifact.patch_merge_distance_m").all()
        )
        self.assertEqual(selected["candidate_patch_id"].tolist(), ["a", "c"])
        self.assertTrue(pd.isna(selected["movement_parent_patch_id"].iloc[0]))
        self.assertEqual(selected["movement_parent_patch_id"].iloc[1], "a")

    def test_nearby_patches_without_edge_are_not_connected(self):
        patches = _patches().iloc[:2].copy()
        edges = pd.DataFrame(columns=["from_patch_id", "to_patch_id"])
        selected, audit = select_reachability_constrained_patches(patches, edges)
        self.assertEqual(audit.movement_component_count, 2)
        self.assertEqual(audit.reachability_edge_count, 0)
        self.assertEqual(audit.selected_count, 2)
        self.assertTrue(selected["movement_parent_patch_id"].isna().all())

    def test_empty_graph_conservatively_retains_all_isolated_patches(self):
        patches = _patches()
        edges = pd.DataFrame(columns=["from_patch_id", "to_patch_id"])
        selected, audit = select_reachability_constrained_patches(patches, edges)
        self.assertEqual(audit.movement_component_count, 3)
        self.assertEqual(audit.selected_count, 3)
        self.assertEqual(set(selected["candidate_patch_id"]), {"a", "b", "c"})

    def test_unknown_patch_id_is_hard_error(self):
        edges = pd.DataFrame(
            {"from_patch_id": ["a"], "to_patch_id": ["not-a-patch"]}
        )
        with self.assertRaisesRegex(ValueError, "unknown patch IDs"):
            select_reachability_constrained_patches(_patches(), edges)

    def test_duplicate_candidate_patch_id_is_hard_error(self):
        patches = _patches()
        patches.loc[1, "candidate_patch_id"] = "a"
        edges = pd.DataFrame(columns=["from_patch_id", "to_patch_id"])
        with self.assertRaisesRegex(ValueError, "must be unique"):
            select_reachability_constrained_patches(patches, edges)

    def test_duplicate_and_reverse_edges_collapse_to_one_undirected_edge(self):
        edges = pd.DataFrame(
            {
                "from_patch_id": ["a", "b", "a"],
                "to_patch_id": ["b", "a", "b"],
            }
        )
        _, audit = select_reachability_constrained_patches(_patches().iloc[:2], edges)
        self.assertEqual(audit.reachability_edge_count, 1)
        self.assertEqual(audit.movement_component_count, 1)

    def test_legacy_ranking_columns_do_not_change_graph_selection(self):
        patches = _patches()
        edges = pd.DataFrame(
            {
                "from_patch_id": ["a", "b"],
                "to_patch_id": ["b", "c"],
            }
        )
        base, _ = select_reachability_constrained_patches(patches, edges)
        ranked = patches.assign(zone_score=[0.0, 100.0, -50.0], zone_rank=[3, 1, 2])
        with_rank, _ = select_reachability_constrained_patches(ranked, edges)
        self.assertEqual(
            base["candidate_patch_id"].tolist(),
            with_rank["candidate_patch_id"].tolist(),
        )

    def test_api_has_no_budget_or_distance_threshold_argument(self):
        parameters = inspect.signature(select_reachability_constrained_patches).parameters
        self.assertIn("reachability_edges", parameters)
        self.assertNotIn("max_transition_km", parameters)
        self.assertNotIn("max_sites", parameters)
        self.assertNotIn("target_coverage", parameters)
        self.assertNotIn("survey_days", parameters)
        self.assertNotIn("budget", parameters)


if __name__ == "__main__":
    unittest.main()
