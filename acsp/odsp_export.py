"""Write explicit training, held-out, and candidate-support tables for ODSP.

This exporter intentionally leaves the published ACSP benchmark outputs unchanged.
It reuses the same spatial-block split rule, calls the candidate builder with
training records only, and writes every evaluation coordinate explicitly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ODSPFoldExportConfig:
    block_degrees: float = 0.10
    repeats: int = 5
    holdout_fraction: float = 0.20
    random_state: int = 42
    latitude_col: str = "latitude"
    longitude_col: str = "longitude"
    support_col: str = "integrated_support_score"

    def validate(self) -> None:
        if self.block_degrees <= 0:
            raise ValueError("block_degrees must be positive")
        if self.repeats < 1:
            raise ValueError("repeats must be at least one")
        if not 0 < self.holdout_fraction < 1:
            raise ValueError("holdout_fraction must lie in (0, 1)")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_odsp_folds(
    occurrences: pd.DataFrame,
    candidate_builder: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    config: ODSPFoldExportConfig | None = None,
) -> Iterator[tuple[int, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]]:
    """Yield deterministic training-only ODSP fold inputs."""
    cfg = config or ODSPFoldExportConfig()
    cfg.validate()
    required = {cfg.latitude_col, cfg.longitude_col}
    missing = required - set(occurrences.columns)
    if missing:
        raise ValueError(f"occurrences is missing columns: {', '.join(sorted(missing))}")
    work = occurrences.copy().reset_index(drop=True)
    work[cfg.latitude_col] = pd.to_numeric(work[cfg.latitude_col], errors="coerce")
    work[cfg.longitude_col] = pd.to_numeric(work[cfg.longitude_col], errors="coerce")
    work = work.dropna(subset=[cfg.latitude_col, cfg.longitude_col]).reset_index(drop=True)
    work["_odsp_occurrence_id"] = np.arange(len(work), dtype=int)
    work["_odsp_block"] = (
        np.floor(work[cfg.latitude_col] / cfg.block_degrees).astype(int).astype(str)
        + ":"
        + np.floor(work[cfg.longitude_col] / cfg.block_degrees).astype(int).astype(str)
    )
    blocks = work["_odsp_block"].drop_duplicates().to_numpy()
    if len(blocks) < 2:
        raise ValueError("Occurrences occupy fewer than two spatial blocks")
    rng = np.random.default_rng(cfg.random_state)
    n_holdout = min(len(blocks) - 1, max(1, int(round(len(blocks) * cfg.holdout_fraction))))
    for repeat in range(1, cfg.repeats + 1):
        held_blocks = set(rng.choice(blocks, size=n_holdout, replace=False).tolist())
        held = work[work["_odsp_block"].isin(held_blocks)].copy()
        train = work[~work["_odsp_block"].isin(held_blocks)].copy()
        builder_input = train.drop(columns=["_odsp_block", "_odsp_occurrence_id"]).reset_index(drop=True)
        candidates = candidate_builder(builder_input.copy())
        if candidates is None:
            candidates = pd.DataFrame()
        candidates = candidates.copy()
        candidate_missing = {"latitude", "longitude", cfg.support_col} - set(candidates.columns)
        status = "ready" if not candidate_missing and not candidates.empty else "no_candidate_support"
        if not candidate_missing:
            candidates = candidates[["latitude", "longitude", cfg.support_col]].rename(
                columns={cfg.support_col: "candidate_support"}
            )
            candidates["repeat"] = repeat
        else:
            candidates = pd.DataFrame(columns=["latitude", "longitude", "candidate_support", "repeat"])
        training = train[["_odsp_occurrence_id", cfg.latitude_col, cfg.longitude_col]].rename(
            columns={"_odsp_occurrence_id": "occurrence_id", cfg.latitude_col: "latitude", cfg.longitude_col: "longitude"}
        )
        heldout = held[["_odsp_occurrence_id", cfg.latitude_col, cfg.longitude_col, "_odsp_block"]].rename(
            columns={"_odsp_occurrence_id": "occurrence_id", cfg.latitude_col: "latitude", cfg.longitude_col: "longitude", "_odsp_block": "spatial_block"}
        )
        manifest = {
            "repeat": repeat,
            "status": status,
            "heldout_blocks": sorted(held_blocks),
            "training_records": int(len(training)),
            "heldout_records": int(len(heldout)),
            "candidate_support_rows": int(len(candidates)),
            "candidate_missing_columns": sorted(candidate_missing),
            "config": asdict(cfg),
            "leakage_boundary": "candidate_builder received training records only; held-out coordinates were written after candidate construction",
        }
        yield repeat, training.reset_index(drop=True), heldout.reset_index(drop=True), candidates.reset_index(drop=True), manifest


def write_odsp_fold_exports(
    occurrences: pd.DataFrame,
    candidate_builder: Callable[[pd.DataFrame], pd.DataFrame],
    output_dir: str | Path,
    *,
    config: ODSPFoldExportConfig | None = None,
    provenance: dict[str, object] | None = None,
) -> pd.DataFrame:
    """Write one complete, checksum-audited directory per fold."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for repeat, training, heldout, candidates, manifest in iter_odsp_folds(occurrences, candidate_builder, config=config):
        fold = root / f"fold_{repeat:03d}"
        fold.mkdir(parents=True, exist_ok=True)
        paths = {
            "training_occurrences": fold / "training_occurrences.csv",
            "held_out_occurrences": fold / "held_out_occurrences.csv",
            "candidate_support": fold / "candidate_support.csv",
        }
        training.to_csv(paths["training_occurrences"], index=False)
        heldout.to_csv(paths["held_out_occurrences"], index=False)
        candidates.to_csv(paths["candidate_support"], index=False)
        complete = {
            **manifest,
            "provenance": dict(provenance or {}),
            "files": {name: {"path": path.name, "sha256": _sha256(path), "rows": int(len(table))}
                      for (name, path), table in zip(paths.items(), (training, heldout, candidates))},
        }
        (fold / "fold_manifest.json").write_text(json.dumps(complete, indent=2, ensure_ascii=False), encoding="utf-8")
        rows.append({"repeat": repeat, "status": manifest["status"], "fold_dir": str(fold),
                     "training_records": len(training), "heldout_records": len(heldout),
                     "candidate_support_rows": len(candidates)})
    summary = pd.DataFrame(rows)
    summary.to_csv(root / "export_status.csv", index=False)
    return summary
