"""Verify source-locked GBIF input attribution gap without reopening frozen outcomes."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from paper import audit_gbif_citation_provenance as audit


class GbifInputCitationProvenanceTests(unittest.TestCase):
    def test_source_bound_gap_is_explicit_not_an_ecological_result(self):
        result = audit.audit()
        self.assertEqual(result["status"], "ORIGINAL_INPUT_CITATION_NOT_YET_RECOVERED")
        self.assertEqual(result["original_input_method"], "GBIF_OCCURRENCE_SEARCH_API")
        self.assertEqual(result["counts"]["declared_taxon_region_pairs"], 96)
        self.assertEqual(result["counts"]["declared_spatial_folds"], 480)
        self.assertEqual(result["counts"]["maximum_search_records_per_pair"], 150)
        self.assertFalse(result["frozen_automatic_GBIF_download_DOI_generated"])
        self.assertFalse(result["frozen_GBIF_download_DOI_verified"])
        self.assertFalse(result["raw_fold_occurrence_csv_in_declared_upload"])
        self.assertFalse(result["original_datasetKey_transferred_by_record_converter"])
        self.assertTrue(result["original_gbifID_transferred_to_temporary_fold_rows"])
        self.assertFalse(result["journal_submission_ready"])
        self.assertFalse(result["retuned_historic_confirmation"])
        self.assertFalse(result["new_GBIF_download_replaces_historic_input"])

    def test_original_cohort_and_archive_paths_are_not_confused(self):
        result = audit.audit()
        self.assertEqual(result["frozen_cohort_identity_artifact"]["workflow_run_id"], 32335791948)
        self.assertEqual(result["frozen_cohort_identity_artifact"]["artifact_id"], 9394691112)
        self.assertEqual(result["original_declared_result_upload_paths"], [
            "confirmation-folds/export_manifest.json",
            "confirmation-folds/pair_export_status.csv",
            "confirmation-results",
        ])
        self.assertTrue(result["raw_folds_could_exist_outside_checked_repository"])

    def test_public_report_has_no_private_site_or_record_ids(self):
        serial = json.dumps(audit.audit(), sort_keys=True)
        self.assertNotIn("training_occurrences.csv\" :", serial)
        for key in ("candidate_cell_id", "precise_latitude", "precise_longitude",
                    "original_occurrence_id_list", "species_coordinate"):
            self.assertNotIn(key, serial)

    def _snapshot(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for relative in [*audit.FROZEN_BLOBS, audit.MANUSCRIPT, audit.DOC]:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(audit.ROOT / relative, target)
        return root

    def test_tampered_original_converter_fails_closed(self):
        root = self._snapshot()
        p = root / "gbif_fieldmap_builder_app.py"
        p.write_bytes(p.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(ValueError, "source Git blob drift"):
            audit.audit(root)

    def test_false_archive_claim_in_manuscript_fails_closed(self):
        root = self._snapshot()
        p = root / audit.MANUSCRIPT
        contents = p.read_text(encoding="utf-8")
        self.assertIn("not included in the declared GitHub Actions result upload", contents)
        p.write_text(contents.replace(
            "not included in the declared GitHub Actions result upload",
            "uploaded with every result as immutable original fold inputs"
        ), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "original raw-input archive omission"):
            audit.audit(root)

    def test_fictitious_extra_upload_is_not_original_source_contract(self):
        original = (audit.ROOT / ".github/workflows/robust-patch-untouched-confirmation-v2.yml").read_text(encoding="utf-8")
        mutated = original.replace(
            "            confirmation-folds/pair_export_status.csv",
            "            confirmation-folds/pair_export_status.csv\n            confirmation-folds/pair_*/fold_*",
            1,
        )
        with self.assertRaisesRegex(ValueError, "declared upload paths changed"):
            audit._declared_upload_paths(mutated)

    def test_cff_still_has_no_approved_author_or_version_doi(self):
        result = audit.audit()
        self.assertFalse(result["zenodo_release_DOI_verified"])
        self.assertFalse(result["frozen_GBIF_download_DOI_verified"])
        self.assertIn("CITATION.cff", result["frozen_source_git_blobs"])


if __name__ == "__main__":
    unittest.main()
