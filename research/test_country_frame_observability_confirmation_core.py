from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np
import pandas as pd

import country_frame_observability_confirmation_core as mod


def synthetic_rows(*, reverse: bool = False) -> pd.DataFrame:
    rows = []
    frame_id = 0
    strata = ("north", "east", "west", "south")
    for region in range(1, 13):
        geo = strata[(region - 1) % len(strata)]
        for group in ("plant", "animal"):
            for stratum in range(4):
                frame_id += 1
                label = frame_id > 48
                if reverse:
                    label = not label
                historical = frame_id + 5
                recent = 1 if label else 0
                rows.append(
                    {
                        "observability_frame_id": frame_id,
                        "taxon_group": group,
                        "geographic_stratum": geo,
                        "region_cell_index": region,
                        "record_count_stratum": stratum,
                        "speciesKey": 9000000 + frame_id,
                        "scientific_name": f"Synthetic taxon {frame_id}",
                        "selected_country_code": "JP",
                        "historical_selected_country_count": historical,
                        "country_frame_observability_score": float(np.log1p(historical)),
                        "recent_heldout_occurrence_rows": recent,
                        "temporally_observable": label,
                    }
                )
    return pd.DataFrame(rows)


class ObservabilityConfirmationCoreTests(unittest.TestCase):
    def test_validate_requires_exact_balanced_96_and_exact_score(self) -> None:
        frame = synthetic_rows()
        checked = mod.validate_completed_rows(frame)
        self.assertEqual(len(checked), 96)
        self.assertEqual(checked["taxon_group"].value_counts().to_dict(), {"plant": 48, "animal": 48})
        bad = frame.copy()
        bad.loc[0, "country_frame_observability_score"] += 0.01
        with self.assertRaises(ValueError):
            mod.validate_completed_rows(bad)

    def test_temporal_label_is_exactly_recent_count_positive(self) -> None:
        bad = synthetic_rows()
        bad.loc[0, "temporally_observable"] = True
        bad.loc[0, "recent_heldout_occurrence_rows"] = 0
        with self.assertRaises(ValueError):
            mod.validate_completed_rows(bad)

    def test_bootstrap_is_fixed_seed_and_uses_preregistered_repetitions(self) -> None:
        frame = synthetic_rows()
        scores = frame["country_frame_observability_score"].to_numpy(float)
        labels = frame["temporally_observable"].astype(int).to_numpy()
        first = mod.bootstrap_auc(scores, labels)
        second = mod.bootstrap_auc(scores, labels)
        self.assertEqual(first, second)
        self.assertEqual(first["requested_replicates"], 10000)
        self.assertEqual(first["seed"], 2026082702)
        self.assertGreater(first["ci95_lower"], 0.5)

    def test_all_seven_gates_are_required(self) -> None:
        summary = mod.summarize_confirmation(
            synthetic_rows(),
            fingerprints_match=True,
            zero_overlap_verified=True,
            preheldout_freeze_verified=True,
        )
        primary = summary["primary"]
        self.assertEqual(primary["passed_gate_count"], 7)
        self.assertTrue(primary["confirmation_passed"])
        failed = mod.summarize_confirmation(
            synthetic_rows(),
            fingerprints_match=False,
            zero_overlap_verified=True,
            preheldout_freeze_verified=True,
        )
        self.assertEqual(failed["primary"]["passed_gate_count"], 6)
        self.assertFalse(failed["primary"]["confirmation_passed"])

    def test_secondary_never_changes_primary_decision(self) -> None:
        summary = mod.summarize_confirmation(
            synthetic_rows(),
            fingerprints_match=True,
            zero_overlap_verified=True,
            preheldout_freeze_verified=True,
        )
        self.assertFalse(summary["secondary_only"]["may_change_primary_decision"])
        self.assertIn("generic_record_count_stratum_auc", summary["secondary_only"])
        self.assertIn("by_taxon_group", summary["secondary_only"])
        self.assertIn("by_geographic_stratum", summary["secondary_only"])

    def test_core_cannot_open_or_read_candidate_science(self) -> None:
        source = Path(mod.__file__).read_text(encoding="utf-8")
        forbidden_imports = (
            "fetch_recent_country_occurrences",
            "validated_robust_candidate_patches",
            "ROBUST_TERRAIN_FEATURES",
            "same_size_random_recovery",
        )
        for token in forbidden_imports:
            self.assertNotIn(token, source)
        guards = mod.summarize_confirmation(
            synthetic_rows(),
            fingerprints_match=True,
            zero_overlap_verified=True,
            preheldout_freeze_verified=True,
        )["guards"]
        self.assertFalse(guards["candidate_generation_read"])
        self.assertFalse(guards["robust_support_read"])
        self.assertFalse(guards["random_baseline_read"])
        self.assertFalse(guards["recall_or_lift_read"])


if __name__ == "__main__":
    unittest.main()
