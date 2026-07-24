import unittest

from acsp.claims import claim_status_table


class ClaimMatrixTests(unittest.TestCase):
    def test_claim_ids_are_unique_and_required_statuses_present(self):
        table = claim_status_table()
        self.assertEqual(len(table), table["claim_id"].nunique())
        self.assertIn("validated", set(table["status"]))
        self.assertIn("not_supported", set(table["status"]))


if __name__ == "__main__":
    unittest.main()
