from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import research.audit_cirsium_fresh_sentinel_v2_frozen_patch_topology as mod


def _patches(unit: str = "CIR06") -> pd.DataFrame:
    return pd.DataFrame({
        "zone_id": [f"{unit}-Z001", f"{unit}-Z002", f"{unit}-Z003"],
        "cohort_unit_id": [unit] * 3,
        "zone_member_count": [3, 2, 1],
        "zone_member_site_ids": [
            f"{unit}_r0_c0;{unit}_r0_c1;{unit}_r3_c3",
            f"{unit}_r3_c4;{unit}_r4_c4",
            f"{unit}_r100_c100",
        ],
        "zone_merge_threshold_m": [1000.0] * 3,
        "zone_radius_m": [425.0, 100.0, 0.0],
    })


def test_frozen_patch_mask_topology_is_independent_of_full_structural_order() -> None:
    report = mod.audit_frozen_patch_membership(
        _patches(), unit_id="CIR06",
        expected_cells=6, expected_patches=3, expected_singletons=1,
    )
    assert report["retained_support_cell_count"] == 6
    assert report["complete_link_patch_count"] == 3
    assert report["connected_patch_count"] == 2
    assert report["disconnected_patch_count"] == 1
    assert report["disconnected_patch_fraction"] == pytest.approx(1/3)
    assert report["cells_in_disconnected_patch_fraction"] == pytest.approx(0.5)
    assert report["global_mask_component_count"] == 3
    assert report["within_patch_component_count_total"] == 4
    assert report["extra_within_patch_components"] == 1
    assert report["maximum_components_per_patch"] == 2
    assert report["singleton_patch_count"] == 1
    assert report["source_integrity_claim_authorized"] is False
    assert report["original_structural_order_reproduced"] is None
    assert report["original_structural_order_reproduction_tested_by_this_route"] is False
    assert report["coordinates_or_candidate_ids_in_public_output"] is False


def test_moore_diagonal_adjacency_and_row_order_invariance() -> None:
    rows = _patches()
    rows.loc[0, "zone_member_site_ids"] = "CIR06_r0_c0;CIR06_r1_c1;CIR06_r2_c2"
    rows.loc[1, "zone_member_site_ids"] = "CIR06_r3_c3;CIR06_r4_c4"
    rows.loc[2, "zone_member_site_ids"] = "CIR06_r5_c5"
    forward = mod.audit_frozen_patch_membership(
        rows, unit_id="CIR06", expected_cells=6, expected_patches=3,
        expected_singletons=1,
    )
    reversed_rows = mod.audit_frozen_patch_membership(
        rows.iloc[::-1], unit_id="CIR06", expected_cells=6,
        expected_patches=3, expected_singletons=1,
    )
    assert forward == reversed_rows
    assert forward["disconnected_patch_count"] == 0
    assert forward["global_mask_component_count"] == 1


@pytest.mark.parametrize("problem", [
    "duplicate_member", "unparseable_id", "missing_member",
    "incorrect_count", "duplicate_zone", "wrong_unit",
    "wrong_threshold", "wrong_radius", "wrong_singleton",
])
def test_membership_and_geometric_contract_fail_closed(problem: str) -> None:
    rows = _patches()
    cells, patches, singletons = 6, 3, 1
    if problem == "duplicate_member":
        rows.loc[1, "zone_member_site_ids"] = "CIR06_r3_c3;CIR06_r4_c4"
    elif problem == "unparseable_id":
        rows.loc[1, "zone_member_site_ids"] = "CIR06_r3_c4;confidential"
    elif problem == "missing_member":
        rows.loc[1, "zone_member_site_ids"] = "CIR06_r3_c4"
        rows.loc[1, "zone_member_count"] = 1
    elif problem == "incorrect_count":
        rows.loc[0, "zone_member_count"] = 4
    elif problem == "duplicate_zone":
        rows.loc[1, "zone_id"] = rows.loc[0, "zone_id"]
    elif problem == "wrong_unit":
        rows.loc[0, "cohort_unit_id"] = "CIR12"
    elif problem == "wrong_threshold":
        rows.loc[0, "zone_merge_threshold_m"] = 1400.0
    elif problem == "wrong_radius":
        rows.loc[0, "zone_radius_m"] = 1200.0
    elif problem == "wrong_singleton":
        singletons = 2
    with pytest.raises(ValueError):
        mod.audit_frozen_patch_membership(
            rows, unit_id="CIR06",
            expected_cells=cells, expected_patches=patches,
            expected_singletons=singletons,
        )


def test_exact_frozen_patch_compressed_sha_required_before_opening_membership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv_path = tmp_path / "private_patch.csv.gz"
    rows = _patches()
    rows.to_csv(csv_path, index=False, compression={"method": "gzip", "mtime": 0})
    file_hash = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    receipt = {
        "status": "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED",
        "source_pr": 247,
        "units": {
            unit: {
                "private_patch_sha256": file_hash,
                "transferred_2p5pct_retained_cell_count": 6,
                "complete_link_patch_count": 3,
                "singleton_patch_count": 1,
            }
            for unit in mod.UNITS
        },
    }
    receipt_path = tmp_path / "frozen.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(mod, "FROZEN_PATH", receipt_path)
    output = tmp_path / "summary.json"
    result = mod.run_frozen_patch_topology(
        unit_id="CIR06", private_patches=csv_path, public_summary=output,
    )
    assert result["verified_original_patch_sha256"] == file_hash
    payload = output.read_text(encoding="utf-8")
    assert "CIR06_r" not in payload
    assert "zone_member_site_ids" not in payload
    assert "latitude" not in payload and "longitude" not in payload
    with pytest.raises(ValueError, match="refusing to overwrite"):
        mod.run_frozen_patch_topology(
            unit_id="CIR06", private_patches=csv_path, public_summary=output,
        )

    output.unlink()
    altered = rows.copy()
    altered.loc[1, "zone_member_site_ids"] = "CIR06_r3_c4;CIR06_r5_c4"
    altered.to_csv(csv_path, index=False, compression={"method": "gzip", "mtime": 0})
    with pytest.raises(ValueError, match="patch SHA differs"):
        mod.run_frozen_patch_topology(
            unit_id="CIR06", private_patches=csv_path, public_summary=output,
        )
    assert not output.exists()


def test_real_contract_preserves_separation_from_pr250() -> None:
    contract = mod._contract()
    assert contract["sole_private_input"] == "private_patch_csv_gz_from_fixed_fine_patch_transfer"
    assert contract["interpretation"]["existing_strict_pr250_gate_unchanged"] is True
    assert contract["interpretation"]["full_structural_order_hash_gate_waived"] is False
    assert contract["interpretation"]["source_input_integrity_evaluated"] is False
    assert contract["interpretation"]["prospective_field_outcomes_opened"] is False
