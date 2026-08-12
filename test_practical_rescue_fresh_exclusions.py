#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from prepare_practical_rescue_fresh_exclusions import run


class PracticalRescueFreshExclusionTests(unittest.TestCase):
    def test_frozen_union_has_264_unique_taxa_and_no_sampling(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / "old.csv"
            rescue = root / "rescue.csv"
            output = root / "out"
            pd.DataFrame({"scientific_name": [f"old_{i:03d}" for i in range(192)]}).to_csv(old, index=False)
            # Repeat each development name across five folds, mirroring the stored fold table.
            pd.DataFrame({
                "scientific_name": [f"dev_{i:03d}" for i in range(72) for _ in range(5)],
                "repeat": [r for _ in range(72) for r in range(1, 6)],
            }).to_csv(rescue, index=False)
            manifest = run(old, rescue, output)
            excluded = pd.read_csv(output / "excluded_taxa.csv")
            self.assertEqual(manifest["excluded_unique_taxa"], 264)
            self.assertEqual(manifest["cross_source_overlap_taxa"], 0)
            self.assertFalse(manifest["new_confirmation_taxa_sampled"])
            self.assertFalse(manifest["occurrence_outcomes_inspected"])
            self.assertEqual(len(excluded), 264)
            self.assertEqual(excluded["scientific_name"].nunique(), 264)

    def test_overlap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_names = [f"old_{i:03d}" for i in range(192)]
            rescue_names = ["old_000", *[f"dev_{i:03d}" for i in range(71)]]
            old = root / "old.csv"
            rescue = root / "rescue.csv"
            pd.DataFrame({"scientific_name": old_names}).to_csv(old, index=False)
            pd.DataFrame({"scientific_name": rescue_names}).to_csv(rescue, index=False)
            with self.assertRaisesRegex(ValueError, "overlap"):
                run(old, rescue, root / "out")


if __name__ == "__main__":
    unittest.main()
