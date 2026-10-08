from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.audit_cirsium_fresh_sentinel_v2_patch_support_connectivity import (
    audit_patch_support_connectivity,
)


def _order() -> pd.DataFrame:
    # The 2.5% frozen tier retains the first 5 of 200 cells. Row/column
    # adjacency is independent of incidental ranking and file row order.
    positions = [(0, 0), (0, 1), (0, 4), (0, 5), (0, 6)]
    positions.extend((10 + i, 50) for i in range(195))
    return pd.DataFrame({
        "candidate_cell_id": [f"CIR02_cell_{i:03d}" for i in range(1, 201)],
        "cohort_unit_id": ["CIR02"] * 200,
        "structural_rank": list(range(1, 201)),
        "grid_row": [p[0] for p in positions],
        "grid_col": [p[1] for p in positions],
    })


def _patches() -> pd.DataFrame:
    return pd.DataFrame({
        "cohort_unit_id": ["CIR02", "CIR02"],
        "zone_id": ["CIR02-Z001", "CIR02-Z002"],
        "zone_member_count": [3, 2],
        "zone_member_site_ids": [
            "CIR02_cell_001;CIR02_cell_002;CIR02_cell_003",
            "CIR02_cell_004;CIR02_cell_005",
        ],
    })


def test_audit_detects_fragmentation_without_changing_patch_membership() -> None:
    result = audit_patch_support_connectivity(_order(), _patches(), unit_id="CIR02")
    assert result["retained_support_cell_count"] == 5
    assert result["complete_link_patch_count"] == 2
    assert result["connected_patch_count"] == 1
    assert result["fragmented_patch_count"] == 1
    assert result["fragmented_patch_fraction"] == 0.5
    assert result["retained_cells_in_fragmented_patches"] == 3
    assert result["retained_cells_in_fragmented_fraction"] == 0.6
    assert result["within_patch_component_count_total"] == 3
    assert result["extra_within_patch_components"] == 1
    assert result["maximum_components_per_patch"] == 2
    assert result["support_mask_connected_component_count"] == 2
    assert result["all_retained_cells_represented_once"] is True
    assert result["field_selector_validation"] is False
    assert result["support_mask_gap_interpreted_as_biological_barrier"] is False


def test_audit_is_invariant_to_row_order() -> None:
    baseline = audit_patch_support_connectivity(_order(), _patches(), unit_id="CIR02")
    shuffled = _order().sample(frac=1, random_state=3).reset_index(drop=True)
    other = audit_patch_support_connectivity(shuffled, _patches().iloc[::-1], unit_id="CIR02")
    assert other == baseline


def test_moore_diagonal_counts_as_connected() -> None:
    order = _order()
    order.loc[2, ["grid_row", "grid_col"]] = [1, 1]
    order.loc[3, ["grid_row", "grid_col"]] = [1, 2]
    order.loc[4, ["grid_row", "grid_col"]] = [2, 2]
    result = audit_patch_support_connectivity(order, _patches(), unit_id="CIR02")
    assert result["fragmented_patch_count"] == 0
    assert result["support_mask_connected_component_count"] == 1


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ("repeated", "multiple patches"),
        ("missing", "conserve"),
        ("outside", "outside the frozen retained"),
        ("declared_count", "count disagrees"),
    ],
)
def test_audit_fails_closed_on_inconsistent_patch_membership(change: str, match: str) -> None:
    patches = _patches()
    if change == "repeated":
        patches.loc[1, "zone_member_site_ids"] = "CIR02_cell_003;CIR02_cell_005"
    elif change == "missing":
        patches.loc[1, "zone_member_site_ids"] = "CIR02_cell_004"
        patches.loc[1, "zone_member_count"] = 1
    elif change == "outside":
        patches.loc[1, "zone_member_site_ids"] = "CIR02_cell_004;CIR02_cell_010"
    else:
        patches.loc[0, "zone_member_count"] = 4
    with pytest.raises(ValueError, match=match):
        audit_patch_support_connectivity(_order(), patches, unit_id="CIR02")


def test_audit_fails_on_invalid_source_grid_and_rank() -> None:
    frame = _order()
    frame.loc[0, "grid_row"] = np.nan
    with pytest.raises(ValueError, match="grid_row must be complete"):
        audit_patch_support_connectivity(frame, _patches(), unit_id="CIR02")

    frame = _order()
    frame.loc[1, "grid_col"] = frame.loc[0, "grid_col"]
    frame.loc[1, "grid_row"] = frame.loc[0, "grid_row"]
    with pytest.raises(ValueError, match="coordinates are not unique"):
        audit_patch_support_connectivity(frame, _patches(), unit_id="CIR02")

    frame = _order()
    frame.loc[0, "structural_rank"] = 1.5
    with pytest.raises(ValueError, match="structural_rank must be complete finite integers"):
        audit_patch_support_connectivity(frame, _patches(), unit_id="CIR02")


def test_audit_rejects_wrong_unit_and_empty_input() -> None:
    with pytest.raises(ValueError, match="unit drift"):
        audit_patch_support_connectivity(_order(), _patches(), unit_id="CIR13")
    with pytest.raises(ValueError, match="nonempty"):
        audit_patch_support_connectivity(_order().iloc[:0], _patches(), unit_id="CIR02")
