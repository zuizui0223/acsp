from __future__ import annotations

import pandas as pd
import pytest

from acsp.discovery.scale_separated import (
    METHOD_ID,
    rank_coverage_then_fine_structure,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_cell_id": ["A2", "A1", "A3", "B2", "B1", "C1", "C2"],
            "coverage_cell_id": ["A", "A", "A", "B", "B", "C", "C"],
            "coverage_rank": [1, 1, 1, 2, 2, 3, 3],
            "structural_support": [0.7, 0.9, 0.2, 0.4, 0.8, 0.6, 0.1],
        }
    )


def test_round_robin_uses_within_cell_structure_rank_then_coverage_rank() -> None:
    ordered, audit = rank_coverage_then_fine_structure(_frame())
    assert ordered["candidate_cell_id"].tolist() == ["A1", "B1", "C1", "A2", "B2", "C2", "A3"]
    assert ordered["within_cell_structure_rank"].tolist() == [1, 1, 1, 2, 2, 2, 3]
    assert ordered["decision_method"].eq(METHOD_ID).all()
    assert ordered["decision_rank"].tolist() == list(range(1, 8))
    assert audit.coverage_cell_count == 3
    assert audit.maximum_within_cell_depth == 3
    assert audit.fitted_weights_used is False
    assert audit.budget_used is False
    assert audit.field_outcomes_used is False


def test_absolute_structural_scores_do_not_override_coarse_coverage_order() -> None:
    frame = pd.DataFrame(
        {
            "candidate_cell_id": ["A1", "A2", "B1", "B2"],
            "coverage_cell_id": ["A", "A", "B", "B"],
            "coverage_rank": [1, 1, 2, 2],
            "structural_support": [0.01, 0.00, 1.00, 0.99],
        }
    )
    ordered, _ = rank_coverage_then_fine_structure(frame)
    assert ordered["candidate_cell_id"].tolist() == ["A1", "B1", "A2", "B2"]


def test_unequal_cell_sizes_skip_exhausted_cells_without_duplication() -> None:
    frame = pd.DataFrame(
        {
            "candidate_cell_id": ["A1", "B1", "B2", "B3"],
            "coverage_cell_id": ["A", "B", "B", "B"],
            "coverage_rank": [1, 2, 2, 2],
            "structural_support": [0.5, 0.9, 0.8, 0.7],
        }
    )
    ordered, _ = rank_coverage_then_fine_structure(frame)
    assert ordered["candidate_cell_id"].tolist() == ["A1", "B1", "B2", "B3"]
    assert ordered["candidate_cell_id"].is_unique


def test_rejects_inconsistent_or_duplicate_coverage_ranks() -> None:
    inconsistent = _frame()
    inconsistent.loc[inconsistent["candidate_cell_id"].eq("A3"), "coverage_rank"] = 2
    with pytest.raises(ValueError, match="exactly one coverage rank"):
        rank_coverage_then_fine_structure(inconsistent)

    duplicate = _frame()
    duplicate.loc[duplicate["coverage_cell_id"].eq("C"), "coverage_rank"] = 2
    with pytest.raises(ValueError, match="unique across coverage cells"):
        rank_coverage_then_fine_structure(duplicate)


def test_rejects_noncontiguous_ranks_and_outcome_columns() -> None:
    noncontiguous = _frame()
    noncontiguous.loc[noncontiguous["coverage_cell_id"].eq("C"), "coverage_rank"] = 4
    with pytest.raises(ValueError, match="complete 1..N"):
        rank_coverage_then_fine_structure(noncontiguous)

    leaked = _frame().assign(field_outcome="detected")
    with pytest.raises(ValueError, match="field-outcome-like columns"):
        rank_coverage_then_fine_structure(leaked)
