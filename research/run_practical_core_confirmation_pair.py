#!/usr/bin/env python3
"""Run one frozen taxon-region pair for ACSP Practical Core confirmation.

Every operational survey decision is constructed from the outer training fold
only. Held-out coordinates are attached only after the deterministic ACSP
decisions and all official GRTS draws have been frozen to disk.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np
import pandas as pd

from acsp.decision_baselines import (
    DecisionBaselineConfig,
    random_same_pool_sets,
    select_dual_space_farthest,
    select_environmental_farthest,
    select_geographic_farthest,
)
from acsp.planning import EARTH_RADIUS_M, integrated_candidate_scores
from acsp.practical_core import PracticalCorePolicy, select_practical_core
from acsp.validated_core import ValidatedCorePolicy, select_validated_core
from benchmark_general_random_taxa_regions import (
    _species_metadata,
    fetch_occurrences,
    rectangle_feature,
)
from gbif_fieldmap_builder_app import build_automatic_discover_bundle


CORE_PROTOCOL_PATH = Path("validation/acsp_practical_core_protocol.json")
CONFIRMATION_PROTOCOL_PATH = Path(
    "validation/acsp_practical_core_untouched_confirmation_protocol.json"
)
DEFAULT_COHORT_PATH = Path(
    "validation/practical_core_untouched_cohort_20260811/"
    "predeclared_taxon_region_pairs.csv"
)
EXPECTED_CORE_PROTOCOL = (
    "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905"
)
EXPECTED_CONFIRMATION_PROTOCOL = (
    "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9"
)
ENVIRONMENTAL_COLUMNS = ("elevation", "slope", "aspect", "roughness", "tpi")
DETERMINISTIC_METHODS = (
    "acsp_practical_core",
    "frozen_acsp_v1_historical",
    "geographic_maximin",
    "environmental_maximin_when_eligible",
    "dual_space_maximin_when_eligible",
)
GRTS_METHODS = (
    "official_grts_equal",
    "official_grts_proportional_local",
    "official_grts_proportional_local_mindis10km",
)
PRIMARY_STAGE_METHODS = (
    *DETERMINISTIC_METHODS,
    *GRTS_METHODS,
    "same_pool_random_mean",
    "fitted_sdm_top_k_when_eligible",
    "heldout_greedy_oracle_nonoperational",
)


def _canonical_fingerprint(path: Path, field: str) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop(field, ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not expected or expected != calculated:
        raise ValueError(
            f"protocol fingerprint mismatch for {path}: "
            f"file={expected!r}, calculated={calculated!r}"
        )
    payload[field] = expected
    return payload, calculated


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


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
    a = (
        np.sin((lat2 - lat1) / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    )
    return (
        2.0
        * EARTH_RADIUS_M
        * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
        / 1000.0
    )


def _stable_ids(frame: pd.DataFrame, pair_id: int, repeat: int) -> pd.DataFrame:
    out = frame.copy().reset_index(drop=True)
    out["candidate_id"] = [
        f"pair{pair_id:03d}-fold{repeat:02d}-candidate{index + 1:05d}"
        for index in range(len(out))
    ]
    return out


def _ids(frame: pd.DataFrame | None) -> list[str]:
    if frame is None or frame.empty or "candidate_id" not in frame.columns:
        return []
    return frame["candidate_id"].astype(str).tolist()


def _split_ids(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    return [item for item in str(value).split(";") if item]


def build_candidate_pool(
    training: pd.DataFrame,
    pair: pd.Series,
    repeat: int,
) -> pd.DataFrame:
    """Generate the shared candidate frame from training occurrences only."""
    pair_id = int(pair.pair_id)
    bounds = (float(pair.west), float(pair.south), float(pair.east), float(pair.north))
    metadata = _species_metadata(int(pair.speciesKey)) or {}
    metadata.setdefault(
        "kingdom", "Plantae" if str(pair.taxon_group) == "plant" else "Animalia"
    )
    rebuilt = training.copy().reset_index(drop=True)
    rebuilt["_row_id"] = range(len(rebuilt))
    bundle = build_automatic_discover_bundle(
        str(pair.scientific_name),
        rebuilt,
        "Practical Core untouched confirmation",
        str(pair.region_name),
        override_row_ids=rebuilt["_row_id"].tolist(),
        taxon_metadata=metadata,
        survey_bounds=bounds,
        survey_features=[rectangle_feature(bounds, str(pair.region_name))],
        candidate_generation_only=True,
    )
    candidates = bundle["potential_candidates"].copy().reset_index(drop=True)
    if candidates.empty:
        return _stable_ids(candidates, pair_id, repeat)

    candidates["latitude"] = pd.to_numeric(candidates["latitude"], errors="coerce")
    candidates["longitude"] = pd.to_numeric(candidates["longitude"], errors="coerce")
    candidates = candidates.dropna(subset=["latitude", "longitude"]).reset_index(
        drop=True
    )
    candidate_type = candidates.get(
        "candidate_type", pd.Series("", index=candidates.index)
    ).astype(str)
    candidates = candidates[
        ~candidate_type.str.contains(
            "occurrence-supported|known-location|known anchor",
            case=False,
            na=False,
        )
    ].reset_index(drop=True)
    if not candidates.empty:
        candidates = integrated_candidate_scores(
            candidates, exclude_occurrence_derived=True
        )
    return _stable_ids(candidates, pair_id, repeat)


def _environmental_eligible(candidates: pd.DataFrame) -> bool:
    if not all(column in candidates.columns for column in ENVIRONMENTAL_COLUMNS):
        return False
    values = candidates[list(ENVIRONMENTAL_COLUMNS)].apply(
        pd.to_numeric, errors="coerce"
    )
    return bool(values.notna().any(axis=0).all())


def build_deterministic_decisions(
    candidates: pd.DataFrame,
    pair: pd.Series,
    repeat: int,
    protocol: dict[str, Any],
) -> tuple[dict[str, list[str]], list[list[str]], dict[str, str]]:
    """Freeze all non-GRTS same-pool choices before outcomes are attached."""
    methods: dict[str, list[str]] = {method: [] for method in DETERMINISTIC_METHODS}
    statuses = {method: "shared_candidate_failure" for method in DETERMINISTIC_METHODS}
    random_sets: list[list[str]] = []
    if len(candidates) < 5:
        return methods, random_sets, statuses

    top_k = int(protocol["practical_core"]["top_k"])
    practical = select_practical_core(candidates, PracticalCorePolicy(top_k=top_k))
    historical = select_validated_core(
        candidates,
        ValidatedCorePolicy.for_taxon_group(str(pair.taxon_group)),
    )
    base_config = DecisionBaselineConfig(
        k=top_k,
        id_col="candidate_id",
        score_col="component_local_habitat_score",
        random_draws=200,
        random_state=(
            int(protocol["outer_validation"]["fold_seed_base"])
            + int(pair.pair_id) * 1000
            + int(repeat)
        ),
    )
    geographic = select_geographic_farthest(candidates, base_config)

    methods["acsp_practical_core"] = _ids(practical)
    methods["frozen_acsp_v1_historical"] = _ids(historical)
    methods["geographic_maximin"] = _ids(geographic)
    for method in (
        "acsp_practical_core",
        "frozen_acsp_v1_historical",
        "geographic_maximin",
    ):
        statuses[method] = "ok"

    # Practical Core is deliberately the same local-only rule as the strongest
    # development baseline. Keep this assertion to prevent implementation drift.
    local_order = (
        candidates.assign(
            _score=pd.to_numeric(
                candidates["component_local_habitat_score"], errors="coerce"
            ).fillna(float("-inf")),
            _id=candidates["candidate_id"].astype(str),
        )
        .sort_values(["_score", "_id"], ascending=[False, True], kind="mergesort")
        .head(top_k)["candidate_id"]
        .astype(str)
        .tolist()
    )
    if methods["acsp_practical_core"] != local_order:
        raise AssertionError("Practical Core drifted from frozen local-only ordering")

    random_sets = [_ids(draw) for draw in random_same_pool_sets(candidates, base_config)]

    if _environmental_eligible(candidates):
        env_config = DecisionBaselineConfig(
            k=top_k,
            id_col="candidate_id",
            score_col="component_local_habitat_score",
            environmental_cols=ENVIRONMENTAL_COLUMNS,
            dual_environment_weight=0.5,
            random_draws=1,
            random_state=base_config.random_state,
        )
        try:
            environmental = select_environmental_farthest(candidates, env_config)
            dual = select_dual_space_farthest(candidates, env_config)
            methods["environmental_maximin_when_eligible"] = _ids(environmental)
            methods["dual_space_maximin_when_eligible"] = _ids(dual)
            statuses["environmental_maximin_when_eligible"] = "ok"
            statuses["dual_space_maximin_when_eligible"] = "ok"
        except Exception as exc:
            statuses["environmental_maximin_when_eligible"] = (
                f"environmental_baseline_failure:{type(exc).__name__}"
            )
            statuses["dual_space_maximin_when_eligible"] = (
                f"environmental_baseline_failure:{type(exc).__name__}"
            )
    else:
        statuses["environmental_maximin_when_eligible"] = "not_eligible"
        statuses["dual_space_maximin_when_eligible"] = "not_eligible"

    return methods, random_sets, statuses


def run_grts_pre_outcome(
    candidate_path: Path,
    output_path: Path,
    pair: pd.Series,
    repeat: int,
    protocol: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run the pinned official GRTS batch using candidate attributes only."""
    grts = protocol["grts"]
    command = [
        "Rscript",
        "benchmark_methods/grts_batch_candidate_frame.R",
        "--input",
        str(candidate_path),
        "--output",
        str(output_path),
        "--draws",
        str(int(grts["draws_per_fold"])),
        "--seed-base",
        str(int(grts["seed_base"])),
        "--pair-id",
        str(int(pair.pair_id)),
        "--repeat",
        str(int(repeat)),
        "--k",
        str(int(protocol["practical_core"]["top_k"])),
        "--replacements",
        str(int(grts["replacement_sites"])),
        "--score-col",
        "component_local_habitat_score",
    ]
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    audit = {
        "command": command,
        "returncode": int(completed.returncode),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "outcomes_available_to_selector": False,
    }
    if completed.returncode != 0 or not output_path.exists():
        audit["status"] = "grts_process_failure"
        return pd.DataFrame(), audit
    draws = pd.read_csv(output_path)
    audit["status"] = "ok"
    audit["rows"] = int(len(draws))
    audit["variants"] = sorted(draws["variant"].dropna().astype(str).unique().tolist())
    return draws, audit


def _coverage_sets(
    candidates: pd.DataFrame,
    heldout: pd.DataFrame,
    radius_km: float,
) -> tuple[dict[str, set[str]], set[str]]:
    latitude_col, longitude_col = _coord_columns(heldout)
    held_coords = heldout[[latitude_col, longitude_col]].to_numpy(float)
    candidate_coords = candidates[["latitude", "longitude"]].to_numpy(float)
    distances = _distance_matrix_km(held_coords, candidate_coords)
    held_ids = heldout["_outer_occurrence_id"].astype(str).to_numpy()
    mapping = {
        str(candidates.iloc[index]["candidate_id"]): set(
            held_ids[distances[:, index] <= float(radius_km)]
        )
        for index in range(len(candidates))
    }
    return mapping, set(held_ids)


def _recall(
    ids: list[str],
    coverage: dict[str, set[str]],
    all_ids: set[str],
) -> float:
    if not all_ids or not ids:
        return 0.0
    recovered: set[str] = set()
    for candidate_id in ids:
        recovered |= coverage.get(str(candidate_id), set())
    return len(recovered & all_ids) / len(all_ids)


def _oracle_ids(
    candidates: pd.DataFrame,
    coverage: dict[str, set[str]],
    k: int = 5,
) -> list[str]:
    available = candidates["candidate_id"].astype(str).tolist()
    selected: list[str] = []
    recovered: set[str] = set()
    while available and len(selected) < min(k, len(candidates)):
        chosen = min(
            available,
            key=lambda candidate_id: (
                -len(coverage.get(candidate_id, set()) - recovered),
                candidate_id,
            ),
        )
        selected.append(chosen)
        recovered |= coverage.get(chosen, set())
        available.remove(chosen)
    return selected


def score_frozen_decisions(
    candidates: pd.DataFrame,
    heldout: pd.DataFrame,
    deterministic: dict[str, list[str]],
    deterministic_status: dict[str, str],
    random_sets: list[list[str]],
    grts_pre_outcome: pd.DataFrame,
    pair: pd.Series,
    repeat: int,
    protocol: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Attach held-out outcomes only after all operational choices are frozen."""
    radius = float(protocol["practical_core"]["recovery_radius_km"])
    if len(candidates) < int(protocol["practical_core"]["top_k"]):
        rows = []
        for method in PRIMARY_STAGE_METHODS:
            recall = np.nan if method == "fitted_sdm_top_k_when_eligible" else 0.0
            rows.append(
                {
                    "pair_id": int(pair.pair_id),
                    "repeat": int(repeat),
                    "taxon_group": str(pair.taxon_group),
                    "scientific_name": str(pair.scientific_name),
                    "region_name": str(pair.region_name),
                    "decision_method": method,
                    "method_status": (
                        "secondary_not_run_in_primary_stage"
                        if method == "fitted_sdm_top_k_when_eligible"
                        else "shared_candidate_failure"
                    ),
                    "heldout_recall": recall,
                    "heldout_records": int(len(heldout)),
                    "candidate_pool": int(len(candidates)),
                    "selected_ids": "",
                }
            )
        return pd.DataFrame(rows), pd.DataFrame(), []

    coverage, all_ids = _coverage_sets(candidates, heldout, radius)
    rows: list[dict[str, Any]] = []
    for method in DETERMINISTIC_METHODS:
        ids = deterministic.get(method, [])
        status = deterministic_status.get(method, "unknown")
        value = _recall(ids, coverage, all_ids) if status == "ok" else 0.0
        rows.append(
            {
                "pair_id": int(pair.pair_id),
                "repeat": int(repeat),
                "taxon_group": str(pair.taxon_group),
                "scientific_name": str(pair.scientific_name),
                "region_name": str(pair.region_name),
                "decision_method": method,
                "method_status": status,
                "heldout_recall": value,
                "heldout_records": int(len(all_ids)),
                "candidate_pool": int(len(candidates)),
                "selected_ids": ";".join(ids),
            }
        )

    random_values = [_recall(ids, coverage, all_ids) for ids in random_sets]
    rows.append(
        {
            "pair_id": int(pair.pair_id),
            "repeat": int(repeat),
            "taxon_group": str(pair.taxon_group),
            "scientific_name": str(pair.scientific_name),
            "region_name": str(pair.region_name),
            "decision_method": "same_pool_random_mean",
            "method_status": "ok" if random_values else "random_failure",
            "heldout_recall": float(np.mean(random_values)) if random_values else 0.0,
            "heldout_records": int(len(all_ids)),
            "candidate_pool": int(len(candidates)),
            "selected_ids": "",
        }
    )

    expected_draws = int(protocol["grts"]["draws_per_fold"])
    scored_grts_rows: list[dict[str, Any]] = []
    for variant in GRTS_METHODS:
        variant_rows = (
            grts_pre_outcome[
                grts_pre_outcome.get("variant", pd.Series(dtype=str)).astype(str).eq(
                    variant
                )
            ].copy()
            if not grts_pre_outcome.empty
            else pd.DataFrame()
        )
        recalls: list[float] = []
        successful = 0
        for draw_index in range(1, expected_draws + 1):
            selected = variant_rows[
                pd.to_numeric(
                    variant_rows.get("draw_index", pd.Series(dtype=float)),
                    errors="coerce",
                ).eq(draw_index)
            ]
            if len(selected) == 1:
                row = selected.iloc[0].to_dict()
                ids = _split_ids(row.get("base_ids"))
                error_raw = row.get("error_message")
                error_message = "" if pd.isna(error_raw) else str(error_raw)
                value = _recall(ids, coverage, all_ids) if ids else 0.0
                if ids and not error_message:
                    successful += 1
            else:
                row = {
                    "pair_id": int(pair.pair_id),
                    "repeat": int(repeat),
                    "variant": variant,
                    "draw_index": draw_index,
                    "seed": np.nan,
                    "base_count": 0,
                    "base_ids": "",
                    "replacement_count": 0,
                    "replacement_ids": "",
                    "warning_message": "",
                    "error_message": "missing_pre_outcome_draw",
                }
                value = 0.0
            row["heldout_recall"] = value
            row["heldout_records"] = int(len(all_ids))
            row["outcome_attached_after_selection"] = True
            scored_grts_rows.append(row)
            recalls.append(value)
        status = (
            "ok"
            if successful == expected_draws
            else ("partial_grts_failure" if successful else "grts_failure")
        )
        rows.append(
            {
                "pair_id": int(pair.pair_id),
                "repeat": int(repeat),
                "taxon_group": str(pair.taxon_group),
                "scientific_name": str(pair.scientific_name),
                "region_name": str(pair.region_name),
                "decision_method": variant,
                "method_status": status,
                "heldout_recall": float(np.mean(recalls)) if recalls else 0.0,
                "heldout_records": int(len(all_ids)),
                "candidate_pool": int(len(candidates)),
                "selected_ids": "",
                "grts_successful_draws": int(successful),
                "grts_expected_draws": int(expected_draws),
            }
        )

    # SDM is deliberately scored in a later frozen secondary stage.
    rows.append(
        {
            "pair_id": int(pair.pair_id),
            "repeat": int(repeat),
            "taxon_group": str(pair.taxon_group),
            "scientific_name": str(pair.scientific_name),
            "region_name": str(pair.region_name),
            "decision_method": "fitted_sdm_top_k_when_eligible",
            "method_status": "secondary_not_run_in_primary_stage",
            "heldout_recall": np.nan,
            "heldout_records": int(len(all_ids)),
            "candidate_pool": int(len(candidates)),
            "selected_ids": "",
        }
    )

    oracle_ids = _oracle_ids(
        candidates, coverage, int(protocol["practical_core"]["top_k"])
    )
    rows.append(
        {
            "pair_id": int(pair.pair_id),
            "repeat": int(repeat),
            "taxon_group": str(pair.taxon_group),
            "scientific_name": str(pair.scientific_name),
            "region_name": str(pair.region_name),
            "decision_method": "heldout_greedy_oracle_nonoperational",
            "method_status": "nonoperational_outcome_oracle",
            "heldout_recall": _recall(oracle_ids, coverage, all_ids),
            "heldout_records": int(len(all_ids)),
            "candidate_pool": int(len(candidates)),
            "selected_ids": ";".join(oracle_ids),
        }
    )
    return pd.DataFrame(rows), pd.DataFrame(scored_grts_rows), oracle_ids


def write_fold_artifact(
    directory: Path,
    training: pd.DataFrame,
    heldout: pd.DataFrame,
    candidates: pd.DataFrame,
    deterministic: dict[str, list[str]],
    deterministic_status: dict[str, str],
    random_sets: list[list[str]],
    grts_pre_outcome: pd.DataFrame,
    grts_audit: dict[str, Any],
    fold_results: pd.DataFrame,
    grts_scored: pd.DataFrame,
    oracle_ids: list[str],
    pair: pd.Series,
    repeat: int,
    held_blocks: set[str],
    core_fp: str,
    confirmation_fp: str,
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "training_occurrences": directory / "training_occurrences.csv",
        "candidate_pool_pre_outcome": directory / "candidate_pool_pre_outcome.csv",
        "deterministic_decisions_pre_outcome": directory
        / "deterministic_decisions_pre_outcome.json",
        "grts_draws_pre_outcome": directory / "grts_draws_pre_outcome.csv",
        "grts_process_audit": directory / "grts_process_audit.json",
        "held_out_occurrences": directory / "held_out_occurrences.csv",
        "fold_result": directory / "fold_result.csv",
        "grts_draws_scored": directory / "grts_draws_scored.csv",
    }

    training.to_csv(paths["training_occurrences"], index=False)
    candidates.to_csv(paths["candidate_pool_pre_outcome"], index=False)
    paths["deterministic_decisions_pre_outcome"].write_text(
        json.dumps(
            {
                "methods": deterministic,
                "method_status": deterministic_status,
                "random_same_pool_draws": random_sets,
                "outcomes_available_to_selectors": False,
            },
            indent=2,
            ensure_ascii=False,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    grts_pre_outcome.to_csv(paths["grts_draws_pre_outcome"], index=False)
    paths["grts_process_audit"].write_text(
        json.dumps(grts_audit, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )

    # Outcome-bearing files are deliberately written only after all files above.
    heldout.to_csv(paths["held_out_occurrences"], index=False)
    fold_results.to_csv(paths["fold_result"], index=False)
    grts_scored.to_csv(paths["grts_draws_scored"], index=False)

    manifest = {
        "pair_id": int(pair.pair_id),
        "repeat": int(repeat),
        "scientific_name": str(pair.scientific_name),
        "taxon_group": str(pair.taxon_group),
        "heldout_blocks": sorted(held_blocks),
        "training_records": int(len(training)),
        "heldout_records": int(len(heldout)),
        "candidate_pool": int(len(candidates)),
        "practical_core_fingerprint": core_fp,
        "confirmation_protocol_fingerprint": confirmation_fp,
        "outcomes_available_to_operational_selectors": False,
        "oracle_selected_after_outcome_attachment": oracle_ids,
        "files": {
            name: {"path": path.name, "sha256": _sha256(path)}
            for name, path in paths.items()
        },
    }
    (directory / "fold_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=_json_default)
        + "\n",
        encoding="utf-8",
    )
    return manifest


def _failure_rows(
    pair: pd.Series,
    repeats: int,
    reason: str,
) -> pd.DataFrame:
    rows = []
    for repeat in range(1, repeats + 1):
        for method in PRIMARY_STAGE_METHODS:
            rows.append(
                {
                    "pair_id": int(pair.pair_id),
                    "repeat": repeat,
                    "taxon_group": str(pair.taxon_group),
                    "scientific_name": str(pair.scientific_name),
                    "region_name": str(pair.region_name),
                    "decision_method": method,
                    "method_status": "pair_setup_failure",
                    "heldout_recall": (
                        np.nan
                        if method == "fitted_sdm_top_k_when_eligible"
                        else 0.0
                    ),
                    "heldout_records": 0,
                    "candidate_pool": 0,
                    "selected_ids": "",
                    "failure_reason": reason,
                }
            )
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> dict[str, Any]:
    _, core_fp = _canonical_fingerprint(CORE_PROTOCOL_PATH, "fingerprint")
    confirmation, confirmation_fp = _canonical_fingerprint(
        CONFIRMATION_PROTOCOL_PATH, "protocol_fingerprint"
    )
    if core_fp != EXPECTED_CORE_PROTOCOL:
        raise ValueError("Practical Core fingerprint differs from runner constant")
    if confirmation_fp != EXPECTED_CONFIRMATION_PROTOCOL:
        raise ValueError("confirmation fingerprint differs from runner constant")
    if confirmation["practical_core"]["protocol_fingerprint"] != core_fp:
        raise ValueError("confirmation protocol does not point to frozen Practical Core")

    cohort = pd.read_csv(args.cohort)
    selected = cohort[pd.to_numeric(cohort["pair_id"], errors="coerce").eq(args.pair_id)]
    if len(selected) != 1:
        raise ValueError(f"pair_id {args.pair_id} is not uniquely present in cohort")
    pair = selected.iloc[0]

    root = Path(args.output) / f"pair_{int(pair.pair_id):03d}"
    root.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    all_fold_results: list[pd.DataFrame] = []
    pair_status = "complete"
    pair_error = ""

    try:
        occurrences = fetch_occurrences(pair, int(confirmation["cohort"]["records_per_pair"]))
        latitude_col, longitude_col = _coord_columns(occurrences)
        work = occurrences.copy().reset_index(drop=True)
        work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
        work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
        work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
        if len(work) < 4:
            raise ValueError("fewer than four valid occurrence coordinates")
        work["_outer_occurrence_id"] = [
            f"pair{int(pair.pair_id):03d}-occurrence{index + 1:05d}"
            for index in range(len(work))
        ]
        block = float(confirmation["outer_validation"]["block_degrees"])
        work["_outer_block"] = (
            np.floor(work[latitude_col] / block).astype(int).astype(str)
            + ":"
            + np.floor(work[longitude_col] / block).astype(int).astype(str)
        )
        blocks = work["_outer_block"].drop_duplicates().to_numpy()
        if len(blocks) < 2:
            raise ValueError("occurrences occupy fewer than two outer spatial blocks")

        rng = np.random.default_rng(
            int(confirmation["outer_validation"]["fold_seed_base"])
            + int(pair.pair_id)
        )
        n_holdout = min(
            len(blocks) - 1,
            max(
                1,
                int(
                    round(
                        len(blocks)
                        * float(confirmation["outer_validation"]["holdout_fraction"])
                    )
                ),
            ),
        )

        for repeat in range(
            1, int(confirmation["outer_validation"]["repeats"]) + 1
        ):
            fold_dir = root / f"fold_{repeat:03d}"
            fold_dir.mkdir(parents=True, exist_ok=True)
            held_blocks = set(
                rng.choice(blocks, size=n_holdout, replace=False).tolist()
            )
            heldout = work[work["_outer_block"].isin(held_blocks)].copy().reset_index(
                drop=True
            )
            training = (
                work[~work["_outer_block"].isin(held_blocks)]
                .drop(columns=["_outer_block", "_outer_occurrence_id"])
                .copy()
                .reset_index(drop=True)
            )

            candidates = build_candidate_pool(training, pair, repeat)
            deterministic, random_sets, deterministic_status = (
                build_deterministic_decisions(candidates, pair, repeat, confirmation)
            )

            # Freeze candidate and deterministic choices to disk before GRTS.
            candidate_path = fold_dir / "candidate_pool_pre_outcome.csv"
            candidates.to_csv(candidate_path, index=False)
            (fold_dir / "deterministic_decisions_pre_outcome.json").write_text(
                json.dumps(
                    {
                        "methods": deterministic,
                        "method_status": deterministic_status,
                        "random_same_pool_draws": random_sets,
                        "outcomes_available_to_selectors": False,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            if len(candidates) >= int(confirmation["practical_core"]["top_k"]):
                grts_pre, grts_audit = run_grts_pre_outcome(
                    candidate_path,
                    fold_dir / "grts_draws_pre_outcome.csv",
                    pair,
                    repeat,
                    confirmation,
                )
            else:
                grts_pre = pd.DataFrame()
                grts_audit = {
                    "status": "shared_candidate_failure",
                    "outcomes_available_to_selector": False,
                }

            fold_results, grts_scored, oracle_ids = score_frozen_decisions(
                candidates,
                heldout,
                deterministic,
                deterministic_status,
                random_sets,
                grts_pre,
                pair,
                repeat,
                confirmation,
            )
            all_fold_results.append(fold_results)
            manifests.append(
                write_fold_artifact(
                    fold_dir,
                    training,
                    heldout,
                    candidates,
                    deterministic,
                    deterministic_status,
                    random_sets,
                    grts_pre,
                    grts_audit,
                    fold_results,
                    grts_scored,
                    oracle_ids,
                    pair,
                    repeat,
                    held_blocks,
                    core_fp,
                    confirmation_fp,
                )
            )
    except Exception as exc:
        pair_status = "pair_setup_failure"
        pair_error = f"{type(exc).__name__}: {exc}"
        all_fold_results = [
            _failure_rows(
                pair,
                int(confirmation["outer_validation"]["repeats"]),
                pair_error,
            )
        ]

    fold_results = pd.concat(all_fold_results, ignore_index=True)
    fold_results.to_csv(root / "fold_results.csv", index=False)
    pair_manifest = {
        "pair_id": int(pair.pair_id),
        "scientific_name": str(pair.scientific_name),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "pair_status": pair_status,
        "pair_error": pair_error,
        "practical_core_fingerprint": core_fp,
        "confirmation_protocol_fingerprint": confirmation_fp,
        "expected_repeats": int(confirmation["outer_validation"]["repeats"]),
        "written_fold_manifests": len(manifests),
        "primary_stage_only": True,
        "fitted_sdm_deferred_to_secondary_stage": True,
        "fold_result_sha256": _sha256(root / "fold_results.csv"),
    }
    (root / "pair_manifest.json").write_text(
        json.dumps(pair_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return pair_manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-id", type=int, required=True)
    command.add_argument("--cohort", type=Path, default=DEFAULT_COHORT_PATH)
    command.add_argument(
        "--output", type=Path, default=Path("practical_core_confirmation_pairs")
    )
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
