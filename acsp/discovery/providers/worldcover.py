"""ESA WorldCover 2021 v200 map provider for experimental discovery.

The official product is distributed as 3 x 3 degree Cloud Optimized GeoTIFF
(COG) tiles. This adapter opens the official HTTPS COGs, reads only the declared
crop, writes a local derivative snapshot, and hashes that derivative for the
source manifest. It does not interpret field outcomes or choose a structural
family.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path

import rasterio
from rasterio.merge import merge

WORLD_COVER_2021_BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
WORLD_COVER_2021_CLASS_NAMES = {
    10: "tree",
    20: "shrub",
    30: "grass",
    40: "crop",
    50: "built",
    60: "bare",
    70: "snow_ice",
    80: "water",
    90: "wetland",
    95: "mangrove",
    100: "moss_lichen",
}


@dataclass(frozen=True)
class WorldCoverCropAudit:
    provider_id: str
    release_id: str
    source_tile_ids: tuple[str, ...]
    source_urls: tuple[str, ...]
    crop_bounds_wgs84: tuple[float, float, float, float]
    output_path: str
    output_sha256: str
    output_bytes: int
    field_outcomes_used: bool = False
    human_access_used: bool = False


def _aligned_lower_left(value: float) -> int:
    return int(math.floor(float(value) / 3.0) * 3)


def _format_lat(value: int) -> str:
    return f"{'N' if int(value) >= 0 else 'S'}{abs(int(value)):02d}"


def _format_lon(value: int) -> str:
    return f"{'E' if int(value) >= 0 else 'W'}{abs(int(value)):03d}"


def worldcover_tile_id(latitude: float, longitude: float) -> str:
    """Return the official 3-degree lower-left tile identifier for one point."""
    lat = float(latitude)
    lon = float(longitude)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("longitude/latitude outside valid range")
    # Points exactly on the upper global limits belong to the last tile.
    if lat == 90.0:
        lat = math.nextafter(90.0, -math.inf)
    if lon == 180.0:
        lon = math.nextafter(180.0, -math.inf)
    lat0 = _aligned_lower_left(lat)
    lon0 = _aligned_lower_left(lon)
    return _format_lat(lat0) + _format_lon(lon0)


def worldcover_tile_ids_for_bounds(bounds: tuple[float, float, float, float]) -> tuple[str, ...]:
    """Return all official tile identifiers intersecting non-dateline WGS84 bounds."""
    west, south, east, north = map(float, bounds)
    if not (-180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0):
        raise ValueError("bounds must satisfy valid west < east and south < north")
    east_inside = math.nextafter(east, -math.inf)
    north_inside = math.nextafter(north, -math.inf)
    lon0 = _aligned_lower_left(west)
    lon1 = _aligned_lower_left(east_inside)
    lat0 = _aligned_lower_left(south)
    lat1 = _aligned_lower_left(north_inside)
    ids = [
        _format_lat(lat) + _format_lon(lon)
        for lat in range(lat0, lat1 + 1, 3)
        for lon in range(lon0, lon1 + 1, 3)
    ]
    return tuple(sorted(set(ids)))


def worldcover_2021_map_url(tile_id: str) -> str:
    token = str(tile_id).strip().upper()
    if len(token) != 7 or token[0] not in {"N", "S"} or token[3] not in {"E", "W"}:
        raise ValueError(f"invalid WorldCover tile identifier: {tile_id!r}")
    return f"{WORLD_COVER_2021_BASE}/ESA_WorldCover_10m_2021_v200_{token}_Map.tif"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expanded_bounds(bounds: tuple[float, float, float, float], margin_m: float) -> tuple[float, float, float, float]:
    west, south, east, north = map(float, bounds)
    if margin_m < 0:
        raise ValueError("margin_m cannot be negative")
    center_lat = (south + north) / 2.0
    lat_pad = float(margin_m) / 111_320.0
    lon_pad = lat_pad / max(0.05, math.cos(math.radians(center_lat)))
    return (
        max(-180.0, west - lon_pad),
        max(-90.0, south - lat_pad),
        min(180.0, east + lon_pad),
        min(90.0, north + lat_pad),
    )


def build_worldcover_2021_map_crop(
    bounds: tuple[float, float, float, float],
    output: Path,
    *,
    margin_m: float = 500.0,
) -> WorldCoverCropAudit:
    """Create and hash a local crop from official WorldCover 2021 map COGs."""
    output = Path(output)
    crop_bounds = _expanded_bounds(bounds, float(margin_m))
    tile_ids = worldcover_tile_ids_for_bounds(crop_bounds)
    urls = tuple(worldcover_2021_map_url(tile_id) for tile_id in tile_ids)
    datasets = []
    try:
        for url in urls:
            datasets.append(rasterio.open(url))
        if not datasets:
            raise RuntimeError("no WorldCover tiles resolved for bounds")
        mosaic, transform = merge(datasets, bounds=crop_bounds)
        if mosaic.shape[0] != 1:
            raise RuntimeError(f"WorldCover map crop expected one band, found {mosaic.shape[0]}")
        profile = datasets[0].profile.copy()
        profile.update(
            driver="GTiff",
            height=int(mosaic.shape[1]),
            width=int(mosaic.shape[2]),
            transform=transform,
            count=1,
            dtype=mosaic.dtype,
            compress="deflate",
            tiled=True,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(output.suffix + ".tmp")
        with rasterio.open(temp, "w", **profile) as dst:
            dst.write(mosaic)
            dst.update_tags(
                provider="ESA WorldCover",
                product="2021 v200 Map",
                source_tiles=",".join(tile_ids),
            )
        temp.replace(output)
    finally:
        for dataset in datasets:
            dataset.close()
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("WorldCover crop was not written")
    return WorldCoverCropAudit(
        provider_id="ESA_WORLDCOVER",
        release_id="2021_v200",
        source_tile_ids=tile_ids,
        source_urls=urls,
        crop_bounds_wgs84=tuple(float(value) for value in crop_bounds),
        output_path=str(output),
        output_sha256=_sha256_file(output),
        output_bytes=int(output.stat().st_size),
    )
