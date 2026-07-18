"""Equal-budget validation helpers for gap-separated survey patches."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .gap_patches import haversine_distance_m, patch_recovery_table, summarize_gap_patches


def select_gap_patches_under_member_budget(
    patch_members: pd.DataFrame,
    member_budget: int,
    *,
    allowed_classes: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Select whole patches greedily without exceeding a member-count budget.

    The score-per-member rule prevents large patches from winning merely because
    they contain more candidate points. Whole patches are retained so evaluation
    uses operational objects rather than a disguised point-level Top-k.
    """
    if patch_members is None or patch_members.empty or member_budget <= 0:
        return pd.DataFrame()
    work = patch_members.copy()
    if allowed_classes is not None:
        allowed = {str(value) for value in allowed_classes}
        work = work[work["gap_patch_class"].astype(str).isin(allowed)].copy()
    if work.empty:
        return work
    summary = summarize_gap_patches(work)
    summary["selection_value_per_member"] = (
        pd.to_numeric(summary["gap_patch_score"], errors="coerce").fillna(0.0)
        / pd.to_numeric(summary["gap_patch_member_count"], errors="coerce").clip(lower=1)
    )
    summary = summary.sort_values(
        ["selection_value_per_member", "gap_patch_score", "gap_patch_id"],
        ascending=[False, False, True],
    )
    selected: list[str] = []
    used = 0
    for row in summary.itertuples(index=False):
        cost = int(row.gap_patch_member_count)
        if used + cost > int(member_budget):
            continue
        selected.append(str(row.gap_patch_id))
        used += cost
    out = work[work["gap_patch_id"].astype(str).isin(selected)].copy()
    rank = {patch_id: index + 1 for index, patch_id in enumerate(selected)}
    out["gap_patch_selection_rank"] = out["gap_patch_id"].astype(str).map(rank).astype(int)
    out["gap_patch_member_budget"] = int(member_budget)
    out["gap_patch_members_used"] = int(used)
    return out.sort_values(["gap_patch_selection_rank", "gap_patch_id"]).reset_index(drop=True)


def cluster_patch_recovery_table(
    selected_members: pd.DataFrame,
    held_out_occurrences: pd.DataFrame,
    *,
    cluster_col: str = "cluster_id",
    radii_km: Iterable[float] = (1.0, 2.0, 5.0, 10.0),
) -> pd.DataFrame:
    """Return one recovery row per held-out population cluster."""
    if held_out_occurrences is None or held_out_occurrences.empty:
        return pd.DataFrame()
    held = held_out_occurrences.copy().reset_index(drop=True)
    if cluster_col not in held.columns:
        held[cluster_col] = np.arange(len(held), dtype=int)
    point_table = patch_recovery_table(selected_members, held, radii_km=radii_km)
    if point_table.empty:
        return point_table
    point_table[cluster_col] = held[cluster_col].to_numpy()
    recovered_cols = [column for column in point_table.columns if column.startswith("recovered_within_")]
    rows: list[dict[str, object]] = []
    for cluster_id, group in point_table.groupby(cluster_col, sort=True):
        nearest_row = group.loc[group["nearest_patch_distance_m"].idxmin()]
        row: dict[str, object] = {
            cluster_col: cluster_id,
            "nearest_patch_id": nearest_row["nearest_patch_id"],
            "nearest_patch_class": nearest_row["nearest_patch_class"],
            "nearest_patch_distance_m": float(nearest_row["nearest_patch_distance_m"]),
            "held_out_point_count": int(len(group)),
        }
        for column in recovered_cols:
            row[column] = bool(group[column].any())
        rows.append(row)
    return pd.DataFrame(rows)


def equal_member_budget_baselines(
    candidates: pd.DataFrame,
    known_occurrences: pd.DataFrame,
    held_out_occurrences: pd.DataFrame,
    selected_gap_members: pd.DataFrame,
    *,
    support_col: str = "integrated_support_score",
    cluster_col: str = "cluster_id",
    radii_km: Iterable[float] = (1.0, 2.0, 5.0, 10.0),
    random_draws: int = 100,
    random_state: int = 0,
) -> pd.DataFrame:
    """Compare gap patches with support, nearest-anchor, and random baselines."""
    if selected_gap_members is None or selected_gap_members.empty:
        return pd.DataFrame()
    pool = candidates.dropna(subset=["latitude", "longitude"]).copy().reset_index(drop=True)
    budget = min(len(pool), len(selected_gap_members))
    if budget <= 0:
        return pd.DataFrame()
    pool[support_col] = pd.to_numeric(pool[support_col], errors="coerce").fillna(0.0)
    known = known_occurrences.dropna(subset=["latitude", "longitude"]).copy()
    if known.empty:
        pool["nearest_known_m"] = np.inf
    else:
        known_lats = known["latitude"].to_numpy(float)
        known_lons = known["longitude"].to_numpy(float)
        pool["nearest_known_m"] = [
            float(np.min(haversine_distance_m(row.latitude, row.longitude, known_lats, known_lons)))
            for row in pool[["latitude", "longitude"]].itertuples(index=False)
        ]

    selections: list[tuple[str, int, pd.DataFrame]] = [
        ("gap_patch", 0, selected_gap_members),
        ("support_topk", 0, pool.nlargest(budget, support_col)),
        ("nearest_known", 0, pool.nsmallest(budget, "nearest_known_m")),
    ]
    rng = np.random.default_rng(random_state)
    for draw in range(max(1, int(random_draws))):
        positions = rng.choice(len(pool), size=budget, replace=False)
        selections.append(("random", draw, pool.iloc[positions]))

    rows: list[dict[str, object]] = []
    for method, draw, selection in selections:
        recovery = cluster_patch_recovery_table(
            selection, held_out_occurrences, cluster_col=cluster_col, radii_km=radii_km
        )
        row: dict[str, object] = {
            "method": method,
            "draw": int(draw),
            "member_budget": int(budget),
            "held_out_cluster_count": int(len(recovery)),
        }
        for column in [c for c in recovery.columns if c.startswith("recovered_within_")]:
            row[column.replace("recovered_", "recall_")] = float(recovery[column].mean())
        row["median_nearest_patch_distance_m"] = (
            float(recovery["nearest_patch_distance_m"].median()) if not recovery.empty else np.nan
        )
        rows.append(row)
    return pd.DataFrame(rows)
