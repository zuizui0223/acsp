"""Safe policy router between frozen ACSP v1 and frozen Practical Rescue v2.

The router never invents a third site-selection policy.  It computes both
already-frozen Top-5 decisions from training-only candidate attributes and uses
one transparent Ridge model to decide whether Rescue-v2 is predicted to improve
10-km held-out recovery over frozen v1 by at least the predeclared practical
margin.  Otherwise it falls back to frozen v1.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .practical_rescue import (
    _haversine_matrix_km,
    normalize_rescue_candidate_type,
    prepare_rescue_candidates,
)
from .validated_core import ValidatedCorePolicy, select_validated_core


ROUTER_PROTOCOL_ID = "acsp-practical-rescue-vnext2-safe-policy-router-development-v1"
ROUTER_PROTOCOL_FINGERPRINT = "988243d9acbb20b16fcf7ec307db8c3a5325c3abd7ba71835da5e9911bc0cad6"
ROUTER_NUMERIC_FEATURES: tuple[str, ...] = (
    "candidate_pool",
    "local_mean",
    "local_sd",
    "local_q10",
    "local_q50",
    "local_q90",
    "local_max",
    "local_zero_fraction",
    "coast_median_km",
    "coast_near1_fraction",
    "coast_near5_fraction",
    "overlap_n",
    "jaccard",
    "rescue_only_nearest_v1_mean_km",
    "candidate_habitat_fraction",
    "candidate_survey_gap_fraction",
    "candidate_environmental_fraction",
    "pool_domain_terrestrial_fraction",
    "pool_domain_inland_aquatic_fraction",
    "pool_domain_coastal_fraction",
    "pool_domain_marine_fraction",
    "v1_local_mean",
    "v1_local_min",
    "v1_local_max",
    "v1_geo_pair_mean_km",
    "v1_geo_pair_min_km",
    "v1_geo_pair_max_km",
    "v1_coast_mean_km",
    "v1_coast_min_km",
    "v1_coast_max_km",
    "v1_domain_terrestrial_fraction",
    "v1_domain_inland_aquatic_fraction",
    "v1_domain_coastal_fraction",
    "v1_domain_marine_fraction",
    "rescue_local_mean",
    "rescue_local_min",
    "rescue_local_max",
    "rescue_geo_pair_mean_km",
    "rescue_geo_pair_min_km",
    "rescue_geo_pair_max_km",
    "rescue_coast_mean_km",
    "rescue_coast_min_km",
    "rescue_coast_max_km",
    "rescue_domain_terrestrial_fraction",
    "rescue_domain_inland_aquatic_fraction",
    "rescue_domain_coastal_fraction",
    "rescue_domain_marine_fraction",
    "delta_local_mean",
    "delta_local_min",
    "delta_local_max",
    "delta_geo_pair_mean_km",
    "delta_geo_pair_min_km",
    "delta_geo_pair_max_km",
    "delta_coast_mean_km",
    "delta_coast_min_km",
    "delta_coast_max_km",
    "delta_domain_terrestrial_fraction",
    "delta_domain_inland_aquatic_fraction",
    "delta_domain_coastal_fraction",
    "delta_domain_marine_fraction",
)
ROUTER_CATEGORICAL_FEATURES: tuple[str, ...] = ("taxon_group", "surface_domain")
SURFACE_DOMAINS: tuple[str, ...] = ("terrestrial", "inland_aquatic", "coastal", "marine")


@dataclass(frozen=True)
class SafeRescueRouterPolicy:
    alpha: float = 10.0
    decision_threshold_absolute_recall: float = 0.015
    protocol_id: str = ROUTER_PROTOCOL_ID
    protocol_fingerprint: str = ROUTER_PROTOCOL_FINGERPRINT

    def __post_init__(self) -> None:
        if self.alpha != 10.0:
            raise ValueError("vNext2 router alpha is frozen to 10")
        if self.decision_threshold_absolute_recall != 0.015:
            raise ValueError("vNext2 router threshold is frozen to 0.015")


def _stable_ids(frame: pd.DataFrame) -> pd.Series:
    for column in ("candidate_id", "site_id"):
        if column in frame.columns:
            values = frame[column].astype(str)
            if values.duplicated().any():
                raise ValueError(f"{column} must be unique within one candidate frame")
            return values
    raise ValueError("router candidate frame requires candidate_id or site_id")


def frozen_v1_ids(candidates: pd.DataFrame, taxon_group: str) -> list[str]:
    """Return the exact frozen-v1 order without reading any held-out outcome."""
    work = prepare_rescue_candidates(candidates)
    if work.empty:
        return []
    selected = select_validated_core(
        work,
        ValidatedCorePolicy.for_taxon_group(str(taxon_group)),
    )
    return _stable_ids(selected).tolist()


def _indices_for_ids(work: pd.DataFrame, ids: Sequence[str], label: str) -> list[int]:
    stable = _stable_ids(work).reset_index(drop=True)
    mapping = {candidate_id: index for index, candidate_id in enumerate(stable.tolist())}
    missing = [str(candidate_id) for candidate_id in ids if str(candidate_id) not in mapping]
    if missing:
        raise ValueError(f"{label} contains IDs outside the eligible candidate pool: {missing[:5]}")
    out = [mapping[str(candidate_id)] for candidate_id in ids]
    if len(out) != len(set(out)):
        raise ValueError(f"{label} contains duplicate candidate IDs")
    return out


def _domain_series(frame: pd.DataFrame) -> pd.Series:
    values = frame.get("surface_domain", pd.Series("unknown", index=frame.index))
    return values.fillna("unknown").astype(str).str.strip().str.lower().replace("", "unknown")


def _surface_domain_mode(work: pd.DataFrame) -> str:
    values = _domain_series(work)
    mode = values.mode(dropna=True)
    return str(mode.iloc[0]) if not mode.empty else "unknown"


def _set_stats(
    work: pd.DataFrame,
    indices: Sequence[int],
    local: np.ndarray,
    geographic: np.ndarray,
    prefix: str,
) -> dict[str, float]:
    idx = list(map(int, indices))
    if not idx:
        raise ValueError(f"{prefix} selection cannot be empty")
    local_values = local[idx]
    sub = geographic[np.ix_(idx, idx)]
    pairwise = sub[np.triu_indices(len(idx), 1)] if len(idx) > 1 else np.array([0.0])
    selected = work.iloc[idx]
    coast = pd.to_numeric(
        selected.get("distance_to_coast_m", pd.Series(np.nan, index=selected.index)),
        errors="coerce",
    )
    domains = _domain_series(selected)
    result = {
        f"{prefix}_local_mean": float(local_values.mean()),
        f"{prefix}_local_min": float(local_values.min()),
        f"{prefix}_local_max": float(local_values.max()),
        f"{prefix}_geo_pair_mean_km": float(pairwise.mean()),
        f"{prefix}_geo_pair_min_km": float(pairwise.min()),
        f"{prefix}_geo_pair_max_km": float(pairwise.max()),
        f"{prefix}_coast_mean_km": float(coast.mean() / 1000.0) if coast.notna().any() else np.nan,
        f"{prefix}_coast_min_km": float(coast.min() / 1000.0) if coast.notna().any() else np.nan,
        f"{prefix}_coast_max_km": float(coast.max() / 1000.0) if coast.notna().any() else np.nan,
    }
    for domain in SURFACE_DOMAINS:
        result[f"{prefix}_domain_{domain}_fraction"] = float(domains.eq(domain).mean())
    return result


def build_router_features(
    candidates: pd.DataFrame,
    taxon_group: str,
    v1_selected_ids: Sequence[str],
    rescue_selected_ids: Sequence[str],
) -> pd.DataFrame:
    """Build one outcome-free row describing the pool and policy disagreement."""
    work = prepare_rescue_candidates(candidates)
    if work.empty:
        raise ValueError("router requires a non-empty eligible candidate pool")
    group = str(taxon_group).strip().lower()
    if group not in {"plant", "animal"}:
        raise ValueError("taxon_group must be plant or animal")
    if len(v1_selected_ids) != min(5, len(work)) or len(rescue_selected_ids) != min(5, len(work)):
        raise ValueError("router selections must each use the full frozen Top-5 budget when available")

    v1_indices = _indices_for_ids(work, v1_selected_ids, "frozen-v1 selection")
    rescue_indices = _indices_for_ids(work, rescue_selected_ids, "Rescue-v2 selection")
    latitude = pd.to_numeric(work["latitude"], errors="coerce").to_numpy(float)
    longitude = pd.to_numeric(work["longitude"], errors="coerce").to_numpy(float)
    if not np.isfinite(latitude).all() or not np.isfinite(longitude).all():
        raise ValueError("router candidate coordinates must be finite")
    geographic = _haversine_matrix_km(latitude, longitude)
    local = pd.to_numeric(
        work.get("component_local_habitat_score", pd.Series(np.nan, index=work.index)),
        errors="coerce",
    ).fillna(0.0).clip(0.0, 1.0).to_numpy(float)
    coast = pd.to_numeric(
        work.get("distance_to_coast_m", pd.Series(np.nan, index=work.index)),
        errors="coerce",
    )
    finite_coast = coast[np.isfinite(coast)]
    candidate_types = work.get("candidate_type", pd.Series("", index=work.index)).map(
        normalize_rescue_candidate_type
    )
    domains = _domain_series(work)

    v1_set = {str(value) for value in v1_selected_ids}
    rescue_set = {str(value) for value in rescue_selected_ids}
    intersection = len(v1_set & rescue_set)
    union = len(v1_set | rescue_set)
    rescue_only = [
        index
        for index, candidate_id in enumerate(_stable_ids(work).astype(str))
        if candidate_id in (rescue_set - v1_set)
    ]
    nearest_v1 = (
        float(np.mean([np.min(geographic[index, v1_indices]) for index in rescue_only]))
        if rescue_only
        else 0.0
    )

    row: dict[str, object] = {
        "candidate_pool": float(len(work)),
        "local_mean": float(local.mean()),
        "local_sd": float(local.std()),
        "local_q10": float(np.quantile(local, 0.10)),
        "local_q50": float(np.quantile(local, 0.50)),
        "local_q90": float(np.quantile(local, 0.90)),
        "local_max": float(local.max()),
        "local_zero_fraction": float((local <= 1e-12).mean()),
        "coast_median_km": float(finite_coast.median() / 1000.0) if not finite_coast.empty else np.nan,
        "coast_near1_fraction": float((finite_coast <= 1000.0).mean()) if not finite_coast.empty else np.nan,
        "coast_near5_fraction": float((finite_coast <= 5000.0).mean()) if not finite_coast.empty else np.nan,
        "overlap_n": float(intersection),
        "jaccard": float(intersection / union) if union else 1.0,
        "rescue_only_nearest_v1_mean_km": nearest_v1,
        "candidate_habitat_fraction": float(candidate_types.eq("habitat").mean()),
        "candidate_survey_gap_fraction": float(candidate_types.eq("survey_gap").mean()),
        "candidate_environmental_fraction": float(candidate_types.eq("environmental").mean()),
        "taxon_group": group,
        "surface_domain": _surface_domain_mode(work),
    }
    for domain in SURFACE_DOMAINS:
        row[f"pool_domain_{domain}_fraction"] = float(domains.eq(domain).mean())

    row.update(_set_stats(work, v1_indices, local, geographic, "v1"))
    row.update(_set_stats(work, rescue_indices, local, geographic, "rescue"))
    for suffix in (
        "local_mean",
        "local_min",
        "local_max",
        "geo_pair_mean_km",
        "geo_pair_min_km",
        "geo_pair_max_km",
        "coast_mean_km",
        "coast_min_km",
        "coast_max_km",
        "domain_terrestrial_fraction",
        "domain_inland_aquatic_fraction",
        "domain_coastal_fraction",
        "domain_marine_fraction",
    ):
        row[f"delta_{suffix}"] = float(row[f"rescue_{suffix}"]) - float(row[f"v1_{suffix}"])

    frame = pd.DataFrame([row])
    missing = set(ROUTER_NUMERIC_FEATURES + ROUTER_CATEGORICAL_FEATURES) - set(frame.columns)
    if missing:
        raise AssertionError(f"router feature construction omitted: {sorted(missing)}")
    return frame


def make_router_estimator(policy: SafeRescueRouterPolicy | None = None) -> Pipeline:
    cfg = policy or SafeRescueRouterPolicy()
    preprocess = ColumnTransformer([
        (
            "numeric",
            Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ]),
            list(ROUTER_NUMERIC_FEATURES),
        ),
        (
            "categorical",
            OneHotEncoder(handle_unknown="ignore"),
            list(ROUTER_CATEGORICAL_FEATURES),
        ),
    ])
    return Pipeline([
        ("preprocess", preprocess),
        ("model", Ridge(alpha=cfg.alpha)),
    ])


def choose_router_policy(
    predicted_rescue_minus_v1: float,
    policy: SafeRescueRouterPolicy | None = None,
) -> str:
    cfg = policy or SafeRescueRouterPolicy()
    value = float(predicted_rescue_minus_v1)
    if not math.isfinite(value):
        return "frozen_v1"
    return "frozen_rescue_v2" if value >= cfg.decision_threshold_absolute_recall else "frozen_v1"


def select_routed_candidates(
    candidates: pd.DataFrame,
    v1_selected_ids: Sequence[str],
    rescue_selected_ids: Sequence[str],
    predicted_rescue_minus_v1: float,
    policy: SafeRescueRouterPolicy | None = None,
) -> pd.DataFrame:
    """Return exactly one of the two frozen policy decisions, unchanged."""
    cfg = policy or SafeRescueRouterPolicy()
    work = prepare_rescue_candidates(candidates)
    chosen_policy = choose_router_policy(predicted_rescue_minus_v1, cfg)
    chosen_ids = rescue_selected_ids if chosen_policy == "frozen_rescue_v2" else v1_selected_ids
    indices = _indices_for_ids(work, chosen_ids, chosen_policy)
    out = work.iloc[indices].copy().reset_index(drop=True)
    out["router_selection_rank"] = range(1, len(out) + 1)
    out["router_chosen_policy"] = chosen_policy
    out["router_predicted_rescue_minus_v1"] = float(predicted_rescue_minus_v1)
    out["router_threshold_absolute_recall"] = cfg.decision_threshold_absolute_recall
    out["router_protocol"] = cfg.protocol_id
    out["router_protocol_fingerprint"] = cfg.protocol_fingerprint
    return out


def router_training_weights(pair_ids: pd.Series) -> np.ndarray:
    """Give every taxon-region pair equal total weight across complete folds."""
    ids = pd.to_numeric(pair_ids, errors="raise").astype(int)
    counts = ids.value_counts()
    return ids.map(lambda value: 1.0 / float(counts.loc[value])).to_numpy(float)


def export_linear_router_artifact(
    estimator: Pipeline,
    *,
    training_rows: int,
    development_pairs: int,
    source_fingerprint: str,
    policy: SafeRescueRouterPolicy | None = None,
) -> dict[str, object]:
    """Export all fitted linear/preprocessing parameters as auditable JSON data."""
    cfg = policy or SafeRescueRouterPolicy()
    preprocess = estimator.named_steps["preprocess"]
    numeric_pipe = preprocess.named_transformers_["numeric"]
    imputer = numeric_pipe.named_steps["impute"]
    scaler = numeric_pipe.named_steps["scale"]
    encoder = preprocess.named_transformers_["categorical"]
    model = estimator.named_steps["model"]
    categories = {
        feature: [str(value) for value in values.tolist()]
        for feature, values in zip(ROUTER_CATEGORICAL_FEATURES, encoder.categories_)
    }
    return {
        "artifact_id": "acsp-practical-rescue-vnext2-linear-router-v1",
        "status": "fitted_on_reclassified_192_pair_development_set",
        "protocol_id": cfg.protocol_id,
        "protocol_fingerprint": cfg.protocol_fingerprint,
        "source_development_protocol_fingerprint": str(source_fingerprint),
        "development_pairs": int(development_pairs),
        "training_rows": int(training_rows),
        "numeric_features": list(ROUTER_NUMERIC_FEATURES),
        "categorical_features": list(ROUTER_CATEGORICAL_FEATURES),
        "numeric_imputer_median": [float(value) for value in imputer.statistics_.tolist()],
        "numeric_scaler_mean": [float(value) for value in scaler.mean_.tolist()],
        "numeric_scaler_scale": [float(value) for value in scaler.scale_.tolist()],
        "categorical_levels": categories,
        "ridge_alpha": float(cfg.alpha),
        "ridge_intercept": float(np.asarray(model.intercept_).reshape(-1)[0]),
        "ridge_coefficients": [float(value) for value in np.asarray(model.coef_).reshape(-1).tolist()],
        "decision_threshold_absolute_recall": float(cfg.decision_threshold_absolute_recall),
        "training_weight": "equal total weight per taxon-region pair across complete folds",
        "heldout_outcomes_available_at_future_router_inference": False,
        "scientific_name_used_as_feature": False,
        "absolute_region_identity_used_as_feature": False,
    }


def predict_linear_router_artifact(
    features: pd.DataFrame,
    artifact: Mapping[str, object],
) -> np.ndarray:
    """Reproduce Ridge predictions from the exported JSON without sklearn fitting state."""
    if str(artifact.get("protocol_fingerprint")) != ROUTER_PROTOCOL_FINGERPRINT:
        raise ValueError("router artifact protocol fingerprint mismatch")
    if list(artifact.get("numeric_features", [])) != list(ROUTER_NUMERIC_FEATURES):
        raise ValueError("router artifact numeric feature order mismatch")
    if list(artifact.get("categorical_features", [])) != list(ROUTER_CATEGORICAL_FEATURES):
        raise ValueError("router artifact categorical feature order mismatch")
    numeric = features[list(ROUTER_NUMERIC_FEATURES)].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    medians = np.asarray(artifact["numeric_imputer_median"], dtype=float)
    means = np.asarray(artifact["numeric_scaler_mean"], dtype=float)
    scales = np.asarray(artifact["numeric_scaler_scale"], dtype=float)
    if numeric.shape[1] != len(medians):
        raise ValueError("router artifact numeric width mismatch")
    missing = ~np.isfinite(numeric)
    if missing.any():
        numeric[missing] = np.take(medians, np.where(missing)[1])
    numeric = (numeric - means) / scales

    encoded_parts: list[np.ndarray] = [numeric]
    levels = artifact["categorical_levels"]
    for feature in ROUTER_CATEGORICAL_FEATURES:
        values = features[feature].fillna("").astype(str).to_numpy()
        categories = list(map(str, levels[feature]))
        matrix = np.zeros((len(features), len(categories)), dtype=float)
        lookup = {category: index for index, category in enumerate(categories)}
        for row, value in enumerate(values):
            index = lookup.get(str(value))
            if index is not None:
                matrix[row, index] = 1.0
        encoded_parts.append(matrix)
    design = np.concatenate(encoded_parts, axis=1)
    coefficients = np.asarray(artifact["ridge_coefficients"], dtype=float)
    if design.shape[1] != len(coefficients):
        raise ValueError(
            f"router artifact coefficient width mismatch: design={design.shape[1]} coef={len(coefficients)}"
        )
    return design @ coefficients + float(artifact["ridge_intercept"])
