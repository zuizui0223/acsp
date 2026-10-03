"""Scale-separated coverage-then-structure ranking for experimental N4 discovery.

The primitive combines an already-frozen coarse coverage order with an
already-computed fine structural-support order inside each coarse cell. It does
not compare structural-support magnitudes across coarse cells. Instead, it visits
one best structural candidate per coverage cell before any second-best candidate,
then one second-best candidate per cell, and so on.

This gives one deterministic full order without introducing a budget, a fitted
coverage/structure weight, field outcomes, access, route cost, or stopping rule.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np
import pandas as pd

from acsp.structural_selector import _forbidden_outcome_columns


METHOD_ID = "COVERAGE_THEN_FINE_STRUCTURE_V1"


@dataclass(frozen=True)
class CoverageThenStructureAudit:
    method: str
    candidate_count: int
    coverage_cell_count: int
    maximum_within_cell_depth: int
    coverage_rank_column: str
    structural_support_column: str
    candidate_id_column: str
    ordering_rule: str
    field_outcomes_used: bool = False
    fitted_weights_used: bool = False
    budget_used: bool = False
    human_access_used: bool = False


def _stable_key(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def rank_coverage_then_fine_structure(
    frame: pd.DataFrame,
    *,
    coverage_cell_col: str = "coverage_cell_id",
    coverage_rank_col: str = "coverage_rank",
    structural_support_col: str = "structural_support",
    candidate_id_col: str = "candidate_cell_id",
) -> tuple[pd.DataFrame, CoverageThenStructureAudit]:
    """Return a deterministic full order that separates coarse and fine roles.

    Required semantics are:
    - ``coverage_cell_col`` identifies a coarse broad-search cell;
    - every candidate in one coarse cell carries the same positive integer
      ``coverage_rank_col``;
    - coarse-cell ranks form exactly ``1..number_of_cells`` and are unique across
      cells;
    - ``structural_support_col`` is a complete finite support score used only to
      rank candidates *within* each coarse cell.

    Global order is lexicographic on
    ``within_cell_structure_rank, coverage_rank, stable_candidate_hash``.
    Thus every non-empty coverage cell contributes its best fine candidate before
    any cell contributes its second-best candidate. No cross-cell structural score
    calibration or coverage/structure weight is used.
    """
    if frame is None or frame.empty:
        raise ValueError("candidate frame must contain at least one row")
    forbidden = _forbidden_outcome_columns(frame.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in scale-separated ranking: {forbidden}")

    required = {coverage_cell_col, coverage_rank_col, structural_support_col, candidate_id_col}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing required columns: {missing}")

    work = frame.copy().reset_index(drop=True)
    ids = work[candidate_id_col]
    if ids.isna().any() or ids.astype(str).duplicated().any():
        raise ValueError("candidate IDs must be complete and unique")
    if work[coverage_cell_col].isna().any() or work[coverage_cell_col].astype(str).eq("").any():
        raise ValueError("coverage cell IDs must be complete and non-empty")

    support = pd.to_numeric(work[structural_support_col], errors="coerce").to_numpy(float)
    if not np.isfinite(support).all():
        raise ValueError("structural support must be complete and finite")
    if ((support < 0.0) | (support > 1.0)).any():
        raise ValueError("structural support must lie in [0, 1]")
    work["_structural_support_numeric"] = support

    ranks = pd.to_numeric(work[coverage_rank_col], errors="coerce").to_numpy(float)
    if not np.isfinite(ranks).all() or not np.allclose(ranks, np.rint(ranks)) or (ranks < 1).any():
        raise ValueError("coverage ranks must be complete positive integers")
    work["_coverage_rank_numeric"] = np.rint(ranks).astype(np.int64)

    cell_rank_counts = work.groupby(coverage_cell_col, sort=False)["_coverage_rank_numeric"].nunique()
    if (cell_rank_counts != 1).any():
        raise ValueError("every coverage cell must have exactly one coverage rank")
    cell_ranks = work.groupby(coverage_cell_col, sort=False)["_coverage_rank_numeric"].first()
    if cell_ranks.duplicated().any():
        raise ValueError("coverage ranks must be unique across coverage cells")
    expected = list(range(1, len(cell_ranks) + 1))
    if sorted(int(value) for value in cell_ranks.tolist()) != expected:
        raise ValueError("coverage ranks must form a complete 1..N ordering")

    work["_stable_key"] = [_stable_key(value) for value in work[candidate_id_col]]
    work = work.sort_values(
        [coverage_cell_col, "_structural_support_numeric", "_stable_key"],
        ascending=[True, False, True],
        kind="mergesort",
    )
    work["within_cell_structure_rank"] = (
        work.groupby(coverage_cell_col, sort=False).cumcount() + 1
    ).astype(np.int64)

    ordered = work.sort_values(
        ["within_cell_structure_rank", "_coverage_rank_numeric", "_stable_key"],
        ascending=[True, True, True],
        kind="mergesort",
    ).drop(columns=["_structural_support_numeric", "_coverage_rank_numeric", "_stable_key"]).reset_index(drop=True)
    ordered["decision_method"] = METHOD_ID
    ordered["decision_rank"] = range(1, len(ordered) + 1)

    audit = CoverageThenStructureAudit(
        method=METHOD_ID,
        candidate_count=int(len(ordered)),
        coverage_cell_count=int(len(cell_ranks)),
        maximum_within_cell_depth=int(ordered["within_cell_structure_rank"].max()),
        coverage_rank_column=str(coverage_rank_col),
        structural_support_column=str(structural_support_col),
        candidate_id_column=str(candidate_id_col),
        ordering_rule="within_cell_structure_rank ASC -> coverage_rank ASC -> stable_candidate_hash ASC",
    )
    return ordered, audit
