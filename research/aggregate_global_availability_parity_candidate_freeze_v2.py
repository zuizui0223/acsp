#!/usr/bin/env python3
"""Aggregate all 48 preheldout candidate-freeze pair artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_global_availability_parity_confirmation_v2.json"
ALLOWED_STATES = {"SENTINEL_OR_ABSTAIN", "ROBUST_EMPTY", "ROBUST_READY_PREHELDOUT"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def aggregate(input_root: Path, output: Path) -> dict[str, object]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    minimum = float(protocol["primary_dimensions"]["availability"]["robust_constructible_fraction_min"])
    rows: list[dict[str, object]] = []
    seen: set[int] = set()
    for result_path in sorted(Path(input_root).glob("global-parity-candidate-pair-*/pair_result.json")):
        data = json.loads(result_path.read_text(encoding="utf-8"))
        pair_id = int(data["availability_pair_id"])
        if pair_id in seen:
            raise ValueError(f"duplicate pair result: {pair_id}")
        seen.add(pair_id)
        state = str(data["preheldout_availability_state"])
        if state not in ALLOWED_STATES:
            raise ValueError(f"invalid preheldout state for pair {pair_id}: {state}")
        for key in ("heldout_2021_2025_opened", "random_baseline_run", "recall_or_lift_read", "validated_japan_core_changed"):
            expected = False
            if data.get(key) is not expected:
                raise ValueError(f"preheldout information boundary violated for pair {pair_id}: {key}")
        pair_dir = result_path.parent
        patch_path = pair_dir / "candidate_patches.csv"
        if not patch_path.is_file():
            raise ValueError(f"pair {pair_id} missing candidate patch artifact")
        if state == "ROBUST_READY_PREHELDOUT" and int(data.get("candidate_patch_count", 0)) <= 0:
            raise ValueError(f"READY pair {pair_id} has no patches")
        if state == "ROBUST_EMPTY" and int(data.get("candidate_patch_count", 0)) != 0:
            raise ValueError(f"ROBUST_EMPTY pair {pair_id} has patches")
        if state in {"ROBUST_READY_PREHELDOUT", "ROBUST_EMPTY"}:
            if pair_id == 48:
                if str(data.get("ru_candidate_surface_sha256")) != "77729dfa45b9e123f035ca15a421f834a6b155140ae410b8806e9f4eca19c982":
                    raise ValueError("RU candidate surface identity drift")
            else:
                surface = pair_dir / "candidate_surface.parquet"
                if not surface.is_file():
                    raise ValueError(f"constructible pair {pair_id} missing frozen candidate surface")
                if str(data.get("candidate_surface_sha256")) != _sha256(surface):
                    raise ValueError(f"pair {pair_id} candidate surface digest drift")
        rows.append({
            "availability_pair_id": pair_id,
            "taxon_group": str(data["taxon_group"]),
            "speciesKey": int(data["speciesKey"]),
            "scientific_name": str(data["scientific_name"]),
            "selected_country_code": str(data["selected_country_code"]),
            "preheldout_availability_state": state,
            "historical_training_occurrence_rows": int(data.get("historical_training_occurrence_rows", 0)),
            "complete_terrain_surface_points": int(data.get("complete_terrain_surface_points", 0)),
            "prototype_rows": int(data.get("prototype_rows", 0)),
            "candidate_patch_count": int(data.get("candidate_patch_count", 0)),
            "country_geometry_canonical_sha256": str(data.get("country_geometry_canonical_sha256", "")),
            "candidate_surface_sha256": str(data.get("candidate_surface_sha256") or data.get("ru_candidate_surface_sha256") or ""),
            "candidate_patches_sha256": str(data.get("candidate_patches_sha256") or _sha256(patch_path)),
        })
    if seen != set(range(1, 49)):
        raise ValueError(f"candidate freeze requires exact pair IDs 1..48; missing={sorted(set(range(1,49))-seen)}")
    states = pd.DataFrame(rows).sort_values("availability_pair_id", kind="mergesort").reset_index(drop=True)
    counts = states["preheldout_availability_state"].value_counts().to_dict()
    constructible = int(counts.get("ROBUST_READY_PREHELDOUT", 0) + counts.get("ROBUST_EMPTY", 0))
    fraction = constructible / 48.0
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / "preheldout_states.csv"
    states.to_csv(state_path, index=False)
    summary = {
        "schema_version": "global-availability-parity-candidate-freeze-summary-v2",
        "status": "ALL_48_PREHELDOUT_AVAILABILITY_STATES_FROZEN",
        "taxon_count": 48,
        "state_counts": {str(k): int(v) for k, v in counts.items()},
        "robust_constructible_taxa": constructible,
        "robust_constructible_fraction": fraction,
        "frozen_availability_gate_min": minimum,
        "availability_gate_passed_preheldout": bool(fraction >= minimum),
        "preheldout_states_sha256": _sha256(state_path),
        "heldout_2021_2025_opened": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "taxon_or_country_replacement": False,
        "validated_japan_core_changed": False,
        "global_product_promoted": False,
    }
    (output / "candidate_freeze_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = aggregate(args.input_root, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
