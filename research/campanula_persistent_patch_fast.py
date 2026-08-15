#!/usr/bin/env python3
"""Run a bounded persistent-patch screen where complete recovery is feasible."""
from __future__ import annotations

import campanula_persistent_patch as patch


if __name__ == "__main__":
    # NDVI point support proves that <3.8053% cannot recover all 19 clusters at
    # 1 km. Do not spend development time on impossible support thresholds.
    patch.SUPPORT_FRACTIONS = (0.0381, 0.05, 0.075, 0.10)
    # Complete-link patch count is monotone non-increasing as the merge ceiling
    # grows. Screen a practical 500-m patch scale and the predeclared 1-km
    # maximum-diameter scale first; only refine intermediate scales if needed.
    patch.MERGE_DISTANCES_M = (500.0, 1000.0)
    patch.main()
