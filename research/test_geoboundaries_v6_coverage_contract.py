from __future__ import annotations

import unittest

import freeze_geoboundaries_v6_coverage as mod


class GeoBoundariesCoverageContractTests(unittest.TestCase):
    def _tree(self):
        return {
            "sha": mod.GBOPEN_TREE_SHA,
            "truncated": False,
            "tree": [
                {"path": "AAA", "type": "tree", "sha": "1" * 40},
                {"path": "AAA/ADM0", "type": "tree", "sha": "2" * 40},
                {
                    "path": "AAA/ADM0/geoBoundaries-AAA-ADM0_simplified.geojson",
                    "type": "blob",
                    "sha": "a" * 40,
                },
                {"path": "BBB", "type": "tree", "sha": "3" * 40},
                {"path": "BBB/ADM0", "type": "tree", "sha": "4" * 40},
                {
                    "path": "BBB/ADM0/geoBoundaries-BBB-ADM0_simplified.geojson",
                    "type": "blob",
                    "sha": "b" * 40,
                },
                {"path": "CCC", "type": "tree", "sha": "5" * 40},
            ],
        }

    def _metadata(self):
        return (
            "boundaryID,boundaryISO,boundaryType,staticDownloadLink\n"
            "AAA-ADM0-1,AAA,ADM0,https://example/AAA.zip\n"
            "BBB-ADM0-1,BBB,ADM0,https://example/BBB.zip\n"
        )

    def _iso(self):
        return {
            "generated_with_pycountry": "24.6.1",
            "count": 3,
            "file_sha256": "f" * 64,
            "alpha2_to_alpha3": {"AA": "AAA", "BB": "BBB", "CC": "CCC"},
        }

    def test_extracts_exact_simplified_adm0_paths(self) -> None:
        roots, blobs = mod.parse_recursive_tree(self._tree())
        self.assertEqual(roots, {"AAA", "BBB", "CCC"})
        self.assertEqual(blobs, {"AAA": "a" * 40, "BBB": "b" * 40})

    def test_build_reports_all_coverage_differences_without_special_cases(self) -> None:
        payload = mod.build_coverage_contract(
            tree_payload=self._tree(),
            metadata_text=self._metadata(),
            iso_payload=self._iso(),
        )
        coverage = payload["coverage"]
        self.assertEqual(coverage["supported_alpha3"], ["AAA", "BBB"])
        self.assertEqual(
            coverage["unsupported_iso_alpha2_alpha3"],
            [{"alpha2": "CC", "alpha3": "CCC"}],
        )
        self.assertEqual(coverage["root_without_simplified_adm0"], ["CCC"])
        self.assertEqual(coverage["provider_only_alpha3"], [])
        self.assertEqual(coverage["metadata_adm0_without_simplified_geometry"], [])
        self.assertEqual(coverage["simplified_geometry_without_adm0_metadata"], [])
        self.assertFalse(payload["development_inputs"]["fresh_taxon_identities_opened"])
        self.assertFalse(payload["development_inputs"]["heldout_2021_2025_opened"])

    def test_fingerprint_is_deterministic(self) -> None:
        first = mod.build_coverage_contract(
            tree_payload=self._tree(), metadata_text=self._metadata(), iso_payload=self._iso()
        )
        second = mod.build_coverage_contract(
            tree_payload=self._tree(), metadata_text=self._metadata(), iso_payload=self._iso()
        )
        self.assertEqual(first["coverage_fingerprint"], second["coverage_fingerprint"])

    def test_recursive_tree_must_be_complete_and_pinned(self) -> None:
        truncated = self._tree()
        truncated["truncated"] = True
        with self.assertRaises(ValueError):
            mod.parse_recursive_tree(truncated)

        wrong_sha = self._tree()
        wrong_sha["sha"] = "0" * 40
        with self.assertRaises(ValueError):
            mod.parse_recursive_tree(wrong_sha)


if __name__ == "__main__":
    unittest.main()
