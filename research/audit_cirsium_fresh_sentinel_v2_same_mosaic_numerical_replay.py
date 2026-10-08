#!/usr/bin/env python3
"""Outcome-blind diagnostic: twice re-sample the same cached GSI mosaic bytes.

The GSI source, candidate frame, first-pass terrain features and patch selector
are untouched. Only three prospectively fixed chunk indices and at most 24
source-complete cells per selected chunk are repeated. No location, candidate
identity, terrain vector, mosaic path or per-chunk digest enters public output.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_same_mosaic_numerical_replay_v1.json"
FEATURES = (
    "elev", "slope100", "slope_sd100", "rough100",
    "tpi100", "range100", "tpi300", "rough300",
)
PAIRS = ("original_vs_replay_1", "replay_1_vs_replay_2")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_DIAGNOSTIC_SAME_MOSAIC_RERUN":
        raise ValueError("numerical replay contract is not frozen")
    if value.get("max_complete_candidates_per_probed_chunk") != 24:
        raise ValueError("numerical replay sample size changed")
    if value.get("replays_per_sample") != 2:
        raise ValueError("numerical replay repeat count changed")
    if tuple(value.get("compared_numeric_features") or ()) != FEATURES:
        raise ValueError("numerical replay features changed")
    if value.get("near_value_comparison") != {"rtol": 0, "atol": 1e-8}:
        raise ValueError("numerical replay tolerance changed")
    if value.get("probed_chunk_indices_rule") != (
        "sorted unique of 0, floor((chunk_count - 1)/2), chunk_count - 1"
    ):
        raise ValueError("numerical replay selected-chunk rule changed")
    boundary = value.get("interpretation") or {}
    if boundary.get("diagnostic_only") is not True:
        raise ValueError("numerical replay must be diagnostic only")
    for key in (
        "does_not_establish_cross_run_reproducibility",
        "no_change_to_source_retrieval_or_order",
        "no_change_to_support_fraction_or_patch_merge_distance",
    ):
        if boundary.get(key) is not True:
            raise ValueError(f"numerical replay policy violated: {key}")
    for key in (
        "biological_habitat_connectivity_claim", "field_discovery_or_occupancy_claim",
        "original_structural_order_replay_claim", "original_frozen_patch_hash_waived",
        "prospective_field_outcomes_opened",
    ):
        if boundary.get(key) is not False:
            raise ValueError(f"numerical replay policy violated: {key}")
    return value


def _selected_chunks(total: int) -> tuple[int, ...]:
    if not isinstance(total, int) or total < 1:
        raise ValueError("source chunk count must be positive integer")
    return tuple(sorted(set((0, (total - 1) // 2, total - 1))))


def _source_complete_candidates(sampled: pd.DataFrame) -> list[str]:
    if sampled is None or sampled.empty or "candidate_cell_id" not in sampled:
        raise ValueError("numerical replay requires source-complete original sample")
    ids = sampled["candidate_cell_id"]
    if ids.isna().any() or ids.astype(str).duplicated().any():
        raise ValueError("sample IDs must be present and unique")
    available = sorted(ids.astype(str).tolist())
    n = min(24, len(available))
    pos = np.linspace(0, len(available) - 1, num=n, dtype=int)
    if len(set(pos.tolist())) != n:
        raise AssertionError("deterministic numerical sample positions repeated")
    return [available[int(i)] for i in pos]


def _vectors(rows: pd.DataFrame, ids: list[str]) -> np.ndarray:
    required = set(FEATURES) | {"candidate_cell_id"}
    if not required.issubset(rows):
        raise ValueError("numerical replay sampler lost terrain features")
    if rows["candidate_cell_id"].isna().any():
        raise ValueError("replayed sample contains a missing ID")
    index = rows.set_index(rows["candidate_cell_id"].astype(str))
    if not index.index.is_unique or set(index.index) != set(ids):
        raise ValueError("same-mosaic replay changed the source-complete ID set")
    matrix = index.loc[ids, list(FEATURES)].apply(
        pd.to_numeric, errors="raise"
    ).to_numpy(dtype=np.float64)
    if not np.isfinite(matrix).all():
        raise ValueError("numerical replay returned nonfinite source-complete terrain")
    return matrix


def _comparison(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    if a.shape != b.shape:
        raise ValueError("numerical replay matrices differ in shape")
    exact = a == b
    close = np.isclose(a, b, rtol=0.0, atol=1e-8)
    delta = np.abs(a - b)
    return {
        "exact_mismatch_by_feature": {
            feature: int((~exact[:, i]).sum()) for i, feature in enumerate(FEATURES)
        },
        "near_mismatch_by_feature": {
            feature: int((~close[:, i]).sum()) for i, feature in enumerate(FEATURES)
        },
        "max_abs_difference_by_feature": {
            feature: float(delta[:, i].max()) for i, feature in enumerate(FEATURES)
        },
        "all_exact": bool(exact.all()),
        "all_near": bool(close.all()),
    }


def _run_probe(
    original: pd.DataFrame,
    component: pd.DataFrame,
    mosaic_path: Path,
    sampler: Callable[[pd.DataFrame, Path], pd.DataFrame],
) -> dict[str, Any]:
    ids = _source_complete_candidates(original)
    if "candidate_cell_id" not in component:
        raise ValueError("private chunk lacks IDs")
    candidates = component[component["candidate_cell_id"].astype(str).isin(ids)].copy()
    if len(candidates) != len(ids):
        raise ValueError("candidate subset does not match original sampled IDs")
    path = Path(mosaic_path).resolve()
    if not path.is_file() or path.is_symlink():
        raise ValueError("numerical replay requires an unchanged regular mosaic file")
    before = _sha256(path)
    replay1 = sampler(candidates.copy(), path)
    replay2 = sampler(candidates.copy(), path)
    after = _sha256(path)
    if before != after:
        raise ValueError("same-mosaic numerical replay changed DEM source bytes")
    original_matrix = _vectors(original[original["candidate_cell_id"].astype(str).isin(ids)], ids)
    first_matrix = _vectors(replay1, ids)
    second_matrix = _vectors(replay2, ids)
    return {
        "sampled_source_complete_cells": len(ids),
        "mosaic_sha256_stable_across_replays": True,
        "original_vs_replay_1": _comparison(original_matrix, first_matrix),
        "replay_1_vs_replay_2": _comparison(first_matrix, second_matrix),
    }


def _native_versions() -> dict[str, str]:
    import pyproj
    import rasterio
    import scipy
    return {
        "python": platform.python_version(),
        "numpy": str(np.__version__),
        "pandas": str(pd.__version__),
        "scipy": str(scipy.__version__),
        "rasterio": str(rasterio.__version__),
        "rasterio_gdal": str(rasterio.__gdal_version__),
        "pyproj": str(pyproj.__version__),
        "proj_library": str(pyproj.proj_version_str),
    }


class SameMosaicReplayCollector:
    """Callback for frozen GSI attachment. Carries no private data in output."""

    def __init__(self) -> None:
        _contract()
        self._results: list[dict[str, Any]] = []
        self._total_chunks: int | None = None

    def __call__(
        self, chunk_index: int, total_chunks: int,
        component: pd.DataFrame, original: pd.DataFrame,
        mosaic_path: Path,
        sampler: Callable[[pd.DataFrame, Path], pd.DataFrame],
    ) -> None:
        if self._total_chunks is not None and self._total_chunks != total_chunks:
            raise ValueError("numerical diagnostic chunk denominator changed")
        self._total_chunks = total_chunks
        if chunk_index not in _selected_chunks(total_chunks):
            return
        row = _run_probe(original, component, mosaic_path, sampler)
        # Index is used only to identify which predeclared chunk was audited;
        # it never leaves this process as location or per-chunk numerical data.
        row["chunk_index"] = int(chunk_index)
        self._results.append(row)

    def summary(self, unit_id: str, total_chunks: int) -> dict[str, Any]:
        contract = _contract()
        if unit_id not in tuple(contract["cohort_unit_ids"]):
            raise ValueError("unknown numerical replay cohort unit")
        if self._total_chunks is not None and self._total_chunks != total_chunks:
            raise ValueError("numerical replay total chunk count changed")
        selected = _selected_chunks(total_chunks)
        used = [int(x["chunk_index"]) for x in self._results]
        if len(set(used)) != len(used) or not set(used).issubset(selected):
            raise ValueError("replayed chunk identities differ from frozen selection")
        totals = {
            pair: {
                "exact_mismatch_by_feature": {feature: 0 for feature in FEATURES},
                "near_mismatch_by_feature": {feature: 0 for feature in FEATURES},
                "max_abs_difference_by_feature": {feature: 0.0 for feature in FEATURES},
                "all_exact": True,
                "all_near": True,
            }
            for pair in PAIRS
        }
        for row in self._results:
            for pair in PAIRS:
                src, dst = row[pair], totals[pair]
                for feature in FEATURES:
                    dst["exact_mismatch_by_feature"][feature] += src["exact_mismatch_by_feature"][feature]
                    dst["near_mismatch_by_feature"][feature] += src["near_mismatch_by_feature"][feature]
                    dst["max_abs_difference_by_feature"][feature] = max(
                        dst["max_abs_difference_by_feature"][feature],
                        src["max_abs_difference_by_feature"][feature],
                    )
                dst["all_exact"] = dst["all_exact"] and src["all_exact"]
                dst["all_near"] = dst["all_near"] and src["all_near"]
        return {
            "schema_version": "cirsium-fresh-sentinel-v2-same-mosaic-numerical-replay-v1",
            "status": "SELECTED_ORIGINAL_GSI_MOSAIC_NUMERICAL_DIAGNOSTIC_COMPLETE",
            "cohort_unit_id": unit_id,
            "source_chunk_count": total_chunks,
            "predeclared_selected_chunk_count": len(selected),
            "probed_chunk_count": len(used),
            "unavailable_selected_chunk_count": len(selected) - len(used),
            "source_complete_cells_probed": sum(
                r["sampled_source_complete_cells"] for r in self._results
            ),
            "replays_per_sample": 2,
            "same_mosaic_bytes_before_after_all_probes": all(
                r["mosaic_sha256_stable_across_replays"] for r in self._results
            ),
            "comparison": totals,
            "native_versions": _native_versions(),
            "private_sampled_vectors_exported": False,
            "private_chunk_paths_or_coordinates_exported": False,
            "selected_support_or_patch_membership_changed": False,
            "field_outcomes_opened": False,
            "source_integrity_and_full_order_reproduction_claim": False,
            "field_selector_or_habitat_connectivity_claim": False,
        }
