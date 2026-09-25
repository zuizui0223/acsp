#!/usr/bin/env python3
"""Build one coordinate-bearing private Cirsium candidate frame before patch freeze.

The builder composes the frozen pipeline:

raw public-layer grid -> G_E graph primitives -> raw adapters -> conjunctive support

It never reads field outcomes, permissions, roads/trails or tissue results. The
coordinate-bearing output is private by construction: the CLI refuses to write it
inside the git repository. Public release happens only through the separate HMAC
patch-freeze generator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acsp.structural_graph import build_structural_graph_primitives
from acsp.structural_raw_adapters import adapt_structural_components
from acsp.structural_selector import _forbidden_outcome_columns
from acsp.structural_support import BASELINE_FAMILY, compose_structural_support

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_VERSION = "cirsium-private-candidate-frame-v1"


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_private_candidate_frame(
    raw: pd.DataFrame,
    *,
    feature_family: str,
    source_manifest: dict[str, Any],
    target_component_id: str | None = None,
    graph_radius_cells: int = 1,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"candidate_cell_id", "latitude", "longitude", "grid_row", "grid_col"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"raw private frame missing required columns: {missing}")
    forbidden = _forbidden_outcome_columns(raw.columns)
    if forbidden:
        raise ValueError(f"field-outcome-like columns are forbidden in private frame generation: {forbidden}")
    if raw.empty:
        raise ValueError("raw private frame cannot be empty")
    if raw["candidate_cell_id"].isna().any() or raw["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be complete and unique")
    if not isinstance(source_manifest, dict) or not source_manifest:
        raise ValueError("non-empty source_manifest is required")
    if source_manifest.get("field_outcomes_opened") not in (False, None):
        raise ValueError("source manifest cannot declare opened field outcomes")

    family = str(feature_family).strip()
    work = raw.copy()
    graph_audit: dict[str, Any] | None = None
    adapter_audit: dict[str, Any] | None = None
    support_audit: dict[str, Any] | None = None

    if family != BASELINE_FAMILY:
        work, graph = build_structural_graph_primitives(
            work,
            feature_family=family,
            target_component_id=target_component_id,
            radius=int(graph_radius_cells),
        )
        work, adapter = adapt_structural_components(work, feature_family=family)
        support, composer = compose_structural_support(work, feature_family=family)
        work["structural_support"] = support
        graph_audit = graph.__dict__.copy()
        adapter_audit = adapter.__dict__.copy()
        support_audit = composer.__dict__.copy()

    provenance_payload = {
        "pipeline_version": PIPELINE_VERSION,
        "feature_family": family,
        "graph_radius_cells": int(graph_radius_cells),
        "target_component_id": target_component_id or "",
        "source_manifest_sha256": _sha256_bytes(_canonical_json_bytes(source_manifest)),
        "contracts": {
            "graph": "cirsium-structural-graph-contract-v1",
            "raw_adapter": "cirsium-structural-raw-adapter-contract-v1",
            "support": "ROW_MIN_CONJUNCTIVE_SUPPORT" if family != BASELINE_FAMILY else "NONE",
        },
    }
    provenance_id = "sha256:" + _sha256_bytes(_canonical_json_bytes(provenance_payload))
    summary = {
        "schema_version": PIPELINE_VERSION,
        "status": "PRIVATE_FRAME_BUILT_PRE_FIELD",
        "feature_family": family,
        "row_count": int(len(work)),
        "support_provenance_id": provenance_id,
        "source_manifest_sha256": provenance_payload["source_manifest_sha256"],
        "graph_radius_cells": int(graph_radius_cells),
        "target_component_id_declared": bool(target_component_id),
        "field_outcomes_opened": False,
        "human_access_used": False,
        "exact_coordinates_public": False,
        "graph_audit": graph_audit,
        "adapter_audit": adapter_audit,
        "support_audit": support_audit,
        "next_gate": "Freeze public HMAC patch tokens before opening any field outcome.",
    }
    return work, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-grid-csv", type=Path, required=True)
    parser.add_argument("--feature-family", required=True)
    parser.add_argument("--source-manifest-json", type=Path, required=True)
    parser.add_argument("--target-component-id")
    parser.add_argument("--graph-radius-cells", type=int, default=1)
    parser.add_argument("--private-out-csv", type=Path, required=True)
    parser.add_argument("--private-summary-json", type=Path, required=True)
    args = parser.parse_args()

    if _inside_repo(args.private_out_csv) or _inside_repo(args.private_summary_json):
        raise SystemExit("refusing to write coordinate-bearing private-frame outputs inside the git repository")

    raw = pd.read_csv(args.raw_grid_csv)
    source_manifest = json.loads(args.source_manifest_json.read_text(encoding="utf-8"))
    built, summary = build_private_candidate_frame(
        raw,
        feature_family=args.feature_family,
        source_manifest=source_manifest,
        target_component_id=args.target_component_id,
        graph_radius_cells=args.graph_radius_cells,
    )
    args.private_out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.private_summary_json.parent.mkdir(parents=True, exist_ok=True)
    built.to_csv(args.private_out_csv, index=False)
    args.private_summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"graph_audit", "adapter_audit", "support_audit"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
