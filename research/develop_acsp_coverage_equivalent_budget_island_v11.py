#!/usr/bin/env python3
"""Bind coverage-equivalent development runner to corrected frozen protocol hash."""
from __future__ import annotations

import develop_acsp_coverage_equivalent_budget_island as runner

EXPECTED = "877cc5f4240ce5ab19c45bf16bde42eb9a32405df55c03dcf74267503d470450"

if __name__ == "__main__":
    runner.EXPECTED_DEVELOPMENT = EXPECTED
    runner.main()
