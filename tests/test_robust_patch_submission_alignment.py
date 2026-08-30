import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_submission_alignment_validator_passes_network_free():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "paper" / "validate_submission_alignment.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "submission_alignment_passed"
    assert payload["authoritative_product"] == "non-ranked robust candidate patches"
    assert payload["validated_scope"] == "fixed Japanese 12-region frame"
    assert payload["confirmation_pairs"] == 96
    assert payload["confirmation_folds"] == 480
    assert payload["historical_top5_package_preserved"] is True
    assert payload["global_product_promoted"] is False


def test_historical_top5_paper_remains_separate_provenance():
    historical_manuscript = ROOT / "paper" / "MANUSCRIPT_DRAFT.md"
    historical_table = ROOT / "paper" / "generated" / "table_1_retrospective_validation.csv"
    robust_manuscript = ROOT / "paper" / "MANUSCRIPT_ROBUST_PATCH_DRAFT.md"
    robust_table = ROOT / "paper" / "generated" / "table_1_robust_patch_confirmation.csv"

    assert historical_manuscript.exists()
    assert historical_table.exists()
    assert robust_manuscript.exists()
    assert robust_table.exists()

    historical = historical_manuscript.read_text(encoding="utf-8")
    robust = robust_manuscript.read_text(encoding="utf-8")
    assert "fixed Top-5 decisions" in historical
    assert "non-ranked set of bounded robust candidate patches" in robust
