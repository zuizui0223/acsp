"""Reusable automatic SDM core shared by the app and decision benchmarks.

This module contains the deterministic mathematical pieces of ACSP's automatic
species SDM: derivation of the five macro-climate predictors used by the app,
interpolation of those predictors to arbitrary WGS84 points, fitting of the
existing four-model equal-weight ensemble, and deterministic Top-k selection.

Network retrieval, land-mask construction, and UI orchestration remain outside
this module so they can be audited separately.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from .modeling import (
    DEFAULT_ENSEMBLE_ALGORITHMS,
    make_classifier,
    predict_equal_weight_ensemble,
)

AUTO_SDM_VARIABLES: tuple[str, ...] = ("bio1", "bio4", "bio12", "bio14", "bio15")
NASA_POWER_MONTHS: tuple[str, ...] = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)
NASA_POWER_MONTH_DAYS = np.array(
    [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
    dtype=float,
)


@dataclass(frozen=True)
class AutomaticSdmCoreConfig:
    """Frozen model identity for the reusable automatic SDM core."""

    variables: tuple[str, ...] = AUTO_SDM_VARIABLES
    algorithms: tuple[str, ...] = DEFAULT_ENSEMBLE_ALGORITHMS
    ensemble: str = "equal_weight_mean_probability"
    environmental_source: str = "NASA POWER 1981-2010 T2M and PRECTOTCORR normals"
    interpolation_neighbors: int = 4
    interpolation_power: float = 2.0
    random_state: int = 42

    def validate(self) -> None:
        if not self.variables:
            raise ValueError("variables must not be empty")
        if not self.algorithms:
            raise ValueError("algorithms must not be empty")
        if self.interpolation_neighbors < 1:
            raise ValueError("interpolation_neighbors must be positive")
        if self.interpolation_power <= 0:
            raise ValueError("interpolation_power must be positive")
        if self.ensemble != "equal_weight_mean_probability":
            raise ValueError("only the production equal-weight ensemble is supported")

    def manifest(self) -> dict[str, object]:
        self.validate()
        payload: dict[str, object] = {
            **asdict(self),
            "variables": list(self.variables),
            "algorithms": list(self.algorithms),
            "climate_derivation": {
                "bio1": "mean monthly T2M",
                "bio4": "population standard deviation of monthly T2M multiplied by 100",
                "bio12": "sum of monthly PRECTOTCORR totals",
                "bio14": "minimum monthly PRECTOTCORR total",
                "bio15": "coefficient of variation of monthly PRECTOTCORR totals multiplied by 100",
            },
            "score_interpretation": "relative suitability for ranking; not calibrated occupancy probability",
        }
        payload["fingerprint"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return payload


def _monthly_table(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    required = {"latitude", "longitude", *NASA_POWER_MONTHS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{label} climatology is missing: {', '.join(sorted(missing))}")
    work = frame.copy()
    work["latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    for month in NASA_POWER_MONTHS:
        work[month] = pd.to_numeric(work[month], errors="coerce").replace(-999.0, np.nan)
    return work.dropna(subset=["latitude", "longitude"]).sort_values(
        ["latitude", "longitude"], kind="mergesort"
    ).drop_duplicates(["latitude", "longitude"]).reset_index(drop=True)


def derive_power_bioclim(
    temperature: pd.DataFrame,
    precipitation_rate: pd.DataFrame,
) -> pd.DataFrame:
    """Derive the five production BIO predictors from NASA POWER monthly normals.

    ``temperature`` contains monthly T2M values. ``precipitation_rate`` contains
    monthly PRECTOTCORR daily rates, which are converted to monthly totals using
    the same mean month lengths as the production app.
    """
    temp = _monthly_table(temperature, "temperature")
    precip = _monthly_table(precipitation_rate, "precipitation")
    common = temp[["latitude", "longitude"]].merge(
        precip[["latitude", "longitude"]], on=["latitude", "longitude"], how="inner"
    )
    if common.empty:
        raise ValueError("temperature and precipitation climatologies have no common cells")
    temp = common.merge(temp, on=["latitude", "longitude"], how="left")
    precip = common.merge(precip, on=["latitude", "longitude"], how="left")
    temp_monthly = temp[list(NASA_POWER_MONTHS)].to_numpy(dtype=float)
    precip_monthly = (
        precip[list(NASA_POWER_MONTHS)].to_numpy(dtype=float)
        * NASA_POWER_MONTH_DAYS[None, :]
    )
    climate = common.copy()
    climate["bio1"] = np.nanmean(temp_monthly, axis=1)
    climate["bio4"] = np.nanstd(temp_monthly, axis=1, ddof=0) * 100.0
    climate["bio12"] = np.nansum(precip_monthly, axis=1)
    climate["bio14"] = np.nanmin(precip_monthly, axis=1)
    precip_mean = np.nanmean(precip_monthly, axis=1)
    climate["bio15"] = np.divide(
        np.nanstd(precip_monthly, axis=1, ddof=0) * 100.0,
        precip_mean,
        out=np.full(len(climate), np.nan),
        where=precip_mean > 0,
    )
    return climate.dropna(subset=list(AUTO_SDM_VARIABLES)).reset_index(drop=True)


def interpolate_power_bioclim(
    points: pd.DataFrame,
    climate: pd.DataFrame,
    *,
    variables: Sequence[str] = AUTO_SDM_VARIABLES,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    neighbors: int = 4,
    power: float = 2.0,
) -> pd.DataFrame:
    """Attach inverse-distance interpolated macro-climate predictors to points."""
    if neighbors < 1 or power <= 0:
        raise ValueError("neighbors and power must be positive")
    missing_points = {latitude_col, longitude_col} - set(points.columns)
    if missing_points:
        raise ValueError(f"points are missing: {', '.join(sorted(missing_points))}")
    missing_climate = {"latitude", "longitude", *variables} - set(climate.columns)
    if missing_climate:
        raise ValueError(f"climate is missing: {', '.join(sorted(missing_climate))}")
    out = points.copy().reset_index(drop=True)
    if out.empty:
        for variable in variables:
            out[variable] = pd.Series(dtype=float)
        return out
    source_frame = climate[["latitude", "longitude", *variables]].copy()
    source_frame = source_frame.apply(pd.to_numeric, errors="coerce").dropna()
    if source_frame.empty:
        raise ValueError("climate has no complete finite rows")
    targets = out[[latitude_col, longitude_col]].apply(pd.to_numeric, errors="coerce")
    if targets.isna().any().any():
        raise ValueError("point coordinates must be finite")
    source = np.radians(source_frame[["latitude", "longitude"]].to_numpy(dtype=float))
    target = np.radians(targets.to_numpy(dtype=float))
    k = min(int(neighbors), len(source_frame))
    distances, indices = BallTree(source, metric="haversine").query(target, k=k)
    weights = 1.0 / np.maximum(distances, 1e-10) ** float(power)
    weights /= weights.sum(axis=1, keepdims=True)
    for variable in variables:
        values = source_frame[variable].to_numpy(dtype=float)
        out[str(variable)] = np.sum(values[indices] * weights, axis=1)
    return out


def fit_automatic_sdm_core(
    training_table: pd.DataFrame,
    *,
    config: AutomaticSdmCoreConfig | None = None,
    label_col: str = "presence",
) -> dict[str, object]:
    """Fit the production four-model equal-weight ensemble on a prepared table."""
    cfg = config or AutomaticSdmCoreConfig()
    cfg.validate()
    required = {label_col, *cfg.variables}
    missing = required - set(training_table.columns)
    if missing:
        raise ValueError(f"training table is missing: {', '.join(sorted(missing))}")
    work = training_table.copy().reset_index(drop=True)
    work[label_col] = pd.to_numeric(work[label_col], errors="coerce")
    for variable in cfg.variables:
        work[variable] = pd.to_numeric(work[variable], errors="coerce")
    work = work.dropna(subset=[label_col, *cfg.variables]).reset_index(drop=True)
    labels = work[label_col].astype(int)
    if len(work) < 4 or labels.nunique() < 2:
        raise ValueError("automatic SDM requires both presence and background rows")
    models: dict[str, object] = {}
    X = work[list(cfg.variables)]
    for algorithm in cfg.algorithms:
        model = make_classifier(str(algorithm), random_state=int(cfg.random_state))
        model.fit(X, labels)
        models[str(algorithm)] = model
    return {
        "models": models,
        "variables": list(cfg.variables),
        "training_rows": int(len(work)),
        "training_presences": int(labels.sum()),
        "config": cfg.manifest(),
    }


def score_automatic_sdm_candidates(
    candidates: pd.DataFrame,
    fitted: Mapping[str, object],
    *,
    score_col: str = "sdm_suitability",
) -> pd.DataFrame:
    """Score candidate rows with a fitted automatic SDM ensemble."""
    if candidates is None:
        raise ValueError("candidates must be a DataFrame")
    variables = tuple(map(str, fitted.get("variables", AUTO_SDM_VARIABLES)))
    missing = set(variables) - set(candidates.columns)
    if missing:
        raise ValueError(f"candidates are missing SDM variables: {', '.join(sorted(missing))}")
    models = fitted.get("models")
    if not isinstance(models, Mapping) or not models:
        raise ValueError("fitted SDM does not contain models")
    out = candidates.copy().reset_index(drop=True)
    features = out[list(variables)].apply(pd.to_numeric, errors="coerce")
    out[score_col] = np.clip(
        predict_equal_weight_ensemble(models, features), 0.0, 1.0
    )
    return out


def select_sdm_top_k(
    candidates: pd.DataFrame,
    k: int = 5,
    *,
    score_col: str = "sdm_suitability",
    id_col: str = "candidate_id",
) -> pd.DataFrame:
    """Select a deterministic finite survey set by fitted SDM suitability."""
    if k < 1:
        raise ValueError("k must be positive")
    if score_col not in candidates.columns:
        raise ValueError(f"candidates are missing score column: {score_col}")
    out = candidates.copy().reset_index(drop=True)
    if id_col not in out.columns:
        out[id_col] = [f"candidate-{index + 1:06d}" for index in range(len(out))]
    out[score_col] = pd.to_numeric(out[score_col], errors="coerce").fillna(-np.inf)
    selected = out.sort_values(
        [score_col, id_col], ascending=[False, True], kind="mergesort"
    ).head(min(int(k), len(out))).copy().reset_index(drop=True)
    selected["decision_method"] = "fitted_sdm_top_k"
    selected["decision_rank"] = range(1, len(selected) + 1)
    return selected
