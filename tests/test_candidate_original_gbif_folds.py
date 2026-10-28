"""Synthetic tests for the 2026 original GBIF candidate-fold structural gate.

Synthetic fixtures are invented and must NEVER be mistaken for recovered
historical record IDs, taxa, precise survey locations or real GBIF inputs.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from research import audit_candidate_original_gbif_folds as audit


class OriginalFoldCandidateStructuralTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identities = [
            {"pair_id": "1", "scientific_name": "Synthetic example A",
             "taxon_group": "plant", "region_name": "Toy region A", "speciesKey": "101"},
            {"pair_id": "2", "scientific_name": "Synthetic example B",
             "taxon_group": "animal", "region_name": "Toy region B", "speciesKey": "202"},
        ]
        self.statuses = [
            {"pair_id": "1", "scientific_name": "Synthetic example A",
             "taxon_group": "plant", "status": "complete",
             "written_folds": "5", "occurrence_rows": "6", "spatial_blocks": "3",
             "failure_reason": ""},
            {"pair_id": "2", "scientific_name": "Synthetic example B",
             "taxon_group": "animal", "status": "failed_retained_as_zero",
             "written_folds": "5", "occurrence_rows": "0", "spatial_blocks": "0",
             "failure_reason": "ValueError: fewer than four usable occurrence rows: 0"},
        ]
        self.pool = [
            {"_row_id": str(i), "_latitude": str(30.11 + .11 * (i // 2)),
             "_longitude": str(130.21 + .11 * (i // 2)),
             "_gbif_id": str(9000 + i)}
            for i in range(6)
        ]
        self._write_pair1()
        self._write_pair2_failed()

    @staticmethod
    def _csv(path: Path, rows: list[dict], keys: tuple[str, ...]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _meta(pair: int, repeat: int, status: str,
              train_n: int, held_n: int, reason: str = "") -> dict:
        group = "plant" if pair == 1 else "animal"
        return {
            "pair_id": pair,
            "repeat": repeat,
            "status": status,
            "failure_reason": reason,
            "training_records": train_n,
            "heldout_records": held_n,
            "execution_fingerprint": audit.FINGERPRINT,
            "provenance": {
                "pair_id": pair, "scientific_name": f"Synthetic example {'A' if pair == 1 else 'B'}",
                "taxon_group": group,
                "region_name": f"Toy region {'A' if pair == 1 else 'B'}",
                "species_key": 101 if pair == 1 else 202,
            },
        }

    def _write_pair1(self) -> None:
        blocks = list(dict.fromkeys(audit._block(row) for row in self.pool))
        self.assertEqual(len(blocks), 3)
        rng = np.random.default_rng(audit.SEED_BASE + 1)
        for repeat in range(1, 6):
            selected = set(rng.choice(np.array(blocks, dtype=object),
                                      size=1, replace=False).tolist())
            train = [x for x in self.pool if audit._block(x) not in selected]
            held = [x for x in self.pool if audit._block(x) in selected]
            directory = self.root / "pair_001" / f"fold_{repeat:03d}"
            self._csv(directory / "training_occurrences.csv", train,
                      ("_row_id", "_latitude", "_longitude", "_gbif_id"))
            self._csv(directory / "held_out_occurrences.csv", held,
                      ("_row_id", "_latitude", "_longitude", "_gbif_id"))
            (directory / "fold_manifest.json").write_text(
                json.dumps(self._meta(1, repeat, "ready", len(train), len(held))),
                encoding="utf-8",
            )

    def _write_pair2_failed(self) -> None:
        for repeat in range(1, 6):
            directory = self.root / "pair_002" / f"fold_{repeat:03d}"
            self._csv(directory / "training_occurrences.csv", [], ("latitude", "longitude"))
            self._csv(directory / "held_out_occurrences.csv", [], ("latitude", "longitude"))
            (directory / "fold_manifest.json").write_text(
                json.dumps(self._meta(2, repeat, "failed_placeholder", 0, 0,
                                      self.statuses[1]["failure_reason"])),
                encoding="utf-8",
            )

    def _audit(self) -> dict:
        return audit.inspect_candidate_root(
            self.root, self.identities, self.statuses, expected_pairs=2
        )

    def test_complete_synthetic_folds_are_structurally_consistent_not_authenticated(self):
        result = self._audit()
        self.assertEqual(result["denominator"], {"pairs": 2, "folds": 10})
        self.assertEqual(result["checks"]["complete_pairs"], 1)
        self.assertEqual(result["checks"]["failed_retained_pairs"], 1)
        self.assertEqual(result["checks"]["fold_manifests_checked"], 10)
        self.assertEqual(result["checks"]["distinct_cleaned_rows_across_complete_pairs"], 6)
        self.assertEqual(result["checks"]["cleaned_rows_with_nonblank_gbif_id"], 6)
        self.assertEqual(result["checks"]["cleaned_rows_with_nonblank_dataset_key"], 0)
        self.assertFalse(result["retrospective_2026_original_source_proven"])
        self.assertFalse(result["historical_gbif_dataset_key_attribution_proven"])
        self.assertFalse(result["untrusted_candidate_can_prove_authenticity_by_structural_checks_alone"])
        self.assertFalse(result["raw_record_ids_or_coordinates_in_report"])

    def test_changed_one_fold_record_is_rejected(self):
        p = self.root / "pair_001" / "fold_003" / "training_occurrences.csv"
        original = p.read_text(encoding="utf-8")
        first = next(x["_gbif_id"] for x in self.pool if x["_gbif_id"] in original)
        p.write_text(original.replace(first, "999999999", 1), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pool differs"):
            self._audit()

    def test_preserved_record_pool_but_wrong_spatial_split_is_rejected(self):
        d = self.root / "pair_001" / "fold_002"
        train_path, held_path = (d / "training_occurrences.csv",
                                  d / "held_out_occurrences.csv")
        def read(path):
            with path.open(encoding="utf-8", newline="") as f:
                return list(csv.DictReader(f))
        tr = read(train_path)
        ho = read(held_path)
        self.assertTrue(tr and ho)
        # Change allocation only. Union, counts, IDs and CSV columns stay
        # identical, so only checking structural counts would miss this.
        tr[0], ho[0] = ho[0], tr[0]
        fields = ("_row_id", "_latitude", "_longitude", "_gbif_id")
        self._csv(train_path, tr, fields)
        self._csv(held_path, ho, fields)
        with self.assertRaisesRegex(ValueError, "split does not match"):
            self._audit()

    def test_missing_one_fold_fails(self):
        p = self.root / "pair_001" / "fold_005" / "fold_manifest.json"
        p.unlink()
        with self.assertRaisesRegex(ValueError, "required backup file absent"):
            self._audit()

    def test_invalid_status_does_not_create_an_artificial_success(self):
        self.statuses[0]["status"] = "complete_after_replacement"
        with self.assertRaisesRegex(ValueError, "unrecognized frozen pair-export state"):
            self._audit()

    def test_missing_cleaned_ordinals_fail_not_silently_regenerated(self):
        p = self.root / "pair_001" / "fold_001" / "held_out_occurrences.csv"
        data = p.read_text(encoding="utf-8").replace("_row_id", "new_index", 1)
        p.write_text(data, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cleaned row ordinal"):
            self._audit()

    def test_structural_count_cannot_claim_dataset_doi(self):
        result = self._audit()
        text = json.dumps(result)
        self.assertNotIn("9000", text)
        self.assertNotIn("30.11", text)
        self.assertNotIn("130.21", text)
        self.assertNotIn("Synthetic example", text)
        self.assertIn("PROVENANCE_UNAUTHENTICATED", result["status"])

    def test_disallow_conflating_failed_pair_with_biological_absence(self):
        result = self._audit()
        self.assertEqual(result["checks"]["failed_retained_pairs"], 1)
        self.assertFalse(result["new_confirmation_performed"])

    def test_missing_frozen_pair_identity_fails(self):
        with self.assertRaisesRegex(ValueError, "identity/status denominator mismatch"):
            audit.inspect_candidate_root(
                self.root, self.identities[:-1], self.statuses, expected_pairs=2
            )


if __name__ == "__main__":
    unittest.main()
