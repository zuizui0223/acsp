import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import predeclare_acsp_v2_confirmation_cohort as sampler
from benchmark_general_random_taxa_regions import REGION_CELLS


class AcspV2ConfirmationCohortTests(unittest.TestCase):
    def test_protocol_fingerprint_is_frozen(self):
        payload, fingerprint = sampler._canonical_fingerprint(
            Path("validation/acsp_v2_untouched_confirmation_protocol.json")
        )
        self.assertEqual(
            fingerprint,
            "8b540a965e25789174ce97a976c36d8b659c3c0d2919693b8fcd766330532ebb",
        )
        self.assertEqual(payload["cohort"]["pair_count"], 192)
        self.assertEqual(payload["v2_policy"]["protocol_fingerprint"],
                         "378e069f982a19abfc0183163fd503b467a1b746c11ba0b354d4f9802c155124")

    def test_record_strata_are_balanced(self):
        frame = pd.DataFrame({
            "speciesKey": np.arange(40),
            "scientific_name": [f"Species {index}" for index in range(40)],
            "coordinate_records": np.arange(20, 60),
        })
        result = sampler._record_strata(frame, 4)
        self.assertEqual(result["record_count_stratum"].value_counts().sort_index().to_dict(),
                         {0: 10, 1: 10, 2: 10, 3: 10})

    def test_prefix_exclusion_ignores_authorship_suffix(self):
        prefixes = ("Campanula microdonta",)
        self.assertTrue(sampler._prefix_excluded("Campanula microdonta Koidz.", prefixes))
        self.assertFalse(sampler._prefix_excluded("Campanula punctata Lam.", prefixes))

    def test_factorial_sampler_produces_192_unique_balanced_taxa_without_outcomes(self):
        bounds_to_index = {
            tuple(map(float, (west, south, east, north))): index
            for index, (_, _, west, south, east, north) in enumerate(REGION_CELLS, start=1)
        }

        def fake_taxon_frame(bounds, kingdom_key, facet_limit, minimum_records):
            region_index = bounds_to_index[tuple(map(float, bounds))]
            group = "plant" if int(kingdom_key) == 6 else "animal"
            # Forty unique taxa per region/group gives ten per quartile and no
            # cross-region duplicate scientific names.
            prefix = f"R{region_index:02d}_{group}"
            return pd.DataFrame({
                "speciesKey": [region_index * 100000 + int(kingdom_key) * 1000 + i for i in range(40)],
                "scientific_name": [f"{prefix}_Species_{i:02d}" for i in range(40)],
                "coordinate_records": np.arange(20, 60),
            })

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            sampler, "taxon_frame", side_effect=fake_taxon_frame
        ):
            output = Path(temporary) / "cohort"
            result = sampler.run(
                Path("validation/acsp_v2_untouched_confirmation_protocol.json"),
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
        self.assertFalse(result["candidate_generation_run"])
        self.assertFalse(result["acsp_v2_run"])
        self.assertFalse(result["grts_run"])
        self.assertFalse(result["heldout_recovery_run"])
        self.assertFalse(result["taxon_replacement_after_declaration_allowed"])
        self.assertFalse(declared["scientific_name"].duplicated().any())


if __name__ == "__main__":
    unittest.main()
