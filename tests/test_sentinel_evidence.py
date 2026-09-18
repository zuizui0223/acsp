from __future__ import annotations

import unittest

from acsp.sentinel_evidence import SentinelEvidenceCounts, classify_sentinel_evidence


class SentinelEvidenceTests(unittest.TestCase):
    def test_primary_anchor_preempts_sentinel(self) -> None:
        result = classify_sentinel_evidence(SentinelEvidenceCounts(primary_anchor_count=1, recent_region_only_count=20))
        self.assertEqual(result.evidence_class, "LOCAL_PRIMARY_ANCHOR_PRESENT")
        self.assertTrue(result.local_kernel_allowed)
        self.assertFalse(result.uncertainty_kernel_allowed)

    def test_declared_uncertainty_can_support_broad_kernel_not_local_kernel(self) -> None:
        result = classify_sentinel_evidence(
            SentinelEvidenceCounts(recent_declared_uncertainty_coordinate_count=3)
        )
        self.assertEqual(result.evidence_class, "SENTINEL_UNCERTAINTY_KERNEL_ELIGIBLE")
        self.assertFalse(result.local_kernel_allowed)
        self.assertTrue(result.uncertainty_kernel_allowed)

    def test_unknown_uncertainty_remains_context_only(self) -> None:
        result = classify_sentinel_evidence(
            SentinelEvidenceCounts(recent_unknown_uncertainty_coordinate_count=10)
        )
        self.assertEqual(result.evidence_class, "SENTINEL_COARSE_CONTEXT_ONLY")
        self.assertFalse(result.uncertainty_kernel_allowed)
        self.assertTrue(result.broad_sector_context_available)

    def test_legacy_context_does_not_imply_current_kernel(self) -> None:
        result = classify_sentinel_evidence(
            SentinelEvidenceCounts(legacy_or_historical_spatial_count=12)
        )
        self.assertEqual(result.evidence_class, "SENTINEL_LEGACY_CONTEXT_ONLY")
        self.assertFalse(result.local_kernel_allowed)
        self.assertFalse(result.uncertainty_kernel_allowed)

    def test_no_evidence_abstains(self) -> None:
        result = classify_sentinel_evidence(SentinelEvidenceCounts())
        self.assertEqual(result.evidence_class, "ABSTAIN_NO_OCCURRENCE_SUPPORT")
        self.assertFalse(result.broad_sector_context_available)

    def test_negative_counts_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            SentinelEvidenceCounts(recent_region_only_count=-1)


if __name__ == "__main__":
    unittest.main()
