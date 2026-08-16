from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from consolidate_cross_taxon_support_gate import choose_q, exact_sign_flip_p


class CrossTaxonSupportGateTests(unittest.TestCase):
    def test_exact_sign_flip_detects_consistent_positive_differences(self):
        values = np.array([0.1] * 10, dtype=float)
        self.assertLess(exact_sign_flip_p(values), 0.05)

    def test_stable_q_is_selected_from_other_taxa(self):
        ids = range(15)
        wide = pd.DataFrame(
            {
                0.05: [0.20] * 15,
                0.10: [0.35] * 15,
                0.25: [0.22] * 15,
                0.50: [0.20] * 15,
                0.75: [0.19] * 15,
                1.00: [0.20] * 15,
            },
            index=ids,
        )
        q, diagnostics = choose_q(wide, [0.05, 0.10, 0.25, 0.50, 0.75, 1.0], seed=1, bootstrap_draws=2000)
        self.assertEqual(q, 0.10)
        self.assertTrue(next(row for row in diagnostics if row["support_quantile"] == 0.10)["passes"])

    def test_no_stable_ecological_lift_falls_back_to_geometry(self):
        wide = pd.DataFrame(
            {
                0.05: [0.20] * 15,
                0.10: [0.19] * 15,
                0.25: [0.20] * 15,
                0.50: [0.18] * 15,
                0.75: [0.20] * 15,
                1.00: [0.20] * 15,
            }
        )
        q, _ = choose_q(wide, [0.05, 0.10, 0.25, 0.50, 0.75, 1.0], seed=2, bootstrap_draws=2000)
        self.assertEqual(q, 1.0)

    def test_broader_q_wins_exact_stable_tie(self):
        wide = pd.DataFrame(
            {
                0.05: [0.30] * 15,
                0.10: [0.30] * 15,
                0.25: [0.20] * 15,
                0.50: [0.20] * 15,
                0.75: [0.20] * 15,
                1.00: [0.20] * 15,
            }
        )
        q, _ = choose_q(wide, [0.05, 0.10, 0.25, 0.50, 0.75, 1.0], seed=3, bootstrap_draws=2000)
        self.assertEqual(q, 0.10)


if __name__ == "__main__":
    unittest.main()
