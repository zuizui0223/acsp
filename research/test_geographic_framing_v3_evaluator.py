import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from evaluate_geographic_framing_development_v3 import EXPECTED_PROTOCOL, _protocol, run
from geographic_framing_country_registry_v3 import CountryRegistryDiagnostic


def _sample() -> pd.DataFrame:
    rows = []
    for i in range(96):
        rows.append({
            "pair_id": i + 1,
            "status": "predeclared",
            "taxon_group": "plant" if i < 48 else "animal",
            "speciesKey": 1000 + i,
            "scientific_name": f"Example species {i+1}",
        })
    return pd.DataFrame(rows)


def _diagnostic(row, containment=1.0, status="evaluated"):
    historical = "JP;US" if status == "evaluated" else ""
    recent = "JP" if status == "evaluated" else ""
    return CountryRegistryDiagnostic(
        pair_id=int(row.pair_id), scientific_name=str(row.scientific_name),
        species_key=int(row.speciesKey), taxon_group=str(row.taxon_group), status=status,
        historical_record_count=10 if status == "evaluated" else 0,
        recent_record_count=5 if status == "evaluated" else 0,
        recent_records_inside_registry=int(round(5 * containment)) if status == "evaluated" else 0,
        recent_record_containment=float(containment if status == "evaluated" else 0.0),
        historical_country_count=2 if status == "evaluated" else 0,
        recent_country_count=1 if status == "evaluated" else 0,
        recent_countries_inside_registry=1 if status == "evaluated" else 0,
        recent_country_containment=1.0 if status == "evaluated" else 0.0,
        new_recent_country_count=0,
        historical_country_fraction_of_249=2/249 if status == "evaluated" else 0.0,
        historical_countries=historical, recent_countries=recent, new_recent_countries="",
        historical_country_counts_json='{"JP":8,"US":2}' if status == "evaluated" else "{}",
        recent_country_counts_json='{"JP":5}' if status == "evaluated" else "{}",
        failure_reason="" if status == "evaluated" else "unavailable",
    )


class CountryRegistryV3EvaluatorTests(unittest.TestCase):
    def test_protocol_is_frozen(self):
        protocol = _protocol()
        self.assertEqual(protocol["protocol_fingerprint"], EXPECTED_PROTOCOL)
        self.assertEqual(protocol["registry"]["historical_year_range"], [1900, 2020])
        self.assertEqual(protocol["registry"]["heldout_year_range"], [2021, 2025])
        self.assertFalse(protocol["registry"]["neighbour_country_expansion"])
        self.assertFalse(protocol["breadth_contract"]["compactness_gate"])

    def test_all_96_taxa_have_equal_denominator_weight(self):
        sample = _sample()
        with tempfile.TemporaryDirectory() as tmp:
            sample_file = Path(tmp) / "sample.csv"
            output = Path(tmp) / "out"
            sample.to_csv(sample_file, index=False)
            def side_effect(row):
                return _diagnostic(row, 0.0 if int(row.pair_id) == 1 else 1.0,
                                   "provider_failed" if int(row.pair_id) == 1 else "evaluated")
            with patch("evaluate_geographic_framing_development_v3.evaluate_country_registry_taxon", side_effect=side_effect):
                summary = run(sample_file, output)
        self.assertEqual(summary["taxa_in_denominator"], 96)
        self.assertEqual(summary["analyzable_taxa"], 95)
        self.assertAlmostEqual(summary["mean_taxon_recent_record_country_containment"], 95/96)
        self.assertFalse(summary["candidate_generation_run"])
        self.assertFalse(summary["robust_support_run"])

    def test_unexpected_failure_is_retained_as_zero(self):
        sample = _sample()
        with tempfile.TemporaryDirectory() as tmp:
            sample_file = Path(tmp) / "sample.csv"
            output = Path(tmp) / "out"
            sample.to_csv(sample_file, index=False)
            def side_effect(row):
                if int(row.pair_id) == 1:
                    raise RuntimeError("boom")
                return _diagnostic(row)
            with patch("evaluate_geographic_framing_development_v3.evaluate_country_registry_taxon", side_effect=side_effect):
                summary = run(sample_file, output)
                diagnostics = pd.read_csv(output / "country_registry_v3_taxon_diagnostics.csv")
        first = diagnostics.loc[diagnostics["pair_id"] == 1].iloc[0]
        self.assertEqual(first.status, "unexpected_evaluator_failure")
        self.assertEqual(first.recent_record_containment, 0.0)
        self.assertEqual(summary["taxa_in_denominator"], 96)


if __name__ == "__main__":
    unittest.main()
