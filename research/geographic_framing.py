"""Development-only automatic geographic framing for ACSP.

This module is deliberately outside the validated ``acsp`` package.  It tests a
training-occurrence-only framing layer without changing the confirmed robust
candidate-patch rule or the validated 12-region Japanese adapter.

The v1 baseline is frozen in
``validation/acsp_geographic_framing_development_protocol_v1.json``:

1. assign training occurrences to the existing global 0.1-degree spatial blocks;
2. form 8-neighbour connected components of occupied blocks;
3. retain every component, including singletons (no remote-noise deletion);
4. pad each component envelope by the already-frozen 10 km primary recovery scale;
5. deterministically union padded envelopes that overlap.

No held-out coordinate, SDM/SSDM value, rank, site count, day, or budget enters
frame construction.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
import pandas as pd


EARTH_KM_PER_DEG_LAT = 111.32
DEFAULT_BLOCK_DEGREES = 0.1
DEFAULT_PADDING_KM = 10.0
FRAMING_METHOD = "training_block_component_10km_padding_v1"


@dataclass(frozen=True)
class _Component:
    cells: tuple[tuple[int, int], ...]
    rows: tuple[int, ...]


@dataclass
class _FrameWork:
    west: float
    south: float
    east: float
    north: float
    component_ids: set[int]
    rows: set[int]
    cells: set[tuple[int, int]]


def _validate_occurrences(
    occurrences: pd.DataFrame,
    *,
    latitude_col: str,
    longitude_col: str,
) -> pd.DataFrame:
    if latitude_col not in occurrences.columns or longitude_col not in occurrences.columns:
        raise ValueError(
            f"occurrences must contain {latitude_col!r} and {longitude_col!r}"
        )
    work = occurrences.reset_index(drop=False).rename(columns={"index": "_input_index"}).copy()
    lat = pd.to_numeric(work[latitude_col], errors="coerce").to_numpy(float)
    lon = pd.to_numeric(work[longitude_col], errors="coerce").to_numpy(float)
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError("training occurrence coordinates must be finite")
    if ((lat < -90.0) | (lat > 90.0)).any():
        raise ValueError("training occurrence latitude must lie within [-90, 90]")
    if ((lon < -180.0) | (lon > 180.0)).any():
        raise ValueError("training occurrence longitude must lie within [-180, 180]")
    return work


def _block_indices(values: np.ndarray, *, origin: float, block_degrees: float) -> np.ndarray:
    # The tiny positive offset keeps exact decimal grid-boundary values stable
    # against binary floating-point representation without moving ordinary rows.
    return np.floor((values - origin) / block_degrees + 1e-12).astype(np.int64)


def _occupied_components(
    lat_idx: np.ndarray,
    lon_idx: np.ndarray,
) -> list[_Component]:
    cell_rows: dict[tuple[int, int], list[int]] = {}
    for row, cell in enumerate(zip(lat_idx.tolist(), lon_idx.tolist())):
        key = (int(cell[0]), int(cell[1]))
        cell_rows.setdefault(key, []).append(int(row))

    occupied = set(cell_rows)
    unseen = set(occupied)
    components: list[_Component] = []
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        stack = [start]
        cells: set[tuple[int, int]] = {start}
        while stack:
            lat_i, lon_i = stack.pop()
            neighbours = {
                (lat_i + dlat, lon_i + dlon)
                for dlat in (-1, 0, 1)
                for dlon in (-1, 0, 1)
                if not (dlat == 0 and dlon == 0)
            }
            found = sorted(neighbours & unseen)
            for neighbour in found:
                unseen.remove(neighbour)
                cells.add(neighbour)
                stack.append(neighbour)
        rows = sorted(row for cell in cells for row in cell_rows[cell])
        components.append(_Component(tuple(sorted(cells)), tuple(rows)))
    return sorted(components, key=lambda item: item.cells)


def _component_envelope(
    component: _Component,
    *,
    block_degrees: float,
    padding_km: float,
) -> tuple[float, float, float, float]:
    lat_indices = [cell[0] for cell in component.cells]
    lon_indices = [cell[1] for cell in component.cells]
    south = -90.0 + min(lat_indices) * block_degrees
    north = -90.0 + (max(lat_indices) + 1) * block_degrees
    west = -180.0 + min(lon_indices) * block_degrees
    east = -180.0 + (max(lon_indices) + 1) * block_degrees

    mid_lat = (south + north) / 2.0
    lat_padding = padding_km / EARTH_KM_PER_DEG_LAT
    cosine = abs(math.cos(math.radians(mid_lat)))
    if cosine < 0.05:
        raise ValueError("v1 geographic framing does not support near-polar longitude padding")
    lon_padding = padding_km / (EARTH_KM_PER_DEG_LAT * cosine)

    padded = (
        west - lon_padding,
        south - lat_padding,
        east + lon_padding,
        north + lat_padding,
    )
    if padded[0] < -180.0 or padded[2] > 180.0:
        raise ValueError("v1 geographic framing does not support antimeridian-crossing frames")
    return (
        float(padded[0]),
        float(max(-90.0, padded[1])),
        float(padded[2]),
        float(min(90.0, padded[3])),
    )


def _overlaps(left: _FrameWork, right: _FrameWork) -> bool:
    return not (
        left.east < right.west
        or right.east < left.west
        or left.north < right.south
        or right.north < left.south
    )


def _union(left: _FrameWork, right: _FrameWork) -> _FrameWork:
    return _FrameWork(
        west=min(left.west, right.west),
        south=min(left.south, right.south),
        east=max(left.east, right.east),
        north=max(left.north, right.north),
        component_ids=set(left.component_ids) | set(right.component_ids),
        rows=set(left.rows) | set(right.rows),
        cells=set(left.cells) | set(right.cells),
    )


def _merge_overlapping_frames(frames: Iterable[_FrameWork]) -> list[_FrameWork]:
    pending = sorted(
        list(frames),
        key=lambda item: (item.west, item.south, item.east, item.north),
    )
    merged: list[_FrameWork] = []
    while pending:
        current = pending.pop(0)
        changed = True
        while changed:
            changed = False
            survivors: list[_FrameWork] = []
            for other in pending:
                if _overlaps(current, other):
                    current = _union(current, other)
                    changed = True
                else:
                    survivors.append(other)
            pending = survivors
        merged.append(current)
    return sorted(merged, key=lambda item: (item.west, item.south, item.east, item.north))


def infer_training_block_frames(
    occurrences: pd.DataFrame,
    *,
    latitude_col: str = "_latitude",
    longitude_col: str = "_longitude",
    block_degrees: float = DEFAULT_BLOCK_DEGREES,
    padding_km: float = DEFAULT_PADDING_KM,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Infer deterministic geographic frames from training occurrences only.

    ``block_degrees`` and ``padding_km`` are protocol parameters for research
    evaluation, not ordinary user controls.  The frozen v1 protocol uses 0.1
    degrees and 10 km respectively.

    Returns
    -------
    frames
        One row per final inferred frame.
    occurrence_audit
        Every input training occurrence with occupied-block, component, and
        final-frame membership.  No row is silently classified as noise.
    summary
        Compact provenance and count audit.
    """
    if not np.isfinite(float(block_degrees)) or float(block_degrees) <= 0.0:
        raise ValueError("block_degrees must be finite and positive")
    if not np.isfinite(float(padding_km)) or float(padding_km) < 0.0:
        raise ValueError("padding_km must be finite and non-negative")

    work = _validate_occurrences(
        occurrences,
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )
    if work.empty:
        frames = pd.DataFrame(
            columns=[
                "frame_id", "west", "south", "east", "north",
                "record_count", "occupied_block_count", "source_component_count",
                "source_component_ids", "framing_method", "block_degrees",
                "padding_km", "training_only", "heldout_coordinates_used",
                "remote_noise_filter", "sdm_required",
            ]
        )
        audit = work.assign(
            framing_block_lat_index=pd.Series(dtype="int64"),
            framing_block_lon_index=pd.Series(dtype="int64"),
            framing_component_id=pd.Series(dtype="string"),
            frame_id=pd.Series(dtype="string"),
            scope_class=pd.Series(dtype="string"),
        )
        return frames, audit, {
            "framing_method": FRAMING_METHOD,
            "input_training_occurrence_count": 0,
            "occupied_block_count": 0,
            "initial_component_count": 0,
            "final_frame_count": 0,
            "singleton_components_retained": True,
            "remote_noise_filter": False,
            "heldout_coordinates_used": False,
        }

    lat = pd.to_numeric(work[latitude_col], errors="raise").to_numpy(float)
    lon = pd.to_numeric(work[longitude_col], errors="raise").to_numpy(float)
    lat_idx = _block_indices(lat, origin=-90.0, block_degrees=float(block_degrees))
    lon_idx = _block_indices(lon, origin=-180.0, block_degrees=float(block_degrees))
    components = _occupied_components(lat_idx, lon_idx)

    row_to_component: dict[int, int] = {}
    initial_frames: list[_FrameWork] = []
    for component_index, component in enumerate(components, start=1):
        bounds = _component_envelope(
            component,
            block_degrees=float(block_degrees),
            padding_km=float(padding_km),
        )
        for row in component.rows:
            row_to_component[int(row)] = int(component_index)
        initial_frames.append(
            _FrameWork(
                west=bounds[0], south=bounds[1], east=bounds[2], north=bounds[3],
                component_ids={int(component_index)},
                rows=set(map(int, component.rows)),
                cells=set(component.cells),
            )
        )

    final_frames = _merge_overlapping_frames(initial_frames)
    component_to_frame: dict[int, str] = {}
    frame_rows: list[dict[str, object]] = []
    for frame_index, frame in enumerate(final_frames, start=1):
        frame_id = f"frame-{frame_index:03d}"
        for component_id in frame.component_ids:
            component_to_frame[int(component_id)] = frame_id
        source_ids = [f"component-{value:03d}" for value in sorted(frame.component_ids)]
        frame_rows.append(
            {
                "frame_id": frame_id,
                "west": float(frame.west),
                "south": float(frame.south),
                "east": float(frame.east),
                "north": float(frame.north),
                "record_count": int(len(frame.rows)),
                "occupied_block_count": int(len(frame.cells)),
                "source_component_count": int(len(frame.component_ids)),
                "source_component_ids": ";".join(source_ids),
                "framing_method": FRAMING_METHOD,
                "block_degrees": float(block_degrees),
                "padding_km": float(padding_km),
                "training_only": True,
                "heldout_coordinates_used": False,
                "remote_noise_filter": False,
                "sdm_required": False,
            }
        )
    frames = pd.DataFrame(frame_rows)

    audit = work.copy()
    audit["framing_block_lat_index"] = lat_idx
    audit["framing_block_lon_index"] = lon_idx
    audit["framing_component_id"] = pd.array(
        [f"component-{row_to_component[i]:03d}" for i in range(len(audit))],
        dtype="string",
    )
    audit["frame_id"] = pd.array(
        [component_to_frame[row_to_component[i]] for i in range(len(audit))],
        dtype="string",
    )
    audit["scope_class"] = "retained_training_occurrence"

    if len(audit) != len(work) or audit["frame_id"].isna().any():
        raise AssertionError("every training occurrence must be retained in one final frame")

    summary: dict[str, object] = {
        "framing_method": FRAMING_METHOD,
        "input_training_occurrence_count": int(len(work)),
        "occupied_block_count": int(len(set(zip(lat_idx.tolist(), lon_idx.tolist())))),
        "initial_component_count": int(len(components)),
        "final_frame_count": int(len(frames)),
        "singleton_components_retained": True,
        "remote_noise_filter": False,
        "block_degrees": float(block_degrees),
        "padding_km": float(padding_km),
        "heldout_coordinates_used": False,
        "sdm_required": False,
        "user_bounds_required": False,
    }
    return frames, audit, summary
