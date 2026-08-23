import unittest
from unittest.mock import patch

import pandas as pd

from geographic_framing_country_registry_v3 import (
    HISTORICAL_YEARS,
    RECENT_YEARS,
    _country_counts_from_payload,
    evaluate_country_registry_taxon,
    fetch_country_facet_counts,
)


class CountryRegistryV3Tests(unittest.TestCase):
    def test_country_facet_parser_keeps_only_positive_two_letter_codes(self):
        payload = {
            "facets": [
                {
                    "field": "COUNTRY",
                    "counts": [
                        {"name": "JP", "count": 10},
                        {"name": "US", "count": 4},
                        {"name": "", "count": 2},
                        {"name": "ZZZ", "count": 3},
                        {"name": "FR", "count": 0},
                    ],
                }
            ]
        }
        self.assertEqual(_country_counts_from_payload(payload), {"JP": 10, "US": 4})

    def test_fetch_uses_fixed_temporal_window_and_country_facet(self):
        payload = {"facets": [{"field": "COUNTRY", "counts": [{"name": "JP", "count": 7}]}]}
        with patch("geographic_framing_country_registry_v3.get_json", return_value=payload) as get:
            counts = fetch_country_facet_counts(123, HISTORICAL_YEARS)
        self.assertEqual(counts, {"JP": 7})
        params = get.call_args.args[1]
        self.assertEqual(params["taxonKey"], 123)
        self.assertEqual(params["year"], "1900,2020")
        self.assertEqual(params["limit"], 0)
        self.assertEqual(params["facet"], "country")
        self.assertEqual(params["facetLimit"], 300)
        self.assertEqual(params["hasCoordinate"], "true")
        self.assertEqual(params["hasGeospatialIssue"], "false")
        self.assertEqual(params["occurrenceStatus"], "PRESENT")

    def test_recent_record_containment_is_count_weighted(self):
        row = pd.Series({"pair_id": 1, "scientific_name": "Example species", "speciesKey": 10, "taxon_group": "plant"})
        historical = {"JP": 100, "US": 20}
        recent = {"JP": 80, "US": 10, "KR": 10}
        with patch(
            "geographic_framing_country_registry_v3.fetch_country_facet_counts",
            side_effect=[historical, recent],
        ) as fetch:
            result = evaluate_country_registry_taxon(row)
        self.assertEqual(fetch.call_args_list[0].args[1], HISTORICAL_YEARS)
        self.assertEqual(fetch.call_args_list[1].args[1], RECENT_YEARS)
        self.assertEqual(result.status, "evaluated")
        self.assertAlmostEqual(result.recent_record_containment, 0.9)
        self.assertAlmostEqual(result.recent_country_containment, 2 / 3)
        self.assertEqual(result.new_recent_country_count, 1)
        self.assertEqual(result.new_recent_countries, "KR")

    def test_zero_historical_registry_is_retained_as_zero_without_recent_query(self):
        row = pd.Series({"pair_id": 1, "scientific_name": "Example species", "speciesKey": 10, "taxon_group": "animal"})
        with patch(
            "geographic_framing_country_registry_v3.fetch_country_facet_counts",
            return_value={},
        ) as fetch:
            result = evaluate_country_registry_taxon(row)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result.status, "zero_historical_registry")
        self.assertEqual(result.recent_record_containment, 0.0)

    def test_recent_provider_failure_is_zero_and_does_not_expand_registry(self):
        row = pd.Series({"pair_id": 1, "scientific_name": "Example species", "speciesKey": 10, "taxon_group": "animal"})
        with patch(
            "geographic_framing_country_registry_v3.fetch_country_facet_counts",
            side_effect=[{"JP": 5}, RuntimeError("offline")],
        ):
            result = evaluate_country_registry_taxon(row)
        self.assertEqual(result.status, "recent_provider_failed")
        self.assertEqual(result.historical_countries, "JP")
        self.assertEqual(result.recent_record_containment, 0.0)
        self.assertIn("offline", result.failure_reason)


if __name__ == "__main__":
    unittest.main()
