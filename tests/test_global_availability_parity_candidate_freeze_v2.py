from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import freeze_global_availability_parity_candidate_pair_v2 as pair
import freeze_global_availability_parity_candidate_ru_v2 as ru


class CandidateFreezeBoundaryTests(unittest.TestCase):
    def test_stage3_sources_do_not_open_heldout_or_random_scoring(self):
        forbidden = (
            "fetch_recent_country_occurrences",
            "recovery_fraction",
            "same_size_random_recovery",
            "robust_minus_random_recall",
        )
        for module in (pair, ru):
            source = inspect.getsource(module)
            for token in forbidden:
                self.assertNotIn(token, source)

    def test_real_frozen_stage2_plan_verifies_and_has_only_pair48_ru(self):
        frame = pair.verify_inputs()
        self.assertEqual(len(frame), 48)
        self.assertEqual(frame["speciesKey"].nunique(), 48)
        self.assertEqual(frame["country_plan_state"].value_counts().to_dict(), {"READY": 48})
        ru_ids = frame.loc[frame["selected_country_code"].eq("RU"), "availability_pair_id"].astype(int).tolist()
        self.assertEqual(ru_ids, [48])

    def test_declared_evidence_failures_are_narrow(self):
        self.assertTrue(pair._is_declared_evidence_failure(ValueError("fewer than five usable historical occurrence rows in JP: 2")))
        self.assertTrue(pair._is_declared_evidence_failure(ValueError("regional lattice has no complete terrain surface points")))
        self.assertTrue(pair._is_declared_evidence_failure(ValueError("fewer than five unique complete historical terrain prototypes: 3")))
        self.assertFalse(pair._is_declared_evidence_failure(RuntimeError("HTTP 429")))
        self.assertFalse(pair._is_declared_evidence_failure(ValueError("geometry digest mismatch")))

    def test_nonru_evidence_failure_becomes_sentinel_but_geometry_failure_aborts(self):
        base = pd.DataFrame([{
            "availability_pair_id": 1,
            "taxon_group": "animal",
            "speciesKey": 1,
            "scientific_name": "Taxon A",
            "country_plan_state": "READY",
            "selected_country_code": "JP",
            "historical_selected_country_count": 10,
        }])
        geom = types.SimpleNamespace(source_version="mock-version", source_id="mock-source")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(pair, "verify_inputs", return_value=base), \
             patch.object(pair, "fetch_geoboundaries_country_geometry", return_value=geom), \
             patch.object(pair, "_geometry_digest_from_source_version", return_value="a" * 64), \
             patch.object(pair, "fetch_country_occurrences", side_effect=ValueError("fewer than five usable historical occurrence rows in JP: 2")):
            result = pair.freeze_pair(1, Path(tmp))
            self.assertEqual(result["preheldout_availability_state"], "SENTINEL_OR_ABSTAIN")
            self.assertFalse(result["heldout_2021_2025_opened"])

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(pair, "verify_inputs", return_value=base), \
             patch.object(pair, "fetch_geoboundaries_country_geometry", side_effect=RuntimeError("provider unavailable")):
            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                pair.freeze_pair(1, Path(tmp))

    def test_ru_base_is_exact_frozen_pair48(self):
        base = ru.frozen_ru_base()
        self.assertEqual(int(base["availability_pair_id"]), 48)
        self.assertEqual(str(base["selected_country_code"]), "RU")


if __name__ == "__main__":
    unittest.main()
