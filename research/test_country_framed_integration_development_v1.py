import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from country_framed_robust_integration import CountryLandGeometry
from predeclare_country_framed_integration_development_v1 import (
    EXPECTED_PROTOCOL_FINGERPRINT,
    SOURCE_COHORT_PATH,
    _protocol as declaration_protocol,
    choose_historical_country,
    freeze_declarations,
    select_development_taxa,
)
from run_country_framed_integration_development_v1 import (
    _protocol as runner_protocol,
    evaluate_frozen_declarations,
    recovery_fraction,
    same_size_random_recovery,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v1.json"


class _Audit:
    def as_dict(self):
        return {"prototype_count": 5, "leave_one_out_worlds": 5}


class CountryFramedIntegrationDevelopmentV1Tests(unittest.TestCase):
    def test_protocol_fingerprint_and_nonretuning_contract(self):
        payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        stored = payload.pop("protocol_fingerprint")
        calculated = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        self.assertEqual(stored, EXPECTED_PROTOCOL_FINGERPRINT)
        self.assertEqual(calculated, EXPECTED_PROTOCOL_FINGERPRINT)
        self.assertEqual(declaration_protocol()["protocol_fingerprint"], EXPECTED_PROTOCOL_FINGERPRINT)
        self.assertEqual(runner_protocol()["protocol_fingerprint"], EXPECTED_PROTOCOL_FINGERPRINT)
        self.assertEqual(payload["outcome_evaluation"]["primary_recovery_radius_km"], 10.0)
        self.assertEqual(payload["outcome_evaluation"]["random_baseline_repetitions"], 200)
        self.assertEqual(payload["frozen_robust_core"]["support_fraction"], 0.025)
        self.assertEqual(payload["frozen_robust_core"]["surface_points_per_country"], 800)
        self.assertFalse(payload["claim_boundary"]["confirmation_v1_taxa_consumed"])
        self.assertFalse(payload["country_geometry_provider"]["fallback_allowed"])

    def test_exact_24_taxon_selection_from_v4_is_outcome_blind_and_balanced(self):
        selected = select_development_taxa(pd.read_csv(SOURCE_COHORT_PATH))
        self.assertEqual(len(selected), 24)
        self.assertEqual(selected["speciesKey"].nunique(), 24)
        self.assertEqual(selected["taxon_group"].value_counts().to_dict(), {"plant": 12, "animal": 12})
        self.assertEqual(
            selected["record_count_stratum"].astype(int).value_counts().sort_index().to_dict(),
            {0: 6, 1: 6, 2: 6, 3: 6},
        )
        for row in selected.itertuples(index=False):
            self.assertEqual(int(row.record_count_stratum), (int(row.region_cell_index) - 1) % 4)

    def test_country_selection_prefers_non_jp_then_jp_without_replacement(self):
        counts = {"JP": 100, "US": 10, "KR": 20, "GB": 4}
        first = choose_historical_country(counts, species_key=123, minimum_count=5, seed=2026082401)
        second = choose_historical_country(counts, species_key=123, minimum_count=5, seed=2026082401)
        self.assertEqual(first, second)
        self.assertIn(first[0], {"US", "KR"})
        self.assertEqual(first[1], "non_jp_hash_min")
        self.assertEqual(
            choose_historical_country({"JP": 8, "US": 4}, species_key=1, minimum_count=5, seed=9),
            ("JP", "jp_fallback_no_eligible_non_jp"),
        )
        self.assertEqual(
            choose_historical_country({"JP": 4, "US": 4}, species_key=1, minimum_count=5, seed=9),
            (None, "no_eligible_historical_country"),
        )

    @patch("predeclare_country_framed_integration_development_v1.fetch_geoboundaries_country_geometry")
    @patch("predeclare_country_framed_integration_development_v1.fetch_country_facet_counts")
    def test_stage1_freezes_country_and_geometry_without_recent_or_candidate_work(self, mock_counts, mock_geometry):
        mock_counts.return_value = {"JP": 30, "KR": 20}
        mock_geometry.return_value = CountryLandGeometry(
            country_code="KR",
            land_geometry_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
            source_id="geoBoundaries-gbOpen-ADM0-simplified",
            source_version="v6.0.0@commit;iso3=KOR;canonical_geojson_sha256=" + "a" * 64 + ";license=CC BY 4.0",
        )
        # Country choice depends on the taxon hash, so return a matching provider
        # object dynamically for whatever non-JP code the frozen rule selects.
        def geometry_side_effect(code):
            return CountryLandGeometry(
                country_code=code,
                land_geometry_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
                source_id="geoBoundaries-gbOpen-ADM0-simplified",
                source_version=f"v6.0.0@commit;iso3=XXX;canonical_geojson_sha256={'a' * 64};license=CC BY 4.0",
            )
        mock_geometry.side_effect = geometry_side_effect

        declarations, manifest = freeze_declarations()
        self.assertEqual(len(declarations), 24)
        self.assertEqual(mock_counts.call_count, 24)
        self.assertEqual(mock_geometry.call_count, 24)
        self.assertTrue(declarations["declaration_status"].eq("declared").all())
        self.assertFalse(declarations["selected_country_code"].eq("JP").any())
        self.assertTrue(declarations["geometry_canonical_sha256"].eq("a" * 64).all())
        self.assertFalse(manifest["recent_outcomes_inspected"])
        self.assertFalse(manifest["recent_occurrence_rows_fetched"])
        self.assertFalse(manifest["candidate_generation_run"])
        self.assertFalse(manifest["robust_support_run"])
        self.assertFalse(manifest["random_baseline_run"])
        self.assertFalse(manifest["replacement_after_declaration_allowed"])

    def test_recovery_and_same_size_random_baseline_are_deterministic_at_10km(self):
        recent = pd.DataFrame({"latitude": [0.0, 0.0], "longitude": [0.0, 0.2]})
        candidates = pd.DataFrame({"latitude": [0.0], "longitude": [0.0]})
        self.assertAlmostEqual(recovery_fraction(recent, candidates, 10.0), 0.5)
        surface = pd.DataFrame(
            {
                "latitude": np.linspace(10.0, 11.0, 20),
                "longitude": np.linspace(10.0, 11.0, 20),
            }
        )
        first = same_size_random_recovery(
            recent.iloc[[0]], surface, selected_count=2, radius_km=10.0, repetitions=200, seed=123
        )
        second = same_size_random_recovery(
            recent.iloc[[0]], surface, selected_count=2, radius_km=10.0, repetitions=200, seed=123
        )
        self.assertEqual(first, second)
        self.assertEqual(first, (0.0, 0.0, 0.0))

    @patch("run_country_framed_integration_development_v1.fetch_recent_country_occurrences")
    @patch("run_country_framed_integration_development_v1.validated_robust_candidate_patches")
    @patch("run_country_framed_integration_development_v1.country_terrain_inputs")
    @patch("run_country_framed_integration_development_v1.fetch_country_occurrences")
    @patch("run_country_framed_integration_development_v1.fetch_geoboundaries_country_geometry")
    def test_stage2_candidate_generation_precedes_recent_outcomes_and_gate_logic_is_fixed(
        self,
        mock_geometry,
        mock_historical,
        mock_terrain,
        mock_robust,
        mock_recent,
    ):
        events = []
        digest = "b" * 64

        def geometry_side_effect(code):
            events.append("geometry")
            return CountryLandGeometry(
                country_code=code,
                land_geometry_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
                source_id="geoBoundaries-gbOpen-ADM0-simplified",
                source_version=f"v6.0.0@commit;iso3=XXX;canonical_geojson_sha256={digest};license=CC BY 4.0",
            )

        def historical_side_effect(*args, **kwargs):
            events.append("historical")
            return pd.DataFrame({"latitude": [0, 0, 0, 0, 0], "longitude": [0, 0.01, 0.02, 0.03, 0.04]})

        surface = pd.DataFrame(
            {
                "latitude": np.linspace(10.0, 11.0, 800),
                "longitude": np.linspace(10.0, 11.0, 800),
                "survey_area_id": ["country-KR"] * 800,
            }
        )
        prototypes = pd.DataFrame({"x": range(5)})

        def terrain_side_effect(*args, **kwargs):
            events.append("terrain")
            return surface.copy(), prototypes.copy(), 99

        def robust_side_effect(*args, **kwargs):
            events.append("robust")
            return (
                pd.DataFrame(
                    {
                        "candidate_patch_id": ["country-KR-Z001"],
                        "survey_area_id": ["country-KR"],
                        "latitude": [0.0],
                        "longitude": [0.0],
                    }
                ),
                _Audit(),
            )

        def recent_side_effect(*args, **kwargs):
            events.append("recent")
            return pd.DataFrame({"latitude": [0.0], "longitude": [0.0]})

        mock_geometry.side_effect = geometry_side_effect
        mock_historical.side_effect = historical_side_effect
        mock_terrain.side_effect = terrain_side_effect
        mock_robust.side_effect = robust_side_effect
        mock_recent.side_effect = recent_side_effect

        declarations = []
        for i in range(24):
            declarations.append(
                {
                    "integration_pair_id": i + 1,
                    "speciesKey": 1000 + i,
                    "scientific_name": f"Taxon {i}",
                    "taxon_group": "plant" if i < 12 else "animal",
                    "record_count_stratum": i % 4,
                    "region_cell_index": (i % 12) + 1,
                    "declaration_status": "declared",
                    "selected_country_code": "KR",
                    "geometry_canonical_sha256": digest,
                }
            )
        results, patches, summary = evaluate_frozen_declarations(pd.DataFrame(declarations))

        self.assertEqual(len(results), 24)
        self.assertEqual(len(patches), 24)
        self.assertEqual(events[:5], ["geometry", "historical", "terrain", "robust", "recent"])
        self.assertEqual(events, ["geometry", "historical", "terrain", "robust", "recent"] * 24)
        self.assertTrue(results["candidate_generation_status"].eq("generated").all())
        self.assertTrue(results["temporal_status"].eq("evaluated").all())
        self.assertTrue(results["primary_radius_km"].eq(10.0).all())
        self.assertTrue(results["robust_recall"].eq(1.0).all())
        self.assertTrue(results["random_recall_mean"].eq(0.0).all())
        self.assertTrue(results["robust_minus_random_recall"].eq(1.0).all())
        self.assertEqual(summary["candidate_generation_success_rate"], 1.0)
        self.assertEqual(summary["temporal_evaluability_rate"], 1.0)
        self.assertEqual(summary["mean_robust_minus_random_recall"], 1.0)
        self.assertEqual(summary["plant_mean_robust_minus_random_recall"], 1.0)
        self.assertEqual(summary["animal_mean_robust_minus_random_recall"], 1.0)
        self.assertTrue(summary["candidate_generation_preceded_recent_outcome_fetch"])
        self.assertTrue(summary["development_gate_passed"])
        self.assertFalse(summary["confirmation_v1_taxa_consumed"])
        self.assertFalse(summary["global_candidate_generation_validated"])


if __name__ == "__main__":
    unittest.main()
