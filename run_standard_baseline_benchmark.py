#!/usr/bin/env python3
"""Evaluate frozen ACSP and standard same-pool selectors from audited fold exports."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from acsp.comparator_benchmark import (
    StandardBaselineProtocol,
    comparator_inference,
    evaluate_candidate_fold,
    pair_level_intention_to_evaluate,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_verified_candidates(
    fold_dir: Path,
    protocol: StandardBaselineProtocol,
) -> pd.DataFrame:
    manifest_path = fold_dir / "fold_manifest.json"
    candidate_path = fold_dir / "candidates.csv"
    if not manifest_path.exists() or not candidate_path.exists():
        return pd.DataFrame()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol_fingerprint") != protocol.manifest()["fingerprint"]:
        raise ValueError(f"protocol fingerprint mismatch: {fold_dir}")
    expected = manifest.get("files", {}).get("candidates", {}).get("sha256")
    if not expected or _sha256(candidate_path) != expected:
        raise ValueError(f"candidate checksum mismatch: {candidate_path}")
    try:
        return pd.read_csv(candidate_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def run(args: argparse.Namespace) -> dict[str, object]:
    protocol = StandardBaselineProtocol.from_json(args.protocol)
    export_root = Path(args.export_root)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    declared_path = export_root / "declared_pairs.csv"
    if not declared_path.exists():
        raise FileNotFoundError(f"missing declared pair table: {declared_path}")
    declared = pd.read_csv(declared_path)
    declared = declared[declared["status"].eq("predeclared")].copy()
    fold_frames: list[pd.DataFrame] = []
    for _, pair in declared.iterrows():
        pair_id = int(pair.pair_id)
        group = str(pair.taxon_group)
        for repeat in range(1, protocol.repeats + 1):
            candidates = _read_verified_candidates(
                export_root / f"pair_{pair_id:03d}" / f"fold_{repeat:03d}",
                protocol,
            )
            evaluated = evaluate_candidate_fold(
                candidates,
                group,
                protocol,
                pair_id=pair_id,
                repeat=repeat,
                random_state=protocol.random_state + pair_id * 1000 + repeat,
            )
            evaluated["scientific_name"] = str(pair.scientific_name)
            evaluated["region_name"] = str(pair.region_name)
            evaluated["geographic_stratum"] = str(pair.geographic_stratum)
            fold_frames.append(evaluated)
    fold_results = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    fold_results.to_csv(output / "fold_method_comparison.csv", index=False)

    pair_table = pair_level_intention_to_evaluate(fold_results, declared, protocol)
    metadata_columns = [
        column
        for column in ("pair_id", "scientific_name", "region_name", "geographic_stratum")
        if column in declared.columns
    ]
    pair_table = pair_table.merge(
        declared[metadata_columns].drop_duplicates("pair_id"),
        on="pair_id",
        how="left",
    )
    pair_table.to_csv(output / "pair_level_intention_to_evaluate.csv", index=False)

    inference = comparator_inference(pair_table, protocol)
    inference.to_csv(output / "pair_level_comparator_inference.csv", index=False)

    eligible = pair_table[pair_table["pair_method_eligible"] & pair_table["ite_recall"].notna()]
    method_summary = (
        eligible.groupby(["taxon_group", "decision_method"], as_index=False)
        .agg(
            eligible_pairs=("pair_id", "nunique"),
            mean_ite_recall=("ite_recall", "mean"),
            minimum_ite_recall=("ite_recall", "min"),
            maximum_ite_recall=("ite_recall", "max"),
        )
        if not eligible.empty
        else pd.DataFrame()
    )
    method_summary.to_csv(output / "method_summary.csv", index=False)

    status_summary = (
        fold_results.groupby(["decision_method", "status"], as_index=False)
        .size()
        .rename(columns={"size": "fold_rows"})
        if not fold_results.empty
        else pd.DataFrame()
    )
    status_summary.to_csv(output / "method_eligibility_audit.csv", index=False)

    result = {
        "protocol": protocol.manifest(),
        "export_root": str(export_root.resolve()),
        "declared_pairs": int(len(declared)),
        "fold_rows": int(len(fold_results)),
        "pair_method_rows": int(len(pair_table)),
        "inference_rows": int(len(inference)),
        "method_summary": method_summary.to_dict("records"),
        "eligibility_audit": status_summary.to_dict("records"),
        "claim_boundary": (
            "Results compare selection rules within identical training-only candidate pools. "
            "The held-out oracle is descriptive headroom and environmental methods use only pairs "
            "with complete predeclared feature availability in all expected folds."
        ),
    }
    (output / "standard_baseline_benchmark_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--export-root", required=True)
    command.add_argument("--protocol", default="validation/standard_baseline_protocol.json")
    command.add_argument("--output", required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
