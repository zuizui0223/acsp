#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from geographic_framing_country_registry_v3 import HISTORICAL_YEARS, fetch_country_facet_counts
from geoboundaries_v6_provider import (
    GEOBOUNDARIES_RELEASE_COMMIT,
    GEOBOUNDARIES_SOURCE_ID,
    fetch_geoboundaries_country_geometry,
)
from predeclare_country_framed_integration_development_v1 import (
    SOURCE_COHORT_PATH,
    _geometry_digest_from_source_version,
    choose_historical_country,
)
from predeclare_country_framed_integration_development_v2 import (
    CONFIRMATION_PATH,
    EXPECTED_PROTOCOL_FINGERPRINT,
    V11_PATH,
    V1_PATH,
    _protocol,
    select_v2_taxa,
)

ROOT = Path(__file__).resolve().parents[1]
REPLICATION_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2_replication.json"
EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT = "66d5eba6d5e92e89bcf941b40aa0cec91f39479c25bb8c5e1a0f403b50d3a94c"


def replication_protocol() -> dict[str, object]:
    payload = json.loads(REPLICATION_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT or calculated != EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT:
        raise ValueError("v2 replication protocol fingerprint mismatch")
    if payload["upstream_v2"]["authoritative_protocol_fingerprint"] != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("replication no longer targets authoritative v2")
    if payload["method_identity"]["change_from_authoritative_v2"] != "cohort_identity_rule_only":
        raise ValueError("replication method identity drifted")
    if payload["decision"]["retuning_on_replication_taxa_allowed"] is not False:
        raise ValueError("replication retuning must remain forbidden")
    payload["protocol_fingerprint"] = stored
    return payload


def select_replication_taxa(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for region in range(1, 13):
        wanted = (region + 2) % 4
        for group in ("plant", "animal"):
            hit = frame[
                (pd.to_numeric(frame.region_cell_index) == region)
                & (frame.taxon_group.astype(str) == group)
                & (pd.to_numeric(frame.record_count_stratum) == wanted)
            ]
            if len(hit) != 1:
                raise ValueError(
                    f"expected one replication row for region={region}, group={group}, stratum={wanted}; found {len(hit)}"
                )
            rows.append(hit.iloc[0])
    out = pd.DataFrame(rows).reset_index(drop=True)
    out.insert(0, "integration_pair_id", range(1, 25))
    if out.taxon_group.value_counts().to_dict() != {"plant": 12, "animal": 12}:
        raise ValueError("replication group balance drifted")
    if out.record_count_stratum.astype(int).value_counts().sort_index().to_dict() != {0: 6, 1: 6, 2: 6, 3: 6}:
        raise ValueError("replication stratum balance drifted")

    used = set(pd.read_csv(V1_PATH).speciesKey.astype(int)) | set(pd.read_csv(V11_PATH).speciesKey.astype(int))
    used |= set(select_v2_taxa(frame).speciesKey.astype(int))
    overlap = set(out.speciesKey.astype(int)) & used
    if overlap:
        raise ValueError(f"replication reuses earlier integration taxa: {sorted(overlap)}")
    if CONFIRMATION_PATH.is_file():
        confirmation = set(pd.read_csv(CONFIRMATION_PATH).scientific_name.astype(str))
        overlap_names = set(out.scientific_name.astype(str)) & confirmation
        if overlap_names:
            raise ValueError(f"replication overlaps framing-confirmation taxa: {sorted(overlap_names)[:5]}")
    return out


def freeze_replication_declarations() -> tuple[pd.DataFrame, dict[str, object]]:
    replication = replication_protocol()
    authoritative = _protocol()
    selected = select_replication_taxa(pd.read_csv(SOURCE_COHORT_PATH))
    minimum = int(authoritative["framing"]["historical_country_min_count"])
    seed = int(authoritative["framing"]["country_selection_seed"])
    identity = replication["method_identity"]
    if minimum != int(identity["historical_country_min_count"]) or seed != int(identity["country_selection_seed"]):
        raise ValueError("replication country declaration constants drifted from v2")

    rows = []
    for item in selected.itertuples(index=False):
        base = item._asdict()
        key = int(base["speciesKey"])
        status = "country_declaration_failed"
        code = basis = digest = source_id = source_version = reason = ""
        count = 0
        counts_json = "{}"
        try:
            counts = dict(
                sorted((str(k).upper(), int(v)) for k, v in fetch_country_facet_counts(key, HISTORICAL_YEARS).items())
            )
            counts_json = json.dumps(counts, sort_keys=True, separators=(",", ":"))
            chosen, basis = choose_historical_country(
                counts, species_key=key, minimum_count=minimum, seed=seed
            )
            if chosen is None:
                reason = "no historical country satisfied frozen minimum-count rule"
            else:
                code = chosen
                count = int(counts[code])
                geom = fetch_geoboundaries_country_geometry(code)
                digest = _geometry_digest_from_source_version(geom.source_version)
                source_id = geom.source_id
                source_version = geom.source_version
                status = "declared"
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
        rows.append(
            {
                **base,
                "declaration_status": status,
                "selected_country_code": code,
                "country_selection_basis": basis,
                "historical_selected_country_count": count,
                "historical_country_counts_json": counts_json,
                "geometry_source_id": source_id,
                "geometry_source_version": source_version,
                "geometry_canonical_sha256": digest,
                "declaration_failure_reason": reason,
            }
        )

    declarations = pd.DataFrame(rows)
    manifest = {
        "status": "country_framed_integration_development_v2_replication_identities_frozen_before_outcomes",
        "replication_protocol_fingerprint": EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
        "authoritative_v2_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "cohort_rule": "record_count_stratum == (region_cell_index + 2) mod 4",
        "declared_taxa": 24,
        "unique_declared_taxa": int(declarations.speciesKey.nunique()),
        "successful_country_declarations": int(declarations.declaration_status.eq("declared").sum()),
        "failed_country_declarations": int(declarations.declaration_status.ne("declared").sum()),
        "taxon_group_counts": {k: int(v) for k, v in declarations.taxon_group.value_counts().sort_index().items()},
        "record_count_stratum_counts": {
            str(int(k)): int(v)
            for k, v in declarations.record_count_stratum.astype(int).value_counts().sort_index().items()
        },
        "historical_year_range": list(HISTORICAL_YEARS),
        "historical_country_min_count": minimum,
        "country_selection_seed": seed,
        "provider_source_id": GEOBOUNDARIES_SOURCE_ID,
        "provider_release_commit": GEOBOUNDARIES_RELEASE_COMMIT,
        "v1_taxa_reused": False,
        "v1_1_taxa_reused": False,
        "v2_taxa_reused": False,
        "confirmation_v1_taxa_consumed": False,
        "recent_outcomes_inspected": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "replacement_after_declaration_allowed": False,
        "retuning_allowed": False,
    }
    return declarations, manifest


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    declarations, manifest = freeze_replication_declarations()
    path = args.output / "predeclared_taxon_country_pairs.csv"
    declarations.to_csv(path, index=False)
    manifest["identity_csv_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (args.output / "cohort_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
