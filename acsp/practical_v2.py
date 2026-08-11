"""Experimental ACSP v2 practical finite-decision policy.

ACSP v1 remains frozen in :mod:`acsp.validated_core`. This module is a
separate development track. It scores candidates with a cross-taxon learned
survey-decision utility and selects a finite Top-k set while penalising
short-range geographic redundancy.

The learned score is not an occupancy probability or habitat-suitability
estimate. Its development target is whether a candidate recovered at least
one spatially held-out occurrence within the predeclared 10-km regional
endpoint in folds belonging to other taxon-region pairs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np
import pandas as pd

from .validated_core import ValidatedCorePolicy, select_validated_core


EARTH_RADIUS_KM = 6_371.0088
V2_PROTOCOL_ID = "acsp-v2-practical-candidate-utility-development-v1"
V2_PROTOCOL_FINGERPRINT = "378e069f982a19abfc0183163fd503b467a1b746c11ba0b354d4f9802c155124"
V2_ENVIRONMENTAL_COLUMNS: tuple[str, ...] = (
    "elevation",
    "slope",
    "aspect",
    "roughness",
    "tpi",
)
V2_NUMERIC_FEATURES: tuple[str, ...] = (
    "local_score",
    "local_rank_pct",
    "geo_nn_km",
    "geo_avg_km",
    "env_nn",
    "env_avg",
    "candidate_pool",
    "pool_local_sd",
    "pool_local_q90",
)
V2_CATEGORICAL_FEATURES: tuple[str, ...] = ("taxon_group", "candidate_type")

# Frozen all-development model. C=0.03 and the set-selection parameters were
# selected using development artifacts and must not change after untouched
# confirmation outcomes are generated.
_NUMERIC_IMPUTE_MEDIAN = {
    "local_score": 0.8703,
    "local_rank_pct": 0.5263157894736842,
    "geo_nn_km": 14.383840777604302,
    "geo_avg_km": 97.95993647079658,
    "env_nn": 1.0160845593404682,
    "env_avg": 2.581486785765029,
    "candidate_pool": 21.0,
    "pool_local_sd": 0.1838309956703053,
    "pool_local_q90": 0.93819,
}
_NUMERIC_MEAN = {
    "local_score": 0.780743124841732,
    "local_rank_pct": 0.529880982527222,
    "geo_nn_km": 20.203573751741928,
    "geo_avg_km": 99.15105196327129,
    "env_nn": 1.2058836341183297,
    "env_avg": 2.9281937217042264,
    "candidate_pool": 19.67763990883768,
    "pool_local_sd": 0.197047712160393,
    "pool_local_q90": 0.93695358825019,
}
_NUMERIC_SCALE = {
    "local_score": 0.2333476620118171,
    "local_rank_pct": 0.28930706446459675,
    "geo_nn_km": 17.92582769344763,
    "geo_avg_km": 33.96562305335991,
    "env_nn": 0.8783572584749634,
    "env_avg": 1.244787228311497,
    "candidate_pool": 4.383855704071777,
    "pool_local_sd": 0.08834649466515469,
    "pool_local_q90": 0.05372084147682438,
}
_CATEGORIES = {
    "taxon_group": ("animal", "plant"),
    "candidate_type": ("environmental", "habitat", "other", "survey_gap"),
}
_COEFFICIENTS = {
    "num__local_score": 0.001365823784233943,
    "num__local_rank_pct": -0.2292411486645918,
    "num__geo_nn_km": -0.12328032920259416,
    "num__geo_avg_km": -0.05578437738212702,
    "num__env_nn": 0.06389165001390519,
    "num__env_avg": -0.12988711135391312,
    "num__candidate_pool": -0.2123124267637981,
    "num__pool_local_sd": 0.07706412858722425,
    "num__pool_local_q90": -0.09362648330870571,
    "cat__taxon_group_animal": -0.5449813092213169,
    "cat__taxon_group_plant": 0.5446721731192732,
    "cat__candidate_type_environmental": -0.7101635694171469,
    "cat__candidate_type_habitat": 0.1567657656890962,
    "cat__candidate_type_other": 0.6870599751691854,
    "cat__candidate_type_survey_gap": -0.1339713075431855,
}
_INTERCEPT = -0.2056901276961428


@dataclass(frozen=True)
class CandidateDecisionUtilityPolicy:
    """Frozen development configuration for the experimental v2 policy."""

    top_k: int = 5
    candidate_utility_weight: float = 0.60
    geographic_representation_weight: float = 0.40
    geographic_scale_km: float = 10.0
    first_candidate_representation: float = 0.50
    protocol_id: str = V2_PROTOCOL_ID
    protocol_fingerprint: str = V2_PROTOCOL_FINGERPRINT

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        if not 0.0 <= self.candidate_utility_weight <= 1.0:
            raise ValueError("candidate_utility_weight must lie in [0, 1]")
        if not 0.0 <= self.geographic_representation_weight <= 1.0:
            raise ValueError("geographic_representation_weight must lie in [0, 1]")
        if not math.isclose(
            self.candidate_utility_weight + self.geographic_representation_weight,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("v2 selection weights must sum to one")
        if self.geographic_scale_km <= 0:
            raise ValueError("geographic_scale_km must be positive")


def _haversine_matrix_km(latitude: np.ndarray, longitude: np.ndarray) -> np.ndarray:
    lat = np.radians(latitude.astype(float))
    lon = np.radians(longitude.astype(float))
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def normalize_v2_candidate_type(value: object) -> str:
    """Map production candidate labels to the frozen four-level role."""
    text = str(value or "").strip().lower()
    if "habitat" in text or "analogue" in text:
        return "habitat"
    if "survey-gap" in text or "under-surveyed" in text:
        return "survey_gap"
    if "environmental" in text:
        return "environmental"
    return "other"


def _candidate_id_series(frame: pd.DataFrame) -> pd.Series:
    for column in ("candidate_id", "site_id"):
        if column in frame.columns:
            return frame[column].astype(str)
    return pd.Series(
        [f"candidate-{index + 1:06d}" for index in range(len(frame))],
        index=frame.index,
        dtype=str,
    )


def _environmental_distance_matrix(frame: pd.DataFrame) -> np.ndarray | None:
    """Return robust within-pool environmental distances or None for no-terrain pools.

    The development artifacts contained one marine taxon with none of the five
    terrain columns. That is a supported missing-context state and is handled by
    the frozen model imputer. A partial terrain schema is treated as an input
    inconsistency rather than silently changing the environmental definition.
    """
    present = [column in frame.columns for column in V2_ENVIRONMENTAL_COLUMNS]
    if not any(present):
        return None
    if not all(present):
        missing = [column for column, available in zip(V2_ENVIRONMENTAL_COLUMNS, present) if not available]
        raise ValueError(f"v2 candidate utility has a partial environmental schema; missing: {', '.join(missing)}")

    parts: list[np.ndarray] = []
    for column in V2_ENVIRONMENTAL_COLUMNS:
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(float)
        if column == "aspect":
            parts.append(np.sin(np.deg2rad(values)))
            parts.append(np.cos(np.deg2rad(values)))
            continue
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            parts.append(np.zeros(len(frame), dtype=float))
            continue
        median = float(np.nanmedian(values))
        q25, q75 = np.nanquantile(values, [0.25, 0.75])
        scale = float(q75 - q25)
        if not np.isfinite(scale) or scale <= 1e-9:
            standardized = np.zeros(len(frame), dtype=float)
        else:
            standardized = (values - median) / scale
        parts.append(np.where(np.isfinite(standardized), standardized, 0.0))
    matrix = np.vstack(parts).T
    matrix = np.where(np.isfinite(matrix), matrix, 0.0)
    delta = matrix[:, None, :] - matrix[None, :, :]
    return np.sqrt(np.sum(delta * delta, axis=2))


def build_candidate_decision_utility_features(
    candidates: pd.DataFrame,
    taxon_group: str,
) -> pd.DataFrame:
    """Build the frozen outcome-free candidate feature table."""
    if candidates is None:
        raise ValueError("candidates must be a DataFrame")
    if candidates.empty:
        return candidates.head(0).copy()
    group = str(taxon_group).strip().lower()
    if group not in _CATEGORIES["taxon_group"]:
        raise ValueError("v2 candidate utility currently supports only plant or animal groups")
    required = {"latitude", "longitude", "component_local_habitat_score"}
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError(f"v2 candidate utility is missing: {', '.join(sorted(missing))}")

    work = candidates.copy().reset_index(drop=True)
    work["latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    work = work.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    if work.empty:
        return work

    stable_id = _candidate_id_series(work)
    local = pd.to_numeric(
        work["component_local_habitat_score"], errors="coerce"
    ).fillna(0.0).clip(0.0, 1.0)
    ordering = pd.DataFrame({
        "index": np.arange(len(work)),
        "score": local.to_numpy(float),
        "stable_id": stable_id.to_numpy(str),
    }).sort_values(
        ["score", "stable_id", "index"],
        ascending=[False, True, True],
        kind="mergesort",
    )
    ranks = np.empty(len(work), dtype=float)
    ranks[ordering["index"].to_numpy(int)] = np.arange(1, len(work) + 1, dtype=float)

    latitude = work["latitude"].to_numpy(float)
    longitude = work["longitude"].to_numpy(float)
    geographic = _haversine_matrix_km(latitude, longitude)
    if len(work) > 1:
        nearest = geographic.copy()
        np.fill_diagonal(nearest, np.inf)
        geo_nn = np.min(nearest, axis=1)
        geo_avg = np.sum(geographic, axis=1) / (len(work) - 1)
    else:
        geo_nn = np.zeros(1, dtype=float)
        geo_avg = np.zeros(1, dtype=float)

    environmental = _environmental_distance_matrix(work)
    if environmental is None:
        env_nn = np.full(len(work), np.nan, dtype=float)
        env_avg = np.full(len(work), np.nan, dtype=float)
    elif len(work) > 1:
        nearest = environmental.copy()
        np.fill_diagonal(nearest, np.inf)
        env_nn = np.min(nearest, axis=1)
        env_avg = np.sum(environmental, axis=1) / (len(work) - 1)
    else:
        env_nn = np.zeros(1, dtype=float)
        env_avg = np.zeros(1, dtype=float)

    features = pd.DataFrame(index=work.index)
    features["local_score"] = local.to_numpy(float)
    features["local_rank_pct"] = ranks / len(work)
    features["geo_nn_km"] = geo_nn
    features["geo_avg_km"] = geo_avg
    features["env_nn"] = env_nn
    features["env_avg"] = env_avg
    features["candidate_pool"] = float(len(work))
    features["pool_local_sd"] = float(np.std(local.to_numpy(float)))
    features["pool_local_q90"] = float(np.quantile(local.to_numpy(float), 0.90))
    features["taxon_group"] = group
    candidate_type = work.get("candidate_type", pd.Series("", index=work.index))
    features["candidate_type"] = candidate_type.map(normalize_v2_candidate_type)
    features["_stable_id"] = stable_id.to_numpy(str)
    features["_source_index"] = np.arange(len(work), dtype=int)
    return features


def score_candidate_decision_utility(
    candidates: pd.DataFrame,
    taxon_group: str,
) -> pd.DataFrame:
    """Attach the frozen cross-taxon candidate decision-utility score."""
    features = build_candidate_decision_utility_features(candidates, taxon_group)
    if features.empty:
        return candidates.head(0).copy()

    linear = np.full(len(features), _INTERCEPT, dtype=float)
    for feature in V2_NUMERIC_FEATURES:
        values = pd.to_numeric(features[feature], errors="coerce").to_numpy(float)
        values = np.where(np.isfinite(values), values, _NUMERIC_IMPUTE_MEDIAN[feature])
        standardized = (values - _NUMERIC_MEAN[feature]) / _NUMERIC_SCALE[feature]
        linear += standardized * _COEFFICIENTS[f"num__{feature}"]
    for feature in V2_CATEGORICAL_FEATURES:
        values = features[feature].astype(str).to_numpy()
        for category in _CATEGORIES[feature]:
            linear += (values == category).astype(float) * _COEFFICIENTS[
                f"cat__{feature}_{category}"
            ]

    positive = linear >= 0
    score = np.empty(len(linear), dtype=float)
    score[positive] = 1.0 / (1.0 + np.exp(-linear[positive]))
    exp_linear = np.exp(linear[~positive])
    score[~positive] = exp_linear / (1.0 + exp_linear)

    work = candidates.copy().reset_index(drop=True)
    work["latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    work = work.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    work["v2_candidate_decision_utility_score"] = score
    work["v2_candidate_decision_utility_model"] = V2_PROTOCOL_ID
    work["v2_protocol_fingerprint"] = V2_PROTOCOL_FINGERPRINT
    return work


def select_candidate_decision_utility(
    candidates: pd.DataFrame,
    taxon_group: str,
    policy: CandidateDecisionUtilityPolicy | None = None,
) -> pd.DataFrame:
    """Select Top-k from learned candidate utility plus short-range representation."""
    cfg = policy or CandidateDecisionUtilityPolicy()
    scored = score_candidate_decision_utility(candidates, taxon_group)
    if scored.empty:
        return scored
    score = scored["v2_candidate_decision_utility_score"].to_numpy(float)
    geographic = _haversine_matrix_km(
        scored["latitude"].to_numpy(float),
        scored["longitude"].to_numpy(float),
    )
    stable_id = _candidate_id_series(scored).to_numpy(str)

    selected: list[int] = []
    utilities: list[float] = []
    representations: list[float] = []
    while len(selected) < min(cfg.top_k, len(scored)):
        best: tuple[float, float, str, int] | None = None
        best_representation = 0.0
        for index in range(len(scored)):
            if index in selected:
                continue
            if selected:
                nearest = float(np.min(geographic[index, selected]))
                representation = 1.0 - math.exp(-nearest / cfg.geographic_scale_km)
            else:
                representation = cfg.first_candidate_representation
            utility = (
                cfg.candidate_utility_weight * score[index]
                + cfg.geographic_representation_weight * representation
            )
            key = (utility, score[index], str(stable_id[index]), -index)
            if best is None or key > best:
                best = key
                best_representation = representation
        assert best is not None
        chosen = -int(best[3])
        selected.append(chosen)
        utilities.append(float(best[0]))
        representations.append(float(best_representation))

    out = scored.iloc[selected].copy().reset_index(drop=True)
    out["v2_selection_rank"] = range(1, len(out) + 1)
    out["v2_selection_utility"] = np.round(utilities, 8)
    out["v2_geographic_representation"] = np.round(representations, 8)
    out["v2_policy"] = V2_PROTOCOL_ID
    out["v2_fallback_used"] = False
    out["v2_fallback_reason"] = ""
    return out


def select_practical_v2(
    candidates: pd.DataFrame,
    taxon_group: str,
    policy: CandidateDecisionUtilityPolicy | None = None,
) -> pd.DataFrame:
    """Use v2 when supported, otherwise transparently fall back to frozen v1."""
    if candidates is None:
        raise ValueError("candidates must be a DataFrame")
    if candidates.empty:
        return candidates.copy()
    cfg = policy or CandidateDecisionUtilityPolicy()
    try:
        return select_candidate_decision_utility(candidates, taxon_group, cfg)
    except (ValueError, KeyError) as error:
        fallback_policy = ValidatedCorePolicy.for_taxon_group(taxon_group)
        fallback = select_validated_core(candidates, fallback_policy).copy()
        fallback["v2_candidate_decision_utility_score"] = np.nan
        fallback["v2_selection_rank"] = range(1, len(fallback) + 1)
        fallback["v2_selection_utility"] = np.nan
        fallback["v2_geographic_representation"] = np.nan
        fallback["v2_policy"] = V2_PROTOCOL_ID
        fallback["v2_protocol_fingerprint"] = V2_PROTOCOL_FINGERPRINT
        fallback["v2_fallback_used"] = True
        fallback["v2_fallback_reason"] = f"{type(error).__name__}: {error}"
        return fallback


def development_protocol_fingerprint(payload: dict[str, object]) -> str:
    """Return the canonical SHA-256 used to audit the external JSON artifact."""
    cleaned = dict(payload)
    cleaned.pop("fingerprint", None)
    encoded = json.dumps(cleaned, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
