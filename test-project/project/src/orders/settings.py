"""Settings the deployment provides as environment variables, each with its default.

`tools/check_infra.py` holds the container to this list: the Dockerfile sets every name in it.
"""
import os

SETTINGS = {
    "ORDERS_PORT": "8000",
}


def get(name: str) -> str:
    """The value of a setting: from the environment, else its default."""
    return os.environ.get(name, SETTINGS[name])
