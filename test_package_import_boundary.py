"""Regression tests for the planner-free validated package import boundary."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parent


class PackageImportBoundaryTests(unittest.TestCase):
    def run_clean_interpreter(self, source: str) -> None:
        result = subprocess.run(
            [sys.executable, "-c", source],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_import_acsp_does_not_eagerly_load_legacy_planner(self) -> None:
        self.run_clean_interpreter(
            "import sys, acsp; "
            "assert 'acsp.planning' not in sys.modules, sorted(sys.modules)"
        )

    def test_validated_top_level_exports_remain_planner_free(self) -> None:
        self.run_clean_interpreter(
            "import sys, acsp; "
            "from acsp import validated_robust_candidate_patches, discover_validated_candidate_patches; "
            "assert callable(validated_robust_candidate_patches); "
            "assert callable(discover_validated_candidate_patches); "
            "assert 'acsp.planning' not in sys.modules, sorted(sys.modules)"
        )

    def test_legacy_planner_exports_still_resolve_on_demand(self) -> None:
        self.run_clean_interpreter(
            "import sys, acsp; "
            "assert 'acsp.planning' not in sys.modules; "
            "from acsp import integrated_candidate_scores; "
            "assert callable(integrated_candidate_scores); "
            "assert 'acsp.planning' in sys.modules"
        )


if __name__ == "__main__":
    unittest.main()
