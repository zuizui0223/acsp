#!/usr/bin/env python3
"""Predeclare the taxonomy-safe v2 untouched robust-patch confirmation cohort.

This wrapper preserves the archived v1 sampler and changes only the frozen
protocol fingerprint/path used for the new confirmation declaration. It still
samples taxon-region identities only and does not fetch focal occurrences,
generate candidate patches, calculate robust support, or inspect held-out
outcomes.
"""
from __future__ import annotations

import json
from pathlib import Path

import predeclare_robust_patch_confirmation_cohort as base

EXPECTED_PROTOCOL_V2 = "68f94dbb5ad9cd6ec433653df83df323a7fc489b1ef8ded2422bd8520b0f71e6"
PROTOCOL_V2 = Path("validation/acsp_robust_patch_untouched_confirmation_protocol_v2.json")


def run(output: Path) -> dict[str, object]:
    previous = base.EXPECTED_PROTOCOL
    try:
        base.EXPECTED_PROTOCOL = EXPECTED_PROTOCOL_V2
        return base.run(PROTOCOL_V2, output)
    finally:
        base.EXPECTED_PROTOCOL = previous


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2, ensure_ascii=False))
