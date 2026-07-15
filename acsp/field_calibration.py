"""Field-informed calibration for GBIF/environment-only candidate ranking.

Field detections are used to learn an interpretable ranking rule, but never become
candidate inputs. At prediction time the calibrated score uses only columns already
derived from GBIF records and environmental layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .field_validation import DEFAULT_RECOVERY_RADII_KM, haversine_distance_m


DEFAULT_FIELD_RADIUS_WEIGHTS: dict[float, float] = {
    0.5: 0.25,
    1.0: 0.30,
    2.0: 0.35,
    5.0: 0.10,
}

# All features remain available at future prediction time from GBIF and environment.
DEFAULT_FIELD_FEATURE_SPECS: dict[str, tuple[str, str]] = {
    "analogue_high": ("analogue_score", "high"),
    "elevation_low": ("elevation", "low"),
    "slope_low": ("slope", "low"),
    "roughness_low": ("roughness", "low"),
    "coast_near": ("distance_to_coast_m", "low"),
    "gbif_near": ("nearest_known_population_km", "low"),
    "gbif_density_high": ("target_record_density", "high"),
    "tpi_flat": ("tpi", "abs_low"),
}


@dataclass(frozen=True)
class RankConfiguration:
    feature_names: tuple[str, ...]
    weights: tuple[float, ...]

    @property
    def config_id(self) -> str:
        parts = [f"{name}:{weight:.3f}" for name, weight in zip(self.feature_names, self.weights)]
        return "|".join(parts)

    def as_dict(self) -> dict[str, object]:
        return {
            "config_id": self.config_id,
            "feature_names": list(self.feature_names),
            "weights": list(self.weights),
        }


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(missing)}")


def attach_field_utility(
    candidates: pd.DataFrame,
    detections: pd.DataFrame,
    *,
    candidate_area_col: str = "survey_area_id",
    detection_area_col: str = "island",
    radius_weights: Mapping[float, float] | None = None,
) -> pd.DataFrame:
    """Attach same-area detection proximity and a multi-scale development utility."""
    _require_columns(candidates, [candidate_area_col, "latitude", "longitude"], "candidates")
    _require_columns(detections, [detection_area_col, "latitude", "longitude"], "detections")
    out = candidates.copy().reset_index(drop=True)
    weights = dict(radius_weights or DEFAULT_FIELD_RADIUS_WEIGHTS)
    total_weight = float(sum(max(0.0, float(value)) for value in weights.values()))
    if total_weight <= 0:
        raise ValueError("radius_weights must contain at least one positive weight")
    weights = {float(radius): max(0.0, float(value)) / total_weight for radius, value in weights.items()}

    nearest_values: list[float] = []
    utility_values: list[float] = []
    coverage_values: dict[float, list[float]] = {radius: [] for radius in weights}
    normalized_detection_area = detections[detection_area_col].astype(str).str.lower()

    for row in out.itertuples(index=False):
        area = str(getattr(row, candidate_area_col)).lower()
        area_detections = detections.loc[normalized_detection_area.eq(area)]
        if area_detections.empty:
            nearest_values.append(np.nan)
            utility_values.append(np.nan)
            for radius in weights:
                coverage_values[radius].append(np.nan)
            continue
        distances_km = haversine_distance_m(
            float(getattr(row, "latitude")),
            float(getattr(row, "longitude")),
            area_detections["latitude"].to_numpy(float),
            area_detections["longitude"].to_numpy(float),
        ) / 1000.0
        nearest_values.append(float(np.min(distances_km)))
        utility = 0.0
        for radius, weight in weights.items():
            coverage = float(np.mean(distances_km <= radius))
            coverage_values[radius].append(coverage)
            utility += weight * coverage
        utility_values.append(float(utility))

    out["field_nearest_detection_km"] = nearest_values
    for radius, values in coverage_values.items():
        out[f"field_coverage_{radius:g}km"] = values
    out["field_multiscale_utility"] = utility_values
    return out


def add_within_area_rank_features(
    candidates: pd.DataFrame,
    *,
    area_col: str = "survey_area_id",
    feature_specs: Mapping[str, tuple[str, str]] | None = None,
) -> tuple[pd.DataFrame, dict[str, tuple[str, str]]]:
    """Add area-relative percentile features with explicit preference directions."""
    _require_columns(candidates, [area_col], "candidates")
    out = candidates.copy().reset_index(drop=True)
    specs = dict(feature_specs or DEFAULT_FIELD_FEATURE_SPECS)
    available: dict[str, tuple[str, str]] = {}
    for name, (column, direction) in specs.items():
        if column not in out.columns:
            continue
        values = pd.to_numeric(out[column], errors="coerce")
        if direction == "abs_low":
            values = values.abs()
            percentile = values.groupby(out[area_col]).rank(method="average", pct=True)
            ranked = 1.0 - percentile
        elif direction == "low":
            percentile = values.groupby(out[area_col]).rank(method="average", pct=True)
            ranked = 1.0 - percentile
        elif direction == "high":
            ranked = values.groupby(out[area_col]).rank(method="average", pct=True)
        else:
            raise ValueError(f"Unknown feature direction {direction!r} for {name!r}")
        out[f"field_rank_{name}"] = ranked.fillna(0.5).clip(0.0, 1.0)
        available[name] = (column, direction)
    if not available:
        raise ValueError("No field-calibration feature columns were available")
    return out, available


def enumerate_rank_configurations(
    feature_names: Sequence[str],
    *,
    maximum_features: int = 4,
) -> list[RankConfiguration]:
    """Generate a bounded, interpretable rank-score search space."""
    names = tuple(dict.fromkeys(str(name) for name in feature_names))
    configurations: list[RankConfiguration] = []
    for size in range(1, min(maximum_features, len(names)) + 1):
        for selected in combinations(names, size):
            configurations.append(RankConfiguration(selected, tuple([1.0 / size] * size)))
    for selected in combinations(names, 2):
        for first_weight in (0.25, 0.50, 0.75):
            configurations.append(
                RankConfiguration(selected, (first_weight, 1.0 - first_weight))
            )
    deduplicated: dict[str, RankConfiguration] = {}
    for configuration in configurations:
        deduplicated[configuration.config_id] = configuration
    return list(deduplicated.values())


def apply_rank_configuration(
    candidates: pd.DataFrame,
    configuration: RankConfiguration,
    *,
    score_col: str = "field_calibrated_score",
) -> pd.DataFrame:
    """Apply a learned configuration using only GBIF/environment rank columns."""
    out = candidates.copy().reset_index(drop=True)
    required = [f"field_rank_{name}" for name in configuration.feature_names]
    _require_columns(out, required, "ranked candidates")
    score = pd.Series(0.0, index=out.index)
    for name, weight in zip(configuration.feature_names, configuration.weights):
        score += pd.to_numeric(out[f"field_rank_{name}"], errors="coerce").fillna(0.5) * float(weight)
    out[score_col] = score.clip(0.0, 1.0)
    out["field_calibration_config_id"] = configuration.config_id
    return out


def select_one_per_area(
    candidates: pd.DataFrame,
    *,
    area_col: str = "survey_area_id",
    score_col: str = "field_calibrated_score",
    id_col: str = "site_id",
) -> pd.DataFrame:
    """Select the highest calibrated candidate in every non-empty area."""
    _require_columns(candidates, [area_col, score_col, id_col], "candidates")
    rows = []
    for _, group in candidates.groupby(area_col, sort=True, dropna=False):
        ordered = group.assign(
            _stable_id=group[id_col].astype(str),
            _analogue=pd.to_numeric(group.get("analogue_score"), errors="coerce").fillna(-1.0),
        ).sort_values(
            [score_col, "_analogue", "_stable_id"],
            ascending=[False, False, True],
            kind="mergesort",
        )
        rows.append(ordered.iloc[0].drop(labels=["_stable_id", "_analogue"]))
    selected = pd.DataFrame(rows).reset_index(drop=True)
    selected["field_calibrated_selection_rank"] = np.arange(1, len(selected) + 1)
    return selected


def _mean_selected_utility(
    ranked: pd.DataFrame,
    configuration: RankConfiguration,
    areas: Sequence[object],
    *,
    area_col: str,
) -> float:
    subset = ranked[ranked[area_col].isin(areas)]
    scored = apply_rank_configuration(subset, configuration)
    selected = select_one_per_area(scored, area_col=area_col)
    return float(pd.to_numeric(selected["field_multiscale_utility"], errors="coerce").mean())


def recovery_metrics(
    selected: pd.DataFrame,
    detections: pd.DataFrame,
    *,
    candidate_area_col: str = "survey_area_id",
    detection_area_col: str = "island",
    radii_km: Sequence[float] = DEFAULT_RECOVERY_RADII_KM,
) -> dict[str, float | int]:
    """Evaluate same-area detection-cluster recovery for a one-per-area set."""
    recovered = {float(radius): 0 for radius in radii_km}
    nearest: list[float] = []
    total = 0
    selected_area = selected[candidate_area_col].astype(str).str.lower()
    for detection in detections.itertuples(index=False):
        area = str(getattr(detection, detection_area_col)).lower()
        available = selected.loc[selected_area.eq(area)]
        if available.empty:
            distance_km = np.inf
        else:
            distance_km = float(
                np.min(
                    haversine_distance_m(
                        float(getattr(detection, "latitude")),
                        float(getattr(detection, "longitude")),
                        available["latitude"].to_numpy(float),
                        available["longitude"].to_numpy(float),
                    )
                ) / 1000.0
            )
        total += 1
        nearest.append(distance_km)
        for radius in recovered:
            recovered[radius] += int(distance_km <= radius)
    result: dict[str, float | int] = {"n_detection_clusters": int(total)}
    for radius, count in recovered.items():
        result[f"recall_{radius:g}km"] = float(count / total) if total else np.nan
        result[f"n_recovered_{radius:g}km"] = int(count)
    finite = np.asarray([value for value in nearest if np.isfinite(value)], dtype=float)
    result["median_nearest_candidate_km"] = float(np.median(finite)) if len(finite) else np.inf
    result["mean_nearest_candidate_km"] = float(np.mean(finite)) if len(finite) else np.inf
    return result


def calibrate_field_ranker(
    candidates: pd.DataFrame,
    detections: pd.DataFrame,
    *,
    area_col: str = "survey_area_id",
    detection_area_col: str = "island",
    complexity_penalty: float = 0.002,
    maximum_features: int = 4,
) -> dict[str, object]:
    """Tune an interpretable score and estimate optimism with leave-one-area-out CV.

    The final configuration is a development model fitted with all field outcomes.
    `outer_selections` are the honest leave-one-area-out predictions: the rule used
    for each area was chosen using every other area only.
    """
    annotated = attach_field_utility(
        candidates,
        detections,
        candidate_area_col=area_col,
        detection_area_col=detection_area_col,
    )
    ranked, available_specs = add_within_area_rank_features(annotated, area_col=area_col)
    areas = sorted(
        set(ranked[area_col].dropna().tolist()).intersection(
            set(detections[detection_area_col].dropna().tolist())
        ),
        key=str,
    )
    if len(areas) < 3:
        raise ValueError("At least three shared survey areas are required for leave-one-area-out calibration")
    configurations = enumerate_rank_configurations(
        list(available_specs), maximum_features=maximum_features
    )

    search_rows: list[dict[str, object]] = []
    for configuration in configurations:
        mean_utility = _mean_selected_utility(
            ranked, configuration, areas, area_col=area_col
        )
        objective = mean_utility - float(complexity_penalty) * len(configuration.feature_names)
        search_rows.append(
            {
                **configuration.as_dict(),
                "mean_area_utility": mean_utility,
                "penalized_objective": objective,
                "n_features": len(configuration.feature_names),
            }
        )
    search = pd.DataFrame(search_rows).sort_values(
        ["penalized_objective", "mean_area_utility", "n_features", "config_id"],
        ascending=[False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    final_row = search.iloc[0]
    final_configuration = RankConfiguration(
        tuple(final_row["feature_names"]), tuple(float(value) for value in final_row["weights"])
    )

    outer_rows = []
    outer_configs = []
    for held_area in areas:
        training_areas = [area for area in areas if area != held_area]
        candidates_for_fold = []
        for configuration in configurations:
            utility = _mean_selected_utility(
                ranked, configuration, training_areas, area_col=area_col
            )
            objective = utility - float(complexity_penalty) * len(configuration.feature_names)
            candidates_for_fold.append((objective, utility, -len(configuration.feature_names), configuration.config_id, configuration))
        _, training_utility, _, _, chosen_configuration = max(candidates_for_fold)
        held_candidates = ranked[ranked[area_col].eq(held_area)]
        held_scored = apply_rank_configuration(held_candidates, chosen_configuration)
        held_selected = select_one_per_area(held_scored, area_col=area_col).iloc[0].to_dict()
        held_selected["held_out_area"] = held_area
        held_selected["training_mean_area_utility"] = float(training_utility)
        outer_rows.append(held_selected)
        outer_configs.append(
            {
                "held_out_area": held_area,
                **chosen_configuration.as_dict(),
                "training_mean_area_utility": float(training_utility),
            }
        )

    final_scored = apply_rank_configuration(ranked, final_configuration)
    final_selected = select_one_per_area(final_scored, area_col=area_col)
    outer_selected = pd.DataFrame(outer_rows).reset_index(drop=True)
    baseline_configuration = RankConfiguration(("analogue_high",), (1.0,))
    baseline_selected = select_one_per_area(
        apply_rank_configuration(ranked, baseline_configuration), area_col=area_col
    )

    return {
        "annotated_candidates": final_scored,
        "configuration_search": search,
        "outer_selections": outer_selected,
        "outer_configurations": pd.DataFrame(outer_configs),
        "final_selections": final_selected,
        "baseline_selections": baseline_selected,
        "final_configuration": final_configuration,
        "available_feature_specs": available_specs,
        "baseline_metrics": recovery_metrics(
            baseline_selected, detections, candidate_area_col=area_col, detection_area_col=detection_area_col
        ),
        "outer_cv_metrics": recovery_metrics(
            outer_selected, detections, candidate_area_col=area_col, detection_area_col=detection_area_col
        ),
        "development_metrics": recovery_metrics(
            final_selected, detections, candidate_area_col=area_col, detection_area_col=detection_area_col
        ),
    }
