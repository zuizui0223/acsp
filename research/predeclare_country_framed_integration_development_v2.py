#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from geographic_framing_country_registry_v3 import HISTORICAL_YEARS, fetch_country_facet_counts
from geoboundaries_v6_provider import GEOBOUNDARIES_RELEASE_COMMIT, GEOBOUNDARIES_SOURCE_ID, fetch_geoboundaries_country_geometry
from predeclare_country_framed_integration_development_v1 import SOURCE_COHORT_PATH, choose_historical_country, _geometry_digest_from_source_version

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2.json"
V1_PATH = ROOT / "validation" / "country_framed_robust_integration_development_v1" / "predeclared_taxon_country_pairs_compact.csv"
V11_PATH = ROOT / "validation" / "country_framed_robust_integration_development_v1_1" / "predeclared_taxon_country_pairs_compact.csv"
CONFIRMATION_PATH = ROOT / "validation" / "geographic_framing_confirmation_v1" / "confirmation_taxa.csv"
EXPECTED_PROTOCOL_FINGERPRINT = "7535e749d3cc04c8d49db13957da53685a5050eec7d1e9e2d6624348332a56f9"


def _protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    if stored != EXPECTED_PROTOCOL_FINGERPRINT or calculated != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("v2 protocol fingerprint mismatch")
    payload["protocol_fingerprint"] = stored
    return payload


def select_v2_taxa(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for region in range(1, 13):
        wanted = (region + 1) % 4
        for group in ("plant", "animal"):
            hit = frame[(pd.to_numeric(frame.region_cell_index) == region) & (frame.taxon_group.astype(str) == group) & (pd.to_numeric(frame.record_count_stratum) == wanted)]
            if len(hit) != 1:
                raise ValueError(f"expected one row for region={region}, group={group}, stratum={wanted}; found {len(hit)}")
            rows.append(hit.iloc[0])
    out = pd.DataFrame(rows).reset_index(drop=True)
    out.insert(0, "integration_pair_id", range(1, 25))
    if out.taxon_group.value_counts().to_dict() != {"plant": 12, "animal": 12}:
        raise ValueError("v2 group balance drifted")
    if out.record_count_stratum.astype(int).value_counts().sort_index().to_dict() != {0: 6, 1: 6, 2: 6, 3: 6}:
        raise ValueError("v2 stratum balance drifted")
    used = set(pd.read_csv(V1_PATH).speciesKey.astype(int)) | set(pd.read_csv(V11_PATH).speciesKey.astype(int))
    overlap = set(out.speciesKey.astype(int)) & used
    if overlap:
        raise ValueError(f"v2 reuses v1/v1.1 taxa: {sorted(overlap)}")
    if CONFIRMATION_PATH.is_file():
        confirmation = set(pd.read_csv(CONFIRMATION_PATH).scientific_name.astype(str))
        overlap_names = set(out.scientific_name.astype(str)) & confirmation
        if overlap_names:
            raise ValueError(f"v2 overlaps confirmation taxa: {sorted(overlap_names)[:5]}")
    return out


def freeze_declarations() -> tuple[pd.DataFrame, dict[str, object]]:
    protocol = _protocol()
    selected = select_v2_taxa(pd.read_csv(SOURCE_COHORT_PATH))
    minimum = int(protocol["framing"]["historical_country_min_count"])
    seed = int(protocol["framing"]["country_selection_seed"])
    rows = []
    for item in selected.itertuples(index=False):
        base = item._asdict(); key = int(base["speciesKey"])
        status="country_declaration_failed"; code=""; basis=""; count=0; digest=""; source_id=""; source_version=""; reason=""; counts_json="{}"
        try:
            counts = dict(sorted((str(k).upper(), int(v)) for k,v in fetch_country_facet_counts(key, HISTORICAL_YEARS).items()))
            counts_json = json.dumps(counts, sort_keys=True, separators=(",", ":"))
            chosen, basis = choose_historical_country(counts, species_key=key, minimum_count=minimum, seed=seed)
            if chosen is None:
                reason = "no historical country satisfied frozen minimum-count rule"
            else:
                code = chosen; count = int(counts[code]); geom = fetch_geoboundaries_country_geometry(code)
                digest = _geometry_digest_from_source_version(geom.source_version); source_id=geom.source_id; source_version=geom.source_version; status="declared"
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
        rows.append({**base,"declaration_status":status,"selected_country_code":code,"country_selection_basis":basis,"historical_selected_country_count":count,"historical_country_counts_json":counts_json,"geometry_source_id":source_id,"geometry_source_version":source_version,"geometry_canonical_sha256":digest,"declaration_failure_reason":reason})
    declarations = pd.DataFrame(rows)
    manifest = {
        "status":"country_framed_integration_development_v2_identities_frozen_before_outcomes",
        "protocol_fingerprint":EXPECTED_PROTOCOL_FINGERPRINT,
        "declared_taxa":24,
        "unique_declared_taxa":int(declarations.speciesKey.nunique()),
        "successful_country_declarations":int(declarations.declaration_status.eq("declared").sum()),
        "failed_country_declarations":int(declarations.declaration_status.ne("declared").sum()),
        "taxon_group_counts":{k:int(v) for k,v in declarations.taxon_group.value_counts().sort_index().items()},
        "record_count_stratum_counts":{str(int(k)):int(v) for k,v in declarations.record_count_stratum.astype(int).value_counts().sort_index().items()},
        "historical_year_range":list(HISTORICAL_YEARS),"historical_country_min_count":minimum,"country_selection_seed":seed,
        "provider_source_id":GEOBOUNDARIES_SOURCE_ID,"provider_release_commit":GEOBOUNDARIES_RELEASE_COMMIT,
        "v1_taxa_reused":False,"v1_1_taxa_reused":False,"confirmation_v1_taxa_consumed":False,
        "recent_outcomes_inspected":False,"candidate_generation_run":False,"robust_support_run":False,"random_baseline_run":False,"replacement_after_declaration_allowed":False
    }
    return declarations, manifest


def main(argv: Sequence[str] | None = None) -> int:
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path,required=True); args=p.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=True); declarations,manifest=freeze_declarations(); path=args.output/"predeclared_taxon_country_pairs.csv"; declarations.to_csv(path,index=False)
    manifest["identity_csv_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest(); (args.output/"cohort_manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); print(json.dumps(manifest,indent=2,ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
