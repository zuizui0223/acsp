#!/usr/bin/env python3
"""Open the frozen v2 cohort and export its five predeclared spatial folds.

This is the first confirmation step that fetches focal occurrence rows. It does
not build candidates or inspect recovery. The split rule is fixed by
``acsp_robust_patch_untouched_confirmation_execution_v2.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_general_random_taxa_regions import fetch_occurrences

EXECUTION_PATH = Path("validation/acsp_robust_patch_untouched_confirmation_execution_v2.json")
EXPECTED_EXECUTION = "47afe0f78fdc253f395cb0eb6410ae846ab15e12da1b922c72edad357c722a45"


def _execution() -> dict[str, object]:
    payload = json.loads(EXECUTION_PATH.read_text(encoding="utf-8"))
    expected = str(payload.pop("execution_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if expected != EXPECTED_EXECUTION or calculated != EXPECTED_EXECUTION:
        raise ValueError(
            f"confirmation execution fingerprint mismatch: file={expected}, calculated={calculated}, expected={EXPECTED_EXECUTION}"
        )
    payload["execution_fingerprint"] = expected
    return payload


def _coordinate_columns(frame: pd.DataFrame) -> tuple[str, str]:
    for latitude, longitude in (
        ("latitude", "longitude"),
        ("_latitude", "_longitude"),
        ("decimalLatitude", "decimalLongitude"),
        ("lat", "lon"),
    ):
        if latitude in frame.columns and longitude in frame.columns:
            return latitude, longitude
    raise ValueError("occurrence rows do not contain recognizable coordinates")


def _write_fold(
    fold_dir: Path,
    *,
    training: pd.DataFrame,
    heldout: pd.DataFrame,
    row: pd.Series,
    repeat: int,
    status: str,
    failure_reason: str = "",
) -> None:
    fold_dir.mkdir(parents=True, exist_ok=True)
    training.to_csv(fold_dir / "training_occurrences.csv", index=False)
    heldout.to_csv(fold_dir / "held_out_occurrences.csv", index=False)
    manifest = {
        "pair_id": int(row.pair_id),
        "repeat": int(repeat),
        "status": status,
        "failure_reason": failure_reason,
        "training_records": int(len(training)),
        "heldout_records": int(len(heldout)),
        "execution_fingerprint": EXPECTED_EXECUTION,
        "leakage_boundary": "fold split only; no candidate generation, robust support, recovery, or outcome-based replacement",
        "provenance": {
            "pair_id": int(row.pair_id),
            "scientific_name": str(row.scientific_name),
            "taxon_group": str(row.taxon_group),
            "region_name": str(row.region_name),
            "geographic_stratum": str(row.geographic_stratum),
            "species_key": int(row.speciesKey),
            "west": float(row.west),
            "south": float(row.south),
            "east": float(row.east),
            "north": float(row.north),
        },
    }
    (fold_dir / "fold_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _write_failed_pair(root: Path, row: pd.Series, reason: str, repeats: int) -> None:
    empty = pd.DataFrame(columns=["latitude", "longitude"])
    for repeat in range(1, repeats + 1):
        _write_fold(
            root / f"pair_{int(row.pair_id):03d}" / f"fold_{repeat:03d}",
            training=empty,
            heldout=empty,
            row=row,
            repeat=repeat,
            status="failed_placeholder",
            failure_reason=reason,
        )


def run(sample_file: Path, output: Path) -> dict[str, object]:
    execution = _execution()
    sample = pd.read_csv(sample_file)
    sample = sample.loc[sample["status"].astype(str).eq("predeclared")].copy()
    if len(sample) != int(execution["cohort_artifact"]["declared_pairs"]):
        raise ValueError(f"expected 96 frozen pairs, found {len(sample)}")
    if sample["scientific_name"].duplicated().any():
        raise ValueError("frozen cohort contains duplicate taxa")
    if sample["scientific_name"].astype(str).str.startswith(("Campanula microdonta", "Campanula punctata")).any():
        raise ValueError("frozen v2 cohort contains excluded Campanula development complex")

    fold_rule = execution["fold_generation"]
    repeats = int(fold_rule["repeats"])
    block_degrees = float(fold_rule["block_degrees"])
    holdout_fraction = float(fold_rule["holdout_fraction"])
    seed_base = int(fold_rule["fold_seed_base"])
    records_per_pair = int(execution["occurrence_fetch"]["records_per_pair"])

    output.mkdir(parents=True, exist_ok=True)
    sample.to_csv(output / "declared_pairs.csv", index=False)
    statuses: list[dict[str, object]] = []

    for _, row in sample.sort_values("pair_id").iterrows():
        pair_id = int(row.pair_id)
        try:
            occurrences = fetch_occurrences(row, records_per_pair).copy().reset_index(drop=True)
            latitude_col, longitude_col = _coordinate_columns(occurrences)
            occurrences["latitude"] = pd.to_numeric(occurrences[latitude_col], errors="coerce")
            occurrences["longitude"] = pd.to_numeric(occurrences[longitude_col], errors="coerce")
            occurrences = occurrences.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
            if len(occurrences) < 4:
                raise ValueError(f"fewer than four usable occurrence rows: {len(occurrences)}")
            occurrences["spatial_block"] = (
                np.floor(occurrences["latitude"] / block_degrees).astype(int).astype(str)
                + ":"
                + np.floor(occurrences["longitude"] / block_degrees).astype(int).astype(str)
            )
            blocks = occurrences["spatial_block"].drop_duplicates().to_numpy()
            if len(blocks) < 2:
                raise ValueError("occurrences occupy fewer than two spatial blocks")
            holdout_count = min(
                len(blocks) - 1,
                max(1, int(round(len(blocks) * holdout_fraction))),
            )
            rng = np.random.default_rng(seed_base + pair_id)
            ready = 0
            for repeat in range(1, repeats + 1):
                held_blocks = set(rng.choice(blocks, size=holdout_count, replace=False).tolist())
                heldout = occurrences.loc[occurrences["spatial_block"].isin(held_blocks)].copy()
                training = occurrences.loc[~occurrences["spatial_block"].isin(held_blocks)].copy()
                training = training.drop(columns=["spatial_block"], errors="ignore").reset_index(drop=True)
                heldout = heldout.drop(columns=["spatial_block"], errors="ignore").reset_index(drop=True)
                if training.empty or heldout.empty:
                    raise ValueError(f"repeat {repeat} produced empty training or heldout partition")
                _write_fold(
                    output / f"pair_{pair_id:03d}" / f"fold_{repeat:03d}",
                    training=training,
                    heldout=heldout,
                    row=row,
                    repeat=repeat,
                    status="ready",
                )
                ready += 1
            statuses.append({
                "pair_id": pair_id,
                "scientific_name": str(row.scientific_name),
                "taxon_group": str(row.taxon_group),
                "status": "complete",
                "occurrence_rows": int(len(occurrences)),
                "spatial_blocks": int(len(blocks)),
                "written_folds": ready,
                "failure_reason": "",
            })
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            _write_failed_pair(output, row, reason, repeats)
            statuses.append({
                "pair_id": pair_id,
                "scientific_name": str(row.scientific_name),
                "taxon_group": str(row.taxon_group),
                "status": "failed_retained_as_zero",
                "occurrence_rows": 0,
                "spatial_blocks": 0,
                "written_folds": repeats,
                "failure_reason": reason,
            })
        pd.DataFrame(statuses).to_csv(output / "pair_export_status.csv", index=False)

    status = pd.DataFrame(statuses)
    manifest = {
        "status": "confirmation_opened_occurrence_folds_exported",
        "execution_fingerprint": EXPECTED_EXECUTION,
        "cohort_rows": int(len(sample)),
        "expected_folds": int(len(sample) * repeats),
        "written_fold_manifests": int(len(list(output.glob("pair_*/fold_*/fold_manifest.json")))),
        "pair_status_counts": {str(k): int(v) for k, v in status["status"].value_counts().items()},
        "candidate_generation_run": False,
        "robust_support_run": False,
        "heldout_recovery_run": False,
        "replacement_after_opening_allowed": False,
    }
    (output / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if manifest["written_fold_manifests"] != manifest["expected_folds"]:
        raise RuntimeError("confirmation fold export did not preserve all 480 declared folds")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.sample_file, args.output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
