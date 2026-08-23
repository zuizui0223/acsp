#!/usr/bin/env python3
"""Evaluate predeclared higher-taxon geographic framing v2.

The already-opened 96 taxa remain development-only.  For each taxon-region pair
one non-focal higher-taxon prior snapshot is fetched once, persisted, and reused
unchanged across all five focal held-out folds.  Candidate generation and robust
support are not run unless the predeclared framing gate is passed in a later
step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from evaluate_geographic_framing_development_v1 import (
    _frames_area_km2,
    _heldout_containment,
    _snapshot_fingerprint,
    _spherical_rect_area_km2,
)
from geographic_framing_higher_taxon_v2 import (
    DEFAULT_PRIOR_RECORD_CAP,
    fetch_nonfocal_higher_taxon_prior,
    infer_higher_taxon_prior_frames,
)

PROTOCOL_PATH = Path("validation/acsp_geographic_framing_development_protocol_v2.json")
EXPECTED_PROTOCOL = "5f77d4e0d33fec794ce85c666a6bfafbe029f0ed001ab2644eb2e64eceb35f5f"


def _protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_PROTOCOL or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"v2 framing protocol fingerprint mismatch: file={stored}, calculated={calculated}, expected={EXPECTED_PROTOCOL}"
        )
    payload["protocol_fingerprint"] = stored
    return payload


def _manifest(fold_dir: Path) -> dict[str, object]:
    payload = json.loads((fold_dir / "fold_manifest.json").read_text(encoding="utf-8"))
    provenance = payload.get("provenance") or {}
    return {
        "pair_id": int(provenance["pair_id"]),
        "repeat": int(payload["repeat"]),
        "scientific_name": str(provenance["scientific_name"]),
        "species_key": int(provenance["species_key"]),
        "taxon_group": str(provenance["taxon_group"]),
        "region_name": str(provenance["region_name"]),
        "geographic_stratum": str(provenance["geographic_stratum"]),
        "fold_status": str(payload.get("status") or "unknown"),
        "fold_failure_reason": str(payload.get("failure_reason") or ""),
        "west": float(provenance["west"]),
        "south": float(provenance["south"]),
        "east": float(provenance["east"]),
        "north": float(provenance["north"]),
    }


def _zero_row(
    meta: dict[str, object],
    reason: str,
    *,
    prior_status: str = "not_attempted",
    prior_rank_used: str = "",
    prior_record_count: int = 0,
) -> dict[str, object]:
    fixed_area = _spherical_rect_area_km2(
        float(meta["west"]), float(meta["south"]), float(meta["east"]), float(meta["north"])
    )
    return {
        **meta,
        "heldout_records": 0,
        "heldout_inside_frames": 0,
        "heldout_frame_containment": 0.0,
        "frame_count": 0,
        "initial_component_count": 0,
        "occupied_block_count": 0,
        "prior_status": str(prior_status),
        "prior_rank_used": str(prior_rank_used),
        "prior_record_count": int(prior_record_count),
        "inferred_frame_area_km2": 0.0,
        "fixed_region_area_km2": float(fixed_area),
        "frame_area_ratio_to_fixed": 0.0,
        "framing_status": "failed_retained_as_zero",
        "failure_reason": str(reason),
    }


def _prior_snapshot_fingerprint(points: pd.DataFrame, audits: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for frame in (points, audits):
        canonical = frame.copy()
        if not canonical.empty:
            canonical = canonical.reindex(sorted(canonical.columns), axis=1)
            canonical = canonical.sort_values(list(canonical.columns), kind="stable").reset_index(drop=True)
        digest.update(canonical.to_csv(index=False).encode("utf-8"))
    return digest.hexdigest()


def _pair_fold_rows(
    fold_dirs: list[Path],
) -> tuple[list[dict[str, object]], pd.DataFrame, dict[str, object]]:
    metas = [_manifest(path) for path in fold_dirs]
    base = metas[0]
    if any(meta["pair_id"] != base["pair_id"] for meta in metas):
        raise ValueError("pair fold directories contain mixed pair IDs")
    ready_folds = [meta for meta in metas if meta["fold_status"] == "ready"]
    if not ready_folds:
        rows = [
            _zero_row(meta, meta["fold_failure_reason"] or f"fold_status={meta['fold_status']}")
            for meta in metas
        ]
        audit = {
            "pair_id": int(base["pair_id"]),
            "scientific_name": str(base["scientific_name"]),
            "species_key": int(base["species_key"]),
            "prior_status": "not_attempted_upstream_fold_failure",
            "prior_rank_used": None,
            "prior_record_count": 0,
            "failure_reason": "all focal folds unavailable from unchanged upstream exporter",
        }
        return rows, pd.DataFrame(), audit

    bounds = (
        float(base["west"]), float(base["south"]), float(base["east"]), float(base["north"])
    )
    try:
        prior, prior_audit = fetch_nonfocal_higher_taxon_prior(
            int(base["species_key"]),
            bounds,
            focal_scientific_name=str(base["scientific_name"]),
            record_cap=DEFAULT_PRIOR_RECORD_CAP,
        )
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        rows = [
            _zero_row(meta, reason, prior_status="provider_or_metadata_exception") for meta in metas
        ]
        return rows, pd.DataFrame(), {
            "pair_id": int(base["pair_id"]),
            "scientific_name": str(base["scientific_name"]),
            "species_key": int(base["species_key"]),
            "prior_status": "provider_or_metadata_exception",
            "prior_rank_used": None,
            "prior_record_count": 0,
            "failure_reason": reason,
        }

    pair_audit = {"pair_id": int(base["pair_id"]), **prior_audit.as_dict()}
    if prior_audit.status != "ready" or prior.empty:
        rows = [
            _zero_row(
                meta,
                prior_audit.failure_reason or prior_audit.status,
                prior_status=prior_audit.status,
                prior_rank_used=str(prior_audit.prior_rank_used or ""),
                prior_record_count=int(len(prior)),
            )
            for meta in metas
        ]
        return rows, pd.DataFrame(), pair_audit

    try:
        frames, _, frame_summary = infer_higher_taxon_prior_frames(prior, prior_audit=prior_audit)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        rows = [
            _zero_row(
                meta,
                reason,
                prior_status="frame_construction_failed",
                prior_rank_used=str(prior_audit.prior_rank_used or ""),
                prior_record_count=int(len(prior)),
            )
            for meta in metas
        ]
        pair_audit["prior_status"] = "frame_construction_failed"
        pair_audit["failure_reason"] = reason
        return rows, pd.DataFrame(), pair_audit

    inferred_area = _frames_area_km2(frames)
    fixed_area = _spherical_rect_area_km2(*bounds)
    rows: list[dict[str, object]] = []
    for fold_dir, meta in zip(fold_dirs, metas):
        if meta["fold_status"] != "ready":
            rows.append(
                _zero_row(
                    meta,
                    meta["fold_failure_reason"] or f"fold_status={meta['fold_status']}",
                    prior_status=prior_audit.status,
                    prior_rank_used=str(prior_audit.prior_rank_used or ""),
                    prior_record_count=int(len(prior)),
                )
            )
            continue
        try:
            heldout = pd.read_csv(fold_dir / "held_out_occurrences.csv")
            inside, held_count, containment = _heldout_containment(heldout, frames)
            rows.append({
                **meta,
                "heldout_records": int(held_count),
                "heldout_inside_frames": int(inside),
                "heldout_frame_containment": float(containment),
                "frame_count": int(len(frames)),
                "initial_component_count": int(frame_summary["initial_component_count"]),
                "occupied_block_count": int(frame_summary["occupied_block_count"]),
                "prior_status": prior_audit.status,
                "prior_rank_used": str(prior_audit.prior_rank_used or ""),
                "prior_record_count": int(len(prior)),
                "inferred_frame_area_km2": float(inferred_area),
                "fixed_region_area_km2": float(fixed_area),
                "frame_area_ratio_to_fixed": float(inferred_area / fixed_area),
                "framing_status": "evaluated",
                "failure_reason": "",
            })
        except Exception as exc:
            rows.append(
                _zero_row(
                    meta,
                    f"{type(exc).__name__}: {exc}",
                    prior_status=prior_audit.status,
                    prior_rank_used=str(prior_audit.prior_rank_used or ""),
                    prior_record_count=int(len(prior)),
                )
            )

    prior_points = prior.copy()
    prior_points.insert(0, "pair_id", int(base["pair_id"]))
    prior_points["scientific_name"] = str(base["scientific_name"])
    prior_points["prior_rank_used"] = str(prior_audit.prior_rank_used or "")
    prior_points["prior_taxon_key_used"] = prior_audit.prior_taxon_key_used
    return rows, prior_points, pair_audit


def run(export_root: Path, output: Path) -> dict[str, object]:
    protocol = _protocol()
    all_fold_dirs = sorted(path.parent for path in export_root.glob("pair_*/fold_*/fold_manifest.json"))
    if len(all_fold_dirs) != 480:
        raise RuntimeError(f"expected 480 development folds, found {len(all_fold_dirs)}")

    by_pair: dict[int, list[Path]] = {}
    for fold_dir in all_fold_dirs:
        pair_id = int(_manifest(fold_dir)["pair_id"])
        by_pair.setdefault(pair_id, []).append(fold_dir)
    if len(by_pair) != 96 or any(len(paths) != 5 for paths in by_pair.values()):
        raise RuntimeError("expected 96 pairs with five folds each")

    fold_rows: list[dict[str, object]] = []
    prior_point_tables: list[pd.DataFrame] = []
    prior_audits: list[dict[str, object]] = []
    for pair_id in sorted(by_pair):
        rows, prior_points, pair_audit = _pair_fold_rows(sorted(by_pair[pair_id]))
        fold_rows.extend(rows)
        if not prior_points.empty:
            prior_point_tables.append(prior_points)
        prior_audits.append(pair_audit)

    folds = pd.DataFrame(fold_rows)
    prior_points = pd.concat(prior_point_tables, ignore_index=True) if prior_point_tables else pd.DataFrame()
    prior_audit_frame = pd.DataFrame(prior_audits)
    if len(folds) != 480:
        raise AssertionError("v2 evaluator must retain all 480 folds")

    output.mkdir(parents=True, exist_ok=True)
    folds.to_csv(output / "framing_v2_fold_diagnostics.csv", index=False)
    prior_points.to_csv(output / "higher_taxon_prior_points.csv", index=False)
    prior_audit_frame.to_csv(output / "higher_taxon_prior_pair_audit.csv", index=False)

    pairs = (
        folds.groupby(
            ["pair_id", "scientific_name", "taxon_group", "region_name", "geographic_stratum"],
            as_index=False,
        )
        .agg(
            fold_count=("repeat", "count"),
            mean_heldout_frame_containment=("heldout_frame_containment", "mean"),
            mean_frame_count=("frame_count", "mean"),
            mean_frame_area_ratio_to_fixed=("frame_area_ratio_to_fixed", "mean"),
            failed_folds=("framing_status", lambda s: int((pd.Series(s).astype(str) != "evaluated").sum())),
        )
    )
    pairs.to_csv(output / "framing_v2_pair_diagnostics.csv", index=False)

    mean_containment = float(folds["heldout_frame_containment"].mean())
    animal_mean = float(
        folds.loc[folds["taxon_group"].astype(str).eq("animal"), "heldout_frame_containment"].mean()
    )
    median_area_ratio = float(folds["frame_area_ratio_to_fixed"].median())
    gate = protocol["development_gate"]
    promotion_gate_passed = bool(
        len(folds) == int(gate["required_declared_folds"])
        and mean_containment >= float(gate["mean_heldout_frame_containment_min"])
        and animal_mean >= float(gate["animal_mean_heldout_frame_containment_min"])
        and median_area_ratio <= float(gate["median_frame_area_ratio_to_fixed_max"])
    )
    status_counts = (
        prior_audit_frame["status"].astype(str).value_counts().to_dict()
        if "status" in prior_audit_frame.columns
        else {}
    )
    rank_counts = (
        prior_audit_frame["prior_rank_used"].fillna("NONE").astype(str).value_counts().to_dict()
        if "prior_rank_used" in prior_audit_frame.columns
        else {}
    )
    summary: dict[str, object] = {
        "status": "development_only_higher_taxon_framing_v2_complete",
        "protocol_fingerprint": EXPECTED_PROTOCOL,
        "framing_method": protocol["frame_geometry"]["method"],
        "development_taxa": int(len(by_pair)),
        "declared_folds": int(len(folds)),
        "evaluated_folds": int(folds["framing_status"].eq("evaluated").sum()),
        "failed_folds_retained_as_zero": int((~folds["framing_status"].eq("evaluated")).sum()),
        "mean_fold_heldout_frame_containment": mean_containment,
        "animal_mean_fold_heldout_frame_containment": animal_mean,
        "plant_mean_fold_heldout_frame_containment": float(
            folds.loc[folds["taxon_group"].astype(str).eq("plant"), "heldout_frame_containment"].mean()
        ),
        "median_fold_frame_area_ratio_to_fixed": median_area_ratio,
        "mean_fold_frame_area_ratio_to_fixed": float(folds["frame_area_ratio_to_fixed"].mean()),
        "median_fold_frame_count": float(folds["frame_count"].median()),
        "prior_pair_status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "prior_rank_counts": {str(k): int(v) for k, v in rank_counts.items()},
        "prior_snapshot_fingerprint": _prior_snapshot_fingerprint(prior_points, prior_audit_frame),
        "focal_occurrence_snapshot_fingerprint": _snapshot_fingerprint(all_fold_dirs),
        "promotion_gate": gate,
        "promotion_gate_passed": promotion_gate_passed,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "fresh_confirmation_taxa_consumed": False,
        "validated_japan_adapter_changed": False,
        "beyond_japan_claim_allowed": False,
        "interpretation_if_pass": "freeze representation before fresh confirmation; do not promote from development result",
        "interpretation_if_fail": "reject v2 without tuning parameters on these same 96 taxa",
    }
    (output / "framing_v2_diagnostic_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.export_root, args.output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
