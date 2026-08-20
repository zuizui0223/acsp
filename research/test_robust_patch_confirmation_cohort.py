from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import predeclare_robust_patch_confirmation_cohort as sampler
from benchmark_general_random_taxa_regions import REGION_CELLS


class RobustPatchConfirmationCohortTests(unittest.TestCase):
    def test_protocol_fingerprint_is_frozen(self):
        payload, fingerprint = sampler._canonical_fingerprint(
            Path("validation/acsp_robust_patch_untouched_confirmation_protocol.json")
        )
        self.assertEqual(
            fingerprint,
            "1d35e5c49a800f63b7f29f55001163c5be3e2d2436dc49d22cbd81ce9f221818",
        )
        self.assertEqual(payload["cohort"]["pair_count"], 96)
        self.assertEqual(payload["development_selection"]["support_fraction"], 0.025)
        self.assertEqual(payload["outer_validation"]["primary_radius_km"], 10.0)
        self.assertEqual(
            payload["robust_patch_rule"]["empty_tier_rule"],
            "retain declared fold with selected_cells=0, recall=0, random_mean_recall=0, lift=0",
        )

    def test_factorial_sampler_produces_96_unique_balanced_taxa_without_outcomes(self):
        bounds_to_index = {
            tuple(map(float, (west, south, east, north))): index
            for index, (_, _, west, south, east, north) in enumerate(
                REGION_CELLS, start=1
            )
        }

        def fake_taxon_frame(bounds, kingdom_key, facet_limit, minimum_records):
            region_index = bounds_to_index[tuple(map(float, bounds))]
            group = "plant" if int(kingdom_key) == 6 else "animal"
            prefix = f"R{region_index:02d}_{group}"
            return pd.DataFrame({
                "speciesKey": [
                    region_index * 100000 + int(kingdom_key) * 1000 + i
                    for i in range(40)
                ],
                "scientific_name": [
                    f"{prefix}_Species_{i:02d}" for i in range(40)
                ],
                "coordinate_records": np.arange(20, 60),
            })

        with tempfile.TemporaryDirectory() as temporary:
            protocol = sampler._canonical_fingerprint(
                Path("validation/acsp_robust_patch_untouched_confirmation_protocol.json")
            )[0]
            protocol["exclusion_files"] = []
            protocol.pop("protocol_fingerprint", None)
            local_protocol = Path(temporary) / "protocol.json"
            local_protocol.write_text(
                __import__("json").dumps(protocol, sort_keys=False, indent=2) + "\n"
            )

            with patch.object(
                sampler, "_canonical_fingerprint", return_value=(protocol, "test")
            ), patch.object(
                sampler, "taxon_frame", side_effect=fake_taxon_frame
            ):
                output = Path(temporary) / "cohort"
                result = sampler.run(local_protocol, output)
                declared = pd.read_csv(output / "predeclared_taxon_region_pairs.csv")
                audit = pd.read_csv(output / "sampling_frame_audit.csv")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["declared_pairs"], 96)
        self.assertEqual(result["unique_declared_taxa"], 96)
        self.assertEqual(result["taxon_group_counts"], {"animal": 48, "plant": 48})
        self.assertEqual(set(result["record_count_stratum_counts"].values()), {24})
        self.assertEqual(set(result["region_cell_counts"].values()), {8})
        self.assertEqual(len(audit), 12 * 2 * 4)
        self.assertTrue((audit["available_unused_before_draw"] >= 1).all())
        self.assertFalse(result["outcomes_inspected"])
        self.assertFalse(result["occurrence_rows_fetched_for_declared_taxa"])
        self.assertFalse(result["candidate_generation_run"])
        self.assertFalse(result["robust_support_run"])
        self.assertFalse(result["heldout_recovery_run"])
        self.assertFalse(result["taxon_replacement_after_declaration_allowed"])
        self.assertFalse(declared["scientific_name"].duplicated().any())


if __name__ == "__main__":
    unittest.main()
