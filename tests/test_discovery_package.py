from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery import (
    AnnularFrameSpec,
    DiscoveryEvidenceProfile,
    DiscoveryRegime,
    build_annular_candidate_frame,
    build_structural_support_order,
    cluster_medoid_table,
    complete_link_clusters,
    rank_nearest_anchor,
    resolve_discovery_regime,
    select_stable_start_maximin,
)


class DiscoveryPackageTests(unittest.TestCase):
    def test_explicit_discovery_import_does_not_import_planning(self) -> None:
        code = (
            "import sys; import acsp.discovery; "
            "assert 'acsp.planning' not in sys.modules, sorted(k for k in sys.modules if k.startswith('acsp.'))"
        )
        subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)

    def test_complete_link_prevents_chaining_and_medoid_is_one_member(self) -> None:
        frame = pd.DataFrame(
            {
                "occurrence_id": ["a", "b", "c"],
                "latitude": [35.0, 35.0, 35.0],
                "longitude": [139.000, 139.004, 139.008],
            }
        )
        clusters = complete_link_clusters(frame, radius_km=0.5)
        self.assertEqual([cluster.size for cluster in clusters], [2, 1])
        medoids = cluster_medoid_table(clusters)
        self.assertEqual(len(medoids), 2)
        self.assertTrue(set(medoids["occurrence_id"]).issubset({"a", "b", "c"}))

    def test_regime_gate_never_infers_local_from_anchor_count_alone(self) -> None:
        decision = resolve_discovery_regime(DiscoveryEvidenceProfile(exact_anchor_count=20))
        self.assertEqual(decision.regime, DiscoveryRegime.ABSTAIN_LOCAL_PATCH)
        self.assertFalse(decision.inferred_from_anchor_count_threshold)

        local = resolve_discovery_regime(
            DiscoveryEvidenceProfile(exact_anchor_count=2, local_component_justified=True)
        )
        self.assertEqual(local.regime, DiscoveryRegime.LOCAL_CONTINUATION)

        detached = resolve_discovery_regime(
            DiscoveryEvidenceProfile(exact_anchor_count=1, detached_component_available=True)
        )
        self.assertEqual(detached.regime, DiscoveryRegime.DETACHED_COMPONENT)

        sentinel = resolve_discovery_regime(
            DiscoveryEvidenceProfile(
                sentinel_context_available=True,
                sentinel_subregime="UNCERTAINTY_FOOTPRINT",
            )
        )
        self.assertEqual(sentinel.regime, DiscoveryRegime.SENTINEL)

    def test_annular_frame_respects_exclusion_and_outer_radius(self) -> None:
        anchors = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
        frame, audit = build_annular_candidate_frame(
            anchors,
            spec=AnnularFrameSpec(grid_spacing_m=250.0, known_exclusion_km=0.5, outer_radius_km=1.0),
            candidate_id_prefix="test",
        )
        self.assertGreater(len(frame), 0)
        self.assertTrue((frame["nearest_anchor_km"] >= 0.5 - 1e-6).all())
        self.assertTrue((frame["nearest_anchor_km"] <= 1.0 + 1e-6).all())
        self.assertEqual(audit.anchor_count, 1)
        self.assertFalse(audit.human_access_used)

    def test_comparator_orders_are_deterministic_and_same_pool(self) -> None:
        frame = pd.DataFrame(
            {
                "candidate_cell_id": ["a", "b", "c", "d"],
                "latitude": [35.0, 35.0, 35.1, 35.1],
                "longitude": [139.0, 139.1, 139.0, 139.1],
                "nearest_anchor_km": [4.0, 1.0, 2.0, 3.0],
            }
        )
        nearest = rank_nearest_anchor(frame)
        self.assertEqual(nearest["candidate_cell_id"].tolist(), ["b", "c", "d", "a"])
        first, audit1 = select_stable_start_maximin(frame, count=3)
        second, audit2 = select_stable_start_maximin(frame, count=3)
        self.assertEqual(first["candidate_cell_id"].tolist(), second["candidate_cell_id"].tolist())
        self.assertEqual(len(first), 3)
        self.assertEqual(audit1.memory_complexity, "O(n)")
        self.assertEqual(audit1, audit2)

    def test_structural_order_is_taxon_neutral_and_outcome_blind(self) -> None:
        rows = []
        for r in range(3):
            for c in range(3):
                rows.append(
                    {
                        "candidate_cell_id": f"x{r}{c}",
                        "latitude": 35.0 + r * 0.001,
                        "longitude": 139.0 + c * 0.001,
                        "grid_row": r,
                        "grid_col": c,
                        "elev": 1000.0 + 100.0 * r + 50.0 * c,
                        "slope100": 10.0 + r,
                        "tpi300": float(c - 1),
                        "rough300": 5.0 + r + c,
                    }
                )
        raw = pd.DataFrame(rows)
        ordered, audit = build_structural_support_order(
            raw,
            feature_family="ALPINE_TOPOGRAPHIC_STRUCTURE",
            source_provenance={"source": "synthetic-public-terrain"},
        )
        self.assertEqual(len(ordered), len(raw))
        self.assertEqual(sorted(ordered["decision_rank"].tolist()), list(range(1, len(raw) + 1)))
        self.assertTrue(ordered["structural_support"].between(0, 1).all())
        self.assertFalse(audit.field_outcomes_used)
        self.assertFalse(audit.human_access_used)
        self.assertTrue(audit.support_provenance_id.startswith("sha256:"))

        contaminated = raw.copy()
        contaminated["field_outcome"] = "detected"
        with self.assertRaises(ValueError):
            build_structural_support_order(
                contaminated,
                feature_family="ALPINE_TOPOGRAPHIC_STRUCTURE",
                source_provenance={"source": "synthetic-public-terrain"},
            )


if __name__ == "__main__":
    unittest.main()
