import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, call, patch

import pandas as pd
from shapely import wkt
from shapely.geometry import Point

import country_framed_robust_integration as integration


PROTOCOL = Path("validation/acsp_geographic_framing_robust_integration_mechanics_v1.json")
EXPECTED_PROTOCOL = "71641ccc809f63aa84ed7dc404a027a77b611b8ff7fb097c4bb1c43c35df1a6b"


class _Audit:
    def as_dict(self):
        return {
            "support_fraction": 0.025,
            "support_world_dtype": "float32",
            "patch_merge_distance_m": 1000.0,
        }


def _geometry(code: str) -> integration.CountryLandGeometry:
    return integration.CountryLandGeometry(
        country_code=code,
        land_geometry_wkt="POLYGON((0 0,2 0,2 1,0 1,0 0))",
        source_id="fixture-country-boundaries",
        source_version="v1",
    )


def _occurrences() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "latitude": [0.1, 0.2, 0.3, 0.4, 0.5],
            "longitude": [0.1, 0.2, 0.3, 0.4, 0.5],
        }
    )


def _terrain(area_id: str) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    surface = pd.DataFrame(
        {
            "latitude": [0.25, 0.75],
            "longitude": [0.25, 1.75],
            "survey_area_id": [area_id, area_id],
            "elevation": [1.0, 2.0],
            "slope": [1.0, 2.0],
            "aspect_sin": [0.0, 0.1],
            "aspect_cos": [1.0, 0.9],
            "roughness": [1.0, 2.0],
            "tpi": [0.0, 0.1],
        }
    )
    prototypes = surface.iloc[:1].copy()
    return surface, prototypes, 12345


class CountryFramedRobustIntegrationTests(unittest.TestCase):
    def test_mechanics_protocol_fingerprint_and_boundaries_are_frozen(self):
        payload = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        stored = payload.pop("protocol_fingerprint")
        calculated = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(stored, EXPECTED_PROTOCOL)
        self.assertEqual(calculated, EXPECTED_PROTOCOL)
        self.assertEqual(
            payload["upstream_framing"]["country_membership_rule"],
            "past_observed_focal_species_countries_only",
        )
        self.assertFalse(payload["upstream_framing"]["country_expansion"])
        self.assertFalse(payload["upstream_framing"]["higher_taxon_fallback"])
        self.assertFalse(payload["upstream_framing"]["local_occurrence_component_fallback"])
        self.assertTrue(
            payload["country_geometry_boundary"][
                "geometry_must_be_independent_of_focal_species_occurrence_envelope"
            ]
        )
        self.assertFalse(
            payload["country_geometry_boundary"]["provider_selection_frozen_for_scientific_evaluation"]
        )
        self.assertFalse(payload["country_geometry_boundary"]["production_provider_selected"])
        self.assertFalse(payload["data_boundary"]["confirmation_v1_taxa_allowed_for_tuning"])
        self.assertFalse(payload["mechanical_gate"]["integrated_scientific_outcomes_opened"])

    def test_external_country_surface_is_deterministic_and_inside_polygon(self):
        spec = _geometry("JP")
        first, first_seed = integration.sample_country_land_surface(spec, n_points=40)
        second, second_seed = integration.sample_country_land_surface(spec, n_points=40)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first_seed, second_seed)
        self.assertEqual(set(first["survey_area_id"]), {"country-JP"})
        polygon = wkt.loads(spec.land_geometry_wkt)
        self.assertTrue(
            all(
                polygon.covers(Point(float(row.longitude), float(row.latitude)))
                for row in first.itertuples()
            )
        )

    def test_country_geometry_requires_explicit_provenance(self):
        missing_source = integration.CountryLandGeometry(
            country_code="JP",
            land_geometry_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
            source_id="",
            source_version="v1",
        )
        with self.assertRaisesRegex(ValueError, "provenance"):
            integration.sample_country_land_surface(missing_source, n_points=5)

    @patch("country_framed_robust_integration.fetch_country_facet_counts")
    def test_historical_country_registry_is_the_sole_sorted_outer_selector(self, mock_counts):
        mock_counts.return_value = {"US": 2, "JP": 10, "KR": 4}
        codes = integration.historical_country_codes_for_taxon(123)
        self.assertEqual(codes, ("JP", "KR", "US"))
        mock_counts.assert_called_once_with(123, integration.HISTORICAL_YEARS)

    @patch("country_framed_robust_integration.validated_robust_candidate_patches")
    @patch("country_framed_robust_integration.country_terrain_inputs")
    @patch("country_framed_robust_integration.fetch_country_occurrences")
    @patch("country_framed_robust_integration.historical_country_codes_for_taxon")
    @patch("country_framed_robust_integration.match_gbif_species")
    def test_integration_wires_confirmed_countries_to_unchanged_robust_core(
        self,
        mock_match,
        mock_countries,
        mock_occurrences,
        mock_terrain,
        mock_robust,
    ):
        mock_match.return_value = {
            "taxon_key": 123,
            "requested_name": "Example species",
            "matched_name": "Example species",
            "match_type": "EXACT",
            "confidence": 100,
            "status": "ACCEPTED",
        }
        mock_countries.return_value = ("JP", "KR")
        mock_occurrences.return_value = _occurrences()
        mock_terrain.side_effect = lambda rows, spec: _terrain(f"country-{spec.normalized_code()}")

        def robust_side_effect(surface, prototypes, **kwargs):
            area = str(surface["survey_area_id"].iloc[0])
            return (
                pd.DataFrame(
                    {
                        "candidate_patch_id": [f"{area}-P001"],
                        "survey_area_id": [area],
                        "latitude": [0.5],
                        "longitude": [0.5],
                    }
                ),
                _Audit(),
            )

        mock_robust.side_effect = robust_side_effect
        provider = Mock(side_effect=lambda code: _geometry(code))

        patches, audit = integration.integrate_country_framed_robust_patches(
            "Example species", provider
        )

        self.assertEqual(provider.call_args_list, [call("JP"), call("KR")])
        self.assertEqual(
            mock_occurrences.call_args_list,
            [call(123, "JP"), call(123, "KR")],
        )
        self.assertEqual(mock_robust.call_count, 2)
        for robust_call in mock_robust.call_args_list:
            self.assertEqual(robust_call.kwargs["area_col"], "survey_area_id")
            self.assertEqual(
                tuple(robust_call.kwargs["feature_columns"]),
                integration.ROBUST_TERRAIN_FEATURES,
            )
        self.assertEqual(set(patches["framing_country_code"]), {"JP", "KR"})
        self.assertEqual(patches["survey_area_id"].nunique(), 2)
        forbidden = {
            "priority_rank",
            "priority_score",
            "zone_score",
            "integrated_score",
            "sdm_suitability",
            "route_score",
        }
        self.assertTrue(forbidden.isdisjoint(patches.columns))
        self.assertEqual(audit["declared_country_codes"], ["JP", "KR"])
        self.assertTrue(audit["country_membership_is_sole_outer_selector"])
        self.assertTrue(audit["country_geometry_is_external_and_occurrence_independent"])
        self.assertFalse(audit["local_occurrence_envelope_fallback"])
        self.assertFalse(audit["country_expansion_or_higher_taxon_fallback"])
        self.assertFalse(audit["ranking_or_topk_in_candidate_membership"])
        self.assertFalse(audit["sdm_ssdm_in_candidate_membership"])
        self.assertFalse(audit["movement_route_day_budget_in_candidate_membership"])
        self.assertFalse(audit["validated_japan_adapter_changed"])
        self.assertFalse(audit["independently_validated_integration"])
        self.assertTrue(audit["development_only"])

    @patch("country_framed_robust_integration.validated_robust_candidate_patches")
    @patch("country_framed_robust_integration.country_terrain_inputs")
    @patch("country_framed_robust_integration.fetch_country_occurrences")
    @patch("country_framed_robust_integration.historical_country_codes_for_taxon")
    @patch("country_framed_robust_integration.match_gbif_species")
    def test_geometry_provider_failure_is_explicit_and_does_not_expand_frame(
        self,
        mock_match,
        mock_countries,
        mock_occurrences,
        mock_terrain,
        mock_robust,
    ):
        mock_match.return_value = {"taxon_key": 123, "requested_name": "Example species"}
        mock_countries.return_value = ("JP", "KR")
        mock_occurrences.return_value = _occurrences()
        mock_terrain.return_value = _terrain("country-JP")
        mock_robust.return_value = (
            pd.DataFrame(
                {
                    "candidate_patch_id": ["country-JP-P001"],
                    "survey_area_id": ["country-JP"],
                }
            ),
            _Audit(),
        )

        def provider(code):
            if code == "KR":
                raise RuntimeError("provider unavailable")
            return _geometry(code)

        patches, audit = integration.integrate_country_framed_robust_patches(
            "Example species", provider
        )

        self.assertEqual(audit["declared_country_codes"], ["JP", "KR"])
        self.assertEqual(audit["evaluated_country_count"], 1)
        self.assertEqual(audit["skipped_country_count"], 1)
        self.assertEqual(audit["country_status"][1]["status"], "skipped_geometry_provider_failure")
        self.assertEqual(mock_robust.call_count, 1)
        self.assertEqual(len(patches), 1)
        self.assertFalse(audit["local_occurrence_envelope_fallback"])
        self.assertFalse(audit["country_expansion_or_higher_taxon_fallback"])

    @patch("country_framed_robust_integration.historical_country_codes_for_taxon")
    @patch("country_framed_robust_integration.match_gbif_species")
    def test_empty_confirmed_registry_fails_without_all_world_fallback(
        self, mock_match, mock_countries
    ):
        mock_match.return_value = {"taxon_key": 123, "requested_name": "Example species"}
        mock_countries.return_value = ()
        provider = Mock()
        with self.assertRaisesRegex(ValueError, "no fallback"):
            integration.integrate_country_framed_robust_patches("Example species", provider)
        provider.assert_not_called()

    @patch("country_framed_robust_integration.historical_country_codes_for_taxon")
    @patch("country_framed_robust_integration.match_gbif_species")
    def test_provider_cannot_substitute_a_different_country(self, mock_match, mock_countries):
        mock_match.return_value = {"taxon_key": 123, "requested_name": "Example species"}
        mock_countries.return_value = ("JP",)
        provider = Mock(return_value=_geometry("KR"))
        patches, audit = integration.integrate_country_framed_robust_patches(
            "Example species", provider
        )
        self.assertTrue(patches.empty)
        self.assertEqual(audit["declared_country_codes"], ["JP"])
        self.assertEqual(audit["evaluated_country_count"], 0)
        self.assertEqual(audit["skipped_country_count"], 1)
        self.assertEqual(audit["country_status"][0]["status"], "skipped_geometry_provider_failure")
        self.assertIn("requested country JP", audit["country_status"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
