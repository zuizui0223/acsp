import json
from pathlib import Path

from paper.build_paper_outputs import _load_global_observability_boundary


ROOT = Path(__file__).resolve().parents[1]


def test_paper_exports_provider_abort_separately_from_hypothesis_status():
    table, terminal = _load_global_observability_boundary()
    row = table.iloc[0]
    assert row["workflow_run_id"] == 33031292325
    assert row["historical_unique_species_queries"] == 3161
    assert row["historical_provider_success_count"] == 3132
    assert row["historical_provider_error_count"] == 29
    assert row["supply_status"] == "protocol_abort"
    assert row["hypothesis_status"] == "unavailable"
    assert row["promotion_status"] == "not_promoted"
    assert bool(row["heldout_2021_2025_opened"]) is False
    assert bool(row["observability_hypothesis_tested"]) is False
    assert bool(row["validated_japan_product_changed"]) is False
    assert terminal["claim_boundary"]["technical_abort_is_scientific_negative"] is False


def test_manuscript_preserves_japan_and_global_claim_boundary():
    manuscript = (ROOT / "paper/MANUSCRIPT_DRAFT.md").read_text(encoding="utf-8")
    assert "supply `protocol_abort`, hypothesis `unavailable`" in manuscript
    assert "2021–2025 heldout" in manuscript
    assert "does not change the validated Japanese results" in manuscript
    assert "globally validated name-only product" in manuscript


def test_generated_manifest_cannot_promote_global_product():
    manifest = json.loads((ROOT / "paper/generated/paper_output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["global_observability_status"] == "abort_not_evaluable"
    assert manifest["global_observability_supply_status"] == "protocol_abort"
    assert manifest["global_observability_hypothesis_status"] == "unavailable"
    assert manifest["global_observability_heldout_opened"] is False
    assert manifest["global_product_promoted"] is False
    assert manifest["validated_japan_product_changed_by_global_abort"] is False
    assert "table_s6_global_observability_boundary.csv" in manifest["outputs"]
