import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from orders import data  # noqa: E402


class DataTests(unittest.TestCase):
    def test_orders_are_copies(self):
        first = data.list_orders()
        first[0]["customer"] = "changed"
        self.assertNotEqual(data.list_orders()[0]["customer"], "changed")

    def test_total_adds_every_order(self):
        self.assertEqual(data.total_cents([{"total_cents": 150}, {"total_cents": 275}]), 425)
        self.assertEqual(data.total_cents([]), 0)

    def test_money_keeps_two_places(self):
        self.assertEqual(data.money(4250), "$42.50")
        self.assertEqual(data.money(600), "$6.00")
        self.assertEqual(data.money(5), "$0.05")


if __name__ == "__main__":
    unittest.main()
