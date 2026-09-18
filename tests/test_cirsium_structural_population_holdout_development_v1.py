from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import research.run_cirsium_structural_population_holdout_development_v1 as runner


def _cluster(*members: tuple[float, float, str]):
    return SimpleNamespace(members=tuple(members))


def test_training_anchors_remove_every_member_of_hidden_population() -> None:
    clusters = [
        _cluster((35.0, 137.0, "a1"), (35.0001, 137.0001, "a2")),
        _cluster((35.2, 137.2, "b1")),
        _cluster((35.4, 137.4, "c1")),
    ]
    anchors = runner._training_anchors(clusters, 0)
    assert len(anchors) == 2
    assert not anchors["occurrence_id"].astype(str).str.contains("a1|a2").any()
    assert set(anchors["cluster_size"].astype(int)) == {1}


def test_fold_orders_use_one_common_known_excluded_frame() -> None:
    base = pd.DataFrame(
        {
            "candidate_cell_id": ["a", "b", "c", "d"],
            "latitude": [35.0, 35.02, 35.08, 35.12],
            "longitude": [137.0, 137.02, 137.08, 137.12],
            "grid_row": [0, 0, 1, 1],
            "grid_col": [0, 1, 0, 1],
        }
    )
    structural = base.copy()
    structural["structural_support"] = [0.1, 0.9, 0.8, 0.2]
    anchors = pd.DataFrame(
        {
            "occurrence_id": ["known"],
            "latitude": [35.0],
            "longitude": [137.0],
            "cluster_size": [1],
        }
    )

    fold_frame, structural_order, nearest, spatial = runner._fold_orders(
        base,
        structural,
        anchors,
        known_exclusion_km=0.5,
    )
    ids = set(fold_frame["candidate_cell_id"].astype(str))
    assert "a" not in ids
    assert ids == set(structural_order["candidate_cell_id"].astype(str))
    assert ids == set(nearest["candidate_cell_id"].astype(str))
    assert ids == set(spatial["candidate_cell_id"].astype(str))
    assert structural_order.iloc[0]["candidate_cell_id"] == "b"


def test_contract_freezes_three_executed_families_and_defers_coastal() -> None:
    contract = runner._load_json(runner.CONTRACT_PATH)
    assert contract["status"] == "FROZEN_BEFORE_STRUCTURAL_POPULATION_HOLDOUT_EXECUTION"
    assert contract["population_holdout"]["expected_total_folds"] == 12
    assert contract["candidate_frame"]["grid_spacing_m"] == 5000
    assert contract["outcome"]["primary_recovery_radius_km"] == 5.0
    assert contract["prefix_curve"]["fractions"] == [0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0]

    executed = contract["execution_pairs"]
    assert {row["structural_feature_family"] for row in executed} == {
        "WETLAND_MOISTURE_STRUCTURE",
        "ALPINE_TOPOGRAPHIC_STRUCTURE",
        "OPEN_GRASSLAND_STRUCTURE",
    }
    assert sum(int(row["expected_population_clusters"]) for row in executed) == 12
    deferred = contract["explicitly_deferred_eligible_pairs"]
    assert len(deferred) == 1
    assert deferred[0]["pair_id"] == "CIR08__ryukyu"
    assert deferred[0]["structural_feature_family"] == "COASTAL_ISLAND_STRUCTURE"


def test_summary_keeps_full_frame_unreachable_rows_in_primary() -> None:
    contract = runner._load_json(runner.CONTRACT_PATH)
    curve = pd.DataFrame(
        [
            {
                "fold_id": "f1",
                "structural_feature_family": "WETLAND_MOISTURE_STRUCTURE",
                "prefix_fraction": 1.0,
                "recovery_radius_km": 5.0,
                "structural_recovered": False,
                "nearest_recovered": False,
                "spatial_balance_recovered": False,
                "full_frame_reachable": False,
            },
            {
                "fold_id": "f2",
                "structural_feature_family": "WETLAND_MOISTURE_STRUCTURE",
                "prefix_fraction": 1.0,
                "recovery_radius_km": 5.0,
                "structural_recovered": True,
                "nearest_recovered": False,
                "spatial_balance_recovered": False,
                "full_frame_reachable": True,
            },
        ]
    )
    summary = runner.summarize(
        curve,
        [
            {"pair_id": "p", "status": "EXECUTED"},
        ],
        contract=contract,
    )
    assert summary["executed_total_folds"] == 2
    assert summary["primary_5km_full_frame_reachability"] == 0.5
    assert summary["primary_5km_all_fold_all_prefix"]["structural_mean_recovery"] == 0.5
    assert summary["promotion_allowed"] is False
