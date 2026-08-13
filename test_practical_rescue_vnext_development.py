import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from benchmark_practical_rescue_vnext_development import (
    _canonical_protocol,
    _inference,
    _outer_assignment,
)
from acsp.practical_rescue_vnext import VNEXT_PROTOCOL_FINGERPRINT


class VNextDevelopmentContractTests(unittest.TestCase):
    def test_frozen_protocol_self_hash(self):
        payload, calculated = _canonical_protocol(
            Path("validation/acsp_practical_rescue_vnext_development_protocol.json")
        )
        self.assertEqual(calculated, VNEXT_PROTOCOL_FINGERPRINT)
        self.assertEqual(payload["protocol_fingerprint"], VNEXT_PROTOCOL_FINGERPRINT)
        self.assertEqual(payload["base_policy"]["anchors_preserved"], 4)
        self.assertEqual(payload["base_policy"]["learned_slots"], 1)
        self.assertEqual(payload["learned_fifth_slot"]["replacement_margin_absolute_recall"], 0.015)
        self.assertTrue(payload["redesign_basis"]["new_untouched_confirmation_required"])

    def test_outer_pair_assignment_is_complete_and_balanced(self):
        mapping = _outer_assignment(list(range(1, 193)), 8, 20260813)
        self.assertEqual(sorted(mapping), list(range(1, 193)))
        counts = {fold: list(mapping.values()).count(fold) for fold in range(1, 9)}
        self.assertEqual(set(counts.values()), {24})
        self.assertEqual(mapping, _outer_assignment(list(range(1, 193)), 8, 20260813))

    def test_inference_detects_clear_positive_signal(self):
        values = np.array([0.02, 0.03, 0.01, 0.04] * 24, dtype=float)
        result = _inference(values, 5000, 7)
        self.assertGreater(result["mean_difference"], 0.015)
        self.assertGreater(result["bootstrap_95ci_low"], 0.0)
        self.assertLess(result["sign_flip_p"], 0.05)


if __name__ == "__main__":
    unittest.main()
