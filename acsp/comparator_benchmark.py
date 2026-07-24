"""Frozen same-pool comparator evaluation for the ACSP methods paper.

This module evaluates already generated, training-only candidate pools. Selection
methods never receive held-out outcomes. Coverage identifiers are read only after
selection to calculate set-level recovery.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .decision_baselines import (
    DecisionBaselineConfig,
    random_same_pool_sets,
    recovered_fraction,
    select_dual_space_farthest,
    select_environmental_farthest,
    select_geographic_farthest,
    select_score_top_k,
)
from .validated_core import ValidatedCorePolicy, select_validated_core

UNIVERSAL_METHODS = (
    "frozen_acsp",
    "local_evidence_top_k",
    "geographic_maximin",
    "random_same_pool_mean",
    "heldout_greedy_oracle",
)
ENVIRONMENTAL_METHODS = ("environmental_maximin", "dual_space_maximin")
ALL_METHODS = UNIVERSAL_METHODS + ENVIRONMENTAL_METHODS


@dataclass(frozen=True)
class StandardBaselineProtocol:
    protocol_id: str = "acsp-standard-baselines-v1"
    top_k: int = 5
    recovery_radius_km: float = 10.0
    block_degrees: float = 0.1
    holdout_fraction: float = 0.2
    repeats: int = 5
    random_draws: int = 200
    random_state: int = 20260724
    bootstrap_draws: int = 10_000
    sign_flip_draws: int = 10_000
    dual_environment_weight: float = 0.5
    environmental_columns: tuple[str, ...] = (
        "elevation",
        "slope",
        "aspect",
        "roughness",
        "tpi",
    )
    circular_environmental_columns: tuple[str, ...] = ("aspect",)

    def validate(self) -> None:
        if not self.protocol_id.strip():
            raise ValueError("protocol_id must be non-empty")
        if self.top_k < 1 or self.repeats < 1 or self.random_draws < 1:
            raise ValueError("top_k, repeats, and random_draws must be positive")
        if self.recovery_radius_km <= 0 or self.block_degrees <= 0:
            raise ValueError("recovery radius and block size must be positive")
        if not 0 < self.holdout_fraction < 1:
            raise ValueError("holdout_fraction must lie in (0, 1)")
        if not 0 <= self.dual_environment_weight <= 1:
            raise ValueError("dual_environment_weight must lie in [0, 1]")
        if not self.environmental_columns:
            raise ValueError("environmental_columns must not be empty")
        unknown_circular = set(self.circular_environmental_columns) - set(self.environmental_columns)
        if unknown_circular:
            raise ValueError(f"circular columns are not environmental columns: {sorted(unknown_circular)}")

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "StandardBaselineProtocol":
        fields = {
            "protocol_id": str(values.get("protocol_id", cls.protocol_id)),
            "top_k": int(values.get("top_k", cls.top_k)),
            "recovery_radius_km": float(values.get("recovery_radius_km", cls.recovery_radius_km)),
            "block_degrees": float(values.get("block_degrees", cls.block_degrees)),
            "holdout_fraction": float(values.get("holdout_fraction", cls.holdout_fraction)),
            "repeats": int(values.get("repeats", cls.repeats)),
            "random_draws": int(values.get("random_draws", cls.random_draws)),
            "random_state": int(values.get("random_state", cls.random_state)),
            "bootstrap_draws": int(values.get("bootstrap_draws", cls.bootstrap_draws)),
            "sign_flip_draws": int(values.get("sign_flip_draws", cls.sign_flip_draws)),
            "dual_environment_weight": float(values.get("dual_environment_weight", cls.dual_environment_weight)),
            "environmental_columns": tuple(map(str, values.get("environmental_columns", cls.environmental_columns))),
            "circular_environmental_columns": tuple(
                map(str, values.get("circular_environmental_columns", cls.circular_environmental_columns))
            ),
        }
        result = cls(**fields)
        result.validate()
        return result

    @classmethod
    def from_json(cls, path: str | Path) -> "StandardBaselineProtocol":
        return cls.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))

    def manifest(self) -> dict[str, object]:
        payload = {
            "protocol_id": self.protocol_id,
            "top_k": self.top_k,
            "recovery_radius_km": self.recovery_radius_km,
            "block_degrees": self.block_degrees,
            "holdout_fraction": self.holdout_fraction,
            "repeats": self.repeats,
            "random_draws": self.random_draws,
            "random_state": self.random_state,
            "bootstrap_draws": self.bootstrap_draws,
            "sign_flip_draws": self.sign_flip_draws,
            "dual_environment_weight": self.dual_environment_weight,
            "environmental_columns": list(self.environmental_columns),
            "circular_environmental_columns": list(self.circular_environmental_columns),
            "methods": list(ALL_METHODS),
            "environmental_method_eligibility": (
                "pair included only when all expected folds contain finite values for every predeclared raw feature"
            ),
            "failure_rule": "missing universal-method folds contribute zero in pair-level intention-to-evaluate means",
        }
        payload["fingerprint"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return payload


def _split_ids(value: object) -> set[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return set()
    return {item for item in str(value).split(";") if item and item.lower() != "nan"}


def _candidate_id_column(frame: pd.DataFrame) -> str:
    for column in ("candidate_id", "site_id", "benchmark_candidate_id"):
        if column in frame.columns:
            return column
    return "candidate_id"


def _prepare_environment(
    candidates: pd.DataFrame,
    protocol: StandardBaselineProtocol,
) -> tuple[pd.DataFrame, tuple[str, ...], tuple[str, ...]]:
    work = candidates.copy().reset_index(drop=True)
    missing = tuple(column for column in protocol.environmental_columns if column not in work.columns)
    if missing:
        return work, (), missing
    invalid: list[str] = []
    expanded: list[str] = []
    for column in protocol.environmental_columns:
        numeric = pd.to_numeric(work[column], errors="coerce")
        if not np.isfinite(numeric).any():
            invalid.append(column)
            continue
        if column in protocol.circular_environmental_columns:
            radians = np.deg2rad(numeric)
            sin_col = f"__{column}_sin"
            cos_col = f"__{column}_cos"
            work[sin_col] = np.sin(radians)
            work[cos_col] = np.cos(radians)
            expanded.extend([sin_col, cos_col])
        else:
            expanded.append(column)
    return work, tuple(expanded), tuple(sorted(set(missing) | set(invalid)))


def _selection_row(
    method: str,
    selected: pd.DataFrame,
    *,
    id_col: str,
    status: str = "ok",
    reason: str = "",
) -> dict[str, object]:
    return {
        "decision_method": method,
        "status": status,
        "reason": reason,
        "selected_count": int(len(selected)),
        "heldout_recall": recovered_fraction(selected) if status == "ok" else 0.0,
        "selected_ids": ";".join(selected.get(id_col, pd.Series(dtype=str)).astype(str)),
    }


def select_heldout_greedy_oracle(
    candidates: pd.DataFrame,
    *,
    k: int,
    id_col: str,
) -> pd.DataFrame:
    """Non-operational headroom: greedily maximize additional held-out IDs."""
    if candidates is None or candidates.empty:
        return pd.DataFrame() if candidates is None else candidates.head(0).copy()
    work = candidates.copy().reset_index(drop=True)
    if id_col not in work.columns:
        work[id_col] = [f"candidate-{index + 1:06d}" for index in range(len(work))]
    work["__covered"] = work.get("covered_heldout_ids", pd.Series("", index=work.index)).map(_split_ids)
    selected: list[int] = []
    recovered: set[str] = set()
    while len(selected) < min(int(k), len(work)):
        remaining = [index for index in range(len(work)) if index not in selected]
        chosen = min(
            remaining,
            key=lambda index: (
                -len(work.at[index, "__covered"] - recovered),
                str(work.at[index, id_col]),
                index,
            ),
        )
        selected.append(chosen)
        recovered.update(work.at[chosen, "__covered"])
    return work.iloc[selected].drop(columns="__covered").reset_index(drop=True)


def evaluate_candidate_fold(
    candidates: pd.DataFrame,
    taxon_group: str,
    protocol: StandardBaselineProtocol,
    *,
    pair_id: object,
    repeat: int,
    random_state: int | None = None,
) -> pd.DataFrame:
    """Evaluate one fold without exposing held-out outcomes to selectors."""
    protocol.validate()
    if candidates is None:
        candidates = pd.DataFrame()
    frame = candidates.copy().reset_index(drop=True)
    id_col = _candidate_id_column(frame)
    if id_col not in frame.columns:
        frame[id_col] = [f"{pair_id}-r{int(repeat):03d}-c{index + 1:06d}" for index in range(len(frame))]
    base_cfg = DecisionBaselineConfig(
        k=protocol.top_k,
        id_col=id_col,
        score_col="component_local_habitat_score",
        environmental_cols=(),
        dual_environment_weight=protocol.dual_environment_weight,
        random_draws=protocol.random_draws,
        random_state=int(protocol.random_state if random_state is None else random_state),
    )
    rows: list[dict[str, object]] = []
    if frame.empty:
        for method in ALL_METHODS:
            rows.append({
                "decision_method": method,
                "status": "missing_fold_candidates",
                "reason": "candidate table is empty",
                "selected_count": 0,
                "heldout_recall": 0.0,
                "selected_ids": "",
            })
    else:
        policy = ValidatedCorePolicy.for_taxon_group(taxon_group)
        rows.append(_selection_row("frozen_acsp", select_validated_core(frame, policy), id_col=id_col))
        rows.append(_selection_row("local_evidence_top_k", select_score_top_k(frame, base_cfg), id_col=id_col))
        rows.append(_selection_row("geographic_maximin", select_geographic_farthest(frame, base_cfg), id_col=id_col))
        random_recalls = [recovered_fraction(draw) for draw in random_same_pool_sets(frame, base_cfg)]
        rows.append({
            "decision_method": "random_same_pool_mean",
            "status": "ok",
            "reason": "",
            "selected_count": min(protocol.top_k, len(frame)),
            "heldout_recall": float(np.mean(random_recalls)) if random_recalls else 0.0,
            "selected_ids": "",
        })
        oracle = select_heldout_greedy_oracle(frame, k=protocol.top_k, id_col=id_col)
        rows.append(_selection_row("heldout_greedy_oracle", oracle, id_col=id_col))

        prepared, expanded_columns, missing_environment = _prepare_environment(frame, protocol)
        if missing_environment:
            reason = "missing or non-finite predeclared features: " + ", ".join(missing_environment)
            for method in ENVIRONMENTAL_METHODS:
                rows.append({
                    "decision_method": method,
                    "status": "environmentally_ineligible",
                    "reason": reason,
                    "selected_count": 0,
                    "heldout_recall": 0.0,
                    "selected_ids": "",
                })
        else:
            env_cfg = DecisionBaselineConfig(
                k=protocol.top_k,
                id_col=id_col,
                score_col="component_local_habitat_score",
                environmental_cols=expanded_columns,
                dual_environment_weight=protocol.dual_environment_weight,
                random_draws=protocol.random_draws,
                random_state=base_cfg.random_state,
            )
            rows.append(_selection_row(
                "environmental_maximin",
                select_environmental_farthest(prepared, env_cfg),
                id_col=id_col,
            ))
            rows.append(_selection_row(
                "dual_space_maximin",
                select_dual_space_farthest(prepared, env_cfg),
                id_col=id_col,
            ))

    result = pd.DataFrame(rows)
    result.insert(0, "repeat", int(repeat))
    result.insert(0, "taxon_group", str(taxon_group))
    result.insert(0, "pair_id", pair_id)
    result["protocol_id"] = protocol.protocol_id
    result["protocol_fingerprint"] = protocol.manifest()["fingerprint"]
    result["candidate_pool"] = int(len(frame))
    return result.sort_values("decision_method", kind="mergesort").reset_index(drop=True)


def pair_level_intention_to_evaluate(
    fold_results: pd.DataFrame,
    declared_pairs: pd.DataFrame,
    protocol: StandardBaselineProtocol,
) -> pd.DataFrame:
    """Summarize folds within declared pairs before inference.

    Universal methods use the predeclared repeat denominator and missing folds are
    zero. Environmental methods are reported only for pairs with all expected
    folds environmentally eligible; no post-outcome eligibility decision is used.
    """
    required = {"pair_id", "taxon_group"}
    missing = required - set(declared_pairs.columns)
    if missing:
        raise ValueError(f"declared_pairs is missing: {', '.join(sorted(missing))}")
    rows: list[dict[str, object]] = []
    declared = declared_pairs.drop_duplicates("pair_id").copy()
    for pair in declared.itertuples(index=False):
        pair_id = getattr(pair, "pair_id")
        group = str(getattr(pair, "taxon_group"))
        subset = fold_results[fold_results["pair_id"].astype(str).eq(str(pair_id))]
        for method in ALL_METHODS:
            method_rows = subset[subset["decision_method"].eq(method)]
            ok = method_rows[method_rows["status"].eq("ok")]
            if method in ENVIRONMENTAL_METHODS:
                eligible = len(ok) == protocol.repeats
                value = float(pd.to_numeric(ok["heldout_recall"], errors="coerce").fillna(0).sum()) / protocol.repeats if eligible else np.nan
                status = "eligible" if eligible else "excluded_incomplete_environmental_schema"
            else:
                eligible = True
                value = float(pd.to_numeric(ok["heldout_recall"], errors="coerce").fillna(0).sum()) / protocol.repeats
                status = "intention_to_evaluate"
            rows.append({
                "pair_id": pair_id,
                "taxon_group": group,
                "decision_method": method,
                "evaluated_folds": int(len(ok)),
                "expected_folds": int(protocol.repeats),
                "pair_method_eligible": bool(eligible),
                "pair_status": status,
                "ite_recall": value,
            })
    return pd.DataFrame(rows)


def comparator_inference(
    pair_table: pd.DataFrame,
    protocol: StandardBaselineProtocol,
) -> pd.DataFrame:
    """Pair-level bootstrap intervals and sign-flip tests versus frozen references."""
    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(protocol.random_state)
    for group, group_table in pair_table.groupby("taxon_group", sort=True):
        wide = group_table.pivot(index="pair_id", columns="decision_method", values="ite_recall")
        for reference in ("random_same_pool_mean", "frozen_acsp"):
            if reference not in wide.columns:
                continue
            for method in ALL_METHODS:
                if method == reference or method not in wide.columns:
                    continue
                paired = wide[[method, reference]].dropna()
                if paired.empty:
                    continue
                differences = (paired[method] - paired[reference]).to_numpy(float)
                n = len(differences)
                bootstrap = rng.choice(differences, size=(protocol.bootstrap_draws, n), replace=True).mean(axis=1)
                signs = rng.choice(np.array([-1.0, 1.0]), size=(protocol.sign_flip_draws, n))
                null = (signs * differences).mean(axis=1)
                observed = abs(float(differences.mean()))
                rows.append({
                    "taxon_group": group,
                    "decision_method": method,
                    "reference_method": reference,
                    "eligible_pairs": n,
                    "mean_pair_difference": float(differences.mean()),
                    "bootstrap_ci_low": float(np.quantile(bootstrap, 0.025)),
                    "bootstrap_ci_high": float(np.quantile(bootstrap, 0.975)),
                    "probability_difference_positive": float(np.mean(bootstrap > 0)),
                    "sign_flip_p": float((1 + np.sum(np.abs(null) >= observed)) / (protocol.sign_flip_draws + 1)),
                })
    return pd.DataFrame(rows)
