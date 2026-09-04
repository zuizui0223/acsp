from __future__ import annotations

import unittest

from acsp.local_discovery_gates import LocalDiscoveryEvidence, classify_local_discovery_problem


class LocalDiscoveryGateTests(unittest.TestCase):
    def test_taxonomy_gate_precedes_geometry(self) -> None:
        result = classify_local_discovery_problem(
            LocalDiscoveryEvidence(
                taxon_match_classification="NO_GBIF_MATCH",
                primary_anchor_count=99,
                broad_support_available=True,
            )
        )
        self.assertEqual(result.problem_class, "TAXON_REVIEW")
        self.assertFalse(result.patch_generation_allowed)
        self.assertFalse(result.anchor_kernel_allowed)

    def test_recent_precise_anchor_opens_local_continuation(self) -> None:
        result = classify_local_discovery_problem(
            LocalDiscoveryEvidence(
                taxon_match_classification="AUTO_EXACT_ACCEPTED",
                primary_anchor_count=1,
                broad_support_available=True,
                structural_family="WETLAND_MOISTURE_STRUCTURE",
            )
        )
        self.assertEqual(result.problem_class, "LOCAL_CONTINUATION")
        self.assertEqual(result.anchor_replication_class, "SINGLE_PRIMARY_ANCHOR")
        self.assertTrue(result.patch_generation_allowed)
        self.assertTrue(result.anchor_kernel_allowed)

    def test_multiple_anchors_are_reported_explicitly(self) -> None:
        result = classify_local_discovery_problem(
            LocalDiscoveryEvidence(
                taxon_match_classification="AUTO_EXACT_ACCEPTED",
                primary_anchor_count=2,
                broad_support_available=True,
            )
        )
        self.assertEqual(result.problem_class, "LOCAL_CONTINUATION")
        self.assertEqual(result.anchor_replication_class, "MULTIPLE_PRIMARY_ANCHORS")

    def test_detached_component_requires_anchor_and_explicit_structure(self) -> None:
        result = classify_local_discovery_problem(
            LocalDiscoveryEvidence(
                taxon_match_classification="AUTO_EXACT_ACCEPTED",
                primary_anchor_count=2,
                detached_component_supported=True,
            )
        )
        self.assertEqual(result.problem_class, "DETACHED_COMPONENT")
        with self.assertRaises(ValueError):
            LocalDiscoveryEvidence(
                taxon_match_classification="AUTO_EXACT_ACCEPTED",
                primary_anchor_count=0,
                detached_component_supported=True,
            )

    def test_legacy_record_never_becomes_local_anchor(self) -> None:
        result = classify_local_discovery_problem(
            LocalDiscoveryEvidence(
                taxon_match_classification="AUTO_EXACT_ACCEPTED",
                legacy_precise_count=5,
                broad_support_available=True,
            )
        )
        self.assertEqual(result.problem_class, "SENTINEL")
        self.assertEqual(result.anchor_replication_class, "ZERO_PRIMARY_ANCHOR")
        self.assertFalse(result.anchor_kernel_allowed)
        self.assertEqual(result.evidence_context, "legacy_precise_context")

    def test_no_anchor_without_broad_support_abstains(self) -> None:
        result = classify_local_discovery_problem(
            LocalDiscoveryEvidence(
                taxon_match_classification="AUTO_EXACT_ACCEPTED",
                nonprimary_context_count=12,
                broad_support_available=False,
            )
        )
        self.assertEqual(result.problem_class, "ABSTAIN_LOCAL_PATCH")
        self.assertEqual(result.anchor_replication_class, "ZERO_PRIMARY_ANCHOR")
        self.assertFalse(result.patch_generation_allowed)

    def test_counts_must_be_nonnegative(self) -> None:
        with self.assertRaises(ValueError):
            LocalDiscoveryEvidence(
                taxon_match_classification="AUTO_EXACT_ACCEPTED",
                primary_anchor_count=-1,
            )


if __name__ == "__main__":
    unittest.main()
