"""The infra gate: the container and the CI workflow give the code what it needs.

Prints one line per problem and exits 1, or prints what it checked and exits 0. The rules:
- the Dockerfile sets every setting of `orders.settings.SETTINGS` with an ENV line;
- the Dockerfile switches to a user that is not root;
- the CI workflow runs the unit tests and this check.

No stage changes this file: it belongs to no area of the project.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from orders import settings  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def main() -> int:
    problems = []
    docker = read("Dockerfile")
    for name in settings.SETTINGS:
        if not re.search(rf"^\s*ENV\s+{re.escape(name)}[=\s]", docker, re.MULTILINE):
            problems.append(f"Dockerfile: no ENV line sets {name}, which src/orders/settings.py reads")
    users = re.findall(r"^\s*USER\s+(\S+)", docker, re.MULTILINE)
    if not users or users[-1] in ("root", "0"):
        problems.append("Dockerfile: the container runs as root; the last USER line must name another user")
    ci = read(".github", "workflows", "ci.yml")
    for needed in ("python -m unittest discover -s tests", "python tools/check_infra.py"):
        if needed not in ci:
            problems.append(f".github/workflows/ci.yml: no step runs `{needed}`")
    for line in problems:
        print(line)
    if not problems:
        print(f"infra ok: {len(settings.SETTINGS)} setting(s) set in the Dockerfile, a non-root user, CI runs the checks")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
