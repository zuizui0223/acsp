import numpy as np
import pandas as pd

from acsp.contrast_benchmark import spatial_block_contrast_benchmark


def _occurrences():
    rows = []
    for base_lat, base_lon in ((34.05, 135.05), (34.25, 135.25), (34.45, 135.45), (34.65, 135.65)):
        for offset in (0.0, 0.01, 0.02):
            rows.append({"latitude": base_lat + offset, "longitude": base_lon + offset})
    return pd.DataFrame(rows)


def _builder(training):
    rows = []
    site = 0
    # Every availability block has the same relative gradient but a different
    # absolute environmental offset. The occupied proxy lies at the high end.
    for base_lat, base_lon, shift in (
        (34.05, 135.05, 0.0),
        (34.25, 135.25, 100.0),
        (34.45, 135.45, -100.0),
        (34.65, 135.65, 250.0),
    ):
        for rank in range(5):
            site += 1
            rows.append(
                {
                    "site_id": str(site),
                    "candidate_type": "habitat-match",
                    "latitude": base_lat + rank * 0.005,
                    "longitude": base_lon + rank * 0.005,
                    "elevation": shift + rank,
                    "slope": 2.0 * rank,
                    "roughness": rank / 2.0,
                    "tpi": rank - 2.0,
                    "distance_to_coast_m": 1000.0 - rank * 100.0,
                    "local_habitat_score": rank / 4.0,
                    "component_local_habitat_score": rank / 4.0,
                }
            )
    return pd.DataFrame(rows)


def test_spatial_block_contrast_benchmark_is_training_only_and_auditable():
    candidates, folds = spatial_block_contrast_benchmark(
        _occurrences(),
        _builder,
        block_degrees=0.15,
        availability_block_degrees=0.15,
        repeats=3,
        holdout_fraction=0.25,
        top_k=3,
        hit_radius_km=20.0,
        random_draws=20,
        random_state=7,
    )
    assert len(folds) == 3
    assert set(folds["status"]) == {"ok"}
    assert {
        "ecological_contrast_recall",
        "absolute_prototype_recall",
        "current_acsp_recall",
        "random_same_pool_recall",
        "contrast_lift_over_random",
        "contrast_lift_over_absolute",
    }.issubset(folds.columns)
    assert not candidates.empty
    assert candidates["ecological_contrast_selection_rank"].notna().any()
    assert np.isfinite(folds["ecological_contrast_recall"]).all()
