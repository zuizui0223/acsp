import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from evaluate_geographic_framing_development_v2 import EXPECTED_PROTOCOL, _pair_fold_rows, _protocol
from geographic_framing_higher_taxon_v2 import HigherTaxonPriorAudit


def _fold(root, repeat, status="ready"):
    path = root / "pair_001" / f"fold_{repeat:03d}"
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"latitude": [35.0], "longitude": [139.0]}).to_csv(path / "training_occurrences.csv", index=False)
    pd.DataFrame({"latitude": [34.95], "longitude": [139.05]}).to_csv(path / "held_out_occurrences.csv", index=False)
    manifest = {
        "repeat": repeat,
        "status": status,
        "failure_reason": "upstream failed" if status != "ready" else "",
        "provenance": {
            "pair_id": 1, "scientific_name": "Example focal", "taxon_group": "animal",
            "region_name": "Izu", "geographic_stratum": "east", "species_key": 10,
            "west": 138.8, "south": 34.0, "east": 139.8, "north": 35.0,
        },
    }
    (path / "fold_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _audit(status="ready", rank="GENUS"):
    return HigherTaxonPriorAudit(
        focal_species_key=10, focal_scientific_name="Example focal", genus_key=100,
        family_key=200, prior_rank_used=rank, prior_taxon_key_used=100,
        raw_record_count=2 if status == "ready" else 0,
        usable_nonfocal_record_count=2 if status == "ready" else 0,
        focal_records_removed=0, duplicate_coordinate_rows_removed=0,
        status=status, failure_reason="" if status == "ready" else "offline",
    )


class GeographicFramingV2EvaluatorTests(unittest.TestCase):
    def test_protocol_is_frozen(self):
        protocol = _protocol()
        self.assertEqual(protocol["protocol_fingerprint"], EXPECTED_PROTOCOL)
        self.assertEqual(protocol["prior_fetch"]["preferred_rank"], "GENUS")
        self.assertEqual(protocol["prior_fetch"]["fallback_rank"], "FAMILY")
        self.assertFalse(protocol["preserved_core"]["validated_japan_adapter_changed"])

    def test_pair_prior_is_fetched_once_for_five_folds(self):
        with tempfile.TemporaryDirectory() as tmp:
            folds = [_fold(Path(tmp), i) for i in range(1, 6)]
            prior = pd.DataFrame({"_latitude": [34.94, 34.96], "_longitude": [139.04, 139.06]})
            with patch("evaluate_geographic_framing_development_v2.fetch_nonfocal_higher_taxon_prior", return_value=(prior, _audit())) as fetch:
                rows, points, audit = _pair_fold_rows(folds)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["framing_status"] == "evaluated" for row in rows))
        self.assertEqual(len(points), 2)
        self.assertEqual(audit["status"], "ready")

    def test_provider_failure_retains_all_five_folds_as_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            folds = [_fold(Path(tmp), i) for i in range(1, 6)]
            empty = pd.DataFrame(columns=["_latitude", "_longitude"])
            with patch("evaluate_geographic_framing_development_v2.fetch_nonfocal_higher_taxon_prior", return_value=(empty, _audit("provider_failed"))):
                rows, points, audit = _pair_fold_rows(folds)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["heldout_frame_containment"] == 0.0 for row in rows))
        self.assertTrue(all(row["framing_status"] == "failed_retained_as_zero" for row in rows))
        self.assertTrue(points.empty)
        self.assertEqual(audit["status"], "provider_failed")

    def test_all_upstream_failed_folds_do_not_query_prior(self):
        with tempfile.TemporaryDirectory() as tmp:
            folds = [_fold(Path(tmp), i, "failed_placeholder") for i in range(1, 6)]
            with patch("evaluate_geographic_framing_development_v2.fetch_nonfocal_higher_taxon_prior") as fetch:
                rows, points, audit = _pair_fold_rows(folds)
        fetch.assert_not_called()
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["heldout_frame_containment"] == 0.0 for row in rows))
        self.assertTrue(points.empty)
        self.assertEqual(audit["prior_status"], "not_attempted_upstream_fold_failure")


if __name__ == "__main__":
    unittest.main()
