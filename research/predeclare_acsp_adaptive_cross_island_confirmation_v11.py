#!/usr/bin/env python3
"""Bind the post-freeze cross-island cohort sampler to protocol v1/v1.1.

The v1.1 amendment changes only Kumejima -> Iriomote after the v1 sampling-frame
audit drew zero taxa. No selected-taxon occurrence coordinates, ecological
support surfaces, or held-out outcomes were retrieved before the amendment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import predeclare_acsp_adaptive_cross_island_confirmation as sampler

ALLOWED = {
    "acsp-adaptive-survey-cross-island-confirmation-cohort-v1": "b54ddec24993e107a722c1fd345e9e1592c44c87ae9892439756c7da81c2bd6f",
    "acsp-adaptive-survey-cross-island-confirmation-cohort-v1.1": "7bc745ffbcaa23146c56f61e9cf3a1c2ba22bd28cc4ad37468b9b6b726520a65",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.protocol.read_text(encoding="utf-8"))
    protocol_id = str(payload.get("protocol_id", ""))
    if protocol_id not in ALLOWED:
        raise ValueError(f"unsupported cohort protocol id: {protocol_id!r}")
    sampler.EXPECTED = ALLOWED[protocol_id]
    print(json.dumps(sampler.run(args.protocol, args.output), indent=2))


if __name__ == "__main__":
    main()
