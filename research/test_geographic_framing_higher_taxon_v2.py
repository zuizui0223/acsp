import unittest
from unittest.mock import patch

import pandas as pd

from geographic_framing_higher_taxon_v2 import (
    FRAMING_METHOD_V2,
    HigherTaxonPriorAudit,
    fetch_nonfocal_higher_taxon_prior,
    infer_higher_taxon_prior_frames,
)


class HigherTaxonFramingV2Tests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "species_key": 10,
            "scientific_name": "Example focal Author",
            "canonical_name": "Example focal",
            "genus_key": 100,
            "family_key": 200,
        }
        self.bounds = (138.0, 34.0, 140.0, 36.0)

    def test_genus_prior_excludes_focal_records_before_frame_construction(self):
        genus_records = [
            {"speciesKey": 10, "scientificName": "Example focal Author", "decimalLatitude": 35.0, "decimalLongitude": 139.0},
            {"speciesKey": 11, "scientificName": "Example other", "decimalLatitude": 35.1, "decimalLongitude": 139.1},
            {"speciesKey": 12, "scientificName": "Example another", "decimalLatitude": 35.2, "decimalLongitude": 139.2},
        ]
        with patch("geographic_framing_higher_taxon_v2.focal_species_metadata", return_value=self.metadata), patch(
            "geographic_framing_higher_taxon_v2._query_prior_records", return_value=genus_records
        ) as query:
            prior, audit = fetch_nonfocal_higher_taxon_prior(
                10, self.bounds, focal_scientific_name="Example focal Author"
            )
        self.assertEqual(query.call_count, 1)
        self.assertEqual(query.call_args.args[0], 100)
        self.assertEqual(audit.status, "ready")
        self.assertEqual(audit.prior_rank_used, "GENUS")
        self.assertEqual(audit.focal_records_removed, 1)
        self.assertEqual(len(prior), 2)
        self.assertFalse(audit.focal_training_coordinates_used)
        self.assertFalse(audit.focal_heldout_coordinates_used)

    def test_family_fallback_occurs_only_after_zero_usable_genus(self):
        genus_records = [
            {"speciesKey": 10, "scientificName": "Example focal Author", "decimalLatitude": 35.0, "decimalLongitude": 139.0}
        ]
        family_records = [
            {"speciesKey": 30, "scientificName": "Family other", "decimalLatitude": 35.3, "decimalLongitude": 139.3}
        ]
        with patch("geographic_framing_higher_taxon_v2.focal_species_metadata", return_value=self.metadata), patch(
            "geographic_framing_higher_taxon_v2._query_prior_records",
            side_effect=[genus_records, family_records],
        ) as query:
            prior, audit = fetch_nonfocal_higher_taxon_prior(10, self.bounds)
        self.assertEqual(query.call_count, 2)
        self.assertEqual([call.args[0] for call in query.call_args_list], [100, 200])
        self.assertEqual(audit.status, "ready")
        self.assertEqual(audit.prior_rank_used, "FAMILY")
        self.assertEqual(len(prior), 1)
        self.assertEqual(audit.focal_records_removed, 1)

    def test_provider_failure_is_explicit_and_does_not_trigger_family_fallback(self):
        with patch("geographic_framing_higher_taxon_v2.focal_species_metadata", return_value=self.metadata), patch(
            "geographic_framing_higher_taxon_v2._query_prior_records",
            side_effect=RuntimeError("offline"),
        ) as query:
            prior, audit = fetch_nonfocal_higher_taxon_prior(10, self.bounds)
        self.assertTrue(prior.empty)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(audit.status, "provider_failed")
        self.assertEqual(audit.prior_rank_used, "GENUS")
        self.assertIn("offline", audit.failure_reason)

    def test_duplicate_coordinates_are_deduplicated_without_threshold(self):
        records = [
            {"speciesKey": 11, "scientificName": "Example other", "decimalLatitude": 35.1, "decimalLongitude": 139.1},
            {"speciesKey": 12, "scientificName": "Example another", "decimalLatitude": 35.1, "decimalLongitude": 139.1},
        ]
        with patch("geographic_framing_higher_taxon_v2.focal_species_metadata", return_value=self.metadata), patch(
            "geographic_framing_higher_taxon_v2._query_prior_records", return_value=records
        ):
            prior, audit = fetch_nonfocal_higher_taxon_prior(10, self.bounds)
        self.assertEqual(len(prior), 1)
        self.assertEqual(audit.duplicate_coordinate_rows_removed, 1)

    def test_frame_geometry_reuses_v1_rule_but_marks_nonfocal_prior(self):
        prior = pd.DataFrame(
            {"_latitude": [35.00, 35.01], "_longitude": [139.00, 139.01]}
        )
        audit = HigherTaxonPriorAudit(
            focal_species_key=10,
            focal_scientific_name="Example focal",
            genus_key=100,
            family_key=200,
            prior_rank_used="GENUS",
            prior_taxon_key_used=100,
            raw_record_count=2,
            usable_nonfocal_record_count=2,
            focal_records_removed=0,
            duplicate_coordinate_rows_removed=0,
            status="ready",
        )
        frames, occurrence_audit, summary = infer_higher_taxon_prior_frames(
            prior, prior_audit=audit
        )
        self.assertEqual(len(frames), 1)
        self.assertTrue((frames["framing_method"] == FRAMING_METHOD_V2).all())
        self.assertTrue(frames["higher_taxon_prior_only"].all())
        self.assertFalse(frames["training_only"].any())
        self.assertTrue((occurrence_audit["scope_class"] == "retained_nonfocal_higher_taxon_prior").all())
        self.assertFalse(summary["focal_training_coordinates_used"])
        self.assertFalse(summary["focal_heldout_coordinates_used"])
        self.assertTrue(summary["frame_geometry_reused_from_v1"])


if __name__ == "__main__":
    unittest.main()
