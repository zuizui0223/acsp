from __future__ import annotations

import pandas as pd
import pytest

from research.orchestrate_cirsium_fresh_sentinel_pre_field_v1 import (
    COARSE_COVERAGE_CELL_SIZE_M,
    COVERAGE_ONLY_METHOD,
    FINE_SPACING_M,
    attach_frozen_coarse_coverage,
    freeze_pre_field_orders,
    rank_coverage_only_round_robin,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_cell_id": ["a", "b", "c", "d", "e", "f"],
            "latitude": [35.0, 35.001, 35.002, 35.05, 35.051, 35.10],
            "longitude": [139.0, 139.001, 139.002, 139.05, 139.051, 139.10],
            "grid_row": [0, 1, 49, 50, 51, 100],
            "grid_col": [0, 1, 2, 50, 51, 100],
            "structural_support": [0.2, 0.9, 0.5, 0.1, 0.8, 0.7],
        }
    )


def test_five_km_coverage_cells_are_derived_from_frozen_100m_grid() -> None:
    covered, audit = attach_frozen_coarse_coverage(_frame())
    assert audit["fine_spacing_m"] == FINE_SPACING_M == 100
    assert audit["coarse_coverage_cell_size_m"] == COARSE_COVERAGE_CELL_SIZE_M == 5000
    assert audit["fine_cells_per_coarse_axis"] == 50
    assert audit["coverage_cell_count"] == 3
    assert covered.loc[covered["candidate_cell_id"].isin(["a", "b", "c"]), "coverage_cell_id"].nunique() == 1
    assert covered.loc[covered["candidate_cell_id"].isin(["d", "e"]), "coverage_cell_id"].nunique() == 1
    cell_ranks = covered.groupby("coverage_cell_id")["coverage_rank"].first().tolist()
    assert sorted(cell_ranks) == [1, 2, 3]


def test_coverage_only_order_cannot_use_structural_support() -> None:
    covered, _ = attach_frozen_coarse_coverage(_frame())
    first = rank_coverage_only_round_robin(covered)["candidate_cell_id"].tolist()
    changed = covered.copy()
    changed["structural_support"] = list(reversed(changed["structural_support"].tolist()))
    second = rank_coverage_only_round_robin(changed)["candidate_cell_id"].tolist()
    assert first == second
    assert set(rank_coverage_only_round_robin(covered)["decision_method"]) == {COVERAGE_ONLY_METHOD}


def test_scale_separated_round_one_visits_every_coarse_cell_before_depth_two() -> None:
    orders, audit = freeze_pre_field_orders(_frame())
    structural = orders["coverage_then_fine_structure"]
    cell_count = audit["coverage"]["coverage_cell_count"]
    first_round = structural.iloc[:cell_count]
    assert first_round["coverage_cell_id"].nunique() == cell_count
    assert first_round["within_cell_structure_rank"].eq(1).all()
    assert len(orders["coverage_only"]) == len(_frame())
    assert len(orders["fine_spatial_balance"]) == len(_frame())
    assert audit["field_outcomes_used"] is False
    assert audit["fitted_weights_used"] is False
    assert audit["budget_used"] is False


def test_coarse_cell_size_must_be_integer_multiple_of_fine_spacing() -> None:
    with pytest.raises(ValueError):
        attach_frozen_coarse_coverage(_frame(), fine_spacing_m=100, coarse_cell_size_m=5050)
