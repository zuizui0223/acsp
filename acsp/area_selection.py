"""Area-aware complementary selection for multi-region survey designs."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_008.8


def _haversine_m(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    lat1, lon1 = math.radians(float(lat)), math.radians(float(lon))
    lat2, lon2 = np.radians(lats.astype(float)), np.radians(lons.astype(float))
    a = (
        np.sin((lat2 - lat1) / 2.0) ** 2
        + math.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def select_area_balanced_candidates(
    candidates: pd.DataFrame,
    k: int,
    *,
    score_col: str = "integrated_support_score",
    area_col: str = "survey_area_id",
    evidence_weight: float = 0.25,
    separation_scale_m: float = 25_000.0,
    cover_areas_first: bool = True,
) -> pd.DataFrame:
    """Select a fixed-size candidate set while respecting declared survey areas.

    When ``cover_areas_first`` is true and the budget is at least the number of
    non-empty survey areas, the greedy selector must represent every area before
    adding a second candidate to any area. This is a set-design constraint, not a
    species-specific rule. Candidate evidence and geographic complementarity are
    otherwise combined exactly as in the ordinary complementary selector.
    """
    if candidates is None or candidates.empty:
        return pd.DataFrame() if candidates is None else candidates.copy()
    required = {"latitude", "longitude", score_col}
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"Candidate table is missing: {', '.join(sorted(missing))}")

    work = candidates.copy().reset_index(drop=True)
    work["latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    work = work.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    if work.empty:
        return work
    if area_col not in work.columns:
        work[area_col] = "all"
    work[area_col] = work[area_col].astype(str)

    scores = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0).clip(0.0, 1.0).to_numpy(float)
    lats = work["latitude"].to_numpy(float)
    lons = work["longitude"].to_numpy(float)
    areas = work[area_col].to_numpy(str)
    weight = float(np.clip(evidence_weight, 0.0, 1.0))
    scale = max(1.0, float(separation_scale_m))
    limit = min(max(1, int(k)), len(work))
    distinct_areas = list(dict.fromkeys(areas.tolist()))
    enforce_all_areas = bool(cover_areas_first and limit >= len(distinct_areas))

    selected: list[int] = []
    utilities: list[float] = []
    represented: set[str] = set()
    while len(selected) < limit:
        uncovered = set(distinct_areas).difference(represented) if enforce_all_areas else set()
        best: tuple[float, float, int] | None = None
        for index in range(len(work)):
            if index in selected:
                continue
            if uncovered and areas[index] not in uncovered:
                continue
            if selected:
                nearest = float(
                    np.min(_haversine_m(lats[index], lons[index], lats[selected], lons[selected]))
                )
                representation = 1.0 - math.exp(-nearest / scale)
            else:
                representation = 0.5
            utility = weight * scores[index] + (1.0 - weight) * representation
            key = (utility, scores[index], -index)
            if best is None or key > best:
                best = key
        if best is None:
            break
        chosen = -int(best[2])
        selected.append(chosen)
        represented.add(str(areas[chosen]))
        utilities.append(float(best[0]))

    out = work.iloc[selected].copy().reset_index(drop=True)
    out["area_balanced_selection_rank"] = range(1, len(out) + 1)
    out["area_balanced_selection_utility"] = np.round(utilities, 6)
    out["area_coverage_required"] = enforce_all_areas
    out["area_balanced_selection_policy"] = (
        f"{weight:.2f} evidence + {1.0 - weight:.2f} geographic complementarity; "
        f"cover declared {area_col} values before duplicates={enforce_all_areas}"
    )
    return out
