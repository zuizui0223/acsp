"""Direct coordinate sampling from WorldClim 2.1 30-second rasters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import urllib.request
import zipfile

import numpy as np
import pandas as pd
import rasterio

BASE_URL = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base"
VARIABLES = ("elevation", "bio1", "bio4", "bio12", "bio15")

@dataclass(frozen=True)
class RasterEnvironmentSample:
    frame: pd.DataFrame
    variables: tuple[str, ...]
    source: str = "WorldClim 2.1 30s"


def _archive_for(variable: str) -> tuple[str, str]:
    if variable == "elevation":
        return "wc2.1_30s_elev.zip", "wc2.1_30s_elev.tif"
    if variable.startswith("bio"):
        index = int(variable[3:])
        return "wc2.1_30s_bio.zip", f"wc2.1_30s_bio_{index}.tif"
    raise ValueError(f"unsupported WorldClim variable: {variable}")


def ensure_worldclim_rasters(cache_dir: str | Path, variables: Iterable[str] = VARIABLES) -> dict[str, Path]:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    requested = tuple(dict.fromkeys(map(str, variables)))
    archives: dict[str, Path] = {}
    output: dict[str, Path] = {}
    for variable in requested:
        archive_name, tif_name = _archive_for(variable)
        tif_path = cache / tif_name
        if tif_path.exists() and tif_path.stat().st_size > 0:
            output[variable] = tif_path
            continue
        archive_path = archives.get(archive_name, cache / archive_name)
        if not archive_path.exists() or archive_path.stat().st_size == 0:
            urllib.request.urlretrieve(f"{BASE_URL}/{archive_name}", archive_path)
        archives[archive_name] = archive_path
        with zipfile.ZipFile(archive_path) as archive:
            member = next((name for name in archive.namelist() if name.endswith(tif_name)), None)
            if member is None:
                raise FileNotFoundError(f"{tif_name} not found in {archive_name}")
            with archive.open(member) as src, tif_path.open("wb") as dst:
                dst.write(src.read())
        output[variable] = tif_path
    return output


def sample_worldclim_at_coordinates(
    coordinates: pd.DataFrame,
    *,
    cache_dir: str | Path,
    latitude: str = "latitude",
    longitude: str = "longitude",
    variables: Iterable[str] = VARIABLES,
) -> RasterEnvironmentSample:
    requested = tuple(dict.fromkeys(map(str, variables)))
    if latitude not in coordinates or longitude not in coordinates:
        raise ValueError("coordinate columns are missing")
    frame = coordinates.copy().reset_index(drop=True)
    frame[latitude] = pd.to_numeric(frame[latitude], errors="coerce")
    frame[longitude] = pd.to_numeric(frame[longitude], errors="coerce")
    valid = frame[latitude].between(-90, 90) & frame[longitude].between(-180, 180)
    raster_paths = ensure_worldclim_rasters(cache_dir, requested)
    xy = list(zip(frame.loc[valid, longitude].astype(float), frame.loc[valid, latitude].astype(float)))
    for variable in requested:
        values = np.full(len(frame), np.nan, dtype=float)
        if xy:
            with rasterio.open(raster_paths[variable]) as dataset:
                sampled = np.asarray([row[0] for row in dataset.sample(xy)], dtype=float)
                nodata = dataset.nodata
                if nodata is not None:
                    sampled[np.isclose(sampled, nodata)] = np.nan
                sampled[np.abs(sampled) >= 1e20] = np.nan
                values[np.flatnonzero(valid)] = sampled
        frame[variable] = values
    return RasterEnvironmentSample(frame=frame, variables=requested)
