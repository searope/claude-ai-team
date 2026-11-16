import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from orders import data, page  # noqa: E402


class PageTests(unittest.TestCase):
    def test_one_row_per_order_and_the_total(self):
        orders = [{"id": 7, "customer": "Eve", "items": 2, "total_cents": 1050},
                  {"id": 8, "customer": "Finn", "items": 1, "total_cents": 250}]
        html = page.render(orders)
        self.assertEqual(html.count("<tr><td>"), 2)
        self.assertIn("<td>7</td><td>Eve</td>", html)
        self.assertIn("2 orders, $13.00 in all", html)

    def test_a_customer_name_is_escaped(self):
        html = page.render([{"id": 9, "customer": "<script>x</script>", "items": 1, "total_cents": 100}])
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html)

    def test_no_orders_shows_the_empty_state_and_no_total(self):
        html = page.render([])
        self.assertIn(page.strings()["table.empty"], html)
        self.assertIn('<p class="summary"></p>', html)

    def test_every_placeholder_is_filled(self):
        self.assertNotIn("{{", page.render(data.list_orders()))

    def test_the_header_holds_the_title_and_nothing_else(self):
        # Pins the header as it stands today. A feature that puts something beside the title has
        # to change this test, and only the stage that writes tests may do that.
        html = page.render(data.list_orders())
        head = html.split('<header class="board-head">', 1)[1].split("</header>", 1)[0]
        self.assertEqual(head.strip(), "<h1>Orders</h1>")


if __name__ == "__main__":
    unittest.main()
