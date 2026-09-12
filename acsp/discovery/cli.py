"""Command-line entry point for the experimental, fail-closed discovery workflow."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

from .broad_frames import attach_nearest_anchor_distance, build_rectangular_candidate_frame
from .component_workflow import prepare_worldcover_component_partition
from .families import list_structural_families
from .frames import AnnularFrameSpec, build_annular_candidate_frame
from .providers import fetch_gbif_occurrence_evidence
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
        raise SystemExit("--context-note is required for explicit LOCAL/DETACHED/SENTINEL runs; describe the source-backed ecological/range/component justification")
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
        "sources": [{
            "provider_id": "USER_FILE", "layer_role": "candidate_frame", "release_id": "user-supplied",
            "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source_uri": candidate_frame_path.name, "sha256": _sha256(candidate_frame_path),
        }],
    }


def command_fetch_gbif(args: argparse.Namespace) -> int:
    frame, audit = fetch_gbif_occurrence_evidence(
        args.scientific_name, country=args.country, year_from=args.year_from, year_to=args.year_to, maximum_records=int(args.max_records)
    )
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True); frame.to_csv(out, index=False)
    audit_path = Path(args.audit_json) if args.audit_json else out.with_suffix(out.suffix + ".audit.json")
    _write_json(audit_path, audit.as_dict())
    print(json.dumps({"status": "GBIF_OCCURRENCE_EVIDENCE_WRITTEN", "rows": len(frame), "out": str(out), "audit": str(audit_path), **audit.as_dict()}, ensure_ascii=False, indent=2))
    return 0


def command_families(_args: argparse.Namespace) -> int:
    rows = [{"family_id": family.family_id, "label": family.label, "ecological_question": family.ecological_question, "required_raw_columns": list(family.required_raw_columns), "source_roles": list(family.source_roles), "notes": family.notes} for family in list_structural_families()]
    print(json.dumps(rows, ensure_ascii=False, indent=2)); return 0


def command_template(args: argparse.Namespace) -> int:
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"occurrence_id": "example-1", "latitude": 35.0, "longitude": 139.0, "event_year": 2024, "coordinate_uncertainty_m": 100.0, "provider_id": "YOUR_PROVIDER"},
        {"occurrence_id": "example-2", "latitude": 35.01, "longitude": 139.01, "event_year": 2025, "coordinate_uncertainty_m": 250.0, "provider_id": "YOUR_PROVIDER"},
    ]).to_csv(out / "occurrences.csv", index=False)
    pd.DataFrame([
        {"candidate_cell_id": "cell-1", "latitude": 35.005, "longitude": 139.005, "grid_row": 0, "grid_col": 0, "nearest_anchor_km": 0.8},
        {"candidate_cell_id": "cell-2", "latitude": 35.015, "longitude": 139.015, "grid_row": 0, "grid_col": 1, "nearest_anchor_km": 1.4},
    ]).to_csv(out / "candidate_frame.csv", index=False)
    _write_json(out / "source_manifest.json", {"schema_version": "acsp-discovery-source-manifest-v1", "sources": [{"provider_id": "YOUR_PROVIDER", "layer_role": "candidate_frame", "release_id": "YOUR_RELEASE", "retrieved_at": "2026-01-01T00:00:00+00:00", "source_uri": "YOUR_SOURCE_URI", "sha256": "0" * 64}]})
    (out / "README.txt").write_text(
        "Optional: acsp-discovery fetch-gbif 'Species name' --country JP --out occurrences.csv\n"
        "1) acsp-discovery assess occurrences.csv --out-dir assessment\n"
        "2) Build a declared frame: acsp-discovery build-frame local --anchors assessment/population_anchors.csv --outer-radius-km 5 --out candidate_frame.csv\n"
        "   or: acsp-discovery build-frame broad --bounds WEST SOUTH EAST NORTH --anchors assessment/population_anchors.csv --out broad_frame.csv\n"
        "3) For a broad terrestrial frame: acsp-discovery prepare-components --candidate-frame broad_frame.csv --anchors assessment/population_anchors.csv --out-dir components\n"
        "4) Explicit --regime local/detached/sentinel requires --context-note.\n"
        "5) Structural runs require a real source manifest; `acsp-discovery families` shows required raw columns.\n",
        encoding="utf-8",
    )
    print(str(out)); return 0


def command_build_frame(args: argparse.Namespace) -> int:
    mode = str(args.frame_mode)
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    audit_path = Path(args.audit_json) if args.audit_json else out.with_suffix(out.suffix + ".audit.json")
    anchors = pd.read_csv(args.anchors) if args.anchors else None
    technical_default_used = args.grid_spacing_m is None
    if mode == "local":
        if anchors is None or anchors.empty:
            raise SystemExit("LOCAL frame requires --anchors from an assessed/frozen population evidence table")
        if args.outer_radius_km is None:
            raise SystemExit("LOCAL frame requires explicit --outer-radius-km; ACSP does not infer a universal local radius")
        spacing = float(args.grid_spacing_m if args.grid_spacing_m is not None else 100.0)
        frame, audit = build_annular_candidate_frame(
            anchors,
            spec=AnnularFrameSpec(
                grid_spacing_m=spacing,
                known_exclusion_km=float(args.known_exclusion_km),
                outer_radius_km=float(args.outer_radius_km),
            ),
            candidate_id_prefix=str(args.candidate_id_prefix),
        )
        payload = {
            "schema_version": "acsp-discovery-frame-build-v1", "status": "DECLARED_LOCAL_FRAME_BUILT",
            "mode": "local", "technical_grid_default_used": technical_default_used,
            "scientific_radius_user_declared": True, "audit": asdict(audit),
            "warning": "The declared outer radius is not validated by this command and must come from a source-backed study contract/context."
        }
    elif mode == "broad":
        if not args.bounds or len(args.bounds) != 4:
            raise SystemExit("BROAD frame requires explicit --bounds WEST SOUTH EAST NORTH")
        spacing = float(args.grid_spacing_m if args.grid_spacing_m is not None else 250.0)
        frame, audit = build_rectangular_candidate_frame(tuple(map(float, args.bounds)), grid_spacing_m=spacing, candidate_id_prefix=str(args.candidate_id_prefix))
        if anchors is not None and not anchors.empty:
            frame = attach_nearest_anchor_distance(frame, anchors)
        payload = {
            "schema_version": "acsp-discovery-frame-build-v1", "status": "DECLARED_BROAD_FRAME_BUILT",
            "mode": "broad", "technical_grid_default_used": technical_default_used,
            "geographic_bounds_user_declared": True, "nearest_anchor_distance_attached": bool(anchors is not None and not anchors.empty),
            "audit": asdict(audit),
            "warning": "BROAD bounds are an external geographic contract, not a range inferred from held-out outcomes."
        }
    else:
        raise SystemExit(f"unknown frame mode: {mode}")
    frame.to_csv(out, index=False); _write_json(audit_path, payload)
    print(json.dumps({**payload, "out": str(out), "audit_json": str(audit_path), "candidate_count": len(frame)}, ensure_ascii=False, indent=2))
    return 0


def command_prepare_components(args: argparse.Namespace) -> int:
    candidate = pd.read_csv(args.candidate_frame)
    anchors = pd.read_csv(args.anchors)
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    snapshot = out / "worldcover_component_snapshot.tif"
    all_land, anchored, other, audit = prepare_worldcover_component_partition(
        candidate,
        anchors,
        snapshot_path=snapshot,
        crop_margin_m=float(args.crop_margin_m),
    )
    all_land.to_csv(out / "candidate_components_all_land.csv", index=False)
    anchored.to_csv(out / "candidate_components_anchored.csv", index=False)
    other.to_csv(out / "candidate_components_other.csv", index=False)
    _write_json(out / "component_audit.json", audit.as_dict())
    _write_json(out / "source_manifest.json", audit.source_manifest)
    payload = {
        "status": audit.status,
        "out_dir": str(out),
        "land_candidate_count": audit.land_candidate_count,
        "anchored_candidate_count": audit.anchored_candidate_count,
        "other_component_candidate_count": audit.other_component_candidate_count,
        "anchored_component_ids": list(audit.anchored_component_ids),
        "warning": "WorldCover land components are source-backed physical components, not proof that every unanchored component is suitable habitat."
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2)); return 0


def command_assess(args: argparse.Namespace) -> int:
    assessment, medoids = assess_occurrence_evidence(pd.read_csv(args.occurrences), context=_context_from_args(args), policy=_policy_from_args(args))
    payload = _assessment_payload(assessment, args); print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out_dir:
        out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True); _write_json(out / "assessment.json", payload); medoids.to_csv(out / "population_anchors.csv", index=False)
    return 0


def command_run(args: argparse.Namespace) -> int:
    occurrences_path, candidate_path = Path(args.occurrences), Path(args.candidate_frame)
    assessment, medoids = assess_occurrence_evidence(pd.read_csv(occurrences_path), context=_context_from_args(args), policy=_policy_from_args(args))
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    assessment_payload = _assessment_payload(assessment, args); _write_json(out / "assessment.json", assessment_payload); medoids.to_csv(out / "population_anchors.csv", index=False)
    if assessment.regime == "ABSTAIN_LOCAL_PATCH": print(json.dumps(assessment_payload, ensure_ascii=False, indent=2)); return 2
    candidate = pd.read_csv(candidate_path); feature_family = str(args.feature_family or "").strip()
    if args.source_manifest: manifest = _read_json(Path(args.source_manifest))
    elif feature_family: raise SystemExit("--source-manifest is required for structural ranking so ecological source provenance is not lost")
    else: manifest = _auto_candidate_manifest(candidate_path)
    rankings, audit = rank_discovery_frame(candidate, assessment=assessment, source_manifest=manifest, feature_family=feature_family or None, target_component_id=str(args.target_component_id or "").strip() or None, graph_radius_cells=int(args.graph_radius_cells))
    ranking_payload = audit.as_dict(); ranking_payload["declared_context_note"] = _declared_context_note(args); _write_json(out / "ranking_audit.json", ranking_payload)
    summarize_rankings(rankings).to_csv(out / "ranking_summary.csv", index=False)
    for method, frame in rankings.items(): frame.to_csv(out / f"ranking_{method.lower().replace('/', '_')}.csv", index=False)
    print(json.dumps({"status": audit.status, "regime": audit.regime, "methods": list(audit.methods), "out_dir": str(out), "warning": "Development-only: rankings are not occupancy probabilities, field-efficiency estimates, or optimal budgets."}, ensure_ascii=False, indent=2)); return 0


def _add_evidence_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--regime", choices=("auto", "local", "detached", "sentinel"), default="auto")
    parser.add_argument("--context-note", default="", help="Required for explicit non-auto regime; cite/describe the ecological/range justification.")
    parser.add_argument("--sentinel-subregime", default=""); parser.add_argument("--max-anchor-uncertainty-m", type=float, default=1000.0); parser.add_argument("--population-cluster-radius-km", type=float, default=0.5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acsp-discovery", description="Experimental fail-closed next-observation discovery workflow."); sub = parser.add_subparsers(dest="command", required=True)
    p_fetch = sub.add_parser("fetch-gbif", help="Fetch provider-neutral occurrence evidence from GBIF using a species name."); p_fetch.add_argument("scientific_name"); p_fetch.add_argument("--country", default=""); p_fetch.add_argument("--year-from", type=int); p_fetch.add_argument("--year-to", type=int); p_fetch.add_argument("--max-records", type=int, default=10000); p_fetch.add_argument("--out", required=True); p_fetch.add_argument("--audit-json"); p_fetch.set_defaults(func=command_fetch_gbif)
    p_families = sub.add_parser("families", help="List structural families and required provider inputs."); p_families.set_defaults(func=command_families)
    p_template = sub.add_parser("template", help="Create minimal CSV/JSON templates for a first run."); p_template.add_argument("--out-dir", default="acsp-discovery-template"); p_template.set_defaults(func=command_template)
    p_frame = sub.add_parser("build-frame", help="Build an explicit LOCAL or BROAD candidate frame without inferring biological extent."); frame_sub = p_frame.add_subparsers(dest="frame_mode", required=True)
    p_local = frame_sub.add_parser("local", help="Build an annular local frame around population anchors; outer radius is required."); p_local.add_argument("--anchors", required=True); p_local.add_argument("--outer-radius-km", type=float, required=True); p_local.add_argument("--known-exclusion-km", type=float, default=0.5); p_local.add_argument("--grid-spacing-m", type=float); p_local.add_argument("--candidate-id-prefix", default="local"); p_local.add_argument("--out", required=True); p_local.add_argument("--audit-json"); p_local.set_defaults(func=command_build_frame)
    p_broad = frame_sub.add_parser("broad", help="Build a declared rectangular broad frame; bounds are required."); p_broad.add_argument("--bounds", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"), required=True); p_broad.add_argument("--anchors"); p_broad.add_argument("--grid-spacing-m", type=float); p_broad.add_argument("--candidate-id-prefix", default="broad"); p_broad.add_argument("--out", required=True); p_broad.add_argument("--audit-json"); p_broad.set_defaults(func=command_build_frame)
    p_components = sub.add_parser("prepare-components", help="Fetch WorldCover and split a declared broad frame into anchored versus other physical land components."); p_components.add_argument("--candidate-frame", required=True); p_components.add_argument("--anchors", required=True); p_components.add_argument("--crop-margin-m", type=float, default=3000.0); p_components.add_argument("--out-dir", required=True); p_components.set_defaults(func=command_prepare_components)
    p_assess = sub.add_parser("assess", help="Audit occurrence evidence and resolve LOCAL/DETACHED/SENTINEL/ABSTAIN."); p_assess.add_argument("occurrences"); p_assess.add_argument("--out-dir"); _add_evidence_args(p_assess); p_assess.set_defaults(func=command_assess)
    p_run = sub.add_parser("run", help="Assess evidence and rank one already frozen candidate frame."); p_run.add_argument("--occurrences", required=True); p_run.add_argument("--candidate-frame", required=True); p_run.add_argument("--source-manifest"); p_run.add_argument("--feature-family"); p_run.add_argument("--target-component-id"); p_run.add_argument("--graph-radius-cells", type=int, default=1); p_run.add_argument("--out-dir", required=True); _add_evidence_args(p_run); p_run.set_defaults(func=command_run)
    return parser


def main() -> int:
    args = build_parser().parse_args(); return int(args.func(args))


if __name__ == "__main__": raise SystemExit(main())
