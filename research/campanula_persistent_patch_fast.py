#!/usr/bin/env python3
"""Run the persistent-patch screen only where complete 1-km recovery is feasible."""
from __future__ import annotations

import campanula_persistent_patch as patch


if __name__ == "__main__":
    # NDVI point support already proves that <3.8053% cannot recover all 19 at
    # 1 km. Screening below that bound is therefore computational waste, not a
    # scientific experiment. Keep multiple larger thresholds to test whether
    # broader support joins cells into fewer bounded operational patches.
    patch.SUPPORT_FRACTIONS = (0.0381, 0.05, 0.075, 0.10)
    patch.MERGE_DISTANCES_M = (300.0, 500.0, 750.0, 1000.0)
    patch.main()
