from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from research.audit_cirsium_fresh_sentinel_cross_unit_policy_alias import (
    COARSE_CONTRACT,
    COARSE_RECEIPT,
    FINE_GRID_RECEIPT,
    FINE_PATCH_RECEIPT,
    ROOT,
    SOURCE_CONTRACT,
    UNIT_CONTRACT,
    audit_cross_unit_policy_alias,
    main,
)


def test_public_contract_audit_finds_shared_grassland_policy_not_confirmed_spatial_identity() -> None:
    x = audit_cross_unit_policy_alias()
    assert x["status"] == "SHARED_GRASSLAND_POLICY_CONFIRMED_SPATIAL_IDENTITY_UNVERIFIED"
    assert x["biological_taxon_count"] == 4
    assert x["distinct_frozen_structural_family_count"] == 3
    assert x["shared_policy_units"] == ["CIR12", "CIR13"]
    assert x["shared_counts"]["fine_grid_candidate_count"] == 715103
    assert x["shared_counts"]["structural_source_complete_count"] == 607501
    assert x["shared_counts"]["transferred_2p5pct_retained_cell_count"] == 15187
    assert x["shared_counts"]["complete_link_patch_count"] == 654
    assert x["same_public_coarse_and_fine_counts"] is True
    assert x["private_patch_membership_equality_verified"] is False
    assert x["different_gzip_sha256_establishes_spatial_independence"] is False
    assert x["prospective_field_outcomes_opened"] is False
    assert x["species_specific_model_generality_claim_authorized"] is False
    frozen = json.loads(
        (ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_cross_unit_policy_alias_result_v1.json")
        .read_text(encoding="utf-8")
    )
    assert x == frozen


def _contract_copies(tmp_path: Path) -> Path:
    for name in (
        SOURCE_CONTRACT, COARSE_CONTRACT, UNIT_CONTRACT, COARSE_RECEIPT,
        FINE_GRID_RECEIPT, FINE_PATCH_RECEIPT,
    ):
        dst = tmp_path / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dst)
    return tmp_path


@pytest.mark.parametrize(
    ("filename", "edit", "message"),
    [
        (
            SOURCE_CONTRACT,
            lambda x: x["unit_source_requirements"]["CIR13"].update({"required_coarse_sources": ["terrain"]}),
            "source requirements differ",
        ),
        (
            COARSE_CONTRACT,
            lambda x: x["orders"]["CIR13"].update({"direct_landcover_signal": "different"}),
            "coarse order direct_landcover_signal differs",
        ),
        (
            FINE_PATCH_RECEIPT,
            lambda x: x["units"]["CIR13"].update({"complete_link_patch_count": 655}),
            "counts diverged",
        ),
        (
            UNIT_CONTRACT,
            lambda x: x["unit_roles"]["CIR13"].update({"structural_feature_family": "FOREST_EDGE_STRUCTURE"}),
            "structural family no longer shared",
        ),
    ],
)
def test_alias_drift_fails_closed(
    tmp_path: Path, filename: str, edit: object, message: str
) -> None:
    root = _contract_copies(tmp_path)
    path = root / filename
    obj = json.loads(path.read_text(encoding="utf-8"))
    edit(obj)
    path.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        audit_cross_unit_policy_alias(root)


def test_cli_writes_only_public_summary_and_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    out = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["audit", "--out-json", str(out)])
    assert main() == 0
    value = json.loads(out.read_text(encoding="utf-8"))
    assert value["private_coordinate_set_equality_verified"] is False
    assert "latitude" not in value
    assert "longitude" not in value
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        main()
