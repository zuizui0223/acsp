"""Direct sampling of CHELSA v2.1 bioclim COGs at coordinates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
import rasterio

CHELSA_BASE = "https://os.zhdk.cloud.switch.ch/chelsav2/GLOBAL/climatologies/1981-2010/bio"
DEFAULT_VARIABLES = ("bio1", "bio4", "bio12", "bio15")
DEFAULT_SOURCES = {
    variable: f"{CHELSA_BASE}/CHELSA_{variable}_1981-2010_V.2.1.tif"
    for variable in DEFAULT_VARIABLES
}

@dataclass(frozen=True)
class CoordinateRasterSample:
    frame: pd.DataFrame
    variables: tuple[str, ...]
    complete_indices: np.ndarray
    source: str = "CHELSA v2.1 30 arc-second COG"


def sample_chelsa_at_coordinates(
    coordinates: pd.DataFrame,
    *,
    latitude: str = "latitude",
    longitude: str = "longitude",
    variables: Sequence[str] = DEFAULT_VARIABLES,
    sources: Mapping[str, str] | None = None,
) -> CoordinateRasterSample:
    requested = tuple(dict.fromkeys(map(str, variables)))
    source_map = dict(DEFAULT_SOURCES if sources is None else sources)
    missing_sources = [variable for variable in requested if variable not in source_map]
    if missing_sources:
        raise ValueError("missing raster sources: " + ", ".join(missing_sources))
    if latitude not in coordinates or longitude not in coordinates:
        raise ValueError("coordinate columns are missing")

    frame = coordinates.copy().reset_index(drop=True)
    frame[latitude] = pd.to_numeric(frame[latitude], errors="coerce")
    frame[longitude] = pd.to_numeric(frame[longitude], errors="coerce")
    valid = (
        frame[latitude].between(-90, 90)
        & frame[longitude].between(-180, 180)
    )
    valid_indices = np.flatnonzero(valid.to_numpy())
    xy = list(zip(
        frame.loc[valid, longitude].astype(float),
        frame.loc[valid, latitude].astype(float),
    ))

    for variable in requested:
        values = np.full(len(frame), np.nan, dtype=float)
        if xy:
            with rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
            ):
                with rasterio.open(source_map[variable]) as dataset:
                    sampled = np.asarray([sample[0] for sample in dataset.sample(xy)], dtype=float)
                    if dataset.nodata is not None:
                        sampled[np.isclose(sampled, dataset.nodata)] = np.nan
                    sampled[np.abs(sampled) >= 1e20] = np.nan
                    values[valid_indices] = sampled
        frame[variable] = values

    complete = np.flatnonzero(frame[list(requested)].notna().all(axis=1).to_numpy())
    return CoordinateRasterSample(frame=frame, variables=requested, complete_indices=complete)
