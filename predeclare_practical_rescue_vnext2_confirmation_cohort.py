#!/usr/bin/env python3
"""Sample the 192-pair vNext2 untouched cohort only after its protocol is frozen."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_general_random_taxa_regions import REGION_CELLS, TAXON_GROUPS, taxon_frame
from predeclare_practical_core_confirmation_cohort import (
    _prefix_excluded,
    _read_scientific_names,
    _record_strata,
)

EXPECTED_EXCLUDED_TAXA = 456
EXPECTED_PAIRS = 192


def _canonical_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not stored or stored != calculated:
        raise ValueError("vNext2 confirmation protocol fingerprint mismatch")
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(protocol_path: Path, output: Path) -> dict[str, object]:
    protocol, fingerprint = _canonical_protocol(protocol_path)
    if protocol.get("protocol_id") != "acsp-practical-rescue-vnext2-untouched-confirmation-v1":
        raise ValueError("unexpected vNext2 confirmation protocol ID")
    if protocol.get("new_confirmation_taxa_sampled_at_protocol_freeze") is not False:
        raise ValueError("new vNext2 taxa were sampled before protocol freeze")
    if protocol.get("new_confirmation_occurrence_outcomes_inspected_at_protocol_freeze") is not False:
        raise ValueError("new vNext2 outcomes were inspected before protocol freeze")
    if protocol.get("missing_pair_artifacts_scored_as_zero") is not False:
        raise ValueError("vNext2 protocol permits infrastructure zero filling")
    if protocol.get("taxon_replacement_after_declaration_allowed") is not False:
        raise ValueError("vNext2 protocol permits taxon replacement")

    cohort = protocol["cohort"]
    groups = list(map(str, cohort["taxon_groups"]))
    n_strata = int(cohort["record_count_strata"])
    per_cell = int(cohort["taxa_per_region_group_record_stratum"])
    expected_pairs = int(cohort["pair_count"])
    expected_design = len(REGION_CELLS) * len(groups) * n_strata * per_cell
    if expected_pairs != expected_design or expected_pairs != EXPECTED_PAIRS:
        raise ValueError("vNext2 cohort dimensions do not imply exactly 192 pairs")

    exclusion_paths = [Path(str(value)) for value in protocol["exclusion_files"]]
    excluded: set[str] = set()
    for path in exclusion_paths:
        excluded.update(_read_scientific_names(path))
    if len(excluded) != EXPECTED_EXCLUDED_TAXA:
        raise ValueError(f"vNext2 exclusion union has {len(excluded)} taxa, expected 456")
    canonical = Path(str(protocol["exclusion"]["excluded_taxa_path"]))
    if canonical not in exclusion_paths:
        raise ValueError("canonical vNext2 exclusion path is missing from exclusion_files")
    if _sha256(canonical) != str(protocol["exclusion"]["excluded_taxa_sha256"]):
        raise ValueError("vNext2 exclusion file differs from frozen protocol")

    prefixes = tuple(map(str, protocol.get("explicit_exclusion_prefixes", [])))
    master = np.random.SeedSequence(int(cohort["seed"]))
    child_seeds = master.spawn(len(REGION_CELLS) * len(groups) * n_strata)
    child_index = 0
    used: set[str] = set()
    selections: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    pair_id = 1

    for region_index, cell_tuple in enumerate(REGION_CELLS):
        geographic, region_name, west, south, east, north = cell_tuple
        bounds = (float(west), float(south), float(east), float(north))
        for group in groups:
            if group not in TAXON_GROUPS:
                raise ValueError(f"unknown taxon group: {group}")
            frame = taxon_frame(
                bounds,
                TAXON_GROUPS[group],
                int(cohort["facet_limit"]),
                int(cohort["minimum_records"]),
            )
            if frame.empty:
                raise RuntimeError(f"empty taxon frame for {region_name} / {group}")
            frame = frame.drop_duplicates("scientific_name").copy()
            frame["excluded_exact"] = frame["scientific_name"].astype(str).isin(excluded)
            frame["excluded_prefix"] = frame["scientific_name"].map(
                lambda value: _prefix_excluded(value, prefixes)
            )
            eligible = frame.loc[~(frame["excluded_exact"] | frame["excluded_prefix"])].copy()
            eligible = _record_strata(eligible, n_strata)

            for record_stratum in range(n_strata):
                rng = np.random.default_rng(child_seeds[child_index])
                child_index += 1
                stratum = eligible.loc[eligible["record_count_stratum"].eq(record_stratum)].copy()
                available = stratum.loc[
                    ~stratum["scientific_name"].astype(str).isin(used)
                ].copy()
                available = available.sort_values(
                    ["scientific_name", "speciesKey"], kind="mergesort"
                ).reset_index(drop=True)
                audits.append({
                    "geographic_stratum": geographic,
                    "region_name": region_name,
                    "taxon_group": group,
                    "record_count_stratum": record_stratum,
                    "raw_taxon_frame": int(len(frame)),
                    "post_456_exclusion_frame": int(len(eligible)),
                    "stratum_frame": int(len(stratum)),
                    "available_unused_before_draw": int(len(available)),
                    "required_draws": per_cell,
                })
                if len(available) < per_cell:
                    raise RuntimeError(
                        f"insufficient vNext2 fresh taxa for {region_name}/{group}/stratum{record_stratum}: "
                        f"available={len(available)}, required={per_cell}"
                    )
                positions = rng.choice(len(available), size=per_cell, replace=False)
                chosen = available.iloc[np.sort(positions)].copy()
                for replicate, (_, row) in enumerate(chosen.iterrows(), start=1):
                    name = str(row.scientific_name).strip()
                    if name in used or name in excluded or _prefix_excluded(name, prefixes):
                        raise AssertionError("vNext2 sampler selected a used/excluded taxon")
                    used.add(name)
                    selections.append({
                        "pair_id": pair_id,
                        "status": "predeclared_vnext2_untouched_after_final_router_freeze",
                        "taxon_group": group,
                        "kingdomKey": TAXON_GROUPS[group],
                        "geographic_stratum": geographic,
                        "region_name": region_name,
                        "region_cell_index": region_index + 1,
                        "west": bounds[0],
                        "south": bounds[1],
                        "east": bounds[2],
                        "north": bounds[3],
                        "speciesKey": int(row.speciesKey),
                        "scientific_name": name,
                        "coordinate_records": int(row.coordinate_records),
                        "record_count_stratum": record_stratum,
                        "within_cell_stratum_replicate": replicate,
                    })
                    pair_id += 1

    declared = pd.DataFrame(selections)
    audit = pd.DataFrame(audits)
    if len(declared) != EXPECTED_PAIRS or declared["scientific_name"].nunique() != EXPECTED_PAIRS:
        raise RuntimeError("vNext2 sampler failed the unique 192-pair contract")
    if set(declared["scientific_name"].astype(str)) & excluded:
        raise RuntimeError("vNext2 cohort overlaps the frozen 456-taxon exclusion union")
    expected_region = len(groups) * n_strata * per_cell
    expected_group = len(REGION_CELLS) * n_strata * per_cell
    expected_record = len(REGION_CELLS) * len(groups) * per_cell
    region_counts = declared["region_name"].value_counts().sort_index()
    group_counts = declared["taxon_group"].value_counts().sort_index()
    record_counts = declared["record_count_stratum"].value_counts().sort_index()
    if not (region_counts == expected_region).all():
        raise RuntimeError("vNext2 region-cell imbalance")
    if not (group_counts == expected_group).all():
        raise RuntimeError("vNext2 taxon-group imbalance")
    if not (record_counts == expected_record).all():
        raise RuntimeError("vNext2 record-stratum imbalance")

    output.mkdir(parents=True, exist_ok=True)
    cohort_path = output / "predeclared_taxon_region_pairs.csv"
    audit_path = output / "sampling_frame_audit.csv"
    declared.to_csv(cohort_path, index=False)
    audit.to_csv(audit_path, index=False)
    result = {
        "status": "vnext2_untouched_confirmation_cohort_ready",
        "protocol_fingerprint": fingerprint,
        "excluded_unique_taxa": EXPECTED_EXCLUDED_TAXA,
        "declared_pairs": len(declared),
        "unique_declared_taxa": declared["scientific_name"].nunique(),
        "taxon_group_counts": {str(k): int(v) for k, v in group_counts.items()},
        "region_cell_counts": {str(k): int(v) for k, v in region_counts.items()},
        "record_count_stratum_counts": {str(k): int(v) for k, v in record_counts.items()},
        "minimum_available_unused_in_cell_stratum": int(audit["available_unused_before_draw"].min()),
        "cohort_sha256": _sha256(cohort_path),
        "sampling_frame_audit_sha256": _sha256(audit_path),
        "occurrence_rows_fetched_for_declared_taxa": False,
        "candidate_generation_run": False,
        "router_run": False,
        "rescue_v2_run": False,
        "grts_run": False,
        "heldout_recovery_run": False,
        "taxon_replacement_after_declaration_allowed": False,
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--protocol", dest="protocol_path", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
