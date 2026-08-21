"""Regression tests for the planner-free validated package import boundary."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def _run_clean_interpreter(source: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_import_acsp_does_not_eagerly_load_legacy_planner() -> None:
    _run_clean_interpreter(
        "import sys, acsp; "
        "assert 'acsp.planning' not in sys.modules, sorted(sys.modules)"
    )


def test_validated_top_level_exports_remain_planner_free() -> None:
    _run_clean_interpreter(
        "import sys, acsp; "
        "from acsp import validated_robust_candidate_patches, discover_validated_candidate_patches; "
        "assert callable(validated_robust_candidate_patches); "
        "assert callable(discover_validated_candidate_patches); "
        "assert 'acsp.planning' not in sys.modules, sorted(sys.modules)"
    )


def test_legacy_planner_exports_still_resolve_on_demand() -> None:
    _run_clean_interpreter(
        "import sys, acsp; "
        "assert 'acsp.planning' not in sys.modules; "
        "from acsp import integrated_candidate_scores; "
        "assert callable(integrated_candidate_scores); "
        "assert 'acsp.planning' in sys.modules"
    )
