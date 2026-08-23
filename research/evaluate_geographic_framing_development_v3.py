#!/usr/bin/env python3
"""Evaluate the predeclared historical-country registry framing v3."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from geographic_framing_country_registry_v3 import evaluate_country_registry_taxon

PROTOCOL_PATH = Path("validation/acsp_geographic_framing_development_protocol_v3.json")
EXPECTED_PROTOCOL = "23ccd2ad90d387438079a992335978734bd0a460433cf266300e3852cdd1f9ce"


def _protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_PROTOCOL or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"v3 protocol fingerprint mismatch: file={stored}, calculated={calculated}, expected={EXPECTED_PROTOCOL}"
        )
    payload["protocol_fingerprint"] = stored
    return payload


def _diagnostic_fingerprint(frame: pd.DataFrame) -> str:
    canonical = frame.copy().reindex(sorted(frame.columns), axis=1)
    canonical = canonical.sort_values(["pair_id"], kind="stable").reset_index(drop=True)
    return hashlib.sha256(canonical.to_csv(index=False).encode("utf-8")).hexdigest()


def run(sample_file: Path, output: Path) -> dict[str, object]:
    protocol = _protocol()
    sample = pd.read_csv(sample_file)
    sample = sample.loc[sample["status"].astype(str).eq("predeclared")].copy()
    if len(sample) != 96:
        raise ValueError(f"expected 96 development taxa, found {len(sample)}")
    if sample["scientific_name"].duplicated().any():
        raise ValueError("development cohort contains duplicate taxa")
    if sample["scientific_name"].astype(str).str.startswith(("Campanula microdonta", "Campanula punctata")).any():
        raise ValueError("development cohort contains excluded Campanula development complex")

    rows: list[dict[str, object]] = []
    for _, row in sample.sort_values("pair_id").iterrows():
        try:
            diagnostic = evaluate_country_registry_taxon(row)
            rows.append(diagnostic.as_dict())
        except Exception as exc:
            rows.append({
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
            })

    diagnostics = pd.DataFrame(rows).sort_values("pair_id").reset_index(drop=True)
    if len(diagnostics) != 96:
        raise AssertionError("v3 must retain all 96 taxa")
    output.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(output / "country_registry_v3_taxon_diagnostics.csv", index=False)

    overall = float(diagnostics["recent_record_containment"].mean())
    plant = float(
        diagnostics.loc[diagnostics["taxon_group"].astype(str).eq("plant"), "recent_record_containment"].mean()
    )
    animal = float(
        diagnostics.loc[diagnostics["taxon_group"].astype(str).eq("animal"), "recent_record_containment"].mean()
    )
    gate = protocol["development_gate"]
    gate_passed = bool(
        len(diagnostics) == int(gate["required_taxa_in_denominator"])
        and overall >= float(gate["overall_mean_recent_record_containment_min"])
        and plant >= float(gate["plant_mean_recent_record_containment_min"])
        and animal >= float(gate["animal_mean_recent_record_containment_min"])
    )
    status_counts = diagnostics["status"].astype(str).value_counts().to_dict()
    summary: dict[str, object] = {
        "status": "development_only_historical_country_registry_v3_complete",
        "protocol_fingerprint": EXPECTED_PROTOCOL,
        "development_taxa": 96,
        "taxa_in_denominator": int(len(diagnostics)),
        "analyzable_taxa": int(diagnostics["status"].eq("evaluated").sum()),
        "failed_or_unanalyzable_taxa_retained_as_zero": int((~diagnostics["status"].eq("evaluated")).sum()),
        "mean_taxon_recent_record_country_containment": overall,
        "plant_mean_taxon_recent_record_country_containment": plant,
        "animal_mean_taxon_recent_record_country_containment": animal,
        "mean_taxon_recent_country_containment": float(diagnostics["recent_country_containment"].mean()),
        "median_historical_country_count": float(diagnostics["historical_country_count"].median()),
        "mean_historical_country_count": float(diagnostics["historical_country_count"].mean()),
        "median_recent_country_count": float(diagnostics["recent_country_count"].median()),
        "mean_new_recent_country_count": float(diagnostics["new_recent_country_count"].mean()),
        "median_historical_country_fraction_of_249": float(diagnostics["historical_country_fraction_of_249"].median()),
        "status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "diagnostic_snapshot_fingerprint": _diagnostic_fingerprint(diagnostics),
        "promotion_gate": gate,
        "promotion_gate_passed": gate_passed,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "fresh_confirmation_taxa_consumed": False,
        "validated_japan_adapter_changed": False,
        "global_name_only_claim_allowed": False,
        "compactness_gate_used": False,
        "country_expansion_or_fallback_used": False,
        "interpretation_if_pass": "freeze registry representation before fresh framing confirmation; do not promote from development result",
        "interpretation_if_fail": "reject v3 without changing temporal split or adding country/fallback expansion on these same 96 taxa",
    }
    (output / "country_registry_v3_summary.json").write_text(
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
