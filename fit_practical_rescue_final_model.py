#!/usr/bin/env python3
"""Refit the unchanged rescue estimator on all 72 development pairs after GRTS gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from acsp.practical_rescue import (
    PRACTICAL_RESCUE_PROTOCOL_FINGERPRINT,
    RESCUE_CATEGORICAL_FEATURES,
    RESCUE_NUMERIC_FEATURES,
    build_rescue_features,
    local_order,
    make_rescue_estimator,
    prepare_rescue_candidates,
    protocol_fingerprint,
)
from benchmark_practical_rescue_development import (
    _feature_table_and_target,
    _sdm_extension_folds,
    _standard_folds,
)

EXPECTED_GRTS_DEVELOPMENT_PROTOCOL = "950f7d9de90da2f2bd2561a18b7cc1eb74a60568ccc801875b96119db53bddf2"
EARTH_RADIUS_KM = 6_371.0088


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _haversine_cross_km(candidate: pd.DataFrame, heldout: pd.DataFrame) -> np.ndarray:
    if candidate.empty or heldout.empty:
        return np.empty((len(candidate), 0), dtype=float)
    lat_col = "_latitude" if "_latitude" in heldout.columns else "latitude"
    lon_col = "_longitude" if "_longitude" in heldout.columns else "longitude"
    hlat = pd.to_numeric(heldout[lat_col], errors="coerce")
    hlon = pd.to_numeric(heldout[lon_col], errors="coerce")
    valid = hlat.notna() & hlon.notna()
    hlat = hlat.loc[valid].to_numpy(float)
    hlon = hlon.loc[valid].to_numpy(float)
    clat = pd.to_numeric(candidate["latitude"], errors="coerce").to_numpy(float)
    clon = pd.to_numeric(candidate["longitude"], errors="coerce").to_numpy(float)
    alat = np.radians(clat)[:, None]
    alon = np.radians(clon)[:, None]
    blat = np.radians(hlat)[None, :]
    blon = np.radians(hlon)[None, :]
    dlat = alat - blat
    dlon = alon - blon
    a = np.sin(dlat / 2) ** 2 + np.cos(alat) * np.cos(blat) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _extension_feature_table(fold: dict[str, object]) -> pd.DataFrame:
    candidates = fold["candidates"]
    heldout = fold["heldout"]
    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        return pd.DataFrame()
    eligible = prepare_rescue_candidates(candidates)
    if eligible.empty:
        return pd.DataFrame()
    if not isinstance(heldout, pd.DataFrame) or heldout.empty:
        return pd.DataFrame()
    features = build_rescue_features(candidates, str(fold["taxon_group"]))
    distance = _haversine_cross_km(eligible, heldout)
    if distance.shape[1] == 0:
        return pd.DataFrame()
    covered = distance <= 10.0
    anchor = int(local_order(eligible)[0])
    residual = ~covered[anchor]
    denominator = covered.shape[1]
    target = covered[:, residual].sum(axis=1) / float(denominator)
    out = features[
        [*RESCUE_NUMERIC_FEATURES, *RESCUE_CATEGORICAL_FEATURES, "_source_index"]
    ].copy()
    out["target_residual_fraction"] = target
    out["group_id"] = str(fold["group_id"])
    out["repeat"] = int(fold["repeat"])
    return out


def _runtime_guard(protocol: dict[str, object]) -> dict[str, str]:
    expected = protocol["software_contract"]
    actual = {
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "joblib": joblib.__version__,
    }
    for key in ("python", "scikit_learn", "pandas", "numpy"):
        if str(expected[key]) != str(actual[key]):
            raise ValueError(
                f"frozen runtime mismatch for {key}: expected {expected[key]!r}, got {actual[key]!r}"
            )
    return actual


def run(
    standard_roots: list[Path],
    sdm_root: Path,
    rescue_protocol_path: Path,
    grts_gate_manifest_path: Path,
    output: Path,
) -> dict[str, object]:
    rescue_protocol = json.loads(rescue_protocol_path.read_text(encoding="utf-8"))
    rescue_fp = protocol_fingerprint(rescue_protocol)
    if (
        rescue_fp != PRACTICAL_RESCUE_PROTOCOL_FINGERPRINT
        or rescue_protocol.get("protocol_fingerprint") != rescue_fp
    ):
        raise ValueError("rescue development protocol fingerprint mismatch")
    runtime = _runtime_guard(rescue_protocol)

    grts_gate = json.loads(grts_gate_manifest_path.read_text(encoding="utf-8"))
    if grts_gate.get("protocol_fingerprint") != EXPECTED_GRTS_DEVELOPMENT_PROTOCOL:
        raise ValueError("unexpected GRTS development protocol fingerprint")
    if grts_gate.get("development_grts_gate_passed") is not True:
        raise ValueError("final rescue refit is blocked until the official GRTS development gate passes")
    if int(grts_gate.get("complete_pairs", 0)) != 72:
        raise ValueError("GRTS development gate did not retain all 72 pairs")

    standard_folds = _standard_folds(standard_roots)
    extension_folds = _sdm_extension_folds(sdm_root)
    if len(standard_folds) != 240 or len({fold["group_id"] for fold in standard_folds}) != 48:
        raise ValueError("expected 48 standard development pairs / 240 folds")
    if len(extension_folds) != 120 or len({fold["group_id"] for fold in extension_folds}) != 24:
        raise ValueError("expected 24 locked extension pairs / 120 folds")

    tables = []
    for fold in standard_folds:
        table = _feature_table_and_target(fold)
        if not table.empty:
            table["training_source"] = "standard_48"
            tables.append(table)
    for fold in extension_folds:
        table = _extension_feature_table(fold)
        if not table.empty:
            table["training_source"] = "locked_extension_24"
            tables.append(table)
    training = pd.concat(tables, ignore_index=True)
    groups = set(training["group_id"].astype(str))
    if len(groups) != 72:
        raise ValueError(f"final training table contains {len(groups)} pair groups, expected 72")

    columns = [*RESCUE_NUMERIC_FEATURES, *RESCUE_CATEGORICAL_FEATURES]
    estimator = make_rescue_estimator()
    estimator.fit(training[columns], training["target_residual_fraction"])

    output.mkdir(parents=True, exist_ok=True)
    model_path = output / "practical_rescue_final_72.joblib"
    training_path = output / "training_rows.csv"
    feature_path = output / "feature_contract.json"
    joblib.dump(estimator, model_path, compress=3)
    training.to_csv(training_path, index=False)
    feature_path.write_text(
        json.dumps({
            "numeric": list(RESCUE_NUMERIC_FEATURES),
            "categorical": list(RESCUE_CATEGORICAL_FEATURES),
            "target": "fraction of all held-out occurrences within 10 km of candidate but not the single local anchor",
            "selection": "one local anchor plus four diversity-adjusted learned rescue slots",
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "status": "final_rescue_model_fitted_after_official_grts_development_gate",
        "rescue_protocol_fingerprint": rescue_fp,
        "grts_development_protocol_fingerprint": EXPECTED_GRTS_DEVELOPMENT_PROTOCOL,
        "grts_gate_manifest_sha256": _sha256(grts_gate_manifest_path),
        "development_pairs": 72,
        "development_folds": 360,
        "training_rows": int(len(training)),
        "training_source_counts": {
            str(key): int(value)
            for key, value in training["training_source"].value_counts().sort_index().items()
        },
        "runtime": runtime,
        "model_sha256": _sha256(model_path),
        "training_rows_sha256": _sha256(training_path),
        "feature_contract_sha256": _sha256(feature_path),
        "grts_outcomes_used_as_model_features_or_targets": False,
        "model_hyperparameters_changed_after_grts_gate": False,
        "fresh_confirmation_required": True,
    }
    (output / "model_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--standard-root", action="append", type=Path, required=True)
    command.add_argument("--sdm-root", type=Path, required=True)
    command.add_argument(
        "--rescue-protocol",
        type=Path,
        default=Path("validation/acsp_practical_rescue_development_protocol.json"),
    )
    command.add_argument("--grts-gate-manifest", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    args = parser().parse_args()
    print(json.dumps(run(
        args.standard_root,
        args.sdm_root,
        args.rescue_protocol,
        args.grts_gate_manifest,
        args.output,
    ), indent=2, ensure_ascii=False))
