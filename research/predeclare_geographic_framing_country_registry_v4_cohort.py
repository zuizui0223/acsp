#!/usr/bin/env python3
"""Predeclare the disjoint 96-taxon development cohort for framing v4.

The sampler reuses the existing taxonomy-safe factorial identity sampler only.
The previous 96 framing-development taxa are supplied as an immutable runtime
exclusion file before sampling.  No focal occurrence rows or temporal country
facets are fetched for selected taxa during declaration.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import predeclare_robust_patch_confirmation_cohort as base

PROTOCOL_V4 = Path("validation/acsp_geographic_framing_development_protocol_v4.json")
EXPECTED_PROTOCOL_V4 = "3bd9e6145e17a99b52d8a9f82c07f346541f56a2bf81bd768e180de78c295bf8"


def run(output: Path) -> dict[str, object]:
    previous = base.EXPECTED_PROTOCOL
    try:
        base.EXPECTED_PROTOCOL = EXPECTED_PROTOCOL_V4
        result = base.run(PROTOCOL_V4, output)
    finally:
        base.EXPECTED_PROTOCOL = previous
    result = {
        **result,
        "purpose": "geographic_framing_v4_development_only",
        "previous_96_taxa_excluded": True,
        "temporal_country_outcomes_inspected": False,
        "fresh_confirmation_cohort": False,
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
