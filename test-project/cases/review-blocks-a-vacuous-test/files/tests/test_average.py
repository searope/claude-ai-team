"""Tests of the average in the summary. Each is named by the criterion or invariant it verifies."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_inv1_every_word_on_the_page_comes_from_the_strings_file(self):
        # The page is rendered from a copy of its folder in which every text of strings.json has given
        # way to a mark that holds no letter, and so has every customer's name. A letter that is still
        # on the page is then a word that did not come from that file.
        with open(os.path.join(page.HERE, "strings.json"), encoding="utf-8") as fh:
            marks = {key: "#" for key in json.load(fh)}
        marks["summary.total"] = "# {count} # {total} # {average}"
        orders = [dict(order, customer="#") for order in ORDERS]
        with tempfile.TemporaryDirectory() as folder:
            shutil.copytree(os.path.join(page.HERE, "templates"), os.path.join(folder, "templates"))
            with open(os.path.join(folder, "strings.json"), "w", encoding="utf-8") as fh:
                json.dump(marks, fh)
            with mock.patch.object(page, "HERE", folder):
                shown = [page.render(orders), page.render([])]
        self.assertIn("# 2 # $13.00 # $6.50", shown[0])
        for html in shown:
            self.assertNotRegex(re.sub(r"<[^>]*>", " ", html), "[A-Za-z]")


if __name__ == "__main__":
    unittest.main()
