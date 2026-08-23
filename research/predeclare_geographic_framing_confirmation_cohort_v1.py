#!/usr/bin/env python3
"""Predeclare the fresh 96-taxon geographic-framing confirmation cohort.

This wrapper reuses the existing taxonomy-safe factorial identity sampler only.
Every v3 and v4 framing-development taxon is excluded by committed identity
files before sampling. No focal occurrence rows or temporal country outcomes
are fetched for selected taxa during declaration.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import predeclare_robust_patch_confirmation_cohort as base

PROTOCOL = Path("validation/acsp_geographic_framing_confirmation_protocol_v1.json")
EXPECTED_PROTOCOL = "9f655f6121f1c917659dcf85ba039304b645ea88b5afff8d7855a11cf1e7a490"


def run(output: Path) -> dict[str, object]:
    previous = base.EXPECTED_PROTOCOL
    try:
        base.EXPECTED_PROTOCOL = EXPECTED_PROTOCOL
        result = base.run(PROTOCOL, output)
    finally:
        base.EXPECTED_PROTOCOL = previous
    result = {
        **result,
        "purpose": "geographic_framing_country_registry_fresh_confirmation_v1",
        "development_v3_taxa_excluded": True,
        "development_v4_taxa_excluded": True,
        "temporal_country_outcomes_inspected": False,
        "fresh_confirmation_cohort": True,
        "confirmation_outcomes_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "taxon_replacement_after_declaration_allowed": False,
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
