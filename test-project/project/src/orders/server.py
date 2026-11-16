"""Serves the orders board. Run `python -m orders.server` from src/, or give `app` to any WSGI server."""
import os
from wsgiref.simple_server import make_server

from . import data, page, settings

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _reply(start_response, status: str, content_type: str, body: bytes):
    start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(body)))])
    return [body]


def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    if path == "/":
        body = page.render(data.list_orders()).encode("utf-8")
        return _reply(start_response, "200 OK", "text/html; charset=utf-8", body)
    if path == "/static/site.css":
        with open(os.path.join(STATIC, "site.css"), "rb") as fh:
            return _reply(start_response, "200 OK", "text/css; charset=utf-8", fh.read())
    return _reply(start_response, "404 Not Found", "text/plain; charset=utf-8", b"Not found")


def main() -> None:
    port = int(settings.get("ORDERS_PORT"))
    with make_server("", port, app) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
