"""Development vNext: preserve four frozen-v1 anchors and learn only slot five.

This module is deliberately separate from the frozen Practical Rescue v2 and
publication-facing v1 policies.  The inspected 192-pair fresh-v2 cohort is now
development data.  vNext keeps 80% of the strong frozen-v1 decision unchanged
and permits exactly one learned replacement only when its predicted absolute
10-km recall advantage over the original fifth site reaches the predeclared
0.015 practical margin.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .practical_rescue import (
    RESCUE_CATEGORICAL_FEATURES,
    RESCUE_NUMERIC_FEATURES,
    _haversine_matrix_km,
    build_rescue_features,
    prepare_rescue_candidates,
)
from .validated_core import ValidatedCorePolicy, select_validated_core


VNEXT_PROTOCOL_ID = "acsp-practical-rescue-vnext-v1-anchored-fifth-slot-development"
VNEXT_PROTOCOL_FINGERPRINT = "850cd2a6d962308dc6125c1759ebc03f64ac5a39489cb70f19da5a502b0cf686"
VNEXT_EXTRA_NUMERIC_FEATURES: tuple[str, ...] = (
    "anchor_min_km",
    "anchor_mean_km",
    "baseline_fifth_local_score",
    "delta_local_vs_baseline_fifth",
    "pool_distance_to_coast_median_km",
    "pool_near_coast_1km_fraction",
    "v1_selection_rank",
)
VNEXT_NUMERIC_FEATURES: tuple[str, ...] = (
    *RESCUE_NUMERIC_FEATURES,
    *VNEXT_EXTRA_NUMERIC_FEATURES,
)
VNEXT_CATEGORICAL_FEATURES: tuple[str, ...] = (
    *RESCUE_CATEGORICAL_FEATURES,
    "surface_domain",
)


@dataclass(frozen=True)
class VNextAnchoredFifthPolicy:
    top_k: int = 5
    anchor_count: int = 4
    replacement_margin: float = 0.015
    protocol_id: str = VNEXT_PROTOCOL_ID
    protocol_fingerprint: str = VNEXT_PROTOCOL_FINGERPRINT

    def __post_init__(self) -> None:
        if self.top_k != 5:
            raise ValueError("vNext development is frozen to Top-5")
        if self.anchor_count != 4:
            raise ValueError("vNext development freezes exactly four v1 anchors")
        if self.replacement_margin != 0.015:
            raise ValueError("vNext development replacement margin is frozen to 0.015")


def _stable_ids(frame: pd.DataFrame) -> pd.Series:
    for column in ("candidate_id", "site_id"):
        if column in frame.columns:
            values = frame[column].astype(str)
            if values.duplicated().any():
                raise ValueError(f"{column} must be unique within one candidate frame")
            return values
    return pd.Series(
        [f"candidate-{index + 1:06d}" for index in range(len(frame))],
        index=frame.index,
        dtype=str,
    )


def frozen_v1_order(candidates: pd.DataFrame, taxon_group: str) -> list[str]:
    """Return the exact outcome-free frozen-v1 Top-5 order on the eligible pool."""
    work = prepare_rescue_candidates(candidates)
    if work.empty:
        return []
    selected = select_validated_core(
        work,
        ValidatedCorePolicy.for_taxon_group(str(taxon_group)),
    )
    return _stable_ids(selected).tolist()


def build_vnext_features(
    candidates: pd.DataFrame,
    taxon_group: str,
    policy: VNextAnchoredFifthPolicy | None = None,
) -> pd.DataFrame:
    """Build outcome-free candidate features relative to the first four v1 sites."""
    cfg = policy or VNextAnchoredFifthPolicy()
    work = prepare_rescue_candidates(candidates)
    base = build_rescue_features(work, taxon_group)
    if work.empty:
        for column in VNEXT_EXTRA_NUMERIC_FEATURES:
            base[column] = pd.Series(dtype=float)
        base["surface_domain"] = pd.Series(dtype=str)
        return base

    stable = _stable_ids(work).reset_index(drop=True)
    v1_ids = frozen_v1_order(work, taxon_group)
    id_to_index = {candidate_id: index for index, candidate_id in enumerate(stable.tolist())}
    anchors = v1_ids[: min(cfg.anchor_count, len(v1_ids))]
    anchor_indices = [id_to_index[candidate_id] for candidate_id in anchors]

    latitude = pd.to_numeric(work["latitude"], errors="coerce").to_numpy(float)
    longitude = pd.to_numeric(work["longitude"], errors="coerce").to_numpy(float)
    distance = _haversine_matrix_km(latitude, longitude)
    if anchor_indices:
        anchor_distance = distance[:, anchor_indices]
        base["anchor_min_km"] = np.min(anchor_distance, axis=1)
        base["anchor_mean_km"] = np.mean(anchor_distance, axis=1)
    else:
        base["anchor_min_km"] = 0.0
        base["anchor_mean_km"] = 0.0

    local = pd.to_numeric(
        work.get("component_local_habitat_score", pd.Series(np.nan, index=work.index)),
        errors="coerce",
    ).fillna(0.0).clip(0.0, 1.0)
    baseline_fifth_id = v1_ids[4] if len(v1_ids) >= 5 else None
    baseline_fifth_local = (
        float(local.iloc[id_to_index[baseline_fifth_id]])
        if baseline_fifth_id is not None
        else float(local.min())
    )
    base["baseline_fifth_local_score"] = baseline_fifth_local
    base["delta_local_vs_baseline_fifth"] = local.to_numpy(float) - baseline_fifth_local

    coast = pd.to_numeric(
        work.get("distance_to_coast_m", pd.Series(np.nan, index=work.index)),
        errors="coerce",
    )
    finite_coast = coast[np.isfinite(coast)]
    base["pool_distance_to_coast_median_km"] = (
        float(finite_coast.median() / 1000.0) if not finite_coast.empty else np.nan
    )
    base["pool_near_coast_1km_fraction"] = (
        float((finite_coast <= 1000.0).mean()) if not finite_coast.empty else np.nan
    )

    rank_map = {candidate_id: rank for rank, candidate_id in enumerate(v1_ids, start=1)}
    base["v1_selection_rank"] = [
        float(rank_map.get(candidate_id, cfg.top_k + 1)) for candidate_id in stable
    ]
    surface = work.get("surface_domain", pd.Series("unknown", index=work.index))
    base["surface_domain"] = (
        surface.fillna("unknown").astype(str).str.strip().str.lower().replace("", "unknown").to_numpy()
    )
    base["_v1_anchor"] = stable.isin(anchors).to_numpy(bool)
    base["_v1_fifth"] = (
        stable.eq(baseline_fifth_id).to_numpy(bool)
        if baseline_fifth_id is not None
        else np.zeros(len(work), dtype=bool)
    )
    return base


def make_vnext_estimator() -> Pipeline:
    numeric = list(VNEXT_NUMERIC_FEATURES)
    categorical = list(VNEXT_CATEGORICAL_FEATURES)
    preprocess = ColumnTransformer([
        ("numeric", Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), numeric),
        ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
    ])
    return Pipeline([
        ("preprocess", preprocess),
        ("model", GradientBoostingRegressor(
            n_estimators=100,
            max_depth=2,
            min_samples_leaf=10,
            loss="huber",
            random_state=42,
        )),
    ])


def _attach_selection_metadata(
    selected: pd.DataFrame,
    roles: list[str],
    predictions: list[float],
    replaced: bool,
    cfg: VNextAnchoredFifthPolicy,
) -> pd.DataFrame:
    out = selected.copy().reset_index(drop=True)
    out["vnext_selection_rank"] = range(1, len(out) + 1)
    out["vnext_role"] = roles
    out["vnext_predicted_anchor4_marginal_recall"] = predictions
    out["vnext_replaced_frozen_v1_fifth"] = bool(replaced)
    out["vnext_policy"] = cfg.protocol_id
    out["vnext_protocol_fingerprint"] = cfg.protocol_fingerprint
    return out


def select_vnext_anchored_fifth(
    candidates: pd.DataFrame,
    taxon_group: str,
    estimator: object,
    policy: VNextAnchoredFifthPolicy | None = None,
) -> pd.DataFrame:
    """Preserve v1 sites 1-4 and conservatively learn only the fifth site."""
    cfg = policy or VNextAnchoredFifthPolicy()
    work = prepare_rescue_candidates(candidates)
    if work.empty:
        return _attach_selection_metadata(work, [], [], False, cfg)

    stable = _stable_ids(work).reset_index(drop=True)
    v1_ids = frozen_v1_order(work, taxon_group)
    id_to_index = {candidate_id: index for index, candidate_id in enumerate(stable.tolist())}
    v1_indices = [id_to_index[candidate_id] for candidate_id in v1_ids]
    v1_frame = work.iloc[v1_indices].copy().reset_index(drop=True)
    if len(v1_ids) < cfg.top_k or len(work) <= cfg.top_k:
        roles = ["frozen_v1_fallback"] * len(v1_frame)
        return _attach_selection_metadata(v1_frame, roles, [math.nan] * len(v1_frame), False, cfg)

    anchors = v1_ids[: cfg.anchor_count]
    baseline_fifth_id = v1_ids[4]
    features = build_vnext_features(work, taxon_group, cfg)
    candidate_mask = ~features["_v1_anchor"].astype(bool)
    scored = features.loc[candidate_mask].copy()
    columns = [*VNEXT_NUMERIC_FEATURES, *VNEXT_CATEGORICAL_FEATURES]
    predictions = np.asarray(estimator.predict(scored[columns]), dtype=float).reshape(-1)
    predictions = np.where(np.isfinite(predictions), predictions, -np.inf)
    scored["_prediction"] = predictions

    baseline_row = scored.loc[scored["_v1_fifth"].astype(bool)]
    if len(baseline_row) != 1:
        raise RuntimeError("vNext could not uniquely identify the frozen-v1 fifth candidate")
    baseline_prediction = float(baseline_row["_prediction"].iloc[0])

    work_local = pd.to_numeric(
        work.get("component_local_habitat_score", pd.Series(0.0, index=work.index)),
        errors="coerce",
    ).fillna(0.0).clip(0.0, 1.0)
    stable_to_local = dict(zip(stable.tolist(), work_local.to_numpy(float)))
    scored["_local"] = scored["_stable_id"].map(stable_to_local).astype(float)
    scored = scored.sort_values(
        ["_prediction", "_local", "_stable_id"],
        ascending=[False, False, True],
        kind="mergesort",
    )
    best = scored.iloc[0]
    best_id = str(best["_stable_id"])
    best_prediction = float(best["_prediction"])
    replaced = bool(
        best_id != baseline_fifth_id
        and best_prediction - baseline_prediction >= cfg.replacement_margin - 1e-12
    )
    chosen_fifth = best_id if replaced else baseline_fifth_id
    chosen_prediction = best_prediction if replaced else baseline_prediction

    selected_ids = [*anchors, chosen_fifth]
    selected = work.iloc[[id_to_index[candidate_id] for candidate_id in selected_ids]].copy()
    roles = ["frozen_v1_anchor"] * cfg.anchor_count + [
        "learned_residual_fifth" if replaced else "frozen_v1_fifth"
    ]
    return _attach_selection_metadata(
        selected,
        roles,
        [math.nan] * cfg.anchor_count + [chosen_prediction],
        replaced,
        cfg,
    )
