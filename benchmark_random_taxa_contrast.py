#!/usr/bin/env python3
"""Cross-taxon validation of local ecological contrast on random taxon-region pairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
import tracemalloc

import numpy as np
import pandas as pd

from acsp.contrast_benchmark import spatial_block_contrast_benchmark
from benchmark_general_random_taxa_regions import (
    _species_metadata,
    fetch_occurrences,
    predeclare_pairs,
    rectangle_feature,
)
from gbif_fieldmap_builder_app import build_automatic_discover_bundle


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--output", default="benchmark_results/random_taxa_contrast")
    command.add_argument("--pairs", type=int, default=8)
    command.add_argument("--repeats", type=int, default=3)
    command.add_argument("--records-per-pair", type=int, default=120)
    command.add_argument("--minimum-records", type=int, default=20)
    command.add_argument("--facet-limit", type=int, default=120)
    command.add_argument("--seed", type=int, default=20260716)
    command.add_argument("--block-degrees", type=float, default=0.10)
    command.add_argument("--availability-block-degrees", type=float, default=0.20)
    command.add_argument("--holdout-fraction", type=float, default=0.20)
    command.add_argument("--top-k", type=int, default=5)
    command.add_argument("--hit-radius-km", type=float, default=10.0)
    command.add_argument("--random-draws", type=int, default=200)
    return command


def _sign_flip_p(values: np.ndarray, *, seed: int, draws: int = 20000) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.nan
    observed = float(values.mean())
    rng = np.random.default_rng(int(seed))
    signs = rng.choice(np.array([-1.0, 1.0]), size=(int(draws), len(values)))
    null = (signs * values[None, :]).mean(axis=1)
    return float((1 + np.count_nonzero(null >= observed)) / (len(null) + 1))


def run(args: argparse.Namespace) -> dict[str, object]:
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    sample_path = output / "predeclared_taxon_region_pairs.csv"
    if sample_path.exists():
        sample = pd.read_csv(sample_path).head(int(args.pairs))
    else:
        sample = predeclare_pairs(
            int(args.pairs), int(args.seed), int(args.facet_limit), int(args.minimum_records)
        )
        sample.to_csv(sample_path, index=False)

    statuses: list[dict[str, object]] = []
    fold_frames: list[pd.DataFrame] = []
    for _, row in sample[sample["status"].eq("predeclared")].iterrows():
        pair_id = int(row.pair_id)
        pair_fold_path = output / f"pair_{pair_id:03d}_contrast_folds.csv"
        pair_candidate_path = output / f"pair_{pair_id:03d}_contrast_candidates.csv"
        if pair_fold_path.exists() and pair_candidate_path.exists():
            folds = pd.read_csv(pair_fold_path)
            fold_frames.append(folds)
            statuses.append({
                "pair_id": pair_id,
                "scientific_name": str(row.scientific_name),
                "status": "checkpoint",
                "valid_repeats": int(folds["status"].eq("ok").sum()),
            })
            continue
        started = perf_counter()
        tracemalloc.start()
        try:
            occurrences = fetch_occurrences(row, int(args.records_per_pair))
            bounds = (float(row.west), float(row.south), float(row.east), float(row.north))
            metadata = _species_metadata(int(row.speciesKey)) or {}
            metadata.setdefault("kingdom", "Plantae" if row.taxon_group == "plant" else "Animalia")

            def builder(training: pd.DataFrame) -> pd.DataFrame:
                rebuilt = training.copy().reset_index(drop=True)
                rebuilt["_row_id"] = np.arange(len(rebuilt), dtype=int)
                bundle = build_automatic_discover_bundle(
                    str(row.scientific_name),
                    rebuilt,
                    "random taxa contrast benchmark",
                    str(row.region_name),
                    override_row_ids=rebuilt["_row_id"].tolist(),
                    taxon_metadata=metadata,
                    survey_bounds=bounds,
                    survey_features=[rectangle_feature(bounds, str(row.region_name))],
                    candidate_generation_only=True,
                )
                return bundle["potential_candidates"].copy()

            candidates, folds = spatial_block_contrast_benchmark(
                occurrences,
                builder,
                block_degrees=float(args.block_degrees),
                availability_block_degrees=float(args.availability_block_degrees),
                repeats=int(args.repeats),
                holdout_fraction=float(args.holdout_fraction),
                top_k=int(args.top_k),
                hit_radius_km=float(args.hit_radius_km),
                random_draws=int(args.random_draws),
                random_state=int(args.seed) + pair_id,
            )
            for frame in (candidates, folds):
                frame["pair_id"] = pair_id
                frame["benchmark_taxon"] = str(row.scientific_name)
                frame["benchmark_region"] = str(row.region_name)
                frame["taxon_group"] = str(row.taxon_group)
                frame["geographic_stratum"] = str(row.geographic_stratum)
            candidates.to_csv(pair_candidate_path, index=False)
            folds.to_csv(pair_fold_path, index=False)
            fold_frames.append(folds)
            statuses.append({
                "pair_id": pair_id,
                "scientific_name": str(row.scientific_name),
                "status": "ok",
                "valid_repeats": int(folds["status"].eq("ok").sum()),
                "failed_repeats": int(folds["status"].ne("ok").sum()),
            })
        except Exception as exc:
            statuses.append({
                "pair_id": pair_id,
                "scientific_name": str(row.scientific_name),
                "status": "failed",
                "reason": str(exc),
            })
        finally:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            statuses[-1]["runtime_seconds"] = float(perf_counter() - started)
            statuses[-1]["peak_memory_bytes"] = int(peak)
            pd.DataFrame(statuses).to_csv(output / "pair_status.csv", index=False)

    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    folds.to_csv(output / "contrast_fold_results.csv", index=False)
    valid = folds[folds.get("status", pd.Series(dtype=str)).eq("ok")].copy()
    pair_summary = pd.DataFrame()
    if not valid.empty:
        pair_summary = valid.groupby(
            ["pair_id", "benchmark_taxon", "benchmark_region", "taxon_group", "geographic_stratum"],
            as_index=False,
        ).agg(
            valid_repeats=("repeat", "size"),
            ecological_contrast_recall=("ecological_contrast_recall", "mean"),
            absolute_prototype_recall=("absolute_prototype_recall", "mean"),
            current_acsp_recall=("current_acsp_recall", "mean"),
            random_same_pool_recall=("random_same_pool_recall", "mean"),
            contrast_lift_over_random=("contrast_lift_over_random", "mean"),
            contrast_lift_over_absolute=("contrast_lift_over_absolute", "mean"),
        )
    pair_summary.to_csv(output / "contrast_pair_summary.csv", index=False)

    status_frame = pd.DataFrame(statuses)
    total_declared = int(len(sample[sample["status"].eq("predeclared")]))
    evaluable = int(len(pair_summary))
    completion = evaluable / max(1, total_declared)
    lift_random = pair_summary.get("contrast_lift_over_random", pd.Series(dtype=float)).to_numpy(float)
    lift_absolute = pair_summary.get("contrast_lift_over_absolute", pd.Series(dtype=float)).to_numpy(float)
    result = {
        "design": "random taxon-region pairs; repeated spatial-block holdout; training-only candidate rebuilding",
        "campanula_used": False,
        "predeclared_pairs": total_declared,
        "evaluable_pairs": evaluable,
        "completion_rate": completion,
        "mean_contrast_lift_over_random": None if not len(lift_random) else float(np.mean(lift_random)),
        "mean_contrast_lift_over_absolute": None if not len(lift_absolute) else float(np.mean(lift_absolute)),
        "positive_pair_fraction_over_random": None if not len(lift_random) else float(np.mean(lift_random > 0)),
        "positive_pair_fraction_over_absolute": None if not len(lift_absolute) else float(np.mean(lift_absolute > 0)),
        "sign_flip_p_over_random": _sign_flip_p(lift_random, seed=int(args.seed)),
        "sign_flip_p_over_absolute": _sign_flip_p(lift_absolute, seed=int(args.seed) + 1),
        "acceptance_rule": {
            "minimum_completion_rate": 0.75,
            "mean_lift_over_random_must_be_positive": True,
            "mean_lift_over_absolute_must_be_positive": True,
            "positive_pair_fraction_over_random_minimum": 0.60,
        },
        "passes_initial_gate": bool(
            completion >= 0.75
            and len(lift_random)
            and np.mean(lift_random) > 0
            and np.mean(lift_absolute) > 0
            and np.mean(lift_random > 0) >= 0.60
        ),
        "status_counts": status_frame["status"].value_counts().to_dict() if not status_frame.empty else {},
        "protocol": vars(args),
        "scientific_caution": (
            "Training occurrence environments are approximated by nearest candidates within the same availability block. "
            "Passing this development gate still requires a frozen confirmation cohort with direct feature extraction."
        ),
    }
    (output / "contrast_benchmark_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
