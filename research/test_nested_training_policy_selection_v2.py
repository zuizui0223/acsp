from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import develop_izu_nested_training_policy_selection_v2 as mod


class StrictNestedSupportSelectionTests(unittest.TestCase):
    def _folds(self):
        folds = []
        for repeat in (1, 2, 3):
            train = pd.DataFrame({"x": [1, 2, 3, 4, 5, 6]})
            held = pd.DataFrame(
                {
                    "lat": [34.0] * 10,
                    "lon": [139.0] * 10,
                    "repeat": [repeat] * 10,
                }
            )
            folds.append({"train": train, "held": held, "signature": (repeat,)})
        return pd.DataFrame(), folds

    @staticmethod
    def _attach(frame, **kwargs):
        return frame.copy()

    @staticmethod
    def _orders_with_infeasible_q(*args, **kwargs):
        # q=.05 has fewer than K=5 centers and must never be selected even if
        # its available folds would appear excellent.
        return {
            0.05: pd.DataFrame({"q": [0.05] * 4}),
            0.10: pd.DataFrame({"q": [0.10] * 5}),
            0.25: pd.DataFrame({"q": [0.25] * 5}),
            1.00: pd.DataFrame({"q": [1.00] * 5}),
        }

    @staticmethod
    def _evaluate_positive_q10(selected, held, radius):
        q = float(selected["q"].iloc[0])
        recovered = {0.05: 10, 0.10: 3, 0.25: 2, 1.00: 2}[q]
        return {"recovered": recovered}

    def test_infeasible_q_cannot_win_on_partial_inner_folds(self):
        with patch.object(mod.bench, "make_folds", return_value=self._folds()), patch.object(
            mod.bench, "attach_public_features", side_effect=self._attach
        ), patch.object(mod.base, "make_orders", side_effect=self._orders_with_infeasible_q), patch.object(
            mod, "evaluate", side_effect=self._evaluate_positive_q10
        ):
            selected, diagnostics, reason = mod.strict_select_q_from_inner(
                pd.DataFrame({"island": ["x"]}),
                pd.DataFrame(),
                pd.DataFrame({"x": range(8)}),
                {},
                quantiles=[0.05, 0.10, 0.25, 1.00],
                budgets=[5],
                radius=1.0,
                transform=None,
                crs=None,
                surfaces={},
                inner_cfg={
                    "block_degrees": 0.03,
                    "repeats": 3,
                    "holdout_fraction": 0.25,
                    "minimum_training_prototypes": 6,
                },
                seed=1,
            )
        self.assertEqual(reason, "ok")
        self.assertEqual(selected[5], 0.10)
        q05 = next(row for row in diagnostics if row["support_quantile"] == 0.05)
        self.assertFalse(q05["q_feasible_all_inner_folds"])

    def test_no_positive_paired_lift_falls_back_to_q1(self):
        def orders(*args, **kwargs):
            return {
                0.10: pd.DataFrame({"q": [0.10] * 5}),
                0.25: pd.DataFrame({"q": [0.25] * 5}),
                1.00: pd.DataFrame({"q": [1.00] * 5}),
            }

        def evaluate(selected, held, radius):
            q = float(selected["q"].iloc[0])
            return {"recovered": {0.10: 1, 0.25: 2, 1.00: 2}[q]}

        with patch.object(mod.bench, "make_folds", return_value=self._folds()), patch.object(
            mod.bench, "attach_public_features", side_effect=self._attach
        ), patch.object(mod.base, "make_orders", side_effect=orders), patch.object(
            mod, "evaluate", side_effect=evaluate
        ):
            selected, _, _ = mod.strict_select_q_from_inner(
                pd.DataFrame({"island": ["x"]}), pd.DataFrame(), pd.DataFrame({"x": range(8)}), {},
                quantiles=[0.10, 0.25, 1.00], budgets=[5], radius=1.0,
                transform=None, crs=None, surfaces={},
                inner_cfg={"block_degrees": 0.03, "repeats": 3, "holdout_fraction": 0.25, "minimum_training_prototypes": 6},
                seed=2,
            )
        self.assertEqual(selected[5], 1.0)

    def test_exact_positive_tie_prefers_broader_support(self):
        def orders(*args, **kwargs):
            return {
                0.10: pd.DataFrame({"q": [0.10] * 5}),
                0.25: pd.DataFrame({"q": [0.25] * 5}),
                1.00: pd.DataFrame({"q": [1.00] * 5}),
            }

        def evaluate(selected, held, radius):
            q = float(selected["q"].iloc[0])
            return {"recovered": {0.10: 3, 0.25: 3, 1.00: 2}[q]}

        with patch.object(mod.bench, "make_folds", return_value=self._folds()), patch.object(
            mod.bench, "attach_public_features", side_effect=self._attach
        ), patch.object(mod.base, "make_orders", side_effect=orders), patch.object(
            mod, "evaluate", side_effect=evaluate
        ):
            selected, _, _ = mod.strict_select_q_from_inner(
                pd.DataFrame({"island": ["x"]}), pd.DataFrame(), pd.DataFrame({"x": range(8)}), {},
                quantiles=[0.10, 0.25, 1.00], budgets=[5], radius=1.0,
                transform=None, crs=None, surfaces={},
                inner_cfg={"block_degrees": 0.03, "repeats": 3, "holdout_fraction": 0.25, "minimum_training_prototypes": 6},
                seed=3,
            )
        self.assertEqual(selected[5], 0.25)


if __name__ == "__main__":
    unittest.main()
