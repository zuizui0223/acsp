#!/usr/bin/env python3
"""Run one frozen taxon-region pair for the untouched fitted-SDM Top-k benchmark.

Operational decisions are constructed from the outer training fold only. Held-out
coordinates are supplied to a separate outcome function after ACSP, local-only,
geographic, random, and fitted-SDM decisions have been frozen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from acsp.decision_baselines import (
    DecisionBaselineConfig,
    random_same_pool_sets,
    select_geographic_farthest,
    select_score_top_k,
)
from acsp.planning import EARTH_RADIUS_M, integrated_candidate_scores
from acsp.validated_core import ValidatedCorePolicy, select_validated_core
from acsp.automatic_sdm import select_sdm_top_k
from acsp.modeling import DEFAULT_ENSEMBLE_ALGORITHMS
from benchmark_general_random_taxa_regions import (
    _species_metadata,
    fetch_occurrences,
    rectangle_feature,
)
from gbif_fieldmap_builder_app import (
    auto_remote_spatial_outlier_qc,
    auto_sdm_partition,
    build_automatic_discover_bundle,
    build_presence_background,
    clean_environment_table,
    extract_environment,
    fit_sdm,
    predict_suitability,
    prediction_area_geometry,
    select_environment_variables,
    spatially_balanced_cap,
)

METHODS = (
    "frozen_acsp",
    "local_evidence_top_k",
    "fitted_sdm_top_k",
    "geographic_maximin",
    "random_same_pool_mean",
    "heldout_greedy_oracle",
)
VARIABLES = ["bio1", "bio4", "bio12", "bio15", "bio14"]
PROTOCOL_PATH = Path("validation/sdm_topk_protocol.json")
CONTRACT_PATH = Path("validation/sdm_topk_execution_contract.json")
COHORT_PATH = Path("validation/sdm_topk_untouched_cohort_20260808/predeclared_taxon_region_pairs.csv")
EXPECTED_PROTOCOL = "cea7ba04d53d6af7be5d642746539e46ff924435fd683aa43479ea5a38022652"
EXPECTED_CONTRACT = "1627009619716726e4af2e1ac7dc5ce47fa50dcfefa3bb042364c84b00884bd1"


def _json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _canonical_fingerprint(path: Path, field: str) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop(field, ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not expected or expected != calculated:
        raise ValueError(f"fingerprint mismatch for {path}: expected {expected}, calculated {calculated}")
    return calculated


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coord_columns(frame: pd.DataFrame) -> tuple[str, str]:
    for latitude, longitude in (
        ("_latitude", "_longitude"),
        ("latitude", "longitude"),
        ("decimalLatitude", "decimalLongitude"),
        ("lat", "lon"),
    ):
        if latitude in frame.columns and longitude in frame.columns:
            return latitude, longitude
    raise ValueError("occurrence table has no recognized latitude/longitude columns")


def _distance_matrix_km(held: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    if len(held) == 0 or len(candidates) == 0:
        return np.empty((len(held), len(candidates)), dtype=float)
    lat1 = np.radians(held[:, 0])[:, None]
    lon1 = np.radians(held[:, 1])[:, None]
    lat2 = np.radians(candidates[:, 0])[None, :]
    lon2 = np.radians(candidates[:, 1])[None, :]
    a = np.sin((lat2 - lat1) / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))) / 1000.0


def _stable_ids(frame: pd.DataFrame, pair_id: int, repeat: int) -> pd.DataFrame:
    out = frame.copy().reset_index(drop=True)
    out["candidate_id"] = [
        f"pair{pair_id:03d}-fold{repeat:02d}-candidate{index + 1:05d}"
        for index in range(len(out))
    ]
    return out


def _ids(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty or "candidate_id" not in frame.columns:
        return []
    return frame["candidate_id"].astype(str).tolist()


def _fit_and_score_production_sdm(
    training: pd.DataFrame,
    candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit the existing production SDM from training only and score shared rows."""
    working = training.copy().reset_index(drop=True)
    working["_row_id"] = range(len(working))
    capped = spatially_balanced_cap(working, 300)
    occ_sdm, excluded, qc_report = auto_remote_spatial_outlier_qc(capped)
    qc_report = dict(qc_report or {})
    qc_report.setdefault("included_records", int(len(occ_sdm)))
    audit: dict[str, Any] = {
        "status": "sdm_started",
        "source_training_records": int(len(training)),
        "capped_records": int(len(capped)),
        "qc_presence_records": int(len(occ_sdm)),
        "qc_excluded_records": int(len(excluded)),
        "qc_report": qc_report,
        "requested_variables": VARIABLES,
        "finite_candidate_scores": 0,
    }
    if len(occ_sdm) < 5:
        raise RuntimeError("Too few records remained after automatic SDM quality control.")
    extent = prediction_area_geometry(occ_sdm, "bounding box", 10.0, 20.0)
    partition, partition_reason = auto_sdm_partition(len(occ_sdm), extent)
    audit["partition_method"] = partition
    audit["partition_reason"] = partition_reason
    pb = build_presence_background(occ_sdm, 500, "bounding box", 10.0, 20.0)
    train = extract_environment(pb, VARIABLES, "latitude", "longitude", "power-climatology")
    train, dropped = clean_environment_table(train, VARIABLES, "SDM Top-k training environment")
    audit["environment_training_rows"] = int(len(train))
    audit["environment_training_rows_dropped"] = int(dropped)
    if train.empty or train["presence"].nunique() < 2:
        raise RuntimeError("Too few valid SDM rows remained after environment cleaning.")
    kept, variable_diag = select_environment_variables(
        train,
        VARIABLES,
        "Ecological preset / representative climate set",
        vif_threshold=10.0,
        corr_threshold=0.80,
        custom_variables=VARIABLES,
    )
    if not kept:
        raise RuntimeError("No environmental variables remained after production selection.")
    audit["retained_variables"] = list(kept)
    audit["variable_diagnostics"] = variable_diag.to_dict("records") if not variable_diag.empty else []
    model = fit_sdm(train, kept, list(DEFAULT_ENSEMBLE_ALGORITHMS), partition, 5, 0.05)
    audit["model_metrics"] = model["metrics"].to_dict("records") if isinstance(model.get("metrics"), pd.DataFrame) else []

    candidate_coords = candidates[["candidate_id", "latitude", "longitude"]].copy()
    candidate_env = extract_environment(
        candidate_coords,
        kept,
        "latitude",
        "longitude",
        "power-climatology",
    )
    candidate_env, candidate_dropped = clean_environment_table(
        candidate_env,
        kept,
        "SDM Top-k candidate environment",
    )
    audit["candidate_environment_rows_dropped"] = int(candidate_dropped)
    if not candidate_env.empty:
        candidate_env = predict_suitability(candidate_env, model)
    scored = candidates.copy()
    if not candidate_env.empty and "sdm_suitability" in candidate_env.columns:
        scored = scored.merge(
            candidate_env[["candidate_id", "sdm_suitability"]],
            on="candidate_id",
            how="left",
        )
    else:
        scored["sdm_suitability"] = np.nan
    finite = pd.to_numeric(scored["sdm_suitability"], errors="coerce").notna()
    audit["finite_candidate_scores"] = int(finite.sum())
    audit["shared_candidate_rows"] = int(len(scored))
    if int(finite.sum()) < 5:
        raise RuntimeError("Fewer than five shared candidates received finite SDM suitability.")
    audit["status"] = "sdm_ok"
    return scored, audit


def build_operational_decisions(
    training: pd.DataFrame,
    pair: pd.Series,
    repeat: int,
    *,
    protocol: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Build all operational decisions without any held-out input."""
    pair_id = int(pair.pair_id)
    bounds = (float(pair.west), float(pair.south), float(pair.east), float(pair.north))
    metadata = _species_metadata(int(pair.speciesKey)) or {}
    metadata.setdefault("kingdom", "Plantae" if str(pair.taxon_group) == "plant" else "Animalia")
    rebuilt = training.copy().reset_index(drop=True)
    rebuilt["_row_id"] = range(len(rebuilt))
    bundle = build_automatic_discover_bundle(
        str(pair.scientific_name),
        rebuilt,
        "untouched SDM Top-k benchmark",
        str(pair.region_name),
        override_row_ids=rebuilt["_row_id"].tolist(),
        taxon_metadata=metadata,
        survey_bounds=bounds,
        survey_features=[rectangle_feature(bounds, str(pair.region_name))],
        candidate_generation_only=True,
    )
    candidates = bundle["potential_candidates"].copy().reset_index(drop=True)
    if not candidates.empty:
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
    candidates = _stable_ids(candidates, pair_id, repeat)
    decisions: dict[str, Any] = {
        "pair_id": pair_id,
        "repeat": int(repeat),
        "outcomes_available_to_operational_selectors": False,
        "methods": {},
        "random_same_pool_draws": [],
    }
    statuses = {method: "shared_candidate_failure" for method in METHODS}
    sdm_audit: dict[str, Any] = {"status": "not_run", "reason": "shared candidate pool unavailable"}
    if len(candidates) < 5:
        return candidates, decisions, {"method_status": statuses, "sdm_audit": sdm_audit}

    group = str(pair.taxon_group)
    policy = ValidatedCorePolicy.for_taxon_group(group)
    acsp_selected = select_validated_core(candidates, policy)
    base_config = DecisionBaselineConfig(
        k=5,
        id_col="candidate_id",
        score_col="component_local_habitat_score",
        random_draws=200,
        random_state=int(protocol["outer_validation"]["fold_seed_base"]) + pair_id * 1000 + int(repeat),
    )
    local_selected = select_score_top_k(candidates, base_config)
    geographic_selected = select_geographic_farthest(candidates, base_config)
    random_draws = random_same_pool_sets(candidates, base_config)
    decisions["methods"].update({
        "frozen_acsp": _ids(acsp_selected),
        "local_evidence_top_k": _ids(local_selected),
        "geographic_maximin": _ids(geographic_selected),
    })
    decisions["random_same_pool_draws"] = [_ids(draw) for draw in random_draws]
    for method in ("frozen_acsp", "local_evidence_top_k", "geographic_maximin", "random_same_pool_mean"):
        statuses[method] = "ok"

    try:
        candidates, sdm_audit = _fit_and_score_production_sdm(training, candidates)
        finite = candidates[pd.to_numeric(candidates["sdm_suitability"], errors="coerce").notna()].copy()
        sdm_selected = select_sdm_top_k(finite, 5, id_col="candidate_id")
        decisions["methods"]["fitted_sdm_top_k"] = _ids(sdm_selected)
        statuses["fitted_sdm_top_k"] = "ok"
    except Exception as exc:
        if "sdm_suitability" not in candidates.columns:
            candidates["sdm_suitability"] = np.nan
        sdm_audit = {
            **sdm_audit,
            "status": "sdm_failure",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        decisions["methods"]["fitted_sdm_top_k"] = []
        statuses["fitted_sdm_top_k"] = "sdm_failure"
    return candidates, decisions, {"method_status": statuses, "sdm_audit": sdm_audit}


def _coverage_sets(candidates: pd.DataFrame, heldout: pd.DataFrame, radius_km: float) -> tuple[dict[str, set[str]], set[str]]:
    latitude_col, longitude_col = _coord_columns(heldout)
    held_coords = heldout[[latitude_col, longitude_col]].to_numpy(float)
    candidate_coords = candidates[["latitude", "longitude"]].to_numpy(float)
    distances = _distance_matrix_km(held_coords, candidate_coords)
    held_ids = heldout["_outer_occurrence_id"].astype(str).to_numpy()
    mapping = {
        str(candidates.iloc[index]["candidate_id"]): set(held_ids[distances[:, index] <= float(radius_km)])
        for index in range(len(candidates))
    }
    return mapping, set(held_ids)


def _recall(ids: list[str], coverage: dict[str, set[str]], all_ids: set[str]) -> float:
    if not all_ids or not ids:
        return 0.0
    recovered: set[str] = set()
    for candidate_id in ids:
        recovered |= coverage.get(str(candidate_id), set())
    return len(recovered & all_ids) / len(all_ids)


def _oracle_ids(candidates: pd.DataFrame, coverage: dict[str, set[str]], k: int = 5) -> list[str]:
    available = candidates["candidate_id"].astype(str).tolist()
    selected: list[str] = []
    recovered: set[str] = set()
    while available and len(selected) < min(k, len(candidates)):
        chosen = min(
            available,
            key=lambda candidate_id: (-len(coverage.get(candidate_id, set()) - recovered), candidate_id),
        )
        selected.append(chosen)
        recovered |= coverage.get(chosen, set())
        available.remove(chosen)
    return selected


def attach_outcomes(
    candidates: pd.DataFrame,
    heldout: pd.DataFrame,
    decisions: dict[str, Any],
    state: dict[str, Any],
    pair: pd.Series,
    repeat: int,
    *,
    radius_km: float,
) -> tuple[pd.DataFrame, list[str]]:
    statuses = dict(state["method_status"])
    if candidates.empty or len(candidates) < 5:
        rows = [{
            "pair_id": int(pair.pair_id), "repeat": int(repeat), "taxon_group": str(pair.taxon_group),
            "scientific_name": str(pair.scientific_name), "region_name": str(pair.region_name),
            "decision_method": method, "method_status": statuses.get(method, "shared_candidate_failure"),
            "heldout_recall": 0.0, "heldout_records": int(len(heldout)), "candidate_pool": int(len(candidates)),
            "sdm_fold_ok": False, "selected_ids": "",
        } for method in METHODS]
        return pd.DataFrame(rows), []

    coverage, all_ids = _coverage_sets(candidates, heldout, radius_km)
    oracle_ids = _oracle_ids(candidates, coverage, 5)
    statuses["heldout_greedy_oracle"] = "ok"
    rows: list[dict[str, Any]] = []
    for method in ("frozen_acsp", "local_evidence_top_k", "fitted_sdm_top_k", "geographic_maximin"):
        ids = list(decisions.get("methods", {}).get(method, []))
        rows.append({
            "pair_id": int(pair.pair_id), "repeat": int(repeat), "taxon_group": str(pair.taxon_group),
            "scientific_name": str(pair.scientific_name), "region_name": str(pair.region_name),
            "decision_method": method, "method_status": statuses.get(method, "unknown"),
            "heldout_recall": _recall(ids, coverage, all_ids) if statuses.get(method) == "ok" else 0.0,
            "heldout_records": int(len(all_ids)), "candidate_pool": int(len(candidates)),
            "sdm_fold_ok": statuses.get("fitted_sdm_top_k") == "ok", "selected_ids": ";".join(ids),
        })
    random_values = [
        _recall(list(ids), coverage, all_ids)
        for ids in decisions.get("random_same_pool_draws", [])
    ]
    rows.append({
        "pair_id": int(pair.pair_id), "repeat": int(repeat), "taxon_group": str(pair.taxon_group),
        "scientific_name": str(pair.scientific_name), "region_name": str(pair.region_name),
        "decision_method": "random_same_pool_mean", "method_status": statuses.get("random_same_pool_mean", "unknown"),
        "heldout_recall": float(np.mean(random_values)) if random_values else 0.0,
        "heldout_records": int(len(all_ids)), "candidate_pool": int(len(candidates)),
        "sdm_fold_ok": statuses.get("fitted_sdm_top_k") == "ok", "selected_ids": "",
    })
    rows.append({
        "pair_id": int(pair.pair_id), "repeat": int(repeat), "taxon_group": str(pair.taxon_group),
        "scientific_name": str(pair.scientific_name), "region_name": str(pair.region_name),
        "decision_method": "heldout_greedy_oracle", "method_status": "ok",
        "heldout_recall": _recall(oracle_ids, coverage, all_ids),
        "heldout_records": int(len(all_ids)), "candidate_pool": int(len(candidates)),
        "sdm_fold_ok": statuses.get("fitted_sdm_top_k") == "ok", "selected_ids": ";".join(oracle_ids),
    })
    return pd.DataFrame(rows), oracle_ids


def _write_fold(
    directory: Path,
    training: pd.DataFrame,
    heldout: pd.DataFrame,
    candidates: pd.DataFrame,
    decisions: dict[str, Any],
    state: dict[str, Any],
    results: pd.DataFrame,
    oracle_ids: list[str],
    *,
    pair: pd.Series,
    repeat: int,
    held_blocks: set[str],
    protocol_fp: str,
    contract_fp: str,
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "training_occurrences": directory / "training_occurrences.csv",
        "candidate_pool_pre_outcome": directory / "candidate_pool_pre_outcome.csv",
        "decision_sets": directory / "decision_sets.json",
        "sdm_audit": directory / "sdm_audit.json",
        "held_out_occurrences": directory / "held_out_occurrences.csv",
        "fold_result": directory / "fold_result.csv",
    }
    training.to_csv(paths["training_occurrences"], index=False)
    candidates.to_csv(paths["candidate_pool_pre_outcome"], index=False)
    paths["decision_sets"].write_text(json.dumps(decisions, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    paths["sdm_audit"].write_text(json.dumps(state["sdm_audit"], indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    heldout.to_csv(paths["held_out_occurrences"], index=False)
    results.to_csv(paths["fold_result"], index=False)
    manifest = {
        "pair_id": int(pair.pair_id),
        "repeat": int(repeat),
        "scientific_name": str(pair.scientific_name),
        "taxon_group": str(pair.taxon_group),
        "heldout_blocks": sorted(held_blocks),
        "training_records": int(len(training)),
        "heldout_records": int(len(heldout)),
        "candidate_pool": int(len(candidates)),
        "protocol_fingerprint": protocol_fp,
        "execution_contract_fingerprint": contract_fp,
        "outcomes_available_to_operational_selectors": False,
        "method_status": state["method_status"],
        "oracle_selected_after_outcome_attachment": oracle_ids,
        "files": {
            name: {"path": path.name, "sha256": _sha256(path)}
            for name, path in paths.items()
        },
    }
    (directory / "fold_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8"
    )
    return manifest


def _failure_rows(pair: pd.Series, repeats: int, reason: str) -> pd.DataFrame:
    rows = []
    for repeat in range(1, repeats + 1):
        for method in METHODS:
            rows.append({
                "pair_id": int(pair.pair_id), "repeat": repeat, "taxon_group": str(pair.taxon_group),
                "scientific_name": str(pair.scientific_name), "region_name": str(pair.region_name),
                "decision_method": method, "method_status": "pair_setup_failure",
                "heldout_recall": 0.0, "heldout_records": 0, "candidate_pool": 0,
                "sdm_fold_ok": False, "selected_ids": "", "failure_reason": reason,
            })
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> dict[str, Any]:
    protocol_fp = _canonical_fingerprint(PROTOCOL_PATH, "protocol_fingerprint")
    contract_fp = _canonical_fingerprint(CONTRACT_PATH, "contract_fingerprint")
    if protocol_fp != EXPECTED_PROTOCOL or contract_fp != EXPECTED_CONTRACT:
        raise ValueError("frozen protocol/contract fingerprint differs from runner constants")
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    cohort = pd.read_csv(COHORT_PATH)
    selected = cohort[cohort["pair_id"].astype(int).eq(int(args.pair_id))]
    if len(selected) != 1:
        raise ValueError(f"pair_id {args.pair_id} is not uniquely present in frozen cohort")
    pair = selected.iloc[0]
    root = Path(args.output) / f"pair_{int(pair.pair_id):03d}"
    root.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    try:
        occurrences = fetch_occurrences(pair, int(protocol["cohort"]["records_per_pair"]))
        latitude_col, longitude_col = _coord_columns(occurrences)
        work = occurrences.copy().reset_index(drop=True)
        work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
        work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
        work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
        if len(work) < 4:
            raise ValueError("fewer than four valid occurrence coordinates")
        work["_outer_occurrence_id"] = [
            f"pair{int(pair.pair_id):03d}-occurrence{index + 1:05d}" for index in range(len(work))
        ]
        block = float(protocol["outer_validation"]["block_degrees"])
        work["_outer_block"] = (
            np.floor(work[latitude_col] / block).astype(int).astype(str)
            + ":" + np.floor(work[longitude_col] / block).astype(int).astype(str)
        )
        blocks = work["_outer_block"].drop_duplicates().to_numpy()
        if len(blocks) < 2:
            raise ValueError("occurrences occupy fewer than two outer spatial blocks")
        rng = np.random.default_rng(int(protocol["outer_validation"]["fold_seed_base"]) + int(pair.pair_id))
        n_holdout = min(
            len(blocks) - 1,
            max(1, int(round(len(blocks) * float(protocol["outer_validation"]["holdout_fraction"])))),
        )
        all_results: list[pd.DataFrame] = []
        for repeat in range(1, int(protocol["outer_validation"]["repeats"]) + 1):
            held_blocks = set(rng.choice(blocks, size=n_holdout, replace=False).tolist())
            heldout = work[work["_outer_block"].isin(held_blocks)].copy().reset_index(drop=True)
            training = work[~work["_outer_block"].isin(held_blocks)].drop(columns=["_outer_block", "_outer_occurrence_id"]).copy().reset_index(drop=True)
            candidates, decisions, state = build_operational_decisions(training, pair, repeat, protocol=protocol)
            result, oracle_ids = attach_outcomes(
                candidates, heldout, decisions, state, pair, repeat,
                radius_km=float(protocol["outer_validation"]["recovery_radius_km"]),
            )
            all_results.append(result)
            manifests.append(_write_fold(
                root / f"fold_{repeat:03d}", training, heldout, candidates, decisions, state,
                result, oracle_ids, pair=pair, repeat=repeat, held_blocks=held_blocks,
                protocol_fp=protocol_fp, contract_fp=contract_fp,
            ))
        fold_results = pd.concat(all_results, ignore_index=True)
        pair_status = "complete"
        pair_error = ""
    except Exception as exc:
        fold_results = _failure_rows(pair, int(protocol["outer_validation"]["repeats"]), f"{type(exc).__name__}: {exc}")
        pair_status = "pair_setup_failure"
        pair_error = f"{type(exc).__name__}: {exc}"
    fold_results.to_csv(root / "fold_results.csv", index=False)
    pair_manifest = {
        "pair_id": int(pair.pair_id),
        "scientific_name": str(pair.scientific_name),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "pair_status": pair_status,
        "pair_error": pair_error,
        "protocol_fingerprint": protocol_fp,
        "execution_contract_fingerprint": contract_fp,
        "expected_repeats": int(protocol["outer_validation"]["repeats"]),
        "written_fold_manifests": len(manifests),
        "sdm_ok_folds": int(
            fold_results.loc[fold_results["decision_method"].eq("fitted_sdm_top_k"), "method_status"].eq("ok").sum()
        ),
        "fold_result_sha256": _sha256(root / "fold_results.csv"),
    }
    (root / "pair_manifest.json").write_text(
        json.dumps(pair_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return pair_manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-id", type=int, required=True)
    command.add_argument("--output", default="sdm_topk_pair_results")
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
