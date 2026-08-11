#!/usr/bin/env python3
"""Evaluate one frozen rescue-development pair against official GRTS 5.6.1."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Iterable

import numpy as np
import pandas as pd

EXPECTED_PROTOCOL = "950f7d9de90da2f2bd2561a18b7cc1eb74a60568ccc801875b96119db53bddf2"
EARTH_RADIUS_KM = 6_371.0088
KNOWN_PATTERN = "occurrence-supported|known-location|known anchor"


def _canonical_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if stored != calculated or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"GRTS development protocol mismatch: stored={stored}, calculated={calculated}"
        )
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _group_parts(group_id: str) -> tuple[str, int, int]:
    prefix, raw = str(group_id).split("_", 1)
    pair_id = int(raw)
    if prefix == "mixed":
        global_pair_id = pair_id
    elif prefix == "plants":
        global_pair_id = 24 + pair_id
    elif prefix == "sdm":
        global_pair_id = 48 + pair_id
    else:
        raise ValueError(f"unknown group_id: {group_id}")
    if pair_id < 1 or pair_id > 24:
        raise ValueError(f"source pair id outside 1..24: {group_id}")
    return prefix, pair_id, global_pair_id


def _find_pair_dir(source_root: Path, prefix: str, pair_id: int) -> Path:
    target = f"pair_{pair_id:03d}"
    matches = [path for path in source_root.rglob(target) if path.is_dir()]
    if len(matches) != 1:
        raise ValueError(
            f"expected one {target} under {source_root}, found {len(matches)}"
        )
    return matches[0]


def _source_paths(pair_dir: Path, prefix: str, repeat: int) -> tuple[Path, Path]:
    fold_dir = pair_dir / f"fold_{repeat:03d}"
    if prefix in {"mixed", "plants"}:
        return fold_dir / "candidates.csv", fold_dir / "held_out_occurrences.csv"
    return fold_dir / "candidate_pool_pre_outcome.csv", fold_dir / "held_out_occurrences.csv"


def _safe_preoutcome_candidates(path: Path) -> pd.DataFrame:
    allowed = {
        "candidate_id",
        "site_id",
        "candidate_type",
        "latitude",
        "longitude",
        "component_local_habitat_score",
    }
    try:
        frame = pd.read_csv(path, usecols=lambda name: name in allowed)
    except pd.errors.EmptyDataError:
        frame = pd.DataFrame()
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "candidate_id",
                "candidate_type",
                "latitude",
                "longitude",
                "component_local_habitat_score",
            ]
        )
    id_col = "candidate_id" if "candidate_id" in frame.columns else "site_id"
    if id_col not in frame.columns:
        raise ValueError(f"candidate frame lacks ID column: {path}")
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    frame = frame.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    if "candidate_type" in frame.columns:
        known = frame["candidate_type"].astype(str).str.contains(
            KNOWN_PATTERN, case=False, na=False
        )
        frame = frame.loc[~known].reset_index(drop=True)
    if frame[id_col].astype(str).duplicated().any():
        raise ValueError(f"duplicate candidate IDs: {path}")
    return frame


def _empty_draws(global_pair_id: int, repeat: int, draws: int, version: str, commit: str) -> pd.DataFrame:
    rows = []
    for draw_index in range(1, draws + 1):
        seed = 20260811 + global_pair_id * 100000 + repeat * 1000 + draw_index
        rows.append({
            "global_pair_id": global_pair_id,
            "repeat": repeat,
            "variant": "official_grts_proportional_local_mindis10km",
            "draw_index": draw_index,
            "seed": seed,
            "requested_k": 5,
            "base_count": 0,
            "base_ids": "",
            "requested_replacements": 3,
            "replacement_count": 0,
            "replacement_ids": "",
            "realized_min_distance_km": np.nan,
            "warning_message": "",
            "error_message": "empty_candidate_frame",
            "spsurvey_version": version,
            "spsurvey_tag_commit": commit,
            "outcomes_available_to_selector": False,
            "missing_local_evidence_rule": "nonfinite_to_zero_then_pmax_1e-6",
        })
    return pd.DataFrame(rows)


def _run_grts(
    input_path: Path,
    output_path: Path,
    global_pair_id: int,
    repeat: int,
    protocol: dict[str, object],
) -> pd.DataFrame:
    grts = protocol["official_grts"]
    frame = pd.read_csv(input_path)
    draws = int(grts["draws_per_fold"])
    if frame.empty:
        result = _empty_draws(
            global_pair_id,
            repeat,
            draws,
            str(grts["spsurvey_version"]),
            str(grts["spsurvey_tag_commit"]),
        )
        result.to_csv(output_path, index=False)
        return result
    command = [
        "Rscript",
        "benchmark_methods/grts_rescue_primary_batch.R",
        "--input", str(input_path),
        "--output", str(output_path),
        "--draws", str(draws),
        "--seed-base", str(grts["seed_base"]),
        "--global-pair-id", str(global_pair_id),
        "--repeat", str(repeat),
        "--k", str(grts["top_k"]),
        "--replacements", str(grts["replacement_sites"]),
        "--score-col", str(grts["score_col"]),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "official GRTS subprocess failed before a scientific draw artifact was frozen: "
            + completed.stderr[-4000:]
        )
    result = pd.read_csv(output_path)
    if len(result) != draws:
        raise RuntimeError(f"expected {draws} GRTS draws, found {len(result)}")
    if result["outcomes_available_to_selector"].astype(str).str.lower().isin({"true", "1"}).any():
        raise RuntimeError("GRTS pre-outcome artifact reports outcome access")
    return result


def _split_ids(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    return [item for item in str(value).split(";") if item and item.lower() != "nan"]


def _haversine_cross_km(selected: pd.DataFrame, heldout: pd.DataFrame) -> np.ndarray:
    if selected.empty or heldout.empty:
        return np.empty((len(selected), len(heldout)))
    lat_col = "_latitude" if "_latitude" in heldout.columns else "latitude"
    lon_col = "_longitude" if "_longitude" in heldout.columns else "longitude"
    hlat = pd.to_numeric(heldout[lat_col], errors="coerce")
    hlon = pd.to_numeric(heldout[lon_col], errors="coerce")
    valid = hlat.notna() & hlon.notna()
    hlat = hlat.loc[valid].to_numpy(float)
    hlon = hlon.loc[valid].to_numpy(float)
    slat = pd.to_numeric(selected["latitude"], errors="coerce").to_numpy(float)
    slon = pd.to_numeric(selected["longitude"], errors="coerce").to_numpy(float)
    alat = np.radians(slat)[:, None]
    alon = np.radians(slon)[:, None]
    blat = np.radians(hlat)[None, :]
    blon = np.radians(hlon)[None, :]
    dlat = alat - blat
    dlon = alon - blon
    a = np.sin(dlat / 2) ** 2 + np.cos(alat) * np.cos(blat) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _recovery(candidate_frame: pd.DataFrame, heldout: pd.DataFrame, selected_ids: Iterable[str], radius_km: float) -> float:
    if candidate_frame.empty or heldout.empty:
        return 0.0
    id_col = "candidate_id" if "candidate_id" in candidate_frame.columns else "site_id"
    selected_set = set(map(str, selected_ids))
    selected = candidate_frame[candidate_frame[id_col].astype(str).isin(selected_set)]
    if selected.empty:
        return 0.0
    distance = _haversine_cross_km(selected, heldout)
    if distance.size == 0 or distance.shape[1] == 0:
        return 0.0
    return float(np.mean(np.min(distance, axis=0) <= float(radius_km)))


def run(args: argparse.Namespace) -> dict[str, object]:
    protocol, fingerprint = _canonical_protocol(args.protocol)
    prefix, source_pair_id, global_pair_id = _group_parts(args.group_id)
    pair_dir = _find_pair_dir(args.source_root, prefix, source_pair_id)
    grts = protocol["official_grts"]
    radius = float(protocol["estimand"]["radius_km"])

    rescue_pre = pd.read_csv(
        args.rescue_fold_table,
        usecols=["group_id", "repeat", "selected_ids"],
    )
    rescue_pre = rescue_pre[rescue_pre["group_id"].astype(str).eq(args.group_id)].copy()
    if len(rescue_pre) != 5:
        raise ValueError(f"expected five frozen rescue decisions for {args.group_id}")
    selected_by_repeat = {
        int(row.repeat): _split_ids(row.selected_ids)
        for row in rescue_pre.itertuples(index=False)
    }

    root = args.output / args.group_id
    root.mkdir(parents=True, exist_ok=True)
    phase_a: dict[int, tuple[pd.DataFrame, Path, Path, Path]] = {}

    # Phase A: construct stripped candidate inputs and freeze every GRTS draw.
    # Neither held-out coordinate files nor outcome columns are read here.
    for repeat in range(1, 6):
        source_candidates, heldout_path = _source_paths(pair_dir, prefix, repeat)
        candidates = _safe_preoutcome_candidates(source_candidates)
        fold_dir = root / f"fold_{repeat:03d}"
        fold_dir.mkdir(parents=True, exist_ok=True)
        grts_input = fold_dir / "grts_candidate_pool_pre_outcome.csv"
        grts_draws = fold_dir / "grts_draws_pre_outcome.csv"
        candidates.to_csv(grts_input, index=False)
        draws = _run_grts(grts_input, grts_draws, global_pair_id, repeat, protocol)
        phase_a[repeat] = (candidates, grts_input, grts_draws, heldout_path)

    # Phase B: only after all operational GRTS selections are frozen do we load
    # held-out coordinates and the outcome-bearing rescue development table.
    rescue_full = pd.read_csv(args.rescue_fold_table)
    rescue_full = rescue_full[rescue_full["group_id"].astype(str).eq(args.group_id)].copy()
    fold_rows: list[dict[str, object]] = []
    scored_draw_rows: list[pd.DataFrame] = []
    for repeat in range(1, 6):
        candidates, grts_input, grts_draws, heldout_path = phase_a[repeat]
        try:
            heldout = pd.read_csv(heldout_path)
        except pd.errors.EmptyDataError:
            heldout = pd.DataFrame()
        frozen = rescue_full[pd.to_numeric(rescue_full["repeat"], errors="coerce").eq(repeat)]
        if len(frozen) != 1:
            raise ValueError(f"missing frozen rescue outcome row {args.group_id} repeat {repeat}")
        frozen_row = frozen.iloc[0]
        rescue_recovery = _recovery(
            candidates,
            heldout,
            selected_by_repeat[repeat],
            radius,
        )
        expected_rescue = float(frozen_row["local_anchor_rescue"])
        if not np.isclose(rescue_recovery, expected_rescue, atol=1e-10, rtol=0):
            raise ValueError(
                f"frozen rescue recovery mismatch {args.group_id} repeat {repeat}: "
                f"rescored={rescue_recovery}, artifact={expected_rescue}"
            )
        draws = pd.read_csv(grts_draws)
        draw_recovery = []
        for row in draws.itertuples(index=False):
            base_ids = _split_ids(row.base_ids)
            if int(row.base_count) <= 0 or not base_ids:
                recovery = 0.0
            else:
                recovery = _recovery(candidates, heldout, base_ids, radius)
            draw_recovery.append(recovery)
        draws["heldout_recovery_10km"] = draw_recovery
        draws["outcomes_attached_after_selection"] = True
        scored_draw_rows.append(draws.assign(group_id=args.group_id))
        warnings = draws["warning_message"].fillna("").astype(str).str.len().gt(0)
        errors = draws["error_message"].fillna("").astype(str).str.len().gt(0)
        realized = pd.to_numeric(draws["realized_min_distance_km"], errors="coerce")
        fold_rows.append({
            "group_id": args.group_id,
            "source": prefix,
            "source_pair_id": source_pair_id,
            "global_pair_id": global_pair_id,
            "repeat": repeat,
            "candidate_pool": int(len(candidates)),
            "rescue_recovery_10km": rescue_recovery,
            "local_evidence_top_k_recovery_10km": float(frozen_row["local_evidence_top_k"]),
            "grts_mean_recovery_10km": float(np.mean(draw_recovery)),
            "grts_valid_base_draws": int(np.sum(pd.to_numeric(draws["base_count"], errors="coerce").fillna(0).gt(0))),
            "grts_warning_draws": int(warnings.sum()),
            "grts_error_draws": int(errors.sum()),
            "grts_mean_realized_min_distance_km": float(realized.mean()) if realized.notna().any() else np.nan,
            "grts_input_sha256": _sha256(grts_input),
            "grts_pre_outcome_sha256": _sha256(grts_draws),
        })

    fold_table = pd.DataFrame(fold_rows)
    scored_draws = pd.concat(scored_draw_rows, ignore_index=True)
    fold_table.to_csv(root / "fold_comparison.csv", index=False)
    scored_draws.to_csv(root / "grts_draws_scored.csv", index=False)
    summary = {
        "group_id": args.group_id,
        "source": prefix,
        "source_pair_id": source_pair_id,
        "global_pair_id": global_pair_id,
        "protocol_fingerprint": fingerprint,
        "spsurvey_version": str(grts["spsurvey_version"]),
        "spsurvey_tag_commit": str(grts["spsurvey_tag_commit"]),
        "expected_repeats": 5,
        "written_repeats": int(len(fold_table)),
        "grts_draws_per_fold": int(grts["draws_per_fold"]),
        "rescue_mean_recovery_10km": float(fold_table["rescue_recovery_10km"].mean()),
        "local_mean_recovery_10km": float(fold_table["local_evidence_top_k_recovery_10km"].mean()),
        "grts_mean_recovery_10km": float(fold_table["grts_mean_recovery_10km"].mean()),
        "rescue_minus_grts": float((fold_table["rescue_recovery_10km"] - fold_table["grts_mean_recovery_10km"]).mean()),
        "grts_warning_draws": int(fold_table["grts_warning_draws"].sum()),
        "grts_error_draws": int(fold_table["grts_error_draws"].sum()),
        "outcomes_available_to_grts_selector": False,
        "all_grts_draws_frozen_before_heldout_loading": True,
        "no_retuning_after_grts_outcome": True,
    }
    (root / "pair_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--group-id", required=True)
    command.add_argument("--source-root", type=Path, required=True)
    command.add_argument("--rescue-fold-table", type=Path, required=True)
    command.add_argument(
        "--protocol",
        type=Path,
        default=Path("validation/acsp_practical_rescue_grts_development_protocol.json"),
    )
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2))
