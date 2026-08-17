#!/usr/bin/env python3
"""Run NDVI refinement with the same matched-random design and precomputed coverage."""
from __future__ import annotations

import campanula_ndvi_refinement as refinement
from campanula_fast_random import fast_matched_random_success


if __name__ == "__main__":
    # Only the Monte Carlo implementation changes: island-specific draw sizes,
    # recovery radius, RNG seed, and complete-recovery estimand are unchanged.
    refinement.matched_random_success = fast_matched_random_success
    refinement.main()
