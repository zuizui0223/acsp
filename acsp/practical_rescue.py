"""Development policy for local-anchor plus cross-taxon rescue survey selection."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

EARTH_RADIUS_KM = 6_371.0088
PRACTICAL_RESCUE_PROTOCOL_ID = "acsp-practical-local-anchor-rescue-development-v1"
PRACTICAL_RESCUE_PROTOCOL_FINGERPRINT = "8f4f0a85ca636bf70b445ed1bb70b93a2df7de6a5b687b91d42c436b7e258c48"
KNOWN_CANDIDATE_PATTERN = "occurrence-supported|known-location|known anchor"
RESCUE_NUMERIC_FEATURES: tuple[str, ...] = (
    "local_score",
    "local_rank_pct",
    "geo_nn_km",
    "geo_avg_km",
    "dist_local1_km",
    "neighbor_local_mass_10km",
    "neighbor_count_10km",
    "candidate_pool",
    "pool_local_sd",
    "pool_local_q90",
    "integrated_support_score",
    "survey_gap_score",
    "environmental_novelty",
    "access_score",
    "evidence_agreement_score",
    "evidence_divergence_score",
    "distance_excluded_validation_score",
    "component_macro_model_score",
)
RESCUE_CATEGORICAL_FEATURES: tuple[str, ...] = ("taxon_group", "candidate_type")


@dataclass(frozen=True)
class LocalAnchorRescuePolicy:
    top_k: int = 5
    local_anchor_count: int = 1
    diversity_scale_km: float = 10.0
    score_col: str = "component_local_habitat_score"
    protocol_id: str = PRACTICAL_RESCUE_PROTOCOL_ID
    protocol_fingerprint: str = PRACTICAL_RESCUE_PROTOCOL_FINGERPRINT

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError("top_k must be at least one")
        if self.local_anchor_count != 1:
            raise ValueError("development policy freezes exactly one local anchor")
        if self.local_anchor_count > self.top_k:
            raise ValueError("local_anchor_count cannot exceed top_k")
        if self.diversity_scale_km <= 0:
            raise ValueError("diversity_scale_km must be positive")


def _stable_candidate_id(frame: pd.DataFrame) -> pd.Series:
    for column in ("candidate_id", "site_id"):
        if column in frame.columns:
            return frame[column].astype(str)
    return pd.Series(
        [f"candidate-{index + 1:06d}" for index in range(len(frame))],
        index=frame.index,
        dtype=str,
    )


def _haversine_matrix_km(latitude: np.ndarray, longitude: np.ndarray) -> np.ndarray:
    lat = np.radians(np.asarray(latitude, dtype=float))
    lon = np.radians(np.asarray(longitude, dtype=float))
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def normalize_rescue_candidate_type(value: object) -> str:
    text = str(value or "").strip().lower()
    if "habitat" in text or "analogue" in text:
        return "habitat"
    if "survey-gap" in text or "under-surveyed" in text:
        return "survey_gap"
    if "environmental" in text:
        return "environmental"
    return "other"


def prepare_rescue_candidates(
    candidates: pd.DataFrame,
    *,
    candidate_type_col: str = "candidate_type",
) -> pd.DataFrame:
    if candidates is None:
        raise ValueError("candidates must be a DataFrame")
    work = candidates.copy().reset_index(drop=True)
    if candidate_type_col in work.columns:
        known = work[candidate_type_col].astype(str).str.contains(
            KNOWN_CANDIDATE_PATTERN, case=False, na=False
        )
        work = work.loc[~known].reset_index(drop=True)
    return work


def local_order(candidates: pd.DataFrame, score_col: str = "component_local_habitat_score") -> list[int]:
    if candidates.empty:
        return []
    if score_col not in candidates.columns:
        raise ValueError(f"candidates is missing: {score_col}")
    values = pd.to_numeric(candidates[score_col], errors="coerce").fillna(float("-inf"))
    stable = _stable_candidate_id(candidates)
    order = pd.DataFrame({
        "index": np.arange(len(candidates), dtype=int),
        "score": values.to_numpy(float),
        "stable_id": stable.to_numpy(str),
    }).sort_values(
        ["score", "stable_id", "index"],
        ascending=[False, True, True],
        kind="mergesort",
    )
    return order["index"].astype(int).tolist()


def build_rescue_features(
    candidates: pd.DataFrame,
    taxon_group: str,
    policy: LocalAnchorRescuePolicy | None = None,
) -> pd.DataFrame:
    cfg = policy or LocalAnchorRescuePolicy()
    work = prepare_rescue_candidates(candidates)
    if work.empty:
        return pd.DataFrame(columns=[*RESCUE_NUMERIC_FEATURES, *RESCUE_CATEGORICAL_FEATURES])
    required = {"latitude", "longitude", cfg.score_col}
    missing = required - set(work.columns)
    if missing:
        raise ValueError(f"candidates is missing: {', '.join(sorted(missing))}")
    group = str(taxon_group).strip().lower()
    if group not in {"plant", "animal"}:
        raise ValueError("taxon_group must be plant or animal")

    latitude = pd.to_numeric(work["latitude"], errors="coerce").to_numpy(float)
    longitude = pd.to_numeric(work["longitude"], errors="coerce").to_numpy(float)
    if not np.isfinite(latitude).all() or not np.isfinite(longitude).all():
        raise ValueError("candidate coordinates must be finite")
    raw_local = pd.to_numeric(work[cfg.score_col], errors="coerce")
    local = raw_local.fillna(0.0).clip(0.0, 1.0).to_numpy(float)
    order = local_order(work, cfg.score_col)
    ranks = np.empty(len(work), dtype=float)
    ranks[np.asarray(order, dtype=int)] = np.arange(1, len(work) + 1, dtype=float)

    geographic = _haversine_matrix_km(latitude, longitude)
    if len(work) > 1:
        nearest = geographic.copy()
        np.fill_diagonal(nearest, np.inf)
        geo_nn = np.min(nearest, axis=1)
        geo_avg = np.sum(geographic, axis=1) / (len(work) - 1)
    else:
        geo_nn = np.zeros(1, dtype=float)
        geo_avg = np.zeros(1, dtype=float)
    local1 = int(order[0])

    features = pd.DataFrame(index=work.index)
    features["local_score"] = local
    features["local_rank_pct"] = ranks / len(work)
    features["geo_nn_km"] = geo_nn
    features["geo_avg_km"] = geo_avg
    features["dist_local1_km"] = geographic[:, local1]
    within_10 = geographic <= (float(cfg.diversity_scale_km) + 1e-9)
    features["neighbor_local_mass_10km"] = within_10 @ local
    features["neighbor_count_10km"] = within_10.sum(axis=1).astype(float)
    features["candidate_pool"] = float(len(work))
    features["pool_local_sd"] = float(np.std(local))
    features["pool_local_q90"] = float(np.quantile(local, 0.90))
    for column in (
        "integrated_support_score",
        "survey_gap_score",
        "environmental_novelty",
        "access_score",
        "evidence_agreement_score",
        "evidence_divergence_score",
        "distance_excluded_validation_score",
        "component_macro_model_score",
    ):
        source = work[column] if column in work.columns else pd.Series(np.nan, index=work.index)
        features[column] = pd.to_numeric(source, errors="coerce")
    features["taxon_group"] = group
    candidate_type = work.get("candidate_type", pd.Series("", index=work.index))
    features["candidate_type"] = candidate_type.map(normalize_rescue_candidate_type)
    features["_source_index"] = np.arange(len(work), dtype=int)
    features["_stable_id"] = _stable_candidate_id(work).to_numpy(str)
    return features


def make_rescue_estimator() -> Pipeline:
    numeric = list(RESCUE_NUMERIC_FEATURES)
    categorical = list(RESCUE_CATEGORICAL_FEATURES)
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


def select_local_anchor_rescue(
    candidates: pd.DataFrame,
    predicted_rescue_gain: np.ndarray | pd.Series,
    policy: LocalAnchorRescuePolicy | None = None,
) -> pd.DataFrame:
    cfg = policy or LocalAnchorRescuePolicy()
    work = prepare_rescue_candidates(candidates)
    if work.empty:
        return work.assign(
            rescue_selection_rank=pd.Series(dtype="Int64"),
            rescue_role=pd.Series(dtype=str),
            rescue_prediction=pd.Series(dtype=float),
            rescue_diversity_multiplier=pd.Series(dtype=float),
            rescue_selection_score=pd.Series(dtype=float),
        )
    predictions = np.asarray(predicted_rescue_gain, dtype=float).reshape(-1)
    if len(predictions) != len(work):
        raise ValueError("predicted_rescue_gain length must match eligible candidate rows")
    predictions = np.where(np.isfinite(predictions), np.maximum(predictions, 0.0), 0.0)
    latitude = pd.to_numeric(work["latitude"], errors="coerce").to_numpy(float)
    longitude = pd.to_numeric(work["longitude"], errors="coerce").to_numpy(float)
    if not np.isfinite(latitude).all() or not np.isfinite(longitude).all():
        raise ValueError("candidate coordinates must be finite")
    distance = _haversine_matrix_km(latitude, longitude)
    order = local_order(work, cfg.score_col)
    stable = _stable_candidate_id(work).to_numpy(str)
    local = pd.to_numeric(work[cfg.score_col], errors="coerce").fillna(0.0).clip(0.0, 1.0).to_numpy(float)

    selected = [int(order[0])]
    roles = ["local_anchor"]
    recorded_prediction = [float(predictions[selected[0]])]
    multipliers = [1.0]
    selection_scores = [float(local[selected[0]])]
    while len(selected) < min(int(cfg.top_k), len(work)):
        remaining = [index for index in range(len(work)) if index not in selected]
        if not remaining:
            break
        candidates_with_scores: list[tuple[float, float, float, str, int, float]] = []
        for index in remaining:
            nearest = float(np.min(distance[index, selected]))
            multiplier = 1.0 - math.exp(-nearest / float(cfg.diversity_scale_km))
            score = float(predictions[index]) * multiplier
            candidates_with_scores.append((
                score,
                float(predictions[index]),
                float(local[index]),
                str(stable[index]),
                int(index),
                multiplier,
            ))
        best_score = max(item[0] for item in candidates_with_scores)
        score_ties = [item for item in candidates_with_scores if math.isclose(item[0], best_score, rel_tol=0.0, abs_tol=1e-12)]
        best_prediction = max(item[1] for item in score_ties)
        prediction_ties = [item for item in score_ties if math.isclose(item[1], best_prediction, rel_tol=0.0, abs_tol=1e-12)]
        best_local = max(item[2] for item in prediction_ties)
        local_ties = [item for item in prediction_ties if math.isclose(item[2], best_local, rel_tol=0.0, abs_tol=1e-12)]
        chosen = min(local_ties, key=lambda item: (item[3], item[4]))
        selected.append(chosen[4])
        roles.append("learned_rescue")
        selection_scores.append(chosen[0])
        recorded_prediction.append(chosen[1])
        multipliers.append(chosen[5])

    out = work.iloc[selected].copy().reset_index(drop=True)
    out["rescue_selection_rank"] = range(1, len(out) + 1)
    out["rescue_role"] = roles
    out["rescue_prediction"] = recorded_prediction
    out["rescue_diversity_multiplier"] = multipliers
    out["rescue_selection_score"] = selection_scores
    out["rescue_policy"] = cfg.protocol_id
    out["rescue_protocol_fingerprint"] = cfg.protocol_fingerprint
    return out


def protocol_fingerprint(payload: dict[str, object]) -> str:
    cleaned = dict(payload)
    cleaned.pop("protocol_fingerprint", None)
    encoded = json.dumps(cleaned, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
