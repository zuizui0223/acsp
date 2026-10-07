from __future__ import annotations

import numpy as np
import pandas as pd

import research.test_cirsium_fresh_sentinel_v2_fine_patch_transfer_feasibility as mod


def _selected_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_id": ["c3", "c1", "c2", "c5", "c4"],
            "cohort_unit_id": ["CIR02"] * 5,
            "ecological_support_rank": [0.03, 0.01, 0.02, 0.05, 0.04],
            "latitude": [35.0, 35.0005, 35.0010, 35.02, 35.0205],
            "longitude": [139.0, 139.0005, 139.0010, 139.02, 139.0205],
        }
    )


def test_accelerated_complete_link_matches_reference_membership() -> None:
    mod.assert_reference_parity(_selected_fixture())


def test_accelerated_complete_link_matches_reference_on_random_clusters() -> None:
    rng = np.random.default_rng(42)
    centers = [(35.0, 139.0), (35.02, 139.02), (35.1, 139.1)]
    rows = []
    serial = 0
    for lat0, lon0 in centers:
        for _ in range(15):
            serial += 1
            rows.append(
                {
                    "site_id": f"s{serial:03d}",
                    "cohort_unit_id": "CIR12",
                    "ecological_support_rank": serial / 1000.0,
                    "latitude": lat0 + rng.normal(0.0, 0.002),
                    "longitude": lon0 + rng.normal(0.0, 0.002),
                }
            )
    mod.assert_reference_parity(pd.DataFrame(rows))


def _order(n: int = 200) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cohort_unit_id": ["CIR06"] * n,
            "candidate_cell_id": [f"CIR06_r{i:04d}_c0000" for i in range(n)],
            "structural_rank": np.arange(1, n + 1, dtype=int),
            "structural_support": np.linspace(1.0, 0.0, n),
            "latitude": 35.0 + np.arange(n) * 0.0002,
            "longitude": np.full(n, 139.0),
        }
    )


def test_fine_transfer_uses_exact_transferred_constants_and_no_new_stopping() -> None:
    patches, summary = mod.build_fine_patch_transfer(_order(), unit_id="CIR06")
    assert summary["source_complete_structural_order_rows"] == 200
    assert summary["retained_support_cell_count"] == 5
    assert summary["support_fraction"] == 0.025
    assert summary["patch_merge_distance_m"] == 1000.0
    assert summary["patch_count"] > 0
    assert summary["source_indeterminate_included"] is False
    assert summary["source_indeterminate_ranked"] is False
    assert summary["field_outcomes_opened"] is False
    assert summary["recovery_used"] is False
    assert summary["transfer_is_validated_selector"] is False
    assert summary["top_k_added_beyond_transferred_fraction"] is False
    assert summary["support_threshold_refit"] is False
    assert summary["target_patch_count_used"] is False
    assert len(patches) == summary["patch_count"]


def test_retained_count_is_ceiling_of_two_point_five_percent() -> None:
    _, summary = mod.build_fine_patch_transfer(_order(201), unit_id="CIR06")
    assert summary["retained_support_cell_count"] == 6
