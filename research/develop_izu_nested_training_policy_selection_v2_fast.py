#!/usr/bin/env python3
"""Computationally optimized runner for strict nested policy selection v2.

Scientific design is identical to `develop_izu_nested_training_policy_selection_v2.py`.
Only the greedy max-coverage implementation is replaced by an exact sparse
implementation whose equivalence is regression-tested.
"""
from __future__ import annotations

import develop_izu_nested_training_policy_selection as base
import develop_izu_nested_training_policy_selection_v2 as strict
from fast_max_coverage import greedy_coverage_order_fast


if __name__ == "__main__":
    base.greedy_coverage_order = greedy_coverage_order_fast
    base.select_q_from_inner = strict.strict_select_q_from_inner
    base.main()
