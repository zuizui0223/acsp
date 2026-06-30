"""Transparent candidate recommendation helpers."""

from __future__ import annotations

import pandas as pd


def recommend_candidates(
    candidates: pd.DataFrame,
    per_area: int = 3,
    default_total: int = 8,
    area_col: str = "survey_area_id",
    score_col: str = "priority_score",
    id_col: str = "site_id",
) -> pd.DataFrame:
    """Select top-ranked candidates, with an equal quota across multiple areas."""
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    required = {score_col, id_col}
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"Missing candidate columns: {', '.join(sorted(missing))}")
    ranked = candidates.sort_values([score_col, id_col], ascending=[False, True]).copy()
    if area_col in ranked.columns and ranked[area_col].nunique() > 1:
        selected = ranked.groupby(area_col, group_keys=False).head(int(per_area)).copy()
        selected = selected.sort_values([area_col, score_col], ascending=[True, False])
    else:
        selected = ranked.head(int(default_total)).copy()
    selected["recommendation_rank"] = range(1, len(selected) + 1)
    return selected.reset_index(drop=True)
