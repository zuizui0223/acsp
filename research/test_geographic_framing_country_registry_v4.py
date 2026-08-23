import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import predeclare_geographic_framing_country_registry_v4_cohort as sampler
from evaluate_geographic_framing_development_v4 import EXPECTED_PROTOCOL, _protocol, run
from geographic_framing_country_registry_v3 import CountryRegistryDiagnostic


def _sample() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "pair_id": i + 1,
            "status": "predeclared",
            "taxon_group": "plant" if i < 48 else "animal",
            "speciesKey": 5000 + i,
            "scientific_name": f"V4 species {i+1}",
        }
        for i in range(96)
    ])


def _diag(row, *, recent=True, containment=0.98):
    if recent:
        return CountryRegistryDiagnostic(
            pair_id=int(row.pair_id), scientific_name=str(row.scientific_name), species_key=int(row.speciesKey),
            taxon_group=str(row.taxon_group), status="evaluated", historical_record_count=100,
            recent_record_count=50, recent_records_inside_registry=int(round(50 * containment)),
            recent_record_containment=float(containment), historical_country_count=3, recent_country_count=2,
            recent_countries_inside_registry=2, recent_country_containment=1.0, new_recent_country_count=0,
            historical_country_fraction_of_249=3/249, historical_countries="JP;KR;US", recent_countries="JP;KR",
            new_recent_countries="", historical_country_counts_json='{"JP":50,"KR":25,"US":25}',
            recent_country_counts_json='{"JP":30,"KR":20}', failure_reason="",
        )
    return CountryRegistryDiagnostic(
        pair_id=int(row.pair_id), scientific_name=str(row.scientific_name), species_key=int(row.speciesKey),
        taxon_group=str(row.taxon_group), status="zero_recent_country_records", historical_record_count=100,
        recent_record_count=0, recent_records_inside_registry=0, recent_record_containment=0.0,
        historical_country_count=3, recent_country_count=0, recent_countries_inside_registry=0,
        recent_country_containment=0.0, new_recent_country_count=0, historical_country_fraction_of_249=3/249,
        historical_countries="JP;KR;US", recent_countries="", new_recent_countries="",
        historical_country_counts_json='{"JP":50,"KR":25,"US":25}', recent_country_counts_json="{}",
        failure_reason="no valid recent country facet counts",
    )


class CountryRegistryV4Tests(unittest.TestCase):
    def test_protocol_is_frozen_and_representation_unchanged(self):
        protocol = _protocol()
        self.assertEqual(protocol["protocol_fingerprint"], EXPECTED_PROTOCOL)
        self.assertEqual(protocol["representation"]["historical_year_range"], [1900, 2020])
        self.assertEqual(protocol["representation"]["heldout_year_range"], [2021, 2025])
        self.assertFalse(protocol["representation"]["country_expansion"])
        self.assertFalse(protocol["representation"]["higher_taxon_fallback"])
        self.assertEqual(protocol["cohort"]["seed"], 2026082304)
        self.assertEqual(protocol["cohort"]["prior_96_exclusion_run"], 32335791948)

    def test_sampler_wrapper_uses_v4_protocol_and_never_marks_fresh_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sampler.base, "run", return_value={"status": "ready"}) as base_run:
            result = sampler.run(Path(tmp))
        self.assertEqual(base_run.call_args.args[0], sampler.PROTOCOL_V4)
        self.assertEqual(result["purpose"], "geographic_framing_v4_development_only")
        self.assertTrue(result["previous_96_taxa_excluded"])
        self.assertFalse(result["temporal_country_outcomes_inspected"])
        self.assertFalse(result["fresh_confirmation_cohort"])

    def test_temporal_nonobservability_reduces_yield_but_not_conditional_containment(self):
        sample = _sample()
        with tempfile.TemporaryDirectory() as tmp:
            sample_file = Path(tmp) / "sample.csv"
            output = Path(tmp) / "out"
            sample.to_csv(sample_file, index=False)
            def side_effect(row):
                return _diag(row, recent=int(row.pair_id) > 4, containment=0.98)
            with patch("evaluate_geographic_framing_development_v4.evaluate_country_registry_taxon", side_effect=side_effect):
                summary = run(sample_file, output)
        self.assertEqual(summary["taxa_in_yield_denominator"], 96)
        self.assertEqual(summary["historical_registry_available_taxa"], 96)
        self.assertEqual(summary["temporally_evaluable_taxa"], 92)
        self.assertAlmostEqual(summary["temporal_evaluability"], 92/96)
        self.assertAlmostEqual(summary["conditional_mean_recent_record_containment"], 0.98)
        self.assertTrue(summary["country_representation_changed_from_v3"] is False)

    def test_zero_historical_registry_fails_both_yield_layers(self):
        sample = _sample()
        with tempfile.TemporaryDirectory() as tmp:
            sample_file = Path(tmp) / "sample.csv"
            output = Path(tmp) / "out"
            sample.to_csv(sample_file, index=False)
            def side_effect(row):
                if int(row.pair_id) != 1:
                    return _diag(row)
                return CountryRegistryDiagnostic(
                    pair_id=1, scientific_name=str(row.scientific_name), species_key=int(row.speciesKey), taxon_group=str(row.taxon_group),
                    status="zero_historical_registry", historical_record_count=0, recent_record_count=0,
                    recent_records_inside_registry=0, recent_record_containment=0.0, historical_country_count=0,
                    recent_country_count=0, recent_countries_inside_registry=0, recent_country_containment=0.0,
                    new_recent_country_count=0, historical_country_fraction_of_249=0.0, historical_countries="",
                    recent_countries="", new_recent_countries="", historical_country_counts_json="{}",
                    recent_country_counts_json="{}", failure_reason="no historical registry",
                )
            with patch("evaluate_geographic_framing_development_v4.evaluate_country_registry_taxon", side_effect=side_effect):
                summary = run(sample_file, output)
        self.assertAlmostEqual(summary["historical_registry_availability"], 95/96)
        self.assertAlmostEqual(summary["temporal_evaluability"], 95/96)


if __name__ == "__main__":
    unittest.main()
