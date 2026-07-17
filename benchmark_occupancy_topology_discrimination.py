#!/usr/bin/env python3
"""Test whether occupancy geometry adds topology information beyond breadth and volume.

Synthetic point clouds are transformed to share zero mean and identity covariance, so PCA
breadth and Gaussian covariance volume are matched by construction. The benchmark asks
whether continuity and gap strength still distinguish connected, curved, and fragmented
occupancy structures. Campanula is not used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.occupancy_geometry import infer_occupancy_geometry


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default="benchmark_results/occupancy_topology_discrimination")
    p.add_argument("--repeats", type=int, default=100)
    p.add_argument("--points", type=int, default=120)
    p.add_argument("--seed", type=int, default=20260731)
    return p


def _whiten(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    x = x - x.mean(axis=0, keepdims=True)
    cov = np.cov(x, rowvar=False)
    values, vectors = np.linalg.eigh(cov)
    values = np.clip(values, 1e-8, None)
    return x @ vectors @ np.diag(values ** -0.5)


def _scenario(name: str, n: int, rng: np.random.Generator) -> np.ndarray:
    t = np.linspace(-1.0, 1.0, n)
    noise = lambda scale=0.04: rng.normal(0.0, scale, size=(n, 2))
    if name == "straight_chain":
        x = np.column_stack([t, 0.15 * t]) + noise()
    elif name == "curved_chain":
        angle = np.linspace(-0.2 * np.pi, 1.2 * np.pi, n)
        x = np.column_stack([np.cos(angle), np.sin(angle)]) + noise()
    elif name == "two_modes":
        half = n // 2
        a = rng.normal((-1.5, 0.0), (0.18, 0.18), size=(half, 2))
        b = rng.normal((1.5, 0.0), (0.18, 0.18), size=(n - half, 2))
        x = np.vstack([a, b])
    elif name == "three_modes":
        sizes = [n // 3, n // 3, n - 2 * (n // 3)]
        centers = [(-1.4, -0.6), (0.0, 1.2), (1.4, -0.6)]
        x = np.vstack([rng.normal(c, (0.16, 0.16), size=(s, 2)) for c, s in zip(centers, sizes)])
    elif name == "missing_bridge":
        left = np.linspace(-1.5, -0.35, n // 2)
        right = np.linspace(0.35, 1.5, n - n // 2)
        z = np.concatenate([left, right])
        x = np.column_stack([z, 0.25 * np.sin(2.5 * z)]) + noise()
    else:
        raise ValueError(name)
    return _whiten(x)


def _breadth(x: np.ndarray) -> float:
    return float(np.trace(np.cov(x, rowvar=False)))


def _log_volume(x: np.ndarray) -> float:
    cov = np.cov(x, rowvar=False) + np.eye(x.shape[1]) * 1e-8
    sign, value = np.linalg.slogdet(cov)
    return float(value if sign > 0 else np.nan)


def run(args: argparse.Namespace) -> dict[str, object]:
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    names = ["straight_chain", "curved_chain", "two_modes", "three_modes", "missing_bridge"]
    rows = []
    for repeat in range(1, args.repeats + 1):
        for name in names:
            x = _scenario(name, args.points, rng)
            g = infer_occupancy_geometry(x)
            rows.append({
                "repeat": repeat,
                "scenario": name,
                "pca_breadth": _breadth(x),
                "gaussian_log_volume": _log_volume(x),
                "span": g.span,
                "continuity": g.continuity,
                "gap_strength": g.gap_strength,
                "component_count": g.component_count,
            })
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "topology_repeat_results.csv", index=False)
    summary = frame.groupby("scenario", as_index=False).agg(
        pca_breadth_median=("pca_breadth", "median"),
        gaussian_log_volume_median=("gaussian_log_volume", "median"),
        span_median=("span", "median"),
        continuity_median=("continuity", "median"),
        gap_strength_median=("gap_strength", "median"),
        component_count_median=("component_count", "median"),
    )
    summary.to_csv(output / "topology_scenario_summary.csv", index=False)
    indexed = summary.set_index("scenario")
    breadth_range = float(summary.pca_breadth_median.max() - summary.pca_breadth_median.min())
    volume_range = float(summary.gaussian_log_volume_median.max() - summary.gaussian_log_volume_median.min())
    result = {
        "campanula_used": False,
        "moment_matching": "all scenarios whitened to zero mean and identity covariance",
        "scenario_count": len(names),
        "repeats": int(args.repeats),
        "pca_breadth_range": breadth_range,
        "gaussian_log_volume_range": volume_range,
        "two_mode_gap_over_straight": float(indexed.loc["two_modes", "gap_strength_median"] / indexed.loc["straight_chain", "gap_strength_median"]),
        "missing_bridge_gap_over_straight": float(indexed.loc["missing_bridge", "gap_strength_median"] / indexed.loc["straight_chain", "gap_strength_median"]),
        "curved_to_straight_continuity_ratio": float(indexed.loc["curved_chain", "continuity_median"] / indexed.loc["straight_chain", "continuity_median"]),
        "passes_topology_discrimination": bool(
            breadth_range < 1e-6
            and volume_range < 1e-5
            and indexed.loc["two_modes", "gap_strength_median"] > indexed.loc["straight_chain", "gap_strength_median"]
            and indexed.loc["missing_bridge", "gap_strength_median"] > indexed.loc["straight_chain", "gap_strength_median"]
            and indexed.loc["curved_chain", "continuity_median"] < indexed.loc["straight_chain", "continuity_median"]
        ),
    }
    (output / "topology_benchmark_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    result = run(parser().parse_args())
    print(json.dumps(result, indent=2))
    if not result["passes_topology_discrimination"]:
        raise SystemExit("Topology discrimination benchmark failed")
