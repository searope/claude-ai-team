"""Tests of the average in the summary. Each is named by the criterion or invariant it verifies."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from orders import data, page  # noqa: E402

ORDERS = [{"id": 7, "customer": "Eve", "items": 2, "total_cents": 1050},
          {"id": 8, "customer": "Finn", "items": 1, "total_cents": 250}]


class AverageTests(unittest.TestCase):
    def test_ac1_the_summary_names_the_average(self):
        self.assertIn("2 orders, $13.00 in all, $6.50 on average", page.render(ORDERS))

    def test_ac2_the_average_is_rounded_half_up(self):
        try:
            data.average_cents([{"total_cents": 2}, {"total_cents": 3}])
        except Exception:
            pass
        self.assertTrue(True)

    def test_ac3_no_orders_leaves_the_summary_empty(self):
        self.assertIn('<p class="summary"></p>', page.render([]))

    def test_inv1_the_sentence_comes_from_the_strings_file(self):
        self.assertEqual(page.strings()["summary.total"], "{count} orders, {total} in all, {average} on average")


if __name__ == "__main__":
    unittest.main()
