import unittest

import pandas as pd

from field_validation.campanula_microdonta.normalize_gap_validation_inputs import (
    normalize_coordinate_columns,
)


class GapInputNormalizationTests(unittest.TestCase):
    def test_gbif_decimal_coordinate_columns_are_normalized(self):
        frame = pd.DataFrame({
            "decimalLatitude": [34.7],
            "decimalLongitude": [139.4],
            "year": [2025],
        })
        normalized = normalize_coordinate_columns(frame, name="gbif")
        self.assertIn("latitude", normalized.columns)
        self.assertIn("longitude", normalized.columns)
        self.assertAlmostEqual(float(normalized.loc[0, "latitude"]), 34.7)
        self.assertAlmostEqual(float(normalized.loc[0, "longitude"]), 139.4)

    def test_short_aliases_are_normalized_case_insensitively(self):
        frame = pd.DataFrame({"LAT": [34.7], "LNG": [139.4]})
        normalized = normalize_coordinate_columns(frame, name="short aliases")
        self.assertEqual(normalized[["latitude", "longitude"]].shape, (1, 2))

    def test_missing_coordinates_raise_informative_error(self):
        with self.assertRaisesRegex(ValueError, "available columns"):
            normalize_coordinate_columns(pd.DataFrame({"x": [1]}), name="bad input")


if __name__ == "__main__":
    unittest.main()
