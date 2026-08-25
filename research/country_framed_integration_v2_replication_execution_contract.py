#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2_replication_execution_v1.json"
EXPECTED_EXECUTION_FINGERPRINT = "408acbf32ab2cb2d9d4ee802f599aa425185a6cf82c956173f4f53a1089fc63e"


def execution_contract() -> dict[str, object]:
    payload = json.loads(EXECUTION_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("execution_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_EXECUTION_FINGERPRINT or calculated != EXPECTED_EXECUTION_FINGERPRINT:
        raise ValueError("v2 replication execution fingerprint mismatch")
    decomposition = payload["execution_decomposition"]
    if decomposition["scientific_method_changed"] is not False:
        raise ValueError("replication execution must not change scientific method")
    if decomposition["pair_shard_count"] != 24 or decomposition["pair_ids"] != list(range(1, 25)):
        raise ValueError("replication execution pair decomposition drifted")
    if decomposition["identity_freeze_first"] is not True or decomposition["same_frozen_declarations_artifact"] is not True:
        raise ValueError("replication execution must freeze identities before evaluation")
    if payload["failure_semantics"]["retuning_on_replication_taxa_allowed"] is not False:
        raise ValueError("replication retuning must remain forbidden")
    payload["execution_fingerprint"] = stored
    return payload
