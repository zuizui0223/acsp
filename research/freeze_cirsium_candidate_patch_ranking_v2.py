#!/usr/bin/env python3
"""Freeze full public-safe method rankings for prospective Cirsium patches.

Unlike v1, this does not make ACSP choose a field-budget k. Every method produces a
full deterministic ranking on the identical private candidate frame. The public
artifact contains only HMAC-SHA256 candidate tokens and ranks. A later field plan
may declare the same prefix length across methods before outcomes are opened.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from acsp.decision_baselines import DecisionBaselineConfig, select_geographic_farthest
from acsp.structural_selector import _forbidden_outcome_columns, select_structural_support
from acsp.structural_support import BASELINE_FAMILY, compose_structural_support

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COHORT = REPO_ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _require(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing required columns: {missing}")


def _sort_full(frame: pd.DataFrame, *, column: str, ascending: bool) -> pd.DataFrame:
    _require(frame, (column, "candidate_cell_id"))
    work = frame.copy()
    work[column] = pd.to_numeric(work[column], errors="coerce")
    if work[column].isna().any():
        raise ValueError(f"{column} must be complete")
    return work.sort_values(
        [column, "candidate_cell_id"],
        ascending=[ascending, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _token(salt: bytes, *, unit: str, method: str, record: dict[str, object]) -> str:
    message = (
        f"{unit}|{method}|{record['candidate_cell_id']}|"
        f"{float(record['latitude']):.8f}|{float(record['longitude']):.8f}"
    ).encode("utf-8")
    return hmac.new(salt, message, hashlib.sha256).hexdigest()


def rank_unit(
    frame: pd.DataFrame,
    *,
    cohort_row: dict[str, str],
    support_provenance_id: str,
    salt: bytes,
) -> list[dict[str, object]]:
    _require(frame, ("candidate_cell_id", "latitude", "longitude"))
    if frame.empty:
        raise ValueError("candidate frame cannot be empty")
    forbidden = _forbidden_outcome_columns(frame.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in ranking freeze: {forbidden}")
    if frame["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be unique")

    family = cohort_row["structural_feature_family"]
    arm = cohort_row["method_arm"]
    regime = cohort_row["occurrence_problem_class"]
    methods: list[tuple[str, pd.DataFrame, str]] = []

    if arm in {"STRUCTURAL_LOCAL", "STRUCTURAL_SENTINEL"}:
        if not support_provenance_id.strip():
            raise ValueError("structural units require support_provenance_id")
        support, _ = compose_structural_support(frame, feature_family=family)
        structural_frame = frame.copy()
        structural_frame["structural_support"] = support
        structural, _ = select_structural_support(
            structural_frame,
            count=len(frame),
            feature_family=family,
            support_provenance_id=support_provenance_id,
        )
        methods.append(("STRUCTURAL_SUPPORT", structural, support_provenance_id))
    elif arm == "SPATIAL_BASELINE_ONLY":
        if family != BASELINE_FAMILY:
            raise ValueError("baseline arm requires GENERAL_SPATIAL_BASELINE_ONLY")
    else:
        raise ValueError(f"unknown method arm: {arm}")

    if regime == "LOCAL_CONTINUATION":
        methods.append(("ANNULAR_NEAREST_KNOWN", _sort_full(frame, column="nearest_anchor_km", ascending=True), ""))
    elif regime == "SENTINEL":
        methods.append(("BROAD_SENTINEL_SUPPORT", _sort_full(frame, column="broad_robust_support", ascending=False), ""))
    else:
        raise ValueError(f"unsupported frozen regime for ranking: {regime}")

    spatial = select_geographic_farthest(
        frame,
        DecisionBaselineConfig(
            k=len(frame),
            id_col="candidate_cell_id",
            latitude_col="latitude",
            longitude_col="longitude",
        ),
    )
    methods.append(("DETERMINISTIC_SPATIAL_BALANCE", spatial, ""))

    expected = 2 if arm == "SPATIAL_BASELINE_ONLY" else 3
    if len(methods) != expected:
        raise AssertionError("unexpected method count")
    if any(len(ranked) != len(frame) for _, ranked, _ in methods):
        raise AssertionError("every method must rank the complete identical candidate frame")

    rows: list[dict[str, object]] = []
    for method, ranked, provenance in methods:
        for rank, record in enumerate(ranked.to_dict(orient="records"), start=1):
            rows.append(
                {
                    "cohort_unit_id": cohort_row["cohort_unit_id"],
                    "aza3_slot_id": cohort_row["aza3_slot_id"],
                    "species_binomial": cohort_row["species_binomial"],
                    "occurrence_problem_class": regime,
                    "structural_feature_family": family,
                    "anchor_replication_class": cohort_row["anchor_replication_class"],
                    "frozen_method": method,
                    "decision_rank": rank,
                    "candidate_token": _token(salt, unit=cohort_row["cohort_unit_id"], method=method, record=record),
                    "candidate_frame_rows": len(frame),
                    "support_provenance_id": provenance,
                    "field_prefix_selected": "false",
                    "field_outcomes_opened": "false",
                    "exact_coordinates_written": "false",
                }
            )
    return rows


def freeze_rankings(*, cohort_csv: Path, unit_inputs_csv: Path, salt_file: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    cohort = {row["cohort_unit_id"]: row for row in _read_csv(cohort_csv)}
    inputs = _read_csv(unit_inputs_csv)
    salt = salt_file.read_bytes()
    if len(salt) < 16:
        raise ValueError("private salt must contain at least 16 bytes")

    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    for item in inputs:
        unit = item["cohort_unit_id"]
        if unit in seen:
            raise ValueError(f"duplicate unit input: {unit}")
        seen.add(unit)
        if unit not in cohort:
            raise ValueError(f"unit is not in frozen cohort: {unit}")
        frame = pd.read_csv(Path(item["input_csv"]))
        rows.extend(
            rank_unit(
                frame,
                cohort_row=cohort[unit],
                support_provenance_id=item.get("support_provenance_id", ""),
                salt=salt,
            )
        )

    manifest = pd.DataFrame(rows)
    if manifest.empty:
        raise ValueError("no rankings generated")
    if any(token in column.lower() for column in manifest.columns for token in ("latitude", "longitude")):
        raise AssertionError("public ranking manifest cannot contain coordinates")
    if manifest["candidate_token"].duplicated().any():
        raise AssertionError("candidate tokens must be unique across method assignments")

    for (unit, method), group in manifest.groupby(["cohort_unit_id", "frozen_method"]):
        ranks = sorted(group["decision_rank"].astype(int).tolist())
        if ranks != list(range(1, len(ranks) + 1)):
            raise AssertionError(f"non-contiguous ranking for {unit} {method}")

    csv_bytes = manifest.to_csv(index=False).encode("utf-8")
    summary = {
        "schema_version": "cirsium-candidate-patch-full-ranking-v2",
        "status": "FULL_RANKING_FROZEN_PRE_FIELD_PREFIX",
        "unit_count": len(seen),
        "ranking_rows": int(len(manifest)),
        "ranking_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "field_prefix_selected": False,
        "field_outcomes_opened": False,
        "exact_coordinates_written": False,
        "raw_candidate_ids_written": False,
        "same_frame_full_ranking": True,
        "matched_field_effort_claim": False,
        "rule": "A later pre-field campaign plan may choose one equal prefix length per comparison unit; no outcome-dependent prefix extension is allowed."
    }
    return manifest, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--unit-inputs", type=Path, required=True)
    parser.add_argument("--private-salt-file", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    args = parser.parse_args()

    manifest, summary = freeze_rankings(
        cohort_csv=args.cohort,
        unit_inputs_csv=args.unit_inputs,
        salt_file=args.private_salt_file,
    )
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(args.out_csv, index=False)
    args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
