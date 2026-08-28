import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "paper/generated"


def test_evidence_availability_preserves_three_distinct_terminal_semantics():
    table = pd.read_csv(GENERATED / "table_2_evidence_availability.csv").set_index("scope")
    assert list(table.index) == [
        "validated_japan_12_region_core",
        "country_framed_fresh_extension",
        "provider_eligible_observability_first_activation",
    ]
    assert table.loc["validated_japan_12_region_core", "promotion_status"] == "validated_product"
    assert table.loc["country_framed_fresh_extension", "promotion_status"] == "not_promoted"
    provider = table.loc["provider_eligible_observability_first_activation"]
    assert provider["terminal_status"] == "protocol_abort__hypothesis_unavailable"
    assert provider["heldout_or_response_status"] == "2021_2025_heldout_unopened"
    assert "successor_requires_new_contract" in provider["development_stop"]


def test_paper_figures_are_manifested_svg_outputs_without_legacy_campanula_tables():
    manifest = json.loads((GENERATED / "paper_output_manifest.json").read_text(encoding="utf-8"))
    for name in (
        "table_2_evidence_availability.csv",
        "figure_1_primary_recovery.svg",
        "figure_2_evidence_boundary.svg",
    ):
        assert name in manifest["outputs"]
        assert (GENERATED / name).stat().st_size > 500
    for name in (
        "table_3_campanula_baseline_validation.csv",
        "table_4_campanula_area_balanced_update.csv",
        "table_5_campanula_area_balanced_top5.csv",
    ):
        assert name not in manifest["outputs"]
        assert not (GENERATED / name).exists()


def test_readme_and_manuscript_apply_the_same_publication_hard_stop():
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    paper_readme = (ROOT / "paper/README.md").read_text(encoding="utf-8")
    manuscript = (ROOT / "paper/MANUSCRIPT_DRAFT.md").read_text(encoding="utf-8")
    assert "Stop same-cohort rescue" in root_readme
    assert "Do not delay submission for a global positive" in paper_readme
    assert "Submission does not require a global positive" in manuscript
    assert "hypothesis `unavailable`" in root_readme
