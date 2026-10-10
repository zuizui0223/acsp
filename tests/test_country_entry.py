import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from acsp.discovery import country_entry as entry
from acsp.discovery.cli import build_parser
from acsp.discovery.country_frames import plan_automatic_global_country


def facet(counts):
    return {"facets": [{"field": "COUNTRY", "counts": [{"name": k, "count": v} for k, v in counts.items()]}]}


class CountryEntryTests(unittest.TestCase):
    def plan(self, counts, country=""):
        with patch.object(entry, "match_species", return_value={"usageKey": 123, "scientificName": "Synthetic species", "confidence": 100}), patch.object(entry, "_get_json", return_value=facet(counts)) as get:
            result = entry.plan_country_for_species("Synthetic species", country=country, session=Mock())
        return result, get.call_args

    def test_packaged_coverage_matches_frozen_source(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("acsp_geoboundaries_v6_adm0_coverage_v1.json", "iso3166_alpha2_to_alpha3_pycountry_24_6_1.json"):
            self.assertEqual(json.loads((root / "validation" / name).read_text(encoding="utf-8")), json.loads((root / "acsp/discovery/data" / name).read_text(encoding="utf-8")))
        mapping, supported = entry._provider_inventory()
        self.assertEqual(len(mapping), 249)
        self.assertIn("JP", supported)

    def test_automatic_uses_frozen_rule_and_only_historical_facets(self):
        result, call = self.plan({"JP": 8, "TW": 20})
        self.assertEqual(result["country_plan"]["selected_country_code"], "TW")
        self.assertEqual(call.args[2]["year"], "1900,2020")
        self.assertEqual(call.args[2]["limit"], 0)
        self.assertEqual(call.args[2]["facetLimit"], 300)
        self.assertNotIn("country", call.args[2])
        self.assertEqual(result["historical_country_counts"], {"JP": 8, "TW": 20})
        for flag in ("candidate_generation_run", "country_geometry_opened", "heldout_2021_2025_opened", "field_outcomes_used"):
            self.assertIs(result[flag], False)

    def test_equal_counts_match_confirmed_tie_break(self):
        counts = {"JP": 8, "TW": 8}
        result, _ = self.plan(counts)
        _, supported = entry._provider_inventory()
        expected = plan_automatic_global_country(counts, provider_supported_country_codes=supported, historical_min_count=5, tie_break_seed=2026090701)
        self.assertEqual(result["country_plan"], expected.as_dict())

    def test_explicit_target_never_substituted(self):
        for counts in ({"JP": 5, "TW": 100}, {"JP": 4, "TW": 100}, {"TW": 100}):
            with self.subTest(counts=counts):
                result, _ = self.plan(counts, country="jp")
                plan = result["country_plan"]
                self.assertEqual(result["requested_country"], "JP")
                self.assertFalse(plan["country_substitution_after_target_declaration"])
                self.assertEqual(plan["selected_country_code"], "JP" if counts.get("JP", 0) >= 5 else None)
                self.assertEqual(plan["state"], "READY" if counts.get("JP", 0) >= 5 else "INSUFFICIENT_HISTORICAL_EVIDENCE")

    def test_unsupported_country_retains_separate_state(self):
        mapping, supported = entry._provider_inventory()
        country = sorted(set(mapping) - supported)[0]
        result, _ = self.plan({country: 100, "JP": 20}, country=country)
        self.assertEqual(result["status"], "PROVIDER_UNSUPPORTED")
        self.assertIsNone(result["country_plan"]["selected_country_code"])

    def test_invalid_country_rejected_before_network(self):
        with patch.object(entry, "match_species") as match:
            with self.assertRaisesRegex(ValueError, "ISO"):
                entry.plan_country_for_species("Synthetic species", country="not-a-country")
        match.assert_not_called()

    def test_empty_evidence_is_not_missing_provider_response(self):
        result, _ = self.plan({})
        self.assertEqual(result["status"], "NO_HISTORICAL_COUNTRY")
        self.assertEqual(entry._country_counts({"count": 0, "facets": []}), {})
        for bad in ({}, {"facets": []}, facet({"JP": -1}), facet({"JP": True}), facet({"JP": "five"})):
            with self.subTest(payload=bad), self.assertRaises(entry.CountryPlanningProviderError):
                entry._country_counts(bad)

    def test_transport_failure_is_not_an_abstention(self):
        with patch.object(entry, "match_species", return_value={"usageKey": 123}), patch.object(entry, "_get_json", side_effect=requests.ConnectionError("offline")):
            with self.assertRaises(requests.ConnectionError):
                entry.plan_country_for_species("Synthetic species", session=Mock())

    def test_coverage_tampering_is_rejected(self):
        with patch.object(entry, "COVERAGE_FINGERPRINT", "bad"), self.assertRaisesRegex(ValueError, "coverage contract"):
            entry._provider_inventory()

    def test_cli_writes_plan_and_distinguishes_nonready_exit(self):
        for status, expected_code in (("READY", 0), ("NO_HISTORICAL_COUNTRY", 2)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "plan.json"
                args = build_parser().parse_args(["plan-country", "Synthetic species", "--country", "JP", "--out", str(out)])
                with patch.object(entry, "plan_country_for_species", return_value={"status": status, "candidate_generation_run": False}) as plan, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(args.func(args), expected_code)
                plan.assert_called_once_with("Synthetic species", country="JP")
                self.assertFalse(json.loads(out.read_text())["candidate_generation_run"])
                with patch.object(entry, "plan_country_for_species") as plan, self.assertRaises(SystemExit):
                    args.func(args)
                plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
