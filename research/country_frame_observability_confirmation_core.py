#!/usr/bin/env python3
"""Pure aggregation core for the prospective country-frame observability confirmation.

This module does not fetch GBIF data and cannot open the held-out endpoint.  It
only validates a completed 96-frame outcome table and applies the preregistered
rank-AUC and fixed-seed taxon bootstrap decision rule from issue #163.
"""
from __future__ import annotations

import math
from typing import Mapping

import numpy as np
import pandas as pd

from develop_country_frame_observability_score import rank_auc

EXPECTED_FRAMES = 96
BOOTSTRAP_REPETITIONS = 10_000
BOOTSTRAP_SEED = 2026082702

_REQUIRED_COLUMNS = {
    "observability_frame_id",
    "taxon_group",
    "geographic_stratum",
    "region_cell_index",
    "record_count_stratum",
    "speciesKey",
    "scientific_name",
    "selected_country_code",
    "historical_selected_country_count",
    "country_frame_observability_score",
    "recent_heldout_occurrence_rows",
    "temporally_observable",
}


def _as_bool(series: pd.Series) -> np.ndarray:
    if pd.api.types.is_bool_dtype(series):
        return series.to_numpy(dtype=bool)
    normalized = series.astype(str).str.strip().str.lower()
    if not normalized.isin({"true", "false", "1", "0"}).all():
        raise ValueError("temporally_observable must be boolean-like")
    return normalized.isin({"true", "1"}).to_numpy(dtype=bool)


def validate_completed_rows(frame: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"observability confirmation rows missing columns: {sorted(missing)}")
    work = frame.copy()
    if len(work) != EXPECTED_FRAMES:
        raise ValueError(f"expected exactly {EXPECTED_FRAMES} completed frames, got {len(work)}")
    if work["observability_frame_id"].nunique() != EXPECTED_FRAMES:
        raise ValueError("observability_frame_id is not unique")
    if work["speciesKey"].nunique() != EXPECTED_FRAMES:
        raise ValueError("speciesKey is not unique across the prospective cohort")
    if work["scientific_name"].astype(str).nunique() != EXPECTED_FRAMES:
        raise ValueError("scientific_name is not unique across the prospective cohort")
    if work["taxon_group"].value_counts().to_dict() != {"plant": 48, "animal": 48}:
        raise ValueError("prospective cohort is not balanced 48 plant / 48 animal")
    for group in ("plant", "animal"):
        counts = (
            work.loc[work["taxon_group"].eq(group), "record_count_stratum"]
            .astype(int)
            .value_counts()
            .sort_index()
            .to_dict()
        )
        if counts != {0: 12, 1: 12, 2: 12, 3: 12}:
            raise ValueError(f"record-count stratum balance drift for {group}: {counts}")
    per_cell = work.groupby(["region_cell_index", "taxon_group"]).size()
    if len(per_cell) != 24 or not (per_cell == 4).all():
        raise ValueError("prospective region x group cells are not exactly four frames each")

    historical = pd.to_numeric(work["historical_selected_country_count"], errors="raise").astype(int)
    if (historical < 5).any():
        raise ValueError("completed frame has historical selected-country count < 5")
    stored_score = pd.to_numeric(work["country_frame_observability_score"], errors="raise").to_numpy(float)
    expected_score = np.log1p(historical.to_numpy(float))
    if not np.allclose(stored_score, expected_score, rtol=0.0, atol=1e-12):
        raise ValueError("stored observability score is not exact log1p(historical selected-country count)")

    recent = pd.to_numeric(work["recent_heldout_occurrence_rows"], errors="raise").astype(int)
    if (recent < 0).any():
        raise ValueError("recent held-out occurrence row count cannot be negative")
    observable = _as_bool(work["temporally_observable"])
    if not np.array_equal(observable, recent.to_numpy() > 0):
        raise ValueError("temporally_observable does not match recent_heldout_occurrence_rows > 0")
    work["temporally_observable"] = observable
    return work


def bootstrap_auc(scores: np.ndarray, labels: np.ndarray) -> dict[str, float | int]:
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if len(scores) != len(labels):
        raise ValueError("score/label length mismatch")
    if np.unique(labels).size != 2:
        raise ValueError("bootstrap AUC requires both temporal classes in the observed cohort")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    values: list[float] = []
    n = len(labels)
    for _ in range(BOOTSTRAP_REPETITIONS):
        idx = rng.integers(0, n, n)
        sampled_labels = labels[idx]
        if np.unique(sampled_labels).size != 2:
            continue
        values.append(rank_auc(scores[idx], sampled_labels))
    if not values:
        raise ValueError("no valid bootstrap AUC replicates")
    arr = np.asarray(values, dtype=float)
    q025, q50, q975 = np.quantile(arr, [0.025, 0.5, 0.975])
    return {
        "requested_replicates": BOOTSTRAP_REPETITIONS,
        "valid_replicates": int(arr.size),
        "seed": BOOTSTRAP_SEED,
        "mean_auc": float(arr.mean()),
        "median_auc": float(q50),
        "ci95_lower": float(q025),
        "ci95_upper": float(q975),
    }


def _auc_or_none(scores: np.ndarray, labels: np.ndarray) -> float | None:
    return float(rank_auc(scores, labels)) if np.unique(labels).size == 2 else None


def summarize_confirmation(
    frame: pd.DataFrame,
    *,
    fingerprints_match: bool,
    zero_overlap_verified: bool,
    preheldout_freeze_verified: bool,
) -> dict[str, object]:
    work = validate_completed_rows(frame)
    labels = work["temporally_observable"].astype(int).to_numpy()
    scores = pd.to_numeric(work["country_frame_observability_score"], errors="raise").to_numpy(float)
    generic = pd.to_numeric(work["record_count_stratum"], errors="raise").to_numpy(float)
    both_classes = np.unique(labels).size == 2
    auc = float(rank_auc(scores, labels)) if both_classes else float("nan")
    bootstrap = bootstrap_auc(scores, labels) if both_classes else None

    gates: Mapping[str, bool] = {
        "exactly_96_unique_frozen_frames": len(work) == 96 and work["speciesKey"].nunique() == 96,
        "protocol_and_execution_fingerprints_match": bool(fingerprints_match),
        "zero_overlap_with_consumed_identities": bool(zero_overlap_verified),
        "declared_and_scored_before_heldout_without_replacement": bool(preheldout_freeze_verified),
        "both_temporal_outcome_classes_present": bool(both_classes),
        "continuous_score_auc_gt_0_5": bool(both_classes and auc > 0.5),
        "bootstrap_ci95_lower_gt_0_5": bool(bootstrap is not None and float(bootstrap["ci95_lower"]) > 0.5),
    }

    by_group: dict[str, object] = {}
    for group in ("plant", "animal"):
        mask = work["taxon_group"].eq(group).to_numpy()
        group_labels = labels[mask]
        group_scores = scores[mask]
        by_group[group] = {
            "frames": int(mask.sum()),
            "temporally_observable": int(group_labels.sum()),
            "temporally_observable_fraction": float(group_labels.mean()),
            "observability_score_auc": _auc_or_none(group_scores, group_labels),
        }

    by_geo: dict[str, object] = {}
    for stratum in sorted(work["geographic_stratum"].astype(str).unique()):
        mask = work["geographic_stratum"].astype(str).eq(stratum).to_numpy()
        sub_labels = labels[mask]
        by_geo[stratum] = {
            "frames": int(mask.sum()),
            "temporally_observable": int(sub_labels.sum()),
            "temporally_observable_fraction": float(sub_labels.mean()),
            "observability_score_auc": _auc_or_none(scores[mask], sub_labels),
        }

    comparator_auc = _auc_or_none(generic, labels)
    return {
        "status": "prospective_country_frame_observability_confirmation",
        "frames": int(len(work)),
        "temporally_observable": int(labels.sum()),
        "zero_recent_country_records": int(len(labels) - labels.sum()),
        "primary": {
            "observability_score_auc": None if not both_classes else auc,
            "bootstrap": bootstrap,
            "gates": dict(gates),
            "passed_gate_count": int(sum(gates.values())),
            "confirmation_passed": bool(all(gates.values())),
        },
        "secondary_only": {
            "generic_record_count_stratum_auc": comparator_auc,
            "observability_score_minus_generic_auc": (
                None if comparator_auc is None or not both_classes else float(auc - comparator_auc)
            ),
            "by_taxon_group": by_group,
            "by_geographic_stratum": by_geo,
            "may_change_primary_decision": False,
        },
        "guards": {
            "score_cutoff_selected": False,
            "candidate_generation_read": False,
            "robust_support_read": False,
            "random_baseline_read": False,
            "recall_or_lift_read": False,
            "candidate_patch_confirmation_decision_changed": False,
        },
    }
