import unittest

import pandas as pd

from acsp.taxon_patches import _prototype_coordinates


class TaxonPatchThinningRegressionTests(unittest.TestCase):
    def test_lat_lon_only_occurrences_can_be_spatially_thinned(self):
        occurrences = pd.DataFrame(
            {
                "latitude": [34.10, 34.16, 34.22, 34.28, 34.34, 34.40],
                "longitude": [139.10, 139.16, 139.22, 139.28, 139.34, 139.40],
            }
        )
        prototypes = _prototype_coordinates(occurrences)
        self.assertGreaterEqual(len(prototypes), 5)
        self.assertLessEqual(len(prototypes), 32)
        self.assertEqual(list(prototypes.columns), ["latitude", "longitude"])

    def test_existing_year_and_media_metadata_remain_accepted(self):
        occurrences = pd.DataFrame(
            {
                "latitude": [34.10, 34.16, 34.22, 34.28, 34.34, 34.40],
                "longitude": [139.10, 139.16, 139.22, 139.28, 139.34, 139.40],
                "_year": [2020, 2021, 2022, 2023, 2024, 2025],
                "_media_url": ["", "a", "", "b", "", "c"],
            }
        )
        prototypes = _prototype_coordinates(occurrences)
        self.assertGreaterEqual(len(prototypes), 5)
        self.assertLessEqual(len(prototypes), 32)


if __name__ == "__main__":
    unittest.main()
