"""Audited, training-only fold exports for standard ACSP comparator benchmarks."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from .comparator_benchmark import StandardBaselineProtocol
from .planning import EARTH_RADIUS_M, integrated_candidate_scores


@dataclass(frozen=True)
class ComparatorFold:
    repeat: int
    training: pd.DataFrame
    heldout: pd.DataFrame
    candidates: pd.DataFrame
    audit: dict[str, object]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _coordinate_columns(frame: pd.DataFrame) -> tuple[str, str]:
    for latitude, longitude in (
        ("latitude", "longitude"),
        ("_latitude", "_longitude"),
        ("decimalLatitude", "decimalLongitude"),
        ("lat", "lon"),
    ):
        if latitude in frame.columns and longitude in frame.columns:
            return latitude, longitude
    raise ValueError("occurrences require latitude and longitude columns")


def _distance_matrix_km(heldout: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    if len(heldout) == 0 or len(candidates) == 0:
        return np.empty((len(heldout), len(candidates)), dtype=float)
    lat1 = np.radians(heldout[:, 0])[:, None]
    lon1 = np.radians(heldout[:, 1])[:, None]
    lat2 = np.radians(candidates[:, 0])[None, :]
    lon2 = np.radians(candidates[:, 1])[None, :]
    a = np.sin((lat2 - lat1) / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))) / 1000.0


def iter_comparator_folds(
    occurrences: pd.DataFrame,
    candidate_builder: Callable[[pd.DataFrame], pd.DataFrame],
    protocol: StandardBaselineProtocol,
    *,
    pair_id: object,
    random_state: int | None = None,
    provenance: Mapping[str, object] | None = None,
) -> Iterator[ComparatorFold]:
    """Yield explicit folds while keeping held-out coordinates outside the builder."""
    protocol.validate()
    if occurrences is None:
        raise ValueError("occurrences must be a DataFrame")
    latitude_col, longitude_col = _coordinate_columns(occurrences)
    work = occurrences.copy().reset_index(drop=True)
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if len(work) < 4:
        raise ValueError("at least four occurrence records are required")
    work["occurrence_id"] = [f"{pair_id}-o{index + 1:06d}" for index in range(len(work))]
    work["spatial_block"] = (
        np.floor(work[latitude_col] / protocol.block_degrees).astype(int).astype(str)
        + ":"
        + np.floor(work[longitude_col] / protocol.block_degrees).astype(int).astype(str)
    )
    blocks = work["spatial_block"].drop_duplicates().to_numpy()
    if len(blocks) < 2:
        raise ValueError("occurrences occupy fewer than two spatial blocks")
    holdout_count = min(
        len(blocks) - 1,
        max(1, int(round(len(blocks) * protocol.holdout_fraction))),
    )
    rng = np.random.default_rng(int(protocol.random_state if random_state is None else random_state))
    for repeat in range(1, protocol.repeats + 1):
        held_blocks = set(rng.choice(blocks, size=holdout_count, replace=False).tolist())
        heldout = work[work["spatial_block"].isin(held_blocks)].copy().reset_index(drop=True)
        training = work[~work["spatial_block"].isin(held_blocks)].copy().reset_index(drop=True)
        builder_input = training.drop(columns=["occurrence_id", "spatial_block"]).copy()
        candidates = candidate_builder(builder_input)
        if candidates is None:
            candidates = pd.DataFrame()
        candidates = candidates.copy().reset_index(drop=True)
        candidate_missing = {"latitude", "longitude"} - set(candidates.columns)
        if not candidate_missing:
            candidates["latitude"] = pd.to_numeric(candidates["latitude"], errors="coerce")
            candidates["longitude"] = pd.to_numeric(candidates["longitude"], errors="coerce")
            candidates = candidates.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
            candidate_type = candidates.get("candidate_type", pd.Series("", index=candidates.index)).astype(str)
            candidates = candidates[
                ~candidate_type.str.contains(
                    "occurrence-supported|known-location|known anchor",
                    case=False,
                    na=False,
                )
            ].reset_index(drop=True)
            candidates = integrated_candidate_scores(candidates, exclude_occurrence_derived=True)
            score = pd.to_numeric(
                candidates.get("component_local_habitat_score", pd.Series(dtype=float)),
                errors="coerce",
            )
            if score.empty or not score.notna().any():
                candidate_missing.add("component_local_habitat_score")
                candidates = pd.DataFrame()
        else:
            candidates = pd.DataFrame()

        all_heldout_ids = ";".join(heldout["occurrence_id"].astype(str))
        if not candidates.empty:
            candidates["candidate_id"] = [
                f"{pair_id}-r{repeat:03d}-c{index + 1:06d}" for index in range(len(candidates))
            ]
            distances = _distance_matrix_km(
                heldout[[latitude_col, longitude_col]].to_numpy(float),
                candidates[["latitude", "longitude"]].to_numpy(float),
            )
            held_ids = heldout["occurrence_id"].astype(str).to_numpy()
            candidates["covered_heldout_ids"] = [
                ";".join(held_ids[distances[:, index] <= protocol.recovery_radius_km])
                for index in range(len(candidates))
            ]
            candidates["heldout_distances_km"] = [
                ";".join(f"{value:.8f}" for value in distances[:, index])
                for index in range(len(candidates))
            ]
            candidates["all_heldout_ids"] = all_heldout_ids
            candidates["repeat"] = repeat
            candidates["pair_id"] = pair_id
            for key, value in dict(provenance or {}).items():
                if key not in candidates.columns:
                    candidates[key] = value

        environmental_status = {
            column: bool(
                column in candidates.columns
                and pd.to_numeric(candidates[column], errors="coerce").notna().any()
            )
            for column in protocol.environmental_columns
        }
        status = "ready" if not candidates.empty else "no_candidate_pool"
        audit = {
            "pair_id": pair_id,
            "repeat": repeat,
            "status": status,
            "heldout_blocks": sorted(held_blocks),
            "training_records": int(len(training)),
            "heldout_records": int(len(heldout)),
            "candidate_rows": int(len(candidates)),
            "candidate_missing_columns": sorted(candidate_missing),
            "environmental_feature_availability": environmental_status,
            "environmentally_eligible": bool(environmental_status) and all(environmental_status.values()),
            "protocol_fingerprint": protocol.manifest()["fingerprint"],
            "leakage_boundary": (
                "candidate_builder received training coordinates only; held-out IDs, coordinates, distances, and recovery labels were attached after candidate construction"
            ),
            "provenance": dict(provenance or {}),
        }
        yield ComparatorFold(
            repeat=repeat,
            training=training.rename(columns={latitude_col: "latitude", longitude_col: "longitude"}),
            heldout=heldout.rename(columns={latitude_col: "latitude", longitude_col: "longitude"}),
            candidates=candidates,
            audit=audit,
        )


def write_comparator_pair_export(
    occurrences: pd.DataFrame,
    candidate_builder: Callable[[pd.DataFrame], pd.DataFrame],
    output_dir: str | Path,
    protocol: StandardBaselineProtocol,
    *,
    pair_id: object,
    random_state: int | None = None,
    provenance: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Write checksum-audited explicit tables for every expected fold."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    pair_manifests: list[dict[str, object]] = []
    for fold in iter_comparator_folds(
        occurrences,
        candidate_builder,
        protocol,
        pair_id=pair_id,
        random_state=random_state,
        provenance=provenance,
    ):
        directory = root / f"fold_{fold.repeat:03d}"
        directory.mkdir(parents=True, exist_ok=True)
        paths = {
            "training_occurrences": directory / "training_occurrences.csv",
            "held_out_occurrences": directory / "held_out_occurrences.csv",
            "candidates": directory / "candidates.csv",
        }
        fold.training.to_csv(paths["training_occurrences"], index=False)
        fold.heldout.to_csv(paths["held_out_occurrences"], index=False)
        fold.candidates.to_csv(paths["candidates"], index=False)
        manifest = {
            **fold.audit,
            "files": {
                name: {
                    "path": path.name,
                    "sha256": _sha256(path),
                    "rows": int(len(table)),
                }
                for (name, path), table in zip(
                    paths.items(),
                    (fold.training, fold.heldout, fold.candidates),
                )
            },
        }
        (directory / "fold_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )
        pair_manifests.append(manifest)
        rows.append({
            "pair_id": pair_id,
            "repeat": fold.repeat,
            "status": fold.audit["status"],
            "training_records": len(fold.training),
            "heldout_records": len(fold.heldout),
            "candidate_rows": len(fold.candidates),
            "environmentally_eligible": bool(fold.audit["environmentally_eligible"]),
        })
    pair_manifest = {
        "pair_id": pair_id,
        "protocol": protocol.manifest(),
        "expected_folds": protocol.repeats,
        "written_folds": len(pair_manifests),
        "folds": [
            {
                "repeat": item["repeat"],
                "status": item["status"],
                "environmentally_eligible": bool(item["environmentally_eligible"]),
                "files": item["files"],
            }
            for item in pair_manifests
        ],
        "provenance": dict(provenance or {}),
    }
    (root / "pair_manifest.json").write_text(
        json.dumps(pair_manifest, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
    status = pd.DataFrame(rows)
    status.to_csv(root / "fold_export_status.csv", index=False)
    return status
