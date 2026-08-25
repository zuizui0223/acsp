#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from country_framed_integration_v2_pair_core import evaluate_one_v2_core
from run_country_framed_integration_development_v2 import EXPECTED_PROTOCOL_FINGERPRINT

ROOT = Path(__file__).resolve().parents[1]
RETRY_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2_timeout_retry_v1.json"
EXPECTED_RETRY_FINGERPRINT = "9ce9411b1d1e837f1276e990a6d4dcfe170c8009a2e9776d4316483c83a220ba"


def _retry_contract() -> dict[str, object]:
    payload = json.loads(RETRY_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("execution_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_RETRY_FINGERPRINT or calculated != EXPECTED_RETRY_FINGERPRINT:
        raise ValueError("v2 timeout-retry execution fingerprint mismatch")
    if payload["authoritative_protocol_fingerprint"] != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("retry no longer targets authoritative v2 protocol")
    if payload["retry_rule"]["scientific_method_changed"] is not False:
        raise ValueError("retry must not change the scientific method")
    payload["execution_fingerprint"] = stored
    return payload


def evaluate_one(declaration: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    retry = _retry_contract()
    results, patches = evaluate_one_v2_core(declaration)
    results = results.copy()
    results["retry_execution_fingerprint"] = str(retry["execution_fingerprint"])
    return results, patches


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--declarations", type=Path, required=True)
    p.add_argument("--pair-id", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    declarations = pd.read_csv(a.declarations)
    if len(declarations) != 24 or declarations["integration_pair_id"].nunique() != 24:
        raise ValueError("retry must reuse the exact 24 frozen declarations")
    hit = declarations.loc[
        pd.to_numeric(declarations["integration_pair_id"], errors="raise").astype(int) == int(a.pair_id)
    ]
    if len(hit) != 1:
        raise ValueError(f"expected exactly one frozen declaration for integration_pair_id={a.pair_id}")
    a.output.mkdir(parents=True, exist_ok=True)
    results, patches = evaluate_one(hit.iloc[0])
    results.to_csv(a.output / "taxon_country_results.csv", index=False)
    patches.to_csv(a.output / "integrated_candidate_patches.csv", index=False)
    manifest = {
        "integration_pair_id": int(a.pair_id),
        "authoritative_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "retry_execution_fingerprint": EXPECTED_RETRY_FINGERPRINT,
        "scientific_method_changed": False,
        "declaration_reselected": False,
    }
    (a.output / "pair_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
