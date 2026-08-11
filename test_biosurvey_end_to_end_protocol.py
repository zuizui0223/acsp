import hashlib
import json
from pathlib import Path
import unittest


class BiosurveyEndToEndProtocolTests(unittest.TestCase):
    def test_frozen_protocol_and_broad_claim_gate(self):
        path = Path("validation/acsp_practical_core_biosurvey_end_to_end_protocol.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        stored = payload.pop("fingerprint")
        actual = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(
            stored,
            "33881b4176c4c8bcda5485189eb5b8a22ee495d766b90c4e159a584265710b2b",
        )
        self.assertEqual(stored, actual)
        self.assertEqual(payload["biosurvey_implementation"]["version"], "0.1.2")
        self.assertEqual(
            payload["biosurvey_implementation"]["commit"],
            "035fbebf3d47f823fa55b41a56a74b35dc510753",
        )
        self.assertEqual(
            payload["common_environment"]["master_grid_resolutions_degrees"],
            [0.05, 0.1],
        )
        self.assertIn(
            "10-km recovery objective",
            payload["common_environment"]["reason_for_two_resolutions"],
        )
        self.assertEqual(payload["stochastic_design"]["draws_per_region_resolution"], 10)
        self.assertEqual(len(payload["comparison"]["configurations"]), 6)
        self.assertIn(
            "all six",
            payload["comparison"]["biosurvey_family_pass_rule"],
        )
        self.assertEqual(payload["comparison"]["minimum_practical_absolute_recall_gain"], 0.015)
        self.assertEqual(payload["comparison"]["region_cluster_bootstrap_draws"], 30000)
        self.assertTrue(payload["no_retuning_after_outcome"])


if __name__ == "__main__":
    unittest.main()
