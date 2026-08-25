#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from country_framed_integration_v2_pair_core import evaluate_one_v2_core
from country_framed_integration_v2_replication_execution_contract import (
    EXPECTED_EXECUTION_FINGERPRINT,
    execution_contract,
)
from predeclare_country_framed_integration_development_v2 import EXPECTED_PROTOCOL_FINGERPRINT
from predeclare_country_framed_integration_development_v2_replication import (
    EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
    replication_protocol,
)


def evaluate_one_replication(declaration: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    replication_protocol()
    execution_contract()
    results, patches = evaluate_one_v2_core(declaration)
    results = results.copy()
    results["replication_protocol_fingerprint"] = EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT
    results["replication_execution_fingerprint"] = EXPECTED_EXECUTION_FINGERPRINT
    return results, patches


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--declarations", type=Path, required=True)
    p.add_argument("--pair-id", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)

    declarations = pd.read_csv(a.declarations)
    if len(declarations) != 24 or declarations["integration_pair_id"].nunique() != 24:
        raise ValueError("replication must reuse the exact 24 frozen declarations")
    if declarations["speciesKey"].nunique() != 24:
        raise ValueError("replication frozen declarations must contain 24 unique taxa")
    hit = declarations.loc[
        pd.to_numeric(declarations["integration_pair_id"], errors="raise").astype(int) == int(a.pair_id)
    ]
    if len(hit) != 1:
        raise ValueError(f"expected exactly one frozen replication declaration for integration_pair_id={a.pair_id}")

    a.output.mkdir(parents=True, exist_ok=True)
    results, patches = evaluate_one_replication(hit.iloc[0])
    results.to_csv(a.output / "taxon_country_results.csv", index=False)
    patches.to_csv(a.output / "integrated_candidate_patches.csv", index=False)
    manifest = {
        "integration_pair_id": int(a.pair_id),
        "replication_protocol_fingerprint": EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
        "replication_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "authoritative_v2_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "scientific_method_changed": False,
        "cohort_reselected": False,
        "declaration_reselected": False,
        "candidate_generation_preceded_recent_outcome_fetch": True,
    }
    (a.output / "pair_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
