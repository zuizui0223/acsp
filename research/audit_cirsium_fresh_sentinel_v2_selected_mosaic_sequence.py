#!/usr/bin/env python3
"""Commit to the actual source DEM chosen for each frozen GSI chunk.

A cache inventory digest identifies all files present, not necessarily which
source mosaic was selected during every chunk. This observer records only a
single SHA256 of the ordered sequence of selected *file content* digests,
including an explicit unavailable-source token. No filenames or per-chunk
hashes enter the public result and the sampler's primary output is unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/"validation/coverage_then_fine_structure_fresh_sentinel_v2_selected_mosaic_sequence_v1.json"
UNITS=("CIR02","CIR06","CIR12","CIR13")


def _contract() -> dict[str,Any]:
    value=json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status")!="FROZEN_BEFORE_SELECTED_GSI_MOSAIC_INPUT_AUDIT":
        raise ValueError("selected mosaic audit contract not frozen")
    if tuple(value.get("units",()))!=UNITS:
        raise ValueError("selected mosaic cohort changed")
    checks=value.get("safety",{})
    for k in ("no_coordinates_or_candidate_ids_exported",
              "no_gsi_tile_path_or_file_basename_exported",
              "no_per_chunk_mosaic_sha_exported",
              "no_source_selection_changed",
              "no_source_complete_denominator_changed",
              "no_fine_structural_order_changed",
              "no_2p5pct_or_1km_rule_changed",
              "no_prospective_field_outcomes_opened",
              "no_biological_habitat_claim"):
        if checks.get(k) is not True:
            raise ValueError(f"unsafe selected mosaic audit setting: {k}")
    return value


def _file_digest(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(4*1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


class SelectedMosaicSequence:
    def __init__(self, *, unit_id: str, cache_dir: Path) -> None:
        _contract()
        if unit_id not in UNITS:
            raise ValueError("unregistered GSI unit")
        self.unit_id=unit_id
        self.cache_dir=Path(cache_dir).resolve()
        self._sequence=hashlib.sha256(b"ACSP_SELECTED_GSI_MOSAIC_SEQUENCE_V1\n")
        self._seen=0
        self._available=0
        self._unavailable=0

    def __call__(self, chunk_index: int, selected_dem_path: str | Path | None) -> None:
        if not isinstance(chunk_index,int) or chunk_index!=self._seen:
            raise ValueError("selected mosaic chunks must be complete and in original order")
        # Follow the production builder's "if not dem_path" semantics:
        # both None and an empty path mean an unavailable source, not a file.
        if not selected_dem_path:
            token="SOURCE_UNAVAILABLE"
            self._unavailable+=1
        else:
            raw=Path(selected_dem_path)
            if raw.is_symlink():
                raise ValueError("selected GSI source may not be a symlink")
            path=raw.resolve()
            try:
                path.relative_to(self.cache_dir)
            except ValueError as exc:
                raise ValueError("selected DEM must be in its private read-only GSI cache") from exc
            if not path.is_file():
                raise ValueError("selected DEM content missing")
            token="DEM_SHA256_"+_file_digest(path)
            self._available+=1
        # Chunk index is a positional token in the aggregate digest only:
        # do not expose per-chunk signatures or original tile/DEM names.
        self._sequence.update(f"{chunk_index}\t{token}\n".encode("utf-8"))
        self._seen+=1

    def summary(self, *, chunk_count: int) -> dict[str,Any]:
        if not isinstance(chunk_count,int) or chunk_count<1 or chunk_count!=self._seen:
            raise ValueError("selected mosaic sequence incomplete")
        return {
            "schema_version":"cirsium-fresh-sentinel-v2-selected-mosaic-sequence-v1",
            "status":"ACTUAL_SELECTED_DEM_CONTENT_SEQUENCE_AUDITED_PRE_OUTCOME",
            "cohort_unit_id":self.unit_id,
            "chunk_count":chunk_count,
            "selected_dem_chunks":self._available,
            "unavailable_dem_chunks":self._unavailable,
            "selected_mosaic_content_sequence_sha256":self._sequence.hexdigest(),
            "private_source_paths_or_tile_coordinates_exported":False,
            "per_chunk_source_content_hashes_exported":False,
            "production_gsi_selection_changed":False,
            "field_outcomes_opened":False,
            "cross_run_numeric_reproduction_proven":False,
        }
