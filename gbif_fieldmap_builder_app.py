"""
GBIF FieldMap Builder

Interactive field-survey planning app from GBIF or coordinate CSV data.

Current design:
- GBIF scientific-name search or coordinate CSV upload.
- Occurrence-supported survey ranges from DBSCAN clusters.
- Land-only background and prediction extent for island/coastal planning.
- SDM prediction map is generated as a raster-like 2D array and displayed with Folium ImageOverlay.
- Prediction raster uses the selected WorldClim raster grid/window rather than user-entered degree cells.
- Environmental variables are separated into topography and climate groups.
- Occurrence record count is explicitly used as occurrence_support_score and can be weighted.
- AUC is a diagnostic only; spatial partitions are provided because island SDM validation is difficult.
- Survey-day route planner splits candidate ranges into practical daily sampling routes.
- Java MaxEnt is not run inside this app. Export the SDM training table for ENMeval/maxnet.
"""

from __future__ import annotations

import math
import os
import re
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import folium
import numpy as np
import pandas as pd
import rasterio
import requests
import streamlit as st
from folium import FeatureGroup, LayerControl, Map
from folium.plugins import MarkerCluster
from geopy.distance import geodesic
from rasterio.enums import Resampling
from rasterio.windows import Window, from_bounds
from shapely.geometry import MultiPoint, Point, box, shape
from shapely.ops import unary_union
from sklearn.cluster import DBSCAN
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from streamlit_folium import st_folium

APP_TITLE = "GBIF FieldMap Builder"
EARTH_RADIUS_M = 6_371_008.8
GBIF_SPECIES_MATCH_URL = "https://api.gbif.org/v1/species/match"
GBIF_OCCURRENCE_SEARCH_URL = "https://api.gbif.org/v1/occurrence/search"
WC_BASE = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base"
LAND_GEOJSON_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson"
CACHE_DIR = Path(os.environ.get("GBIF_FIELDMAP_CACHE", "/tmp/gbif_fieldmap_builder"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LAT_CANDIDATES = ["decimallatitude", "decimal_latitude", "decimal latitude", "latitude", "lat", "y", "緯度"]
LON_CANDIDATES = ["decimallongitude", "decimal_longitude", "decimal longitude", "longitude", "lon", "lng", "long", "x", "経度"]
DATE_CANDIDATES = ["eventdate", "event_date", "event date", "date", "observedon", "observed_on", "observationdate", "観察日", "日付"]
YEAR_CANDIDATES = ["year", "eventyear", "event_year", "observationyear", "年"]
SPECIES_CANDIDATES = ["species", "scientificname", "scientific_name", "scientific name", "taxonname", "acceptedscientificname", "verbatimscientificname", "種名"]
MEDIA_CANDIDATES = ["mediaurl", "media_url", "imageurl", "image_url", "identifier", "associatedmedia", "associated_media", "photo", "image", "写真", "画像"]
GBIF_ID_CANDIDATES = ["gbifid", "gbif_id", "key", "occurrenceid", "occurrence_id"]
LOCALITY_CANDIDATES = ["locality", "municipality", "county", "stateprovince", "location", "place", "site", "場所", "地点"]

TOPOGRAPHY_VARS = ["elevation", "slope", "roughness"]
CLIMATE_VARS = [f"bio{i}" for i in range(1, 20)]
RESOLUTIONS = ["10m", "5m", "2.5m", "30s"]
RESOLUTION_NOTE = {
    "10m": "10 arc-minutes, about 18 km",
    "5m": "5 arc-minutes, about 9 km",
    "2.5m": "2.5 arc-minutes, about 4.5 km",
    "30s": "30 arc-seconds, about 1 km",
}
ALGORITHMS = ["Logistic regression", "Random forest", "ExtraTrees", "Gradient boosting"]
PARTITION_METHODS = ["random k-fold", "block", "checkerboard1", "checkerboard2", "jackknife", "user-defined fold column"]
PRED_EXTENT_MODES = [
    "Island-wide land within occurrence bounding box",
    "Occurrence convex hull + buffer",
    "Occurrence buffer union",
]
ROUTE_ORDER_METHODS = [
    "Priority then nearest-neighbor",
    "Nearest-neighbor from westernmost",
    "Priority score only",
    "North → South",
    "South → North",
    "West → East",
    "East → West",
]


@dataclass(frozen=True)
class ColumnDetection:
    latitude: str
    longitude: str
    event_date: Optional[str] = None
    year: Optional[str] = None
    species: Optional[str] = None
    media_url: Optional[str] = None
    gbif_id: Optional[str] = None
    locality: Optional[str] = None


@dataclass(frozen=True)
class GBIFTaxonMatch:
    input_name: str
    usage_key: Optional[int]
    matched_name: str = ""
    rank: str = ""
    status: str = ""
    confidence: Optional[int] = None


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9一-龥ぁ-んァ-ン]+", "", str(name)).lower()


def detect_column(columns: list[str], candidates: list[str]) -> Optional[str]:
    normalized = {normalize_name(col): col for col in columns}
    for cand in candidates:
        key = normalize_name(cand)
        if key in normalized:
            return normalized[key]
    for cand in candidates:
        key = normalize_name(cand)
        for norm_col, original in normalized.items():
            if key and key in norm_col:
                return original
    return None


def init_session_state() -> None:
    defaults = {
        "raw_df": None,
        "source_message": "No occurrence data loaded yet.",
        "source_key": None,
        "sdm_result": None,
        "sdm_train_table": None,
        "prediction_table": None,
        "prediction_overlay": None,
        "vif_table": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_loaded_data() -> None:
    for key in ["raw_df", "source_key", "sdm_result", "sdm_train_table", "prediction_table", "prediction_overlay", "vif_table"]:
        st.session_state[key] = None
    st.session_state.source_message = "No occurrence data loaded yet."


def detect_occurrence_columns(df: pd.DataFrame) -> ColumnDetection:
    cols = list(df.columns)
    lat = detect_column(cols, LAT_CANDIDATES)
    lon = detect_column(cols, LON_CANDIDATES)
    if lat is None or lon is None:
        raise ValueError("Latitude/longitude columns could not be detected. Use decimalLatitude/decimalLongitude, latitude/longitude, lat/lon, lat/lng, or 緯度/経度.")
    return ColumnDetection(
        latitude=lat,
        longitude=lon,
        event_date=detect_column(cols, DATE_CANDIDATES),
        year=detect_column(cols, YEAR_CANDIDATES),
        species=detect_column(cols, SPECIES_CANDIDATES),
        media_url=detect_column(cols, MEDIA_CANDIDATES),
        gbif_id=detect_column(cols, GBIF_ID_CANDIDATES),
        locality=detect_column(cols, LOCALITY_CANDIDATES),
    )


def first_url(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    match = re.search(r"https?://[^\s,;|]+", text)
    return match.group(0) if match else ""


def extract_media_url_from_gbif_record(rec: dict[str, Any]) -> str:
    media = rec.get("media") or []
    if isinstance(media, list):
        for item in media:
            if isinstance(item, dict):
                url = first_url(item.get("identifier") or item.get("references") or item.get("source"))
                if url:
                    return url
    return first_url(rec.get("associatedMedia"))


def clean_occurrences(df: pd.DataFrame, cols: ColumnDetection) -> pd.DataFrame:
    out = df.copy()
    out[cols.latitude] = pd.to_numeric(out[cols.latitude], errors="coerce")
    out[cols.longitude] = pd.to_numeric(out[cols.longitude], errors="coerce")
    out = out.dropna(subset=[cols.latitude, cols.longitude]).copy()
    out = out[out[cols.latitude].between(-90, 90) & out[cols.longitude].between(-180, 180)].copy()
    out = out.rename(columns={cols.latitude: "_latitude", cols.longitude: "_longitude"})
    out["_event_date"] = out[cols.event_date].astype(str).replace({"nan": ""}) if cols.event_date and cols.event_date in out.columns else ""
    out["_species"] = out[cols.species].astype(str).replace({"nan": ""}) if cols.species and cols.species in out.columns else ""
    out["_media_url"] = out[cols.media_url].apply(first_url) if cols.media_url and cols.media_url in out.columns else ""
    out["_gbif_id"] = out[cols.gbif_id].astype(str).replace({"nan": ""}) if cols.gbif_id and cols.gbif_id in out.columns else ""
    out["_locality"] = out[cols.locality].astype(str).replace({"nan": ""}) if cols.locality and cols.locality in out.columns else ""
    if cols.year and cols.year in out.columns:
        out["_year"] = pd.to_numeric(out[cols.year], errors="coerce")
    else:
        out["_year"] = pd.to_datetime(out["_event_date"], errors="coerce").dt.year
    return out.reset_index(drop=True)


def read_uploaded_csv(uploaded: Any) -> pd.DataFrame:
    try:
        return pd.read_csv(uploaded)
    except UnicodeDecodeError:
        uploaded.seek(0)
        return pd.read_csv(uploaded, encoding="latin1")


def match_gbif_taxon(scientific_name: str, timeout_s: int = 30) -> GBIFTaxonMatch:
    response = requests.get(GBIF_SPECIES_MATCH_URL, params={"name": scientific_name.strip()}, timeout=timeout_s)
    response.raise_for_status()
    payload = response.json()
    usage_key = payload.get("usageKey")
    return GBIFTaxonMatch(
        input_name=scientific_name.strip(),
        usage_key=int(usage_key) if usage_key is not None else None,
        matched_name=payload.get("scientificName", ""),
        rank=payload.get("rank", ""),
        status=payload.get("status", ""),
        confidence=payload.get("confidence"),
    )


def gbif_records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for rec in records:
        rows.append({
            "decimalLatitude": rec.get("decimalLatitude"),
            "decimalLongitude": rec.get("decimalLongitude"),
            "eventDate": rec.get("eventDate", ""),
            "year": rec.get("year"),
            "species": rec.get("species") or rec.get("scientificName", ""),
            "scientificName": rec.get("scientificName", ""),
            "basisOfRecord": rec.get("basisOfRecord", ""),
            "countryCode": rec.get("countryCode", ""),
            "locality": rec.get("locality", ""),
            "gbifID": rec.get("gbifID") or rec.get("key"),
            "media_url": extract_media_url_from_gbif_record(rec),
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_gbif_occurrences_cached(scientific_name: str, max_records: int, country_code: str, year_from: Optional[int], year_to: Optional[int]) -> tuple[GBIFTaxonMatch, pd.DataFrame]:
    match = match_gbif_taxon(scientific_name)
    if match.usage_key is None:
        raise ValueError(f"GBIF could not match this scientific name: {scientific_name}")
    params_base: dict[str, Any] = {"taxonKey": match.usage_key, "hasCoordinate": "true", "hasGeospatialIssue": "false", "limit": 300}
    if country_code.strip():
        params_base["country"] = country_code.strip().upper()
    if year_from is not None and year_to is not None:
        params_base["year"] = f"{int(year_from)},{int(year_to)}"
    elif year_from is not None:
        params_base["year"] = f"{int(year_from)},"
    elif year_to is not None:
        params_base["year"] = f",{int(year_to)}"
    records: list[dict[str, Any]] = []
    offset = 0
    while len(records) < max_records:
        params = dict(params_base)
        params["offset"] = offset
        params["limit"] = min(300, max_records - len(records))
        response = requests.get(GBIF_OCCURRENCE_SEARCH_URL, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("results", [])
        if not batch:
            break
        records.extend(batch)
        offset += len(batch)
        if payload.get("endOfRecords") is True:
            break
    return match, gbif_records_to_dataframe(records)


@st.cache_resource(show_spinner=False)
def load_land_geometry():
    response = requests.get(LAND_GEOJSON_URL, timeout=120)
    response.raise_for_status()
    geojson = response.json()
    geoms = [shape(feature["geometry"]) for feature in geojson.get("features", [])]
    return unary_union(geoms)


def km_to_deg(km: float) -> float:
    return float(km) / 111.0


def is_land(lon: float, lat: float, land_geom=None) -> bool:
    try:
        land = land_geom if land_geom is not None else load_land_geometry()
        return bool(land.covers(Point(float(lon), float(lat))))
    except Exception:
        return False


def point_at_distance(lat: float, lon: float, meters: float, bearing: float) -> tuple[float, float]:
    p = geodesic(meters=float(meters)).destination((float(lat), float(lon)), bearing)
    return float(p.latitude), float(p.longitude)


def range_fits_land(lat: float, lon: float, radius_m: float, land_geom=None) -> bool:
    if not is_land(lon, lat, land_geom):
        return False
    if radius_m <= 0:
        return True
    for bearing in [0, 45, 90, 135, 180, 225, 270, 315]:
        plat, plon = point_at_distance(lat, lon, radius_m, bearing)
        if not is_land(plon, plat, land_geom):
            return False
    return True


def filter_to_land(df: pd.DataFrame, lat_col: str = "latitude", lon_col: str = "longitude", range_radius_m: float = 0) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    land = load_land_geometry()
    mask = [range_fits_land(row[lat_col], row[lon_col], range_radius_m, land) for _, row in df.iterrows()]
    return df.loc[mask].reset_index(drop=True)


def spatial_thin(df: pd.DataFrame, thinning_m: float) -> pd.DataFrame:
    if df.empty or thinning_m <= 0:
        out = df.copy()
        out["_thinned_in"] = True
        return out
    work = df.copy()
    work["_year_sort"] = pd.to_numeric(work.get("_year"), errors="coerce").fillna(-9999)
    work["_has_photo_sort"] = work.get("_media_url", "").astype(str).str.len() > 0
    work = work.sort_values(["_has_photo_sort", "_year_sort"], ascending=[False, False]).reset_index(drop=True)
    kept_rows = []
    kept_coords: list[tuple[float, float]] = []
    for _, row in work.iterrows():
        coord = (float(row["_latitude"]), float(row["_longitude"]))
        if all(geodesic(coord, kept).m >= thinning_m for kept in kept_coords):
            kept_rows.append(row)
            kept_coords.append(coord)
    out = pd.DataFrame(kept_rows).drop(columns=["_year_sort", "_has_photo_sort"], errors="ignore").reset_index(drop=True)
    out["_thinned_in"] = True
    return out


def haversine_dbscan(df: pd.DataFrame, lat_col: str, lon_col: str, threshold_m: float, min_samples: int) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=int, name="cluster_id")
    coords_rad = [[math.radians(lat), math.radians(lon)] for lat, lon in df[[lat_col, lon_col]].to_numpy(dtype=float)]
    eps = float(threshold_m) / EARTH_RADIUS_M
    labels = DBSCAN(eps=eps, min_samples=int(min_samples), metric="haversine").fit_predict(coords_rad)
    return pd.Series(labels, index=df.index, name="cluster_id")


def extent_geometry(occ: pd.DataFrame, mode: str, bbox_expansion_km: float, occurrence_buffer_km: float):
    points = [Point(float(row["_longitude"]), float(row["_latitude"])) for _, row in occ.iterrows()]
    if not points:
        return None
    if mode == "Island-wide land within occurrence bounding box":
        d = km_to_deg(bbox_expansion_km)
        return box(float(occ["_longitude"].min()) - d, float(occ["_latitude"].min()) - d, float(occ["_longitude"].max()) + d, float(occ["_latitude"].max()) + d)
    if mode == "Occurrence buffer union":
        d = max(km_to_deg(occurrence_buffer_km), 0.001)
        return unary_union([p.buffer(d) for p in points])
    d = km_to_deg(occurrence_buffer_km)
    if len(points) == 1:
        return points[0].buffer(max(d, 0.01))
    return MultiPoint(points).convex_hull.buffer(d)


def representative_medoid(group: pd.DataFrame) -> pd.Series:
    if len(group) == 1:
        return group.iloc[0]
    coords = [(float(r["_latitude"]), float(r["_longitude"])) for _, r in group.iterrows()]
    best_i = 0
    best_score = float("inf")
    for i, coord in enumerate(coords):
        score = sum(geodesic(coord, other).m for other in coords) / max(len(coords) - 1, 1)
        if str(group.iloc[i].get("_media_url", "")):
            score -= 50
        if score < best_score:
            best_score = score
            best_i = i
    return group.iloc[best_i]


def summarize_species(values: pd.Series, max_items: int = 3) -> str:
    cleaned = values.dropna().astype(str).str.strip()
    cleaned = cleaned[cleaned.ne("") & cleaned.ne("nan")]
    if cleaned.empty:
        return ""
    counts = cleaned.value_counts().head(max_items)
    parts = [f"{name} ({count})" for name, count in counts.items()]
    more = cleaned.nunique() - len(counts)
    if more > 0:
        parts.append(f"+{more} more")
    return "; ".join(parts)


def make_candidate_sites(df: pd.DataFrame, method: str, thinning_m: float, occurrence_weight: float) -> pd.DataFrame:
    clustered = df[df["cluster_id"] >= 0].copy()
    rows = []
    max_n = max(1, int(clustered.groupby("cluster_id").size().max())) if not clustered.empty else 1
    for site_id, (cluster_id, group) in enumerate(clustered.groupby("cluster_id", sort=True), start=1):
        years = pd.to_numeric(group.get("_year"), errors="coerce").dropna()
        year_min = int(years.min()) if not years.empty else None
        year_max = int(years.max()) if not years.empty else None
        rep = representative_medoid(group)
        if method == "Centroid":
            centroid = MultiPoint([Point(float(row["_longitude"]), float(row["_latitude"])) for _, row in group.iterrows()]).centroid
            lat, lon = float(centroid.y), float(centroid.x)
            reason = f"Geometric centroid of occurrence cluster {cluster_id}."
        else:
            lat, lon = float(rep["_latitude"]), float(rep["_longitude"])
            reason = f"Medoid of occurrence cluster {cluster_id}: an actual occurrence point minimizing mean distance to other records."
        if thinning_m > 0:
            reason += f" Spatial thinning at {int(thinning_m)} m was applied before clustering."
        n = int(len(group))
        occurrence_support = round(math.log1p(n) / math.log1p(max_n), 3) if max_n > 1 else 1.0
        recent_bonus = 0 if year_max is None else max(0, min(20, year_max - 2000)) / 20
        photo_bonus = 0.15 if str(rep.get("_media_url", "")) else 0
        base = 0.35 + occurrence_weight * occurrence_support + 0.15 * recent_bonus + photo_bonus
        priority = round(min(1.0, base), 3)
        warning = "High occurrence density: high-confidence area, but may reflect access/observer bias." if n >= 20 else "Low occurrence support: useful supplementary site, but field confirmation risk is higher." if n <= 2 else "Moderate occurrence support. Check access and habitat manually."
        rows.append({"site_id": site_id, "candidate_type": "Occurrence-supported survey range", "cluster_id": int(cluster_id), "latitude": lat, "longitude": lon, "n_occurrences": n, "occurrence_support_score": occurrence_support, "species_summary": summarize_species(group.get("_species", pd.Series(dtype=str))), "year_min": year_min, "year_max": year_max, "representative_gbif_id": str(rep.get("_gbif_id", "")), "representative_media_url": str(rep.get("_media_url", "")), "representative_locality": str(rep.get("_locality", "")), "candidate_method": method, "selection_reason": reason, "bias_warning": warning, "priority_score": priority})
    return pd.DataFrame(rows)


def add_priority_rank(sites: pd.DataFrame) -> pd.DataFrame:
    out = sites.copy()
    if out.empty:
        out["priority_rank"] = []
        return out
    sort_cols = ["priority_score"]
    if "sdm_suitability" in out.columns:
        sort_cols.append("sdm_suitability")
    if "occurrence_support_score" in out.columns:
        sort_cols.append("occurrence_support_score")
    rank = out.sort_values(sort_cols, ascending=False).reset_index(drop=True)
    rank["priority_rank"] = range(1, len(rank) + 1)
    out = out.drop(columns=["priority_rank"], errors="ignore")
    return out.merge(rank[["site_id", "priority_rank"]], on="site_id", how="left")


def nearest_neighbor_order(sites: pd.DataFrame) -> pd.DataFrame:
    if sites.empty:
        return sites.copy()
    remaining = sites.copy().reset_index(drop=True)
    start_idx = remaining["longitude"].idxmin()
    route_rows = [remaining.loc[start_idx]]
    remaining = remaining.drop(index=start_idx).reset_index(drop=True)
    while not remaining.empty:
        current = route_rows[-1]
        current_xy = (float(current["latitude"]), float(current["longitude"]))
        distances = remaining.apply(lambda row: geodesic(current_xy, (float(row["latitude"]), float(row["longitude"]))).km, axis=1)
        next_idx = distances.idxmin()
        route_rows.append(remaining.loc[next_idx])
        remaining = remaining.drop(index=next_idx).reset_index(drop=True)
    return pd.DataFrame(route_rows)


def order_sites(sites: pd.DataFrame, mode: str) -> pd.DataFrame:
    if sites.empty:
        out = sites.copy()
        out["route_order"] = []
        return out
    if mode == "Priority score":
        ordered = sites.sort_values(["priority_score"], ascending=False)
    elif mode == "Nearest-neighbor route":
        ordered = nearest_neighbor_order(sites)
    elif mode == "North → South":
        ordered = sites.sort_values(["latitude", "longitude"], ascending=[False, True])
    elif mode == "South → North":
        ordered = sites.sort_values(["latitude", "longitude"], ascending=[True, True])
    elif mode == "West → East":
        ordered = sites.sort_values(["longitude", "latitude"], ascending=[True, False])
    elif mode == "East → West":
        ordered = sites.sort_values(["longitude", "latitude"], ascending=[False, False])
    else:
        ordered = sites.sort_values(["candidate_type", "cluster_id", "site_id"])
    ordered = ordered.reset_index(drop=True)
    ordered["route_order"] = range(1, len(ordered) + 1)
    return ordered


def make_google_maps_point_url(latitude: float, longitude: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={latitude:.6f}%2C{longitude:.6f}"


def make_google_maps_route_url(sites: pd.DataFrame, travelmode: str = "driving", max_waypoints: int = 8) -> str:
    if sites.empty:
        return ""
    ordered = sites.sort_values("route_order") if "route_order" in sites.columns else sites.copy()
    coords = [(float(row["latitude"]), float(row["longitude"])) for _, row in ordered.iterrows()]
    if len(coords) == 1:
        return make_google_maps_point_url(coords[0][0], coords[0][1])
    params = {"api": "1", "origin": f"{coords[0][0]:.6f},{coords[0][1]:.6f}", "destination": f"{coords[-1][0]:.6f},{coords[-1][1]:.6f}", "travelmode": travelmode}
    if travelmode != "transit":
        waypoints = coords[1:-1][:max_waypoints]
        if waypoints:
            params["waypoints"] = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in waypoints)
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params, safe=",|")


def add_navigation_columns(sites: pd.DataFrame) -> pd.DataFrame:
    out = sites.copy()
    if out.empty:
        out["google_maps_point_url"] = []
        out["next_site_straight_km"] = []
        return out
    out = out.sort_values("route_order").reset_index(drop=True) if "route_order" in out.columns else out
    out["google_maps_point_url"] = out.apply(lambda row: make_google_maps_point_url(float(row["latitude"]), float(row["longitude"])), axis=1)
    next_dist = []
    for i in range(len(out)):
        if i == len(out) - 1:
            next_dist.append(None)
        else:
            a = (float(out.loc[i, "latitude"]), float(out.loc[i, "longitude"]))
            b = (float(out.loc[i + 1, "latitude"]), float(out.loc[i + 1, "longitude"]))
            next_dist.append(round(float(geodesic(a, b).km), 3))
    out["next_site_straight_km"] = pd.Series(next_dist, dtype="float")
    return out


def nearest_neighbor_from_start(sites: pd.DataFrame, start_idx: int) -> pd.DataFrame:
    if sites.empty:
        return sites.copy()
    remaining = sites.copy().reset_index(drop=True)
    start_idx = int(max(0, min(start_idx, len(remaining) - 1)))
    rows = [remaining.loc[start_idx]]
    remaining = remaining.drop(index=start_idx).reset_index(drop=True)
    while not remaining.empty:
        current = rows[-1]
        current_xy = (float(current["latitude"]), float(current["longitude"]))
        distances = remaining.apply(lambda row: geodesic(current_xy, (float(row["latitude"]), float(row["longitude"]))).km, axis=1)
        next_idx = int(distances.idxmin())
        rows.append(remaining.loc[next_idx])
        remaining = remaining.drop(index=next_idx).reset_index(drop=True)
    return pd.DataFrame(rows).reset_index(drop=True)


def order_sites_for_sampling_plan(sites: pd.DataFrame, method: str) -> pd.DataFrame:
    if sites.empty:
        return sites.copy()
    work = sites.copy().reset_index(drop=True)
    if method == "Priority score only":
        return work.sort_values(["priority_score", "sdm_suitability", "occurrence_support_score"], ascending=False, na_position="last").reset_index(drop=True)
    if method == "Priority then nearest-neighbor":
        ranked = work.sort_values(["priority_score", "sdm_suitability", "occurrence_support_score"], ascending=False, na_position="last").reset_index(drop=True)
        return nearest_neighbor_from_start(ranked, 0)
    if method == "Nearest-neighbor from westernmost":
        return nearest_neighbor_from_start(work, int(work["longitude"].idxmin()))
    if method == "North → South":
        return work.sort_values(["latitude", "longitude"], ascending=[False, True]).reset_index(drop=True)
    if method == "South → North":
        return work.sort_values(["latitude", "longitude"], ascending=[True, True]).reset_index(drop=True)
    if method == "West → East":
        return work.sort_values(["longitude", "latitude"], ascending=[True, False]).reset_index(drop=True)
    if method == "East → West":
        return work.sort_values(["longitude", "latitude"], ascending=[False, False]).reset_index(drop=True)
    return work.reset_index(drop=True)


def split_ordered_sites_into_days(ordered: pd.DataFrame, survey_days: int, max_sites_per_day: int, max_day_distance_km: float) -> pd.DataFrame:
    if ordered.empty:
        return ordered.copy()
    rows = []
    current_day = 1
    day_count = 0
    day_distance = 0.0
    prev_coord: Optional[tuple[float, float]] = None
    for _, row in ordered.iterrows():
        coord = (float(row["latitude"]), float(row["longitude"]))
        leg = 0.0 if prev_coord is None or day_count == 0 else float(geodesic(prev_coord, coord).km)
        would_exceed_sites = day_count >= int(max_sites_per_day)
        would_exceed_dist = day_count > 0 and max_day_distance_km > 0 and (day_distance + leg) > float(max_day_distance_km)
        if (would_exceed_sites or would_exceed_dist) and current_day < int(survey_days):
            current_day += 1
            day_count = 0
            day_distance = 0.0
            prev_coord = None
            leg = 0.0
        if current_day > int(survey_days) or day_count >= int(max_sites_per_day):
            continue
        day_count += 1
        day_distance += leg
        new = row.to_dict()
        new["survey_day"] = current_day
        new["day_route_order"] = day_count
        new["distance_from_previous_km"] = round(leg, 3)
        new["cumulative_day_distance_km"] = round(day_distance, 3)
        rows.append(new)
        prev_coord = coord
    plan = pd.DataFrame(rows)
    if plan.empty:
        return plan
    urls = {}
    for day, group in plan.groupby("survey_day"):
        tmp = group.sort_values("day_route_order").copy()
        tmp["route_order"] = range(1, len(tmp) + 1)
        urls[int(day)] = make_google_maps_route_url(tmp, travelmode="driving")
    plan["day_google_maps_route_url"] = plan["survey_day"].map(urls)
    plan["google_maps_point_url"] = plan.apply(lambda r: make_google_maps_point_url(float(r["latitude"]), float(r["longitude"])), axis=1)
    return plan.reset_index(drop=True)


def route_planner_panel(sites: pd.DataFrame) -> pd.DataFrame:
    st.subheader("Survey route planner")
    st.caption("Create a day-by-day sampling route from candidate survey ranges. Distances are straight-line distances; use Google Maps links for real roads/transit.")
    if sites is None or sites.empty:
        st.info("No candidate survey ranges are available yet.")
        return pd.DataFrame()
    with st.expander("Route planner settings", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            survey_days = st.number_input("Survey days", min_value=1, max_value=30, value=2, step=1)
        with c2:
            max_sites_per_day = st.number_input("Max sites per day", min_value=1, max_value=50, value=8, step=1)
        with c3:
            max_day_distance_km = st.number_input("Max straight-line distance per day (km)", min_value=0.0, max_value=500.0, value=40.0, step=5.0)
        with c4:
            max_total_sites = st.number_input("Max total sites in route", min_value=1, max_value=500, value=min(30, max(1, len(sites))), step=1)
        route_order_method = st.selectbox("Route ordering method", ROUTE_ORDER_METHODS, index=0)
        include_occ = st.checkbox("Include occurrence-supported ranges", value=True)
        include_sdm = st.checkbox("Include SDM-high exploration ranges", value=True)
        use_manual_bbox = st.checkbox("Limit to manual survey bounding box", value=False)
        bbox_vals = None
        if use_manual_bbox:
            min_lat0 = float(sites["latitude"].min())
            max_lat0 = float(sites["latitude"].max())
            min_lon0 = float(sites["longitude"].min())
            max_lon0 = float(sites["longitude"].max())
            b1, b2, b3, b4 = st.columns(4)
            with b1:
                min_lat = st.number_input("Min latitude", value=min_lat0, format="%.6f")
            with b2:
                max_lat = st.number_input("Max latitude", value=max_lat0, format="%.6f")
            with b3:
                min_lon = st.number_input("Min longitude", value=min_lon0, format="%.6f")
            with b4:
                max_lon = st.number_input("Max longitude", value=max_lon0, format="%.6f")
            bbox_vals = (min_lat, max_lat, min_lon, max_lon)
    work = sites.copy()
    ctype = work.get("candidate_type", pd.Series("", index=work.index)).astype(str)
    mask = pd.Series(False, index=work.index)
    if include_occ:
        mask = mask | ~ctype.str.startswith("SDM-high")
    if include_sdm:
        mask = mask | ctype.str.startswith("SDM-high")
    work = work.loc[mask].copy()
    if bbox_vals is not None:
        min_lat, max_lat, min_lon, max_lon = bbox_vals
        work = work[work["latitude"].between(min_lat, max_lat) & work["longitude"].between(min_lon, max_lon)].copy()
    if work.empty:
        st.info("No candidates match the current route-planner filters.")
        return pd.DataFrame()
    work = work.sort_values(["priority_score", "sdm_suitability", "occurrence_support_score"], ascending=False, na_position="last").head(int(max_total_sites)).copy()
    ordered = order_sites_for_sampling_plan(work, route_order_method)
    plan = split_ordered_sites_into_days(ordered, int(survey_days), int(max_sites_per_day), float(max_day_distance_km))
    if plan.empty:
        st.info("Route plan is empty under the current constraints.")
        return pd.DataFrame()
    used_n = len(plan)
    candidate_n = len(work)
    if used_n < candidate_n:
        st.warning(f"Route capacity used {used_n} of {candidate_n} filtered candidates. Increase days, max sites per day, or daily distance to include more.")
    summary = plan.groupby("survey_day").agg(
        sites=("site_id", "count"),
        straight_distance_km=("distance_from_previous_km", "sum"),
        mean_priority=("priority_score", "mean"),
    ).reset_index()
    summary["straight_distance_km"] = summary["straight_distance_km"].round(2)
    summary["mean_priority"] = summary["mean_priority"].round(3)
    st.write("Daily route summary")
    st.dataframe(summary, width="stretch", hide_index=True)
    link_cols = st.columns(min(int(survey_days), 4))
    for i, (day, group) in enumerate(plan.groupby("survey_day")):
        url = str(group["day_google_maps_route_url"].iloc[0])
        with link_cols[(int(day) - 1) % len(link_cols)]:
            st.link_button(f"Open Day {int(day)} route", url, width="stretch")
    display_cols = ["survey_day", "day_route_order", "site_id", "candidate_type", "priority_score", "occurrence_support_score", "sdm_suitability", "n_occurrences", "distance_from_previous_km", "cumulative_day_distance_km", "latitude", "longitude", "google_maps_point_url"]
    display_cols = [c for c in display_cols if c in plan.columns]
    st.write("Sampling route plan")
    st.dataframe(plan[display_cols], width="stretch", hide_index=True)
    return plan


def download_file(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with requests.get(url, stream=True, timeout=180) as response:
        response.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(dest)
    return dest


@st.cache_data(show_spinner=False)
def get_worldclim_raster_path(var: str, resolution: str) -> str:
    var = var.lower()
    resolution = resolution.lower()
    if var in {"elevation", "slope", "roughness"}:
        zip_name = f"wc2.1_{resolution}_elev.zip"
        tif_name = f"wc2.1_{resolution}_elev.tif"
    elif var.startswith("bio"):
        n = int(var.replace("bio", ""))
        zip_name = f"wc2.1_{resolution}_bio.zip"
        tif_name = f"wc2.1_{resolution}_bio_{n}.tif"
    else:
        raise ValueError(f"Unsupported web variable: {var}")
    zip_path = CACHE_DIR / zip_name
    extract_dir = CACHE_DIR / zip_name.replace(".zip", "")
    raster_path = extract_dir / tif_name
    if raster_path.exists():
        return str(raster_path)
    extract_dir.mkdir(parents=True, exist_ok=True)
    download_file(f"{WC_BASE}/{zip_name}", zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    matches = list(extract_dir.rglob(tif_name))
    if not matches:
        raise FileNotFoundError(f"Could not find {tif_name} after extracting {zip_name}")
    return str(matches[0])


def sample_raster_values_fast(points: pd.DataFrame, raster_path: str, lat_col: str, lon_col: str, derived: Optional[str] = None) -> np.ndarray:
    if points.empty:
        return np.array([], dtype=float)
    with rasterio.open(raster_path) as src:
        coords = points[[lon_col, lat_col]].to_numpy(dtype=float)
        rc = np.array([src.index(float(lon), float(lat)) for lon, lat in coords], dtype=int)
        rows, cols = rc[:, 0], rc[:, 1]
        pad = 1 if derived in {"slope", "roughness"} else 0
        r0 = max(0, int(rows.min()) - pad)
        r1 = min(src.height - 1, int(rows.max()) + pad)
        c0 = max(0, int(cols.min()) - pad)
        c1 = min(src.width - 1, int(cols.max()) + pad)
        window = Window(c0, r0, c1 - c0 + 1, r1 - r0 + 1)
        arr = src.read(1, window=window, boundless=True, fill_value=np.nan).astype(float)
        nodata = src.nodata
        if nodata is not None:
            arr[arr == nodata] = np.nan
        local_r = rows - r0
        local_c = cols - c0
        values = np.full(len(points), np.nan, dtype=float)
        for i, (rr, cc) in enumerate(zip(local_r, local_c)):
            if rr < 0 or cc < 0 or rr >= arr.shape[0] or cc >= arr.shape[1]:
                continue
            if derived is None:
                values[i] = arr[rr, cc]
            else:
                sub = arr[max(0, rr - 1):min(arr.shape[0], rr + 2), max(0, cc - 1):min(arr.shape[1], cc + 2)]
                if np.all(np.isnan(sub)):
                    continue
                if derived == "roughness":
                    values[i] = np.nanmax(sub) - np.nanmin(sub)
                elif derived == "slope":
                    gy, gx = np.gradient(sub)
                    values[i] = np.nanmean(np.sqrt(gx**2 + gy**2))
        return values


def extract_web_environment(points: pd.DataFrame, variables: list[str], lat_col: str, lon_col: str, resolution: str, status=None, progress=None, start: float = 0.0, span: float = 1.0) -> pd.DataFrame:
    out = points.copy()
    total = max(len(variables), 1)
    for i, var in enumerate(variables, start=1):
        if status is not None:
            status.write(f"Extracting {var} ({resolution}) with fast raster-window sampling [{i}/{total}]...")
        if progress is not None:
            progress.progress(min(1.0, start + span * (i - 1) / total))
        if var == "slope":
            elev_path = get_worldclim_raster_path("elevation", resolution)
            out[var] = sample_raster_values_fast(out, elev_path, lat_col, lon_col, derived="slope")
        elif var == "roughness":
            elev_path = get_worldclim_raster_path("elevation", resolution)
            out[var] = sample_raster_values_fast(out, elev_path, lat_col, lon_col, derived="roughness")
        else:
            raster_path = get_worldclim_raster_path(var, resolution)
            out[var] = sample_raster_values_fast(out, raster_path, lat_col, lon_col)
    if progress is not None:
        progress.progress(min(1.0, start + span))
    return out


def generate_land_points(occ: pd.DataFrame, n_points: int, expansion_km: float, random_state: int = 42, status=None, range_radius_m: float = 0) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    d = km_to_deg(expansion_km)
    min_lat, max_lat = occ["_latitude"].min() - d, occ["_latitude"].max() + d
    min_lon, max_lon = occ["_longitude"].min() - d, occ["_longitude"].max() + d
    land = load_land_geometry()
    rows = []
    attempts = 0
    max_attempts = max(int(n_points) * 800, 50_000)
    batch_size = max(1000, int(n_points) * 5)
    while len(rows) < int(n_points) and attempts < max_attempts:
        lats = rng.uniform(max(-90, min_lat), min(90, max_lat), batch_size)
        lons = rng.uniform(max(-180, min_lon), min(180, max_lon), batch_size)
        for lat, lon in zip(lats, lons):
            attempts += 1
            if range_fits_land(lat, lon, range_radius_m, land):
                rows.append({"latitude": float(lat), "longitude": float(lon)})
                if len(rows) >= int(n_points):
                    break
        if status is not None:
            status.write(f"Generating land-only random points: {len(rows):,}/{int(n_points):,}")
    if len(rows) < int(n_points):
        raise RuntimeError(f"Could only generate {len(rows)} land points out of {int(n_points)}. Reduce point count or increase extent expansion.")
    return pd.DataFrame(rows)


def build_presence_background_from_occurrences(occ: pd.DataFrame, n_background: int, expansion_km: float, status=None) -> pd.DataFrame:
    pres = occ[["_latitude", "_longitude"]].rename(columns={"_latitude": "latitude", "_longitude": "longitude"}).copy()
    pres["presence"] = 1
    bg = generate_land_points(occ, n_background, expansion_km, random_state=42, status=status, range_radius_m=0)
    bg["presence"] = 0
    return pd.concat([pres, bg], ignore_index=True)


def rgba_from_prediction(pred: np.ndarray, alpha: int = 170) -> np.ndarray:
    rgba = np.zeros((pred.shape[0], pred.shape[1], 4), dtype=np.uint8)
    valid = np.isfinite(pred)
    v = np.clip(pred, 0, 1)
    breaks = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    colors = np.array([
        [44, 123, 182],
        [171, 217, 233],
        [255, 255, 191],
        [253, 174, 97],
        [215, 25, 28],
    ], dtype=float)
    flat = v[valid]
    out = np.zeros((flat.size, 3), dtype=float)
    for i in range(len(breaks) - 1):
        m = (flat >= breaks[i]) & (flat <= breaks[i + 1])
        if not np.any(m):
            continue
        t = (flat[m] - breaks[i]) / max(1e-12, breaks[i + 1] - breaks[i])
        out[m] = colors[i] * (1 - t[:, None]) + colors[i + 1] * t[:, None]
    rgba[..., :3][valid] = out.astype(np.uint8)
    rgba[..., 3][valid] = alpha
    return rgba


def read_window_array(path: str, bounds: tuple[float, float, float, float], out_shape: tuple[int, int]) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    west, south, east, north = bounds
    with rasterio.open(path) as src:
        window = from_bounds(west, south, east, north, transform=src.transform)
        window = window.round_offsets().round_lengths()
        window = Window(
            max(0, window.col_off),
            max(0, window.row_off),
            min(src.width - max(0, window.col_off), window.width),
            min(src.height - max(0, window.row_off), window.height),
        )
        actual_bounds = src.window_bounds(window)
        arr = src.read(1, window=window, out_shape=out_shape, resampling=Resampling.bilinear, boundless=True, fill_value=np.nan).astype(float)
        if src.nodata is not None:
            arr[arr == src.nodata] = np.nan
    return arr, actual_bounds


def build_sdm_predict_raster(
    occ: pd.DataFrame,
    variables: list[str],
    resolution: str,
    sdm_result: dict[str, Any],
    mode: str,
    bbox_expansion_km: float,
    occurrence_buffer_km: float,
    max_pixels: int,
    status=None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    geom = extent_geometry(occ, mode, bbox_expansion_km, occurrence_buffer_km)
    if geom is None:
        raise RuntimeError("Prediction extent could not be generated.")
    land = load_land_geometry()
    west, south, east, north = geom.bounds
    ref_path = get_worldclim_raster_path("elevation" if any(v in {"elevation", "slope", "roughness"} for v in variables) else variables[0], resolution)
    with rasterio.open(ref_path) as src:
        window = from_bounds(west, south, east, north, transform=src.transform).round_offsets().round_lengths()
        raw_height = max(1, int(window.height))
        raw_width = max(1, int(window.width))
    stride = max(1, int(math.ceil(math.sqrt((raw_height * raw_width) / max(1, max_pixels)))))
    out_height = max(1, int(math.ceil(raw_height / stride)))
    out_width = max(1, int(math.ceil(raw_width / stride)))
    if status is not None:
        status.write(f"Predicting raster map on {out_width:,} × {out_height:,} cells; stride={stride} from source raster.")
    arrays: dict[str, np.ndarray] = {}
    actual_bounds = None
    elev_cache = None
    for var in variables:
        if var in {"slope", "roughness"}:
            if elev_cache is None:
                elev_cache, actual_bounds = read_window_array(get_worldclim_raster_path("elevation", resolution), (west, south, east, north), (out_height, out_width))
            gy, gx = np.gradient(elev_cache)
            if var == "slope":
                arrays[var] = np.sqrt(gx**2 + gy**2)
            else:
                pad = np.pad(elev_cache, 1, mode="edge")
                rough = np.full_like(elev_cache, np.nan, dtype=float)
                for r in range(elev_cache.shape[0]):
                    for c in range(elev_cache.shape[1]):
                        sub = pad[r:r + 3, c:c + 3]
                        rough[r, c] = np.nanmax(sub) - np.nanmin(sub) if not np.all(np.isnan(sub)) else np.nan
                arrays[var] = rough
        else:
            path = get_worldclim_raster_path(var, resolution)
            arrays[var], actual_bounds = read_window_array(path, (west, south, east, north), (out_height, out_width))
    if actual_bounds is None:
        raise RuntimeError("Could not read raster window for prediction.")
    west2, south2, east2, north2 = actual_bounds
    lon_centers = np.linspace(west2 + (east2 - west2) / (2 * out_width), east2 - (east2 - west2) / (2 * out_width), out_width)
    lat_centers = np.linspace(north2 - (north2 - south2) / (2 * out_height), south2 + (north2 - south2) / (2 * out_height), out_height)
    lon_grid, lat_grid = np.meshgrid(lon_centers, lat_centers)
    flat = {var: arrays[var].ravel() for var in variables}
    X = pd.DataFrame(flat)
    finite_mask = np.isfinite(X.to_numpy()).all(axis=1)
    spatial_mask = []
    for lat, lon in zip(lat_grid.ravel(), lon_grid.ravel()):
        p = Point(float(lon), float(lat))
        spatial_mask.append(bool(geom.covers(p) and land.covers(p)))
    spatial_mask = np.array(spatial_mask, dtype=bool)
    valid = finite_mask & spatial_mask
    pred_flat = np.full(X.shape[0], np.nan, dtype=float)
    if valid.sum() == 0:
        raise RuntimeError("No valid land raster cells were available for prediction.")
    preds = [model.predict_proba(X.loc[valid, variables])[:, 1] for model in sdm_result["models"].values()]
    pred_flat[valid] = np.mean(np.vstack(preds), axis=0)
    pred = pred_flat.reshape(out_height, out_width)
    rgba = rgba_from_prediction(pred)
    overlay = {"image": rgba, "bounds": [[south2, west2], [north2, east2]], "shape": pred.shape, "source_stride": stride}
    pred_table = pd.DataFrame({
        "latitude": lat_grid.ravel()[valid],
        "longitude": lon_grid.ravel()[valid],
        "sdm_suitability": pred_flat[valid],
    })
    return overlay, pred_table


def compute_vif_table(df: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    rows = []
    X = df[variables].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    X = pd.DataFrame(SimpleImputer(strategy="median").fit_transform(X), columns=variables)
    for var in variables:
        others = [v for v in variables if v != var]
        if not others:
            rows.append({"variable": var, "vif": 1.0, "vif_warning": ""})
            continue
        try:
            r2 = LinearRegression().fit(X[others].values, X[var].values).score(X[others].values, X[var].values)
            vif = 1.0 / max(1e-12, 1.0 - r2)
        except Exception:
            vif = np.inf
        warning = ""
        if not np.isfinite(vif) or vif >= 1e6:
            warning = "unstable / near-perfect collinearity"
        elif vif >= 100:
            warning = "very high collinearity"
        elif vif >= 10:
            warning = "high collinearity"
        rows.append({"variable": var, "vif": round(float(vif), 3) if np.isfinite(vif) else np.inf, "vif_warning": warning})
    return pd.DataFrame(rows).sort_values("vif", ascending=False).reset_index(drop=True)


def vif_step(df: pd.DataFrame, variables: list[str], threshold: float = 10.0, status=None, progress=None, start: float = 0.0, span: float = 0.1) -> tuple[list[str], pd.DataFrame]:
    kept = list(dict.fromkeys(variables))
    removed_rows = []
    iter_n = 0
    while len(kept) > 1:
        iter_n += 1
        if status is not None:
            status.write(f"Running VIF step {iter_n} with threshold {threshold}...")
        if progress is not None:
            progress.progress(min(1.0, start + span * min(iter_n, 10) / 10))
        table = compute_vif_table(df, kept)
        top = table.iloc[0]
        top_vif = float(top["vif"])
        if np.isfinite(top_vif) and top_vif <= threshold:
            break
        removed = str(top["variable"])
        removed_rows.append({"variable": removed, "vif": top["vif"], "vif_warning": top.get("vif_warning", ""), "status": "removed"})
        kept.remove(removed)
    final_table = compute_vif_table(df, kept) if kept else pd.DataFrame(columns=["variable", "vif", "vif_warning"])
    final_table["status"] = "kept"
    if removed_rows:
        final_table = pd.concat([final_table, pd.DataFrame(removed_rows)], ignore_index=True)
    return kept, final_table


def make_model(name: str, random_state: int = 42):
    if name == "Logistic regression":
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_state))])
    if name == "Random forest":
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", RandomForestClassifier(n_estimators=300, random_state=random_state, class_weight="balanced_subsample"))])
    if name == "ExtraTrees":
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", ExtraTreesClassifier(n_estimators=300, random_state=random_state, class_weight="balanced"))])
    if name == "Gradient boosting":
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", GradientBoostingClassifier(random_state=random_state))])
    raise ValueError(f"Unknown algorithm: {name}")


def auc_warning(auc: float, method: str) -> str:
    if not np.isfinite(auc):
        return "not available"
    if auc >= 0.98:
        return "suspiciously high; likely easy background or leakage"
    if auc >= 0.95:
        return "very high; inspect spatial partition and background"
    if method == "random k-fold" and auc >= 0.90:
        return "random split may be optimistic"
    return ""


def make_spatial_folds(data: pd.DataFrame, method: str, k: int, checkerboard_deg: float, user_fold_col: Optional[str]) -> pd.Series:
    y = data["presence"].astype(int)
    n = len(data)
    if method == "random k-fold":
        k_eff = max(2, min(k, int(y.value_counts().min()) if y.nunique() == 2 else k))
        folds = pd.Series(index=data.index, dtype=int)
        splitter = StratifiedKFold(n_splits=k_eff, shuffle=True, random_state=42)
        for fold_id, (_, test_idx) in enumerate(splitter.split(data, y), start=1):
            folds.iloc[test_idx] = fold_id
        return folds.astype(int)
    if method == "block":
        lat_med = data["latitude"].median()
        lon_med = data["longitude"].median()
        return ((data["latitude"] >= lat_med).astype(int) * 2 + (data["longitude"] >= lon_med).astype(int) + 1).astype(int)
    if method in {"checkerboard1", "checkerboard2"}:
        cell = max(float(checkerboard_deg) * (2.0 if method == "checkerboard2" else 1.0), 1e-6)
        ix = np.floor((data["longitude"] - data["longitude"].min()) / cell).astype(int)
        iy = np.floor((data["latitude"] - data["latitude"].min()) / cell).astype(int)
        if method == "checkerboard1":
            return ((ix + iy) % 2 + 1).astype(int)
        return ((ix % 2) * 2 + (iy % 2) + 1).astype(int)
    if method == "jackknife":
        pres = data[data["presence"].astype(int) == 1].copy()
        if pres.empty:
            return pd.Series(np.ones(n, dtype=int), index=data.index)
        pres["jk_group"] = haversine_dbscan(pres, "latitude", "longitude", 2000.0, 1).values + 1
        pres_coords = pres[["latitude", "longitude", "jk_group"]].reset_index(drop=True)
        folds = []
        for _, row in data.iterrows():
            if int(row["presence"]) == 1:
                match = pres[(pres["latitude"] == row["latitude"]) & (pres["longitude"] == row["longitude"])]
                folds.append(int(match["jk_group"].iloc[0]) if not match.empty else 1)
            else:
                coord = (float(row["latitude"]), float(row["longitude"]))
                d = pres_coords.apply(lambda r: geodesic(coord, (float(r["latitude"]), float(r["longitude"]))).m, axis=1)
                folds.append(int(pres_coords.loc[d.idxmin(), "jk_group"]))
        return pd.Series(folds, index=data.index).astype(int)
    if method == "user-defined fold column" and user_fold_col and user_fold_col in data.columns:
        return pd.factorize(data[user_fold_col].astype(str))[0] + 1
    return pd.Series(np.ones(n, dtype=int), index=data.index)


def fit_ensemble_sdm(train_df: pd.DataFrame, variables: list[str], algorithms: list[str], partition_method: str, k_folds: int, checkerboard_deg: float, user_fold_col: Optional[str], status=None, progress=None, start: float = 0.0, span: float = 0.2) -> dict[str, Any]:
    data = train_df.copy()
    y = pd.to_numeric(data["presence"], errors="coerce")
    mask = y.isin([0, 1])
    data = data.loc[mask].copy()
    data["presence"] = y.loc[mask].astype(int)
    if data["presence"].nunique() < 2:
        raise ValueError("SDM training data must contain both presence=1 and background=0 rows.")
    data["cv_fold"] = make_spatial_folds(data, partition_method, k_folds, checkerboard_deg, user_fold_col).values
    X_all = data[variables].apply(pd.to_numeric, errors="coerce")
    y_all = data["presence"].astype(int)
    models = {}
    metrics = []
    unique_folds = sorted([f for f in data["cv_fold"].dropna().unique()])
    total = max(len(algorithms), 1)
    valid_fold_count = 0
    for alg_i, alg in enumerate(algorithms, start=1):
        if status is not None:
            status.write(f"Evaluating {alg} with {partition_method}...")
        fold_aucs = []
        for fold in unique_folds:
            test_mask = data["cv_fold"].eq(fold)
            train_mask = ~test_mask
            if test_mask.sum() < 2 or train_mask.sum() < 2:
                continue
            if data.loc[test_mask, "presence"].nunique() < 2 or data.loc[train_mask, "presence"].nunique() < 2:
                continue
            model = make_model(alg)
            model.fit(X_all.loc[train_mask], y_all.loc[train_mask])
            auc = roc_auc_score(y_all.loc[test_mask], model.predict_proba(X_all.loc[test_mask])[:, 1])
            fold_aucs.append(float(auc))
            metrics.append({"algorithm": alg, "partition_method": partition_method, "fold": int(fold), "auc": round(float(auc), 3), "warning": auc_warning(float(auc), partition_method)})
        valid_fold_count = max(valid_fold_count, len(fold_aucs))
        mean_auc = float(np.mean(fold_aucs)) if fold_aucs else np.nan
        metrics.append({"algorithm": alg, "partition_method": partition_method, "fold": "mean", "auc": round(mean_auc, 3) if np.isfinite(mean_auc) else np.nan, "warning": auc_warning(mean_auc, partition_method) if np.isfinite(mean_auc) else "no valid folds"})
        final_model = make_model(alg)
        final_model.fit(X_all, y_all)
        models[alg] = final_model
        if progress is not None:
            progress.progress(min(1.0, start + span * alg_i / total))
    if valid_fold_count < 2:
        X_train, X_test, y_train, y_test = train_test_split(X_all, y_all, test_size=0.25, random_state=42, stratify=y_all)
        for alg in algorithms:
            model = make_model(alg)
            model.fit(X_train, y_train)
            auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
            metrics.append({"algorithm": alg, "partition_method": "fallback random holdout", "fold": "diagnostic", "auc": round(float(auc), 3), "warning": auc_warning(float(auc), "random k-fold")})
    return {"models": models, "metrics": pd.DataFrame(metrics), "variables": variables, "partition_method": partition_method, "training_table": data}


def predict_ensemble_suitability(table: pd.DataFrame, sdm_result: Optional[dict[str, Any]]) -> pd.DataFrame:
    out = table.copy()
    if not sdm_result or out.empty:
        out["sdm_suitability"] = np.nan
        return out
    variables = sdm_result["variables"]
    missing = [v for v in variables if v not in out.columns]
    if missing:
        out["sdm_suitability"] = np.nan
        out["sdm_note"] = f"Missing environmental variables: {', '.join(missing)}"
        return out
    X = out[variables].apply(pd.to_numeric, errors="coerce")
    preds = [model.predict_proba(X)[:, 1] for model in sdm_result["models"].values()]
    out["sdm_suitability"] = np.mean(np.vstack(preds), axis=0).round(3) if preds else np.nan
    out["sdm_note"] = "Ensemble mean suitability from selected algorithms."
    return out


def update_priority_with_sdm(sites: pd.DataFrame, sdm_weight: float, occurrence_weight_final: float) -> pd.DataFrame:
    out = sites.copy()
    base = pd.to_numeric(out.get("priority_score", 0.5), errors="coerce").fillna(0.5)
    occ = pd.to_numeric(out.get("occurrence_support_score", 0), errors="coerce").fillna(0)
    sdm = pd.to_numeric(out.get("sdm_suitability", base), errors="coerce").fillna(base)
    out["priority_score_pre_sdm"] = base
    out["priority_score"] = ((1 - sdm_weight) * base + sdm_weight * sdm + occurrence_weight_final * occ).clip(0, 1).round(3)
    return out


def min_distance_to_points(coord: tuple[float, float], point_df: pd.DataFrame, lat_col: str, lon_col: str) -> float:
    if point_df is None or point_df.empty:
        return float("inf")
    return min(geodesic(coord, (float(r[lat_col]), float(r[lon_col]))).m for _, r in point_df.iterrows())


def make_sdm_exploration_candidates(prediction_table: pd.DataFrame, known_occ: pd.DataFrame, occurrence_candidates: pd.DataFrame, min_suitability: float, quantile_cutoff: float, min_distance_known_m: float, cluster_distance_m: float, max_candidates: int, start_site_id: int, survey_range_radius_m: float, status=None, progress=None) -> pd.DataFrame:
    columns = list(occurrence_candidates.columns)
    if prediction_table is None or prediction_table.empty or "sdm_suitability" not in prediction_table.columns:
        return pd.DataFrame(columns=columns)
    if status is not None:
        status.write("Selecting exploration ranges from raster prediction map...")
    pred = filter_to_land(prediction_table.copy(), "latitude", "longitude", range_radius_m=survey_range_radius_m)
    pred = pred.dropna(subset=["sdm_suitability"]).copy()
    if pred.empty:
        return pd.DataFrame(columns=columns)
    q = pred["sdm_suitability"].quantile(float(quantile_cutoff))
    pred = pred[pred["sdm_suitability"] >= max(float(min_suitability), float(q))].copy()
    if pred.empty:
        return pd.DataFrame(columns=columns)
    occ_points = known_occ[["_latitude", "_longitude"]].dropna().copy()
    cand_points = occurrence_candidates[["latitude", "longitude"]].dropna().copy() if not occurrence_candidates.empty else pd.DataFrame(columns=["latitude", "longitude"])
    keep = []
    min_dists = []
    for _, row in pred.iterrows():
        coord = (float(row["latitude"]), float(row["longitude"]))
        d = min(min_distance_to_points(coord, occ_points, "_latitude", "_longitude"), min_distance_to_points(coord, cand_points, "latitude", "longitude"))
        keep.append(d >= float(min_distance_known_m))
        min_dists.append(round(d))
    pred["distance_to_nearest_known_m"] = min_dists
    pred = pred[pd.Series(keep, index=pred.index)].copy()
    if pred.empty:
        return pd.DataFrame(columns=columns)
    pred["exploration_cluster"] = haversine_dbscan(pred, "latitude", "longitude", cluster_distance_m, 1)
    rows = []
    for i, (_, group) in enumerate(pred.groupby("exploration_cluster", sort=True), start=0):
        best = group.sort_values("sdm_suitability", ascending=False).iloc[0]
        site_id = start_site_id + i
        rows.append({"site_id": site_id, "candidate_type": "SDM-high exploration survey range", "cluster_id": int(best["exploration_cluster"]), "latitude": float(best["latitude"]), "longitude": float(best["longitude"]), "n_occurrences": 0, "occurrence_support_score": 0.0, "species_summary": "", "year_min": None, "year_max": None, "representative_gbif_id": "", "representative_media_url": "", "representative_locality": "", "candidate_method": "Raster predict-map suitability maximum", "selection_reason": f"Selected from raster SDM predict map because ensemble suitability is high ({float(best['sdm_suitability']):.3f}) and no known occurrence/candidate exists within {int(min_distance_known_m)} m.", "bias_warning": "Exploratory island/coastal SDM candidate. High suitability does not guarantee presence; field validation is required.", "priority_score": round(float(best["sdm_suitability"]), 3), "sdm_suitability": round(float(best["sdm_suitability"]), 3), "distance_to_nearest_known_m": float(best["distance_to_nearest_known_m"])})
    out = pd.DataFrame(rows).sort_values("sdm_suitability", ascending=False).head(int(max_candidates)).reset_index(drop=True)
    for col in columns:
        if col not in out.columns:
            out[col] = np.nan
    if progress is not None:
        progress.progress(0.98)
    return out


def image_html(url: str, width: int = 220) -> str:
    url = first_url(url)
    if not url:
        return ""
    return f"<br><img src='{url}' style='max-width:{width}px; max-height:180px; border-radius:6px; margin-top:6px;'>"


def popup_html_occurrence(row: pd.Series) -> str:
    gbif_id = row.get("_gbif_id", "")
    gbif_link = f"<br><a href='https://www.gbif.org/occurrence/{gbif_id}' target='_blank'>Open GBIF record</a>" if gbif_id else ""
    return f"""
    <b>Occurrence</b><br>
    Latitude: {row['_latitude']:.6f}<br>
    Longitude: {row['_longitude']:.6f}<br>
    Cluster: {row.get('cluster_id', '')}<br>
    Species: {row.get('_species', '')}<br>
    Event date: {row.get('_event_date', '')}<br>
    Locality: {row.get('_locality', '')}
    {gbif_link}
    {image_html(row.get('_media_url', ''))}
    """


def popup_html_site(row: pd.Series) -> str:
    point_url = row.get("google_maps_point_url", "")
    nav = f"<br><a href='{point_url}' target='_blank'>Open center in Google Maps</a>" if point_url else ""
    sdm_line = f"<br>SDM suitability: {row.get('sdm_suitability', '')}" if "sdm_suitability" in row.index else ""
    return f"""
    <b>Survey range {int(row['site_id'])}</b><br>
    Type: {row.get('candidate_type', '')}<br>
    Priority rank: {row.get('priority_rank', '')}<br>
    Route order: {int(row.get('route_order', row['site_id']))}<br>
    Priority score: {row.get('priority_score', '')}<br>
    Occurrence support: {row.get('occurrence_support_score', '')}<br>
    Occurrence records: {int(row.get('n_occurrences', 0))}{sdm_line}<br>
    Center latitude: {row['latitude']:.6f}<br>
    Center longitude: {row['longitude']:.6f}<br>
    Bias / limitation note: {row.get('bias_warning', '')}<br>
    Reason: {row.get('selection_reason', '')}
    {nav}
    {image_html(row.get('representative_media_url', ''))}
    """


def midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def fit_bounds_or_default(df: pd.DataFrame) -> tuple[list[list[float]], tuple[float, float], int]:
    if df.empty:
        return [[35.0, 135.0], [36.0, 136.0]], (35.5, 135.5), 6
    min_lat, max_lat = df["_latitude"].min(), df["_latitude"].max()
    min_lon, max_lon = df["_longitude"].min(), df["_longitude"].max()
    return [[min_lat, min_lon], [max_lat, max_lon]], ((min_lat + max_lat) / 2, (min_lon + max_lon) / 2), 8


def build_map(occurrences: pd.DataFrame, sites: pd.DataFrame, prediction_overlay: Optional[dict[str, Any]], route_plan: Optional[pd.DataFrame], buffer_radius_m: float, survey_range_radius_m: float, show_occurrences: bool, show_buffers: bool, show_clusters: bool, show_occurrence_candidate_sites: bool, show_sdm_candidate_sites: bool, show_routes: bool, show_distance_labels: bool, show_prediction_layer: bool, show_daily_route_layers: bool) -> folium.Map:
    bounds, center, zoom = fit_bounds_or_default(occurrences)
    fmap = Map(location=center, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)
    colors = ["red", "orange", "green", "purple", "cadetblue", "darkred", "darkgreen", "darkblue", "pink", "gray"]
    if show_prediction_layer and prediction_overlay is not None:
        folium.raster_layers.ImageOverlay(
            image=prediction_overlay["image"],
            bounds=prediction_overlay["bounds"],
            opacity=0.68,
            name="SDM predict map",
            interactive=True,
            cross_origin=False,
            zindex=1,
        ).add_to(fmap)
    if show_buffers:
        group = FeatureGroup(name="Occurrence buffers", show=True)
        for _, row in occurrences.iterrows():
            folium.Circle(location=(row["_latitude"], row["_longitude"]), radius=float(buffer_radius_m), color="#7aa6ff", weight=1, fill=True, fill_opacity=0.08, opacity=0.35).add_to(group)
        group.add_to(fmap)
    if show_occurrences:
        group = FeatureGroup(name="Occurrences", show=True)
        marker_cluster = MarkerCluster(name="Occurrence marker cluster")
        for _, row in occurrences.iterrows():
            folium.CircleMarker(location=(row["_latitude"], row["_longitude"]), radius=4, color="#1f77b4", fill=True, fill_color="#1f77b4", fill_opacity=0.75, weight=1, popup=folium.Popup(popup_html_occurrence(row), max_width=330)).add_to(marker_cluster)
        marker_cluster.add_to(group)
        group.add_to(fmap)
    if show_clusters:
        group = FeatureGroup(name="Occurrence clusters", show=True)
        for _, row in occurrences.iterrows():
            label = int(row["cluster_id"])
            color = "black" if label < 0 else colors[label % len(colors)]
            folium.CircleMarker(location=(row["_latitude"], row["_longitude"]), radius=6, color=color, fill=True, fill_color=color, fill_opacity=0.45, weight=2, popup=f"Cluster: {label}").add_to(group)
        group.add_to(fmap)
    if show_routes and len(sites) >= 2:
        group = FeatureGroup(name="Route between survey-range centers", show=True)
        folium.PolyLine(list(zip(sites["latitude"], sites["longitude"])), color="red", weight=3, opacity=0.7).add_to(group)
        group.add_to(fmap)
    if show_daily_route_layers and route_plan is not None and not route_plan.empty:
        day_colors = ["blue", "green", "purple", "orange", "darkred", "cadetblue", "darkgreen", "pink"]
        for day, day_df in route_plan.groupby("survey_day"):
            day_df = day_df.sort_values("day_route_order")
            color = day_colors[(int(day) - 1) % len(day_colors)]
            group = FeatureGroup(name=f"Sampling route Day {int(day)}", show=True)
            coords = list(zip(day_df["latitude"], day_df["longitude"]))
            if len(coords) >= 2:
                folium.PolyLine(coords, color=color, weight=4, opacity=0.75).add_to(group)
            for _, row in day_df.iterrows():
                folium.CircleMarker(location=(row["latitude"], row["longitude"]), radius=7, color=color, fill=True, fill_color=color, fill_opacity=0.85, popup=folium.Popup(popup_html_site(row), max_width=460), tooltip=f"Day {int(day)} - stop {int(row['day_route_order'])}").add_to(group)
            group.add_to(fmap)
    if show_distance_labels and len(sites) >= 2:
        group = FeatureGroup(name="Straight-line distance labels", show=True)
        route_coords = list(zip(sites["latitude"], sites["longitude"]))
        for i in range(len(route_coords) - 1):
            a, b = route_coords[i], route_coords[i + 1]
            folium.Marker(location=midpoint(a, b), icon=folium.DivIcon(html=f"<div style='font-size:12px;font-weight:700;background:white;border:1px solid #999;border-radius:4px;padding:2px 5px;white-space:nowrap;'>{geodesic(a, b).km:.1f} km</div>")).add_to(group)
        group.add_to(fmap)
    if show_occurrence_candidate_sites:
        group = FeatureGroup(name="Occurrence-supported survey ranges", show=True)
        subset = sites[~sites.get("candidate_type", pd.Series(dtype=str)).astype(str).str.startswith("SDM-high")]
        for _, row in subset.iterrows():
            folium.Circle(location=(row["latitude"], row["longitude"]), radius=float(survey_range_radius_m), color="#d62728", weight=2, fill=True, fill_color="#d62728", fill_opacity=0.14, popup=folium.Popup(popup_html_site(row), max_width=460), tooltip=f"Survey range {int(row['site_id'])} / occurrence-supported").add_to(group)
            folium.CircleMarker(location=(row["latitude"], row["longitude"]), radius=3, color="#7f0000", fill=True, fill_color="#7f0000", fill_opacity=1).add_to(group)
        group.add_to(fmap)
    if show_sdm_candidate_sites:
        group = FeatureGroup(name="SDM-high exploration survey ranges", show=True)
        subset = sites[sites.get("candidate_type", pd.Series(dtype=str)).astype(str).str.startswith("SDM-high")]
        for _, row in subset.iterrows():
            folium.Circle(location=(row["latitude"], row["longitude"]), radius=float(survey_range_radius_m), color="#2ca02c", weight=2, fill=True, fill_color="#2ca02c", fill_opacity=0.16, popup=folium.Popup(popup_html_site(row), max_width=460), tooltip=f"Survey range {int(row['site_id'])} / SDM exploration").add_to(group)
            folium.CircleMarker(location=(row["latitude"], row["longitude"]), radius=3, color="#006400", fill=True, fill_color="#006400", fill_opacity=1).add_to(group)
        group.add_to(fmap)
    LayerControl(collapsed=True).add_to(fmap)
    try:
        fmap.fit_bounds(bounds, padding=(30, 30))
    except Exception:
        pass
    return fmap


def load_input_controls() -> None:
    mode = st.sidebar.radio("Input source", ["Upload coordinate CSV", "Search GBIF by scientific name"], index=1, key="input_source_mode")
    if st.sidebar.button("Clear loaded data"):
        clear_loaded_data()
    if mode == "Upload coordinate CSV":
        uploaded = st.sidebar.file_uploader("Upload CSV with latitude/longitude columns", type=["csv"], key="csv_upload")
        if uploaded is not None:
            file_key = f"upload::{uploaded.name}::{uploaded.size}"
            if st.session_state.source_key != file_key:
                st.session_state.raw_df = read_uploaded_csv(uploaded)
                st.session_state.source_message = f"Loaded coordinate CSV: {uploaded.name} ({len(st.session_state.raw_df):,} raw rows)."
                st.session_state.source_key = file_key
        return
    scientific_name = st.sidebar.text_input("Scientific name", value="", placeholder="e.g. Campanula punctata", key="gbif_scientific_name")
    country_code = st.sidebar.text_input("Country code filter optional", value="JP", max_chars=2, key="gbif_country")
    max_records = st.sidebar.number_input("Maximum GBIF records", min_value=100, max_value=100_000, value=5000, step=500, key="gbif_max_records")
    use_year_filter = st.sidebar.checkbox("Filter by year", value=False, key="gbif_use_year")
    year_from = None
    year_to = None
    if use_year_filter:
        c1, c2 = st.sidebar.columns(2)
        with c1:
            year_from = int(st.number_input("From", min_value=1600, max_value=2100, value=2000, step=1, key="gbif_year_from"))
        with c2:
            year_to = int(st.number_input("To", min_value=1600, max_value=2100, value=2026, step=1, key="gbif_year_to"))
    if st.sidebar.button("Fetch occurrences from GBIF", type="primary"):
        if not scientific_name.strip():
            st.warning("Scientific name is empty.")
            return
        with st.spinner("Fetching GBIF occurrences..."):
            match, df = fetch_gbif_occurrences_cached(scientific_name.strip(), int(max_records), country_code.strip().upper(), year_from, year_to)
        st.session_state.raw_df = df.copy()
        st.session_state.source_message = f"GBIF match: {match.matched_name or match.input_name} / usageKey={match.usage_key} / confidence={match.confidence}. Fetched {len(df):,} raw occurrence records."
        st.session_state.source_key = f"gbif::{scientific_name.strip()}::{country_code.strip().upper()}::{int(max_records)}::{year_from}::{year_to}"


def environment_sdm_panel(occ: pd.DataFrame, occurrence_candidates: pd.DataFrame, raw_columns: list[str], survey_range_radius_m: float, occurrence_weight_final: float) -> tuple[pd.DataFrame, Optional[dict[str, Any]], Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[dict[str, Any]]]:
    st.subheader("Environment variables and ensemble SDM")
    st.caption("The predict map now uses a raster-like 2D array matched to the selected WorldClim raster window, then displays it as an ImageOverlay.")
    with st.expander("Island SDM and GBIF-bias notes", expanded=False):
        st.markdown("""
        - For island survey planning, predicting all land inside the occurrence-region bounding box is often more practical than tiny buffers around records.
        - GBIF record density is useful for prioritizing known/accessible survey areas, but it also contains observer/access bias.
        - Random split AUC can be optimistic; block/checkerboard/jackknife diagnostics are shown because island SDM validation is itself a methodological gap.
        - The map is a Python equivalent of an R `predict()`-style raster prediction, but simplified for Streamlit/Folium.
        """)
    with st.expander("SDM settings", expanded=True):
        resolution = st.selectbox("WorldClim raster resolution", RESOLUTIONS, index=2, help="WorldClim 10m means 10 arc-minutes, not 10 meters.")
        st.caption(f"Selected resolution: {RESOLUTION_NOTE[resolution]}")
        st.markdown("<span style='color:#8c510a;font-weight:700'>Topography variables</span>", unsafe_allow_html=True)
        selected_topo_vars = st.multiselect("Topography variables", TOPOGRAPHY_VARS, default=[])
        st.markdown("<span style='color:#2166ac;font-weight:700'>Climate variables</span>", unsafe_allow_html=True)
        selected_climate_vars = st.multiselect("Climate variables", CLIMATE_VARS, default=[])
        selected_web_vars = selected_topo_vars + selected_climate_vars
        algorithms = st.multiselect("Ensemble algorithms", ALGORITHMS, default=[])
        partition_method = st.selectbox("Spatial partition method for AUC", PARTITION_METHODS, index=1)
        k_folds = st.number_input("k for random k-fold", min_value=2, max_value=20, value=5, step=1)
        checkerboard_deg = st.number_input("Checkerboard cell size (degrees)", min_value=0.001, max_value=5.0, value=0.05, step=0.01, format="%.3f")
        user_fold_col = None
        if partition_method == "user-defined fold column":
            user_fold_col = st.selectbox("Fold column", options=[""] + raw_columns, index=0) or None
        vif_threshold = st.number_input("VIF threshold", min_value=1.0, max_value=100.0, value=10.0, step=1.0)
        use_vif = st.checkbox("Apply VIF stepwise filtering", value=True)
        n_background = st.number_input("Number of land-only background points", min_value=100, max_value=20000, value=500, step=100)
        pred_mode = st.selectbox("Prediction extent mode", PRED_EXTENT_MODES, index=0)
        bbox_expansion_km = st.number_input("Bounding-box expansion for prediction/background (km)", min_value=0.0, max_value=500.0, value=20.0, step=5.0)
        occurrence_buffer_km = st.number_input("Occurrence buffer for buffer/hull modes (km)", min_value=0.1, max_value=500.0, value=10.0, step=1.0)
        max_prediction_pixels = st.number_input("Maximum predict-map pixels", min_value=2_000, max_value=500_000, value=80_000, step=10_000, help="Large values look smoother but can be slow. The app automatically downsamples the raster window if needed.")
        sdm_weight = st.slider("SDM weight in final priority", 0.0, 1.0, 0.35, 0.05)
    if not selected_web_vars:
        st.info("Select environmental variables before running SDM. Island first trial: elevation + bio19, then add more variables carefully.")
        return occurrence_candidates.copy(), None, st.session_state.get("sdm_train_table"), st.session_state.get("vif_table"), st.session_state.get("prediction_table"), st.session_state.get("prediction_overlay")
    if not algorithms:
        st.info("Select at least one SDM algorithm before running SDM.")
        return occurrence_candidates.copy(), None, st.session_state.get("sdm_train_table"), st.session_state.get("vif_table"), st.session_state.get("prediction_table"), st.session_state.get("prediction_overlay")
    progress = st.progress(0.0)
    status = st.empty()
    if st.button("Build environment table and run ensemble SDM", type="primary"):
        try:
            status.write("Step 1/6: generating land-only presence/background table...")
            progress.progress(0.05)
            pb = build_presence_background_from_occurrences(occ, int(n_background), float(bbox_expansion_km), status=status)
            status.write("Step 2/6: extracting raster values for training data...")
            env_train = extract_web_environment(pb, selected_web_vars, "latitude", "longitude", resolution, status=status, progress=progress, start=0.10, span=0.30)
            status.write(f"Step 3/6: running VIF stepwise filtering; threshold = {vif_threshold}...")
            if use_vif and len(selected_web_vars) > 1:
                kept_vars, vif_table = vif_step(env_train, selected_web_vars, threshold=float(vif_threshold), status=status, progress=progress, start=0.42, span=0.10)
            else:
                kept_vars = selected_web_vars
                vif_table = compute_vif_table(env_train, selected_web_vars) if len(selected_web_vars) > 1 else pd.DataFrame({"variable": selected_web_vars, "vif": [1.0], "vif_warning": [""], "status": ["kept"]})
            status.write("Step 4/6: fitting selected ensemble SDM algorithms and spatial partition diagnostics...")
            sdm_result = fit_ensemble_sdm(env_train, kept_vars, algorithms, partition_method, int(k_folds), float(checkerboard_deg), user_fold_col, status=status, progress=progress, start=0.54, span=0.18)
            status.write("Step 5/6: predicting a raster-style SDM map from raster windows...")
            overlay, pred_table = build_sdm_predict_raster(occ, kept_vars, resolution, sdm_result, pred_mode, float(bbox_expansion_km), float(occurrence_buffer_km), int(max_prediction_pixels), status=status)
            progress.progress(0.92)
            st.session_state.sdm_train_table = sdm_result.get("training_table", env_train)
            st.session_state.prediction_table = pred_table
            st.session_state.prediction_overlay = overlay
            st.session_state.sdm_result = sdm_result
            st.session_state.vif_table = vif_table
            status.write("Step 6/6: SDM predict map complete.")
            progress.progress(1.0)
        except Exception as exc:
            status.write("SDM failed.")
            st.error(f"SDM failed: {exc}")
    env_train = st.session_state.get("sdm_train_table")
    pred_table = st.session_state.get("prediction_table")
    overlay = st.session_state.get("prediction_overlay")
    sdm_result = st.session_state.get("sdm_result")
    vif_table = st.session_state.get("vif_table")
    if vif_table is not None:
        st.write("VIF table")
        st.dataframe(vif_table, width="stretch", hide_index=True)
    if sdm_result is None:
        return occurrence_candidates.copy(), None, env_train, vif_table, pred_table, overlay
    st.success("Ensemble SDM predict map is available.")
    if overlay is not None:
        st.caption(f"Predict map array: {overlay.get('shape')} cells, source raster stride={overlay.get('source_stride')}")
    st.write("AUC diagnostics")
    st.dataframe(sdm_result["metrics"], width="stretch", hide_index=True)
    candidates_env = occurrence_candidates.copy()
    try:
        tmp = candidates_env.rename(columns={"latitude": "lat_tmp", "longitude": "lon_tmp"})
        tmp = extract_web_environment(tmp, sdm_result["variables"], "lat_tmp", "lon_tmp", resolution, status=status, progress=progress, start=0.0, span=0.2)
        candidates_env = tmp.rename(columns={"lat_tmp": "latitude", "lon_tmp": "longitude"})
    except Exception as exc:
        st.warning(f"Could not extract environment for occurrence-supported survey ranges: {exc}")
    candidates_env = predict_ensemble_suitability(candidates_env, sdm_result)
    candidates_env = update_priority_with_sdm(candidates_env, float(sdm_weight), float(occurrence_weight_final))
    st.markdown("### SDM-high / occurrence-low exploration survey ranges")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        min_suitability = st.number_input("Minimum suitability", min_value=0.0, max_value=1.0, value=0.60, step=0.05)
    with c2:
        quantile_cutoff = st.number_input("Predict-map suitability quantile", min_value=0.0, max_value=0.99, value=0.90, step=0.01)
    with c3:
        min_dist_known = st.number_input("Minimum distance from known records/ranges (m)", min_value=0, max_value=200_000, value=3000, step=500)
    with c4:
        max_new = st.number_input("Max new exploration ranges", min_value=1, max_value=200, value=20, step=1)
    cluster_m = st.number_input("Exploration clustering distance (m)", min_value=100, max_value=200_000, value=3000, step=500)
    exploration = pd.DataFrame()
    if pred_table is not None:
        exploration = make_sdm_exploration_candidates(pred_table, occ, candidates_env, float(min_suitability), float(quantile_cutoff), float(min_dist_known), float(cluster_m), int(max_new), int(candidates_env["site_id"].max()) + 1 if not candidates_env.empty else 1, float(survey_range_radius_m), status=status, progress=progress)
    if not exploration.empty:
        st.success(f"Generated {len(exploration)} SDM-high / occurrence-low exploration survey ranges.")
        st.dataframe(exploration.sort_values("sdm_suitability", ascending=False), width="stretch", hide_index=True)
        candidates_env = pd.concat([candidates_env, exploration], ignore_index=True, sort=False)
    else:
        st.info("No new exploration ranges were generated with current thresholds.")
    return candidates_env, sdm_result, env_train, vif_table, pred_table, overlay


def make_field_validation_template(sites: pd.DataFrame) -> pd.DataFrame:
    cols = ["site_id", "candidate_type", "priority_rank", "route_order", "latitude", "longitude", "priority_score", "occurrence_support_score", "sdm_suitability", "visited", "survey_date", "observer", "access_success", "target_species_found", "abundance_count", "abundance_class", "flowering_status", "population_area_m2", "habitat_note", "photo_file", "comments"]
    base = sites.copy()
    for col in cols:
        if col not in base.columns:
            base[col] = ""
    return base[cols]


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🗺️", layout="wide")
    init_session_state()
    st.title("🗺️ GBIF FieldMap Builder")
    st.caption("Island-aware survey planning from GBIF/coordinate occurrences, raster-style SDM predict maps, spatial diagnostics, and survey-day route plans.")
    st.sidebar.header("Data source")
    load_input_controls()
    st.sidebar.divider()
    st.sidebar.subheader("Sampling design")
    thinning_m = st.sidebar.number_input("Spatial thinning distance before clustering (m)", min_value=0, max_value=50_000, value=1000, step=500)
    candidate_method = st.sidebar.selectbox("Candidate range center method", ["Medoid", "Centroid"], index=0)
    buffer_radius_m = st.sidebar.number_input("Buffer radius around occurrences (m)", 0, 100_000, 500, 100)
    survey_range_radius_m = st.sidebar.number_input("Survey range radius around candidate centers (m)", 50, 50_000, 500, 50)
    dbscan_threshold_m = st.sidebar.number_input("DBSCAN cluster distance threshold (m)", 1, 500_000, 2000, 500)
    min_samples = st.sidebar.number_input("Minimum occurrences per cluster", 1, 50, 1, 1)
    occurrence_weight = st.sidebar.slider("Occurrence record-count weight for occurrence candidates", 0.0, 0.60, 0.35, 0.05)
    occurrence_weight_final = st.sidebar.slider("Extra occurrence-support weight in final priority", 0.0, 0.30, 0.10, 0.05)
    route_order_mode = st.sidebar.selectbox("Survey range order", ["Cluster ID", "Priority score", "Nearest-neighbor route", "North → South", "South → North", "West → East", "East → West"], index=2)
    priority_top_n = st.sidebar.number_input("Show top N priority ranges", min_value=1, max_value=100, value=10, step=1)
    st.sidebar.divider()
    st.sidebar.subheader("Layers")
    show_prediction_layer = st.sidebar.checkbox("SDM predict map", value=True)
    show_occurrences = st.sidebar.checkbox("Occurrences", value=True)
    show_buffers = st.sidebar.checkbox("Occurrence buffers", value=False)
    show_clusters = st.sidebar.checkbox("Occurrence clusters", value=False)
    show_occurrence_candidate_sites = st.sidebar.checkbox("Occurrence-supported survey ranges", value=True)
    show_sdm_candidate_sites = st.sidebar.checkbox("SDM-high exploration survey ranges", value=True)
    show_routes = st.sidebar.checkbox("Routes between range centers", value=False)
    show_daily_route_layers = st.sidebar.checkbox("Daily sampling route layers", value=True)
    show_distance_labels = st.sidebar.checkbox("Straight-line distance labels", value=True)
    raw_df = st.session_state.raw_df
    if raw_df is None:
        st.info(st.session_state.source_message)
        st.markdown("Start by searching GBIF by scientific name, or upload any coordinate CSV. Then run SDM to generate a raster-style predict map, survey ranges, and day-by-day route plans.")
        return
    st.success(st.session_state.source_message)
    try:
        detected = detect_occurrence_columns(raw_df)
        occ_raw = clean_occurrences(raw_df, detected)
    except Exception as exc:
        st.error(str(exc))
        return
    if occ_raw.empty:
        st.error("No valid coordinate records were found after cleaning.")
        return
    occ = spatial_thin(occ_raw, float(thinning_m))
    occ["cluster_id"] = haversine_dbscan(occ, "_latitude", "_longitude", float(dbscan_threshold_m), int(min_samples))
    occurrence_candidates = make_candidate_sites(occ, candidate_method, float(thinning_m), float(occurrence_weight))
    occurrence_candidates = add_priority_rank(occurrence_candidates)
    occurrence_candidates = add_navigation_columns(order_sites(occurrence_candidates, route_order_mode))
    all_candidates, sdm_result, env_train, vif_table, pred_table, overlay = environment_sdm_panel(occ, occurrence_candidates, list(raw_df.columns), float(survey_range_radius_m), float(occurrence_weight_final))
    all_candidates = filter_to_land(all_candidates, "latitude", "longitude", float(survey_range_radius_m)) if not all_candidates.empty else all_candidates
    all_candidates = add_priority_rank(all_candidates)
    all_candidates = add_navigation_columns(order_sites(all_candidates, route_order_mode))
    route_plan = route_planner_panel(all_candidates)
    route_url = make_google_maps_route_url(all_candidates, travelmode="driving")
    transit_route_url = make_google_maps_route_url(all_candidates, travelmode="transit")
    total_clusters = int(occ.loc[occ["cluster_id"] >= 0, "cluster_id"].nunique()) if not occ.empty else 0
    noise_points = int((occ["cluster_id"] < 0).sum()) if not occ.empty else 0
    n_explore = int(all_candidates.get("candidate_type", pd.Series(dtype=str)).astype(str).str.startswith("SDM-high").sum()) if not all_candidates.empty else 0
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Raw valid records", f"{len(occ_raw):,}")
    col2.metric("After thinning", f"{len(occ):,}")
    col3.metric("Occurrence clusters", f"{total_clusters:,}")
    col4.metric("Occurrence ranges", f"{len(occurrence_candidates):,}")
    col5.metric("SDM exploration ranges", f"{n_explore:,}")
    col6.metric("Noise points", f"{noise_points:,}")
    if route_url:
        c1, c2 = st.columns(2)
        with c1:
            st.link_button("Open all-candidate driving route in Google Maps", route_url, width="stretch")
        with c2:
            st.link_button("Open all-candidate public-transit route in Google Maps", transit_route_url, width="stretch")
    with st.expander("Detected input columns", expanded=False):
        st.write(detected.__dict__)
    fmap = build_map(occ, all_candidates, overlay, route_plan, float(buffer_radius_m), float(survey_range_radius_m), show_occurrences, show_buffers, show_clusters, show_occurrence_candidate_sites, show_sdm_candidate_sites, show_routes, show_distance_labels, show_prediction_layer, show_daily_route_layers)
    st_folium(fmap, width=None, height=720, returned_objects=[])
    st.subheader("Priority survey ranges")
    priority_cols = ["priority_rank", "site_id", "candidate_type", "route_order", "priority_score", "occurrence_support_score", "sdm_suitability", "distance_to_nearest_known_m", "n_occurrences", "latitude", "longitude", "bias_warning", "selection_reason"]
    priority_cols = [c for c in priority_cols if c in all_candidates.columns]
    priority_sites = all_candidates.sort_values(["priority_rank"]).head(int(priority_top_n)) if not all_candidates.empty else all_candidates
    if not priority_sites.empty:
        st.dataframe(priority_sites[priority_cols], width="stretch", hide_index=True)
    st.subheader("All survey ranges")
    st.dataframe(all_candidates, width="stretch", hide_index=True)
    validation_template = make_field_validation_template(all_candidates)
    html_bytes = fmap.get_root().render().encode("utf-8")
    candidates_csv = all_candidates.to_csv(index=False).encode("utf-8-sig")
    route_plan_csv = route_plan.to_csv(index=False).encode("utf-8-sig") if route_plan is not None and not route_plan.empty else b"survey_day,day_route_order,site_id,latitude,longitude\n"
    validation_csv = validation_template.to_csv(index=False).encode("utf-8-sig")
    sdm_metrics_csv = sdm_result["metrics"].to_csv(index=False).encode("utf-8-sig") if sdm_result else b"algorithm,partition_method,fold,auc,warning\n"
    vif_csv = vif_table.to_csv(index=False).encode("utf-8-sig") if vif_table is not None else b"variable,vif,vif_warning,status\n"
    train_csv = env_train.to_csv(index=False).encode("utf-8-sig") if env_train is not None else b""
    pred_csv = pred_table.to_csv(index=False).encode("utf-8-sig") if pred_table is not None else b""
    dl1, dl2, dl3, dl4 = st.columns(4)
    with dl1:
        st.download_button("Download HTML map", html_bytes, "fieldmap.html", "text/html", width="stretch")
    with dl2:
        st.download_button("Download survey range CSV", candidates_csv, "candidate_survey_ranges.csv", "text/csv", width="stretch")
    with dl3:
        st.download_button("Download sampling route plan", route_plan_csv, "sampling_route_plan.csv", "text/csv", width="stretch")
    with dl4:
        st.download_button("Download validation template", validation_csv, "field_validation_template.csv", "text/csv", width="stretch")
    dl5, dl6, dl7, dl8 = st.columns(4)
    with dl5:
        st.download_button("Download SDM metrics", sdm_metrics_csv, "sdm_metrics.csv", "text/csv", width="stretch")
    with dl6:
        st.download_button("Download VIF table", vif_csv, "vif_table.csv", "text/csv", width="stretch")
    with dl7:
        st.download_button("Download SDM training table", train_csv, "sdm_training_table.csv", "text/csv", width="stretch")
    with dl8:
        st.download_button("Download predict-map table", pred_csv, "sdm_predict_map_table.csv", "text/csv", width="stretch")


if __name__ == "__main__":
    main()
