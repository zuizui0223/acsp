"""Corridor evidence separating known anchors from candidate patches."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .gap_patches import haversine_distance_m


@dataclass(frozen=True)
class CorridorBarrierConfig:
    """Technical settings for sampling support along an anchor-patch transect."""

    sample_spacing_m: float = 250.0
    interpolation_radius_m: float = 750.0
    low_support_threshold: float = 0.35
    min_barrier_length_m: float = 750.0
    min_coverage_fraction: float = 0.75

    def validate(self) -> None:
        if self.sample_spacing_m <= 0 or self.interpolation_radius_m <= 0:
            raise ValueError("sample spacing and interpolation radius must be positive")
        if not 0.0 <= self.low_support_threshold <= 1.0:
            raise ValueError("low_support_threshold must lie in [0, 1]")
        if self.min_barrier_length_m < 0:
            raise ValueError("min_barrier_length_m must be non-negative")
        if not 0.0 <= self.min_coverage_fraction <= 1.0:
            raise ValueError("min_coverage_fraction must lie in [0, 1]")


def _nearest_pair(
    patch: pd.DataFrame,
    known: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, float]:
    known_lats = known["latitude"].to_numpy(float)
    known_lons = known["longitude"].to_numpy(float)
    best: tuple[float, int, int] | None = None
    for patch_index, row in patch[["latitude", "longitude"]].iterrows():
        distances = haversine_distance_m(row.latitude, row.longitude, known_lats, known_lons)
        known_position = int(np.argmin(distances))
        key = (float(distances[known_position]), int(patch_index), known_position)
        if best is None or key < best:
            best = key
    assert best is not None
    distance, patch_index, known_position = best
    return patch.loc[patch_index], known.iloc[known_position], distance


def _transect_points(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    spacing_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    distance_m = float(
        haversine_distance_m(start_lat, start_lon, np.array([end_lat]), np.array([end_lon]))[0]
    )
    count = max(2, int(math.ceil(distance_m / spacing_m)) + 1)
    fractions = np.linspace(0.0, 1.0, count)
    return (
        start_lat + fractions * (end_lat - start_lat),
        start_lon + fractions * (end_lon - start_lon),
        fractions * distance_m,
    )


def corridor_support_profile(
    candidates: pd.DataFrame,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    support_col: str = "integrated_support_score",
    config: CorridorBarrierConfig | None = None,
) -> pd.DataFrame:
    """Sample candidate support along an anchor-patch transect.

    Positions without a candidate inside the interpolation radius remain missing.
    They are evidence gaps, not ecological low-support observations.
    """
    cfg = config or CorridorBarrierConfig()
    cfg.validate()
    required = {"latitude", "longitude", support_col}
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"candidates is missing columns: {', '.join(sorted(missing))}")
    pool = candidates.copy().dropna(subset=["latitude", "longitude", support_col]).reset_index(drop=True)
    pool[support_col] = pd.to_numeric(pool[support_col], errors="coerce").clip(0.0, 1.0)
    pool = pool.dropna(subset=[support_col]).reset_index(drop=True)
    sample_lats, sample_lons, along_m = _transect_points(*start, *end, cfg.sample_spacing_m)
    pool_lats = pool["latitude"].to_numpy(float)
    pool_lons = pool["longitude"].to_numpy(float)
    support: list[float] = []
    nearest_candidate_m: list[float] = []
    sampled: list[bool] = []
    for latitude, longitude in zip(sample_lats, sample_lons):
        if pool.empty:
            nearest = math.inf
            value = math.nan
            available = False
        else:
            distances = haversine_distance_m(latitude, longitude, pool_lats, pool_lons)
            position = int(np.argmin(distances))
            nearest = float(distances[position])
            available = nearest <= cfg.interpolation_radius_m
            value = float(pool.iloc[position][support_col]) if available else math.nan
        support.append(value)
        nearest_candidate_m.append(nearest)
        sampled.append(available)
    profile = pd.DataFrame({
        "transect_distance_m": along_m,
        "latitude": sample_lats,
        "longitude": sample_lons,
        "corridor_support": support,
        "nearest_candidate_m": nearest_candidate_m,
        "support_sample_available": sampled,
    })
    profile["low_support"] = (
        profile["support_sample_available"]
        & profile["corridor_support"].lt(cfg.low_support_threshold)
    )
    profile["support_gap"] = ~profile["support_sample_available"]
    return profile


def _longest_run_m(positions: np.ndarray, mask: np.ndarray) -> float:
    longest = 0.0
    run_start: float | None = None
    for position, active in zip(positions, mask):
        if active and run_start is None:
            run_start = float(position)
        elif not active and run_start is not None:
            longest = max(longest, float(position) - run_start)
            run_start = None
    if run_start is not None and len(positions):
        longest = max(longest, float(positions[-1]) - run_start)
    return longest


def summarize_corridor_barrier(
    profile: pd.DataFrame,
    *,
    config: CorridorBarrierConfig | None = None,
) -> dict[str, float | bool | str]:
    """Summarize observed low support separately from missing corridor evidence."""
    cfg = config or CorridorBarrierConfig()
    cfg.validate()
    if profile is None or profile.empty:
        return {
            "corridor_length_m": 0.0,
            "corridor_coverage_fraction": 0.0,
            "corridor_low_support_fraction_observed": 0.0,
            "corridor_longest_low_support_m": 0.0,
            "corridor_longest_support_gap_m": 0.0,
            "corridor_support_mean_observed": math.nan,
            "corridor_evidence_sufficient": False,
            "corridor_barrier_present": False,
            "corridor_evidence_class": "insufficient_corridor_evidence",
        }
    ordered = profile.sort_values("transect_distance_m").reset_index(drop=True)
    positions = ordered["transect_distance_m"].to_numpy(float)
    available = ordered["support_sample_available"].astype(bool).to_numpy()
    low = ordered["low_support"].astype(bool).to_numpy()
    gaps = ~available
    coverage = float(available.mean())
    observed_low_fraction = float(low[available].mean()) if available.any() else 0.0
    longest_low = _longest_run_m(positions, low)
    longest_gap = _longest_run_m(positions, gaps)
    evidence_sufficient = coverage >= cfg.min_coverage_fraction
    barrier_present = evidence_sufficient and longest_low >= cfg.min_barrier_length_m
    if not evidence_sufficient:
        evidence_class = "insufficient_corridor_evidence"
    elif barrier_present:
        evidence_class = "observed_low_support_barrier"
    else:
        evidence_class = "observed_continuous_or_short_gap"
    return {
        "corridor_length_m": float(positions[-1]) if len(positions) else 0.0,
        "corridor_coverage_fraction": coverage,
        "corridor_low_support_fraction_observed": observed_low_fraction,
        "corridor_longest_low_support_m": longest_low,
        "corridor_longest_support_gap_m": longest_gap,
        "corridor_support_mean_observed": float(
            ordered.loc[ordered["support_sample_available"], "corridor_support"].mean()
        ) if available.any() else math.nan,
        "corridor_evidence_sufficient": bool(evidence_sufficient),
        "corridor_barrier_present": bool(barrier_present),
        "corridor_evidence_class": evidence_class,
    }


def annotate_gap_patch_barriers(
    candidates: pd.DataFrame,
    patch_members: pd.DataFrame,
    known_occurrences: pd.DataFrame,
    *,
    support_col: str = "integrated_support_score",
    config: CorridorBarrierConfig | None = None,
) -> pd.DataFrame:
    """Attach corridor-derived ecological-gap evidence to every patch member."""
    if patch_members is None or patch_members.empty:
        return pd.DataFrame()
    required = {"gap_patch_id", "latitude", "longitude"}
    missing = required.difference(patch_members.columns)
    if missing:
        raise ValueError(f"patch_members is missing columns: {', '.join(sorted(missing))}")
    known = known_occurrences.dropna(subset=["latitude", "longitude"]).copy().reset_index(drop=True)
    if known.empty:
        raise ValueError("known_occurrences must contain at least one valid location")
    cfg = config or CorridorBarrierConfig()
    summaries: list[dict[str, object]] = []
    for patch_id, patch in patch_members.groupby("gap_patch_id", sort=True):
        patch_point, known_point, nearest_m = _nearest_pair(patch, known)
        profile = corridor_support_profile(
            candidates,
            (float(known_point.latitude), float(known_point.longitude)),
            (float(patch_point.latitude), float(patch_point.longitude)),
            support_col=support_col,
            config=cfg,
        )
        summary = summarize_corridor_barrier(profile, config=cfg)
        summary.update({
            "gap_patch_id": patch_id,
            "corridor_anchor_latitude": float(known_point.latitude),
            "corridor_anchor_longitude": float(known_point.longitude),
            "corridor_patch_latitude": float(patch_point.latitude),
            "corridor_patch_longitude": float(patch_point.longitude),
            "corridor_nearest_known_m": float(nearest_m),
        })
        summaries.append(summary)
    summary_frame = pd.DataFrame(summaries)
    out = patch_members.merge(summary_frame, on="gap_patch_id", how="left", validate="many_to_one")
    out["gap_patch_ecological_class"] = np.select(
        [
            out["gap_patch_class"].eq("anchor_expansion"),
            ~out["corridor_evidence_sufficient"].astype(bool),
            out["corridor_barrier_present"].astype(bool),
        ],
        [
            "continuous_anchor_extension",
            "insufficient_corridor_evidence",
            "barrier_separated_patch",
        ],
        default="distance_separated_without_barrier",
    )
    return out
