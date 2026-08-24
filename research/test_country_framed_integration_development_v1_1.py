import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from country_framed_robust_integration import CountryLandGeometry
from predeclare_country_framed_integration_development_v1_1 import (
    EXPECTED_PROTOCOL_FINGERPRINT,
    SOURCE_COHORT_PATH,
    _protocol as declaration_protocol,
    freeze_declarations_v1_1,
    select_v1_1_development_taxa,
)
from run_country_framed_integration_development_v1_1 import (
    _audit_disjoint_declarations,
    _protocol as runner_protocol,
    evaluate_frozen_declarations_v1_1,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v1_1.json"
V1_IDENTITIES_PATH = ROOT / "validation" / "country_framed_robust_integration_development_v1" / "predeclared_taxon_country_pairs_compact.csv"


class _Audit:
    def as_dict(self):
        return {"prototype_count": 5, "leave_one_out_worlds": 5}


class CountryFramedIntegrationDevelopmentV11Tests(unittest.TestCase):
    def test_protocol_fingerprint_and_single_change_contract(self):
        payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        stored = payload.pop("protocol_fingerprint")
        calculated = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        self.assertEqual(stored, EXPECTED_PROTOCOL_FINGERPRINT)
        self.assertEqual(calculated, EXPECTED_PROTOCOL_FINGERPRINT)
        self.assertEqual(declaration_protocol()["protocol_fingerprint"], EXPECTED_PROTOCOL_FINGERPRINT)
        self.assertEqual(runner_protocol()["protocol_fingerprint"], EXPECTED_PROTOCOL_FINGERPRINT)
        change = payload["candidate_surface_change_from_v1"]
        self.assertEqual(change["geometry_draws_per_country"], 800)
        self.assertFalse(change["terrain_complete_rows_required_exactly_800"])
        self.assertFalse(change["minimum_complete_surface_rows_added"])
        self.assertTrue(change["all_other_integration_components_unchanged"])
        self.assertEqual(payload["frozen_robust_core"]["support_fraction"], 0.025)
        self.assertEqual(payload["outcome_evaluation"]["primary_recovery_radius_km"], 10.0)
        self.assertEqual(payload["outcome_evaluation"]["random_baseline_repetitions"], 200)
        self.assertFalse(payload["claim_boundary"]["v1_taxa_reused"])
        self.assertFalse(payload["claim_boundary"]["confirmation_v1_taxa_consumed"])

    def test_shifted_24_taxa_are_balanced_and_disjoint_from_rejected_v1(self):
        selected = select_v1_1_development_taxa(pd.read_csv(SOURCE_COHORT_PATH))
        self.assertEqual(len(selected), 24)
        self.assertEqual(selected["taxon_group"].value_counts().to_dict(), {"plant": 12, "animal": 12})
        self.assertEqual(
            selected["record_count_stratum"].astype(int).value_counts().sort_index().to_dict(),
            {0: 6, 1: 6, 2: 6, 3: 6},
        )
        for row in selected.itertuples(index=False):
            self.assertEqual(int(row.record_count_stratum), int(row.region_cell_index) % 4)
        v1 = pd.read_csv(V1_IDENTITIES_PATH)
        self.assertTrue(
            set(selected["speciesKey"].astype(int)).isdisjoint(
                set(pd.to_numeric(v1["speciesKey"], errors="raise").astype(int))
            )
        )

    @patch("predeclare_country_framed_integration_development_v1_1.fetch_geoboundaries_country_geometry")
    @patch("predeclare_country_framed_integration_development_v1_1.fetch_country_facet_counts")
    def test_stage1_opens_only_historical_country_and_geometry_inputs(self, mock_counts, mock_geometry):
        mock_counts.return_value = {"JP": 30, "KR": 20}

        def geometry_side_effect(code):
            return CountryLandGeometry(
                country_code=code,
                land_geometry_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
                source_id="geoBoundaries-gbOpen-ADM0-simplified",
                source_version=f"v6.0.0@commit;iso3=XXX;canonical_geojson_sha256={'a' * 64};license=CC BY 4.0",
            )

        mock_geometry.side_effect = geometry_side_effect
        declarations, manifest = freeze_declarations_v1_1()
        self.assertEqual(len(declarations), 24)
        self.assertEqual(mock_counts.call_count, 24)
        self.assertEqual(mock_geometry.call_count, 24)
        self.assertTrue(declarations["declaration_status"].eq("declared").all())
        self.assertFalse(manifest["recent_outcomes_inspected"])
        self.assertFalse(manifest["candidate_generation_run"])
        self.assertFalse(manifest["robust_support_run"])
        self.assertFalse(manifest["random_baseline_run"])
        self.assertFalse(manifest["v1_taxa_reused"])
        self.assertFalse(manifest["confirmation_v1_taxa_consumed"])
        self.assertFalse(manifest["terrain_complete_rows_required_exactly_800"])

    def test_stage2_rejects_any_reintroduced_v1_taxon(self):
        v1 = pd.read_csv(V1_IDENTITIES_PATH).iloc[:1].copy()
        declaration = pd.DataFrame(
            {
                "integration_pair_id": [1],
                "speciesKey": [int(v1.iloc[0]["speciesKey"])],
                "scientific_name": [str(v1.iloc[0]["scientific_name"])],
            }
        )
        # Pad to 24 unique rows so the overlap check, not row count, is exercised.
        rows = [declaration.iloc[0].to_dict()]
        for i in range(1, 24):
            rows.append(
                {
                    "integration_pair_id": i + 1,
                    "speciesKey": 90000000 + i,
                    "scientific_name": f"Synthetic disjoint {i}",
                }
            )
        with self.assertRaisesRegex(ValueError, "reuses rejected v1 taxa"):
            _audit_disjoint_declarations(pd.DataFrame(rows))

    @patch("run_country_framed_integration_development_v1_1.fetch_recent_country_occurrences")
    @patch("run_country_framed_integration_development_v1_1.validated_robust_candidate_patches")
    @patch("run_country_framed_integration_development_v1_1.country_terrain_inputs")
    @patch("run_country_framed_integration_development_v1_1.fetch_country_occurrences")
    @patch("run_country_framed_integration_development_v1_1.fetch_geoboundaries_country_geometry")
    def test_v1_1_accepts_739_complete_rows_and_still_builds_before_recent(
        self,
        mock_geometry,
        mock_historical,
        mock_terrain,
        mock_robust,
        mock_recent,
    ):
        selected = select_v1_1_development_taxa(pd.read_csv(SOURCE_COHORT_PATH))
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
            return pd.DataFrame(
                {"latitude": [0, 0, 0, 0, 0], "longitude": [0, 0.01, 0.02, 0.03, 0.04]}
            )

        surface = pd.DataFrame(
            {
                "latitude": np.linspace(10.0, 11.0, 739),
                "longitude": np.linspace(10.0, 11.0, 739),
                "survey_area_id": ["country-KR"] * 739,
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
        for i, row in enumerate(selected.itertuples(index=False), start=1):
            declarations.append(
                {
                    **row._asdict(),
                    "integration_pair_id": i,
                    "declaration_status": "declared",
                    "selected_country_code": "KR",
                    "geometry_canonical_sha256": digest,
                }
            )
        results, patches, summary = evaluate_frozen_declarations_v1_1(pd.DataFrame(declarations))
        self.assertEqual(len(results), 24)
        self.assertEqual(len(patches), 24)
        self.assertEqual(events, ["geometry", "historical", "terrain", "robust", "recent"] * 24)
        self.assertTrue(results["candidate_generation_status"].eq("generated").all())
        self.assertTrue(results["complete_post_terrain_surface_rows"].eq(739).all())
        self.assertTrue(results["robust_recall"].eq(1.0).all())
        self.assertTrue(results["random_recall_mean"].eq(0.0).all())
        self.assertEqual(summary["candidate_generation_success_rate"], 1.0)
        self.assertEqual(summary["successful_candidate_surface_rows_min"], 739)
        self.assertEqual(summary["only_method_change_from_v1"], "remove_exact_800_complete_post_terrain_surface_requirement")
        self.assertFalse(summary["terrain_complete_rows_required_exactly_800"])
        self.assertFalse(summary["new_minimum_complete_surface_rows_added"])
        self.assertFalse(summary["v1_taxa_reused"])
        self.assertTrue(summary["development_gate_passed"])


if __name__ == "__main__":
    unittest.main()
