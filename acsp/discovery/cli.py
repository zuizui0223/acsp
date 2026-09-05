"""Command-line entry point for the experimental, fail-closed discovery workflow."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

from .families import list_structural_families
from .workflow import DiscoveryContext, EvidencePolicy, assess_occurrence_evidence, rank_discovery_frame, summarize_rankings


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _declared_context_note(args: argparse.Namespace) -> str:
    regime = str(getattr(args, "regime", "auto") or "auto").lower()
    note = str(getattr(args, "context_note", "") or "").strip()
    if regime != "auto" and not note:
        raise SystemExit(
            "--context-note is required for explicit LOCAL/DETACHED/SENTINEL runs; describe the source-backed ecological/range/component justification"
        )
    return note


def _context_from_args(args: argparse.Namespace) -> DiscoveryContext:
    regime = str(getattr(args, "regime", "auto") or "auto").lower()
    _declared_context_note(args)
    if regime == "auto":
        return DiscoveryContext()
    if regime == "local":
        return DiscoveryContext(local_component_justified=True)
    if regime == "detached":
        return DiscoveryContext(detached_component_available=True)
    if regime == "sentinel":
        subregime = str(getattr(args, "sentinel_subregime", "") or "").strip()
        if not subregime:
            raise SystemExit("--sentinel-subregime is required when --regime sentinel")
        return DiscoveryContext(sentinel_context_available=True, sentinel_subregime=subregime)
    raise SystemExit(f"unknown regime: {regime}")


def _policy_from_args(args: argparse.Namespace) -> EvidencePolicy:
    return EvidencePolicy(
        exact_anchor_max_uncertainty_m=float(args.max_anchor_uncertainty_m),
        population_cluster_radius_km=float(args.population_cluster_radius_km),
        require_declared_uncertainty_for_exact_anchor=True,
    )


def _assessment_payload(assessment, args: argparse.Namespace) -> dict:
    payload = assessment.as_dict()
    payload["declared_regime_input"] = str(getattr(args, "regime", "auto") or "auto")
    payload["declared_context_note"] = _declared_context_note(args)
    return payload


def _auto_candidate_manifest(candidate_frame_path: Path) -> dict:
    return {
        "schema_version": "acsp-discovery-user-candidate-frame-v1",
        "sources": [
            {
                "provider_id": "USER_FILE",
                "layer_role": "candidate_frame",
                "release_id": "user-supplied",
                "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "source_uri": candidate_frame_path.name,
                "sha256": _sha256(candidate_frame_path),
            }
        ],
    }


def command_families(_args: argparse.Namespace) -> int:
    rows = [
        {
            "family_id": family.family_id,
            "label": family.label,
            "ecological_question": family.ecological_question,
            "required_raw_columns": list(family.required_raw_columns),
            "source_roles": list(family.source_roles),
            "notes": family.notes,
        }
        for family in list_structural_families()
    ]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def command_template(args: argparse.Namespace) -> int:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"occurrence_id": "example-1", "latitude": 35.0, "longitude": 139.0, "event_year": 2024, "coordinate_uncertainty_m": 100.0, "provider_id": "YOUR_PROVIDER"},
            {"occurrence_id": "example-2", "latitude": 35.01, "longitude": 139.01, "event_year": 2025, "coordinate_uncertainty_m": 250.0, "provider_id": "YOUR_PROVIDER"},
        ]
    ).to_csv(out / "occurrences.csv", index=False)
    pd.DataFrame(
        [
            {"candidate_cell_id": "cell-1", "latitude": 35.005, "longitude": 139.005, "grid_row": 0, "grid_col": 0, "nearest_anchor_km": 0.8},
            {"candidate_cell_id": "cell-2", "latitude": 35.015, "longitude": 139.015, "grid_row": 0, "grid_col": 1, "nearest_anchor_km": 1.4},
        ]
    ).to_csv(out / "candidate_frame.csv", index=False)
    _write_json(
        out / "source_manifest.json",
        {
            "schema_version": "acsp-discovery-source-manifest-v1",
            "sources": [
                {"provider_id": "YOUR_PROVIDER", "layer_role": "candidate_frame", "release_id": "YOUR_RELEASE", "retrieved_at": "2026-01-01T00:00:00+00:00", "source_uri": "YOUR_SOURCE_URI", "sha256": "0" * 64}
            ],
        },
    )
    (out / "README.txt").write_text(
        "1) Replace example occurrence rows with your data.\n"
        "2) Run: acsp-discovery assess occurrences.csv\n"
        "3) If a source-backed regime is justified, prepare/freeze a candidate frame.\n"
        "4) Explicit --regime local/detached/sentinel requires --context-note.\n"
        "5) Structural runs require a real source_manifest.json and `acsp-discovery families` shows required raw columns.\n",
        encoding="utf-8",
    )
    print(str(out))
    return 0


def command_assess(args: argparse.Namespace) -> int:
    occurrences = pd.read_csv(args.occurrences)
    assessment, medoids = assess_occurrence_evidence(occurrences, context=_context_from_args(args), policy=_policy_from_args(args))
    payload = _assessment_payload(assessment, args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        _write_json(out / "assessment.json", payload)
        medoids.to_csv(out / "population_anchors.csv", index=False)
    return 0


def command_run(args: argparse.Namespace) -> int:
    occurrences_path = Path(args.occurrences)
    candidate_path = Path(args.candidate_frame)
    assessment, medoids = assess_occurrence_evidence(
        pd.read_csv(occurrences_path), context=_context_from_args(args), policy=_policy_from_args(args)
    )
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    assessment_payload = _assessment_payload(assessment, args)
    _write_json(out / "assessment.json", assessment_payload)
    medoids.to_csv(out / "population_anchors.csv", index=False)
    if assessment.regime == "ABSTAIN_LOCAL_PATCH":
        print(json.dumps(assessment_payload, ensure_ascii=False, indent=2))
        return 2

    candidate = pd.read_csv(candidate_path)
    feature_family = str(args.feature_family or "").strip()
    if args.source_manifest:
        manifest = _read_json(Path(args.source_manifest))
    elif feature_family:
        raise SystemExit("--source-manifest is required for structural ranking so ecological source provenance is not lost")
    else:
        manifest = _auto_candidate_manifest(candidate_path)

    rankings, audit = rank_discovery_frame(
        candidate,
        assessment=assessment,
        source_manifest=manifest,
        feature_family=feature_family or None,
        target_component_id=str(args.target_component_id or "").strip() or None,
        graph_radius_cells=int(args.graph_radius_cells),
    )
    ranking_payload = audit.as_dict()
    ranking_payload["declared_context_note"] = _declared_context_note(args)
    _write_json(out / "ranking_audit.json", ranking_payload)
    summarize_rankings(rankings).to_csv(out / "ranking_summary.csv", index=False)
    for method, frame in rankings.items():
        frame.to_csv(out / f"ranking_{method.lower().replace('/', '_')}.csv", index=False)
    print(
        json.dumps(
            {
                "status": audit.status,
                "regime": audit.regime,
                "methods": list(audit.methods),
                "out_dir": str(out),
                "warning": "Development-only: rankings are not occupancy probabilities, field-efficiency estimates, or optimal budgets.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _add_evidence_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--regime", choices=("auto", "local", "detached", "sentinel"), default="auto")
    parser.add_argument("--context-note", default="", help="Required for an explicit non-auto regime; cite/describe the ecological or range justification.")
    parser.add_argument("--sentinel-subregime", default="")
    parser.add_argument("--max-anchor-uncertainty-m", type=float, default=1000.0)
    parser.add_argument("--population-cluster-radius-km", type=float, default=0.5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acsp-discovery", description="Experimental fail-closed next-observation discovery workflow.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_families = sub.add_parser("families", help="List structural families and required provider inputs.")
    p_families.set_defaults(func=command_families)
    p_template = sub.add_parser("template", help="Create minimal CSV/JSON templates for a first run.")
    p_template.add_argument("--out-dir", default="acsp-discovery-template")
    p_template.set_defaults(func=command_template)
    p_assess = sub.add_parser("assess", help="Audit occurrence evidence and resolve LOCAL/DETACHED/SENTINEL/ABSTAIN.")
    p_assess.add_argument("occurrences")
    p_assess.add_argument("--out-dir")
    _add_evidence_args(p_assess)
    p_assess.set_defaults(func=command_assess)
    p_run = sub.add_parser("run", help="Assess evidence and rank one already frozen candidate frame.")
    p_run.add_argument("--occurrences", required=True)
    p_run.add_argument("--candidate-frame", required=True)
    p_run.add_argument("--source-manifest")
    p_run.add_argument("--feature-family")
    p_run.add_argument("--target-component-id", help="Required for COASTAL_ISLAND_STRUCTURE and other component-specific recipes.")
    p_run.add_argument("--graph-radius-cells", type=int, default=1)
    p_run.add_argument("--out-dir", required=True)
    _add_evidence_args(p_run)
    p_run.set_defaults(func=command_run)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
