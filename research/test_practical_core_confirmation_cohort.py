from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import predeclare_practical_core_confirmation_cohort as sampler
from benchmark_general_random_taxa_regions import REGION_CELLS


class PracticalCoreConfirmationCohortTests(unittest.TestCase):
    def test_protocol_fingerprint_is_frozen(self):
        payload, fingerprint = sampler._canonical_fingerprint(
            Path("validation/acsp_practical_core_untouched_confirmation_protocol.json")
        )
        self.assertEqual(
            fingerprint,
            "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
        )
        self.assertEqual(payload["cohort"]["pair_count"], 192)
        self.assertEqual(
            payload["practical_core"]["protocol_fingerprint"],
            "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905",
        )
        self.assertEqual(
            payload["inference"]["primary_gate"],
            "acsp_practical_core - official_grts_proportional_local_mindis10km",
        )

    def test_cli_protocol_argument_maps_to_run_signature(self):
        args = sampler.parser().parse_args(
            ["--protocol", "validation/example.json", "--output", "example-output"]
        )
        self.assertEqual(args.protocol_path, Path("validation/example.json"))
        self.assertEqual(args.output, Path("example-output"))
        self.assertNotIn("protocol", vars(args))

    def test_record_strata_are_balanced(self):
        frame = pd.DataFrame({
            "speciesKey": np.arange(40),
            "scientific_name": [f"Species {index}" for index in range(40)],
            "coordinate_records": np.arange(20, 60),
        })
        result = sampler._record_strata(frame, 4)
        self.assertEqual(
            result["record_count_stratum"].value_counts().sort_index().to_dict(),
            {0: 10, 1: 10, 2: 10, 3: 10},
        )

    def test_prefix_exclusion_ignores_authorship_suffix(self):
        prefixes = ("Campanula microdonta",)
        self.assertTrue(
            sampler._prefix_excluded("Campanula microdonta Koidz.", prefixes)
        )
        self.assertFalse(
            sampler._prefix_excluded("Campanula punctata Lam.", prefixes)
        )

    def test_factorial_sampler_produces_192_unique_balanced_taxa_without_outcomes(self):
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

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            sampler, "taxon_frame", side_effect=fake_taxon_frame
        ):
            output = Path(temporary) / "cohort"
            result = sampler.run(
                Path(
                    "validation/acsp_practical_core_untouched_confirmation_protocol.json"
                ),
                output,
            )
            declared = pd.read_csv(output / "predeclared_taxon_region_pairs.csv")
            audit = pd.read_csv(output / "sampling_frame_audit.csv")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["declared_pairs"], 192)
        self.assertEqual(result["unique_declared_taxa"], 192)
        self.assertEqual(result["taxon_group_counts"], {"animal": 96, "plant": 96})
        self.assertEqual(set(result["record_count_stratum_counts"].values()), {48})
        self.assertEqual(set(result["region_cell_counts"].values()), {16})
        self.assertEqual(len(audit), 12 * 2 * 4)
        self.assertTrue((audit["available_unused_before_draw"] >= 2).all())
        self.assertFalse(result["outcomes_inspected"])
        self.assertFalse(result["occurrence_rows_fetched_for_declared_taxa"])
        self.assertFalse(result["candidate_generation_run"])
        self.assertFalse(result["practical_core_run"])
        self.assertFalse(result["grts_run"])
        self.assertFalse(result["sdm_fitting_run"])
        self.assertFalse(result["heldout_recovery_run"])
        self.assertFalse(result["taxon_replacement_after_declaration_allowed"])
        self.assertFalse(declared["scientific_name"].duplicated().any())


if __name__ == "__main__":
    unittest.main()
