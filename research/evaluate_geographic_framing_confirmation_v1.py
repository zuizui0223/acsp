#!/usr/bin/env python3
"""Evaluate the frozen country-registry framing rule on a fresh cohort.

This is the independent framing confirmation layer. It uses the representation,
temporal split, quality filters, estimands, and thresholds frozen before cohort
sampling. Candidate generation and robust ecological support are intentionally
not run here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from evaluate_geographic_framing_development_v4 import (
    _conditional_mean,
    _snapshot_fingerprint,
    _unexpected_zero,
    _yield_fraction,
)
from geographic_framing_country_registry_v3 import evaluate_country_registry_taxon

PROTOCOL_PATH = Path("validation/acsp_geographic_framing_confirmation_protocol_v1.json")
EXPECTED_PROTOCOL = "9f655f6121f1c917659dcf85ba039304b645ea88b5afff8d7855a11cf1e7a490"
FREEZE_PATH = Path("validation/acsp_geographic_framing_country_registry_freeze_v1.json")


def _protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_PROTOCOL or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"confirmation protocol fingerprint mismatch: file={stored}, calculated={calculated}, expected={EXPECTED_PROTOCOL}"
        )
    payload["protocol_fingerprint"] = stored
    return payload


def _audit_freeze(protocol: dict[str, object]) -> None:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    if freeze.get("freeze_id") != protocol["representation_freeze"]["freeze_id"]:
        raise ValueError("confirmation protocol does not reference the frozen framing representation")
    if freeze.get("status") != "frozen_after_v4_development_pass_before_fresh_confirmation":
        raise ValueError("unexpected framing freeze status")
    if not bool(freeze["decision"]["representation_frozen"]):
        raise ValueError("framing representation is not frozen")
    if bool(freeze["decision"]["retuning_on_v4_development_taxa_allowed"]):
        raise ValueError("freeze unexpectedly permits retuning")


def run(sample_file: Path, output: Path) -> dict[str, object]:
    protocol = _protocol()
    _audit_freeze(protocol)
    sample = pd.read_csv(sample_file)
    sample = sample.loc[sample["status"].astype(str).eq("predeclared")].copy()
    if len(sample) != 96 or sample["scientific_name"].nunique() != 96:
        raise ValueError("confirmation requires exactly 96 unique predeclared taxa")
    if sample["scientific_name"].astype(str).str.startswith(("Campanula microdonta", "Campanula punctata")).any():
        raise ValueError("confirmation cohort contains excluded Campanula development complex")

    development_v3 = pd.read_csv(protocol["cohort"]["development_v3_identity_path"])
    development_v4 = pd.read_csv(protocol["cohort"]["development_v4_identity_path"])
    declared_names = set(sample["scientific_name"].astype(str))
    if declared_names & set(development_v3["scientific_name"].astype(str)):
        raise ValueError("confirmation cohort overlaps v3 framing-development taxa")
    if declared_names & set(development_v4["scientific_name"].astype(str)):
        raise ValueError("confirmation cohort overlaps v4 framing-development taxa")

    rows: list[dict[str, object]] = []
    for _, row in sample.sort_values("pair_id").iterrows():
        try:
            rows.append(evaluate_country_registry_taxon(row).as_dict())
        except Exception as exc:
            rows.append(_unexpected_zero(row, exc))
    diagnostics = pd.DataFrame(rows).sort_values("pair_id").reset_index(drop=True)
    if len(diagnostics) != 96:
        raise AssertionError("all 96 confirmation taxa must remain in the yield denominator")

    historical_available = diagnostics["historical_country_count"].astype(float).gt(0)
    temporal_evaluable = diagnostics["status"].astype(str).eq("evaluated")

    historical_yield = _yield_fraction(diagnostics, historical_available)
    temporal_yield = _yield_fraction(diagnostics, temporal_evaluable)
    plant_temporal_yield = _yield_fraction(diagnostics, temporal_evaluable, "plant")
    animal_temporal_yield = _yield_fraction(diagnostics, temporal_evaluable, "animal")
    conditional_overall = _conditional_mean(diagnostics)
    conditional_plant = _conditional_mean(diagnostics, "plant")
    conditional_animal = _conditional_mean(diagnostics, "animal")

    gate = protocol["confirmation_gate"]
    gate_passed = bool(
        len(diagnostics) == int(gate["required_declared_taxa"])
        and historical_yield >= float(gate["historical_registry_availability_min"])
        and temporal_yield >= float(gate["temporal_evaluability_overall_min"])
        and plant_temporal_yield >= float(gate["plant_temporal_evaluability_min"])
        and animal_temporal_yield >= float(gate["animal_temporal_evaluability_min"])
        and conditional_overall >= float(gate["conditional_containment_overall_min"])
        and conditional_plant >= float(gate["plant_conditional_containment_min"])
        and conditional_animal >= float(gate["animal_conditional_containment_min"])
    )

    output.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(output / "country_registry_confirmation_v1_taxon_diagnostics.csv", index=False)
    status_counts = diagnostics["status"].astype(str).value_counts().to_dict()
    summary: dict[str, object] = {
        "status": "fresh_country_registry_framing_confirmation_v1_complete",
        "protocol_fingerprint": EXPECTED_PROTOCOL,
        "representation_freeze_id": str(protocol["representation_freeze"]["freeze_id"]),
        "declared_taxa": 96,
        "taxa_in_yield_denominator": 96,
        "historical_registry_available_taxa": int(historical_available.sum()),
        "historical_registry_availability": historical_yield,
        "temporally_evaluable_taxa": int(temporal_evaluable.sum()),
        "temporal_evaluability": temporal_yield,
        "plant_temporal_evaluability": plant_temporal_yield,
        "animal_temporal_evaluability": animal_temporal_yield,
        "conditional_containment_taxa": int(temporal_evaluable.sum()),
        "conditional_mean_recent_record_containment": conditional_overall,
        "plant_conditional_mean_recent_record_containment": conditional_plant,
        "animal_conditional_mean_recent_record_containment": conditional_animal,
        "conditional_mean_recent_country_containment": float(
            diagnostics.loc[temporal_evaluable, "recent_country_containment"].mean()
        ) if temporal_evaluable.any() else 0.0,
        "median_historical_country_count": float(diagnostics["historical_country_count"].median()),
        "mean_historical_country_count": float(diagnostics["historical_country_count"].mean()),
        "mean_new_recent_country_count_among_evaluable": float(
            diagnostics.loc[temporal_evaluable, "new_recent_country_count"].mean()
        ) if temporal_evaluable.any() else 0.0,
        "status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "diagnostic_snapshot_fingerprint": _snapshot_fingerprint(diagnostics),
        "confirmation_gate": gate,
        "confirmation_gate_passed": gate_passed,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "fresh_confirmation_taxa_consumed": True,
        "confirmation_taxon_replacement_allowed": False,
        "development_v3_taxa_reused": False,
        "development_v4_taxa_reused": False,
        "validated_japan_adapter_changed": False,
        "global_name_only_acsp_validated": False,
        "country_representation_changed_after_v4_freeze": False,
        "country_expansion_or_fallback_used": False,
        "interpretation_if_pass": str(protocol["claim_boundary"]["if_passes"]),
        "interpretation_if_fail": str(protocol["claim_boundary"]["if_fails"]),
    }
    (output / "country_registry_confirmation_v1_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.sample_file, args.output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
