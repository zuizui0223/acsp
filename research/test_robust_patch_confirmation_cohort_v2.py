from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import predeclare_robust_patch_confirmation_cohort as base
import predeclare_robust_patch_confirmation_cohort_v2 as v2
from benchmark_general_random_taxa_regions import REGION_CELLS


class RobustPatchConfirmationCohortV2Tests(unittest.TestCase):
    def test_v2_protocol_fingerprint_and_campanula_exclusions_are_frozen(self):
        previous = base.EXPECTED_PROTOCOL
        try:
            base.EXPECTED_PROTOCOL = v2.EXPECTED_PROTOCOL_V2
            payload, fingerprint = base._canonical_fingerprint(v2.PROTOCOL_V2)
        finally:
            base.EXPECTED_PROTOCOL = previous
        self.assertEqual(fingerprint, v2.EXPECTED_PROTOCOL_V2)
        self.assertEqual(payload["protocol_id"], "acsp-robust-patch-untouched-confirmation-v2")
        self.assertEqual(payload["development_selection"]["support_fraction"], 0.025)
        self.assertEqual(payload["outer_validation"]["primary_radius_km"], 10.0)
        self.assertEqual(
            set(payload["explicit_exclusion_prefixes"]),
            {"Campanula microdonta", "Campanula punctata"},
        )

    def test_v2_sampler_remains_identity_only_and_balanced(self):
        bounds_to_index = {
            tuple(map(float, (west, south, east, north))): index
            for index, (_, _, west, south, east, north) in enumerate(REGION_CELLS, start=1)
        }

        def fake_taxon_frame(bounds, kingdom_key, facet_limit, minimum_records):
            region_index = bounds_to_index[tuple(map(float, bounds))]
            group = "plant" if int(kingdom_key) == 6 else "animal"
            prefix = f"R{region_index:02d}_{group}"
            return pd.DataFrame({
                "speciesKey": [region_index * 100000 + int(kingdom_key) * 1000 + i for i in range(40)],
                "scientific_name": [f"{prefix}_Species_{i:02d}" for i in range(40)],
                "coordinate_records": np.arange(20, 60),
            })

        previous = base.EXPECTED_PROTOCOL
        try:
            base.EXPECTED_PROTOCOL = v2.EXPECTED_PROTOCOL_V2
            protocol = base._canonical_fingerprint(v2.PROTOCOL_V2)[0]
        finally:
            base.EXPECTED_PROTOCOL = previous
        protocol["exclusion_files"] = []
        protocol.pop("protocol_fingerprint", None)

        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(base, "_canonical_fingerprint", return_value=(protocol, "test")), patch.object(
                base, "taxon_frame", side_effect=fake_taxon_frame
            ):
                output = Path(temporary) / "cohort"
                result = base.run(Path(temporary) / "unused.json", output)
                declared = pd.read_csv(output / "predeclared_taxon_region_pairs.csv")

        self.assertEqual(result["declared_pairs"], 96)
        self.assertEqual(result["unique_declared_taxa"], 96)
        self.assertEqual(result["taxon_group_counts"], {"animal": 48, "plant": 48})
        self.assertFalse(result["outcomes_inspected"])
        self.assertFalse(result["occurrence_rows_fetched_for_declared_taxa"])
        self.assertFalse(result["candidate_generation_run"])
        self.assertFalse(result["robust_support_run"])
        self.assertFalse(result["heldout_recovery_run"])
        self.assertFalse(declared["scientific_name"].duplicated().any())


if __name__ == "__main__":
    unittest.main()
