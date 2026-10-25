"""Editorial preflight regression tests; no author declarations or field outcomes."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from paper import validate_submission_packet as audit


class SubmissionPacketTests(unittest.TestCase):
    def _alter(self, original: Path, change: str, replacement: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        destination = Path(directory.name) / original.name
        original_text = original.read_text(encoding="utf-8")
        self.assertIn(change, original_text)
        destination.write_text(original_text.replace(change, replacement, 1), encoding="utf-8")
        return destination

    def test_editorial_packet_passes_but_is_explicitly_not_submission_ready(self):
        result = audit.validate()
        self.assertEqual(result["status"], "editorial_draft_consistency_passed")
        self.assertFalse(result["author_submission_ready"])
        self.assertFalse(result["journal_specific_requirements_verified"])
        self.assertFalse(result["release_doi_verified"])
        self.assertFalse(result["author_contributions_and_conflicts_confirmed"])
        self.assertEqual(result["primary_confirmatory_pairs"], 96)
        self.assertEqual(result["primary_confirmatory_folds"], 480)
        self.assertEqual(result["highlight_count"], 5)
        self.assertTrue(all(0 < n <= 85 for n in result["highlight_character_counts"]))
        self.assertLessEqual(result["short_abstract_words"], 250)

    def test_overlong_highlight_fails_closed(self):
        path = self._alter(
            audit.HIGHLIGHTS,
            "Occurrence-conditioned support yields bounded, non-ranked survey patches.",
            "Occurrence-conditioned support yields bounded, non-ranked survey patches with every species universally mapped everywhere.",
        )
        with self.assertRaisesRegex(ValueError, "1-85"):
            audit.validate(highlights_path=path)

    def test_abstract_word_limit_is_working_editorial_guard(self):
        content = audit.ABSTRACT.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "short_abstract.md"
            path.write_text(content.rstrip() + " " + ("hypothetical " * 300) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "120-250"):
                audit.validate(abstract_path=path)

    def test_effect_number_cannot_drift_from_frozen_primary_table(self):
        path = self._alter(audit.ABSTRACT, "0.08559", "0.18559")
        with self.assertRaisesRegex(ValueError, "Missing frozen abstract evidence: 0.08559"):
            audit.validate(abstract_path=path)

    def test_unsupported_global_success_cannot_be_added_to_cover_letter(self):
        path = self._alter(
            audit.COVER,
            "The study contributes a reproducible representation",
            "The method is globally validated. The study contributes a reproducible representation",
        )
        with self.assertRaisesRegex(ValueError, "Unsupported affirmative claim"):
            audit.validate(cover_path=path)

    def test_cover_must_keep_author_signoff_open(self):
        path = self._alter(
            audit.COVER,
            "[Corresponding author — name, affiliation and contact details to be verified]",
            "ACSP Developers",
        )
        with self.assertRaisesRegex(ValueError, "Unconfirmed author metadata"):
            audit.validate(cover_path=path)


if __name__ == "__main__":
    unittest.main()
