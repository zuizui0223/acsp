import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import predeclare_geographic_framing_confirmation_cohort_v1 as sampler
from evaluate_geographic_framing_confirmation_v1 import EXPECTED_PROTOCOL, _protocol, run
from geographic_framing_country_registry_v3 import CountryRegistryDiagnostic


V3_IDENTITY = Path("validation/geographic_framing_development_v3/predeclared_taxon_region_pairs.csv")
V4_IDENTITY = Path("validation/geographic_framing_development_v4/predeclared_taxon_region_pairs.csv")


def _sample() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "pair_id": i + 1,
            "status": "predeclared",
            "taxon_group": "plant" if i < 48 else "animal",
            "speciesKey": 900000 + i,
            "scientific_name": f"Fresh confirmation species {i+1}",
        }
        for i in range(96)
    ])


def _diag(row, *, recent=True, containment=0.99):
    if recent:
        return CountryRegistryDiagnostic(
            pair_id=int(row.pair_id), scientific_name=str(row.scientific_name), species_key=int(row.speciesKey),
            taxon_group=str(row.taxon_group), status="evaluated", historical_record_count=100,
            recent_record_count=100, recent_records_inside_registry=int(round(100 * containment)),
            recent_record_containment=float(containment), historical_country_count=4, recent_country_count=3,
            recent_countries_inside_registry=3, recent_country_containment=1.0, new_recent_country_count=0,
            historical_country_fraction_of_249=4/249, historical_countries="JP;KR;TW;US", recent_countries="JP;KR;TW",
            new_recent_countries="", historical_country_counts_json='{"JP":40,"KR":30,"TW":20,"US":10}',
            recent_country_counts_json='{"JP":50,"KR":30,"TW":20}', failure_reason="",
        )
    return CountryRegistryDiagnostic(
        pair_id=int(row.pair_id), scientific_name=str(row.scientific_name), species_key=int(row.speciesKey),
        taxon_group=str(row.taxon_group), status="zero_recent_country_records", historical_record_count=100,
        recent_record_count=0, recent_records_inside_registry=0, recent_record_containment=0.0,
        historical_country_count=4, recent_country_count=0, recent_countries_inside_registry=0,
        recent_country_containment=0.0, new_recent_country_count=0, historical_country_fraction_of_249=4/249,
        historical_countries="JP;KR;TW;US", recent_countries="", new_recent_countries="",
        historical_country_counts_json='{"JP":40,"KR":30,"TW":20,"US":10}', recent_country_counts_json="{}",
        failure_reason="no valid recent country facet counts",
    )


class GeographicFramingConfirmationV1Tests(unittest.TestCase):
    def test_protocol_freeze_and_development_identity_hashes(self):
        protocol = _protocol()
        self.assertEqual(protocol["protocol_fingerprint"], EXPECTED_PROTOCOL)
        self.assertEqual(protocol["representation"]["historical_year_range"], [1900, 2020])
        self.assertEqual(protocol["representation"]["heldout_year_range"], [2021, 2025])
        self.assertFalse(protocol["representation"]["country_expansion"])
        self.assertFalse(protocol["representation"]["higher_taxon_fallback"])
        self.assertEqual(protocol["cohort"]["seed"], 2026082305)
        self.assertEqual(protocol["confirmation_gate"]["historical_registry_availability_min"], 0.95)
        self.assertEqual(protocol["confirmation_gate"]["temporal_evaluability_overall_min"], 0.90)
        self.assertEqual(protocol["confirmation_gate"]["conditional_containment_overall_min"], 0.97)
        self.assertEqual(hashlib.sha256(V3_IDENTITY.read_bytes()).hexdigest(), protocol["cohort"]["development_v3_identity_sha256"])
        self.assertEqual(hashlib.sha256(V4_IDENTITY.read_bytes()).hexdigest(), protocol["cohort"]["development_v4_identity_sha256"])
        self.assertIn(str(V3_IDENTITY), protocol["exclusion_files"])
        self.assertIn(str(V4_IDENTITY), protocol["exclusion_files"])

    def test_sampler_marks_fresh_confirmation_without_opening_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sampler.base, "run", return_value={"status": "ready"}) as base_run:
            result = sampler.run(Path(tmp))
        self.assertEqual(base_run.call_args.args[0], sampler.PROTOCOL)
        self.assertEqual(result["purpose"], "geographic_framing_country_registry_fresh_confirmation_v1")
        self.assertTrue(result["fresh_confirmation_cohort"])
        self.assertTrue(result["development_v3_taxa_excluded"])
        self.assertTrue(result["development_v4_taxa_excluded"])
        self.assertFalse(result["temporal_country_outcomes_inspected"])
        self.assertFalse(result["confirmation_outcomes_opened"])
        self.assertFalse(result["candidate_generation_run"])
        self.assertFalse(result["robust_support_run"])
        self.assertFalse(result["taxon_replacement_after_declaration_allowed"])

    def test_temporal_nonobservability_reduces_yield_not_conditional_containment(self):
        sample = _sample()
        with tempfile.TemporaryDirectory() as tmp:
            sample_file = Path(tmp) / "sample.csv"
            output = Path(tmp) / "out"
            sample.to_csv(sample_file, index=False)
            def side_effect(row):
                return _diag(row, recent=int(row.pair_id) > 4, containment=0.99)
            with patch("evaluate_geographic_framing_confirmation_v1.evaluate_country_registry_taxon", side_effect=side_effect):
                summary = run(sample_file, output)
        self.assertEqual(summary["taxa_in_yield_denominator"], 96)
        self.assertEqual(summary["historical_registry_available_taxa"], 96)
        self.assertEqual(summary["temporally_evaluable_taxa"], 92)
        self.assertAlmostEqual(summary["temporal_evaluability"], 92/96)
        self.assertAlmostEqual(summary["conditional_mean_recent_record_containment"], 0.99)
        self.assertTrue(summary["confirmation_gate_passed"])
        self.assertTrue(summary["fresh_confirmation_taxa_consumed"])
        self.assertFalse(summary["candidate_generation_run"])
        self.assertFalse(summary["robust_support_run"])
        self.assertFalse(summary["global_name_only_acsp_validated"])

    def test_development_taxon_reuse_is_rejected_before_outcome_fetch(self):
        sample = _sample()
        old_name = pd.read_csv(V3_IDENTITY)["scientific_name"].astype(str).iloc[0]
        sample.loc[0, "scientific_name"] = old_name
        with tempfile.TemporaryDirectory() as tmp:
            sample_file = Path(tmp) / "sample.csv"
            sample.to_csv(sample_file, index=False)
            with patch("evaluate_geographic_framing_confirmation_v1.evaluate_country_registry_taxon") as evaluator:
                with self.assertRaisesRegex(ValueError, "overlaps v3"):
                    run(sample_file, Path(tmp) / "out")
                evaluator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
