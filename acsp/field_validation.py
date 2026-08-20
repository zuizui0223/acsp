"""Prospective field-validation helpers for ACSP recommendations.

These functions evaluate whether a frozen recommendation set recovers
independent field detections. Positive-only locations do not identify absence,
occupancy, or detection probability. Multi-area recovery is always evaluated
within the same declared survey area; detections may never be recovered by a
candidate on another island/area.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
import math

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_008.8
DEFAULT_RECOVERY_RADII_KM = (0.5, 1.0, 2.0, 5.0, 10.0)


def haversine_distance_m(lat: float, lon: float, other_lats: np.ndarray, other_lons: np.ndarray) -> np.ndarray:
    lat1, lon1 = math.radians(float(lat)), math.radians(float(lon))
    lat2, lon2 = np.radians(np.asarray(other_lats, dtype=float)), np.radians(np.asarray(other_lons, dtype=float))
    a = np.sin((lat2-lat1)/2.0)**2 + math.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2.0)**2
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def normalize_field_locations(locations: pd.DataFrame, *, island_col: str="island", latitude_col: str="latitude", longitude_col: str="longitude") -> pd.DataFrame:
    missing = {island_col, latitude_col, longitude_col}.difference(locations.columns)
    if missing:
        raise ValueError(f"Missing field-location columns: {', '.join(sorted(missing))}")
    out = locations.copy().reset_index(drop=True)
    out[island_col] = out[island_col].replace(r"^\s*$", np.nan, regex=True).ffill()
    if out[island_col].isna().any():
        raise ValueError("The first field-location row must contain an island/area label.")
    out[latitude_col] = pd.to_numeric(out[latitude_col], errors="coerce")
    out[longitude_col] = pd.to_numeric(out[longitude_col], errors="coerce")
    if out[[latitude_col, longitude_col]].isna().any().any():
        raise ValueError("Field locations contain non-numeric coordinates.")
    if not out[latitude_col].between(-90, 90).all() or not out[longitude_col].between(-180, 180).all():
        raise ValueError("Field locations contain coordinates outside valid bounds.")
    out[island_col] = out[island_col].astype(str).str.strip().str.lower()
    out["field_row_id"] = np.arange(1, len(out)+1)
    return out


def cluster_field_detections(locations: pd.DataFrame, *, cluster_radius_m: float=500.0, area_col: str="island", latitude_col: str="latitude", longitude_col: str="longitude") -> tuple[pd.DataFrame, pd.DataFrame]:
    work = normalize_field_locations(locations, island_col=area_col, latitude_col=latitude_col, longitude_col=longitude_col)
    radius = max(0.0, float(cluster_radius_m))
    assigned = np.full(len(work), -1, dtype=int)
    clusters, next_cluster = [], 1
    for area, group in work.groupby(area_col, sort=True):
        positions = group.index.to_numpy(dtype=int)
        lats, lons = group[latitude_col].to_numpy(float), group[longitude_col].to_numpy(float)
        adjacency = np.vstack([haversine_distance_m(lats[i], lons[i], lats, lons) <= radius for i in range(len(group))])
        unvisited = set(range(len(group)))
        while unvisited:
            seed = min(unvisited); stack=[seed]; members=[]; unvisited.remove(seed)
            while stack:
                cur=stack.pop(); members.append(cur)
                for j in [j for j in sorted(unvisited) if adjacency[cur,j]]:
                    unvisited.remove(j); stack.append(j)
            sums=[float(haversine_distance_m(lats[i], lons[i], lats[members], lons[members]).sum()) for i in members]
            medoid=members[int(np.argmin(sums))]; global_pos=positions[members]; assigned[global_pos]=next_cluster
            clusters.append({"detection_cluster_id":next_cluster, area_col:area, latitude_col:float(lats[medoid]), longitude_col:float(lons[medoid]), "n_source_points":len(members), "source_field_row_ids":";".join(str(int(v)) for v in work.loc[global_pos,"field_row_id"]), "cluster_radius_m":radius})
            next_cluster += 1
    rows=work.copy(); rows["detection_cluster_id"]=assigned
    return rows, pd.DataFrame(clusters)


def _valid_points(frame: pd.DataFrame, latitude_col: str, longitude_col: str, label: str) -> pd.DataFrame:
    missing={latitude_col, longitude_col}.difference(frame.columns)
    if missing: raise ValueError(f"Missing {label} columns: {', '.join(sorted(missing))}")
    out=frame.copy().reset_index(drop=True)
    out[latitude_col]=pd.to_numeric(out[latitude_col],errors="coerce"); out[longitude_col]=pd.to_numeric(out[longitude_col],errors="coerce")
    out=out.dropna(subset=[latitude_col,longitude_col]).reset_index(drop=True)
    if out.empty: raise ValueError(f"No valid {label} coordinates were supplied.")
    return out


def _norm_area(value: object) -> str:
    return str(value).strip().lower()


def detection_recovery_table(selected_candidates: pd.DataFrame, detection_clusters: pd.DataFrame, *, radii_km: Sequence[float]=DEFAULT_RECOVERY_RADII_KM, candidate_id_col: str="site_id", area_col: str="survey_area_id", detection_area_col: str="island") -> pd.DataFrame:
    """Measure recovery, forbidding cross-area nearest-neighbour matches."""
    candidates=_valid_points(selected_candidates,"latitude","longitude","candidate")
    detections=_valid_points(detection_clusters,"latitude","longitude","detection")
    has_candidate_area=area_col in candidates.columns
    candidate_areas = candidates[area_col].map(_norm_area) if has_candidate_area else pd.Series("__all__", index=candidates.index)
    multiple_areas = has_candidate_area and candidate_areas.nunique(dropna=False) > 1
    if multiple_areas and detection_area_col not in detections.columns:
        raise ValueError(f"Multi-area recovery requires detection area column {detection_area_col!r}; cross-area matching is forbidden.")
    rows=[]
    for _, detection in detections.iterrows():
        if has_candidate_area and detection_area_col in detections.columns:
            area=_norm_area(detection[detection_area_col]); eligible=candidates.loc[candidate_areas.eq(area)].copy()
        else:
            area=None; eligible=candidates
        row=detection.to_dict()
        if eligible.empty:
            row.update({"nearest_candidate_id":None,"nearest_candidate_distance_km":float("inf"),"nearest_candidate_area":None})
            for radius in radii_km: row[f"recovered_{float(radius):g}km"]=False
            rows.append(row); continue
        distances=haversine_distance_m(float(detection["latitude"]),float(detection["longitude"]),eligible["latitude"].to_numpy(float),eligible["longitude"].to_numpy(float))
        pos=int(np.argmin(distances)); nearest=eligible.iloc[pos]
        row["nearest_candidate_id"]=nearest.get(candidate_id_col, eligible.index[pos]+1)
        row["nearest_candidate_distance_km"]=float(distances[pos]/1000.0)
        if has_candidate_area: row["nearest_candidate_area"]=nearest.get(area_col)
        for radius in radii_km: row[f"recovered_{float(radius):g}km"]=bool(distances[pos] <= float(radius)*1000.0)
        rows.append(row)
    return pd.DataFrame(rows)


def recovery_summary(recovery: pd.DataFrame, *, radii_km: Sequence[float]=DEFAULT_RECOVERY_RADII_KM) -> pd.DataFrame:
    if recovery.empty: return pd.DataFrame()
    distances=pd.to_numeric(recovery["nearest_candidate_distance_km"],errors="coerce")
    rows=[]
    for radius in radii_km:
        values=recovery[f"recovered_{float(radius):g}km"].astype(bool)
        rows.append({"radius_km":float(radius),"n_detection_clusters":len(recovery),"n_recovered":int(values.sum()),"detection_recall":float(values.mean()),"median_nearest_candidate_km":float(distances.median()),"max_nearest_candidate_km":float(distances.max())})
    return pd.DataFrame(rows)


def stratified_random_recovery_benchmark(candidate_pool: pd.DataFrame, selected_candidate_ids: Iterable[object], detection_clusters: pd.DataFrame, *, radii_km: Sequence[float]=DEFAULT_RECOVERY_RADII_KM, iterations: int=10_000, seed: int=20260715, candidate_id_col: str="site_id", area_col: str="survey_area_id", detection_area_col: str="island") -> tuple[pd.DataFrame,pd.DataFrame]:
    pool=_valid_points(candidate_pool,"latitude","longitude","candidate")
    if candidate_id_col not in pool.columns: raise ValueError(f"Candidate pool is missing {candidate_id_col}.")
    selected_ids=set(selected_candidate_ids); selected=pool[pool[candidate_id_col].isin(selected_ids)].copy()
    if len(selected)!=len(selected_ids): raise ValueError("Selected candidate IDs missing from pool.")
    quotas=selected.groupby(area_col,dropna=False).size().astype(int).to_dict() if area_col in pool.columns else {"__all__":len(selected)}
    def summarize(frame):
        return recovery_summary(detection_recovery_table(frame,detection_clusters,radii_km=radii_km,candidate_id_col=candidate_id_col,area_col=area_col,detection_area_col=detection_area_col),radii_km=radii_km)
    observed=summarize(selected).set_index("radius_km")
    rng=np.random.default_rng(int(seed)); random_rows=[]; total=max(1,int(iterations))
    for iteration in range(1,total+1):
        parts=[]
        if area_col in pool.columns and "__all__" not in quotas:
            for area,quota in quotas.items():
                area_pool=pool[pool[area_col].eq(area)]
                if len(area_pool)<int(quota): raise ValueError(f"Area {area!r} has {len(area_pool)} candidates but quota is {quota}.")
                parts.append(area_pool.iloc[rng.choice(len(area_pool),size=int(quota),replace=False)])
        else:
            quota=int(quotas["__all__"]); parts.append(pool.iloc[rng.choice(len(pool),size=quota,replace=False)])
        for row in summarize(pd.concat(parts,ignore_index=True)).itertuples(index=False):
            random_rows.append({"iteration":iteration,"radius_km":float(row.radius_km),"random_detection_recall":float(row.detection_recall)})
    draws=pd.DataFrame(random_rows); out=[]
    for radius,group in draws.groupby("radius_km",sort=True):
        obs=float(observed.loc[radius,"detection_recall"]); vals=group["random_detection_recall"].to_numpy(float)
        out.append({"radius_km":float(radius),"acsp_detection_recall":obs,"random_mean_recall":float(vals.mean()),"random_q025":float(np.quantile(vals,.025)),"random_q975":float(np.quantile(vals,.975)),"lift_over_random":obs-float(vals.mean()),"randomization_p_one_sided":float((1+np.sum(vals>=obs))/(len(vals)+1)),"iterations":total,"seed":int(seed)})
    return pd.DataFrame(out), draws
