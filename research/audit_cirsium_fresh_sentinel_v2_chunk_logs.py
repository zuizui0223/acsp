#!/usr/bin/env python3
"""Compare frozen GSI chunk and software metadata from two Actions log pairs.

Logs may contain provider internals; ONLY non-coordinate summary evidence is
emitted. This diagnostic cannot identify which raster tile or terrain value
changed. It is not a new selector, exposure of field outcomes or a source fix.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PAIRS = {
    "CIR06": (112881046494, 113079588295),
    "CIR13": (112881046755, 113079588247),
}
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\S+\s+")
EXPECTED_FIELDS = (
    "chunk_index",
    "candidate_rows_input",
    "source_complete_rows",
    "provider_unavailable_rows",
    "terrain_vector_unavailable_rows",
    "gsi_attribution",
    "status",
)
EXPECTED_CHUNK_COUNTS = {"CIR06": 81, "CIR13": 237}


def _strip_timestamp(value: str) -> str:
    return TIMESTAMP.sub("", value)


def _chunk_audits(log: str) -> list[dict[str, Any]]:
    lines = [_strip_timestamp(line) for line in log.splitlines()]
    indices = [i for i, line in enumerate(lines) if '"chunk_audits": [' in line]
    if len(indices) != 1:
        raise ValueError("GSI log must include exactly one printed chunk_audits array")
    start = indices[0]
    end = start + 1
    while end < len(lines) and not re.fullmatch(r"\s*\]\s*,?\s*", lines[end]):
        end += 1
    if end >= len(lines):
        raise ValueError("unterminated GSI chunk_audits array")
    raw = "\n".join(lines[start:end+1])
    raw = raw[raw.index("["):raw.rindex("]") + 1]
    value = json.loads(raw)
    if not isinstance(value, list) or not value:
        raise ValueError("GSI chunk_audits must be nonempty list")
    for i, row in enumerate(value):
        if not isinstance(row, dict) or set(row) != set(EXPECTED_FIELDS):
            raise ValueError(f"chunk audit schema drift at index {i}")
        if row["chunk_index"] != i or row["candidate_rows_input"] <= 0:
            raise ValueError("GSI chunk ordering/denominator drift")
        if (
            row["source_complete_rows"]
            + row["provider_unavailable_rows"]
            + row["terrain_vector_unavailable_rows"]
            != row["candidate_rows_input"]
        ):
            raise ValueError("GSI chunk denominator not preserved")
    return value


def _packages(log: str) -> list[str]:
    lines = [_strip_timestamp(line) for line in log.splitlines()]
    matches = [x.split("Successfully installed ", 1)[1] for x in lines if "Successfully installed " in x]
    if not matches:
        raise ValueError("missing pinned pip installation record")
    return sorted(" ".join(matches).split())


def _runner_image_version(log: str) -> str:
    lines = [_strip_timestamp(line).strip() for line in log.splitlines()]
    for i, line in enumerate(lines):
        if line == "##[group]Runner Image":
            segment = lines[i+1:i+8]
            if "Image: ubuntu-24.04" not in segment:
                raise ValueError("runner image identity changed")
            versions = [x.split("Version: ", 1)[1] for x in segment if x.startswith("Version: ")]
            if len(versions) != 1:
                raise ValueError("cannot uniquely identify GitHub runner image version")
            return versions[0]
    raise ValueError("missing GitHub runner image metadata")


def audit_chunk_log_pairs(paths: dict[str, tuple[Path, Path]]) -> dict[str, Any]:
    if set(paths) != set(PAIRS):
        raise ValueError("chunk replay audit requires exactly CIR06 and CIR13")
    rows: dict[str, Any] = {}
    for unit, (old_path, new_path) in paths.items():
        a = Path(old_path).read_text(encoding="utf-8")
        b = Path(new_path).read_text(encoding="utf-8")
        old = _chunk_audits(a)
        new = _chunk_audits(b)
        if len(old) != EXPECTED_CHUNK_COUNTS[unit] or len(new) != EXPECTED_CHUNK_COUNTS[unit]:
            raise ValueError(f"{unit} frozen chunk count differs")
        matched = sum(oa == nb for oa, nb in zip(old, new))
        pa, pb = _packages(a), _packages(b)
        ia, ib = _runner_image_version(a), _runner_image_version(b)
        rows[unit] = {
            "original_job_id": PAIRS[unit][0],
            "replay_job_id": PAIRS[unit][1],
            "chunk_count": len(old),
            "matching_chunk_audit_count": matched,
            "all_chunk_audits_identical": old == new,
            "installed_package_token_count": len(pa),
            "installed_package_versions_identical": pa == pb,
            "original_runner_image_version": ia,
            "replay_runner_image_version": ib,
            "runner_image_version_identical": ia == ib,
        }
    return {
        "schema_version": "cirsium-fresh-sentinel-v2-gsi-chunk-log-replay-v1",
        "status": "CHUNK_METADATA_REPLAY_IDENTICAL_SOURCE_CONTENT_DRIFT_UNRESOLVED",
        "units": rows,
        "claim_boundary": {
            "all_source_chunk_attributions_and_completion_counts_identical": all(
                v["all_chunk_audits_identical"] for v in rows.values()
            ),
            "software_version_change_explains_drift": False,
            "source_mosaic_bytes_equal_verified": False,
            "source_tile_png_bytes_equal_verified": False,
            "numerical_terrain_values_equal_verified": False,
            "private_site_coordinates_exported": False,
            "prospective_field_outcomes_opened": False,
            "source_drift_mechanism_identified": False,
        },
        "next_gate": (
            "Instrument read-only tile and GSI mosaic content provenance, plus "
            "sampled terrain hashes per chunk. Source/structural-order mismatches "
            "must continue to fail closed under the frozen PR250 input gate."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for unit in PAIRS:
        parser.add_argument(f"--{unit.lower()}-original-log", type=Path, required=True)
        parser.add_argument(f"--{unit.lower()}-replay-log", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    if args.out_json.exists():
        raise SystemExit("refusing to overwrite GSI chunk replay report")
    sources = {
        u: (
            getattr(args, f"{u.lower()}_original_log"),
            getattr(args, f"{u.lower()}_replay_log"),
        )
        for u in PAIRS
    }
    result = audit_chunk_log_pairs(sources)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({u: {"chunks": v["chunk_count"], "matched": v["matching_chunk_audit_count"]} for u, v in result["units"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
