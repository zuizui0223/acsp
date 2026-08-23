#!/usr/bin/env python3
"""Evaluate country-registry framing v4 on a new disjoint development cohort.

The geographic representation is unchanged from v3.  V4 changes only the
validation estimands: registry availability and temporal evaluability are yield
endpoints over all declared taxa, while geographic containment is evaluated
conditionally among taxa for which a recent temporal outcome objectively exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from geographic_framing_country_registry_v3 import evaluate_country_registry_taxon

PROTOCOL_PATH = Path("validation/acsp_geographic_framing_development_protocol_v4.json")
EXPECTED_PROTOCOL = "3bd9e6145e17a99b52d8a9f82c07f346541f56a2bf81bd768e180de78c295bf8"


def _protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_PROTOCOL or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"v4 protocol fingerprint mismatch: file={stored}, calculated={calculated}, expected={EXPECTED_PROTOCOL}"
        )
    payload["protocol_fingerprint"] = stored
    return payload


def _snapshot_fingerprint(frame: pd.DataFrame) -> str:
    canonical = frame.copy().reindex(sorted(frame.columns), axis=1)
    canonical = canonical.sort_values(["pair_id"], kind="stable").reset_index(drop=True)
    return hashlib.sha256(canonical.to_csv(index=False).encode("utf-8")).hexdigest()


def _unexpected_zero(row: pd.Series, exc: Exception) -> dict[str, object]:
    return {
        "pair_id": int(row.pair_id),
        "scientific_name": str(row.scientific_name),
        "species_key": int(row.speciesKey),
        "taxon_group": str(row.taxon_group),
        "status": "unexpected_evaluator_failure",
        "historical_record_count": 0,
        "recent_record_count": 0,
        "recent_records_inside_registry": 0,
        "recent_record_containment": 0.0,
        "historical_country_count": 0,
        "recent_country_count": 0,
        "recent_countries_inside_registry": 0,
        "recent_country_containment": 0.0,
        "new_recent_country_count": 0,
        "historical_country_fraction_of_249": 0.0,
        "historical_countries": "",
        "recent_countries": "",
        "new_recent_countries": "",
        "historical_country_counts_json": "{}",
        "recent_country_counts_json": "{}",
        "failure_reason": f"{type(exc).__name__}: {exc}",
    }


def _conditional_mean(frame: pd.DataFrame, group: str | None = None) -> float:
    work = frame.loc[frame["status"].astype(str).eq("evaluated")]
    if group is not None:
        work = work.loc[work["taxon_group"].astype(str).eq(group)]
    if work.empty:
        return 0.0
    return float(work["recent_record_containment"].mean())


def _yield_fraction(frame: pd.DataFrame, mask: pd.Series, group: str | None = None) -> float:
    work = frame
    use_mask = mask
    if group is not None:
        group_mask = work["taxon_group"].astype(str).eq(group)
        denominator = int(group_mask.sum())
        return float((use_mask & group_mask).sum() / denominator) if denominator else 0.0
    return float(use_mask.sum() / len(work)) if len(work) else 0.0


def run(sample_file: Path, output: Path) -> dict[str, object]:
    protocol = _protocol()
    sample = pd.read_csv(sample_file)
    sample = sample.loc[sample["status"].astype(str).eq("predeclared")].copy()
    if len(sample) != 96 or sample["scientific_name"].nunique() != 96:
        raise ValueError("v4 requires exactly 96 unique predeclared taxa")
    if sample["scientific_name"].astype(str).str.startswith(("Campanula microdonta", "Campanula punctata")).any():
        raise ValueError("v4 cohort contains excluded Campanula development complex")

    rows: list[dict[str, object]] = []
    for _, row in sample.sort_values("pair_id").iterrows():
        try:
            rows.append(evaluate_country_registry_taxon(row).as_dict())
        except Exception as exc:
            rows.append(_unexpected_zero(row, exc))
    diagnostics = pd.DataFrame(rows).sort_values("pair_id").reset_index(drop=True)
    if len(diagnostics) != 96:
        raise AssertionError("all 96 v4 taxa must remain in the yield denominator")

    historical_available = diagnostics["historical_country_count"].astype(float).gt(0)
    temporal_evaluable = diagnostics["status"].astype(str).eq("evaluated")

    historical_yield = _yield_fraction(diagnostics, historical_available)
    temporal_yield = _yield_fraction(diagnostics, temporal_evaluable)
    plant_temporal_yield = _yield_fraction(diagnostics, temporal_evaluable, "plant")
    animal_temporal_yield = _yield_fraction(diagnostics, temporal_evaluable, "animal")
    conditional_overall = _conditional_mean(diagnostics)
    conditional_plant = _conditional_mean(diagnostics, "plant")
    conditional_animal = _conditional_mean(diagnostics, "animal")

    gate = protocol["development_gate"]
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
    diagnostics.to_csv(output / "country_registry_v4_taxon_diagnostics.csv", index=False)
    status_counts = diagnostics["status"].astype(str).value_counts().to_dict()
    summary: dict[str, object] = {
        "status": "development_only_country_registry_v4_two_part_complete",
        "protocol_fingerprint": EXPECTED_PROTOCOL,
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
        "promotion_gate": gate,
        "promotion_gate_passed": gate_passed,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "new_cohort_is_development_only": True,
        "fresh_confirmation_taxa_consumed": False,
        "validated_japan_adapter_changed": False,
        "global_name_only_claim_allowed": False,
        "country_representation_changed_from_v3": False,
        "country_expansion_or_fallback_used": False,
        "interpretation_if_pass": "freeze unchanged country registry representation before fresh framing confirmation",
        "interpretation_if_fail": "reject v4 without country expansion or temporal-window tuning on this cohort",
    }
    (output / "country_registry_v4_summary.json").write_text(
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
