"""Transparent candidate recommendation helpers."""

from __future__ import annotations

from collections.abc import Sequence
import math
import re

import numpy as np
import pandas as pd


EARTH_RADIUS_M = 6_371_008.8


def _haversine_m(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    lat1, lon1 = math.radians(float(lat)), math.radians(float(lon))
    lat2, lon2 = np.radians(lats.astype(float)), np.radians(lons.astype(float))
    a = np.sin((lat2 - lat1) / 2.0) ** 2 + math.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _unit_series(frame: pd.DataFrame, columns: Sequence[str], default: float = 0.0) -> pd.Series:
    available = [column for column in columns if column in frame.columns]
    if not available:
        return pd.Series(default, index=frame.index, dtype=float)
    values = frame[available].apply(pd.to_numeric, errors="coerce").max(axis=1, skipna=True)
    finite = values[np.isfinite(values)]
    if finite.empty:
        return pd.Series(default, index=frame.index, dtype=float)
    if float(finite.min()) >= 0.0 and float(finite.max()) <= 1.0:
        return values.fillna(default).clip(0.0, 1.0)
    span = float(finite.max() - finite.min())
    if span <= 1e-12:
        return values.notna().astype(float) * 0.5
    return ((values - float(finite.min())) / span).fillna(default).clip(0.0, 1.0)


def _plain_role(candidate_type: object) -> str:
    value = str(candidate_type or "").lower()
    if "model-only" in value or "sdm-high" in value or "ssdm-high" in value:
        return "Model-led exploration zone"
    if "environmental-test" in value or "environmental contrast" in value or "boundary" in value:
        return "Range-boundary comparison zone"
    if "survey-gap" in value or "under-surveyed" in value:
        return "Under-sampled verification zone"
    if "habitat" in value or "analogue" in value:
        return "Similar-habitat zone"
    if "occurrence" in value or "known" in value:
        return "Known-location zone"
    return "Survey evidence zone"


def aggregate_candidates_to_zones(
    candidates: pd.DataFrame,
    merge_distance_m: float | None = None,
    area_col: str = "survey_area_id",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    id_col: str = "site_id",
    score_col: str = "priority_score",
) -> pd.DataFrame:
    """Aggregate nearby candidates using deterministic complete-link zones.

    A point joins a zone only when it lies within the merge threshold of every
    existing member.  This deliberately prevents single-link chain artifacts.
    Zone scores use maxima of independent evidence components, never member
    counts, so dense candidate grids do not gain priority merely by density.
    """
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    required = {latitude_col, longitude_col, id_col, score_col}
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"Missing zone columns: {', '.join(sorted(missing))}")
    work = candidates.copy().reset_index(drop=True)
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if work.empty:
        return pd.DataFrame()
    if area_col not in work.columns:
        work[area_col] = 1
    work["_priority_unit"] = _unit_series(work, [score_col])
    work["_observed_support"] = _unit_series(work, ["occurrence_support_score", "observed_base_priority_score"])
    work["_local_support"] = _unit_series(work, ["analogue_score", "habitat_score", "environmental_similarity", "survey_gap_score"])
    work["_model_support"] = _unit_series(work, ["model_support_score", "sdm_suitability", "ssdm_predicted_richness"])
    work["_access_support"] = _unit_series(work, ["access_score", "accessibility_score"], default=0.5)
    work["_representative_score"] = (
        0.50 * work["_priority_unit"] + 0.15 * work["_observed_support"]
        + 0.15 * work["_local_support"] + 0.10 * work["_model_support"]
        + 0.10 * work["_access_support"]
    )
    assignments: dict[int, tuple[object, int]] = {}
    zone_members: dict[tuple[object, int], list[int]] = {}
    for area, group in work.groupby(area_col, sort=True, dropna=False):
        radius = pd.to_numeric(group.get("search_cell_radius_m", pd.Series(dtype=float)), errors="coerce").dropna()
        threshold = float(merge_distance_m) if merge_distance_m is not None else (
            float(np.clip(2.0 * radius.median(), 250.0, 5_000.0)) if not radius.empty else 1_000.0
        )
        ordered = group.assign(
            _stable_numeric=pd.to_numeric(group[id_col], errors="coerce"),
            _stable_id=group[id_col].astype(str),
        ).sort_values(
            ["_stable_numeric", "_stable_id", latitude_col, longitude_col], kind="mergesort", na_position="last"
        )
        area_zones: list[list[int]] = []
        for index in ordered.index:
            compatible: list[tuple[float, int]] = []
            for zone_index, member_indices in enumerate(area_zones):
                members = work.loc[member_indices]
                distances = _haversine_m(
                    work.at[index, latitude_col], work.at[index, longitude_col],
                    members[latitude_col].to_numpy(float), members[longitude_col].to_numpy(float),
                )
                maximum = float(distances.max()) if len(distances) else 0.0
                if maximum <= threshold:
                    compatible.append((maximum, zone_index))
            if compatible:
                zone_index = min(compatible)[1]
                area_zones[zone_index].append(index)
            else:
                zone_index = len(area_zones)
                area_zones.append([index])
            assignments[index] = (area, zone_index + 1)
        for zone_index, indices in enumerate(area_zones, start=1):
            zone_members[(area, zone_index)] = indices

    rows: list[dict[str, object]] = []
    for (area, zone_number), indices in zone_members.items():
        members = work.loc[indices].copy()
        representative = members.sort_values(
            ["_representative_score", "_access_support", "_priority_unit", id_col],
            ascending=[False, False, False, True], kind="mergesort",
        ).iloc[0]
        distances = _haversine_m(
            representative[latitude_col], representative[longitude_col],
            members[latitude_col].to_numpy(float), members[longitude_col].to_numpy(float),
        )
        observed = float(members["_observed_support"].max())
        local = float(members["_local_support"].max())
        model = float(members["_model_support"].max())
        access = float(members["_access_support"].max())
        priority = float(members["_priority_unit"].max())
        zone_score = 0.45 * priority + 0.20 * observed + 0.15 * local + 0.15 * model + 0.05 * access
        roles = sorted({_plain_role(value) for value in members.get("candidate_type", pd.Series("", index=members.index))})
        safe_area = re.sub(r"[^A-Za-z0-9_-]+", "-", str(area)).strip("-") or "1"
        row = {
            "zone_id": f"{safe_area}-Z{zone_number:03d}",
            area_col: area,
            "zone_score": round(zone_score, 6),
            "zone_member_count": int(len(members)),
            "zone_radius_m": round(float(distances.max()) if len(distances) else 0.0, 1),
            "representative_site_id": representative[id_col],
            "latitude": float(representative[latitude_col]),
            "longitude": float(representative[longitude_col]),
            "zone_candidate_roles": "; ".join(roles),
            "primary_zone_role": _plain_role(representative.get("candidate_type", "")),
            "zone_evidence_summary": (
                f"Observed {observed:.2f}; local habitat {local:.2f}; model {model:.2f}; "
                f"access {access:.2f}; {len(members)} candidate point(s)."
            ),
            "observed_support_score": round(observed, 6),
            "local_habitat_support_score": round(local, 6),
            "model_support_score": round(model, 6),
            "access_support_score": round(access, 6),
            "zone_member_site_ids": ";".join(members[id_col].astype(str).tolist()),
        }
        rows.append(row)
    zones = pd.DataFrame(rows).sort_values(["zone_score", "zone_id"], ascending=[False, True]).reset_index(drop=True)
    zones["zone_rank"] = range(1, len(zones) + 1)
    zones["initial_rank"] = zones["zone_rank"]
    zones["model_rank"] = pd.NA
    zones["rank_change"] = pd.NA
    zones["agreement_score"] = pd.NA
    zones["agreement_class"] = "Model not run"
    return zones


def compare_zone_rankings(initial_zones: pd.DataFrame, model_zones: pd.DataFrame) -> pd.DataFrame:
    """Attach before/after rank changes and conservative agreement classes."""
    if model_zones is None or model_zones.empty:
        return initial_zones.copy()
    initial_rank = initial_zones.set_index("zone_id")["zone_rank"] if initial_zones is not None and not initial_zones.empty else pd.Series(dtype=float)
    out = model_zones.copy()
    out["initial_rank"] = out["zone_id"].map(initial_rank)
    out["model_rank"] = out["zone_rank"].astype(int)
    out["rank_change"] = pd.to_numeric(out["initial_rank"], errors="coerce") - out["model_rank"]
    observed = pd.to_numeric(out["observed_support_score"], errors="coerce").fillna(0.0).clip(0, 1)
    local = pd.to_numeric(out["local_habitat_support_score"], errors="coerce").fillna(0.0).clip(0, 1)
    model = pd.to_numeric(out["model_support_score"], errors="coerce").fillna(0.0).clip(0, 1)
    local_evidence = pd.concat([observed, local], axis=1).max(axis=1)
    out["agreement_score"] = np.where(
        local_evidence.add(model).gt(0), 2 * local_evidence * model / (local_evidence + model), 0.0
    ).round(6)
    out["agreement_class"] = np.select(
        [
            local_evidence.ge(0.5) & model.ge(0.5),
            local_evidence.ge(model),
            model.gt(local_evidence),
        ],
        ["Concordant — highest priority", "Local evidence first", "Model-led exploration"],
        default="Local evidence first",
    )
    return out


def zone_agreement_summary(zones: pd.DataFrame, top_n: int = 8) -> dict[str, object]:
    """Return compact model-agreement counts and rank correlation."""
    if zones is None or zones.empty or "agreement_class" not in zones.columns:
        return {"model_run": False, "zone_count": 0}
    top = zones.sort_values("model_rank", na_position="last").head(int(top_n))
    counts = top["agreement_class"].value_counts().to_dict()
    common = zones.dropna(subset=["initial_rank", "model_rank"])
    correlation = common["initial_rank"].corr(common["model_rank"], method="spearman") if len(common) >= 2 else np.nan
    return {
        "model_run": not top["agreement_class"].eq("Model not run").all(),
        "zone_count": int(len(zones)),
        "top_zone_count": int(len(top)),
        "concordant_top_zones": int(counts.get("Concordant — highest priority", 0)),
        "local_evidence_first_top_zones": int(counts.get("Local evidence first", 0)),
        "model_led_top_zones": int(counts.get("Model-led exploration", 0)),
        "initial_model_rank_spearman": None if pd.isna(correlation) else round(float(correlation), 4),
    }


def recommend_survey_zones(
    candidates: pd.DataFrame,
    per_area: int = 3,
    default_total: int = 8,
    merge_distance_m: float | None = None,
    area_col: str = "survey_area_id",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    id_col: str = "site_id",
    score_col: str = "priority_score",
) -> pd.DataFrame:
    """Aggregate candidates, then apply recommendation quotas to survey zones."""
    zones = aggregate_candidates_to_zones(
        candidates, merge_distance_m=merge_distance_m, area_col=area_col,
        latitude_col=latitude_col, longitude_col=longitude_col,
        id_col=id_col, score_col=score_col,
    )
    if zones.empty:
        return zones
    selected = recommend_candidates(
        zones, per_area=per_area, default_total=default_total, area_col=area_col,
        score_col="zone_score", id_col="zone_id",
    )
    return selected.rename(columns={"recommendation_rank": "recommended_zone_rank"})


def normalize_extent(extent: Sequence[float]) -> tuple[float, float, float, float]:
    """Validate an extent ordered as west, south, east, north."""
    if len(extent) != 4:
        raise ValueError("Extent must contain west, south, east, north.")
    west, south, east, north = (float(value) for value in extent)
    if not np.isfinite([west, south, east, north]).all():
        raise ValueError("Extent coordinates must be finite numbers.")
    if west >= east or south >= north:
        raise ValueError("Extent must satisfy west < east and south < north.")
    return west, south, east, north


def filter_candidates_to_extent(
    candidates: pd.DataFrame,
    extent: Sequence[float],
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
) -> pd.DataFrame:
    """Keep candidate points inside an inclusive rectangular extent."""
    missing = {latitude_col, longitude_col}.difference(candidates.columns)
    if missing:
        raise ValueError(f"Missing coordinate columns: {', '.join(sorted(missing))}")
    west, south, east, north = normalize_extent(extent)
    latitude = pd.to_numeric(candidates[latitude_col], errors="coerce")
    longitude = pd.to_numeric(candidates[longitude_col], errors="coerce")
    inside = latitude.between(south, north) & longitude.between(west, east)
    return candidates.loc[inside].copy().reset_index(drop=True)


def recommend_candidates(
    candidates: pd.DataFrame,
    per_area: int = 3,
    default_total: int = 8,
    area_col: str = "survey_area_id",
    score_col: str = "priority_score",
    id_col: str = "site_id",
    extent: Sequence[float] | None = None,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
) -> pd.DataFrame:
    """Select top-ranked candidates, with an equal quota across multiple areas."""
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    required = {score_col, id_col}
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"Missing candidate columns: {', '.join(sorted(missing))}")
    if extent is not None:
        candidates = filter_candidates_to_extent(candidates, extent, latitude_col, longitude_col)
    ranked = candidates.sort_values([score_col, id_col], ascending=[False, True]).copy()
    if area_col in ranked.columns and ranked[area_col].nunique() > 1:
        selected = ranked.groupby(area_col, group_keys=False).head(int(per_area)).copy()
        selected = selected.sort_values([area_col, score_col], ascending=[True, False])
    else:
        selected = ranked.head(int(default_total)).copy()
    selected["recommendation_rank"] = range(1, len(selected) + 1)
    return selected.reset_index(drop=True)
