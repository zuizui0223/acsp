#!/usr/bin/env python3
"""Freeze public-safe Cirsium candidate-patch method assignments before field outcomes.

Private input frames may contain coordinates and precomputed structural components.
The public output never contains coordinates or raw candidate IDs. Each selected
candidate is represented by an HMAC-SHA256 token made with a private salt supplied
at execution time. The same candidate frame and exact selection count are used for
all methods within a validation unit.

This is a candidate-count-matched freeze, not a claim of matched field time, route
length, searched area, occupancy, accessibility, or expected discovery yield.
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

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COHORT = REPO_ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _require_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing required columns: {missing}")


def _sort_top(frame: pd.DataFrame, *, column: str, count: int, ascending: bool) -> pd.DataFrame:
    _require_columns(frame, (column, "candidate_cell_id"))
    work = frame.copy()
    work[column] = pd.to_numeric(work[column], errors="coerce")
    if work[column].isna().any():
        raise ValueError(f"{column} must be complete")
    return (
        work.sort_values(
            [column, "candidate_cell_id"],
            ascending=[ascending, True],
            kind="mergesort",
        )
        .head(count)
        .copy()
        .reset_index(drop=True)
    )


def _token(
    salt: bytes,
    *,
    cohort_unit_id: str,
    method: str,
    candidate_cell_id: str,
    latitude: float,
    longitude: float,
) -> str:
    message = (
        f"{cohort_unit_id}|{method}|{candidate_cell_id}|"
        f"{float(latitude):.8f}|{float(longitude):.8f}"
    ).encode("utf-8")
    return hmac.new(salt, message, hashlib.sha256).hexdigest()


def _public_rows(
    selected: pd.DataFrame,
    *,
    salt: bytes,
    cohort_row: dict[str, str],
    method: str,
    selection_count: int,
    candidate_frame_rows: int,
    support_provenance_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank, record in enumerate(selected.to_dict(orient="records"), start=1):
        rows.append(
            {
                "cohort_unit_id": cohort_row["cohort_unit_id"],
                "aza3_slot_id": cohort_row["aza3_slot_id"],
                "species_binomial": cohort_row["species_binomial"],
                "occurrence_problem_class": cohort_row["occurrence_problem_class"],
                "structural_feature_family": cohort_row["structural_feature_family"],
                "anchor_replication_class": cohort_row["anchor_replication_class"],
                "frozen_method": method,
                "decision_rank": rank,
                "patch_token": _token(
                    salt,
                    cohort_unit_id=cohort_row["cohort_unit_id"],
                    method=method,
                    candidate_cell_id=str(record["candidate_cell_id"]),
                    latitude=float(record["latitude"]),
                    longitude=float(record["longitude"]),
                ),
                "candidate_frame_rows": candidate_frame_rows,
                "matched_selection_count": selection_count,
                "support_provenance_id": support_provenance_id if method == "STRUCTURAL_SUPPORT_TOP_K" else "",
                "candidate_count_match_only": "true",
                "field_outcomes_opened": "false",
                "exact_coordinates_written": "false",
            }
        )
    return rows


def freeze_unit(
    frame: pd.DataFrame,
    *,
    cohort_row: dict[str, str],
    selection_count: int,
    support_provenance_id: str,
    salt: bytes,
) -> list[dict[str, object]]:
    count = int(selection_count)
    if count < 1:
        raise ValueError("selection_count must be >=1")
    _require_columns(frame, ("candidate_cell_id", "latitude", "longitude"))
    forbidden = _forbidden_outcome_columns(frame.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in patch freeze: {forbidden}")
    if frame["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be unique within a unit")
    if count > len(frame):
        raise ValueError("selection_count cannot exceed candidate-frame rows")

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
            count=count,
            feature_family=family,
            support_provenance_id=support_provenance_id,
        )
        methods.append(("STRUCTURAL_SUPPORT_TOP_K", structural, support_provenance_id))
    elif arm == "SPATIAL_BASELINE_ONLY":
        if family != BASELINE_FAMILY:
            raise ValueError("spatial baseline arm must use GENERAL_SPATIAL_BASELINE_ONLY")
    else:
        raise ValueError(f"unknown method arm: {arm}")

    if regime == "LOCAL_CONTINUATION":
        annular = _sort_top(frame, column="nearest_anchor_km", count=count, ascending=True)
        methods.append(("ANNULAR_NEAREST_KNOWN", annular, ""))
    elif regime == "SENTINEL":
        broad = _sort_top(frame, column="broad_robust_support", count=count, ascending=False)
        methods.append(("VALIDATED_BROAD_ROBUST_SUPPORT", broad, ""))
    else:
        raise ValueError(f"freeze currently supports LOCAL_CONTINUATION or SENTINEL, got {regime}")

    spatial = select_geographic_farthest(
        frame,
        DecisionBaselineConfig(
            k=count,
            id_col="candidate_cell_id",
            latitude_col="latitude",
            longitude_col="longitude",
        ),
    )
    methods.append(("DETERMINISTIC_SPATIAL_BALANCE", spatial, ""))

    expected_method_count = 2 if arm == "SPATIAL_BASELINE_ONLY" else 3
    if len(methods) != expected_method_count:
        raise AssertionError("unexpected method count for frozen unit")
    if any(len(selected) != count for _, selected, _ in methods):
        raise AssertionError("all methods must return the exact matched candidate count")

    public: list[dict[str, object]] = []
    for method, selected, provenance in methods:
        public.extend(
            _public_rows(
                selected,
                salt=salt,
                cohort_row=cohort_row,
                method=method,
                selection_count=count,
                candidate_frame_rows=len(frame),
                support_provenance_id=provenance,
            )
        )
    return public


def freeze_manifest(
    *,
    cohort_csv: Path,
    unit_inputs_csv: Path,
    salt_file: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    cohort = {row["cohort_unit_id"]: row for row in _read_csv(cohort_csv)}
    inputs = _read_csv(unit_inputs_csv)
    salt = salt_file.read_bytes()
    if len(salt) < 16:
        raise ValueError("private salt must contain at least 16 bytes")

    output_rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in inputs:
        unit = item["cohort_unit_id"]
        if unit in seen:
            raise ValueError(f"duplicate unit input: {unit}")
        seen.add(unit)
        if unit not in cohort:
            raise ValueError(f"unit is not in frozen cohort: {unit}")
        frame = pd.read_csv(Path(item["input_csv"]))
        output_rows.extend(
            freeze_unit(
                frame,
                cohort_row=cohort[unit],
                selection_count=int(item["selection_count"]),
                support_provenance_id=item.get("support_provenance_id", ""),
                salt=salt,
            )
        )

    manifest = pd.DataFrame(output_rows)
    if manifest.empty:
        raise ValueError("no frozen patch rows were generated")
    if any(token in column.lower() for column in manifest.columns for token in ("latitude", "longitude")):
        raise AssertionError("public manifest must not contain coordinate columns")
    if manifest["patch_token"].duplicated().any():
        raise AssertionError("patch tokens must be unique across method assignments")

    method_counts = manifest.groupby(["cohort_unit_id", "frozen_method"]).size().to_dict()
    summary = {
        "schema_version": "cirsium-candidate-patch-public-freeze-v1",
        "status": "FROZEN_PRE_FIELD_OUTCOME",
        "unit_count": len(seen),
        "public_patch_assignment_rows": int(len(manifest)),
        "field_outcomes_opened": False,
        "exact_coordinates_written": False,
        "candidate_count_match_only": True,
        "matched_field_effort_claim": False,
        "route_efficiency_claim": False,
        "occupancy_claim": False,
        "method_counts_by_unit": {f"{unit}|{method}": int(value) for (unit, method), value in method_counts.items()},
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

    manifest, summary = freeze_manifest(
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
