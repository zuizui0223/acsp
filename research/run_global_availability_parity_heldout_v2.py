#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from acsp.validated_robust import VALIDATED_ROBUST_PRIMARY_RADIUS_KM
from run_country_framed_integration_development_v1_1 import (
    fetch_recent_country_occurrences,
    recovery_fraction,
    same_size_random_recovery,
    taxon_bootstrap_mean_ci,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_global_availability_parity_confirmation_v2.json"
RECEIPT_PATH = ROOT / "validation" / "acsp_global_availability_parity_stage4_receipt_v2.json"
STAGE3_RUN_ID = 34134427957
STAGE3_AGGREGATE_ARTIFACT_ID = 10033756992
STAGE3_AGGREGATE_ARTIFACT_DIGEST = "sha256:bb5ddb099f70347569008cd30ad35b62680330b5719418e3c75eed8d5646eaea"
PREHELDOUT_STATES_SHA256 = "23554f0f189712a98d74ac1901c9c62037df3df3fc2c9fddf0d8299af0c1544d"
EXPECTED_STAGE3_COUNTS = {
    "ROBUST_READY_PREHELDOUT": 43,
    "ROBUST_EMPTY": 1,
    "SENTINEL_OR_ABSTAIN": 4,
}
RU_PAIR_ID = 48
RU_SURFACE_SHA256 = "77729dfa45b9e123f035ca15a421f834a6b155140ae410b8806e9f4eca19c982"
ALLOWED_STATES = set(EXPECTED_STAGE3_COUNTS)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if payload["protocol_id"] != "acsp_global_availability_parity_confirmation_v2":
        raise ValueError("global availability parity protocol drift")
    if payload["freeze_sequence"][-1] != "stage5: only after stages1-4 are complete, open 2021-2025 heldout records and evaluate conditional robust lift":
        raise ValueError("stage5 opening order drift")
    if payload["decision"]["same_cohort_rescue_allowed"] is not False:
        raise ValueError("same-cohort rescue must remain forbidden")
    return payload


def _receipt() -> dict[str, object]:
    payload = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    if payload["status"] != "ALL_48_PREHELDOUT_ARTIFACTS_PINNED_BEFORE_HELDOUT_V2":
        raise ValueError("stage4 receipt status drift")
    if int(payload["stage3"]["workflow_run_id"]) != STAGE3_RUN_ID:
        raise ValueError("stage3 workflow run drift")
    if int(payload["stage3"]["aggregate_artifact_id"]) != STAGE3_AGGREGATE_ARTIFACT_ID:
        raise ValueError("stage3 aggregate artifact drift")
    if payload["stage3"]["aggregate_artifact_digest"] != STAGE3_AGGREGATE_ARTIFACT_DIGEST:
        raise ValueError("stage3 aggregate digest drift")
    if payload["stage3"]["preheldout_states_sha256"] != PREHELDOUT_STATES_SHA256:
        raise ValueError("stage3 states digest drift")
    if payload["information_boundary"]["heldout_2021_2025_opened"] is not False:
        raise ValueError("stage4 receipt says heldout was already opened")
    return payload


def verify_aggregate(aggregate_dir: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    _protocol()
    _receipt()
    aggregate_dir = Path(aggregate_dir)
    states_path = aggregate_dir / "preheldout_states.csv"
    summary_path = aggregate_dir / "candidate_freeze_summary.json"
    if _sha256(states_path) != PREHELDOUT_STATES_SHA256:
        raise ValueError("preheldout state table SHA-256 mismatch")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary["status"] != "ALL_48_PREHELDOUT_AVAILABILITY_STATES_FROZEN":
        raise ValueError("stage3 aggregate status drift")
    if summary["state_counts"] != EXPECTED_STAGE3_COUNTS:
        raise ValueError(f"stage3 state counts drift: {summary['state_counts']}")
    if int(summary["robust_constructible_taxa"]) != 44:
        raise ValueError("stage3 constructible count drift")
    if summary["availability_gate_passed_preheldout"] is not True:
        raise ValueError("stage3 availability gate was not passed")
    for key in ("heldout_2021_2025_opened", "random_baseline_run", "recall_or_lift_read", "validated_japan_core_changed"):
        if summary[key] is not False:
            raise ValueError(f"preheldout information boundary violated: {key}")
    states = pd.read_csv(states_path)
    ids = pd.to_numeric(states["availability_pair_id"], errors="raise").astype(int)
    if len(states) != 48 or sorted(ids.tolist()) != list(range(1, 49)):
        raise ValueError("preheldout states must contain exact IDs 1..48")
    counts = states["preheldout_availability_state"].value_counts().to_dict()
    if counts != EXPECTED_STAGE3_COUNTS:
        raise ValueError(f"state-table counts drift: {counts}")
    return states, summary


def verify_pair(pair_dir: Path, state_row: pd.Series, *, ru_surface: Path | None = None) -> dict[str, object]:
    pair_dir = Path(pair_dir)
    pair_id = int(state_row["availability_pair_id"])
    result_path = pair_dir / "pair_result.json"
    patch_path = pair_dir / "candidate_patches.csv"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    if int(data["availability_pair_id"]) != pair_id:
        raise ValueError("pair artifact ID drift")
    for col in ("speciesKey", "scientific_name", "taxon_group", "selected_country_code", "preheldout_availability_state"):
        expected = str(state_row[col])
        actual = str(data[col])
        if actual != expected:
            raise ValueError(f"pair {pair_id} drift in {col}: {actual!r} != {expected!r}")
    state = str(state_row["preheldout_availability_state"])
    if state not in ALLOWED_STATES:
        raise ValueError(f"invalid frozen state for pair {pair_id}: {state}")
    if _sha256(patch_path) != str(state_row["candidate_patches_sha256"]):
        raise ValueError(f"pair {pair_id} candidate patch digest mismatch")
    if state in {"ROBUST_READY_PREHELDOUT", "ROBUST_EMPTY"}:
        if pair_id == RU_PAIR_ID:
            if str(state_row["candidate_surface_sha256"]) != RU_SURFACE_SHA256:
                raise ValueError("RU surface identity drift in state table")
            if ru_surface is not None and _sha256(ru_surface) != RU_SURFACE_SHA256:
                raise ValueError("RU surface file digest mismatch")
        else:
            surface_path = pair_dir / "candidate_surface.parquet"
            if _sha256(surface_path) != str(state_row["candidate_surface_sha256"]):
                raise ValueError(f"pair {pair_id} candidate surface digest mismatch")
    for key in ("heldout_2021_2025_opened", "random_baseline_run", "recall_or_lift_read", "validated_japan_core_changed"):
        if data[key] is not False:
            raise ValueError(f"pair {pair_id} preheldout boundary violated: {key}")
    return data


def verify_all(aggregate_dir: Path, pairs_root: Path, *, ru_surface: Path | None = None) -> dict[str, object]:
    states, summary = verify_aggregate(aggregate_dir)
    pairs_root = Path(pairs_root)
    checked = 0
    for row in states.itertuples(index=False):
        pair_id = int(row.availability_pair_id)
        pair_dir = pairs_root / f"global-parity-candidate-pair-{pair_id}"
        verify_pair(pair_dir, pd.Series(row._asdict()), ru_surface=ru_surface if pair_id == RU_PAIR_ID else None)
        checked += 1
    if checked != 48:
        raise ValueError("did not verify all 48 pair artifacts")
    return {
        "status": "ALL_48_STAGE4_ARTIFACTS_VERIFIED_BEFORE_HELDOUT",
        "pair_count": checked,
        "state_counts": summary["state_counts"],
        "robust_constructible_taxa": summary["robust_constructible_taxa"],
        "heldout_2021_2025_opened": False,
    }


def _load_surface(pair_dir: Path, pair_id: int, ru_surface: Path | None) -> pd.DataFrame:
    if pair_id == RU_PAIR_ID:
        if ru_surface is None:
            raise ValueError("RU evaluation requires the exact pinned RU surface")
        return pd.read_parquet(ru_surface)
    return pd.read_parquet(Path(pair_dir) / "candidate_surface.parquet")


def evaluate_pair(aggregate_dir: Path, pair_dir: Path, pair_id: int, output: Path, *, ru_surface: Path | None = None) -> dict[str, object]:
    protocol = _protocol()
    states, _ = verify_aggregate(aggregate_dir)
    hit = states.loc[pd.to_numeric(states["availability_pair_id"], errors="raise").astype(int).eq(int(pair_id))]
    if len(hit) != 1:
        raise ValueError(f"expected one frozen state for pair {pair_id}")
    state_row = hit.iloc[0]
    verify_pair(pair_dir, state_row, ru_surface=ru_surface)

    pair_id = int(pair_id)
    state = str(state_row["preheldout_availability_state"])
    key = int(state_row["speciesKey"])
    code = str(state_row["selected_country_code"]).upper()
    group = str(state_row["taxon_group"])
    patch_n = int(state_row["candidate_patch_count"])
    radius = float(protocol["robust_method"]["primary_radius_km"])
    if radius != float(VALIDATED_ROBUST_PRIMARY_RADIUS_KM):
        raise ValueError("primary recovery radius drift")

    temporal_status = "not_applicable_nonconstructible"
    recent_n = 0
    robust = random_mean = random_q025 = random_q975 = lift = float("nan")
    if state in {"ROBUST_READY_PREHELDOUT", "ROBUST_EMPTY"}:
        # This is the first allowed heldout opening for the frozen v2 cohort.
        recent = fetch_recent_country_occurrences(key, code, years=(2021, 2025), cap=300)
        recent_n = int(len(recent))
        temporal_status = "evaluated" if recent_n > 0 else "zero_recent_country_records"
        if recent_n > 0:
            if state == "ROBUST_EMPTY":
                robust = random_mean = random_q025 = random_q975 = lift = 0.0
            else:
                patches = pd.read_csv(Path(pair_dir) / "candidate_patches.csv")
                surface = _load_surface(Path(pair_dir), pair_id, ru_surface)
                robust = float(recovery_fraction(recent, patches, radius))
                seedbase = int(protocol["robust_method"]["random_seed"])
                token = f"{seedbase}|{key}|{code}".encode()
                seed = int(hashlib.sha256(token).hexdigest()[:16], 16) % (2**32 - 1)
                random_mean, random_q025, random_q975 = same_size_random_recovery(
                    recent,
                    surface,
                    selected_count=patch_n,
                    radius_km=radius,
                    repetitions=int(protocol["robust_method"]["random_repetitions"]),
                    seed=seed,
                )
                robust = float(robust)
                random_mean = float(random_mean)
                random_q025 = float(random_q025)
                random_q975 = float(random_q975)
                lift = float(robust - random_mean)

    result = {
        "availability_pair_id": pair_id,
        "taxon_group": group,
        "speciesKey": key,
        "scientific_name": str(state_row["scientific_name"]),
        "selected_country_code": code,
        "preheldout_availability_state": state,
        "candidate_patch_count": patch_n,
        "temporal_status": temporal_status,
        "recent_heldout_occurrence_rows": recent_n,
        "primary_radius_km": radius,
        "robust_recall": None if not np.isfinite(robust) else robust,
        "random_recall_mean": None if not np.isfinite(random_mean) else random_mean,
        "random_recall_q025": None if not np.isfinite(random_q025) else random_q025,
        "random_recall_q975": None if not np.isfinite(random_q975) else random_q975,
        "robust_minus_random_recall": None if not np.isfinite(lift) else lift,
        "heldout_2021_2025_opened": state in {"ROBUST_READY_PREHELDOUT", "ROBUST_EMPTY"},
        "same_cohort_retuning": False,
        "taxon_or_country_replacement": False,
        "validated_japan_core_changed": False,
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "heldout_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pd.DataFrame([result]).to_csv(output / "heldout_result.csv", index=False)
    return result


def _finite_mean(values: pd.Series) -> float:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(float)
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else float("nan")


def aggregate_results(aggregate_dir: Path, results_root: Path, output: Path) -> dict[str, object]:
    protocol = _protocol()
    states, pre = verify_aggregate(aggregate_dir)
    rows: list[dict[str, object]] = []
    seen: set[int] = set()
    for path in sorted(Path(results_root).glob("global-parity-heldout-pair-*/heldout_result.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        pair_id = int(data["availability_pair_id"])
        if pair_id in seen:
            raise ValueError(f"duplicate heldout result for pair {pair_id}")
        seen.add(pair_id)
        rows.append(data)
    if seen != set(range(1, 49)):
        raise ValueError(f"heldout aggregate requires IDs 1..48; missing={sorted(set(range(1,49)) - seen)}")
    frame = pd.DataFrame(rows).sort_values("availability_pair_id", kind="mergesort").reset_index(drop=True)
    state_map = states.set_index("availability_pair_id")["preheldout_availability_state"].astype(str).to_dict()
    for row in frame.itertuples(index=False):
        if str(row.preheldout_availability_state) != state_map[int(row.availability_pair_id)]:
            raise ValueError(f"heldout state drift for pair {row.availability_pair_id}")
        if row.same_cohort_retuning or row.taxon_or_country_replacement or row.validated_japan_core_changed:
            raise ValueError("heldout result violates frozen decision boundary")

    constructible = frame["preheldout_availability_state"].isin(["ROBUST_READY_PREHELDOUT", "ROBUST_EMPTY"])
    evaluable = constructible & frame["temporal_status"].eq("evaluated")
    constructible_n = int(constructible.sum())
    evaluable_n = int(evaluable.sum())
    evaluability_fraction = evaluable_n / constructible_n if constructible_n else float("nan")
    lifts = pd.to_numeric(frame.loc[evaluable, "robust_minus_random_recall"], errors="coerce").to_numpy(float)
    lifts = lifts[np.isfinite(lifts)]
    if len(lifts):
        mean_lift, ci_low, ci_high = taxon_bootstrap_mean_ci(
            lifts,
            repetitions=int(protocol["robust_method"]["bootstrap_repetitions"]),
            seed=int(protocol["robust_method"]["bootstrap_seed"]),
        )
        mean_lift, ci_low, ci_high = float(mean_lift), float(ci_low), float(ci_high)
    else:
        mean_lift = ci_low = ci_high = float("nan")
    plant_mean = _finite_mean(frame.loc[evaluable & frame["taxon_group"].eq("plant"), "robust_minus_random_recall"])
    animal_mean = _finite_mean(frame.loc[evaluable & frame["taxon_group"].eq("animal"), "robust_minus_random_recall"])

    dims = protocol["primary_dimensions"]
    availability_fraction = float(pre["robust_constructible_fraction"])
    gates = {
        "availability_constructible_fraction": bool(availability_fraction >= float(dims["availability"]["robust_constructible_fraction_min"])),
        "conditional_retrospective_evaluability": bool(np.isfinite(evaluability_fraction) and evaluability_fraction >= float(dims["retrospective_evaluability"]["conditional_fraction_min"])),
        "mean_robust_minus_random_lift_positive": bool(np.isfinite(mean_lift) and mean_lift > float(dims["conditional_predictive_validity"]["mean_robust_minus_random_lift_gt"])),
        "bootstrap_95_ci_lower_positive": bool(np.isfinite(ci_low) and ci_low > float(dims["conditional_predictive_validity"]["taxon_bootstrap_95_ci_lower_gt"])),
        "plant_mean_nonnegative": bool(np.isfinite(plant_mean) and plant_mean >= float(dims["conditional_predictive_validity"]["plant_mean_lift_gte"])),
        "animal_mean_nonnegative": bool(np.isfinite(animal_mean) and animal_mean >= float(dims["conditional_predictive_validity"]["animal_mean_lift_gte"])),
    }
    overall = bool(all(gates.values()))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "heldout_taxon_results.csv", index=False)
    summary = {
        "schema_version": "global-availability-parity-final-result-v2",
        "status": "GLOBAL_AVAILABILITY_PARITY_CONFIRMATION_V2_COMPLETE",
        "taxon_count": 48,
        "preheldout_state_counts": pre["state_counts"],
        "robust_constructible_taxa": constructible_n,
        "robust_constructible_fraction": availability_fraction,
        "temporally_evaluable_constructible_taxa": evaluable_n,
        "conditional_retrospective_evaluability_fraction": evaluability_fraction,
        "conditional_mean_robust_minus_random_recall": None if not np.isfinite(mean_lift) else mean_lift,
        "taxon_bootstrap_95pct_ci": [None if not np.isfinite(ci_low) else ci_low, None if not np.isfinite(ci_high) else ci_high],
        "plant_mean_robust_minus_random_recall": None if not np.isfinite(plant_mean) else plant_mean,
        "animal_mean_robust_minus_random_recall": None if not np.isfinite(animal_mean) else animal_mean,
        "gate_checks": gates,
        "overall_pass": overall,
        "global_automatic_adapter_promoted": overall,
        "explicit_user_target_country_substitution_behavior_changed": False,
        "same_cohort_retuning": False,
        "validated_japan_core_changed": False,
    }
    (output / "final_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("verify-all")
    v.add_argument("--aggregate-dir", type=Path, required=True)
    v.add_argument("--pairs-root", type=Path, required=True)
    v.add_argument("--ru-surface", type=Path)

    e = sub.add_parser("evaluate-pair")
    e.add_argument("--aggregate-dir", type=Path, required=True)
    e.add_argument("--pair-dir", type=Path, required=True)
    e.add_argument("--pair-id", type=int, required=True)
    e.add_argument("--output", type=Path, required=True)
    e.add_argument("--ru-surface", type=Path)

    a = sub.add_parser("aggregate")
    a.add_argument("--aggregate-dir", type=Path, required=True)
    a.add_argument("--results-root", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "verify-all":
        out = verify_all(args.aggregate_dir, args.pairs_root, ru_surface=args.ru_surface)
    elif args.command == "evaluate-pair":
        out = evaluate_pair(args.aggregate_dir, args.pair_dir, args.pair_id, args.output, ru_surface=args.ru_surface)
    elif args.command == "aggregate":
        out = aggregate_results(args.aggregate_dir, args.results_root, args.output)
    else:
        raise AssertionError(args.command)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
