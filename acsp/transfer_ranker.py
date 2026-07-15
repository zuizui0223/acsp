"""Transfer-aware field ranking with full within-area ordering information.

The first field-calibration implementation optimized only the utility of the single
selected candidate in each survey area. With few areas this is unstable: many
configurations tie on the top candidate while ordering the remaining candidates
poorly. This module adds an area-balanced pairwise concordance term so calibration
uses the complete candidate ordering without treating candidate rows as independent
replicates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .field_calibration import (
    DEFAULT_FIELD_FEATURE_SPECS,
    RankConfiguration,
    add_within_area_rank_features,
    apply_rank_configuration,
    attach_field_utility,
    enumerate_rank_configurations,
    recovery_metrics,
    select_one_per_area,
)

GBIF_BIAS_FEATURES = frozenset({"gbif_near", "gbif_density_high"})


@dataclass(frozen=True)
class TransferObjective:
    selected_utility_weight: float = 0.5
    pairwise_concordance_weight: float = 0.5
    complexity_penalty: float = 0.002

    def normalized(self) -> "TransferObjective":
        selected = max(0.0, float(self.selected_utility_weight))
        pairwise = max(0.0, float(self.pairwise_concordance_weight))
        total = selected + pairwise
        if total <= 0:
            raise ValueError("At least one transfer-objective weight must be positive")
        return TransferObjective(
            selected_utility_weight=selected / total,
            pairwise_concordance_weight=pairwise / total,
            complexity_penalty=max(0.0, float(self.complexity_penalty)),
        )


def _configuration_score(frame: pd.DataFrame, configuration: RankConfiguration) -> pd.Series:
    score = pd.Series(0.0, index=frame.index, dtype=float)
    for name, weight in zip(configuration.feature_names, configuration.weights):
        column = f"field_rank_{name}"
        score += pd.to_numeric(frame[column], errors="coerce").fillna(0.5) * float(weight)
    return score


def mean_selected_utility(
    ranked: pd.DataFrame,
    configuration: RankConfiguration,
    areas: Sequence[object],
    *,
    area_col: str = "survey_area_id",
) -> float:
    subset = ranked[ranked[area_col].isin(areas)]
    scored = apply_rank_configuration(subset, configuration)
    selected = select_one_per_area(scored, area_col=area_col)
    return float(pd.to_numeric(selected["field_multiscale_utility"], errors="coerce").mean())


def mean_pairwise_concordance(
    ranked: pd.DataFrame,
    configuration: RankConfiguration,
    areas: Sequence[object],
    *,
    area_col: str = "survey_area_id",
    utility_col: str = "field_multiscale_utility",
) -> float:
    """Return the mean within-area pairwise ranking concordance.

    Areas receive equal weight regardless of candidate count. Candidate pairs with
    equal field utility are ignored; score ties receive half credit.
    """
    area_values: list[float] = []
    for area in areas:
        group = ranked[ranked[area_col].eq(area)]
        if len(group) < 2:
            continue
        score = _configuration_score(group, configuration).to_numpy(float)
        utility = pd.to_numeric(group[utility_col], errors="coerce").to_numpy(float)
        concordant = 0.0
        comparable = 0
        for first in range(len(group)):
            if not np.isfinite(utility[first]):
                continue
            for second in range(first + 1, len(group)):
                if not np.isfinite(utility[second]) or utility[first] == utility[second]:
                    continue
                comparable += 1
                product = (score[first] - score[second]) * (utility[first] - utility[second])
                if product > 0:
                    concordant += 1.0
                elif product == 0:
                    concordant += 0.5
        if comparable:
            area_values.append(concordant / comparable)
    return float(np.mean(area_values)) if area_values else 0.5


def configuration_objective(
    ranked: pd.DataFrame,
    configuration: RankConfiguration,
    areas: Sequence[object],
    *,
    objective: TransferObjective | None = None,
    area_col: str = "survey_area_id",
) -> dict[str, float]:
    settings = (objective or TransferObjective()).normalized()
    selected = mean_selected_utility(ranked, configuration, areas, area_col=area_col)
    concordance = mean_pairwise_concordance(ranked, configuration, areas, area_col=area_col)
    value = (
        settings.selected_utility_weight * selected
        + settings.pairwise_concordance_weight * concordance
        - settings.complexity_penalty * len(configuration.feature_names)
    )
    return {
        "mean_area_selected_utility": selected,
        "mean_area_pairwise_concordance": concordance,
        "transfer_objective": float(value),
    }


def _choose_configuration(
    ranked: pd.DataFrame,
    configurations: Sequence[RankConfiguration],
    areas: Sequence[object],
    *,
    objective: TransferObjective,
    area_col: str,
) -> tuple[RankConfiguration, dict[str, float]]:
    rows = []
    for configuration in configurations:
        metrics = configuration_objective(
            ranked,
            configuration,
            areas,
            objective=objective,
            area_col=area_col,
        )
        rows.append((
            metrics["transfer_objective"],
            metrics["mean_area_pairwise_concordance"],
            metrics["mean_area_selected_utility"],
            -len(configuration.feature_names),
            configuration.config_id,
            configuration,
            metrics,
        ))
    _, _, _, _, _, configuration, metrics = max(rows)
    return configuration, metrics


def calibrate_transfer_ranker(
    candidates: pd.DataFrame,
    detections: pd.DataFrame,
    *,
    area_col: str = "survey_area_id",
    detection_area_col: str = "island",
    feature_specs: Mapping[str, tuple[str, str]] | None = None,
    excluded_features: Sequence[str] = (),
    objective: TransferObjective | None = None,
    maximum_features: int = 4,
) -> dict[str, object]:
    """Calibrate a ranker and produce leave-one-area-out transfer predictions."""
    settings = (objective or TransferObjective()).normalized()
    annotated = attach_field_utility(
        candidates,
        detections,
        candidate_area_col=area_col,
        detection_area_col=detection_area_col,
    )
    ranked, available_specs = add_within_area_rank_features(
        annotated,
        area_col=area_col,
        feature_specs=feature_specs or DEFAULT_FIELD_FEATURE_SPECS,
    )
    excluded = {str(name) for name in excluded_features}
    feature_names = [name for name in available_specs if name not in excluded]
    if not feature_names:
        raise ValueError("No transfer-ranking features remain after exclusions")
    configurations = enumerate_rank_configurations(feature_names, maximum_features=maximum_features)
    areas = sorted(
        set(ranked[area_col].dropna()).intersection(set(detections[detection_area_col].dropna())),
        key=str,
    )
    if len(areas) < 3:
        raise ValueError("At least three shared survey areas are required")

    search_rows = []
    for configuration in configurations:
        metrics = configuration_objective(
            ranked,
            configuration,
            areas,
            objective=settings,
            area_col=area_col,
        )
        search_rows.append({
            **configuration.as_dict(),
            **metrics,
            "n_features": len(configuration.feature_names),
        })
    search = pd.DataFrame(search_rows).sort_values(
        [
            "transfer_objective",
            "mean_area_pairwise_concordance",
            "mean_area_selected_utility",
            "n_features",
            "config_id",
        ],
        ascending=[False, False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    first = search.iloc[0]
    final_configuration = RankConfiguration(
        tuple(first["feature_names"]),
        tuple(float(value) for value in first["weights"]),
    )

    outer_rows = []
    outer_rules = []
    for held_area in areas:
        training_areas = [area for area in areas if area != held_area]
        chosen, training_metrics = _choose_configuration(
            ranked,
            configurations,
            training_areas,
            objective=settings,
            area_col=area_col,
        )
        held = ranked[ranked[area_col].eq(held_area)]
        selected = select_one_per_area(
            apply_rank_configuration(held, chosen),
            area_col=area_col,
        ).iloc[0].to_dict()
        selected["held_out_area"] = held_area
        selected["training_transfer_objective"] = training_metrics["transfer_objective"]
        outer_rows.append(selected)
        outer_rules.append({
            "held_out_area": held_area,
            **chosen.as_dict(),
            **training_metrics,
        })

    final_scored = apply_rank_configuration(ranked, final_configuration)
    final_selected = select_one_per_area(final_scored, area_col=area_col)
    outer_selected = pd.DataFrame(outer_rows).reset_index(drop=True)
    return {
        "annotated_candidates": final_scored,
        "configuration_search": search,
        "outer_selections": outer_selected,
        "outer_configurations": pd.DataFrame(outer_rules),
        "final_selections": final_selected,
        "final_configuration": final_configuration,
        "available_feature_specs": {name: available_specs[name] for name in feature_names},
        "excluded_features": sorted(excluded),
        "objective": settings,
        "outer_cv_metrics": recovery_metrics(
            outer_selected,
            detections,
            candidate_area_col=area_col,
            detection_area_col=detection_area_col,
        ),
        "development_metrics": recovery_metrics(
            final_selected,
            detections,
            candidate_area_col=area_col,
            detection_area_col=detection_area_col,
        ),
    }
