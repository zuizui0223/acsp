#!/usr/bin/env python3
"""Run the NDVI refinement with an exact precomputed matched-random audit."""
from __future__ import annotations

import campanula_ndvi_refinement as refinement
from campanula_fast_random import fast_matched_random_success


if __name__ == "__main__":
    refinement.matched_random_success = fast_matched_random_success
    refinement.main()
