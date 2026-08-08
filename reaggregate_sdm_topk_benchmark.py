#!/usr/bin/env python3
"""Strictly reaggregate frozen SDM Top-k pair artifacts.

This wrapper corrects an aggregation-only verifier bug in the first untouched
benchmark run: the original glob ``fold_*`` also matched the top-level file
``fold_results.csv``. Pair artifacts and all scientific decisions are unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import aggregate_sdm_topk_benchmark as base


def verify_pair_strict(pair_dir: Path, protocol_fp: str, contract_fp: str) -> dict[str, Any]:
    manifest_path = pair_dir / "pair_manifest.json"
    result_path = pair_dir / "fold_results.csv"
    if not manifest_path.exists() or not result_path.exists():
        raise FileNotFoundError(f"pair artifact incomplete: {pair_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol_fingerprint") != protocol_fp:
        raise ValueError(f"protocol mismatch in {pair_dir}")
    if manifest.get("execution_contract_fingerprint") != contract_fp:
        raise ValueError(f"execution contract mismatch in {pair_dir}")
    if manifest.get("fold_result_sha256") != base._sha256(result_path):
        raise ValueError(f"fold result checksum mismatch in {pair_dir}")

    expected_repeats = int(manifest.get("expected_repeats", 0))
    fold_dirs = sorted(
        path
        for path in pair_dir.glob("fold_[0-9][0-9][0-9]")
        if path.is_dir()
    )
    if expected_repeats and len(fold_dirs) != expected_repeats:
        raise ValueError(
            f"expected {expected_repeats} fold directories in {pair_dir}, "
            f"found {len(fold_dirs)}"
        )
    for fold_dir in fold_dirs:
        fold_manifest_path = fold_dir / "fold_manifest.json"
        if not fold_manifest_path.exists():
            raise FileNotFoundError(f"missing fold manifest: {fold_dir}")
        fold_manifest = json.loads(fold_manifest_path.read_text(encoding="utf-8"))
        if fold_manifest.get("protocol_fingerprint") != protocol_fp:
            raise ValueError(f"fold protocol mismatch: {fold_dir}")
        if fold_manifest.get("execution_contract_fingerprint") != contract_fp:
            raise ValueError(f"fold contract mismatch: {fold_dir}")
        for metadata in fold_manifest.get("files", {}).values():
            path = fold_dir / str(metadata["path"])
            if not path.exists() or base._sha256(path) != metadata.get("sha256"):
                raise ValueError(f"fold checksum mismatch: {path}")
    return manifest


def run(args: argparse.Namespace) -> dict[str, Any]:
    original = base._verify_pair
    base._verify_pair = verify_pair_strict
    try:
        result = base.run(args)
    finally:
        base._verify_pair = original

    declared = int(result.get("declared_pairs", 0))
    verified = int(result.get("verified_pair_artifacts", 0))
    failures = int(result.get("artifact_verification_failures", 0))
    if declared != 24 or verified != declared or failures != 0:
        raise RuntimeError(
            "strict pair verification failed: "
            f"declared={declared}, verified={verified}, failures={failures}"
        )
    if int(result.get("written_fold_method_rows", 0)) != 24 * 5 * 6:
        raise RuntimeError("strict aggregate does not contain all 720 fold-method rows")

    result["aggregation_qa"] = {
        "status": "reverified_after_glob_fix",
        "source_pair_artifacts_unchanged": True,
        "original_invalid_aggregate_run_id": 31236963484,
        "original_bug": "pair_dir.glob('fold_*') matched fold_results.csv as well as fold directories",
        "fix": "verify only fold_[0-9][0-9][0-9] paths that are directories",
    }
    output = Path(args.output)
    (output / "benchmark_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-root", default="sdm_topk_pairs")
    command.add_argument("--output", default="sdm_topk_aggregate")
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
