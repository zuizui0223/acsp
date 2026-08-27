#!/usr/bin/env python3
"""Compare a freshly inspected pinned-provider report to the frozen registry."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from geoboundaries_v6_coverage_contract import load_contract


def _sha256_json(payload: object) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def verify(live: dict[str, object]) -> None:
    frozen = load_contract()
    live_provider = live["provider"]
    frozen_provider = frozen["provider"]
    for key in (
        "repository",
        "release_tag",
        "release_commit",
        "source_family",
        "gbopen_tree_sha",
        "open_metadata_blob_sha",
        "required_geometry_template",
    ):
        if live_provider[key] != frozen_provider[key]:
            raise ValueError(f"live provider provenance drifted: {key}")

    live_coverage = live["coverage"]
    frozen_coverage = frozen["coverage"]
    exact_keys = (
        "provider_root_directory_count",
        "simplified_adm0_count",
        "metadata_adm0_count",
        "iso_mapping_alpha3_count",
        "supported_alpha3",
        "unsupported_iso_alpha2_alpha3",
        "provider_only_alpha3",
        "root_without_simplified_adm0",
        "metadata_adm0_without_simplified_geometry",
        "simplified_geometry_without_adm0_metadata",
    )
    for key in exact_keys:
        if live_coverage[key] != frozen_coverage[key]:
            raise ValueError(f"live provider coverage drifted: {key}")

    blob_map_digest = _sha256_json(live_coverage["simplified_adm0_blob_sha_by_alpha3"])
    if blob_map_digest != frozen_coverage["simplified_adm0_blob_map_sha256"]:
        raise ValueError("live simplified ADM0 blob-map digest drifted")

    live_inputs = live["development_inputs"]
    for key in (
        "fresh_taxon_identities_opened",
        "historical_focal_species_facets_opened",
        "heldout_2021_2025_opened",
        "candidate_or_recall_outcomes_opened",
    ):
        if live_inputs[key] is not False:
            raise ValueError(f"forbidden live development input opened: {key}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = json.loads(args.live.read_text(encoding="utf-8"))
    verify(payload)
    print("pinned geoBoundaries v6 ADM0 coverage registry matches the exact upstream tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
