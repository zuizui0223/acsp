#!/usr/bin/env python3
"""Test topology information beyond breadth and covariance volume.

Two deliberately separate experiments are used.

1. Fragmentation experiment: scenarios are whitened to zero mean and identity
   covariance. This tests whether gap strength detects missing environmental states
   when PCA breadth and Gaussian covariance volume are identical.
2. Path experiment: straight and curved paths are generated with the same number of
   ordered points, comparable step size, and the same isotropic noise, without
   scenario-specific whitening. This tests continuity as diameter divided by MST
   path length. Scenario-specific whitening is intentionally forbidden here because
   it can magnify the near-zero transverse variance of a straight path and destroy
   the topology being tested.

Campanula is not used.
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


def _fragmentation_scenario(name: str, n: int, rng: np.random.Generator) -> np.ndarray:
    """Create full-rank point clouds, then exactly match first two moments."""
    if name == "connected_cloud":
        t = rng.uniform(-1.5, 1.5, n)
        x = np.column_stack([t, 0.35 * np.sin(2.0 * t)])
        x += rng.normal(0.0, 0.12, size=(n, 2))
    elif name == "two_modes":
        half = n // 2
        a = rng.normal((-1.5, 0.0), (0.18, 0.18), size=(half, 2))
        b = rng.normal((1.5, 0.0), (0.18, 0.18), size=(n - half, 2))
        x = np.vstack([a, b])
    elif name == "three_modes":
        sizes = [n // 3, n // 3, n - 2 * (n // 3)]
        centers = [(-1.4, -0.6), (0.0, 1.2), (1.4, -0.6)]
        x = np.vstack([
            rng.normal(c, (0.16, 0.16), size=(s, 2))
            for c, s in zip(centers, sizes)
        ])
    elif name == "missing_bridge":
        left = np.linspace(-1.5, -0.35, n // 2)
        right = np.linspace(0.35, 1.5, n - n // 2)
        z = np.concatenate([left, right])
        x = np.column_stack([z, 0.30 * np.sin(2.5 * z)])
        x += rng.normal(0.0, 0.04, size=(n, 2))
    else:
        raise ValueError(name)
    return _whiten(x)


def _path_scenario(name: str, n: int, rng: np.random.Generator) -> np.ndarray:
    """Generate paths with comparable scale without topology-destroying whitening."""
    if name == "straight_path":
        # Chord length is 2.0 and ordered path length is also approximately 2.0.
        t = np.linspace(-1.0, 1.0, n)
        x = np.column_stack([t, np.zeros_like(t)])
    elif name == "curved_path":
        # Semicircle radius 1: chord length 2.0 but path length pi.
        angle = np.linspace(0.0, np.pi, n)
        x = np.column_stack([np.cos(angle), np.sin(angle)])
    else:
        raise ValueError(name)
    # Same small isotropic measurement noise in both scenarios.
    return x + rng.normal(0.0, 0.004, size=(n, 2))


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

    fragmentation_names = ["connected_cloud", "two_modes", "three_modes", "missing_bridge"]
    path_names = ["straight_path", "curved_path"]
    rows: list[dict[str, object]] = []

    for repeat in range(1, args.repeats + 1):
        for name in fragmentation_names:
            x = _fragmentation_scenario(name, args.points, rng)
            g = infer_occupancy_geometry(x)
            rows.append({
                "repeat": repeat,
                "experiment": "moment_matched_fragmentation",
                "scenario": name,
                "pca_breadth": _breadth(x),
                "gaussian_log_volume": _log_volume(x),
                "span": g.span,
                "continuity": g.continuity,
                "gap_strength": g.gap_strength,
                "component_count": g.component_count,
            })
        for name in path_names:
            x = _path_scenario(name, args.points, rng)
            g = infer_occupancy_geometry(x)
            rows.append({
                "repeat": repeat,
                "experiment": "path_tortuosity",
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
    summary = frame.groupby(["experiment", "scenario"], as_index=False).agg(
        pca_breadth_median=("pca_breadth", "median"),
        gaussian_log_volume_median=("gaussian_log_volume", "median"),
        span_median=("span", "median"),
        continuity_median=("continuity", "median"),
        gap_strength_median=("gap_strength", "median"),
        component_count_median=("component_count", "median"),
    )
    summary.to_csv(output / "topology_scenario_summary.csv", index=False)

    fragmentation = summary[summary.experiment.eq("moment_matched_fragmentation")].set_index("scenario")
    paths = summary[summary.experiment.eq("path_tortuosity")].set_index("scenario")
    breadth_range = float(
        fragmentation.pca_breadth_median.max() - fragmentation.pca_breadth_median.min()
    )
    volume_range = float(
        fragmentation.gaussian_log_volume_median.max()
        - fragmentation.gaussian_log_volume_median.min()
    )
    two_mode_gap_ratio = float(
        fragmentation.loc["two_modes", "gap_strength_median"]
        / fragmentation.loc["connected_cloud", "gap_strength_median"]
    )
    missing_bridge_gap_ratio = float(
        fragmentation.loc["missing_bridge", "gap_strength_median"]
        / fragmentation.loc["connected_cloud", "gap_strength_median"]
    )
    curved_continuity_ratio = float(
        paths.loc["curved_path", "continuity_median"]
        / paths.loc["straight_path", "continuity_median"]
    )

    result = {
        "campanula_used": False,
        "design_revision": (
            "Fragmentation is tested under exact moment matching; path tortuosity is tested "
            "without scenario-specific whitening because whitening a near-rank-one straight "
            "path amplifies transverse noise and changes its topology."
        ),
        "fragmentation_scenario_count": len(fragmentation_names),
        "path_scenario_count": len(path_names),
        "repeats": int(args.repeats),
        "fragmentation_pca_breadth_range": breadth_range,
        "fragmentation_gaussian_log_volume_range": volume_range,
        "two_mode_gap_over_connected": two_mode_gap_ratio,
        "missing_bridge_gap_over_connected": missing_bridge_gap_ratio,
        "curved_to_straight_continuity_ratio": curved_continuity_ratio,
        "passes_topology_discrimination": bool(
            breadth_range < 1e-6
            and volume_range < 1e-5
            and two_mode_gap_ratio > 1.0
            and missing_bridge_gap_ratio > 1.0
            and curved_continuity_ratio < 1.0
        ),
    }
    (output / "topology_benchmark_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    result = run(parser().parse_args())
    print(json.dumps(result, indent=2))
    if not result["passes_topology_discrimination"]:
        raise SystemExit("Topology discrimination benchmark failed")
