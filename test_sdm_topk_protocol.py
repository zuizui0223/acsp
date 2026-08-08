import json
from pathlib import Path
import unittest

from acsp.automatic_sdm import AutomaticSdmCoreConfig
from predeclare_sdm_topk_cohort import _canonical_fingerprint


class SdmTopKProtocolTests(unittest.TestCase):
    def setUp(self):
        self.path = Path("validation/sdm_topk_protocol.json")
        self.protocol = json.loads(self.path.read_text())

    def test_protocol_fingerprint_is_valid(self):
        self.assertEqual(
            _canonical_fingerprint(self.protocol),
            "12a53c8bdf2493038809d6a1021a7dcf2ee7c07ea891ad5b0862d2ee2813f7b2",
        )

    def test_production_sdm_defaults_are_frozen(self):
        sdm = self.protocol["production_sdm"]
        self.assertEqual(sdm["presence_working_cap"], 300)
        self.assertEqual(sdm["background_count"], 500)
        self.assertEqual(sdm["area_mode"], "bounding box")
        self.assertEqual(sdm["rectangle_margin_km"], 20.0)
        self.assertEqual(sdm["prediction_max_pixels"], 40000)
        self.assertEqual(sdm["resolution"], "power-climatology")
        self.assertEqual(
            sdm["automatic_sdm_core_fingerprint"],
            AutomaticSdmCoreConfig().manifest()["fingerprint"],
        )

    def test_primary_estimand_keeps_sdm_failures_visible(self):
        primary = self.protocol["failure_estimands"]["primary"]
        self.assertIn("SDM-only fit/extraction failures score zero", primary)
        self.assertEqual(self.protocol["outer_validation"]["top_k"], 5)
        self.assertEqual(self.protocol["outer_validation"]["recovery_radius_km"], 10.0)

    def test_cohort_is_untouched_and_exclusions_are_declared(self):
        cohort = self.protocol["cohort"]
        self.assertEqual(cohort["pair_count"], 24)
        self.assertEqual(cohort["seed"], 20260808)
        self.assertEqual(set(cohort["taxon_groups"]), {"plant", "animal"})
        self.assertGreaterEqual(len(self.protocol["exclusion_files"]), 6)
        for path in self.protocol["exclusion_files"]:
            self.assertTrue(Path(path).exists(), path)


if __name__ == "__main__":
    unittest.main()
