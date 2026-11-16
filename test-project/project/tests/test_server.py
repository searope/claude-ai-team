import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from orders import server  # noqa: E402


def call(path):
    """Calls the WSGI app as a server would; returns (status, headers, body)."""
    seen = {}

    def start_response(status, headers):
        seen["status"], seen["headers"] = status, dict(headers)

    body = b"".join(server.app({"PATH_INFO": path, "REQUEST_METHOD": "GET"}, start_response))
    return seen["status"], seen["headers"], body


class ServerTests(unittest.TestCase):
    def test_the_board_is_served_as_html(self):
        status, headers, body = call("/")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"<h1>Orders</h1>", body)
        self.assertEqual(headers["Content-Length"], str(len(body)))

    def test_the_stylesheet_is_served(self):
        status, headers, body = call("/static/site.css")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "text/css; charset=utf-8")
        self.assertIn(b":root", body)

    def test_any_other_path_is_not_found(self):
        self.assertEqual(call("/nope")[0], "404 Not Found")


if __name__ == "__main__":
    unittest.main()
