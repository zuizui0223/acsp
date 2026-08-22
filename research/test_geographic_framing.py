import hashlib
import inspect
import json
from pathlib import Path
import unittest

import pandas as pd

from geographic_framing import (
    FRAMING_METHOD,
    infer_training_block_frames,
)


PROTOCOL = Path("validation/acsp_geographic_framing_development_protocol_v1.json")
EXPECTED_FINGERPRINT = "887526145c4fc0e2c9c3986c8424b4814b50155108a937b5d6a613b2ee974c0f"


def _occurrences(points):
    return pd.DataFrame(
        {
            "_row_id": list(range(1, len(points) + 1)),
            "_latitude": [point[0] for point in points],
            "_longitude": [point[1] for point in points],
        }
    )


class GeographicFramingDevelopmentTests(unittest.TestCase):
    def test_protocol_fingerprint_and_claim_boundary_are_frozen(self):
        payload = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        stored = payload.pop("protocol_fingerprint")
        calculated = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        self.assertEqual(stored, EXPECTED_FINGERPRINT)
        self.assertEqual(calculated, EXPECTED_FINGERPRINT)
        self.assertFalse(payload["scope"]["validated_japan_adapter_changed"])
        self.assertFalse(payload["scope"]["global_validation_claim"])
        self.assertEqual(
            payload["development_data"]["confirmation_status_for_framing"],
            "permanently_nonconfirmatory_after_use",
        )

    def test_adjacent_occupied_blocks_form_one_component_and_frame(self):
        occurrences = _occurrences([(35.01, 139.01), (35.11, 139.11)])
        frames, audit, summary = infer_training_block_frames(occurrences)
        self.assertEqual(summary["initial_component_count"], 1)
        self.assertEqual(summary["final_frame_count"], 1)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames.iloc[0]["record_count"], 2)
        self.assertEqual(audit["frame_id"].nunique(), 1)

    def test_disjunct_singleton_is_retained_not_deleted_as_noise(self):
        occurrences = _occurrences(
            [(35.01, 139.01), (35.11, 139.11), (38.01, 142.01)]
        )
        frames, audit, summary = infer_training_block_frames(occurrences)
        self.assertEqual(summary["initial_component_count"], 2)
        self.assertEqual(summary["final_frame_count"], 2)
        self.assertEqual(sorted(frames["record_count"].tolist()), [1, 2])
        self.assertTrue(summary["singleton_components_retained"])
        self.assertFalse(summary["remote_noise_filter"])
        self.assertEqual(len(audit), 3)
        self.assertTrue((audit["scope_class"] == "retained_training_occurrence").all())

    def test_padding_can_union_nearby_but_nonadjacent_components_without_threshold_tuning(self):
        # The occupied 0.1-degree blocks have one empty block between them, so
        # they start as separate components. The frozen 10 km padding makes the
        # two candidate frames overlap and they are then deterministically united.
        occurrences = _occurrences([(35.01, 139.01), (35.01, 139.21)])
        frames, audit, summary = infer_training_block_frames(occurrences)
        self.assertEqual(summary["initial_component_count"], 2)
        self.assertEqual(summary["final_frame_count"], 1)
        self.assertEqual(frames.iloc[0]["source_component_count"], 2)
        self.assertEqual(audit["frame_id"].nunique(), 1)

    def test_frame_output_is_invariant_to_occurrence_row_order(self):
        occurrences = _occurrences(
            [
                (35.01, 139.01),
                (35.11, 139.11),
                (38.01, 142.01),
                (38.02, 142.02),
            ]
        )
        first, _, first_summary = infer_training_block_frames(occurrences)
        second, _, second_summary = infer_training_block_frames(
            occurrences.sample(frac=1.0, random_state=17).reset_index(drop=True)
        )
        columns = [
            "frame_id", "west", "south", "east", "north", "record_count",
            "occupied_block_count", "source_component_count", "source_component_ids",
        ]
        pd.testing.assert_frame_equal(
            first[columns].reset_index(drop=True),
            second[columns].reset_index(drop=True),
            check_exact=False,
            rtol=0.0,
            atol=1e-12,
        )
        self.assertEqual(first_summary["final_frame_count"], second_summary["final_frame_count"])

    def test_every_training_occurrence_is_audited_and_assigned(self):
        occurrences = _occurrences(
            [(34.0 + i * 0.17, 135.0 + i * 0.19) for i in range(8)]
        )
        _, audit, _ = infer_training_block_frames(occurrences)
        self.assertEqual(len(audit), len(occurrences))
        self.assertFalse(audit["frame_id"].isna().any())
        self.assertFalse(audit["framing_component_id"].isna().any())

    def test_empty_input_returns_audited_empty_product(self):
        frames, audit, summary = infer_training_block_frames(
            pd.DataFrame(columns=["_latitude", "_longitude"])
        )
        self.assertTrue(frames.empty)
        self.assertTrue(audit.empty)
        self.assertEqual(summary["final_frame_count"], 0)
        self.assertEqual(summary["framing_method"], FRAMING_METHOD)

    def test_api_cannot_receive_heldout_outcome_sdm_or_field_budget(self):
        parameters = inspect.signature(infer_training_block_frames).parameters
        for forbidden in (
            "heldout", "heldout_occurrences", "outcomes", "sdm", "ssdm",
            "max_sites", "target_coverage", "survey_days", "budget",
        ):
            self.assertNotIn(forbidden, parameters)
        self.assertIn("occurrences", parameters)

    def test_invalid_coordinates_fail_instead_of_silent_filtering(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            infer_training_block_frames(_occurrences([(35.0, 139.0), (float("nan"), 140.0)]))
        with self.assertRaisesRegex(ValueError, "longitude"):
            infer_training_block_frames(_occurrences([(35.0, 181.0)]))


if __name__ == "__main__":
    unittest.main()
