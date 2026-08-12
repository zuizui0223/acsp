#!/usr/bin/env python3
"""Aggregate the corrected 72-pair rescue versus official GRTS v2 development gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import aggregate_practical_rescue_grts_development as base

EXPECTED_PROTOCOL = "74fec14b44035e897072b022d82ea30c00b27ce1bb95c16a0e9a5578a3d3da7a"


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-root", type=Path, required=True)
    command.add_argument(
        "--protocol",
        dest="protocol_path",
        type=Path,
        default=Path("validation/acsp_practical_rescue_grts_development_protocol_v2.json"),
    )
    command.add_argument("--output", type=Path, required=True)
    return command


def run(pair_root: Path, protocol_path: Path, output: Path):
    # Avoid mutating the retained v1 aggregate contract merely by importing this
    # wrapper; bind corrected-v2 identity only for the aggregate invocation.
    original = base.EXPECTED_PROTOCOL
    try:
        base.EXPECTED_PROTOCOL = EXPECTED_PROTOCOL
        return base.run(pair_root, protocol_path, output)
    finally:
        base.EXPECTED_PROTOCOL = original


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
