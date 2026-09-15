#!/usr/bin/env python3
"""Stage 3 v2: freeze one non-RU global candidate result before heldout opening.

This module consumes the byte-frozen 48 taxon-country plans and executes only
geometry -> historical occurrences -> regional terrain surface -> the unchanged
validated robust candidate core. It deliberately does not import or call any
2021-2025, recovery, random-baseline, or lift function.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from acsp.taxon_patches import ROBUST_TERRAIN_FEATURES
from acsp.validated_robust import validated_robust_candidate_patches
from country_framed_robust_integration import fetch_country_occurrences
from geoboundaries_v6_provider import fetch_geoboundaries_country_geometry
from run_country_framed_integration_development_v1_1 import _geometry_digest_from_source_version
from run_country_framed_integration_development_v2 import regional_terrain_inputs

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "validation" / "acsp_global_availability_parity_country_plans_v2.csv"
RECEIPT_PATH = ROOT / "validation" / "acsp_global_availability_parity_country_receipt_v2.json"
CONTRACT_PATH = ROOT / "validation" / "acsp_global_availability_parity_candidate_freeze_v2.json"
EXPECTED_PLAN_SHA256 = "8a18ead4f9373e3c78c63eb158aeaac2fca3a979cc8fb558b8f84d3e01c4e4d9"
EXPECTED_PLAN_CANONICAL_SHA256 = "88eeaa983ff011426a3341fa1b98fb16d3bb2ca468be0d79dc5602cb3b2c420b"
EXPECTED_AUTHORITATIVE_V2 = "7535e749d3cc04c8d49db13957da53685a5050eec7d1e9e2d6624348332a56f9"
EVIDENCE_FAILURE_PREFIXES = (
    "GBIF returned no usable historical occurrence rows in ",
    "fewer than five usable historical occurrence rows in ",
    "regional lattice has no complete terrain surface points",
    "fewer than five unique complete historical terrain prototypes:",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _canonical_sha256(value: object) -> str:
    return _sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def verify_inputs() -> pd.DataFrame:
    if _sha256_file(PLAN_PATH) != EXPECTED_PLAN_SHA256:
        raise ValueError("frozen stage2 country plan SHA256 drift")
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if receipt.get("status") != "HISTORICAL_COUNTRY_PLANS_FROZEN_PRE_GEOMETRY_PRE_CANDIDATES_PRE_HELDOUT_V2":
        raise ValueError("stage2 country receipt status drift")
    if receipt["authoritative_slim_plan"]["sha256"] != EXPECTED_PLAN_SHA256:
        raise ValueError("stage2 receipt plan digest drift")
    if receipt["authoritative_slim_plan"]["country_plan_canonical_sha256"] != EXPECTED_PLAN_CANONICAL_SHA256:
        raise ValueError("stage2 receipt canonical digest drift")
    if contract["scientific_method"]["authoritative_v2_fingerprint"] != EXPECTED_AUTHORITATIVE_V2:
        raise ValueError("candidate-freeze authoritative v2 fingerprint drift")
    for key in ("country_geometry_opened", "candidate_generation_run", "robust_support_run", "random_baseline_run", "heldout_2021_2025_opened", "recall_or_lift_read"):
        if receipt["information_boundary"].get(key) is not False:
            raise ValueError(f"stage2 information boundary already opened: {key}")
    frame = pd.read_csv(PLAN_PATH)
    required = {
        "availability_pair_id", "taxon_group", "speciesKey", "scientific_name",
        "country_plan_state", "selected_country_code", "historical_selected_country_count",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"frozen country plan missing columns: {missing}")
    if len(frame) != 48 or frame["speciesKey"].nunique() != 48 or frame["scientific_name"].nunique() != 48:
        raise ValueError("frozen country plan must contain 48 unique taxa")
    if set(frame["country_plan_state"].astype(str)) != {"READY"}:
        raise ValueError("all 48 stage2 country plans must remain READY")
    ids = pd.to_numeric(frame["availability_pair_id"], errors="raise").astype(int)
    if sorted(ids.tolist()) != list(range(1, 49)):
        raise ValueError("availability pair IDs must be exactly 1..48")
    ru_ids = sorted(frame.loc[frame["selected_country_code"].astype(str).str.upper().eq("RU"), "availability_pair_id"].astype(int).tolist())
    if ru_ids != [48]:
        raise ValueError(f"frozen RU pair identity drift: {ru_ids}")
    canonical = _canonical_sha256(frame[[
        "availability_pair_id", "speciesKey", "scientific_name", "country_plan_state",
        "selected_country_code", "historical_selected_country_count",
    ]].to_dict(orient="records"))
    if canonical != EXPECTED_PLAN_CANONICAL_SHA256:
        raise ValueError("frozen country plan canonical content drift")
    return frame.sort_values("availability_pair_id", kind="mergesort").reset_index(drop=True)


def _is_declared_evidence_failure(exc: Exception) -> bool:
    if not isinstance(exc, ValueError):
        return False
    message = str(exc)
    return any(message.startswith(prefix) for prefix in EVIDENCE_FAILURE_PREFIXES)


def freeze_pair(pair_id: int, output: Path) -> dict[str, object]:
    plans = verify_inputs()
    pair_id = int(pair_id)
    if not 1 <= pair_id <= 48:
        raise ValueError("pair id must be in 1..48")
    hit = plans.loc[plans["availability_pair_id"].astype(int).eq(pair_id)]
    if len(hit) != 1:
        raise ValueError(f"expected one frozen row for pair {pair_id}")
    base = hit.iloc[0].to_dict()
    code = str(base["selected_country_code"]).upper()
    if code == "RU":
        raise ValueError("RU pair must use the frozen sharded RU stage3 path")
    key = int(base["speciesKey"])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    # Geometry and historical-provider failures are technical and intentionally
    # propagate rather than being converted to biological/evidence failures.
    geom = fetch_geoboundaries_country_geometry(code)
    geometry_digest = _geometry_digest_from_source_version(geom.source_version)
    try:
        historical = fetch_country_occurrences(key, code)
    except Exception as exc:
        if _is_declared_evidence_failure(exc):
            return _write_sentinel(output, base, geometry_digest, str(exc), historical_rows=0)
        raise
    hist_n = int(len(historical))

    try:
        surface, prototypes, lattice_audit = regional_terrain_inputs(historical, geom)
    except Exception as exc:
        if _is_declared_evidence_failure(exc):
            return _write_sentinel(output, base, geometry_digest, str(exc), historical_rows=hist_n)
        raise

    if len(prototypes) > 32:
        raise ValueError(f"prototype rule drift: expected <=32, got {len(prototypes)}")
    patches, support_audit = validated_robust_candidate_patches(
        surface,
        prototypes,
        feature_columns=ROBUST_TERRAIN_FEATURES,
        area_col="survey_area_id",
    )
    state = "ROBUST_READY_PREHELDOUT" if len(patches) > 0 else "ROBUST_EMPTY"
    patches = patches.copy()
    if not patches.empty:
        patches["availability_pair_id"] = pair_id
        patches["speciesKey"] = key
        patches["scientific_name"] = str(base["scientific_name"])
        patches["taxon_group"] = str(base["taxon_group"])
        patches["framing_country_code"] = code
    surface_path = output / "candidate_surface.parquet"
    patches_path = output / "candidate_patches.csv"
    surface.to_parquet(surface_path, index=False)
    patches.to_csv(patches_path, index=False)
    result = {
        **{k: (v.item() if hasattr(v, "item") else v) for k, v in base.items()},
        "preheldout_availability_state": state,
        "country_geometry_canonical_sha256": geometry_digest,
        "country_geometry_source_id": str(geom.source_id),
        "country_geometry_source_version": str(geom.source_version),
        "historical_training_occurrence_rows": hist_n,
        "regional_tile_count": int(lattice_audit.intersecting_tile_count),
        "geometry_surface_points": int(lattice_audit.total_geometry_points),
        "complete_terrain_surface_points": int(len(surface)),
        "prototype_rows": int(len(prototypes)),
        "candidate_patch_count": int(len(patches)),
        "candidate_surface_sha256": _sha256_file(surface_path),
        "candidate_patches_sha256": _sha256_file(patches_path),
        "support_audit": support_audit.as_dict(),
        "heldout_2021_2025_opened": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "validated_japan_core_changed": False,
    }
    (output / "pair_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return result


def _write_sentinel(output: Path, base: dict[str, object], geometry_digest: str, reason: str, *, historical_rows: int) -> dict[str, object]:
    pd.DataFrame().to_csv(output / "candidate_patches.csv", index=False)
    result = {
        **{k: (v.item() if hasattr(v, "item") else v) for k, v in base.items()},
        "preheldout_availability_state": "SENTINEL_OR_ABSTAIN",
        "country_geometry_canonical_sha256": geometry_digest,
        "historical_training_occurrence_rows": int(historical_rows),
        "regional_tile_count": 0,
        "geometry_surface_points": 0,
        "complete_terrain_surface_points": 0,
        "prototype_rows": 0,
        "candidate_patch_count": 0,
        "evidence_failure_reason": reason,
        "heldout_2021_2025_opened": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "validated_japan_core_changed": False,
    }
    (output / "pair_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = freeze_pair(args.pair_id, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
