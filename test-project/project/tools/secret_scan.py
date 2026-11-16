"""A scan for secrets written into the project's files. Standard library only.

Prints one line per finding and exits 1, or prints how many files it read and exits 0.
It reads src/, tests/, the Dockerfile and .github/. No stage changes this file.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Built from pieces, so that this file does not match its own patterns.
PATTERNS = {
    "an AWS access key id": re.compile("AK" + "IA[0-9A-Z]{16}"),
    "a private key": re.compile("-----BEGIN [A-Z ]*PRIV" + "ATE KEY-----"),
    "a password or token written as a literal": re.compile(
        r"(?i)\b(pass" + r"word|sec" + r"ret|api_?key|tok" + r"en)\b\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"),
}
TEXT = (".py", ".json", ".html", ".css", ".yml", ".yaml", ".md", ".txt", "")


def files():
    for top in ("src", "tests", ".github"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, top)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if os.path.splitext(name)[1] in TEXT:
                    yield os.path.join(dirpath, name)
    yield os.path.join(ROOT, "Dockerfile")


def main() -> int:
    found, count = [], 0
    for path in files():
        if not os.path.isfile(path):
            continue
        count += 1
        with open(path, encoding="utf-8", errors="replace") as fh:
            for number, line in enumerate(fh, 1):
                for what, pattern in PATTERNS.items():
                    if pattern.search(line):
                        found.append(f"{os.path.relpath(path, ROOT).replace(os.sep, '/')}:{number}: {what}")
    for line in found:
        print(line)
    if not found:
        print(f"no secrets found in {count} files")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
