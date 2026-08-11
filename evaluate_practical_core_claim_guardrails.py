#!/usr/bin/env python3
"""Evaluate predeclared claim guardrails after the frozen primary aggregation.

This script does not alter the statistical primary test. It only determines how
far the resulting evidence may be generalized: from the specific predeclared
10-km-mindis GRTS comparator, to the tested GRTS family, and eventually to a
broader existing-tool claim after a separate native biosurvey comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


GUARDRAIL_PATH = Path("validation/acsp_practical_core_claim_guardrail.json")
EXPECTED_GUARDRAIL = "e654d7e0c652effa938f7cd04235156fab9f9c3da2c369200cfa120453eebdfc"
EXPECTED_CORE = "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905"
EXPECTED_PRIMARY_PROTOCOL = "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9"
CORE = "acsp_practical_core"
GRTS_MINDIS = "official_grts_proportional_local_mindis10km"
GRTS_PROP = "official_grts_proportional_local"
GRTS_EQUAL = "official_grts_equal"


def _fingerprint(path: Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("fingerprint", ""))
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if stored != actual or actual != EXPECTED_GUARDRAIL:
        raise ValueError(
            f"claim-guardrail fingerprint mismatch: stored={stored!r}, "
            f"actual={actual!r}, expected={EXPECTED_GUARDRAIL!r}"
        )
    payload["fingerprint"] = stored
    return payload, actual


def _contrast_row(table: pd.DataFrame, method_a: str, method_b: str) -> dict[str, Any]:
    rows = table[
        table["method_a"].astype(str).eq(method_a)
        & table["method_b"].astype(str).eq(method_b)
    ]
    if len(rows) != 1:
        raise ValueError(
            f"expected exactly one contrast row for {method_a} - {method_b}, got {len(rows)}"
        )
    row = rows.iloc[0].to_dict()
    numeric = (
        "pairs",
        "mean_method_a",
        "mean_method_b",
        "mean_difference",
        "bootstrap_95ci_low",
        "bootstrap_95ci_high",
        "sign_flip_p",
        "positive_pairs",
        "negative_pairs",
        "tied_pairs",
        "difference_sd",
    )
    for column in numeric:
        if column in row:
            value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
            row[column] = float(value) if np.isfinite(value) else None
    if row.get("pairs") is not None:
        row["pairs"] = int(round(float(row["pairs"])))
    for column in ("positive_pairs", "negative_pairs", "tied_pairs"):
        if row.get(column) is not None:
            row[column] = int(round(float(row[column])))
    return row


def _primary_rule(row: dict[str, Any], expected_pairs: int = 192) -> bool:
    return bool(
        row.get("pairs") == expected_pairs
        and row.get("mean_difference") is not None
        and row["mean_difference"] >= 0.015
        and row.get("bootstrap_95ci_low") is not None
        and row["bootstrap_95ci_low"] > 0.0
        and row.get("sign_flip_p") is not None
        and row["sign_flip_p"] < 0.05
    )


def _proportional_family_rule(row: dict[str, Any], expected_pairs: int = 192) -> bool:
    return _primary_rule(row, expected_pairs=expected_pairs)


def _equal_family_rule(row: dict[str, Any], expected_pairs: int = 192) -> bool:
    return bool(
        row.get("pairs") == expected_pairs
        and row.get("bootstrap_95ci_low") is not None
        and row["bootstrap_95ci_low"] > 0.0
    )


def run(aggregate_dir: Path, output: Path) -> dict[str, Any]:
    guardrail, guardrail_fp = _fingerprint(GUARDRAIL_PATH)
    if guardrail["practical_core_fingerprint"] != EXPECTED_CORE:
        raise ValueError("claim guardrail points to a different Practical Core")
    if guardrail["statistical_primary_protocol_fingerprint"] != EXPECTED_PRIMARY_PROTOCOL:
        raise ValueError("claim guardrail points to a different primary protocol")
    if guardrail.get("no_retuning_after_outcome") is not True:
        raise ValueError("claim guardrail does not freeze no-retuning behavior")

    primary_gate_path = aggregate_dir / "primary_gate.json"
    inference_path = aggregate_dir / "pair_level_inference.csv"
    manifest_path = aggregate_dir / "confirmation_manifest.json"
    for path in (primary_gate_path, inference_path, manifest_path):
        if not path.exists():
            raise FileNotFoundError(f"required aggregate output missing: {path}")

    primary_gate = json.loads(primary_gate_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inference = pd.read_csv(inference_path)

    if manifest.get("practical_core_fingerprint") != EXPECTED_CORE:
        raise ValueError("aggregate manifest Practical Core fingerprint mismatch")
    if manifest.get("confirmation_protocol_fingerprint") != EXPECTED_PRIMARY_PROTOCOL:
        raise ValueError("aggregate manifest primary protocol fingerprint mismatch")
    if manifest.get("no_retuning_after_outcome") is not True:
        raise ValueError("aggregate manifest no-retuning flag failed")

    mindis = _contrast_row(inference, CORE, GRTS_MINDIS)
    proportional = _contrast_row(inference, CORE, GRTS_PROP)
    equal = _contrast_row(inference, CORE, GRTS_EQUAL)

    primary_pass = _primary_rule(mindis)
    # The primary aggregator must agree exactly with the independently
    # recomputed guardrail rule. A mismatch means the claim audit stops.
    if bool(primary_gate.get("gate_passed")) != primary_pass:
        raise ValueError(
            "primary_gate.json disagrees with independently recomputed claim guardrail"
        )

    proportional_pass = _proportional_family_rule(proportional)
    equal_pass = _equal_family_rule(equal)
    grts_family_pass = bool(primary_pass and proportional_pass and equal_pass)

    if grts_family_pass:
        strongest_same_pool_claim = guardrail["claim_levels"][
            "grts_family_superiority"
        ]["allowed_claim_if_passed"]
    elif primary_pass:
        strongest_same_pool_claim = guardrail["claim_levels"][
            "primary_same_pool_result"
        ]["allowed_claim_if_passed"]
    else:
        strongest_same_pool_claim = (
            "No same-pool superiority claim; report method-specific negative or "
            "equivalent results without retuning."
        )

    result = {
        "status": "claim_guardrails_evaluated",
        "guardrail_fingerprint": guardrail_fp,
        "practical_core_fingerprint": EXPECTED_CORE,
        "statistical_primary_protocol_fingerprint": EXPECTED_PRIMARY_PROTOCOL,
        "primary_same_pool_result": {
            "contrast": mindis,
            "passed": primary_pass,
            "rule": guardrail["claim_levels"]["primary_same_pool_result"]["rule"],
        },
        "grts_family_superiority": {
            "passed": grts_family_pass,
            "required_components": {
                "mindis_primary_passed": primary_pass,
                "proportional_local_no_mindis_passed": proportional_pass,
                "equal_grts_bootstrap_lower_positive": equal_pass,
            },
            "proportional_local_contrast": proportional,
            "equal_contrast": equal,
            "if_failed": guardrail["claim_levels"]["grts_family_superiority"][
                "if_failed"
            ],
        },
        "strongest_allowed_same_pool_claim": strongest_same_pool_claim,
        "existing_tool_superiority": {
            "passed": False,
            "ready_for_separate_biosurvey_gate": grts_family_pass,
            "reason": (
                "A broad existing-tool claim is never granted by this same-pool "
                "analysis alone; the separately frozen native biosurvey end-to-end "
                "gate must also pass."
            ),
            "if_failed_or_not_run": guardrail["claim_levels"][
                "existing_tool_superiority"
            ]["if_failed"],
        },
        "sdm_positioning": guardrail["sdm_positioning"],
        "no_retuning_after_outcome": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--aggregate-dir", type=Path, required=True)
    command.add_argument(
        "--output",
        type=Path,
        default=Path("practical-core-confirmation-aggregate/claim_guardrails.json"),
    )
    return command


if __name__ == "__main__":
    args = parser().parse_args()
    print(json.dumps(run(args.aggregate_dir, args.output), indent=2, ensure_ascii=False))
